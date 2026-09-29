class Chunker:
    def __init__(self, target_size: int = 64 * 1024):
        self.target_size = target_size


def chunk(data: bytes, target_size: int = 64 * 1024) -> list[tuple[int, bytes]]:
    chunks = []
    offset = 0
    while offset < len(data):
        end = min(offset + target_size, len(data))
        chunks.append((offset, data[offset:end]))
        offset = end
    return chunks


def reassemble(chunks: list[bytes]) -> bytes:
    return b"".join(chunks)
