"""
run_demo.py  --  OWNER: HAMZA
One command starts the whole demo: tracker + dashboard + peers.

    python run_demo.py                      -> 1 seeder, 2 downloaders that also share with each other
    python run_demo.py --scenario failover  -> 3 seeders, 1 downloader, one seeder is KILLED mid-download

Press Ctrl+C to stop everything.
"""

import argparse  # command-line options
import os  # paths, environment, random bytes
import shutil  # deleting old downloads
import signal  # turning a 'terminate' signal into a clean shutdown
import subprocess  # starting the other programs
import sys  # sys.executable = the python that runs this script
import time  # waiting
import urllib.request  # checking that the tracker API is up
import webbrowser  # opening the dashboard in the browser

ROOT = os.path.dirname(os.path.abspath(__file__))  # the project folder
DATA = os.path.join(ROOT, "demo_data")  # everything the demo creates goes here
TRACKER_PORT, API_PORT, DASH_PORT = 5000, 8000, 8501  # fixed demo ports
procs = []  # every process we started, so we can stop them all


def start(name, args, env):
    """Start a child process and remember it."""
    print(">> starting %-12s %s" % (name, " ".join(args)))  # show the exact command
    p = subprocess.Popen([sys.executable] + args, cwd=ROOT, env=env)  # same python, project folder
    procs.append((name, p))  # remember it for shutdown
    return p  # caller may kill it later


def wait_for(check, what, seconds=30):
    """Wait until check() is true, or stop the demo with a clear message."""
    deadline = time.time() + seconds  # do not wait forever
    while time.time() < deadline:  # still time left
        if check():  # the thing is ready
            return  # continue the demo
        time.sleep(0.3)  # ask again shortly
    raise SystemExit("gave up waiting for " + what)  # explain what went wrong


def api_up():
    """True when the tracker's HTTP API answers."""
    try:  # connection is refused while the tracker starts
        urllib.request.urlopen("http://127.0.0.1:%d/health" % API_PORT, timeout=1).read()  # GET /health
        return True  # it answered
    except OSError:  # not up yet
        return False  # keep waiting


def make_file(path, megabytes):
    """Create the random demo file if it does not exist with the right size."""
    size = megabytes * 1024 * 1024  # bytes
    if os.path.exists(path) and os.path.getsize(path) == size:  # already there
        return  # reuse it
    with open(path, "wb") as f:  # create it
        for _ in range(megabytes):  # one megabyte at a time
            f.write(os.urandom(1024 * 1024))  # random bytes


def peer(port, tracker, delay, env, share=None, download=None):
    """Start one peer in seed or download mode."""
    args = ["-m", "peer.main", "--tracker", tracker, "--port", str(port), "--upload-delay", str(delay)]  # common part
    args += ["--share", share] if share else ["--download", download]  # mode
    return start("peer %d" % port, args, env)  # launch it


def main():
    ap = argparse.ArgumentParser(description="MiniTorrent one-command demo")  # options
    ap.add_argument("--scenario", choices=["swarm", "failover"], default="swarm")  # which story to show
    ap.add_argument("--size", type=int, default=None, help="demo file size in MB")  # default depends on scenario
    ap.add_argument("--delay", type=float, default=0.3, help="fake seconds per uploaded chunk (so you can watch)")
    ap.add_argument("--kill-after", type=float, default=7.0, help="failover: seconds before a seeder is killed")
    ap.add_argument("--no-dashboard", action="store_true", help="do not start Streamlit")  # headless runs
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")  # for screenshots
    args = ap.parse_args()  # read sys.argv

    size = args.size or (20 if args.scenario == "swarm" else 40)  # 80 or 160 chunks
    os.makedirs(DATA, exist_ok=True)  # demo folder
    shutil.rmtree(os.path.join(DATA, "downloads"), ignore_errors=True)  # always start with empty downloads
    source = os.path.join(DATA, "demo_file.bin")  # the file being shared
    make_file(source, size)  # create it if needed
    mtorrent = source + ".mtorrent"  # the seeder writes this
    if os.path.exists(mtorrent):  # left over from an earlier run
        os.remove(mtorrent)  # the seeder will create a fresh one

    env = dict(os.environ)  # children inherit our environment
    env.setdefault("MT_HEARTBEAT", "1")  # demo: heartbeat every second so the grid moves smoothly
    env.setdefault("MT_PEER_TIMEOUT", "6")  # demo: dead peers disappear after 6 s (normal default is 15)
    env["PYTHONUNBUFFERED"] = "1"  # show child output immediately
    tracker = "127.0.0.1:%d" % TRACKER_PORT  # tracker address for the peers

    signal.signal(signal.SIGTERM, signal.default_int_handler)  # treat 'terminate' like Ctrl+C
    try:  # Ctrl+C lands in 'finally'
        start("tracker", ["-m", "tracker.server", "--port", str(TRACKER_PORT),
                          "--api-port", str(API_PORT), "--db", ""], env)  # no SQLite in the demo = clean start
        wait_for(api_up, "the tracker API")  # do not start peers before the tracker listens
        if not args.no_dashboard:  # start the dashboard
            start("dashboard", ["-m", "streamlit", "run", os.path.join("dashboard", "app.py"),
                                "--server.port", str(DASH_PORT), "--server.headless", "true",
                                "--browser.gatherUsageStats", "false"], env)  # headless = no email prompt
            time.sleep(3)  # give Streamlit a moment
            if not args.no_browser:  # open the page for the user
                webbrowser.open("http://localhost:%d" % DASH_PORT)  # default browser
            print("\n   DASHBOARD:  http://localhost:%d\n" % DASH_PORT)  # in case the browser did not open

        peer(6001, tracker, args.delay, env, share=source)  # the first seeder
        wait_for(lambda: os.path.exists(mtorrent), "the .mtorrent file")  # it writes the metadata
        time.sleep(1)  # let it register

        def out(port):  # where a downloader saves its copy
            return ["--out", os.path.join(DATA, "downloads", str(port), "demo_file.bin")]  # per-peer folder

        if args.scenario == "swarm":  # 1 seeder + 2 downloaders
            for port in (6002, 6003):  # two empty peers
                time.sleep(3)  # stagger them so the dashboard tells a story
                start("peer %d" % port, ["-m", "peer.main", "--tracker", tracker, "--port", str(port),
                                         "--upload-delay", str(args.delay), "--download", mtorrent] + out(port), env)
        else:  # failover: 3 seeders + 1 downloader, one seeder dies
            victim = peer(6002, tracker, args.delay, env, share=source)  # the seeder we will kill
            peer(6003, tracker, args.delay, env, share=source)  # third seeder
            time.sleep(3)  # let them register
            start("peer 6004", ["-m", "peer.main", "--tracker", tracker, "--port", "6004",
                                "--upload-delay", str(args.delay), "--download", mtorrent] + out(6004), env)
            time.sleep(args.kill_after)  # download is running...
            print("\n   >>> KILLING SEEDER 6002 NOW - watch the download continue <<<\n")  # announce it
            victim.kill()  # hard kill, like pulling the cable

        print("\n   Demo is running. Press Ctrl+C to stop everything.\n")  # tell the user
        while True:  # keep the launcher alive
            time.sleep(1)  # children do the work
    except KeyboardInterrupt:  # Ctrl+C
        print("\nstopping...")  # goodbye
    finally:  # always stop every child
        for name, p in procs:  # every process we started
            if p.poll() is None:  # still running
                p.terminate()  # ask it to stop


if __name__ == "__main__":  # only when run as a program
    main()  # go
