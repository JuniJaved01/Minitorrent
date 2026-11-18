"""
tests/test_failures.py  --  OWNER: MAAZ
End-to-end failure tests: a real tracker, real peers and a real download inside one process.
    1. parallel download from 3 seeders, final hash matches
    2. one seeder is KILLED mid-download, the download still completes
    3. one peer sends CORRUPTED chunks, they are rejected and re-fetched
    4. an interrupted download RESUMES from its progress file
Run:  pytest -v tests/test_failures.py
"""

import threading  # the download runs in a background thread
import time  # polling

from peer import chunks  # metadata + ChunkStore
from peer.downloader import Downloader  # engine under test
from peer.network import PeerClient, TrackerClient  # networking
from tests.helpers import make_file, seeder_store, start_peer, start_tracker  # in-process swarm

CHUNK = 16 * 1024  # small 16 KB chunks keep the tests fast
NUM = 60  # the test file has 60 chunks


class CorruptStore(chunks.ChunkStore):
    """A dishonest peer: every chunk it uploads has one flipped byte."""

    def read_chunk(self, i):
        data = super().read_chunk(i)  # the real bytes
        return bytes([data[0] ^ 0xFF]) + data[1:]  # damage the first byte


def setup_swarm(tmp_path, seeders, delay):
    """Create a file, a tracker and N seeders. Returns (src, meta, tracker_addr, servers)."""
    src = make_file(tmp_path / "src.bin", CHUNK * NUM - 100)  # last chunk is short on purpose
    meta = chunks.create_metadata(src, CHUNK)  # split + hash
    _, _, tracker_addr = start_tracker()  # tracker on a free port
    servers = [start_peer(meta, seeder_store(meta, src), tracker_addr, delay)[0] for _ in range(seeders)]  # seeders
    return src, meta, tracker_addr, servers  # everything the test needs


def new_downloader(tmp_path, meta, tracker_addr, name="copy.bin", **kw):
    """Build a Downloader writing to tmp_path/name."""
    out = str(tmp_path / "dl" / name)  # output file
    store = chunks.ChunkStore(meta, out)  # empty store
    engine = Downloader(meta, store, PeerClient(timeout=2), TrackerClient(tracker_addr, 1),
                        progress_path=out + ".progress", refresh_interval=0.3, stall_timeout=15, **kw)  # engine
    return engine, store, out  # for the asserts


def wait_for_chunks(store, count, timeout=20):
    """Block until the store holds at least 'count' chunks."""
    deadline = time.time() + timeout  # do not wait forever
    while store.count() < count and time.time() < deadline:  # not there yet
        time.sleep(0.01)  # poll 100 times per second


def test_parallel_download_from_three_seeders(tmp_path):
    src, meta, tracker_addr, servers = setup_swarm(tmp_path, seeders=3, delay=0.005)  # 3 seeders
    engine, store, out = new_downloader(tmp_path, meta, tracker_addr)  # the downloader
    assert engine.run()  # completes and the whole-file hash matches
    assert chunks.file_sha256(out) == chunks.file_sha256(src)  # byte-identical copy
    assert len(set(engine.sources.values())) == 3  # chunks really came from all 3 seeders


def test_download_survives_killed_peer(tmp_path):
    src, meta, tracker_addr, servers = setup_swarm(tmp_path, seeders=3, delay=0.02)  # 3 slow seeders
    engine, store, out = new_downloader(tmp_path, meta, tracker_addr)  # the downloader
    result = {}  # the thread stores its return value here
    t = threading.Thread(target=lambda: result.update(ok=engine.run()))  # download in the background
    t.start()  # go
    wait_for_chunks(store, NUM // 4)  # let a quarter of the file arrive
    servers[0].stop()  # KILL one seeder in the middle of the download
    t.join(timeout=60)  # wait for the download to end
    assert result.get("ok") is True  # it still finished
    assert chunks.file_sha256(out) == chunks.file_sha256(src)  # and the file is correct


def test_corrupted_chunks_are_rejected_and_refetched(tmp_path):
    src = make_file(tmp_path / "src.bin", CHUNK * NUM)  # the original
    meta = chunks.create_metadata(src, CHUNK)  # trusted hashes
    _, _, tracker_addr = start_tracker()  # tracker
    start_peer(meta, seeder_store(meta, src), tracker_addr, 0.005)  # one honest seeder
    start_peer(meta, CorruptStore(meta, src, complete=True), tracker_addr, 0.005)  # one dishonest seeder
    engine, store, out = new_downloader(tmp_path, meta, tracker_addr)  # the downloader
    assert engine.run()  # finishes with a correct file
    assert engine.hash_failures >= 1  # at least one bad chunk was caught
    assert chunks.file_sha256(out) == chunks.file_sha256(src)  # nothing corrupt reached the disk


def test_resume_after_interruption(tmp_path):
    src, meta, tracker_addr, servers = setup_swarm(tmp_path, seeders=1, delay=0.02)  # one slow seeder
    engine, store, out = new_downloader(tmp_path, meta, tracker_addr)  # first attempt
    t = threading.Thread(target=engine.run)  # download in the background
    t.start()  # go
    wait_for_chunks(store, NUM // 3)  # a third arrives
    engine.stop()  # "power cut": abort the download
    t.join(timeout=30)  # wait for the threads to end
    done_before = store.count()  # chunks finished by the first attempt
    assert 0 < done_before < NUM  # really interrupted in the middle
    engine2, store2, _ = new_downloader(tmp_path, meta, tracker_addr)  # second attempt, same output file
    engine2._load_progress()  # what run() does first
    assert store2.count() == done_before  # every old chunk was re-verified and kept
    assert engine2.run()  # the rest is downloaded
    assert len(engine2.sources) == NUM - done_before  # ONLY the missing chunks were fetched again
    assert chunks.file_sha256(out) == chunks.file_sha256(src)  # final file is correct
