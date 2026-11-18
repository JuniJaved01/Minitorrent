"""
tests/test_tracker.py  --  OWNER: MAAZ (tests Arbab's tracker and Junaid's strategies)
Run:  pytest -v
"""

import time  # wait for the timeout

from peer import strategy  # Junaid's chunk picking
from tracker.registry import Registry  # Arbab's peer table
from tracker.storage import Storage  # Arbab's SQLite layer


def msg(port, held=0, bitmap="000"):
    """A REGISTER/HEARTBEAT-like message for file 'f1' with 3 chunks."""
    return {"file_id": "f1", "name": "a.bin", "size": 30, "num_chunks": 3,
            "port": port, "chunks_held": held, "bitmap": bitmap}  # the fields the registry reads


def test_register_and_get_peers_excludes_asker():
    reg = Registry()  # RAM only
    reg.upsert_peer("10.0.0.1", msg(6001, 3, "111"), True)  # a seeder
    reg.upsert_peer("10.0.0.2", msg(6002), True)  # a leecher
    peers = reg.get_peers("f1", exclude=("10.0.0.2", 6002))  # the leecher asks
    assert peers == [{"ip": "10.0.0.1", "port": 6001, "chunks_held": 3}]  # it only gets the seeder
    assert reg.get_peers("other-file") == []  # unknown file has no peers


def test_dead_peer_is_removed_after_timeout():
    reg = Registry(timeout=0.3)  # very short timeout for the test
    reg.upsert_peer("10.0.0.1", msg(6001), True)  # peer that will die
    reg.upsert_peer("10.0.0.2", msg(6002), True)  # peer that stays alive
    time.sleep(0.2)  # some time passes
    reg.upsert_peer("10.0.0.2", msg(6002), False)  # only 6002 sends a HEARTBEAT
    time.sleep(0.2)  # now 6001 is silent for 0.4 s > 0.3 s
    removed = reg.remove_stale()  # what the reaper thread does every second
    assert removed == [("f1", "10.0.0.1", 6001)]  # the dead one is gone
    assert [p["port"] for p in reg.peers_snapshot()] == [6002]  # the live one stays


def test_files_snapshot_counts_seeders_and_availability():
    reg = Registry()  # RAM only
    reg.upsert_peer("10.0.0.1", msg(6001, 3, "111"), True)  # seeder
    reg.upsert_peer("10.0.0.2", msg(6002, 1, "010"), True)  # leecher with chunk 1
    f = reg.files_snapshot()[0]  # the only file
    assert (f["seeders"], f["leechers"]) == (1, 1)  # one of each
    assert f["availability"] == [1, 2, 1]  # chunk 1 is held by both


def test_registry_survives_restart_with_sqlite(tmp_path):
    db = str(tmp_path / "tracker.db")  # database file
    reg1 = Registry(storage=Storage(db))  # first tracker run
    reg1.upsert_peer("10.0.0.1", msg(6001, 3, "111"), True)  # a peer registers
    reg1.storage.close()  # tracker "crashes"
    reg2 = Registry(storage=Storage(db))  # tracker restarts with the same database
    assert reg2.get_peers("f1") == [{"ip": "10.0.0.1", "port": 6001, "chunks_held": 3}]  # peer is back
    assert reg2.files_snapshot()[0]["name"] == "a.bin"  # file is back


def test_rarest_first_picks_lowest_availability():
    availability = {0: 3, 1: 1, 2: 2}  # chunk 1 is the rarest
    assert strategy.rarest_first([0, 1, 2], availability) == 1  # so it is picked
    assert strategy.rarest_first([0, 2], availability) == 2  # without 1, chunk 2 is the rarest


def test_random_pick_and_empty_candidates():
    assert strategy.random_pick([4, 5, 6]) in (4, 5, 6)  # always one of the candidates
    assert strategy.random_pick([]) is None  # nothing to pick
    assert strategy.rarest_first([], {}) is None  # nothing to pick


def test_count_availability():
    bitmaps = {("a", 1): {0, 1}, ("b", 2): {1}}  # two peers
    assert strategy.count_availability(bitmaps) == {0: 1, 1: 2}  # chunk 1 has two holders
