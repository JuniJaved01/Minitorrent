"""
dashboard/app.py  --  OWNER: HAMZA
Live MiniTorrent dashboard (Streamlit). It ONLY reads the tracker's HTTP API:
    GET /stats   GET /peers   GET /files   GET /events
and redraws itself every 2 seconds.

    streamlit run dashboard/app.py
"""

import datetime  # clock shown in the header
import html  # escape text before putting it into HTML
import os  # environment variables for settings

import pandas as pd  # the speed chart wants a DataFrame
import requests  # HTTP client for the tracker API
import streamlit as st  # the dashboard framework

API = os.environ.get("MT_API_URL", "http://127.0.0.1:8000")  # where the tracker API lives
REFRESH = float(os.environ.get("MT_REFRESH", "2"))  # seconds between redraws

PEER_COLORS = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"]  # one per peer
UNKNOWN_COLOR = "#8a8982"  # chunks restored from disk (resume) or from a peer that already left
AVAIL_COLORS = ["#2b2b29", "#1d4f8f", "#3987e5", "#9cc6f7"]  # 0, 1, 2, 3+ holders (one hue, brighter = more)

st.set_page_config(page_title="MiniTorrent Live", page_icon="🧲", layout="wide")  # wide page, tab title

CSS = """
<style>
#MainMenu, header, footer {visibility: hidden;}
.block-container {padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1500px;}
.stApp {background: #111110;}
.mt * {box-sizing: border-box;}
.mt {color: #f0efec; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;}
.mt-head {display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 18px;}
.mt-title {font-size: 40px; font-weight: 800; letter-spacing: -0.5px; line-height: 1;}
.mt-sub {font-size: 17px; color: #c3c2b7; margin-top: 6px;}
.mt-pill {font-size: 18px; font-weight: 700; padding: 10px 18px; border-radius: 999px; border: 2px solid;}
.mt-on {color: #f0efec; border-color: #0ca30c; background: #10300f;}
.mt-off {color: #f0efec; border-color: #e66767; background: #3a1414;}
.mt-kpis {display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin-bottom: 20px;}
.mt-kpi {background: #1a1a19; border: 1px solid #33332f; border-radius: 14px; padding: 16px 20px;}
.mt-kpi-label {white-space: nowrap; font-size: 15px; font-weight: 600; color: #c3c2b7; text-transform: uppercase; letter-spacing: 0.6px;}
.mt-kpi-value {font-size: 38px; font-weight: 800; line-height: 1.15; margin-top: 4px; white-space: nowrap;}
.mt-kpi-note {font-size: 15px; color: #c3c2b7;}
.mt-panel {background: #1a1a19; border: 1px solid #33332f; border-radius: 14px; padding: 20px 24px; margin-bottom: 18px;}
.mt-h2 {font-size: 26px; font-weight: 800; margin-bottom: 2px;}
.mt-meta {font-size: 16px; color: #c3c2b7; margin-bottom: 14px;}
.mt-h3 {font-size: 16px; font-weight: 700; color: #c3c2b7; text-transform: uppercase; letter-spacing: 0.6px; margin: 14px 0 8px;}
.mt-grid {display: flex; flex-wrap: wrap; gap: 3px;}
.mt-cell {border-radius: 3px; flex: none;}
.mt-miss {background: #111110; box-shadow: inset 0 0 0 1px #45453f;}
.mt-legend {display: flex; flex-wrap: wrap; gap: 18px; font-size: 15px; color: #c3c2b7; margin-top: 10px; align-items: center;}
.mt-sw {display: inline-block; width: 16px; height: 16px; border-radius: 3px; margin-right: 7px; vertical-align: -2px;}
.mt-peer {border: 1px solid #33332f; border-left-width: 10px; border-radius: 12px; padding: 16px 20px; margin-top: 14px; background: #151514;}
.mt-peer-top {display: flex; flex-wrap: wrap; align-items: center; gap: 14px;}
.mt-addr {font-family: Consolas, 'SF Mono', monospace; font-size: 26px; font-weight: 700;}
.mt-badge {font-size: 15px; font-weight: 800; padding: 5px 12px; border-radius: 8px; border: 2px solid #8a8982; letter-spacing: 0.5px;}
.mt-b-seed {border-color: #0ca30c; background: #10300f;}
.mt-b-down {border-color: #3987e5; background: #12284a;}
.mt-b-late {border-color: #c98500; background: #3a2a05;}
.mt-pct {margin-left: auto; font-size: 40px; font-weight: 800; line-height: 1;}
.mt-bar {height: 22px; background: #2b2b29; border-radius: 11px; overflow: hidden; margin: 12px 0 10px;}
.mt-fill {height: 100%; border-radius: 11px; transition: width 0.6s ease;}
.mt-stats {display: flex; flex-wrap: wrap; gap: 8px 30px; font-size: 18px;}
.mt-stats b {font-weight: 700;}
.mt-stats span {color: #c3c2b7;}
.mt-ev {font-size: 17px; padding: 9px 0; border-bottom: 1px solid #2b2b29; display: flex; gap: 12px;}
.mt-ev-t {font-family: Consolas, monospace; color: #c3c2b7; flex: none;}
.mt-big {font-size: 22px; line-height: 1.6;}
.mt-big code {background: #2b2b29; padding: 3px 8px; border-radius: 6px; font-size: 19px;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)  # inject the styles once


def fetch(path):
    """GET one API endpoint and return the decoded JSON."""
    return requests.get(API + path, timeout=1.5).json()  # short timeout keeps the page responsive


def fmt_bytes(n):
    """Human-readable size, e.g. 20971520 -> '20.0 MB'."""
    for unit in ("B", "KB", "MB", "GB"):  # try each unit in turn
        if n < 1024 or unit == "GB":  # small enough for this unit
            return ("%d %s" if unit == "B" else "%.1f %s") % (n, unit)  # no decimals for bytes
        n /= 1024.0  # go to the next bigger unit


def fmt_rate(bps):
    """Human-readable speed, e.g. '1.2 MB/s'."""
    return fmt_bytes(bps) + "/s"  # same units, per second


def peer_key(p):
    """The text identity of a peer: 'ip:port'."""
    return "%s:%d" % (p["ip"], p["port"])  # same format the downloader uses for chunk sources


def color_of(key):
    """Give every peer a fixed colour for the whole session (colour follows the peer, not its rank)."""
    table = st.session_state.setdefault("colors", {})  # key -> colour, remembered between redraws
    if key not in table:  # first time we see this peer
        table[key] = PEER_COLORS[len(table) % len(PEER_COLORS)]  # next colour in the fixed order
    return table[key]  # always the same colour for the same peer


def cell_size(n):
    """Pick a square size so even big files fit on the screen."""
    return 24 if n <= 120 else 16 if n <= 400 else 10  # fewer chunks = bigger squares


def kpi(label, value, note=""):
    """HTML of one big number tile."""
    return ('<div class="mt-kpi"><div class="mt-kpi-label">%s</div><div class="mt-kpi-value">%s</div>'
            '<div class="mt-kpi-note">%s</div></div>') % (label, value, note)  # label, number, small note


def availability_html(f):
    """HTML of the 'how many peers hold each chunk' strip for one file."""
    size = cell_size(f["num_chunks"])  # square size
    cells = []  # one square per chunk
    for i, holders in enumerate(f["availability"]):  # holders = number of peers with chunk i
        color = AVAIL_COLORS[min(holders, 3)]  # 3 or more share the brightest step
        cells.append('<div class="mt-cell" title="Chunk %d: held by %d peer(s)" '
                     'style="width:%dpx;height:%dpx;background:%s"></div>' % (i, holders, size, size, color))  # square
    legend = "".join('<span><i class="mt-sw" style="background:%s"></i>%s</span>' % (c, t) for c, t in zip(
        AVAIL_COLORS, ["0 peers", "1 peer (rare)", "2 peers", "3+ peers"]))  # the colour key
    return ('<div class="mt-h3">Chunk availability across the swarm</div><div class="mt-grid">%s</div>'
            '<div class="mt-legend">%s</div>') % ("".join(cells), legend)  # title + strip + legend


def peer_html(p, timeout):
    """HTML of one peer card: role, address, progress bar, numbers and its chunk grid."""
    key = peer_key(p)  # 'ip:port'
    mine = color_of(key)  # this peer's identity colour
    n = p["num_chunks"]  # total chunks of the file
    held = p["chunks_held"]  # chunks this peer holds
    pct = (100.0 * held / n) if n else 0.0  # progress in percent
    extra = p.get("extra") or {}  # role, sources... sent by the peer
    role = extra.get("role", "seeder" if held >= n else "downloader")  # fall back to guessing from progress
    if role == "seeder":  # started with the full file
        badge = '<span class="mt-badge mt-b-seed">▲ SEEDER</span>'  # icon + word, never colour alone
    elif held >= n:  # finished downloading
        badge = '<span class="mt-badge mt-b-seed">✓ COMPLETE · NOW SEEDING</span>'  # done
    else:  # still downloading
        badge = '<span class="mt-badge mt-b-down">▼ DOWNLOADING</span>'  # in progress
    if p["seconds_ago"] > timeout / 2:  # heartbeat is getting old: peer may be dead
        badge += ' <span class="mt-badge mt-b-late">⚠ NO HEARTBEAT FOR %ds</span>' % p["seconds_ago"]  # warning
    sources = extra.get("sources", {})  # chunk index (text) -> 'ip:port' it came from
    size = cell_size(n)  # square size
    cells = []  # one square per chunk
    counts = {}  # supplier -> number of chunks (for the text summary)
    for i, bit in enumerate(p["bitmap"][:n]):  # walk the bitmap string
        if bit != "1":  # chunk not here yet
            cells.append('<div class="mt-cell mt-miss" title="Chunk %d: missing" '
                         'style="width:%dpx;height:%dpx"></div>' % (i, size, size))  # hollow square
            continue  # next chunk
        src = sources.get(str(i))  # who supplied it (None for a seeder's own chunks)
        if src is None and role == "seeder":  # the seeder had it from the start
            color, tip = mine, "own file"  # its own colour
        elif src is None:  # downloaded in an earlier run (resume)
            color, tip = UNKNOWN_COLOR, "from disk (resumed)"  # neutral grey
        else:  # downloaded from another peer
            color, tip = st.session_state.get("colors", {}).get(src, UNKNOWN_COLOR), "from " + src  # supplier colour
            counts[src] = counts.get(src, 0) + 1  # count it
        cells.append('<div class="mt-cell" title="Chunk %d: %s" style="width:%dpx;height:%dpx;background:%s">'
                     '</div>' % (i, html.escape(tip), size, size, color))  # filled square
    received = ""  # text summary of suppliers
    if counts:  # this peer downloaded something
        parts = ['<span><i class="mt-sw" style="background:%s"></i>%d from %s</span>' % (
            st.session_state.get("colors", {}).get(s, UNKNOWN_COLOR), c, html.escape(s))
            for s, c in sorted(counts.items())]  # e.g. "34 from 127.0.0.1:6001"
        received = '<div class="mt-legend"><b style="color:#f0efec">Chunks received:</b>%s</div>' % "".join(parts)
    strategy = ("<div><span>Strategy</span> <b>%s</b></div>" % html.escape(extra["strategy"])) if "strategy" in extra else ""
    return (
        '<div class="mt-peer" style="border-left-color:%s">'
        '<div class="mt-peer-top"><span class="mt-addr">%s</span>%s<span class="mt-pct">%.0f%%</span></div>'
        '<div class="mt-bar"><div class="mt-fill" style="width:%.1f%%;background:%s"></div></div>'
        '<div class="mt-stats"><div><span>Chunks</span> <b>%d / %d</b></div>'
        '<div><span>↓ Download</span> <b>%s</b></div><div><span>↑ Upload</span> <b>%s</b></div>'
        '<div><span>Uploaded</span> <b>%s</b></div><div><span>Last heartbeat</span> <b>%.1fs ago</b></div>%s</div>'
        '<div class="mt-h3">Chunk map</div><div class="mt-grid">%s</div>%s</div>'
    ) % (mine, html.escape(key), badge, pct, pct, mine, held, n, fmt_rate(p["down_rate"]),
         fmt_rate(p["up_rate"]), fmt_bytes(p["uploaded"]), p["seconds_ago"], strategy, "".join(cells), received)


def offline_html():
    """What we show when the tracker API cannot be reached."""
    return ('<div class="mt"><div class="mt-head"><div><div class="mt-title">🧲 MiniTorrent</div>'
            '<div class="mt-sub">Live swarm monitor</div></div>'
            '<span class="mt-pill mt-off">✕ TRACKER OFFLINE</span></div>'
            '<div class="mt-panel mt-big">Cannot reach the tracker API at <code>%s</code>.<br>'
            'Start it with <code>python -m tracker.server</code> or run <code>python run_demo.py</code>. '
            'This page reconnects by itself.</div></div>') % html.escape(API)


@st.fragment(run_every=REFRESH)  # Streamlit re-runs ONLY this function every REFRESH seconds
def live():
    try:  # the tracker may be down
        stats, peers, files, events = fetch("/stats"), fetch("/peers"), fetch("/files"), fetch("/events")  # 4 calls
    except (requests.RequestException, ValueError):  # no connection or bad JSON
        st.markdown(offline_html(), unsafe_allow_html=True)  # big clear error panel
        return  # try again at the next refresh

    for p in peers:  # give every peer its colour BEFORE drawing, in a stable order
        color_of(peer_key(p))  # first seen = first colour
    for p in peers:  # peers that already left still deserve a colour if they supplied chunks
        for src in sorted(set(((p.get("extra") or {}).get("sources") or {}).values())):  # every supplier
            color_of(src)  # so a killed peer's chunks stay recognisable
    seeders = sum(f["seeders"] for f in files)  # peers holding a complete file
    leechers = sum(f["leechers"] for f in files)  # peers still downloading
    total = sum(p["num_chunks"] for p in peers)  # chunks all peers should hold in the end
    have = sum(p["chunks_held"] for p in peers)  # chunks they hold now
    swarm_pct = (100.0 * have / total) if total else 0.0  # overall completion
    now = datetime.datetime.now().strftime("%H:%M:%S")  # clock text

    parts = ['<div class="mt"><div class="mt-head"><div><div class="mt-title">🧲 MiniTorrent</div>'
             '<div class="mt-sub">Live swarm monitor · updated %s · refresh every %gs</div></div>'
             '<span class="mt-pill mt-on">● TRACKER ONLINE</span></div>' % (now, REFRESH)]  # header
    parts.append('<div class="mt-kpis">' + "".join([  # the row of big numbers
        kpi("Peers online", stats["peers_online"], "removed after %gs of silence" % stats["peer_timeout"]),
        kpi("Seeders", seeders, "hold the complete file"),
        kpi("Downloading", leechers, "still fetching chunks"),
        kpi("Swarm progress", "%.0f%%" % swarm_pct, "%d of %d chunks" % (have, total)),
        kpi("Download speed", fmt_rate(stats["swarm_down_rate"]), "all peers combined"),
        kpi("Data transferred", fmt_bytes(stats["total_downloaded"]), "peer to peer, not via tracker"),
    ]) + "</div>")

    if not peers:  # tracker is up but nobody registered yet
        parts.append('<div class="mt-panel mt-big">No peers yet. Start a seeder:<br>'
                     '<code>python -m peer.main --port 6001 --share FILE</code></div>')  # hint
    for f in files:  # one panel per shared file
        mine = [p for p in peers if p["file_id"] == f["file_id"]]  # peers of this file
        if not mine:  # file known but nobody online
            continue  # skip it
        parts.append('<div class="mt-panel"><div class="mt-h2">📄 %s</div>'
                     '<div class="mt-meta">%s · %d chunks of 256 KB · file id %s… · %d seeder(s), %d downloading</div>'
                     % (html.escape(f["name"]), fmt_bytes(f["size"]), f["num_chunks"], f["file_id"][:12],
                        f["seeders"], f["leechers"]))  # file title line
        parts.append(availability_html(f))  # rare/common strip
        legend = "".join('<span><i class="mt-sw" style="background:%s"></i>%s</span>' % (
            color_of(peer_key(p)), html.escape(peer_key(p))) for p in mine)  # peer colour key
        parts.append('<div class="mt-h3">Peers · a square is coloured by the peer that supplied the chunk</div>'
                     '<div class="mt-legend">%s<span><i class="mt-sw mt-miss"></i>missing</span></div>' % legend)
        parts.extend(peer_html(p, stats["peer_timeout"]) for p in mine)  # one card per peer
        parts.append("</div>")  # close the file panel
    parts.append("</div>")  # close .mt
    st.markdown("".join(parts), unsafe_allow_html=True)  # draw everything above in one go

    history = st.session_state.setdefault("history", [])  # speed samples kept between redraws
    history.append({"time": now, "Swarm download speed (MB/s)": stats["swarm_down_rate"] / 1048576.0})  # new sample
    del history[:-90]  # keep the last 90 samples (3 minutes)
    left, right = st.columns(2)  # speed chart | activity feed
    with left:  # left column
        st.markdown('<div class="mt"><div class="mt-h2">Swarm download speed</div>'
                    '<div class="mt-meta">MB per second, all peers combined</div></div>', unsafe_allow_html=True)
        st.line_chart(pd.DataFrame(history), x="time", y="Swarm download speed (MB/s)",
                      color="#3987e5", height=280)  # single series, so the title names it
    with right:  # right column
        icons = {"join": "＋ JOINED", "done": "✓ DONE", "timeout": "✕ LOST"}  # icon + word per event kind
        rows = "".join('<div class="mt-ev"><span class="mt-ev-t">%s</span><b>%s</b><span>%s</span></div>' % (
            datetime.datetime.fromtimestamp(e["time"]).strftime("%H:%M:%S"), icons.get(e["kind"], e["kind"]),
            html.escape(e["text"])) for e in events[:9])  # newest 9 events
        st.markdown('<div class="mt"><div class="mt-h2">Tracker activity</div><div class="mt-meta">'
                    'joins, completions and timeouts</div>%s</div>' % (rows or '<div class="mt-ev">Nothing yet</div>'),
                    unsafe_allow_html=True)  # the feed


live()  # draw the dashboard (and keep redrawing it)
