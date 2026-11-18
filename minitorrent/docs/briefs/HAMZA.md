# Hamza: Dashboard, setup and report

## Your files
| File | What it is |
|---|---|
| `dashboard/app.py` | the Streamlit live dashboard |
| `run_demo.py`, `run_demo.bat` | one command starts everything |
| `requirements.txt`, `.streamlit/config.toml` | setup |
| `Dockerfile`, `docker-compose.yml` | Docker packaging |
| `README.md` | install and run guide |
| final report and slides | assembled from everyone's notes |

## In simple words
You built the **window** into the system and the **start button**.
The dashboard never talks to peers. Every 2 seconds it asks the tracker's API four questions (`/stats`, `/peers`, `/files`, `/events`) and draws the answers.

## Things to say in the demo
1. Top row: peers online, seeders, downloading, swarm progress, speed, data transferred.
2. Chunk availability strip: one square per chunk, brighter means more peers hold it. Dark blue squares are the rare ones.
3. One card per peer with a progress bar and a chunk map.
4. In a downloader's chunk map, **each square has the colour of the peer that supplied it**. This is the visual proof that chunks come from several peers at once.
5. `@st.fragment(run_every=2)` redraws only the live part, so the page does not flicker.
6. `run_demo.py` starts the tracker, waits for `/health`, then starts the dashboard and the peers as subprocesses.

## Your tasks
1. `python run_demo.py` and `python run_demo.py --scenario failover`. Take screenshots at the start, in the middle, at the kill, and at 100 %.
2. **Test Docker:** `docker compose up --build`, then open http://localhost:8501. The compose file was syntax-checked but not run end to end, so fix anything that comes up on your machine.
3. Collect from the others: Ayaan's Wireshark screenshots, Junaid's CSV and graph, Maaz's pytest screenshot, Arbab's log and SQLite screenshots.
4. Assemble the report: introduction (from the proposal), architecture (from `ARCHITECTURE.md`), one section per member, experiments, testing, conclusion.

## Likely viva questions
- **Where does the dashboard get its data?** Only from the tracker's HTTP API. It is a separate process and could run on another machine.
- **Why HTTP for the dashboard but our own protocol for peers?** The dashboard only needs simple read-only JSON, and HTTP tools already exist. Designing the peer protocol ourselves was the learning goal.
- **How does it refresh?** A Streamlit fragment re-runs every 2 seconds.
- **How does it know which peer supplied a chunk?** Each downloader reports a chunk → supplier map in its heartbeat. The tracker passes it through.
- **Why Docker?** Same environment on every machine. One command, no "works on my laptop".
- **Why is the demo slowed down?** On one laptop 20 MB transfers in under a second. `--upload-delay` simulates a slow link so the audience can watch.
- **What if the tracker is down?** The page shows "TRACKER OFFLINE" and reconnects by itself.
