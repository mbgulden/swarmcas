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
