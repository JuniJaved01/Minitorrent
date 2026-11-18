"""
tests/test_node.py
The GUI features end to end, without a browser: two ClientNodes share folders through a tracker.
"""

import os  # paths
import time  # waiting

import pytest  # fixtures

from common import protocol as P  # ProtocolError
from peer import chunks  # file hashes
from peer.network import PeerClient, TrackerClient  # metadata + ping
from peer.node import ClientNode  # the folder-sharing client
from tests.helpers import make_file, start_tracker  # tracker on a free port


def wait_until(check, seconds=20.0):
    """Poll check() until it is true or time runs out."""
    deadline = time.time() + seconds  # give up after this
    while time.time() < deadline:  # still time
        if check():  # done
            return True  # success
        time.sleep(0.1)  # wait a bit
    return False  # timed out


@pytest.fixture
def tracker():
    registry, server, addr = start_tracker(timeout=15.0)  # tracker on a free port
    yield registry, addr  # give it to the test
    server.stop()  # clean up


def node(addr, folder, name):
    """Start a client node on a free peer port."""
    n = ClientNode(addr, str(folder), peer_port=0, device_name=name)  # port 0 = OS picks
    return n.start()  # ping + seed


def test_ping_and_wrong_address(tracker):
    registry, addr = tracker  # running tracker
    pong = TrackerClient(addr, 0).ping()  # PING
    assert pong["type"] == P.PONG and pong["your_ip"] == "127.0.0.1"  # answered
    with pytest.raises(OSError):  # nothing listens on port 1
        TrackerClient(("127.0.0.1", 1), 0, timeout=1).ping()  # refused


def test_folder_share_list_download_and_device_view(tracker, tmp_path):
    registry, addr = tracker  # running tracker
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"  # two shared folders
    a_dir.mkdir(); b_dir.mkdir()  # create them
    src = make_file(a_dir / "movie.bin", 3 * 262144 + 1234)  # 4 chunks
    make_file(a_dir / ".hidden", 100)  # hidden files are never shared
    a = node(addr, a_dir, "PC-A")  # seeder device
    b = node(addr, b_dir, "PC-B")  # empty device
    try:
        assert wait_until(lambda: any(s["status"] == "seeding" for s in a.snapshot()["shared"]))  # hashed + seeding
        assert [s["name"] for s in a.snapshot()["shared"]] == ["movie.bin"]  # hidden file ignored
        a._announce()  # push to the tracker now
        assert wait_until(lambda: b.snapshot()["available"])  # B sees the file in the swarm
        item = b.snapshot()["available"][0]  # the offered file
        assert item["name"] == "movie.bin" and item["seeders"] == 1  # one seeder
        assert item["health"] == "low"  # a single source is flagged (amber)

        devices = {d["name"]: d for d in registry.devices_snapshot()}  # server view
        assert devices["PC-A"]["files"][0]["name"] == "movie.bin"  # the server lists A's file
        assert devices["PC-B"]["files"] == []  # B has nothing yet

        b.start_download(item["file_id"])  # metadata comes from A, no .mtorrent copying
        assert wait_until(lambda: os.path.exists(b_dir / "movie.bin"), 30)  # lands in B's shared folder
        assert chunks.file_sha256(str(b_dir / "movie.bin")) == chunks.file_sha256(src)  # identical
        assert wait_until(lambda: any(s["status"] == "seeding" for s in b.snapshot()["shared"]))  # B seeds it now
        b._announce()  # push to the tracker now
        devices = {d["name"]: d for d in registry.devices_snapshot()}  # server view again
        assert devices["PC-B"]["files"][0]["complete"]  # B is a seeder of the file
        assert registry.list_files()[0]["seeders"] == 2  # two seeders in the swarm

        os.remove(a_dir / "movie.bin")  # A deletes the file from its folder
        assert wait_until(lambda: not a.snapshot()["shared"], 10)  # A stops sharing it
        a._announce()  # tell the tracker
        devices = {d["name"]: d for d in registry.devices_snapshot()}  # server view
        assert devices["PC-A"]["files"] == []  # the server no longer lists it for A
    finally:
        a.stop(); b.stop()  # clean up


def test_kick_device(tracker, tmp_path):
    registry, addr = tracker  # running tracker
    a = node(addr, tmp_path, "PC-A")  # one device
    try:
        key = registry.devices_snapshot()[0]["key"]  # its id
        registry.kick_device(key)  # server presses Disconnect
        a._announce()  # next heartbeat is refused
        assert a.status == "kicked"  # the client shows it
    finally:
        a.stop()  # clean up


def test_forged_metadata_is_rejected(tracker, tmp_path):
    registry, addr = tracker  # running tracker
    make_file(tmp_path / "x.bin", 1000)  # one small file
    a = node(addr, tmp_path, "PC-A")  # seeder
    try:
        assert wait_until(lambda: any(s["status"] == "seeding" for s in a.snapshot()["shared"]))  # ready
        fid = a.snapshot()["shared"][0]["file_id"]  # its id
        meta = PeerClient().get_metadata(("127.0.0.1", a.server.port), fid)  # real metadata is accepted
        assert meta["name"] == "x.bin"  # correct
        with pytest.raises(P.ProtocolError):  # asking with the wrong id fails
            PeerClient().get_metadata(("127.0.0.1", a.server.port), "0" * 64)  # unknown file
    finally:
        a.stop()  # clean up
