"""
peer/node.py
A long-running "client node" for the GUI. It does what peer/main.py does, but for a whole FOLDER:

    * every file in the chosen shared folder is hashed once and SEEDED automatically
    * new files dropped into the folder are picked up, deleted files stop being shared
    * ONE message (ANNOUNCE) tells the tracker about the device and all its files
    * any file in the swarm can be downloaded; the .mtorrent metadata is fetched from a peer
      (GET_METADATA) and checked against the file id, so nobody has to copy .mtorrent files
    * finished downloads land in the shared folder and are seeded straight away

Nothing here is GUI specific: ui/app.py only calls the public methods and snapshot().
"""

import json  # cache file of hashed files
import os  # paths and folder scanning
import threading  # background loops
import time  # timestamps and rates

from common import config  # heartbeat interval, ports
from common import netutil  # PC name and LAN IP
from common import protocol as P  # ProtocolError
from peer import chunks  # metadata + ChunkStore
from peer.downloader import Downloader  # the parallel download engine
from peer.network import PeerClient, PeerServer, TrackerClient  # networking

STATE_DIR = ".minitorrent"  # hidden folder INSIDE the shared folder: hash cache + unfinished downloads
SLOW_RATE = 100 * 1024  # a running download below 100 KB/s is flagged as slow (red)
SCAN_EVERY = 3.0  # seconds between folder scans
SWARM_EVERY = 2.0  # seconds between LIST_FILES calls
HISTORY = 120  # speed samples kept for the chart (one per second = 2 minutes)


def fmt_addr(addr):
    """('127.0.0.1', 6001) -> '127.0.0.1:6001'."""
    return "%s:%d" % addr  # same text format the tracker uses


def unique_path(folder, name):
    """folder/name, or folder/name (1).ext if that already exists."""
    base, ext = os.path.splitext(name)  # 'movie', '.mp4'
    path = os.path.join(folder, name)  # first choice
    n = 1  # suffix counter
    while os.path.exists(path):  # taken
        path = os.path.join(folder, "%s (%d)%s" % (base, n, ext))  # try the next suffix
        n += 1  # count up
    return path  # a free path


def safe_name(name):
    """A file name from the network must never contain folders (no '../../evil')."""
    name = os.path.basename(str(name).replace("\\", "/"))  # drop any folder part
    name = name.strip().lstrip(".")  # no hidden files, no '..'
    return name or "download.bin"  # never empty


class SharedFile:
    """One file in the shared folder."""

    def __init__(self, name, path):
        self.name = name  # file name inside the folder
        self.path = path  # full path
        self.meta = None  # metadata once hashed
        self.store = None  # ChunkStore(complete=True) once hashed
        self.status = "hashing"  # hashing / seeding / paused / error
        self.progress = 0.0  # hashing progress 0..1
        self.error = ""  # reason if status == error
        self.size = 0  # bytes
        self.mtime = 0.0  # last modification time we hashed


class Download:
    """One file being downloaded into the shared folder."""

    def __init__(self, file_id, name, size):
        self.file_id = file_id  # swarm id
        self.name = safe_name(name)  # file name
        self.size = size  # bytes
        self.meta = None  # fetched from a peer
        self.store = None  # ChunkStore in .minitorrent/incoming
        self.downloader = None  # the engine (a new one after every resume)
        self.status = "starting"  # starting / downloading / paused / stalled / failed / done
        self.message = ""  # human-readable detail
        self.rate = 0.0  # bytes/second right now
        self.rate_samples = []  # last few seconds (slow detection)
        self.started = time.time()  # for 'slow' grace period
        self.finished = 0.0  # when it completed
        self.final_path = ""  # where the file ended up
        self.user_paused = False  # True when the user pressed pause (not a stall)
        self._last_bytes = 0  # downloader.downloaded at the last sample
        self._last_obj = None  # which downloader that number belongs to

    def chunks_done(self):
        """Chunks held / total."""
        if self.store is None:  # metadata not fetched yet
            return 0, 0  # nothing
        return self.store.count(), self.meta["num_chunks"]  # e.g. 37, 80


class ClientNode:
    """A device in the swarm: seeds a folder, downloads on request, reports to the tracker."""

    def __init__(self, tracker_addr, folder, peer_port=None, device_name=None, upload_delay=None):
        self.tracker_addr = tracker_addr  # (host, port)
        self.folder = os.path.abspath(os.path.expanduser(folder))  # shared folder
        self.peer_port = peer_port  # None = first free port from 6001
        self.device_name = device_name or netutil.device_name()  # PC name shown on the server
        self.upload_delay = upload_delay  # demo slowness (None = config default)
        self.server = None  # PeerServer
        self.tracker = None  # TrackerClient
        self.status = "stopped"  # stopped / online / reconnecting / kicked
        self.message = ""  # detail for the UI
        self.server_info = {}  # PONG reply (server PC name, version)
        self.my_ip = ""  # how the tracker sees us
        self.shared = {}  # name -> SharedFile
        self.downloads = {}  # file_id -> Download
        self.swarm = []  # last LIST_FILES answer
        self.paused_names = set()  # files the user paused (kept in the cache file)
        self.history = []  # [{t, down, up}] speed samples
        self.down_rate = 0.0  # bytes/second, all downloads
        self.up_rate = 0.0  # bytes/second, all uploads
        self.peak_down = 0.0  # best download speed seen
        self.total_downloaded = 0  # bytes downloaded this session
        self.file_up_rate = {}  # file_id -> bytes/second uploaded
        self._last_up = {}  # file_id -> uploaded counter at last sample
        self._last_up_total = 0  # server.uploaded at last sample
        self._cache = {}  # name -> {size, mtime, meta}
        self._lock = threading.RLock()  # protects shared, downloads, swarm
        self._stop = threading.Event()  # ends every loop
        self._hash_queue = []  # names waiting to be hashed
        self._hash_wake = threading.Event()  # wakes the hashing thread

    # ------------------------------------------------------------------ paths
    def _state_dir(self, *parts):
        """Path inside <folder>/.minitorrent/ (created on demand)."""
        path = os.path.join(self.folder, STATE_DIR, *parts)  # build it
        os.makedirs(os.path.dirname(path) if parts else path, exist_ok=True)  # make sure the folder exists
        return path  # done

    def _load_cache(self):
        """Read the hash cache so restarting does not re-hash big files."""
        try:  # first run has no cache
            with open(self._state_dir("cache.json"), "r", encoding="utf-8") as f:  # open it
                data = json.load(f)  # dict
        except (OSError, ValueError):  # missing or broken
            data = {}  # start fresh
        self._cache = data.get("files", {})  # name -> {size, mtime, meta}
        self.paused_names = set(data.get("paused", []))  # user-paused files

    def _save_cache(self):
        """Write the hash cache (atomic replace)."""
        path = self._state_dir("cache.json")  # target
        tmp = path + ".tmp"  # write here first
        with self._lock:  # consistent snapshot
            data = {"files": dict(self._cache), "paused": sorted(self.paused_names)}  # what we keep
        with open(tmp, "w", encoding="utf-8") as f:  # write
            json.dump(data, f)  # compact JSON
        os.replace(tmp, path)  # never a half-written file

    # ------------------------------------------------------------------ lifecycle
    def start(self):
        """Check the server, open our peer port, scan the folder and start the loops."""
        if not os.path.isdir(self.folder):  # the shared folder must exist
            raise ValueError("shared folder does not exist: %s" % self.folder)  # explain
        probe = TrackerClient(self.tracker_addr, 0)  # temporary client just for PING
        self.server_info = probe.ping()  # raises if nothing / something else answers
        self.server = self._open_peer_server()  # our upload side
        self.tracker = TrackerClient(self.tracker_addr, self.server.port)  # real tracker client
        self._load_cache()  # previous hashes
        self.status = "online"  # connected
        self.message = "Connected to %s" % self.server_info.get("name", "server")  # detail
        self._scan()  # first look at the folder
        for target in (self._hash_loop, self._scan_loop, self._announce_loop, self._swarm_loop, self._rate_loop):
            threading.Thread(target=target, daemon=True).start()  # background loops
        self._announce()  # tell the tracker right away
        return self  # chaining

    def _open_peer_server(self):
        """Listen on the requested port, or on the first free one from 6001 upwards."""
        ports = [self.peer_port] if self.peer_port is not None else list(range(6001, 6051))  # 0 = OS picks
        last = None  # last error
        for port in ports:  # try each one
            try:  # the port may be taken
                return PeerServer(port, upload_delay=self.upload_delay).start()  # success
            except OSError as exc:  # in use
                last = exc  # remember and try the next
        raise OSError("no free peer port (%s)" % last)  # give up

    def stop(self):
        """Disconnect: stop downloads (progress is kept for resume), close sockets."""
        self._stop.set()  # loops end
        self._hash_wake.set()  # wake the hashing thread so it can exit
        with self._lock:  # copy the list
            downloads = list(self.downloads.values())  # every download
        for d in downloads:  # stop each engine
            if d.downloader is not None:  # running
                d.user_paused = True  # not a stall
                d.downloader.stop()  # progress stays on disk
        if self.tracker is not None:  # stop heartbeats
            self.tracker.stop()  # nothing else runs on it
        if self.server is not None:  # close our port
            self.server.stop()  # other peers see us vanish
        self.status = "stopped"  # done

    # ------------------------------------------------------------------ folder scanning
    def _scan(self):
        """Compare the folder with what we share: add new files, drop deleted ones, re-hash changed ones."""
        try:  # the folder may have been removed
            entries = list(os.scandir(self.folder))  # top level only
        except OSError as exc:  # gone or no permission
            self.message = "Cannot read folder: %s" % exc  # show it
            return  # try again later
        seen = {}  # name -> (size, mtime)
        for e in entries:  # every entry
            if e.name.startswith(".") or not e.is_file(follow_symlinks=False):  # hidden, folders, links
                continue  # not shared
            try:  # the file may vanish while we look
                st = e.stat()  # size + mtime
            except OSError:  # gone
                continue  # skip
            if st.st_size == 0:  # an empty file has no chunks
                continue  # nothing to share
            seen[e.name] = (st.st_size, st.st_mtime)  # remember it
        changed = False  # does the cache need saving?
        with self._lock:  # exclusive access
            for name in list(self.shared):  # files we share now
                sf = self.shared[name]  # the record
                if name not in seen or (sf.status != "hashing" and (sf.size, sf.mtime) != seen[name]):  # gone/changed
                    self._unshare(sf)  # stop sharing it
                    del self.shared[name]  # forget it
                    if name not in seen:  # deleted
                        self._cache.pop(name, None)  # forget its hashes too
                        changed = True  # save later
            for name, (size, mtime) in seen.items():  # files on disk
                if name in self.shared:  # already known
                    continue  # nothing to do
                sf = SharedFile(name, os.path.join(self.folder, name))  # new record
                sf.size, sf.mtime = size, mtime  # what we will hash
                cached = self._cache.get(name)  # hashed before?
                if cached and cached.get("size") == size and cached.get("mtime") == mtime and cached.get("meta"):
                    self._activate(sf, cached["meta"])  # reuse the hashes
                else:  # needs hashing
                    self.shared[name] = sf  # show it as 'hashing'
                    self._hash_queue.append(name)  # queue it
                    self._hash_wake.set()  # wake the hasher
        if changed:  # something was deleted
            self._save_cache()  # persist

    def _activate(self, sf, meta):
        """Hashing done: open the store and start seeding (unless paused)."""
        sf.meta = meta  # remember metadata
        sf.store = chunks.ChunkStore(meta, sf.path, complete=True)  # we hold every chunk
        sf.progress = 1.0  # done
        self.shared[sf.name] = sf  # (re)insert
        if sf.name in self.paused_names:  # the user paused it earlier
            sf.status = "paused"  # not offered
        else:  # normal case
            sf.status = "seeding"  # offered to the swarm
            self.server.add_store(meta["file_id"], sf.store)  # peers can now fetch its chunks

    def _unshare(self, sf):
        """Stop offering a file."""
        if sf.meta is not None:  # it was hashed
            other = [s for s in self.shared.values() if s is not sf and s.meta and
                     s.meta["file_id"] == sf.meta["file_id"] and s.status == "seeding"]  # same content twice?
            if not other:  # nobody else in our folder provides it
                self.server.remove_store(sf.meta["file_id"])  # stop serving its chunks

    def _hash_loop(self):
        """Background thread: hash queued files one at a time (big files take a while)."""
        while not self._stop.is_set():  # until disconnect
            self._hash_wake.wait(1.0)  # sleep until there is work
            self._hash_wake.clear()  # reset
            while self._hash_queue and not self._stop.is_set():  # work available
                name = self._hash_queue.pop(0)  # oldest first
                with self._lock:  # read the record
                    sf = self.shared.get(name)  # may have been deleted meanwhile
                if sf is None or sf.status != "hashing":  # nothing to do
                    continue  # next
                def prog(done, total, sf=sf):  # progress callback
                    sf.progress = min(1.0, done / float(total or 1))  # 0..1
                try:  # the file may change or vanish while hashing
                    meta = chunks.create_metadata(sf.path, progress=prog)  # split + hash
                except OSError as exc:  # unreadable
                    sf.status, sf.error = "error", str(exc)  # show the reason
                    continue  # next file
                with self._lock:  # store the result
                    if self.shared.get(name) is not sf:  # removed while hashing
                        continue  # drop the result
                    self._cache[name] = {"size": sf.size, "mtime": sf.mtime, "meta": meta}  # cache it
                    self._activate(sf, meta)  # start seeding
                self._save_cache()  # persist
                self._announce()  # tell the tracker immediately

    def _scan_loop(self):
        """Rescan the folder every few seconds."""
        while not self._stop.wait(SCAN_EVERY):  # until disconnect
            self._scan()  # look again

    # ------------------------------------------------------------------ tracker communication
    def _device(self):
        """What the server shows about this PC."""
        return {"name": self.device_name, "os": netutil.os_name(), "lan_ip": netutil.lan_ip()}  # no folder path

    def _file_states(self):
        """The per-file part of ANNOUNCE."""
        out = []  # result
        with self._lock:  # consistent snapshot
            up = dict(self.server.uploaded_by_file)  # per-file upload counters
            for sf in self.shared.values():  # seeding files
                if sf.status != "seeding":  # hashing / paused / error
                    continue  # not offered
                m = sf.meta  # metadata
                out.append({"file_id": m["file_id"], "name": m["name"], "size": m["size"],
                            "num_chunks": m["num_chunks"], "bitmap": "", "chunks_held": m["num_chunks"],
                            "uploaded": up.get(m["file_id"], 0), "downloaded": 0,
                            "extra": {"role": "seeder"}})  # complete copy: no bitmap needed
            offered = {x["file_id"] for x in out}  # avoid duplicates
            for d in self.downloads.values():  # partial files
                if d.store is None or d.status == "done" or d.file_id in offered:  # nothing to report
                    continue  # skip
                bitmap = d.store.bitmap()  # list of 0/1
                extra = {"role": "downloader"}  # dashboard info
                if d.downloader is not None:  # engine details
                    extra["strategy"] = d.downloader.strategy_name  # rarest / random
                    if d.meta["num_chunks"] <= 2000:  # keep the message small for huge files
                        extra["sources"] = {str(i): s for i, s in list(d.downloader.sources.items())}  # who gave what
                out.append({"file_id": d.file_id, "name": d.meta["name"], "size": d.meta["size"],
                            "num_chunks": d.meta["num_chunks"], "bitmap": "".join(str(b) for b in bitmap),
                            "chunks_held": sum(bitmap), "uploaded": up.get(d.file_id, 0),
                            "downloaded": d.downloader.downloaded if d.downloader else 0, "extra": extra})
        return out  # list of dicts

    def _announce(self):
        """Send one ANNOUNCE and update our connection status."""
        if self.tracker is None:  # not started
            return  # nothing to do
        try:  # the tracker may be down
            reply = self.tracker.announce(self._device(), self._file_states())  # one message for everything
            self.my_ip = reply.get("your_ip", self.my_ip)  # how the tracker sees us
            if self.status != "online":  # we were reconnecting
                self.message = "Connected to %s" % self.server_info.get("name", "server")  # back
            self.status = "online"  # good
        except P.ProtocolError as exc:  # refused
            if "disconnected" in str(exc):  # kicked by the server
                self.status = "kicked"  # show it in red
                self.message = "The server disconnected this device. Retrying in a moment."  # explain
            else:  # other refusal
                self.status, self.message = "reconnecting", str(exc)  # show it
        except OSError:  # unreachable
            self.status = "reconnecting"  # amber
            self.message = "Server unreachable, retrying..."  # explain

    def _announce_loop(self):
        """Heartbeat: ANNOUNCE every HEARTBEAT_INTERVAL seconds."""
        while not self._stop.wait(config.HEARTBEAT_INTERVAL):  # until disconnect
            self._announce()  # one beat

    def _swarm_loop(self):
        """Refresh the list of files available in the swarm."""
        while not self._stop.is_set():  # until disconnect
            try:  # tracker may be down
                files = self.tracker.list_files()  # LIST_FILES
                with self._lock:  # swap it in
                    self.swarm = files  # newest picture
            except (OSError, P.ProtocolError):  # unreachable
                pass  # keep the old list; _announce reports the status
            self._stop.wait(SWARM_EVERY)  # wait

    def _rate_loop(self):
        """Once per second: compute download/upload speeds and keep a short history."""
        while not self._stop.wait(1.0):  # until disconnect
            with self._lock:  # consistent numbers
                total_down = 0.0  # sum of downloads
                for d in self.downloads.values():  # every download
                    dl = d.downloader  # current engine
                    now_bytes = dl.downloaded if dl is not None else 0  # bytes in this engine
                    if dl is not d._last_obj:  # engine replaced (resume) -> start counting again
                        d._last_obj, d._last_bytes = dl, 0  # reset
                    d.rate = max(0.0, now_bytes - d._last_bytes) if d.status == "downloading" else 0.0  # B/s
                    self.total_downloaded += max(0, now_bytes - d._last_bytes)  # session total
                    d._last_bytes = now_bytes  # remember
                    d.rate_samples = (d.rate_samples + [d.rate])[-5:]  # last 5 seconds
                    total_down += d.rate  # add it
                up_total = self.server.uploaded  # bytes uploaded so far
                self.up_rate = max(0, up_total - self._last_up_total)  # B/s
                self._last_up_total = up_total  # remember
                for fid, n in list(self.server.uploaded_by_file.items()):  # per file
                    self.file_up_rate[fid] = max(0, n - self._last_up.get(fid, 0))  # B/s
                    self._last_up[fid] = n  # remember
                self.down_rate = total_down  # B/s
                self.peak_down = max(self.peak_down, total_down)  # best so far
                self.history.append({"t": time.time(), "down": total_down, "up": self.up_rate})  # sample
                del self.history[:-HISTORY]  # keep the last 2 minutes

    # ------------------------------------------------------------------ downloads
    def start_download(self, file_id):
        """Begin (or resume) downloading a swarm file into the shared folder."""
        with self._lock:  # exclusive access
            d = self.downloads.get(file_id)  # already known?
            if d is not None and d.status in ("starting", "downloading"):  # already running
                return d  # nothing to do
            if d is None:  # brand new
                info = next((f for f in self.swarm if f["file_id"] == file_id), None)  # from LIST_FILES
                if info is None:  # unknown id
                    raise KeyError("file is not in the swarm")  # explain
                if any(s.meta and s.meta["file_id"] == file_id for s in self.shared.values()):  # already have it
                    raise ValueError("you already have this file")  # explain
                d = Download(file_id, info["name"], info["size"])  # new record
                self.downloads[file_id] = d  # remember it
            d.status, d.message, d.user_paused = "starting", "Looking for peers...", False  # reset
            d.started = time.time()  # restart the slow grace period
            d.rate_samples = []  # forget old speeds
        threading.Thread(target=self._run_download, args=(d,), daemon=True).start()  # work in the background
        return d  # the record

    def _fetch_meta(self, d):
        """Get the metadata from any peer that has the file."""
        addrs = self.tracker.get_peers(d.file_id)  # who is in the swarm
        if not addrs:  # nobody
            raise P.ProtocolError("no peer has this file right now")  # explain
        client = PeerClient()  # our download side
        last = None  # last error
        for addr in addrs:  # try each peer
            try:  # this one may be dead
                return client.get_metadata(addr, d.file_id)  # verified metadata
            except (OSError, P.ProtocolError) as exc:  # failed
                last = exc  # try the next
        raise P.ProtocolError("could not get file info from any peer (%s)" % last)  # all failed

    def _run_download(self, d):
        """Background thread for one download."""
        try:  # network problems end in 'stalled'
            if d.meta is None:  # first start
                meta = self._fetch_meta(d)  # GET_METADATA
                part = self._state_dir("incoming", "%s_%s" % (d.file_id[:12], safe_name(meta["name"])))  # temp
                with self._lock:  # store the result
                    d.meta = meta  # metadata
                    d.name = safe_name(meta["name"])  # trusted name
                    d.size = meta["size"]  # trusted size
                    d.store = chunks.ChunkStore(meta, part, complete=False)  # pre-allocated temp file
            if d.user_paused:  # paused while we were looking for peers
                d.status, d.message = "paused", "Paused"  # stay paused
                return  # do not start the engine
            self.server.add_store(d.file_id, d.store)  # upload the chunks we already have while downloading
            dl = Downloader(d.meta, d.store, PeerClient(), self.tracker,
                            progress_path=d.store.path + ".progress")  # engine (resumes from the progress file)
            with self._lock:  # publish it
                d.downloader = dl  # the UI reads its progress
                d.status, d.message = "downloading", ""  # running
            self._announce()  # the tracker now lists us as a leecher
            ok = dl.run()  # blocks until done, stalled or paused
        except (OSError, P.ProtocolError) as exc:  # no peers / network trouble
            with self._lock:  # update the record
                d.status, d.message = "stalled", str(exc)  # red in the UI
            return  # the user can press retry
        if ok:  # complete and the whole-file hash matched
            self._finish(d)  # move it into the shared folder
        elif d.user_paused:  # the user pressed pause
            d.status, d.message = "paused", "Paused"  # grey
        elif d.store.is_complete():  # all chunks but the final hash failed
            d.status, d.message = "failed", "File hash mismatch"  # should never happen
        else:  # nobody could serve the missing chunks for 30 s
            done, total = d.chunks_done()  # progress
            d.status = "stalled"  # red
            d.message = "No peer has the missing pieces (%d/%d chunks). Retry when a seeder is online." % (done, total)

    def _finish(self, d):
        """Move a completed download into the shared folder and seed it."""
        with self._lock:  # the folder scanner must not see the file before it is registered
            final = unique_path(self.folder, d.name)  # never overwrite the user's files
            self.server.remove_store(d.file_id)  # nobody may read the temp file while we move it
            for attempt in range(20):  # Windows refuses to move a file another thread still has open
                try:  # usually works at once
                    os.replace(d.store.path, final)  # move (same disk, instant)
                    break  # moved
                except PermissionError:  # an upload was reading it
                    time.sleep(0.1)  # wait for it to finish
            st = os.stat(final)  # size + mtime for the cache
            name = os.path.basename(final)  # may have a (1) suffix
            sf = SharedFile(name, final)  # new record
            sf.size, sf.mtime = st.st_size, st.st_mtime  # what is on disk
            self._cache[name] = {"size": sf.size, "mtime": sf.mtime, "meta": d.meta}  # cache the hashes
            self._activate(sf, d.meta)  # seed from the new location (replaces the temp store)
            d.status, d.message, d.final_path, d.finished = "done", "Saved to shared folder", final, time.time()
        try:  # the progress file is useless now
            os.remove(d.store.path + ".progress")  # clean up
        except OSError:  # already gone
            pass  # fine
        self._save_cache()  # persist
        self._announce()  # we are a seeder now

    def pause_download(self, file_id):
        """Stop a running download; progress stays on disk."""
        with self._lock:  # find it
            d = self.downloads[file_id]  # KeyError if unknown
            d.user_paused = True  # remember why it stops
            d.status, d.message = "paused", "Paused"  # immediate UI feedback
        if d.downloader is not None:  # running
            d.downloader.stop()  # workers end after the current chunk

    def cancel_download(self, file_id):
        """Stop a download and delete its partial data."""
        self.pause_download(file_id)  # stop it first
        with self._lock:  # remove it
            d = self.downloads.pop(file_id)  # forget it
        if d.store is not None and d.status != "done":  # partial file exists
            self.server.remove_store(file_id)  # stop serving its chunks
            time.sleep(0.2)  # let workers finish their current write
            for path in (d.store.path, d.store.path + ".progress"):  # temp files
                try:  # may not exist
                    os.remove(path)  # delete
                except OSError:  # already gone
                    pass  # fine

    def clear_finished(self):
        """Remove finished downloads from the list."""
        with self._lock:  # exclusive access
            for fid in [k for k, d in self.downloads.items() if d.status == "done"]:  # finished ones
                del self.downloads[fid]  # forget

    # ------------------------------------------------------------------ shared-file actions
    def pause_share(self, name):
        """Stop offering one file (it stays in the folder)."""
        with self._lock:  # exclusive access
            sf = self.shared[name]  # KeyError if unknown
            if sf.status == "seeding":  # only seeding files can pause
                self._unshare(sf)  # stop serving it
                sf.status = "paused"  # grey
            self.paused_names.add(name)  # remember across restarts
        self._save_cache()  # persist
        self._announce()  # tracker drops it

    def resume_share(self, name):
        """Offer a paused file again."""
        with self._lock:  # exclusive access
            sf = self.shared[name]  # KeyError if unknown
            self.paused_names.discard(name)  # not paused any more
            if sf.status == "paused" and sf.meta is not None:  # hashed already
                sf.status = "seeding"  # offered again
                self.server.add_store(sf.meta["file_id"], sf.store)  # serve its chunks
        self._save_cache()  # persist
        self._announce()  # tracker lists it again

    def delete_file(self, name):
        """Delete a file from the shared folder (the UI asks for confirmation first)."""
        with self._lock:  # exclusive access
            sf = self.shared.pop(name)  # KeyError if unknown
            self._unshare(sf)  # stop serving it
            self._cache.pop(name, None)  # forget the hashes
            self.paused_names.discard(name)  # forget the pause
        os.remove(sf.path)  # delete from disk
        self._save_cache()  # persist
        self._announce()  # tracker drops it

    def upload_paths(self, name):
        """(temp path, final path) for a file the user adds through the UI.
        The temp file lives in .minitorrent/uploads so the scanner never sees half a file."""
        final = unique_path(self.folder, safe_name(name))  # never overwrite
        tmp = self._state_dir("uploads", os.path.basename(final))  # outside the shared listing
        return tmp, final  # caller writes tmp, then calls finish_upload

    def finish_upload(self, tmp, final):
        """Move an uploaded file into the shared folder; it is hashed and seeded right away."""
        os.replace(tmp, final)  # appears in the folder in one step
        self._scan()  # pick it up now instead of in 3 seconds
        return os.path.basename(final)  # final name

    # ------------------------------------------------------------------ view for the UI
    def _health(self, info, downloading=None):
        """'healthy' (green), 'low' (amber, one source), 'slow' or 'unavailable' (red) for a swarm file."""
        me = "%s:%d" % (self.my_ip, self.server.port) if self.my_ip else None  # our id at the tracker
        others = [h for h in info.get("holders", []) if h != me]  # peers other than us
        if not others or info.get("missing_chunks", 0) > 0:  # nobody, or some chunk is held by nobody
            return "unavailable", "No online peer has the complete file"  # red
        if downloading is not None and downloading.status == "downloading":  # we can measure real speed
            samples = downloading.rate_samples  # last seconds
            if time.time() - downloading.started > 6 and len(samples) >= 5 and max(samples) < SLOW_RATE:  # slow
                return "slow", "Downloading below 100 KB/s"  # red
        if len(others) == 1:  # a single source: works, but no backup if that peer leaves
            return "low", "Only one peer has this file"  # amber
        return "healthy", "%d peers sharing" % len(others)  # green

    def snapshot(self):
        """Everything the client screen needs, as plain JSON-able data."""
        with self._lock:  # consistent view
            swarm = {f["file_id"]: f for f in self.swarm}  # id -> info
            me = "%s:%d" % (self.my_ip, self.server.port) if self.my_ip and self.server else None  # our id
            shared = []  # my files
            mine = set()  # file ids I hold completely
            for sf in sorted(self.shared.values(), key=lambda s: s.name.lower()):  # alphabetical
                fid = sf.meta["file_id"] if sf.meta else None  # may still be hashing
                if fid:  # hashed
                    mine.add(fid)  # I have it
                info = swarm.get(fid, {})  # swarm numbers
                peers = [h for h in info.get("holders", []) if h != me]  # other holders
                shared.append({"name": sf.name, "size": sf.size, "status": sf.status, "file_id": fid,
                               "progress": sf.progress, "error": sf.error, "peers": len(peers),
                               "leechers": info.get("leechers", 0),
                               "up_rate": self.file_up_rate.get(fid, 0) if sf.status == "seeding" else 0})
            downloads = []  # files being fetched
            for d in sorted(self.downloads.values(), key=lambda x: x.started, reverse=True):  # newest first
                done, total = d.chunks_done()  # progress
                health = self._health(swarm[d.file_id], d) if d.file_id in swarm else ("unavailable", "Not in swarm")
                if d.status in ("done", "paused"):  # health does not matter any more
                    health = ("healthy", "")  # neutral
                remaining = (d.size * (1 - done / float(total))) if total else d.size  # bytes left
                downloads.append({"file_id": d.file_id, "name": d.name, "size": d.size, "status": d.status,
                                  "message": d.message, "chunks_done": done, "chunks_total": total,
                                  "progress": (done / float(total)) if total else 0.0, "rate": d.rate,
                                  "eta": (remaining / d.rate) if d.rate > 0 else None,
                                  "health": health[0], "health_reason": health[1],
                                  "hash_failures": d.downloader.hash_failures if d.downloader else 0,
                                  "peer_failures": d.downloader.peer_failures if d.downloader else 0,
                                  "sources": ({str(i): s for i, s in list(d.downloader.sources.items())}
                                              if d.downloader and total <= 2000 else {}),
                                  "bitmap": "".join(str(b) for b in d.store.bitmap()) if d.store and total <= 2000
                                  else ""})
            available = []  # swarm files I could download
            for f in self.swarm:  # every swarm file
                if f["file_id"] in mine:  # already complete in my folder
                    continue  # not offered
                health = self._health(f, self.downloads.get(f["file_id"]))  # colour
                d = self.downloads.get(f["file_id"])  # am I downloading it?
                available.append({"file_id": f["file_id"], "name": f["name"], "size": f["size"],
                                  "seeders": f["seeders"], "leechers": f["leechers"],
                                  "health": health[0], "health_reason": health[1],
                                  "download_status": d.status if d else None,
                                  "progress": (d.chunks_done()[0] / float(d.chunks_done()[1]))
                                  if d and d.chunks_done()[1] else 0.0})
            return {
                "status": self.status, "message": self.message,
                "server": "%s:%d" % self.tracker_addr, "server_name": self.server_info.get("name", ""),
                "server_version": self.server_info.get("version", ""),
                "my_ip": self.my_ip, "peer_port": self.server.port if self.server else None,
                "device_name": self.device_name, "folder": self.folder,
                "stats": {"down_rate": self.down_rate, "up_rate": self.up_rate, "peak_down": self.peak_down,
                          "uploaded": self.server.uploaded if self.server else 0,
                          "downloaded": self.total_downloaded,
                          "seeders": sum(f["seeders"] for f in self.swarm),
                          "leechers": sum(f["leechers"] for f in self.swarm),
                          "requesting": sum(1 for f in self.swarm if f["leechers"]),
                          "swarm_files": len(self.swarm)},
                "shared": shared, "downloads": downloads, "available": available,
                "history": list(self.history),
            }
