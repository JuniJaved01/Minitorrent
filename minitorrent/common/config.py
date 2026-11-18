"""
common/config.py  --  OWNER: AYAAN
All tunable settings of MiniTorrent live here.
Every value can be overridden with an environment variable, so nothing is hard-coded.
"""

import os  # os.environ lets us read environment variables


def _env_int(name, default):
    """Read an integer setting from the environment, or use the default."""
    return int(os.environ.get(name, default))  # env values are strings, so convert to int


def _env_float(name, default):
    """Read a decimal setting from the environment, or use the default."""
    return float(os.environ.get(name, default))  # env values are strings, so convert to float


CHUNK_SIZE = _env_int("MT_CHUNK_SIZE", 262144)  # size of one chunk in bytes (256 KB)
TRACKER_HOST = os.environ.get("MT_TRACKER_HOST", "127.0.0.1")  # where peers look for the tracker
TRACKER_PORT = _env_int("MT_TRACKER_PORT", 5000)  # TCP port of the tracker (peer <-> tracker)
API_PORT = _env_int("MT_API_PORT", 8000)  # HTTP port of the tracker's FastAPI (dashboard reads this)
HEARTBEAT_INTERVAL = _env_float("MT_HEARTBEAT", 5.0)  # a peer says "I am alive" every N seconds
PEER_TIMEOUT = _env_float("MT_PEER_TIMEOUT", 15.0)  # tracker removes a peer silent for N seconds
SOCKET_TIMEOUT = _env_float("MT_SOCKET_TIMEOUT", 5.0)  # give up on a network call after N seconds
NUM_WORKERS = _env_int("MT_WORKERS", 4)  # number of parallel download threads
MAX_PER_PEER = _env_int("MT_MAX_PER_PEER", 2)  # max chunks we request from ONE peer at the same time
BAN_SECONDS = _env_float("MT_BAN_SECONDS", 10.0)  # how long we avoid a peer after it fails
UPLOAD_DELAY = _env_float("MT_UPLOAD_DELAY", 0.0)  # artificial delay per uploaded chunk (simulates slow links)
MAX_HEADER_BYTES = 1024 * 1024  # safety limit: a JSON header may never be bigger than 1 MB
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024  # safety limit: a raw payload may never be bigger than 16 MB
