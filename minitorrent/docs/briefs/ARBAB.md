# Arbab: Tracker and storage

## Your files
| File | What it is |
|---|---|
| `tracker/registry.py` | the in-memory table of files and peers, with a lock |
| `tracker/server.py` | TCP server, thread per client, reaper thread, logging, `main()` |
| `tracker/storage.py` | SQLite: `files` table and `peers` table |
| `tracker/api.py` | FastAPI: `/peers`, `/files`, `/stats`, `/events`, `/health` |

## In simple words
The tracker is a **phone book**. Peers call it and say "I am at this address and I have this file". Other peers ask "who has this file?". It never touches the file itself.
Peers must say "still here" every 5 seconds (heartbeat). Anyone silent for 15 seconds is removed from the book.

## Things to say in the demo
1. The tracker is the client-server part of the project. File transfer is the peer-to-peer part.
2. A peer's identity is (file_id, IP, port). The IP is the one the tracker *sees* on the socket, so a peer cannot lie about it.
3. The registry is shared by many threads, so every method takes the lock.
4. A reaper thread runs every second and removes peers with an old heartbeat.
5. SQLite keeps the registry on disk, so a tracker restart does not lose the swarm.
6. FastAPI exposes the same registry as JSON for the dashboard.

## Your tasks
**Show the timeout**
1. `python run_demo.py --scenario failover`
2. Watch the dashboard. Peer 6002 is killed, gets a "NO HEARTBEAT" warning, then disappears. "LOST" appears under Tracker activity.
3. `tracker.log` has the `TIMEOUT` line. Screenshot it for Hamza.

**Show persistence**
1. `python -m tracker.server` and start one seeder.
2. Open http://localhost:8000/peers in a browser (also try http://localhost:8000/docs).
3. Stop the tracker with Ctrl+C, start it again. `/peers` still lists the peer.
4. Optional: open `tracker.db` with "DB Browser for SQLite" and show the two tables.

## Likely viva questions
- **Does file data pass through the tracker?** No. Only metadata. That is why it scales.
- **What if the tracker dies?** Running transfers continue because peers talk directly. New peers cannot join until it is back. It is a single point of failure for discovery.
- **Why heartbeats?** TCP does not tell you when a remote program crashed if no data is flowing. A missing heartbeat is our failure detector.
- **Why 15 seconds?** Three missed 5 s heartbeats. One lost message should not remove a healthy peer.
- **Why a lock in the registry?** Many client threads read and write the same dictionaries. Without it two threads could corrupt the data.
- **Why SQLite?** Built into Python, a single file, no server to install.
- **Why `?` placeholders in SQL?** To prevent SQL injection. Values never become part of the SQL text.
- **How are speeds computed?** Bytes reported now minus bytes in the last heartbeat, divided by the time between them.
