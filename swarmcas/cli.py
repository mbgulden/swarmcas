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
