"""
tests/helpers.py  --  OWNER: MAAZ
Small helpers that start a tracker and peers INSIDE the test process (on free ports),
so tests and experiments need no terminals and no fixed ports.
"""

import os  # random bytes and paths

from peer import chunks  # metadata + ChunkStore
from peer.main import build_state  # the REGISTER/HEARTBEAT state dictionary
from peer.network import PeerServer, TrackerClient  # networking
from tracker.registry import Registry  # tracker memory
from tracker.server import TrackerServer  # tracker TCP server

LOCAL = "127.0.0.1"  # everything in tests runs on this machine


def make_file(path, size):
    """Create a file of 'size' random bytes and return its path."""
    with open(path, "wb") as f:  # write bytes
        f.write(os.urandom(size))  # random content, so every chunk hash is different
    return str(path)  # path as text


def start_tracker(timeout=15.0):
    """Start a tracker on a free port. Returns (registry, server, (host, port))."""
    registry = Registry(storage=None, timeout=timeout)  # RAM only, no SQLite
    server = TrackerServer(registry, LOCAL, 0).start()  # port 0 = the OS picks a free port
    return registry, server, (LOCAL, server.port)  # the address peers should use


def start_peer(meta, store, tracker_addr, delay=0.0, role="seeder"):
    """Start a PeerServer for 'store' and register it. Returns (server, tracker_client)."""
    server = PeerServer(0, LOCAL, upload_delay=delay).start()  # free port
    server.add_store(meta["file_id"], store)  # share the store
    client = TrackerClient(tracker_addr, server.port)  # tracker helper for this peer
    client.register(build_state(meta, store, server, role))  # REGISTER
    return server, client  # caller stops them


def seeder_store(meta, path):
    """A ChunkStore that already holds the complete file."""
    return chunks.ChunkStore(meta, path, complete=True)  # every bit is 1
