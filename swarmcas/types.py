from __future__ import annotations

from dataclasses import dataclass, field


class CASError(Exception):
    pass


class BlobNotFoundError(CASError):
    pass


class IntegrityError(CASError):
    pass


@dataclass
class BlobRef:
    digest: str
    size_bytes: int
    chunk_count: int
    created_at: float
    content_type: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class ChunkRef:
    digest: str
    offset: int
    size: int


@dataclass
class StoreStats:
    total_blobs: int
    total_bytes: int
    total_chunks: int
    dedup_savings_bytes: int


@dataclass
class SyncTarget:
    target_type: str
    path_or_url: str
    credentials: dict[str, str] | None = None
