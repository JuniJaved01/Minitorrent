"""
peer/main.py  --  OWNER: AYAAN
Command-line entry point of a peer.

    Seed a file      : python -m peer.main --tracker 127.0.0.1:5000 --port 6001 --share movie.mp4
    Download a file  : python -m peer.main --tracker 127.0.0.1:5000 --port 6002 --download movie.mp4.mtorrent
"""

import argparse  # reads the command-line options
import os  # paths
import sys  # exit codes
import time  # sleep while seeding

from common import config  # default tracker address
from common import protocol as P  # parse_addr
from peer import chunks  # Maaz: metadata + ChunkStore
from peer.downloader import Downloader  # Junaid: download engine
from peer.network import PeerClient, PeerServer, TrackerClient  # Ayaan: networking


def build_state(meta, store, server, role, downloader=None):
    """Build the dictionary a peer sends to the tracker in REGISTER and HEARTBEAT."""
    bitmap = store.bitmap()  # list of 0/1
    extra = {"role": role}  # free-form info the tracker passes on to the dashboard
    downloaded = 0  # bytes downloaded (0 for a pure seeder)
    if downloader is not None:  # this peer is (or was) downloading
        downloaded = downloader.downloaded  # bytes fetched so far
        extra["strategy"] = downloader.strategy_name  # rarest / random
        extra["sources"] = {str(i): src for i, src in list(downloader.sources.items())}  # chunk -> supplier
        extra["hash_failures"] = downloader.hash_failures  # rejected chunks
        extra["peer_failures"] = downloader.peer_failures  # timeouts / dead peers
        if store.is_complete():  # finished: this peer now behaves like a seeder
            extra["role"] = "complete"  # dashboard shows it as COMPLETE
    return {  # everything the tracker stores about us
        "file_id": meta["file_id"],  # which file
        "name": meta["name"],  # file name (for the dashboard)
        "size": meta["size"],  # bytes
        "num_chunks": meta["num_chunks"],  # total chunks
        "bitmap": "".join(str(b) for b in bitmap),  # "1101..." compact string
        "chunks_held": sum(bitmap),  # how many chunks we hold
        "uploaded": server.uploaded,  # bytes we uploaded to others
        "downloaded": downloaded,  # bytes we downloaded
        "extra": extra,  # dashboard-only details
    }


def main(argv=None):
    """Parse the arguments and run as seeder or downloader."""
    ap = argparse.ArgumentParser(description="MiniTorrent peer")  # the option parser
    ap.add_argument("--tracker", default="%s:%d" % (config.TRACKER_HOST, config.TRACKER_PORT))  # HOST:PORT
    ap.add_argument("--port", type=int, required=True, help="port this peer listens on")  # our upload port
    mode = ap.add_mutually_exclusive_group(required=True)  # exactly one of share / download
    mode.add_argument("--share", metavar="FILE", help="seed this file")  # seeder mode
    mode.add_argument("--download", metavar="FILE.mtorrent", help="download using this metadata file")  # leecher
    ap.add_argument("--out", help="where to save the download (default downloads/<port>/<name>)")  # output path
    ap.add_argument("--strategy", choices=["rarest", "random"], default="rarest")  # chunk selection
    ap.add_argument("--upload-delay", type=float, default=None, help="seconds of fake delay per uploaded chunk")
    ap.add_argument("--exit-when-done", action="store_true", help="quit after downloading instead of seeding")
    args = ap.parse_args(argv)  # read sys.argv

    tracker_addr = P.parse_addr(args.tracker, config.TRACKER_PORT)  # "host:port" -> tuple
    server = PeerServer(args.port, upload_delay=args.upload_delay).start()  # start uploading side first
    tracker = TrackerClient(tracker_addr, server.port)  # tracker connection helper
    downloader = None  # only set in download mode

    if args.share:  # ---------------- SEEDER ----------------
        meta = chunks.create_metadata(args.share)  # split + hash the file
        mt_path = chunks.save_metadata(meta, args.share + ".mtorrent")  # write FILE.mtorrent next to it
        store = chunks.ChunkStore(meta, args.share, complete=True)  # we hold every chunk
        role = "seeder"  # dashboard label
        print("[peer %d] seeding %s (%d chunks) -> %s" % (server.port, meta["name"], meta["num_chunks"], mt_path))
    else:  # ---------------- DOWNLOADER ----------------
        meta = chunks.load_metadata(args.download)  # read the .mtorrent
        out = args.out or os.path.join("downloads", str(server.port), meta["name"])  # default output path
        store = chunks.ChunkStore(meta, out, complete=False)  # empty store, pre-allocated file
        downloader = Downloader(meta, store, PeerClient(), tracker, strategy=args.strategy,
                                progress_path=out + ".progress")  # engine with resume file
        role = "downloader"  # dashboard label
        print("[peer %d] downloading %s (%d chunks) -> %s" % (server.port, meta["name"], meta["num_chunks"], out))

    server.add_store(meta["file_id"], store)  # even a downloader uploads the chunks it already has

    def state():  # called for REGISTER and for every HEARTBEAT
        return build_state(meta, store, server, role, downloader)  # fresh snapshot each time

    for attempt in range(20):  # the tracker may still be starting, so retry
        try:  # connection may be refused
            if tracker.register(state()):  # REGISTER accepted
                break  # we are in the swarm
        except (OSError, P.ProtocolError):  # tracker not reachable yet
            pass  # retry below
        time.sleep(0.5)  # wait half a second between attempts
    else:  # all 20 attempts failed
        print("[peer %d] could not reach tracker at %s:%d" % ((server.port,) + tracker_addr))  # explain
        return 1  # error exit code
    tracker.start_heartbeat(state)  # HEARTBEAT in the background

    try:  # Ctrl+C ends the peer cleanly
        if downloader is not None:  # download mode
            started = time.time()  # stopwatch
            ok = downloader.run()  # blocks until finished or stalled
            took = time.time() - started  # seconds
            try:  # push the final state immediately so the dashboard shows 100 %
                tracker.heartbeat(state())  # one extra heartbeat
            except (OSError, P.ProtocolError):  # tracker hiccup
                pass  # the regular heartbeat will catch up
            if ok:  # final SHA-256 of the whole file matched
                print("[peer %d] DONE in %.1fs - file hash verified" % (server.port, took))  # success
            else:  # incomplete (stalled) or hash mismatch
                print("[peer %d] FAILED: %d/%d chunks" % ((server.port,) + downloader.progress()))  # report
            if args.exit_when_done or not ok:  # do not keep seeding
                return 0 if ok else 2  # exit code tells scripts what happened
        while True:  # seeding forever
            time.sleep(1)  # the server and heartbeat threads do the work
    except KeyboardInterrupt:  # Ctrl+C
        print("[peer %d] stopping" % server.port)  # goodbye
    finally:  # always clean up
        tracker.stop()  # stop heartbeats
        server.stop()  # close sockets
    return 0  # normal exit


if __name__ == "__main__":  # only when run as a program
    sys.exit(main())  # pass the exit code to the shell
