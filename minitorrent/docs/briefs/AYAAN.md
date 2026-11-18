# Ayaan: Protocol and peer networking

## Your files
| File | What it is |
|---|---|
| `common/protocol.py` | `send_msg`, `recv_msg`, `recv_exact`, message type constants |
| `common/config.py` | every setting (ports, timeouts, chunk size) |
| `peer/network.py` | `PeerServer`, `PeerClient`, `TrackerClient`, `DummyChunkStore` |
| `peer/main.py` | the command line: `--tracker --port --share / --download` |

## In simple words
You built the **language** all programs speak and the **phone lines** between them.
Analogy: TCP is a water pipe. You pour in two letters and the other side just sees water. So before each letter you write its length on the envelope (4 bytes). The reader reads the length first, then reads exactly that many bytes. That is *length-prefixed framing*.

## Things to say in the demo
1. Every message = 4-byte length + JSON header + optional raw bytes.
2. `recv()` can return fewer bytes than asked, so `recv_exact()` loops until all bytes arrive.
3. `PeerServer` listens on a port and gives each connection its own thread.
4. `PeerClient` has a 5 second timeout, so a dead peer cannot freeze the download.
5. `TrackerClient` sends a HEARTBEAT every 5 seconds in a background thread.

## Your task: Wireshark capture
1. Start Wireshark, capture on the **Loopback** adapter (Npcap loopback on Windows).
2. Filter: `tcp.port == 5000 || tcp.port == 6001`
3. Run `python run_demo.py`.
4. Right-click a packet → Follow → TCP Stream. You will see the readable JSON (`"type": "REQUEST_CHUNK"`) followed by raw chunk bytes.
5. Screenshot: the 3-way handshake, one REGISTER, one REQUEST_CHUNK with its CHUNK_DATA. Send them to Hamza.

## Likely viva questions
- **Why do you need framing on TCP?** TCP is a byte stream. It keeps order but not message boundaries. Two sends can arrive as one recv, or one send as many.
- **Why big-endian `>I`?** Network byte order is big-endian by convention. `I` is a 4-byte unsigned int, so a header can be up to 4 GB (we limit it to 1 MB for safety).
- **Why not put the chunk inside the JSON?** JSON cannot hold raw bytes. Base64 would add 33 % size.
- **Why a thread per connection?** `recv` blocks. With one thread, one slow peer would block everyone.
- **Why TCP and not UDP?** We need reliable, ordered delivery. With UDP we would have to rebuild that ourselves.
- **What is `SO_REUSEADDR`?** Lets us restart on the same port immediately instead of waiting for the OS to release it.
- **What does the `ERROR` message do?** A peer asked for a chunk or file we do not have. The client turns it into an exception and the downloader tries another peer.
