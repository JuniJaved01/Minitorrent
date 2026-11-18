"""
ui/__main__.py
Start the MiniTorrent UI:

    python -m ui                         -> http://localhost:8080, pick Client or Server on the title screen
    python -m ui --port 8081             -> a second UI on the same PC (for a second client)
    python -m ui --serve 5000            -> start hosting right away (used by run_demo.py)
    python -m ui --connect 127.0.0.1:5000 --folder ~/MT  -> connect right away

The UI listens on 127.0.0.1 ONLY: nobody else on the network can open it.
The tracker (Server mode) and the peer port (Client mode) DO listen on the network.
"""

import argparse  # command-line options
import logging  # tracker log lines
import threading  # open the browser a moment after start
import webbrowser  # open the page

import uvicorn  # the web server

from ui.app import create_app  # the FastAPI app


def main(argv=None):
    ap = argparse.ArgumentParser(description="MiniTorrent UI")  # options
    ap.add_argument("--port", type=int, default=8080, help="UI port on this computer (default 8080)")  # page port
    ap.add_argument("--serve", type=int, metavar="TRACKER_PORT", help="start Server mode on this port immediately")
    ap.add_argument("--connect", metavar="HOST:PORT", help="start Client mode against this server immediately")
    ap.add_argument("--folder", help="shared folder for --connect")  # client folder
    ap.add_argument("--name", help="device name shown on the server (default: this PC's name)")  # label
    ap.add_argument("--db", default="tracker.db", help="tracker SQLite file in Server mode ('' = memory only)")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")  # headless
    args = ap.parse_args(argv)  # read sys.argv

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")  # console log
    app = create_app(db_path=args.db or None, serve_port=args.serve, connect=args.connect,
                     folder=args.folder, device_name=args.name)  # build the app
    url = "http://localhost:%d" % args.port  # where to look
    print("\n  MiniTorrent UI running at %s  (Ctrl+C to stop)\n" % url)  # tell the user
    if not args.no_browser:  # open it for them
        threading.Timer(1.2, webbrowser.open, args=(url,)).start()  # after the server is up
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")  # blocks until Ctrl+C


if __name__ == "__main__":  # only when run as a program
    main()  # go
