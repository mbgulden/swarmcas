from typing import List, Tuple

class Chunker:
    def __init__(self, target_size: int = 64 * 1024):
        self.target_size = target_size

def chunk(data: bytes, target_size: int = 64 * 1024) -> List[Tuple[int, bytes]]:
    chunks = []
    offset = 0
    while offset < len(data):
        end = min(offset + target_size, len(data))
        chunks.append((offset, data[offset:end]))
        offset = end
    return chunks

def reassemble(chunks: List[bytes]) -> bytes:
    return b"".join(chunks)
