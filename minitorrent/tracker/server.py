"""
tracker/server.py  --  OWNER: ARBAB
The tracker process: a TCP server (thread per client) that understands
REGISTER, GET_PEERS and HEARTBEAT, a reaper thread that removes dead peers,
and the FastAPI app for the dashboard.

    python -m tracker.server --port 5000 --api-port 8000
"""

import argparse  # command-line options
import logging  # log every REGISTER / GET_PEERS / timeout
import socket  # TCP sockets
import threading  # thread per client + reaper thread

from common import config  # default ports and timeout
from common import netutil  # PC name and LAN IP
from common import protocol as P  # send_msg / recv_msg and message names
from tracker.registry import Registry  # the peer table
from tracker.storage import Storage  # SQLite persistence

log = logging.getLogger("tracker")  # our logger
VERSION = "2.0"  # shown on the Connect screen after a successful PING


class TrackerServer:
    """TCP side of the tracker."""

    def __init__(self, registry, host="0.0.0.0", port=None):
        self.registry = registry  # where peers are stored
        self.host = host  # 0.0.0.0 = reachable from other machines
        self.port = config.TRACKER_PORT if port is None else port  # 5000 by default
        self._listener = None  # listening socket
        self._running = False  # True after start()

    def start(self):
        """Open the socket and start the accept + reaper threads."""
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # IPv4 + TCP
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # quick restart on same port
        self._listener.bind((self.host, self.port))  # claim the port
        self._listener.listen(100)  # queue up to 100 waiting connections
        self.port = self._listener.getsockname()[1]  # real port (useful when port=0 in tests)
        self._running = True  # loops may run
        threading.Thread(target=self._accept_loop, daemon=True).start()  # accepts peers
        threading.Thread(target=self._reaper_loop, daemon=True).start()  # removes dead peers
        log.info("tracker listening on %s:%d (peer timeout %ss)", self.host, self.port, self.registry.timeout)
        return self  # allows TrackerServer(...).start()

    def stop(self):
        """Stop the tracker."""
        self._running = False  # loops end
        try:  # may already be closed
            self._listener.close()  # stop accepting
        except OSError:  # ignore
            pass  # nothing to do

    def _accept_loop(self):
        """Accept connections forever, one thread per client."""
        while self._running:  # until stop()
            try:  # accept fails when the listener closes
                conn, addr = self._listener.accept()  # wait for a peer
            except OSError:  # listener closed
                break  # leave the loop
            threading.Thread(target=self._handle, args=(conn, addr), daemon=True).start()  # serve it

    def _reaper_loop(self):
        """Every second, remove peers whose heartbeat is too old."""
        stop = threading.Event()  # only used as an interruptible sleep
        while self._running:  # until stop()
            for file_id, ip, port in self.registry.remove_stale():  # dead peers
                log.warning("TIMEOUT    %s:%d removed (file %s)", ip, port, file_id[:8])  # log each one
            stop.wait(1.0)  # check again in one second

    def _handle(self, conn, addr):
        """Serve one client connection."""
        ip = addr[0]  # the IP address we SEE the peer coming from
        try:  # network errors just end the connection
            conn.settimeout(config.SOCKET_TIMEOUT * 2)  # do not wait forever on a silent client
            while self._running:  # a client may send several messages
                header, _ = P.recv_msg(conn)  # next request
                P.send_msg(conn, self._answer(ip, header))  # reply
        except (P.ProtocolError, OSError):  # closed / timed out
            pass  # normal end
        finally:  # always free the socket
            conn.close()  # done

    def _answer(self, ip, header):
        """Build the reply for one tracker message."""
        mtype = header.get("type")  # which message?
        if mtype == P.PING:  # the Connect screen checks that a tracker really lives here
            return {"type": P.PONG, "name": netutil.device_name(), "version": VERSION,
                    "your_ip": ip, "timeout": self.registry.timeout}  # tracker identity
        if mtype == P.LIST_FILES:  # a client wants the swarm's file list
            return {"type": P.FILES, "files": self.registry.list_files()}  # names, sizes, seeders...
        if mtype == P.ANNOUNCE:  # a GUI client reports its device + every file
            if "port" not in header:  # we must know where it listens
                return {"type": P.ERROR, "reason": "port missing"}  # refuse
            if not self.registry.announce(ip, header):  # the server disconnected this device
                return {"type": P.ERROR, "reason": "disconnected by server"}  # tell it
            return {"type": P.OK, "your_ip": ip}  # accepted
        if "file_id" not in header:  # every other tracker message needs a file_id
            return {"type": P.ERROR, "reason": "file_id missing"}  # refuse
        if mtype in (P.REGISTER, P.HEARTBEAT) and self.registry.is_kicked(ip, header.get("port", -1)):  # banned
            return {"type": P.ERROR, "reason": "disconnected by server"}  # refuse
        if mtype == P.REGISTER:  # a peer joins
            if "port" not in header:  # we must know where it listens
                return {"type": P.ERROR, "reason": "port missing"}  # refuse
            rec = self.registry.upsert_peer(ip, header, is_register=True)  # store it
            log.info("REGISTER   %s:%d file=%s chunks=%d", ip, rec["port"], header["file_id"][:8], rec["chunks_held"])
            return {"type": P.OK}  # accepted
        if mtype == P.HEARTBEAT:  # a peer is alive
            if "port" not in header:  # we must know which peer
                return {"type": P.ERROR, "reason": "port missing"}  # refuse
            self.registry.upsert_peer(ip, header, is_register=False)  # refresh last_seen + progress
            return {"type": P.OK}  # acknowledged
        if mtype == P.GET_PEERS:  # a peer asks who has the file
            exclude = (ip, int(header["port"])) if "port" in header else None  # do not return the asker
            peers = self.registry.get_peers(header["file_id"], exclude=exclude)  # look up
            if not netutil.is_loopback(ip):  # the asker is on ANOTHER computer
                me = netutil.lan_ip()  # this tracker's LAN address
                for p in peers:  # a peer on the tracker's own PC registered as 127.0.0.1 ...
                    if netutil.is_loopback(p["ip"]):  # ... which means nothing to a remote asker
                        p["ip"] = me  # so give out the tracker PC's LAN address instead
            log.info("GET_PEERS  %s file=%s -> %d peers", ip, header["file_id"][:8], len(peers))  # log it
            return {"type": P.PEERS, "peers": peers}  # the list
        return {"type": P.ERROR, "reason": "unknown message type"}  # anything else


def main(argv=None):
    """Start the tracker (TCP + HTTP API)."""
    ap = argparse.ArgumentParser(description="MiniTorrent tracker")  # option parser
    ap.add_argument("--host", default="0.0.0.0")  # interface to listen on
    ap.add_argument("--port", type=int, default=config.TRACKER_PORT)  # TCP port for peers
    ap.add_argument("--api-port", type=int, default=config.API_PORT)  # HTTP port for the dashboard
    ap.add_argument("--db", default="tracker.db", help="SQLite file ('' = no persistence)")  # database path
    ap.add_argument("--no-api", action="store_true", help="run without the HTTP API")  # TCP only
    args = ap.parse_args(argv)  # read sys.argv

    logging.basicConfig(  # log to the console AND to tracker.log
        level=logging.INFO,  # show info and above
        format="%(asctime)s %(levelname)-7s %(message)s",  # time, level, text
        handlers=[logging.StreamHandler(), logging.FileHandler("tracker.log")],  # two outputs
    )
    storage = Storage(args.db) if args.db else None  # SQLite or nothing
    registry = Registry(storage=storage)  # the peer table (restores from SQLite)
    server = TrackerServer(registry, args.host, args.port).start()  # TCP side
    try:  # Ctrl+C stops the tracker
        if args.no_api:  # TCP only mode
            threading.Event().wait()  # sleep forever
        else:  # normal mode
            import uvicorn  # imported here so --no-api works without it
            from tracker.api import create_app  # the FastAPI app factory
            uvicorn.run(create_app(registry), host=args.host, port=args.api_port, log_level="warning")  # blocks
    except KeyboardInterrupt:  # Ctrl+C
        pass  # fall through to cleanup
    finally:  # always
        server.stop()  # close the socket


if __name__ == "__main__":  # only when run as a program
    main()  # go
