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
