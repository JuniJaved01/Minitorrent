# 🧲 MiniTorrent

**A deployable peer-to-peer file sharing system in Python** — CN Lab Project, Group 1

A small, working BitTorrent-style system. A lightweight **tracker** helps peers find each other. Each **peer** splits files into 256 KB chunks, downloads different chunks from several peers **in parallel**, verifies every chunk with **SHA-256**, and uploads the chunks it already has. A **live dashboard** shows the whole swarm.

![Dashboard](docs/dashboard.png)

| | |
|---|---|
| Architecture and protocol | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Who owns which file | [docs/WORK_DISTRIBUTION.md](docs/WORK_DISTRIBUTION.md) |
| Per-member study notes and viva questions | [docs/briefs/](docs/briefs/) |

---

## 1. Quick start (one command)

Requires **Python 3.10+**.

```bash
git clone <your-repo-url> minitorrent
cd minitorrent
pip install -r requirements.txt
python run_demo.py
```

This starts the tracker, the dashboard, one seeder and two downloaders, and opens **http://localhost:8501**.
Press `Ctrl+C` to stop everything. On Windows you can also double-click `run_demo.bat`.

| Demo | Command | What you see |
|---|---|---|
| Swarm | `python run_demo.py` | 1 seeder, 2 empty peers. The grids fill up, and the two downloaders also trade chunks with each other. |
| Fault tolerance | `python run_demo.py --scenario failover` | 3 seeders, 1 downloader. After 7 s one seeder is killed. The download still finishes and the hash is verified. |

Useful options: `--size 50` (file size in MB), `--delay 0.5` (slower, easier to watch), `--kill-after 10`.

> The demo slows uploads down on purpose (`--delay`) because on one laptop a 20 MB file would finish in under a second. It also uses a 1 s heartbeat and a 6 s timeout so you are not waiting in front of the teacher. The real defaults are 5 s and 15 s.

## 2. Running it by hand

Open one terminal per line, all inside the project folder.

```bash
# 1) tracker: TCP port 5000 for peers, HTTP port 8000 for the dashboard
python -m tracker.server --port 5000 --api-port 8000

# 2) dashboard: http://localhost:8501
streamlit run dashboard/app.py

# 3) a seeder: shares a file and writes movie.mp4.mtorrent next to it
python -m peer.main --tracker 127.0.0.1:5000 --port 6001 --share movie.mp4

# 4) a downloader: needs only the small .mtorrent file
python -m peer.main --tracker 127.0.0.1:5000 --port 6002 --download movie.mp4.mtorrent
```

The download is saved to `downloads/<port>/<name>`. After finishing, the peer keeps seeding. If you stop a downloader and start it again with the same command, it **resumes**.

Peer options: `--out PATH`, `--strategy rarest|random`, `--upload-delay SECONDS`, `--exit-when-done`.

## 3. Running on several laptops (same Wi-Fi)

1. One laptop runs the tracker and dashboard. Find its IP with `ipconfig` (Windows) or `ip addr` (Linux), for example `192.168.1.10`.
2. Everyone else starts peers with `--tracker 192.168.1.10:5000`.
3. Copy the `.mtorrent` file to the downloaders (USB, WhatsApp, anything. It is only a few KB).
4. For a dashboard on another laptop: `MT_API_URL=http://192.168.1.10:8000 streamlit run dashboard/app.py`.

## 4. Docker

```bash
docker compose up --build
```

Starts tracker + dashboard + 1 seeder + 2 downloaders. Open http://localhost:8501.

## 5. Ports and firewall fixes

| Port | Protocol | Used by |
|---|---|---|
| 5000 | TCP (our protocol) | peers → tracker |
| 8000 | HTTP | dashboard → tracker API |
| 8501 | HTTP | browser → dashboard |
| 6001, 6002, ... | TCP (our protocol) | peer ↔ peer, one port per peer |

If peers on other laptops cannot connect:

- **Windows:** when the "Windows Defender Firewall" popup appears, tick **Private networks** and click *Allow access*. If you missed it, run in an Administrator terminal:
  `netsh advfirewall firewall add rule name="MiniTorrent" dir=in action=allow protocol=TCP localport=5000,8000,8501,6001-6010`
- **Linux:** `sudo ufw allow 5000,8000,8501,6001:6010/tcp`
- **University / hostel Wi-Fi** often blocks device-to-device traffic ("client isolation"). Use a mobile hotspot instead.
- "Address already in use": another program has the port. Pick another `--port`, or close the old terminal.
- Across the internet you need port forwarding or a VPN such as Tailscale.

## 6. Tests and experiments

```bash
pytest -v                               # 25 tests, about 4 seconds
python -m experiments.run_experiment    # random vs rarest-first with 2, 3, 4 peers -> CSV
python -m experiments.plot_results      # CSV -> experiments/results/strategy_vs_peers.png
```

The tests cover: split and reassemble, a flipped byte, file sizes that are not a multiple of 256 KB, a 50 MB file, message framing, a 3-seeder parallel download, **killing a peer mid-download**, **a peer sending corrupted chunks**, and **resume**.

Sample result (one run on one machine; run it yourself for the report):

![Experiment](experiments/results/strategy_vs_peers.png)

## 7. Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `MT_CHUNK_SIZE` | 262144 | chunk size in bytes |
| `MT_TRACKER_HOST` / `MT_TRACKER_PORT` | 127.0.0.1 / 5000 | tracker address |
| `MT_API_PORT` | 8000 | tracker HTTP API port |
| `MT_HEARTBEAT` | 5 | seconds between heartbeats |
| `MT_PEER_TIMEOUT` | 15 | tracker forgets a silent peer after this many seconds |
| `MT_SOCKET_TIMEOUT` | 5 | network call timeout |
| `MT_WORKERS` | 4 | parallel download threads |
| `MT_MAX_PER_PEER` | 2 | parallel requests to one peer |
| `MT_UPLOAD_DELAY` | 0 | fake seconds per uploaded chunk |
| `MT_API_URL` | http://127.0.0.1:8000 | where the dashboard finds the tracker |
| `MT_REFRESH` | 2 | dashboard refresh in seconds |

## 8. Project structure

```
minitorrent/
  common/       config.py, protocol.py                      Ayaan
  peer/         network.py, main.py                         Ayaan
                chunks.py                                   Maaz
                downloader.py, strategy.py                  Junaid
  tracker/      registry.py, server.py, storage.py, api.py  Arbab
  dashboard/    app.py                                      Hamza
  tests/        test_*.py, helpers.py                       Maaz
  experiments/  run_experiment.py, plot_results.py          Junaid
  tools/        make_test_file.py                           Maaz
  run_demo.py, Dockerfile, docker-compose.yml,
  requirements.txt, README.md                               Hamza
```

## 9. Team

| Member | Roll No. | Module |
|---|---|---|
| Arbab Rahim Ullah Jan | 22I-2726 | Tracker and storage |
| Muhammad Maaz | 22P-9040 | Chunking, integrity and tests |
| Mian Muhammad Ayaan | 22P-9149 | Protocol and peer networking |
| Muhammad Junaid Javed Khan | 22P-9163 | Download engine |
| Muhammad Hamza Khan | 22P-9178 | Dashboard, setup and report |
