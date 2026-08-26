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
        import contextlib
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn, conn:
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
        
        import contextlib
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn, conn:
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

        import contextlib
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn, conn:
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
        import contextlib
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn, conn:
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
        import contextlib
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn, conn:
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

        import contextlib
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn, conn:
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
        import contextlib
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn, conn:
            c = conn.cursor()
            query = "SELECT digest, size_bytes, chunk_count, created_at, content_type, metadata FROM blobs"
            params = ()
            if prefix:
                query += " WHERE digest LIKE ?"
                params = (f"{prefix}%",)
            c.execute(query, params)
            return [BlobRef(r[0], r[1], r[2], r[3], r[4], json.loads(r[5])) for r in c.fetchall()]

    def stats(self) -> StoreStats:
        import contextlib
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn, conn:
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
