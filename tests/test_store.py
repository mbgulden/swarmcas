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
