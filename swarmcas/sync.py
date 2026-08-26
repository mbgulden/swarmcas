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
