"""
tests/test_chunks.py  --  OWNER: MAAZ
Unit tests for chunking and integrity (peer/chunks.py).   Run:  pytest -v
"""

import hashlib  # independent hash to compare against
import threading  # the thread-safety test

from peer import chunks  # the code under test
from tests.helpers import make_file  # random test files

CS = 262144  # the real chunk size: 256 KB


def copy_through_store(tmp_path, size, chunk_size=CS):
    """Split a random file, push every chunk through a ChunkStore, return (source, copy, meta, store)."""
    src = make_file(tmp_path / "src.bin", size)  # the original file
    meta = chunks.create_metadata(src, chunk_size)  # split + hash
    dst = str(tmp_path / "out" / "copy.bin")  # where the copy is rebuilt
    store = chunks.ChunkStore(meta, dst)  # empty downloader store
    for i in reversed(range(meta["num_chunks"])):  # write in REVERSE order on purpose
        assert store.write_chunk(i, chunks.read_chunk(src, i, chunk_size))  # every chunk must be accepted
    return src, dst, meta, store  # for the asserts


def test_split_and_reassemble_matches(tmp_path):
    src, dst, meta, store = copy_through_store(tmp_path, 4 * CS)  # exactly 4 chunks
    assert meta["num_chunks"] == 4  # 1 MB / 256 KB
    assert store.is_complete()  # every chunk stored
    assert chunks.file_sha256(src) == chunks.file_sha256(dst)  # identical content
    assert store.verify_file()  # whole-file hash matches the metadata


def test_size_not_multiple_of_chunk(tmp_path):
    src, dst, meta, store = copy_through_store(tmp_path, 3 * CS + 12345)  # last chunk is short
    assert meta["num_chunks"] == 4  # 3 full chunks + 1 short one
    assert chunks.chunk_length(meta, 3) == 12345  # the short chunk has the leftover bytes
    assert chunks.file_sha256(src) == chunks.file_sha256(dst)  # still identical


def test_flipped_byte_fails_verification(tmp_path):
    src = make_file(tmp_path / "src.bin", 2 * CS)  # two chunks
    meta = chunks.create_metadata(src)  # trusted hashes
    good = chunks.read_chunk(src, 0)  # a real chunk
    bad = bytes([good[0] ^ 0xFF]) + good[1:]  # flip all bits of the first byte
    assert chunks.verify_chunk(meta, 0, good)  # the real chunk passes
    assert not chunks.verify_chunk(meta, 0, bad)  # the damaged chunk fails
    store = chunks.ChunkStore(meta, str(tmp_path / "copy.bin"))  # empty store
    assert not store.write_chunk(0, bad)  # the store refuses it
    assert not store.has(0)  # and does not mark it as held


def test_wrong_index_fails_verification(tmp_path):
    src = make_file(tmp_path / "src.bin", 2 * CS)  # two chunks
    meta = chunks.create_metadata(src)  # trusted hashes
    assert not chunks.verify_chunk(meta, 1, chunks.read_chunk(src, 0))  # chunk 0 is not chunk 1
    assert not chunks.verify_chunk(meta, 99, b"x")  # index outside the file


def test_metadata_fields_and_roundtrip(tmp_path):
    src = make_file(tmp_path / "src.bin", CS + 10)  # two chunks
    meta = chunks.create_metadata(src)  # build metadata
    assert meta["chunk_size"] == CS and meta["size"] == CS + 10  # sizes recorded
    joined = "".join(meta["hashes"]).encode("ascii")  # all hashes glued together
    assert meta["file_id"] == hashlib.sha256(joined).hexdigest()  # file_id = SHA-256 of joined hashes
    path = chunks.save_metadata(meta, str(tmp_path / "src.bin.mtorrent"))  # write .mtorrent
    assert chunks.load_metadata(path) == meta  # reading it back gives the same dict


def test_empty_store_and_missing_chunk(tmp_path):
    src = make_file(tmp_path / "src.bin", 2 * CS)  # two chunks
    meta = chunks.create_metadata(src)  # metadata
    store = chunks.ChunkStore(meta, str(tmp_path / "copy.bin"))  # empty store
    assert store.bitmap() == [0, 0] and store.count() == 0  # nothing held
    try:  # reading a chunk we do not hold must fail
        store.read_chunk(0)  # should raise
        assert False, "expected KeyError"  # we must not get here
    except KeyError:  # the expected error
        pass  # good


def test_store_is_thread_safe(tmp_path):
    src = make_file(tmp_path / "src.bin", 64 * 4096)  # 64 small chunks
    meta = chunks.create_metadata(src, 4096)  # 4 KB chunks so the test is fast
    dst = str(tmp_path / "copy.bin")  # output
    store = chunks.ChunkStore(meta, dst)  # empty store

    def writer(indexes):  # each thread writes its own share of chunks
        for i in indexes:  # every chunk of this thread
            store.write_chunk(i, chunks.read_chunk(src, i, 4096))  # verify + write

    threads = [threading.Thread(target=writer, args=(range(k, 64, 8),)) for k in range(8)]  # 8 threads
    for t in threads:  # start them all
        t.start()  # go
    for t in threads:  # wait for all
        t.join()  # done
    assert store.is_complete() and store.verify_file()  # nothing lost, nothing mixed up


def test_50mb_file_survives(tmp_path):
    src, dst, meta, store = copy_through_store(tmp_path, 50 * 1024 * 1024)  # the 50 MB acceptance test
    assert meta["num_chunks"] == 200  # 50 MB / 256 KB
    assert chunks.file_sha256(src) == chunks.file_sha256(dst)  # identical hash
