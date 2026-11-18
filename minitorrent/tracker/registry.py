"""
tracker/registry.py  --  OWNER: ARBAB
The tracker's memory: which peers are alive and which chunks of which file they hold.
The tracker NEVER stores file data, only this metadata.
"""

import collections  # deque = a list with a maximum length (for the event log)
import threading  # many client threads touch the registry, so we lock it
import time  # timestamps for heartbeats

from common import config  # PEER_TIMEOUT

DEVICE_FORGET = 600.0  # an offline device stays in the list (greyed out) for 10 minutes, then disappears
KICK_SECONDS = 60.0  # a device the server disconnected may not come back for this long


def device_key(ip, port):
    """Identity of a device = the address the tracker saw + the port its peer server listens on."""
    return "%s:%d" % (ip, int(port))  # e.g. '192.168.1.104:6001'


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
        self.devices = {}  # 'ip:port' -> {name, os, lan_ip, first_seen, last_seen, ...} (from ANNOUNCE)
        self.kicked = {}  # 'ip:port' -> time until which the server refuses this device
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
        with self._lock:  # exclusive access
            return self._upsert_locked(ip, msg, is_register)  # the real work

    def _upsert_locked(self, ip, msg, is_register, quiet=False):
        """upsert_peer without taking the lock (caller holds it)."""
        now = time.time()  # the moment we heard from the peer
        file_id = msg["file_id"]  # which file the peer talks about
        key = (file_id, ip, int(msg["port"]))  # identity of a peer = file + ip + port
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
        if quiet:  # ANNOUNCE logs ONE event per device instead of one per file
            pass  # nothing to log here
        elif old is None or is_register:  # a join is worth an event
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
            for dkey, dev in list(self.devices.items()):  # devices that went quiet
                silent = now - dev["last_seen"]  # seconds since its last ANNOUNCE
                if silent > self.timeout and dev.get("online", True):  # just went offline
                    dev["online"] = False  # grey it out in the server UI
                    self._event("timeout", "%s (%s) went offline" % (dev["name"], dkey))  # log
                if silent > DEVICE_FORGET:  # offline for a long time
                    del self.devices[dkey]  # forget it completely
            for dkey, until in list(self.kicked.items()):  # expired bans
                if until < now:  # the ban is over
                    del self.kicked[dkey]  # the device may connect again
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
                if not item["bitmap"] and item["chunks_held"] >= item["num_chunks"]:  # seeder sent no bitmap
                    item["bitmap"] = "1" * item["num_chunks"]  # it holds everything
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
                    bits = "1" * n if rec["chunks_held"] >= n else rec["bitmap"][:n]  # seeders may skip the bitmap
                    for i, bit in enumerate(bits):  # walk its bitmap string
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

    # ------------------------------------------------------------------ devices (GUI clients)
    def is_kicked(self, ip, port):
        """True if the server disconnected this device a moment ago."""
        with self._lock:  # exclusive access
            return self.kicked.get(device_key(ip, port), 0) > time.time()  # ban still running?

    def announce(self, ip, msg):
        """One ANNOUNCE = device info + the state of EVERY file it shares or downloads.

        Files the device no longer lists (deleted from its folder, paused) are removed, so the
        server always shows exactly what is in each device's shared folder right now.
        Returns False if the device is currently disconnected by the server.
        """
        port = int(msg["port"])  # the device's peer-server port
        dkey = device_key(ip, port)  # 'ip:port'
        now = time.time()  # timestamp
        dev_info = msg.get("device") or {}  # name, os, lan_ip, folder
        with self._lock:  # exclusive access
            if self.kicked.get(dkey, 0) > now:  # the server said "go away"
                return False  # refuse
            dev = self.devices.get(dkey)  # previous record
            if dev is None or not dev.get("online", True):  # new device or back from offline
                self._event("join", "%s (%s) connected" % (dev_info.get("name", "?"), dkey))  # one event per device
            self.devices[dkey] = {  # fresh record
                "key": dkey,  # 'ip:port'
                "ip": ip,  # address the tracker SAW
                "port": port,  # peer-server port
                "name": str(dev_info.get("name", dkey))[:80],  # PC name
                "os": str(dev_info.get("os", ""))[:40],  # Windows / Linux / Darwin
                "lan_ip": str(dev_info.get("lan_ip", ip))[:64],  # the address the device thinks it has
                "first_seen": dev["first_seen"] if dev else now,  # when it first connected
                "last_seen": now,  # heartbeat time
                "online": True,  # it just talked to us
            }
            listed = set()  # file_ids in this announce
            for f in msg.get("files", []):  # every file the device shares or downloads
                if "file_id" not in f:  # broken entry
                    continue  # ignore it
                entry = dict(f, port=port)  # the per-file record needs the port
                self._upsert_locked(ip, entry, is_register=False, quiet=True)  # reuse the normal path
                listed.add(f["file_id"])  # remember it
            for key in [k for k in self.peers if k[1] == ip and k[2] == port and k[0] not in listed]:  # dropped files
                del self.peers[key]  # forget them
                if self.storage is not None:  # keep SQLite in sync
                    self.storage.delete_peer(*key)  # delete the row
            return True  # accepted

    def kick_device(self, dkey, seconds=KICK_SECONDS):
        """Disconnect a device: forget its files and refuse its ANNOUNCEs for a while."""
        with self._lock:  # exclusive access
            dev = self.devices.get(dkey)  # may be a CLI peer without a device record
            ip, port = dkey.rsplit(":", 1)  # split 'ip:port'
            port = int(port)  # number
            for key in [k for k in self.peers if k[1] == ip and k[2] == port]:  # its files
                del self.peers[key]  # forget them
                if self.storage is not None:  # keep SQLite in sync
                    self.storage.delete_peer(*key)  # delete the row
            if dev is not None:  # GUI device
                dev["online"] = False  # show as offline
            self.kicked[dkey] = time.time() + seconds  # ban for a while
            self._event("timeout", "%s disconnected by the server" % (dev["name"] if dev else dkey))  # log
            return True  # done

    def _file_health(self, f):
        """Swarm numbers of one file (caller holds the lock)."""
        n = f["num_chunks"]  # total chunks
        availability = [0] * n  # per chunk: how many peers hold it
        seeders = leechers = 0  # counters
        up_rate = 0.0  # combined upload speed of everybody holding this file
        holders = []  # 'ip:port' of every peer in this file's swarm
        for (fid, ip, port), rec in self.peers.items():  # every peer record
            if fid != f["file_id"]:  # other file
                continue  # skip
            holders.append(device_key(ip, port))  # remember who
            up_rate += rec.get("up_rate", 0.0)  # add its speed
            if n and rec["chunks_held"] >= n:  # complete copy
                seeders += 1  # seeder
            else:  # partial copy
                leechers += 1  # leecher
            bits = "1" * n if rec["chunks_held"] >= n else rec["bitmap"][:n]  # seeders may skip the bitmap
            for i, bit in enumerate(bits):  # its chunks
                if bit == "1":  # holds chunk i
                    availability[i] += 1  # one more holder
        return {
            "seeders": seeders,  # complete copies online
            "leechers": leechers,  # partial copies online
            "holders": holders,  # who is in the swarm
            "min_availability": min(availability) if availability else 0,  # rarest chunk's holder count
            "missing_chunks": sum(1 for a in availability if a == 0),  # chunks NOBODY online has
            "swarm_up_rate": up_rate,  # bytes/second
        }

    def list_files(self):
        """Files that at least one online peer holds (answer to LIST_FILES). No chunk hashes here."""
        with self._lock:  # exclusive access
            out = []  # result
            for f in self.files.values():  # every known file
                h = self._file_health(f)  # swarm numbers
                if not h["holders"]:  # nobody online has it
                    continue  # do not offer it
                out.append(dict(f, **h))  # description + numbers
            out.sort(key=lambda x: x["name"].lower())  # alphabetical
            return out  # list of dicts

    def devices_snapshot(self):
        """Every device with the files it holds (for the server screen)."""
        now = time.time()  # for 'seconds ago'
        with self._lock:  # exclusive access
            devices = {k: dict(d, files=[]) for k, d in self.devices.items()}  # copies
            health = {fid: self._file_health(f) for fid, f in self.files.items()}  # per-file numbers
            for (fid, ip, port), rec in self.peers.items():  # every peer record
                dkey = device_key(ip, port)  # its device
                if dkey not in devices:  # a command-line peer (python -m peer.main) has no ANNOUNCE
                    devices[dkey] = {"key": dkey, "ip": ip, "port": port, "name": "peer " + dkey,
                                     "os": "cli", "lan_ip": ip, "first_seen": rec["first_seen"],
                                     "last_seen": rec["last_seen"], "online": True, "files": []}  # synthesize
                f = self.files.get(fid, {})  # file description
                h = health.get(fid, {})  # swarm numbers
                devices[dkey]["files"].append({  # what this device holds
                    "file_id": fid, "name": f.get("name", "?"), "size": f.get("size", 0),
                    "num_chunks": f.get("num_chunks", 0), "chunks_held": rec["chunks_held"],
                    "complete": bool(f.get("num_chunks")) and rec["chunks_held"] >= f.get("num_chunks", 0),
                    "seeders": h.get("seeders", 0), "leechers": h.get("leechers", 0),
                    "up_rate": rec.get("up_rate", 0.0), "down_rate": rec.get("down_rate", 0.0),
                })
                devices[dkey]["last_seen"] = max(devices[dkey]["last_seen"], rec["last_seen"])  # freshest
            out = []  # result
            for d in devices.values():  # finish every device
                d["files"].sort(key=lambda x: x["name"].lower())  # alphabetical
                d["seconds_ago"] = round(now - d["last_seen"], 1)  # heartbeat age
                d["online"] = d.get("online", True) and d["seconds_ago"] <= self.timeout  # alive?
                d["shared_count"] = sum(1 for x in d["files"] if x["complete"])  # complete files
                d["total_size"] = sum(x["size"] for x in d["files"] if x["complete"])  # bytes shared
                d["up_rate"] = sum(x["up_rate"] for x in d["files"])  # bytes/second
                d["down_rate"] = sum(x["down_rate"] for x in d["files"])  # bytes/second
                out.append(d)  # add it
            out.sort(key=lambda d: (not d["online"], d["name"].lower()))  # online first, then by name
            return out  # list of devices
