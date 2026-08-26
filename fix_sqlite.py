import os
from pathlib import Path
import re

base = Path(r"c:\Users\Michael Gulden\Github\swarmcas")
store_path = base / "swarmcas" / "store.py"
gc_path = base / "swarmcas" / "gc.py"

def fix_sqlite(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # replace "with sqlite3.connect(self.db_path) as conn:"
    # with "with contextlib.closing(sqlite3.connect(self.db_path)) as conn, conn:"
    content = content.replace("with sqlite3.connect(", "import contextlib\n        with contextlib.closing(sqlite3.connect(")
    content = content.replace(") as conn:", ")) as conn, conn:")
    # Fix store.db_path in gc.py
    content = content.replace("with contextlib.closing(sqlite3.connect(store.db_path)) as conn, conn:", "with contextlib.closing(sqlite3.connect(store.db_path)) as conn, conn:")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

fix_sqlite(store_path)
fix_sqlite(gc_path)

