"""
peer/network.py  --  OWNER: AYAAN
Everything a peer does on the network:
    PeerServer    : listens on a port and UPLOADS chunks to other peers
    PeerClient    : asks other peers for their bitmap and for chunks
    TrackerClient : REGISTER / GET_PEERS / HEARTBEAT with the tracker
    DummyChunkStore : fake storage so this file can be tested without Maaz's code
"""

import hashlib  # hash of the chunk we send (goes into the CHUNK_DATA header)
import socket  # TCP sockets
import threading  # one thread per connection + heartbeat thread
import time  # sleep for the simulated upload delay

from common import config  # timeouts and intervals
from common import protocol as P  # send_msg / recv_msg and message names


class PeerServer:
    """The upload side of a peer: answers HAVE_BITMAP and REQUEST_CHUNK."""

    def __init__(self, port, host="0.0.0.0", upload_delay=None):
        self.host = host  # 0.0.0.0 = accept connections on every network card
        self.port = port  # the TCP port other peers connect to
        self.stores = {}  # file_id -> chunk store (what we can upload)
        self.uploaded = 0  # total bytes uploaded (shown on the dashboard)
        self.upload_delay = config.UPLOAD_DELAY if upload_delay is None else upload_delay  # fake slowness
        self._lock = threading.Lock()  # protects stores, uploaded and the client list
        self._upload_slot = threading.Lock()  # with a delay, only one chunk is "on the wire" at a time
        self._listener = None  # the listening socket (created in start)
        self._clients = set()  # open connections, so stop() can close them
        self._running = False  # becomes True in start()

    def add_store(self, file_id, store):
        """Start sharing a file."""
        with self._lock:  # stores is shared between threads
            self.stores[file_id] = store  # remember the store under its file_id

    def start(self):
        """Open the listening socket and start accepting in a background thread."""
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # IPv4 + TCP
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # allow quick restart on same port
        self._listener.bind((self.host, self.port))  # claim the port
        self._listener.listen(50)  # up to 50 connections may wait in the queue
        self.port = self._listener.getsockname()[1]  # if port was 0 the OS picked one, read it back
        self._running = True  # the accept loop may run now
        threading.Thread(target=self._accept_loop, daemon=True).start()  # daemon = dies with the program
        return self  # allows PeerServer(...).start()

    def stop(self):
        """Stop like a crashed peer: close the listener and every open connection."""
        self._running = False  # tell the loops to end
        try:  # the listener may already be closed
            self._listener.close()  # no new connections
        except OSError:  # ignore "already closed"
            pass  # nothing to do
        with self._lock:  # copy the client list safely
            clients = list(self._clients)  # snapshot
        for c in clients:  # every open connection
            try:  # it may already be closed
                c.close()  # cut it off (the other side sees an error)
            except OSError:  # ignore
                pass  # nothing to do

    def _accept_loop(self):
        """Wait for connections forever; give each one its own thread."""
        while self._running:  # until stop() is called
            try:  # accept fails when the listener is closed
                conn, addr = self._listener.accept()  # blocks until a peer connects
            except OSError:  # listener was closed by stop()
                break  # leave the loop
            with self._lock:  # client set is shared
                self._clients.add(conn)  # remember it for stop()
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()  # thread per connection

    def _handle(self, conn):
        """Serve one connection: answer messages until the other side hangs up."""
        try:  # any network error just ends this connection
            conn.settimeout(30)  # do not keep a silent connection forever
            while self._running:  # several requests may come over one connection
                header, _ = P.recv_msg(conn)  # wait for the next request
                reply, payload = self._answer(header)  # build the reply
                P.send_msg(conn, reply, payload)  # send it back
        except (P.ProtocolError, OSError, ValueError):  # closed, timed out or garbage
            pass  # normal end of a connection
        finally:  # always clean up
            with self._lock:  # client set is shared
                self._clients.discard(conn)  # forget this connection
            try:  # may already be closed
                conn.close()  # free the socket
            except OSError:  # ignore
                pass  # nothing to do

    def _answer(self, header):
        """Decide the reply for one request. Returns (reply_header, payload_or_None)."""
        mtype = header.get("type")  # which message is this?
        with self._lock:  # stores is shared
            store = self.stores.get(header.get("file_id"))  # the file the peer asks about
        if store is None:  # we do not share that file
            return {"type": P.ERROR, "reason": "unknown file"}, None  # say so
        if mtype == P.HAVE_BITMAP:  # "which chunks do you hold?"
            return {"type": P.HAVE_BITMAP, "bitmap": store.bitmap()}, None  # list of 0/1
        if mtype == P.REQUEST_CHUNK:  # "send me chunk i"
            index = header.get("index", -1)  # the wanted chunk number
            if not store.has(index):  # we do not hold it
                return {"type": P.ERROR, "reason": "chunk not available"}, None  # say so
            data = store.read_chunk(index)  # read the bytes from disk
            if self.upload_delay > 0:  # simulated slow link (used in demos/experiments)
                with self._upload_slot:  # one chunk at a time, like a limited uplink
                    time.sleep(self.upload_delay)  # pretend the upload takes time
            with self._lock:  # counter is shared
                self.uploaded += len(data)  # count the bytes for the dashboard
            reply = {"type": P.CHUNK_DATA, "index": index, "hash": hashlib.sha256(data).hexdigest()}  # header
            return reply, data  # header + raw chunk bytes
        return {"type": P.ERROR, "reason": "unknown message type"}, None  # anything else is an error


class PeerClient:
    """The download side of a peer: talks to other peers' PeerServer."""

    def __init__(self, timeout=None):
        self.timeout = config.SOCKET_TIMEOUT if timeout is None else timeout  # 5 seconds by default

    def get_bitmap(self, addr, file_id):
        """Ask the peer at addr which chunks it holds. Returns a list of 0/1."""
        header, _ = P.request(addr, {"type": P.HAVE_BITMAP, "file_id": file_id}, timeout=self.timeout)  # ask
        if header.get("type") != P.HAVE_BITMAP:  # the peer answered with an ERROR
            raise P.ProtocolError(header.get("reason", "bad bitmap reply"))  # report it
        return header["bitmap"]  # the list of 0/1

    def fetch_chunk(self, addr, file_id, index):
        """Download chunk index from the peer at addr. Returns the raw bytes."""
        msg = {"type": P.REQUEST_CHUNK, "file_id": file_id, "index": index}  # the request
        header, payload = P.request(addr, msg, timeout=self.timeout)  # send and wait (max 5 s)
        if header.get("type") != P.CHUNK_DATA or payload is None:  # ERROR or missing data
            raise P.ProtocolError(header.get("reason", "bad chunk reply"))  # report it
        return payload  # caller verifies the hash against the .mtorrent


class TrackerClient:
    """Talks to the tracker: register, get the peer list, send heartbeats."""

    def __init__(self, tracker_addr, my_port, timeout=None):
        self.tracker_addr = tracker_addr  # (host, port) of the tracker
        self.my_port = my_port  # the port OUR PeerServer listens on
        self.timeout = config.SOCKET_TIMEOUT if timeout is None else timeout  # 5 seconds by default
        self._stop = threading.Event()  # set() ends the heartbeat thread
        self._thread = None  # the heartbeat thread

    def register(self, state):
        """Announce ourselves. state = dict with file_id, name, size, num_chunks, bitmap..."""
        msg = dict(state, type=P.REGISTER, port=self.my_port)  # copy state and add type + our port
        header, _ = P.request(self.tracker_addr, msg, timeout=self.timeout)  # send and wait
        return header.get("type") == P.OK  # True if the tracker accepted us

    def get_peers(self, file_id):
        """Ask who has the file. Returns a list of (ip, port) tuples (never ourselves)."""
        msg = {"type": P.GET_PEERS, "file_id": file_id, "port": self.my_port}  # our port lets the tracker skip us
        header, _ = P.request(self.tracker_addr, msg, timeout=self.timeout)  # send and wait
        if header.get("type") != P.PEERS:  # tracker answered with an ERROR
            raise P.ProtocolError(header.get("reason", "bad peers reply"))  # report it
        return [(p["ip"], p["port"]) for p in header["peers"]]  # dicts -> address tuples

    def heartbeat(self, state):
        """Send one HEARTBEAT carrying our current progress."""
        msg = dict(state, type=P.HEARTBEAT, port=self.my_port)  # copy state and add type + our port
        P.request(self.tracker_addr, msg, timeout=self.timeout)  # send and wait for OK

    def start_heartbeat(self, state_fn, interval=None):
        """Send a heartbeat every few seconds in the background. state_fn() returns fresh state."""
        interval = config.HEARTBEAT_INTERVAL if interval is None else interval  # 5 seconds by default

        def loop():  # the body of the heartbeat thread
            while not self._stop.wait(interval):  # sleep 'interval' seconds, exit early on stop()
                try:  # the tracker may be down for a moment
                    self.heartbeat(state_fn())  # tell the tracker we are alive
                except (OSError, P.ProtocolError):  # tracker unreachable
                    pass  # just try again at the next beat

        self._thread = threading.Thread(target=loop, daemon=True)  # daemon = dies with the program
        self._thread.start()  # start beating

    def stop(self):
        """Stop the heartbeat thread."""
        self._stop.set()  # wakes the loop and ends it


class DummyChunkStore:
    """Fake chunk store that lives in RAM. Lets Ayaan test networking without chunks.py."""

    def __init__(self, chunks):
        self.chunks = dict(chunks)  # {index: bytes}
        self.total = (max(self.chunks) + 1) if self.chunks else 0  # number of chunk slots

    def has(self, i):
        return i in self.chunks  # held if the index is in the dict

    def bitmap(self):
        return [1 if i in self.chunks else 0 for i in range(self.total)]  # 0/1 list

    def read_chunk(self, i):
        return self.chunks[i]  # the bytes of chunk i
