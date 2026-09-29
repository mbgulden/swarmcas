# 📦 SwarmCAS

[![CI](https://github.com/mbgulden/swarmcas/actions/workflows/ci.yml/badge.svg)](https://github.com/mbgulden/swarmcas/actions)
[![PyPI version](https://img.shields.io/badge/pypi-v0.1.0-blue.svg)](https://pypi.org/project/swarmcas/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Content-addressed immutable artifact and blob store.**
> *Store bytes once, address them forever by SHA-256. Automatic chunk-level deduplication, integrity verification on every read, garbage collection, and store-to-store sync.*

---

## 💡 Why SwarmCAS?

When many agents (or many runs of one agent) produce artifacts — build outputs, model files, evidence bundles, receipts — you want three properties:

- **Content addressing**: the same bytes always get the same name (the SHA-256 digest). No naming collisions, no stale-cache bugs.
- **Immutability with verification**: every read re-hashes the data. Corrupted or tampered bytes fail loudly instead of poisoning downstream work.
- **Deduplication**: identical 64 KiB chunks are stored once and reference-counted, even across different blobs — repeated artifacts cost almost nothing.

SwarmCAS gives you that as a small, dependency-free library plus a CLI: a directory on disk, a SQLite index, zlib-compressed chunks laid out like git objects (`objects/ab/cd/<digest>`).

---

## 🏛️ How it works

```
put(b"hello world")
        │
        ▼
┌─────────────────────┐
│  Chunk (64 KiB)     │─── split into fixed-size chunks
│  SHA-256 each chunk │─── chunk digest = content address
│  zlib-compress      │─── write once to objects/ab/cd/<digest>
└─────────┬───────────┘
          │  blob digest = SHA-256 of the full bytes
          ▼
┌─────────────────────┐
│  SQLite index       │─── blobs, chunks, blob→chunk mapping,
│  (index.db)         │    ref counts for dedup
└─────────────────────┘

get(digest) → reassemble chunks → re-hash → return bytes or raise IntegrityError
```

- Putting the same bytes twice returns the existing `BlobRef` — no duplicate storage.
- Two different blobs sharing identical chunks store those chunks once; `ContentStore.delete()` decrements ref counts and removes chunk files only when nothing references them.
- `get()` verifies every chunk's hash *and* the final blob hash; a mismatch raises `IntegrityError`.

---

## 📦 Installation

```bash
pip install swarmcas
```

*Pure Python standard library. Zero runtime dependencies.*

Requires Python 3.9+.

---

## 🚀 Quick start

### CLI

```bash
# Store a file — prints its SHA-256 digest
$ printf 'hello' > hello.txt
$ swarmcas put hello.txt
2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824

# Fetch it back by digest
$ swarmcas get 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824 hello-copy.txt
Wrote to hello-copy.txt

# Verify integrity (exit 0 + OK, or exit 1)
$ swarmcas verify 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
OK

# Store statistics
$ swarmcas stats
StoreStats(total_blobs=1, total_bytes=5, total_chunks=1, dedup_savings_bytes=0)

# Garbage-collect everything (CLI runs with max_age_days=0)
$ swarmcas gc
Removed 1 items

# Sync all blobs into another local store
$ swarmcas sync /backups/cas
Synced 1 blobs
```

The store lives in `./.swarmcas` by default; override with `--store /path/to/dir`.

### Python API

```python
from pathlib import Path
from swarmcas import ContentStore, GarbageCollector, LocalSyncAdapter

store = ContentStore(Path("./cas"))

# Store bytes or a file
ref = store.put(b"hello world", content_type="text/plain", metadata={"run": "42"})
print(ref.digest)          # SHA-256 of the bytes
print(ref.size_bytes)      # 11
print(ref.chunk_count)     # 1

# Read back — hashes verified on every read
data = store.get(ref.digest)
assert store.verify(ref.digest)

# Stats include dedup savings across all blobs
stats = store.stats()
print(stats.total_blobs, stats.dedup_savings_bytes)

# Find blobs by digest prefix
for blob in store.list_blobs(prefix="2cf2"):
    print(blob.digest, blob.size_bytes)

# Garbage-collect blobs older than N days
gc = GarbageCollector()
removed = gc.collect(store, max_age_days=30)
# Or audit the whole store for corruption
corrupted = gc.verify_all(store)   # list of bad digests (usually empty)

# Sync into a second store (skips blobs already present)
other = ContentStore(Path("./cas-backup"))
synced = LocalSyncAdapter().sync(store, other)
print(f"synced {synced} blobs")
```

### Hashing primitives

```python
from swarmcas import content_hash, file_hash, verify_integrity, merkle_root
from swarmcas import chunk, reassemble, Chunker

digest = content_hash(b"hello")                    # SHA-256 hex
digest = file_hash(Path("report.pdf"))             # streams the file, no full read
ok = verify_integrity(b"hello", digest)
root = merkle_root([digest_a, digest_b, digest_c]) # binary hash tree over digests

parts = chunk(data, target_size=64 * 1024)         # [(offset, bytes), ...]
assert reassemble([p[1] for p in parts]) == data
Chunker(target_size=256 * 1024)                    # configurable chunking policy object
```

---

## 🖥️ CLI reference

| Command | Usage | Notes |
|---|---|---|
| `put` | `swarmcas put <file>` | Prints the blob digest |
| `get` | `swarmcas get <digest> <out>` | Writes blob bytes to `<out>` |
| `verify` | `swarmcas verify <digest>` | `OK` (exit 0) or `Corrupted or missing` (exit 1) |
| `stats` | `swarmcas stats` | Blobs, bytes, chunks, dedup savings |
| `gc` | `swarmcas gc` | Removes all blobs (`max_age_days=0`); prints count |
| `sync` | `swarmcas sync <target-dir>` | Copies missing blobs into another store |

Global: `--store <dir>` (default `.swarmcas`).

---

## 📚 API reference

**`swarmcas.ContentStore(root_dir)`**
`put(data, content_type="", metadata=None)` · `put_file(path, ...)` · `get(digest)` · `get_ref(digest)` · `exists(digest)` · `verify(digest)` · `delete(digest)` · `list_blobs(prefix="")` · `stats()`

**`swarmcas.hasher`** — `content_hash(data)` · `file_hash(path)` · `verify_integrity(data, digest)` · `merkle_root(digests)`

**`swarmcas.chunks`** — `chunk(data, target_size=65536)` · `reassemble(chunks)` · `Chunker(target_size=65536)`

**`swarmcas.gc.GarbageCollector`** — `collect(store, max_age_days)` → count removed · `verify_all(store)` → list of corrupted digests

**`swarmcas.sync`** — `SyncAdapter` (base) · `LocalSyncAdapter().sync(source, target, dry_run=False)` → count synced

**`swarmcas.types`** — `BlobRef` · `ChunkRef` · `StoreStats` · `SyncTarget` · `CASError` / `BlobNotFoundError` / `IntegrityError`

Fully type-annotated (`py.typed` included).

---

## 🧩 Fits the Prismatic family

SwarmCAS is the **immutable artifact layer** for the Prismatic engine family: agent runs produce outputs, receipts, and evidence bundles; SwarmCAS stores them content-addressed so any later step can re-fetch the exact bytes and re-verify them. It pairs naturally with **SwarmProof**, the family's verification oracle — SwarmProof proves *what happened*, SwarmCAS keeps *the bytes it happened with*, addressable forever by digest.

---

## 🛠️ Development

```bash
git clone https://github.com/mbgulden/swarmcas.git
cd swarmcas
pip install -e ".[dev]"
pytest tests/ -v
ruff check .
python -m build && twine check dist/*
```

---

## 📄 License

MIT — see [LICENSE](LICENSE).
