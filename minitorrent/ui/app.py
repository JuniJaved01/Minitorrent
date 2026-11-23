"""
ui/app.py
The MiniTorrent desktop UI: a small local web server (FastAPI) + one HTML page (ui/static).

The page has three screens (title, client, server). The browser only ever talks to THIS
program on 127.0.0.1; this program then does the real work:
    * Server mode  -> runs the tracker (TCP, default port 5000) inside this process
    * Client mode  -> runs a ClientNode (peer/node.py) that seeds a folder and downloads files

Start it with:   python -m ui            (then open http://localhost:8080)
"""

import csv  # export of the device/file list
import io  # in-memory CSV
import os  # paths
import string  # drive letters on Windows
import subprocess  # open a folder in Explorer / Finder
import sys  # platform checks
import threading  # lock around the two modes
import time  # timestamps

from fastapi import FastAPI, HTTPException, Request  # web framework
from fastapi.responses import FileResponse, JSONResponse, Response  # replies
from fastapi.staticfiles import StaticFiles  # serves ui/static

from common import config  # default ports
from common import netutil  # PC name, LAN IP
from common import protocol as P  # ProtocolError
from peer.network import TrackerClient  # PING for "Test connection"
from peer.node import ClientNode  # the client engine
from tracker.registry import Registry  # tracker memory
from tracker.server import VERSION, TrackerServer  # tracker TCP side
from tracker.storage import Storage  # SQLite

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    STATIC = os.path.join(sys._MEIPASS, "ui", "static")
else:
    STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "[::1]"}  # the UI is for THIS computer only


class HostedServer:
    """The tracker, running inside the UI process (Server mode)."""

    def __init__(self, port, db_path=None, timeout=None):
        self.storage = Storage(db_path) if db_path else None  # optional SQLite
        self.registry = Registry(storage=self.storage, timeout=timeout)  # peer table
        self.tracker = TrackerServer(self.registry, "0.0.0.0", port).start()  # reachable from the LAN
        self.port = self.tracker.port  # real port
        self.started = time.time()  # uptime
        self.history = []  # network activity samples for the chart

    def stop(self):
        """Stop hosting."""
        self.tracker.stop()  # close the port
        if self.storage is not None:  # close SQLite
            self.storage.close()  # release the file

    def snapshot(self):
        """Everything the server screen shows."""
        devices = self.registry.devices_snapshot()  # devices + their files
        stats = self.registry.stats()  # totals
        files = self.registry.files_snapshot()  # every file with availability
        peers = self.registry.peers_snapshot()  # every peer record (chunk maps)
        live_files = [f for f in files if f["seeders"] + f["leechers"] > 0]  # files someone holds now
        activity = sum(d["up_rate"] for d in devices if d["online"])  # bytes/second moving between peers
        self.history.append({"t": time.time(), "rate": activity})  # sample
        del self.history[:-120]  # last 120 samples
        ip = netutil.lan_ip()  # LAN address of this PC
        return {
            "running": True, "port": self.port, "name": netutil.device_name(), "version": VERSION,
            "lan_ip": ip, "local_url": "127.0.0.1:%d" % self.port,
            "share_url": "%s:%d" % (ip, self.port), "uptime": round(time.time() - self.started),
            "timeout": self.registry.timeout,
            "stats": {"devices_online": sum(1 for d in devices if d["online"]), "devices": len(devices),
                      "files": len(live_files), "activity": activity,
                      "transferred": stats["total_downloaded"]},
            "devices": devices, "files": live_files, "peers": peers,
            "events": self.registry.events_snapshot(30), "history": list(self.history),
        }


class State:
    """What this UI process is doing right now (it can be a server AND a client at the same time)."""

    def __init__(self, db_path):
        self.lock = threading.Lock()  # one mode change at a time
        self.server = None  # HostedServer or None
        self.client = None  # ClientNode or None
        self.db_path = db_path  # tracker database for Server mode
        self.last_client = {}  # remembered connect form (host, port, folder)


def default_folder():
    """A sensible suggestion for the shared folder: ~/Documents/MiniTorrent (or ~/MiniTorrent)."""
    home = os.path.expanduser("~")  # user's home folder
    docs = os.path.join(home, "Documents")  # usual documents folder
    return os.path.join(docs if os.path.isdir(docs) else home, "MiniTorrent")  # suggestion


def open_in_file_manager(path):
    """Show a folder in Explorer / Finder / the Linux file manager."""
    if sys.platform.startswith("win"):  # Windows
        os.startfile(path)  # noqa: opens Explorer
    elif sys.platform == "darwin":  # macOS
        subprocess.Popen(["open", path])  # Finder
    else:  # Linux
        subprocess.Popen(["xdg-open", path])  # default file manager


def create_app(db_path="tracker.db", serve_port=None, connect=None, folder=None, device_name=None):
    """Build the FastAPI app. serve_port / connect+folder start a mode immediately (used by run_demo)."""
    app = FastAPI(title="MiniTorrent UI")  # the application
    state = State(db_path)  # mode holder
    app.state.mt = state  # tests can reach it

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        """Refuse requests whose Host is not this computer (blocks DNS-rebinding tricks)."""
        host = (request.headers.get("host") or "").rsplit(":", 1)[0]  # strip the port
        if host and host not in ALLOWED_HOSTS:  # some other name
            return JSONResponse({"detail": "the MiniTorrent UI only answers on localhost"}, status_code=403)
        return await call_next(request)  # normal request

    def need_client():
        """The running ClientNode, or a 409 error."""
        if state.client is None:  # not connected
            raise HTTPException(409, "not connected to a server")  # explain
        return state.client  # the node

    def need_server():
        """The running HostedServer, or a 409 error."""
        if state.server is None:  # not hosting
            raise HTTPException(409, "server is not running")  # explain
        return state.server  # the tracker

    # ------------------------------------------------------------------ page
    @app.get("/")
    def index():
        return FileResponse(os.path.join(STATIC, "index.html"))  # the single page

    # ------------------------------------------------------------------ general
    @app.get("/api/state")
    def get_state():
        """One call the page makes every second."""
        return {
            "device_name": netutil.device_name(), "lan_ip": netutil.lan_ip(), "os": netutil.os_name(),
            "default_folder": default_folder(), "last_client": state.last_client,
            "default_tracker_port": config.TRACKER_PORT,
            "client": state.client.snapshot() if state.client else None,
            "server": state.server.snapshot() if state.server else None,
        }

    # ------------------------------------------------------------------ server mode
    @app.post("/api/server/start")
    def server_start(body: dict):
        port = int(body.get("port") or config.TRACKER_PORT)  # TCP port to host on
        with state.lock:  # one change at a time
            if state.server is not None:  # already hosting
                return {"ok": True, "port": state.server.port}  # nothing to do
            try:  # the port may be taken
                state.server = HostedServer(port, state.db_path)  # start the tracker
            except OSError as exc:  # address in use
                raise HTTPException(400, "Cannot host on port %d: %s" % (port, exc))  # explain
        return {"ok": True, "port": state.server.port}  # done

    @app.post("/api/server/stop")
    def server_stop():
        with state.lock:  # one change at a time
            if state.server is not None:  # hosting
                state.server.stop()  # close the port
                state.server = None  # forget it
        return {"ok": True}  # done

    @app.post("/api/server/kick")
    def server_kick(body: dict):
        srv = need_server()  # must be hosting
        key = str(body.get("key", ""))  # 'ip:port'
        if ":" not in key:  # malformed
            raise HTTPException(400, "bad device key")  # explain
        srv.registry.kick_device(key)  # disconnect it
        return {"ok": True}  # done

    @app.get("/api/server/export")
    def server_export(fmt: str = "csv"):
        srv = need_server()  # must be hosting
        devices = srv.registry.devices_snapshot()  # current list
        if fmt == "json":  # full detail
            return JSONResponse(devices, headers={"Content-Disposition": "attachment; filename=minitorrent-devices.json"})
        buf = io.StringIO()  # CSV in memory
        w = csv.writer(buf)  # writer
        w.writerow(["device", "ip", "port", "online", "file", "size_bytes", "complete", "seeders", "leechers"])  # header
        for d in devices:  # every device
            for f in d["files"] or [{}]:  # every file (one empty row for devices without files)
                w.writerow([d["name"], d["ip"], d["port"], d["online"], f.get("name", ""), f.get("size", ""),
                            f.get("complete", ""), f.get("seeders", ""), f.get("leechers", "")])  # row
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=minitorrent-devices.csv"})  # file

    # ------------------------------------------------------------------ client mode
    def parse_target(body):
        """(host, port) from the Connect form; accepts '192.168.1.10:5000' in the host box too."""
        host = str(body.get("host", "")).strip()  # typed address
        for prefix in ("minitorrent://", "http://", "https://", "tcp://"):  # people paste URLs
            if host.lower().startswith(prefix):  # remove the scheme
                host = host[len(prefix):]  # rest
        host = host.strip("/")  # trailing slash
        port = body.get("port")  # typed port
        if host.count(":") == 1:  # 'host:port' in one box
            host, typed = host.split(":")  # split
            port = port or typed  # the port box wins if filled
        if not host:  # empty
            raise HTTPException(400, "Enter the server address")  # explain
        try:  # must be a number
            port = int(port or config.TRACKER_PORT)  # default 5000
        except ValueError:  # not a number
            raise HTTPException(400, "The port must be a number")  # explain
        return host, port  # tuple

    @app.post("/api/client/test")
    def client_test(body: dict):
        host, port = parse_target(body)  # where
        started = time.time()  # stopwatch
        try:  # nothing may be there
            pong = TrackerClient((host, port), 0, timeout=3).ping()  # PING
        except (OSError, P.ProtocolError) as exc:  # refused / timeout / not a tracker
            return {"ok": False, "error": "No MiniTorrent server at %s:%d (%s)" % (host, port, exc)}  # explain
        return {"ok": True, "name": pong.get("name"), "version": pong.get("version"),
                "your_ip": pong.get("your_ip"), "ms": round((time.time() - started) * 1000)}  # success

    @app.post("/api/client/connect")
    def client_connect(body: dict):
        host, port = parse_target(body)  # where
        folder = os.path.abspath(os.path.expanduser(str(body.get("folder") or "").strip() or default_folder()))
        if body.get("create") and not os.path.isdir(folder):  # the user agreed to create it
            os.makedirs(folder, exist_ok=True)  # make it
        if not os.path.isdir(folder):  # missing
            raise HTTPException(400, "Folder does not exist: %s" % folder)  # explain
        with state.lock:  # one change at a time
            if state.client is not None:  # already connected somewhere
                state.client.stop()  # disconnect first
                state.client = None  # forget it
            node = ClientNode((host, port), folder, device_name=(body.get("name") or device_name or None))
            try:  # the server may not exist
                node.start()  # PING + start seeding
            except (OSError, P.ProtocolError, ValueError) as exc:  # failed
                node.stop()  # clean up a half-started node
                raise HTTPException(400, "Could not connect to %s:%d: %s" % (host, port, exc))  # explain
            state.client = node  # connected
            state.last_client = {"host": host, "port": port, "folder": folder}  # remember the form
        return {"ok": True}  # done

    @app.post("/api/client/disconnect")
    def client_disconnect():
        with state.lock:  # one change at a time
            if state.client is not None:  # connected
                state.client.stop()  # close everything
                state.client = None  # forget it
        return {"ok": True}  # done

    @app.post("/api/client/folder")
    def client_folder(body: dict):
        node = need_client()  # must be connected
        return client_connect({"host": node.tracker_addr[0], "port": node.tracker_addr[1],
                               "folder": body.get("folder"), "create": body.get("create"),
                               "name": node.device_name})  # reconnect with the new folder

    @app.post("/api/client/download")
    def client_download(body: dict):
        node = need_client()  # must be connected
        try:  # unknown id / already have it
            node.start_download(str(body.get("file_id")))  # start
        except (KeyError, ValueError) as exc:  # explain
            raise HTTPException(400, str(exc).strip("'"))  # message
        return {"ok": True}  # done

    @app.post("/api/client/download/{action}")
    def client_download_action(action: str, body: dict):
        node = need_client()  # must be connected
        fid = str(body.get("file_id"))  # which download
        try:  # unknown id
            if action == "pause":  # stop for now
                node.pause_download(fid)  # pause
            elif action == "resume":  # continue
                node.start_download(fid)  # resumes from the progress file
            elif action == "cancel":  # give up
                node.cancel_download(fid)  # delete partial data
            elif action == "clear":  # tidy the list
                node.clear_finished()  # remove finished rows
            else:  # anything else
                raise HTTPException(404, "unknown action")  # explain
        except KeyError:  # not found
            raise HTTPException(404, "no such download")  # explain
        return {"ok": True}  # done

    @app.post("/api/client/share/{action}")
    def client_share_action(action: str, body: dict):
        node = need_client()  # must be connected
        name = str(body.get("name"))  # which file
        try:  # unknown name
            if action == "pause":  # stop seeding
                node.pause_share(name)  # pause
            elif action == "resume":  # seed again
                node.resume_share(name)  # resume
            elif action == "delete":  # remove from disk (the page asks first)
                node.delete_file(name)  # delete
            else:  # anything else
                raise HTTPException(404, "unknown action")  # explain
        except KeyError:  # not found
            raise HTTPException(404, "no such file")  # explain
        except OSError as exc:  # could not delete
            raise HTTPException(400, str(exc))  # explain
        return {"ok": True}  # done

    @app.post("/api/client/upload")
    async def client_upload(request: Request, name: str):
        """Add a file to the shared folder. The page sends the raw bytes of a chosen file."""
        node = need_client()  # must be connected
        tmp, final = node.upload_paths(name)  # where to write
        try:  # the browser may cancel half-way
            with open(tmp, "wb") as f:  # stream straight to disk (big files never sit in RAM)
                async for block in request.stream():  # body arrives in pieces
                    f.write(block)  # write each piece
        except Exception:  # cancelled / disk full
            if os.path.exists(tmp):  # leftovers
                os.remove(tmp)  # clean up
            raise  # report the error
        return {"ok": True, "name": node.finish_upload(tmp, final)}  # final name

    @app.post("/api/client/open-folder")
    def client_open_folder():
        node = need_client()  # must be connected
        try:  # no desktop / no file manager
            open_in_file_manager(node.folder)  # show it
        except OSError as exc:  # failed
            raise HTTPException(400, "Could not open the folder: %s" % exc)  # explain
        return {"ok": True}  # done

    # ------------------------------------------------------------------ folder picker
    @app.get("/api/fs/list")
    def fs_list(path: str = ""):
        """Folders inside 'path' (browsers cannot hand out real paths, so the page browses through us)."""
        path = os.path.abspath(os.path.expanduser(path or "~"))  # default: home folder
        while not os.path.isdir(path) and os.path.dirname(path) != path:  # typed a folder that does not exist yet
            path = os.path.dirname(path)  # show the nearest parent that exists
        if not os.path.isdir(path):  # typed a bad path
            raise HTTPException(400, "Not a folder: %s" % path)  # explain
        try:  # permission problems
            dirs = sorted((e.name for e in os.scandir(path) if e.is_dir() and not e.name.startswith(".")),
                          key=str.lower)  # visible sub-folders
            files = sum(1 for e in os.scandir(path) if e.is_file())  # file count (for context)
        except OSError as exc:  # no access
            raise HTTPException(400, "Cannot open %s: %s" % (path, exc))  # explain
        parent = os.path.dirname(path)  # one level up
        roots = []  # quick shortcuts
        home = os.path.expanduser("~")  # home
        for label, p in (("Home", home), ("Documents", os.path.join(home, "Documents")),
                         ("Desktop", os.path.join(home, "Desktop")), ("Downloads", os.path.join(home, "Downloads"))):
            if os.path.isdir(p):  # exists on this PC
                roots.append({"label": label, "path": p})  # shortcut
        if sys.platform.startswith("win"):  # drive letters
            roots += [{"label": d + ":", "path": d + ":\\"} for d in string.ascii_uppercase if os.path.exists(d + ":\\")]
        return {"path": path, "parent": parent if parent != path else None, "dirs": dirs,
                "files": files, "roots": roots, "sep": os.sep}  # listing

    @app.post("/api/fs/mkdir")
    def fs_mkdir(body: dict):
        """Create a new folder (for the picker's 'New folder' button)."""
        parent = os.path.abspath(os.path.expanduser(str(body.get("path", ""))))  # where
        name = os.path.basename(str(body.get("name", "")).strip())  # no slashes
        if not name or not os.path.isdir(parent):  # bad input
            raise HTTPException(400, "Bad folder name")  # explain
        target = os.path.join(parent, name)  # full path
        os.makedirs(target, exist_ok=True)  # create
        return {"ok": True, "path": target}  # done

    app.mount("/static", StaticFiles(directory=STATIC), name="static")  # JS, CSS, fonts

    # ------------------------------------------------------------------ optional auto-start
    if serve_port:  # run_demo / scripts: host right away
        state.server = HostedServer(serve_port, db_path)  # start the tracker
    if connect and folder:  # scripts: connect right away
        host, port = P.parse_addr(connect, config.TRACKER_PORT)  # 'host:port'
        os.makedirs(folder, exist_ok=True)  # make sure it exists
        for _ in range(20):  # the tracker may still be starting
            try:  # connect
                state.client = ClientNode((host, port), folder, device_name=device_name).start()  # go
                state.last_client = {"host": host, "port": port, "folder": os.path.abspath(folder)}  # remember
                break  # connected
            except (OSError, P.ProtocolError):  # not yet
                time.sleep(0.5)  # retry
    return app  # uvicorn serves this
