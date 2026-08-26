import os
from pathlib import Path

base = Path(r"c:\Users\Michael Gulden\Github\swarmcas")
base.mkdir(parents=True, exist_ok=True)
(base / "swarmcas").mkdir(exist_ok=True)
(base / "tests").mkdir(exist_ok=True)

def write_file(rel_path, content):
    p = base / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")

write_file("pyproject.toml", """
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "swarmcas"
version = "0.1.0"
description = "Content-addressed immutable artifact and blob store"
readme = "README.md"
authors = [{ name = "Michael Gulden", email = "mbgulden@gmail.com" }]
license = { text = "MIT" }
requires-python = ">=3.9"
classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Typing :: Typed",
]
dependencies = []

[project.optional-dependencies]
test = ["pytest>=7.0.0", "pytest-asyncio>=0.20.0", "mypy>=1.0.0"]

[project.scripts]
swarmcas = "swarmcas.cli:main"

[tool.setuptools.packages.find]
where = ["."]

[tool.setuptools.package-data]
swarmcas = ["py.typed"]
""")

write_file("LICENSE", "MIT License")
write_file("README.md", "# swarmcas\nContent-addressed immutable artifact and blob store.")

write_file("swarmcas/__init__.py", """
from .types import CASError, BlobNotFoundError, IntegrityError, BlobRef, ChunkRef, StoreStats, SyncTarget
from .hasher import content_hash, file_hash, verify_integrity, merkle_root
from .chunks import Chunker, chunk, reassemble
from .store import ContentStore
from .gc import GarbageCollector
from .sync import SyncAdapter, LocalSyncAdapter

__all__ = [
    "CASError",
    "BlobNotFoundError",
    "IntegrityError",
    "BlobRef",
    "ChunkRef",
    "StoreStats",
    "SyncTarget",
    "content_hash",
    "file_hash",
    "verify_integrity",
    "merkle_root",
    "Chunker",
    "chunk",
    "reassemble",
    "ContentStore",
    "GarbageCollector",
    "SyncAdapter",
    "LocalSyncAdapter"
]
""")

write_file("swarmcas/py.typed", "")

write_file("swarmcas/types.py", """
from dataclasses import dataclass, field
from typing import Optional, Dict

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
    metadata: Dict[str, str] = field(default_factory=dict)

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
    credentials: Optional[Dict[str, str]] = None
""")

write_file("swarmcas/hasher.py", """
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
""")

write_file("swarmcas/chunks.py", """
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
""")

write_file("swarmcas/store.py", """
import sqlite3
import json
import time
import zlib
from pathlib import Path
from typing import Optional, Dict, List
from .types import BlobRef, StoreStats, BlobNotFoundError, IntegrityError
from .hasher import content_hash
from .chunks import chunk, reassemble

class ContentStore:
    def __init__(self, root_dir: Path):
        self.root_dir = Path(root_dir)
        self.objects_dir = self.root_dir / "objects"
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root_dir / "index.db"
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS blobs (
                    digest TEXT PRIMARY KEY,
                    size_bytes INTEGER,
                    chunk_count INTEGER,
                    created_at REAL,
                    content_type TEXT,
                    metadata TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS chunks (
                    digest TEXT PRIMARY KEY,
                    size_bytes INTEGER,
                    ref_count INTEGER
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS blob_chunks (
                    blob_digest TEXT,
                    chunk_digest TEXT,
                    chunk_index INTEGER,
                    offset INTEGER,
                    PRIMARY KEY (blob_digest, chunk_index)
                )
            ''')

    def _get_object_path(self, digest: str) -> Path:
        p = self.objects_dir / digest[:2] / digest[2:4]
        p.mkdir(parents=True, exist_ok=True)
        return p / digest

    def put(self, data: bytes, content_type: str = "", metadata: Optional[Dict[str, str]] = None) -> BlobRef:
        blob_digest = content_hash(data)
        if self.exists(blob_digest):
            return self.get_ref(blob_digest)

        chunks_data = chunk(data)
        metadata = metadata or {}
        
        with sqlite3.connect(self.db_path) as conn:
            for idx, (offset, cdata) in enumerate(chunks_data):
                cdigest = content_hash(cdata)
                cpath = self._get_object_path(cdigest)
                
                if not cpath.exists():
                    tmp_path = cpath.with_suffix(".tmp")
                    with open(tmp_path, "wb") as f:
                        f.write(zlib.compress(cdata))
                    tmp_path.rename(cpath)
                    conn.execute("INSERT INTO chunks (digest, size_bytes, ref_count) VALUES (?, ?, ?)", 
                                 (cdigest, len(cdata), 1))
                else:
                    conn.execute("UPDATE chunks SET ref_count = ref_count + 1 WHERE digest = ?", (cdigest,))
                
                conn.execute("INSERT INTO blob_chunks (blob_digest, chunk_digest, chunk_index, offset) VALUES (?, ?, ?, ?)",
                             (blob_digest, cdigest, idx, offset))

            created_at = time.time()
            conn.execute("INSERT INTO blobs (digest, size_bytes, chunk_count, created_at, content_type, metadata) VALUES (?, ?, ?, ?, ?, ?)",
                         (blob_digest, len(data), len(chunks_data), created_at, content_type, json.dumps(metadata)))

        return BlobRef(
            digest=blob_digest,
            size_bytes=len(data),
            chunk_count=len(chunks_data),
            created_at=created_at,
            content_type=content_type,
            metadata=metadata
        )

    def put_file(self, path: Path, content_type: str = "", metadata: Optional[Dict[str, str]] = None) -> BlobRef:
        with open(path, "rb") as f:
            data = f.read()
        return self.put(data, content_type, metadata)

    def get(self, digest: str) -> bytes:
        if not self.exists(digest):
            raise BlobNotFoundError(f"Blob {digest} not found")

        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT chunk_digest FROM blob_chunks WHERE blob_digest = ? ORDER BY chunk_index", (digest,))
            rows = c.fetchall()

        chunks_data = []
        for (cdigest,) in rows:
            cpath = self._get_object_path(cdigest)
            if not cpath.exists():
                raise IntegrityError(f"Missing chunk {cdigest}")
            with open(cpath, "rb") as f:
                cdata = zlib.decompress(f.read())
                if content_hash(cdata) != cdigest:
                    raise IntegrityError(f"Corrupted chunk {cdigest}")
                chunks_data.append(cdata)

        data = reassemble(chunks_data)
        if content_hash(data) != digest:
            raise IntegrityError(f"Corrupted blob {digest}")
        return data

    def get_ref(self, digest: str) -> BlobRef:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT size_bytes, chunk_count, created_at, content_type, metadata FROM blobs WHERE digest = ?", (digest,))
            row = c.fetchone()
            if not row:
                raise BlobNotFoundError(f"Blob {digest} not found")
            return BlobRef(
                digest=digest,
                size_bytes=row[0],
                chunk_count=row[1],
                created_at=row[2],
                content_type=row[3],
                metadata=json.loads(row[4])
            )

    def exists(self, digest: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM blobs WHERE digest = ?", (digest,))
            return c.fetchone() is not None

    def verify(self, digest: str) -> bool:
        try:
            self.get(digest)
            return True
        except (BlobNotFoundError, IntegrityError):
            return False

    def delete(self, digest: str):
        if not self.exists(digest):
            return

        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT chunk_digest FROM blob_chunks WHERE blob_digest = ?", (digest,))
            chunk_digests = [r[0] for r in c.fetchall()]

            conn.execute("DELETE FROM blobs WHERE digest = ?", (digest,))
            conn.execute("DELETE FROM blob_chunks WHERE blob_digest = ?", (digest,))

            for cdigest in chunk_digests:
                conn.execute("UPDATE chunks SET ref_count = ref_count - 1 WHERE digest = ?", (cdigest,))
                c.execute("SELECT ref_count FROM chunks WHERE digest = ?", (cdigest,))
                if c.fetchone()[0] <= 0:
                    conn.execute("DELETE FROM chunks WHERE digest = ?", (cdigest,))
                    cpath = self._get_object_path(cdigest)
                    if cpath.exists():
                        cpath.unlink()
                        
    def list_blobs(self, prefix: str = "") -> List[BlobRef]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            query = "SELECT digest, size_bytes, chunk_count, created_at, content_type, metadata FROM blobs"
            params = ()
            if prefix:
                query += " WHERE digest LIKE ?"
                params = (f"{prefix}%",)
            c.execute(query, params)
            return [BlobRef(r[0], r[1], r[2], r[3], r[4], json.loads(r[5])) for r in c.fetchall()]

    def stats(self) -> StoreStats:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*), SUM(size_bytes) FROM blobs")
            blobs_row = c.fetchone()
            total_blobs = blobs_row[0] or 0
            total_bytes = blobs_row[1] or 0

            c.execute("SELECT COUNT(*), SUM(size_bytes * (ref_count - 1)) FROM chunks")
            chunks_row = c.fetchone()
            total_chunks = chunks_row[0] or 0
            dedup_savings_bytes = chunks_row[1] or 0

        return StoreStats(
            total_blobs=total_blobs,
            total_bytes=total_bytes,
            total_chunks=total_chunks,
            dedup_savings_bytes=dedup_savings_bytes
        )
""")

write_file("swarmcas/gc.py", """
import time
import sqlite3
from typing import List
from .store import ContentStore

class GarbageCollector:
    def collect(self, store: ContentStore, max_age_days: int) -> int:
        cutoff_time = time.time() - (max_age_days * 86400)
        removed_count = 0
        with sqlite3.connect(store.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT digest FROM blobs WHERE created_at < ?", (cutoff_time,))
            old_blobs = [r[0] for r in c.fetchall()]
        
        for digest in old_blobs:
            store.delete(digest)
            removed_count += 1
            
        return removed_count

    def verify_all(self, store: ContentStore) -> List[str]:
        corrupted = []
        for blob_ref in store.list_blobs():
            if not store.verify(blob_ref.digest):
                corrupted.append(blob_ref.digest)
        return corrupted
""")

write_file("swarmcas/sync.py", """
from .store import ContentStore

class SyncAdapter:
    pass

class LocalSyncAdapter(SyncAdapter):
    def sync(self, source: ContentStore, target: ContentStore, dry_run: bool = False) -> int:
        synced_count = 0
        source_blobs = source.list_blobs()
        for b in source_blobs:
            if not target.exists(b.digest):
                if not dry_run:
                    data = source.get(b.digest)
                    target.put(data, b.content_type, b.metadata)
                synced_count += 1
        return synced_count
""")

write_file("swarmcas/cli.py", """
import argparse
import sys
from pathlib import Path
from .store import ContentStore
from .gc import GarbageCollector
from .sync import LocalSyncAdapter

def main():
    parser = argparse.ArgumentParser(prog="swarmcas", description="Content-addressed immutable artifact and blob store")
    parser.add_argument("--store", type=str, default=".swarmcas", help="Path to store directory")
    subparsers = parser.add_subparsers(dest="command")

    put_p = subparsers.add_parser("put", help="Put a file into the store")
    put_p.add_argument("file", type=str)
    
    get_p = subparsers.add_parser("get", help="Get a blob by digest")
    get_p.add_argument("digest", type=str)
    get_p.add_argument("out", type=str)

    verify_p = subparsers.add_parser("verify", help="Verify a blob by digest")
    verify_p.add_argument("digest", type=str)

    subparsers.add_parser("gc", help="Run garbage collection")
    subparsers.add_parser("stats", help="Show store stats")

    sync_p = subparsers.add_parser("sync", help="Sync to target store")
    sync_p.add_argument("target", type=str)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    store = ContentStore(Path(args.store))

    if args.command == "put":
        ref = store.put_file(Path(args.file))
        print(ref.digest)
    elif args.command == "get":
        data = store.get(args.digest)
        with open(args.out, "wb") as f:
            f.write(data)
        print(f"Wrote to {args.out}")
    elif args.command == "verify":
        if store.verify(args.digest):
            print("OK")
        else:
            print("Corrupted or missing")
            sys.exit(1)
    elif args.command == "gc":
        gc = GarbageCollector()
        removed = gc.collect(store, max_age_days=0)
        print(f"Removed {removed} items")
    elif args.command == "stats":
        stats = store.stats()
        print(stats)
    elif args.command == "sync":
        target_store = ContentStore(Path(args.target))
        sync_adapter = LocalSyncAdapter()
        count = sync_adapter.sync(store, target_store)
        print(f"Synced {count} blobs")

if __name__ == "__main__":
    main()
""")

write_file("tests/__init__.py", "")

write_file("tests/test_hasher.py", """
import tempfile
from pathlib import Path
from swarmcas.hasher import content_hash, file_hash, verify_integrity, merkle_root

def test_content_hash():
    digest = content_hash(b"hello")
    assert digest == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"

def test_file_hash():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"hello")
        path = Path(f.name)
    digest = file_hash(path)
    assert digest == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    path.unlink()

def test_verify_integrity():
    assert verify_integrity(b"hello", "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")
    assert not verify_integrity(b"hello", "wrong")

def test_merkle_root():
    root = merkle_root(["a", "b"])
    assert isinstance(root, str)
    assert len(root) == 64
""")

write_file("tests/test_chunks.py", """
from swarmcas.chunks import chunk, reassemble

def test_chunking():
    data = b"a" * 1000
    chunks = chunk(data, target_size=100)
    assert len(chunks) == 10
    assert chunks[0][0] == 0
    assert len(chunks[0][1]) == 100

def test_reassemble():
    data = b"hello world"
    chunks_list = [c[1] for c in chunk(data, target_size=5)]
    assert reassemble(chunks_list) == data
""")

write_file("tests/test_store.py", """
import tempfile
from pathlib import Path
from swarmcas.store import ContentStore
from swarmcas.types import BlobNotFoundError, IntegrityError

def test_put_get():
    with tempfile.TemporaryDirectory() as d:
        store = ContentStore(Path(d))
        ref = store.put(b"test data")
        assert ref.size_bytes == 9
        
        data = store.get(ref.digest)
        assert data == b"test data"

def test_exists():
    with tempfile.TemporaryDirectory() as d:
        store = ContentStore(Path(d))
        ref = store.put(b"test data")
        assert store.exists(ref.digest)
        assert not store.exists("madeup")

def test_stats():
    with tempfile.TemporaryDirectory() as d:
        store = ContentStore(Path(d))
        store.put(b"test data")
        stats = store.stats()
        assert stats.total_blobs == 1
        assert stats.total_bytes == 9

def test_verify():
    with tempfile.TemporaryDirectory() as d:
        store = ContentStore(Path(d))
        ref = store.put(b"test data")
        assert store.verify(ref.digest)
        assert not store.verify("madeup")
""")

write_file("tests/test_gc.py", """
import tempfile
from pathlib import Path
from swarmcas.store import ContentStore
from swarmcas.gc import GarbageCollector

def test_gc_collect():
    with tempfile.TemporaryDirectory() as d:
        store = ContentStore(Path(d))
        ref = store.put(b"test data")
        gc = GarbageCollector()
        
        # Max age 1 day, shouldn't collect
        removed = gc.collect(store, max_age_days=1)
        assert removed == 0
        assert store.exists(ref.digest)

        # Max age -1 days (in future), should collect
        removed = gc.collect(store, max_age_days=-1)
        assert removed == 1
        assert not store.exists(ref.digest)
""")

write_file("tests/test_sync.py", """
import tempfile
from pathlib import Path
from swarmcas.store import ContentStore
from swarmcas.sync import LocalSyncAdapter

def test_local_sync():
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        store1 = ContentStore(Path(d1))
        store2 = ContentStore(Path(d2))
        
        ref = store1.put(b"test data")
        
        sync = LocalSyncAdapter()
        synced = sync.sync(store1, store2)
        
        assert synced == 1
        assert store2.exists(ref.digest)
        assert store2.get(ref.digest) == b"test data"
""")

write_file("tests/test_cli.py", """
import sys
from unittest.mock import patch
from swarmcas.cli import main

def test_cli_help(capsys):
    with patch.object(sys, 'argv', ['swarmcas', '--help']):
        try:
            main()
        except SystemExit:
            pass
    out, _ = capsys.readouterr()
    assert "Content-addressed immutable artifact and blob store" in out
""")
