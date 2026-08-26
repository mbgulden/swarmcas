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
