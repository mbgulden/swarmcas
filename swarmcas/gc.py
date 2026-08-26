import time
import sqlite3
from typing import List
from .store import ContentStore

class GarbageCollector:
    def collect(self, store: ContentStore, max_age_days: int) -> int:
        cutoff_time = time.time() - (max_age_days * 86400)
        removed_count = 0
        import contextlib
        with contextlib.closing(sqlite3.connect(store.db_path)) as conn, conn:
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
