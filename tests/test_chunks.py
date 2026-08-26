from swarmcas.chunks import chunk, reassemble

def test_chunking():
    data = b"a" * 1000
    chunks = chunk(data, target_size=100)
    assert len(chunks) == 10
    assert chunks[0][0] == 0
    assert len(chunks[0][1]) == 100

def test_reassemble():
    data = b"hello world"
    chunks_list = [c[1] for c in chunk(data, target_size=5)]
    assert reassemble(chunks_list) == data
