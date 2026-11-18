"""
tracker/registry.py  --  OWNER: ARBAB
The tracker's memory: which peers are alive and which chunks of which file they hold.
The tracker NEVER stores file data, only this metadata.
"""

import collections  # deque = a list with a maximum length (for the event log)
import threading  # many client threads touch the registry, so we lock it
import time  # timestamps for heartbeats

from common import config  # PEER_TIMEOUT


class Registry:
    """Thread-safe table of files and peers."""

    def __init__(self, storage=None, timeout=None):
        self.storage = storage  # optional SQLite storage (None = RAM only)
        self.timeout = config.PEER_TIMEOUT if timeout is None else timeout  # seconds without heartbeat
        self.started = time.time()  # tracker start time (for uptime)
        self._lock = threading.Lock()  # protects files, peers and events
        self.files = {}  # file_id -> {file_id, name, size, num_chunks}
        self.peers = {}  # (file_id, ip, port) -> peer record
        self.events = collections.deque(maxlen=200)  # last 200 things that happened
        if storage is not None:  # restore the previous state from SQLite
            for f in storage.load_files():  # every saved file
                self.files[f["file_id"]] = f  # put it back
            for p in storage.load_peers():  # every saved peer
                p["last_seen"] = time.time()  # grace period: it gets one full timeout to heartbeat again
                p["first_seen"] = p["last_seen"]  # we do not know the original value
                p["down_rate"] = 0.0  # speeds start at zero
                p["up_rate"] = 0.0  # speeds start at zero
                self.peers[(p["file_id"], p["ip"], p["port"])] = p  # put it back

    def _event(self, kind, text):
        """Remember something that happened (caller must hold the lock)."""
        self.events.append({"time": time.time(), "kind": kind, "text": text})  # newest at the right end

    def upsert_peer(self, ip, msg, is_register):
        """Insert or update a peer from a REGISTER or HEARTBEAT message. Returns the record."""
        now = time.time()  # the moment we heard from the peer
        file_id = msg["file_id"]  # which file the peer talks about
        key = (file_id, ip, int(msg["port"]))  # identity of a peer = file + ip + port
        with self._lock:  # exclusive access
            if file_id not in self.files:  # first time we hear about this file
                self.files[file_id] = {  # remember its description
                    "file_id": file_id,  # the id
                    "name": msg.get("name", "?"),  # file name
                    "size": int(msg.get("size", 0)),  # bytes
                    "num_chunks": int(msg.get("num_chunks", 0)),  # chunk count
                }
                if self.storage is not None:  # persist the new file
                    self.storage.save_file(self.files[file_id])  # write the row
            old = self.peers.get(key)  # previous record of this peer (None if new)
            uploaded = int(msg.get("uploaded", 0))  # total bytes it uploaded
            downloaded = int(msg.get("downloaded", 0))  # total bytes it downloaded
            down_rate = 0.0  # bytes per second, computed below
            up_rate = 0.0  # bytes per second, computed below
            if old is not None and now > old["last_seen"]:  # we can compare with the last report
                dt = now - old["last_seen"]  # seconds since the last report
                down_rate = max(0.0, (downloaded - old["downloaded"]) / dt)  # speed = bytes / time
                up_rate = max(0.0, (uploaded - old["uploaded"]) / dt)  # speed = bytes / time
            record = {  # the fresh record
                "file_id": file_id,  # which file
                "ip": ip,  # address the tracker SAW the peer connect from
                "port": key[2],  # the peer's listening port
                "last_seen": now,  # heartbeat timestamp
                "first_seen": old["first_seen"] if old else now,  # when it joined
                "chunks_held": int(msg.get("chunks_held", 0)),  # how many chunks it holds
                "bitmap": msg.get("bitmap", ""),  # "1101..." string
                "uploaded": uploaded,  # bytes
                "downloaded": downloaded,  # bytes
                "down_rate": down_rate,  # bytes/second
                "up_rate": up_rate,  # bytes/second
                "extra": msg.get("extra", {}),  # dashboard details (role, sources...)
            }
            self.peers[key] = record  # store it
            if old is None or is_register:  # a join is worth an event
                self._event("join", "%s:%d registered for %s" % (ip, key[2], self.files[file_id]["name"]))  # log
            elif old["chunks_held"] < self.files[file_id]["num_chunks"] <= record["chunks_held"]:  # just finished
                self._event("done", "%s:%d completed %s" % (ip, key[2], self.files[file_id]["name"]))  # log
            if self.storage is not None:  # persist the peer
                self.storage.save_peer(record)  # write the row
            return dict(record)  # return a copy

    def get_peers(self, file_id, exclude=None):
        """List the peers of a file (without the asker itself)."""
        with self._lock:  # exclusive access
            result = []  # what we will return
            for (fid, ip, port), rec in self.peers.items():  # look at every peer
                if fid != file_id:  # other file
                    continue  # skip
                if exclude is not None and (ip, port) == exclude:  # the asker itself
                    continue  # skip
                result.append({"ip": ip, "port": port, "chunks_held": rec["chunks_held"]})  # address + progress
            return result  # list of dicts

    def remove_stale(self):
        """Remove peers that have been silent longer than the timeout. Returns the removed keys."""
        now = time.time()  # current time
        removed = []  # keys we removed
        with self._lock:  # exclusive access
            for key, rec in list(self.peers.items()):  # list() because we delete while looping
                if now - rec["last_seen"] > self.timeout:  # silent for too long
                    del self.peers[key]  # forget the peer
                    removed.append(key)  # report it
                    self._event("timeout", "%s:%d timed out (no heartbeat for %ds)" % (key[1], key[2], self.timeout))
                    if self.storage is not None:  # keep SQLite in sync
                        self.storage.delete_peer(*key)  # delete the row
        return removed  # the server logs these

    def peers_snapshot(self):
        """All peers as a list of dicts (for GET /peers)."""
        now = time.time()  # to compute 'seconds since last heartbeat'
        with self._lock:  # exclusive access
            out = []  # result list
            for rec in self.peers.values():  # every peer
                item = dict(rec)  # copy so the API cannot change our data
                item["seconds_ago"] = round(now - rec["last_seen"], 1)  # how fresh the heartbeat is
                item["num_chunks"] = self.files[rec["file_id"]]["num_chunks"]  # total chunks of its file
                out.append(item)  # add to the result
            out.sort(key=lambda p: (p["file_id"], p["port"], p["ip"]))  # stable order for the dashboard
            return out  # list of peers

    def files_snapshot(self):
        """All files with swarm statistics (for GET /files)."""
        with self._lock:  # exclusive access
            out = []  # result list
            for f in self.files.values():  # every known file
                n = f["num_chunks"]  # total chunks
                availability = [0] * n  # per chunk: how many peers hold it
                seeders = 0  # peers with every chunk
                leechers = 0  # peers still downloading
                for rec in self.peers.values():  # look at the peers of this file
                    if rec["file_id"] != f["file_id"]:  # other file
                        continue  # skip
                    if n and rec["chunks_held"] >= n:  # holds everything
                        seeders += 1  # count as seeder
                    else:  # still missing chunks
                        leechers += 1  # count as leecher
                    for i, bit in enumerate(rec["bitmap"][:n]):  # walk its bitmap string
                        if bit == "1":  # it holds chunk i
                            availability[i] += 1  # one more holder
                out.append(dict(f, seeders=seeders, leechers=leechers, availability=availability))  # file + stats
            return out  # list of files

    def stats(self):
        """Overall numbers (for GET /stats)."""
        with self._lock:  # exclusive access
            peers = list(self.peers.values())  # snapshot
            return {  # the summary
                "peers_online": len(peers),  # peers alive right now
                "files": len(self.files),  # files known
                "total_uploaded": sum(p["uploaded"] for p in peers),  # bytes uploaded by live peers
                "total_downloaded": sum(p["downloaded"] for p in peers),  # bytes downloaded by live peers
                "swarm_down_rate": sum(p["down_rate"] for p in peers),  # combined download speed
                "uptime": round(time.time() - self.started, 1),  # seconds since the tracker started
                "peer_timeout": self.timeout,  # the timeout in use
            }

    def events_snapshot(self, limit=50):
        """The newest events first (for GET /events)."""
        with self._lock:  # exclusive access
            return list(self.events)[-limit:][::-1]  # last 'limit' events, reversed
