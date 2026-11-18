"""
peer/downloader.py  --  OWNER: JUNAID
The download engine: several worker threads download DIFFERENT chunks from
DIFFERENT peers at the same time, verify every chunk, retry on failure,
and remember progress on disk so a download can resume.
"""

import json  # the progress (resume) file is JSON
import os  # check whether the progress file exists
import random  # random tie-break between equally loaded peers
import threading  # worker threads, lock and events
import time  # ban timers and stall detection

from common import config  # NUM_WORKERS, BAN_SECONDS, ...
from common import protocol as P  # ProtocolError
from peer.strategy import STRATEGIES, count_availability  # chunk picking strategies


class Downloader:
    """Downloads one file described by 'meta' into 'store' using many peers."""

    def __init__(self, meta, store, peer_client, tracker_client, strategy="rarest",
                 workers=None, max_per_peer=None, progress_path=None,
                 refresh_interval=2.0, stall_timeout=30.0):
        self.meta = meta  # trusted metadata from the .mtorrent
        self.store = store  # Maaz's ChunkStore (verifies + writes chunks)
        self.client = peer_client  # Ayaan's PeerClient (get_bitmap / fetch_chunk)
        self.tracker = tracker_client  # Ayaan's TrackerClient (get_peers)
        self.strategy_name = strategy  # "rarest" or "random" (shown on the dashboard)
        self.pick = STRATEGIES[strategy]  # the actual strategy function
        self.workers = workers or config.NUM_WORKERS  # number of worker threads (default 4)
        self.max_per_peer = max_per_peer or config.MAX_PER_PEER  # parallel requests allowed per peer
        self.progress_path = progress_path  # resume file (None = resume disabled)
        self.refresh_interval = refresh_interval  # how often we re-ask tracker + bitmaps
        self.stall_timeout = stall_timeout  # give up if no progress for this many seconds

        self._lock = threading.Lock()  # THE lock: protects every field below
        self._needed = set()  # chunks we still have to download
        self._in_progress = set()  # chunks some worker is downloading right now
        self._peer_chunks = {}  # addr -> set of chunk indexes that peer holds
        self._load = {}  # addr -> how many requests we have open to that peer
        self._banned = {}  # addr -> time until which we avoid that peer
        self._done = threading.Event()  # set when the download finished or was stopped
        self._last_progress = time.time()  # time of the last stored chunk (stall detection)

        self.downloaded = 0  # bytes downloaded in this run (dashboard)
        self.hash_failures = 0  # chunks rejected because the hash was wrong
        self.peer_failures = 0  # timeouts / dead connections
        self.sources = {}  # chunk index -> "ip:port" it came from (dashboard colours)

    # ------------------------------------------------------------------ resume
    def _load_progress(self):
        """Resume: re-verify the chunks a previous run said it had finished."""
        if not self.progress_path or not os.path.exists(self.progress_path):  # nothing saved
            return  # fresh download
        try:  # the file could be damaged
            with open(self.progress_path, "r", encoding="utf-8") as f:  # open the progress file
                saved = json.load(f)  # {"file_id": ..., "have": [...]}
        except (OSError, ValueError):  # unreadable or bad JSON
            return  # ignore it and start fresh
        if saved.get("file_id") != self.meta["file_id"]:  # progress belongs to another file
            return  # ignore it
        for i in saved.get("have", []):  # every chunk the old run finished
            if 0 <= i < self.meta["num_chunks"]:  # ignore nonsense indexes
                self.store.recheck_chunk(i)  # trust nothing: re-hash it from disk

    def _save_progress(self):
        """Write the list of finished chunks to disk (called after every chunk)."""
        if not self.progress_path:  # resume disabled
            return  # nothing to do
        bitmap = self.store.bitmap()  # current 0/1 list
        have = [i for i, bit in enumerate(bitmap) if bit]  # indexes of finished chunks
        tmp = self.progress_path + ".tmp"  # write to a temp file first
        with open(tmp, "w", encoding="utf-8") as f:  # open the temp file
            json.dump({"file_id": self.meta["file_id"], "have": have}, f)  # save id + finished list
        os.replace(tmp, self.progress_path)  # atomic swap: never leaves a half-written file

    # ------------------------------------------------------------ peer discovery
    def refresh_peers(self):
        """Ask the tracker who is in the swarm, then ask each peer for its bitmap."""
        try:  # the tracker may be unreachable for a moment
            addrs = self.tracker.get_peers(self.meta["file_id"])  # list of (ip, port)
        except (OSError, P.ProtocolError):  # tracker problem
            return  # keep using the peers we already know
        now = time.time()  # current time for ban checks
        fresh = {}  # addr -> chunk set, built outside the lock
        for addr in addrs:  # every peer the tracker knows
            with self._lock:  # read the ban table safely
                banned = self._banned.get(addr, 0) > now  # still in the penalty box?
            if banned:  # skip peers that failed recently
                continue  # try them again after the ban
            try:  # the peer may be dead
                bitmap = self.client.get_bitmap(addr, self.meta["file_id"])  # list of 0/1
            except (OSError, P.ProtocolError):  # no answer
                continue  # not usable right now
            fresh[addr] = {i for i, bit in enumerate(bitmap) if bit}  # 0/1 list -> set of indexes
        with self._lock:  # swap in the new picture of the swarm
            self._peer_chunks = fresh  # peers that vanished from the tracker are dropped here
            for addr in fresh:  # make sure every peer has a load counter
                self._load.setdefault(addr, 0)  # new peers start with 0 open requests

    def _refresh_loop(self):
        """Background thread: keep the swarm picture fresh until the download ends."""
        while not self._done.wait(self.refresh_interval):  # sleep, exit early when done
            self.refresh_peers()  # new peers and new chunks appear here

    # --------------------------------------------------------------- scheduling
    def _next_job(self):
        """Pick (chunk, peer) for a worker. Returns None if nothing can be done right now."""
        with self._lock:  # everything here reads/writes shared state
            now = time.time()  # for ban checks
            alive = {a: c for a, c in self._peer_chunks.items() if self._banned.get(a, 0) <= now}  # not banned
            free = {a: c for a, c in alive.items() if self._load.get(a, 0) < self.max_per_peer}  # has a free slot
            waiting = self._needed - self._in_progress  # needed and not already being fetched
            candidates = [c for c in waiting if any(c in chunks for chunks in free.values())]  # obtainable now
            if not candidates:  # nothing obtainable at this moment
                return None  # worker will wait a little
            availability = count_availability(alive)  # chunk -> how many live peers hold it
            index = self.pick(candidates, availability)  # STRATEGY decides the chunk
            holders = [a for a, chunks in free.items() if index in chunks]  # peers that can serve it now
            least = min(self._load.get(a, 0) for a in holders)  # smallest current load
            addr = random.choice([a for a in holders if self._load.get(a, 0) == least])  # least busy peer
            self._in_progress.add(index)  # reserve the chunk: no other worker may take it
            self._load[addr] = self._load.get(addr, 0) + 1  # one more open request to that peer
            return index, addr  # the job

    def _success(self, index, addr, nbytes):
        """A chunk was fetched, verified and stored."""
        with self._lock:  # update shared state
            self._needed.discard(index)  # not needed any more
            self._in_progress.discard(index)  # no longer in flight
            self._load[addr] = max(0, self._load.get(addr, 1) - 1)  # the request is finished
            self.downloaded += nbytes  # count bytes for the dashboard
            self.sources[index] = "%s:%d" % addr  # remember who gave us this chunk
            self._last_progress = time.time()  # we are making progress
            self._save_progress()  # resume file is updated after EVERY chunk
            if not self._needed:  # that was the last chunk
                self._done.set()  # wake everybody up: we are finished

    def _fail(self, index, addr, drop_peer):
        """A fetch failed: give the chunk back and avoid that peer for a while."""
        with self._lock:  # update shared state
            self._in_progress.discard(index)  # chunk returns to the 'waiting' pool
            self._load[addr] = max(0, self._load.get(addr, 1) - 1)  # the request is finished
            self._banned[addr] = time.time() + config.BAN_SECONDS  # penalty box
            if drop_peer:  # the peer looks dead (timeout / connection refused)
                self._peer_chunks.pop(addr, None)  # forget its chunks until it shows up again

    def _worker(self):
        """One download thread: pick, fetch, verify, store, repeat."""
        while not self._done.is_set():  # until the download ends
            job = self._next_job()  # ask the scheduler for work
            if job is None:  # nothing available right now
                time.sleep(0.05)  # wait a moment and ask again
                continue  # back to the top
            index, addr = job  # the chunk and the peer to get it from
            try:  # the network part can fail in many ways
                data = self.client.fetch_chunk(addr, self.meta["file_id"], index)  # REQUEST_CHUNK
            except (OSError, P.ProtocolError):  # timeout, refused, closed, error reply
                self.peer_failures += 1  # count it
                self._fail(index, addr, drop_peer=True)  # put chunk back, drop the peer
                continue  # another peer will serve this chunk
            if not self.store.write_chunk(index, data):  # the store verifies the SHA-256 first
                self.hash_failures += 1  # corrupted or tampered chunk
                self._fail(index, addr, drop_peer=False)  # put chunk back, ban the peer briefly
                continue  # it will be re-downloaded
            self._success(index, addr, len(data))  # chunk is safely on disk

    # ---------------------------------------------------------------------- run
    def progress(self):
        """Return (chunks_done, chunks_total)."""
        return self.store.count(), self.meta["num_chunks"]  # e.g. (37, 80)

    def stop(self):
        """Abort the download (progress stays on disk for resume)."""
        self._done.set()  # all threads leave their loops

    def run(self):
        """Download the whole file. Returns True if the final file hash matches."""
        self._load_progress()  # resume: pick up chunks from an earlier run
        bitmap = self.store.bitmap()  # what we hold right now
        self._needed = {i for i, bit in enumerate(bitmap) if not bit}  # everything we do not hold
        if self._needed:  # there is work to do
            self.refresh_peers()  # first picture of the swarm before workers start
            threads = [threading.Thread(target=self._refresh_loop, daemon=True)]  # peer refresher
            threads += [threading.Thread(target=self._worker, daemon=True) for _ in range(self.workers)]  # workers
            self._last_progress = time.time()  # start the stall clock
            for t in threads:  # start refresher + workers
                t.start()  # go
            while not self._done.wait(0.25):  # check 4 times per second
                if time.time() - self._last_progress > self.stall_timeout:  # nobody can serve us
                    self._done.set()  # give up (progress is saved, resume later)
            for t in threads:  # wait for threads to finish their current step
                t.join(timeout=config.SOCKET_TIMEOUT + 1)  # never wait forever
        return self.store.is_complete() and self.store.verify_file()  # final whole-file hash check
