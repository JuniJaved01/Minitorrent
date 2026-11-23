"""
ui/__main__.py
Start the MiniTorrent UI:

    python -m ui                         -> http://localhost:9090, pick Client or Server on the title screen
    python -m ui --port 9091             -> a second UI on the same PC (for a second client)
    python -m ui --serve 5000            -> start hosting right away (used by run_demo.py)
    python -m ui --connect 127.0.0.1:5000 --folder ~/MT  -> connect right away

The UI listens on 127.0.0.1 ONLY: nobody else on the network can open it.
The tracker (Server mode) and the peer port (Client mode) DO listen on the network.
"""

import argparse  # command-line options
import logging  # tracker log lines
import sys  # exit on failure
import threading  # open the browser a moment after start
import webbrowser  # open the page

import uvicorn  # the web server

from ui.app import create_app  # the FastAPI app

# Default port chosen above the ranges that Hyper-V / WSL commonly reserve
DEFAULT_PORT = 9090
MAX_RETRIES = 20  # how many ports to try before giving up


def main(argv=None):
    ap = argparse.ArgumentParser(description="MiniTorrent UI")  # options
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help="UI port on this computer (default %d)" % DEFAULT_PORT)
    ap.add_argument("--serve", type=int, metavar="TRACKER_PORT",
                    help="start Server mode on this port immediately")
    ap.add_argument("--connect", metavar="HOST:PORT",
                    help="start Client mode against this server immediately")
    ap.add_argument("--folder", help="shared folder for --connect")
    ap.add_argument("--name",
                    help="device name shown on the server (default: this PC's name)")
    ap.add_argument("--db", default="tracker.db",
                    help="tracker SQLite file in Server mode ('' = memory only)")
    ap.add_argument("--no-browser", action="store_true",
                    help="do not open the browser")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    app = create_app(db_path=args.db or None, serve_port=args.serve,
                     connect=args.connect, folder=args.folder,
                     device_name=args.name)

    # Try the requested port, then keep incrementing until one works.
    # This catches both "port already in use" AND "port blocked by Windows
    # Hyper-V / WSL reserved ranges" (WinError 10013 / errno 13).
    port = args.port
    for attempt in range(MAX_RETRIES):
        url = "http://localhost:%d" % port
        print("\n  MiniTorrent UI starting on %s ..." % url)
        if not args.no_browser:
            threading.Timer(1.5, webbrowser.open, args=(url,)).start()
        try:
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
            return  # clean shutdown (Ctrl+C) — done
        except SystemExit:
            return  # uvicorn sometimes raises SystemExit on Ctrl+C
        except OSError as exc:
            # errno 10013 = WSAEACCES (Windows permission / reserved port)
            # errno 10048 = WSAEADDRINUSE (port already taken)
            # errno 98    = EADDRINUSE (Linux)
            print("  [!] Port %d failed: %s" % (port, exc))
            port += 1
            print("  [+] Trying port %d instead...\n" % port)

    # If we exhausted all retries
    print("\n  [ERROR] Could not find a free port after %d attempts." % MAX_RETRIES)
    print("  Try specifying one manually:  minitorrent.exe --port 50000\n")
    sys.exit(1)


if __name__ == "__main__":
    main()
