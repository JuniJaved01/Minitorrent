MiniTorrent Standalone Executable — macOS (Apple Silicon)
==========================================================

This folder contains the complete, self-contained macOS build of MiniTorrent
for Apple Silicon Macs (M1, M2, M3, M4, M5 and newer).
You do NOT need Python or any other dependencies installed to run it.

How to Run:
1. Double-click run_minitorrent.command
   (macOS may ask you to allow it — see "First Launch" below.)
2. Your web browser will open http://localhost:9090 automatically.
3. Choose Server Mode (Tracker) or Client Mode (Peer) on the screen.

First Launch — macOS Security:
  macOS will block the app the first time because it is not signed.
  To allow it:
    • Right-click (or Control-click) run_minitorrent.command → Open
    • Click "Open" in the dialog
  Or via System Settings:
    • System Settings → Privacy & Security → scroll down
    • You'll see "minitorrent was blocked" — click "Allow Anyway"
    • Run it again.

If port 9090 is blocked on your machine, the app will automatically
try 9091, 9092, etc. until it finds a free port. It will tell you
which port it picked in the Terminal window.

Port usage:
- Web Dashboard: localhost:9090 (or next available)
- Server Tracker: port 5000 (TCP)
- Peer P2P Ports: automatic from 6001 upwards
