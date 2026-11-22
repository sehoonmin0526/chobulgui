from src.srt.srt_node import SRTNode
from typing import List

class SRT:
    """SRT 파일을 저장하고 관리하는 클래스"""
    def __init__(self):
        self.nodes: List[SRTNode] = []  # SRTNode 리스트

    def add_node(self, number: int, timestamp: str, text: str):
        """새로운 SRT 노드 추가"""
        self.nodes.append(SRTNode(number, timestamp, text))

    def append_node(self, node: SRTNode):
        self.nodes.append(node)

    def count(self):
        """현재 저장된 SRT 노드 개수 반환"""
        return len(self.nodes)
    
    def count_total_tokens(self, model="gpt-4o"):
        """전체 SRT 자막의 총 토큰 개수 반환"""
        return sum(node.count_tokens(model) for node in self.nodes)

    def get_text_range(self, start: int, end: int):
        """n부터 m까지 자막 내용만 리스트로 반환"""
        return [node.text for node in self.nodes[start:end]]
    
    def get_nodes(self):
        return self.nodes
    
    def get_all_text(self) -> str:
        return "\n".join(str(node) for node in self.nodes)

    def save(self, filename: str):
        """현재 SRT 데이터를 파일로 저장"""
        with open(filename, "w", encoding="utf-8") as file:
            file.write("\n".join(str(node) for node in self.nodes))
        print(f"✅ SRT 파일 저장 완료: {filename}")

    @classmethod
    def from_file(cls, filename: str):
        """SRT 파일을 읽어서 SRT 객체로 변환하는 클래스 메서드"""
        with open(filename, "r", encoding="utf-8") as file:
            text = file.read()
        return cls.from_text(text)

    @classmethod
    def from_text(cls, text: str):
        """SRT 형식의 문자열을 SRT 객체로 변환하는 클래스 메서드"""
        lines = text.split("\n")
        srt_instance = cls()
        buffer = []
        number = None
        timestamp = None

        for line in lines:
            line = line.strip()
            if line.isdigit():
                if buffer:  # 이전 블록 저장
                    srt_instance.add_node(number, timestamp, "\n".join(buffer))
                    buffer = []
                number = int(line)  # 현재 블록 번호 저장
            elif "-->" in line:
                timestamp = line  # 타임스탬프 저장
            elif line == "":
                continue
            else:
                buffer.append(line)  # 자막 내용 추가

        if buffer:
            srt_instance.add_node(number, timestamp, "\n".join(buffer))

        return srt_instance