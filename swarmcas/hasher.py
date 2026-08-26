import hashlib
from pathlib import Path
from typing import List

def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk_data in iter(lambda: f.read(65536), b""):
            h.update(chunk_data)
    return h.hexdigest()

def verify_integrity(data: bytes, expected_digest: str) -> bool:
    return content_hash(data) == expected_digest

def merkle_root(digests: List[str]) -> str:
    if not digests:
        return content_hash(b"")
    current_level = digests
    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i+1] if i + 1 < len(current_level) else left
            next_level.append(content_hash((left + right).encode("utf-8")))
        current_level = next_level
    return current_level[0]
