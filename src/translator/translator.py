import asyncio
import re
import time
from openai import AsyncOpenAI

from src.srt.srt import SRT
from api_key import OPEN_AI_API_KEY
from src.logger import Logger

TAG_PATTERN = re.compile(r"^\[(\d+)\]\s?(.*)$")

FORMAT_INSTRUCTION = (
    "\n\n[형식 규칙] 입력은 '[번호] 원문' 형식의 줄들로 되어 있다. "
    "각 줄을 번역하고 '[번호] 번역문' 형식으로, 번호와 줄 순서를 그대로 유지해서 응답하라. "
    "번호를 추가/삭제/병합하지 말고, 입력과 동일한 줄 수로 응답하라."
)

DEFAULT_MODEL = "gpt-6.1-sol"

_EXCLUDE_SUBSTRINGS = (
    "embedding", "whisper", "tts", "dall-e", "moderation",
    "davinci", "babbage", "ada", "realtime", "transcribe",
    "audio", "image", "search", "computer-use", "codex",
)

class SRTTranslator:
    def __init__(self, system_msg=None, model=DEFAULT_MODEL):
        self.client = AsyncOpenAI(api_key=OPEN_AI_API_KEY)
        self.system_msg = system_msg
        self.model = model

        # Todo Configuration
        self.max_concurrent_requests = 30
        self.semaphore = asyncio.Semaphore(self.max_concurrent_requests)
        self.max_retries = 1

    @staticmethod
    def _is_chat_model(model_id: str) -> bool:
        lower = model_id.lower()
        if any(x in lower for x in _EXCLUDE_SUBSTRINGS):
            return False
        return lower.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-"))

    @staticmethod
    async def fetch_available_models() -> list:
        """사용 가능한 채팅용 모델 id 목록을 최신순으로 조회 (가격 정보는 API로 제공되지 않음)"""
        client = AsyncOpenAI(api_key=OPEN_AI_API_KEY)
        response = await client.models.list()
        models = [m for m in response.data if SRTTranslator._is_chat_model(m.id)]
        models.sort(key=lambda m: m.created, reverse=True)
        return [m.id for m in models]

    def set_progress_signal(self, progress_update):
        self.progress_update = progress_update

    def _emit_progress(self, done: int, total: int):
        if not total or not hasattr(self, "progress_update"):
            return
        self.progress_update.emit(min(int(done / total * 100), 100))

    def _log_stats(self, start_time, first_token_time, usage):
        end_time = time.perf_counter()
        total_sec = end_time - start_time
        if first_token_time is not None:
            wait_sec = first_token_time - start_time
            Logger.info(
                f"⏱ 소요 시간: 총 {total_sec:.1f}초 "
                f"(첫 출력까지 {wait_sec:.1f}초 + 출력 {end_time - first_token_time:.1f}초)"
            )
        else:
            Logger.info(f"⏱ 소요 시간: 총 {total_sec:.1f}초")

        if usage is None:
            Logger.warning("토큰 사용량 정보를 받지 못했습니다.")
            return

        completion_details = usage.completion_tokens_details
        prompt_details = usage.prompt_tokens_details
        reasoning = (completion_details.reasoning_tokens or 0) if completion_details else 0
        cached = (prompt_details.cached_tokens or 0) if prompt_details else 0
        output = usage.completion_tokens - reasoning
        reasoning_ratio = reasoning / usage.completion_tokens * 100 if usage.completion_tokens else 0

        Logger.info(
            f"🔢 토큰 [{self.model}]: 입력 {usage.prompt_tokens:,} (캐시 {cached:,}) / "
            f"출력 {usage.completion_tokens:,} = 생각 {reasoning:,} ({reasoning_ratio:.0f}%) + 번역문 {output:,}"
        )

    async def translate_text_async(self, text, total_nodes=0):
        """
        OpenAI GPT API를 사용하여 텍스트를 번역하는 함수 (스트리밍, [번호] 단위로 진행률 갱신).
        :param text: 번역할 원본 텍스트 ('[번호] 원문' 형식)
        :param total_nodes: 진행률 계산용 전체 줄 수
        :return: 번역된 텍스트 ('[번호] 번역문' 형식)
        """
        for attempt in range(self.max_retries):
            async with self.semaphore:
                try:
                    start_time = time.perf_counter()
                    first_token_time = None
                    usage = None

                    stream = await self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": f"{self.system_msg}.{FORMAT_INSTRUCTION}"},
                            {"role": "user", "content": text}
                        ],
                        stream=True,
                        stream_options={"include_usage": True}
                    )

                    full_text = ""
                    buffer = ""
                    done_count = 0

                    async for chunk in stream:
                        if chunk.usage:
                            usage = chunk.usage
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta.content
                        if not delta:
                            continue
                        if first_token_time is None:
                            first_token_time = time.perf_counter()
                        full_text += delta
                        buffer += delta

                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            if TAG_PATTERN.match(line.strip()):
                                done_count += 1
                                self._emit_progress(done_count, total_nodes)

                    if TAG_PATTERN.match(buffer.strip()):
                        done_count += 1
                        self._emit_progress(done_count, total_nodes)

                    self._log_stats(start_time, first_token_time, usage)
                    return full_text.strip()

                except Exception as e:
                    Logger.error(f"⚠️ 번역 실패 (시도 {attempt + 1}/{self.max_retries}): {e}")
                    await asyncio.sleep(2 ** attempt)  # exponential backoff

        Logger.error("최종 실패: 원본 유지")
        return text

    async def process_srt_async(self, text) -> SRT:
        srt = SRT.from_text(text)
        self.srt = srt
        self.total_nodes = srt.count()

        nodes = srt.get_nodes()
        self.original_texts = [node.text for node in nodes]
        tagged_input = "\n".join(
            f"[{i}] {node.text.replace(chr(10), ' ')}" for i, node in enumerate(nodes)
        )

        translated = await self.translate_text_async(tagged_input, total_nodes=self.total_nodes)

        translations = {}
        for line in translated.splitlines():
            match = TAG_PATTERN.match(line.strip())
            if match:
                translations[int(match.group(1))] = match.group(2).strip()

        for i, node in enumerate(nodes):
            if i in translations:
                node.text = translations[i]
            else:
                Logger.warning(f"[{i}] 번역 결과 누락, 원문 유지: {node.text}")

        return srt
