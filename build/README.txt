MiniTorrent Standalone Executable
=================================

This folder contains the complete, self-contained Windows build of MiniTorrent.
You do NOT need Python or any other dependencies installed to run it.

How to Run:
1. Simply double-click minitorrent.exe (or run_minitorrent.bat).
2. Your web browser will open http://localhost:9090 automatically.
3. Choose Server Mode (Tracker) or Client Mode (Peer) on the screen.

If port 9090 is blocked on your machine, the app will automatically
try 9091, 9092, etc. until it finds a free port. It will tell you
which port it picked in the console window.

Port usage:
- Web Dashboard: localhost:9090 (or next available)
- Server Tracker: port 5000 (TCP)
- Peer P2P Ports: automatic from 6001 upwards

You can copy minitorrent.exe to any folder, USB drive, or laptop and run it directly.
