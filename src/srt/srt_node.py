import tiktoken

class SRTNode:
    """SRT 자막의 한 블록(번호, 타임스탬프, 내용)을 나타내는 클래스"""
    def __init__(self, number: int, timestamp: str, text: str):
        self.number = number  # 자막 번호
        self.timestamp = timestamp  # 타임스탬프
        self.text = text.strip()  # 자막 내용

    def count_tokens(self, model="gpt-4o"):
        """이 노드의 텍스트(자막 내용) 토큰 개수 반환"""
        tokenizer = tiktoken.encoding_for_model(model)
        return len(tokenizer.encode(self.text))

    def __str__(self):
        """SRT 파일 형식의 문자열 반환"""
        return f"{self.number}\n{self.timestamp}\n{self.text}\n"
