# Maaz: Chunking, integrity and tests

## Your files
| File | What it is |
|---|---|
| `peer/chunks.py` | `create_metadata`, `read_chunk`, `verify_chunk`, `ChunkStore` |
| `tests/test_chunks.py` | 8 tests for chunking, including the 50 MB test |
| `tests/test_protocol.py` | 6 tests for framing and two peers exchanging data |
| `tests/test_tracker.py` | 7 tests for the tracker and the strategies |
| `tests/test_failures.py` | 4 end-to-end tests: parallel, killed peer, corrupt peer, resume |
| `tests/helpers.py`, `conftest.py`, `tools/make_test_file.py` | helpers |

## In simple words
You cut the file into 256 KB pieces and give each piece a **fingerprint** (SHA-256).
Analogy: a jigsaw puzzle where the box lists the exact fingerprint of every piece. If someone hands you a damaged or fake piece, the fingerprint does not match and you refuse it.
The `.mtorrent` file is that list of fingerprints.

## Things to say in the demo
1. `create_metadata` reads the file 256 KB at a time and hashes each piece.
2. `file_id` is the SHA-256 of all hashes joined, so the same content always gets the same id.
3. `read_chunk` uses `seek(i * chunk_size)` to jump straight to chunk i.
4. `ChunkStore.write_chunk` verifies the hash **before** writing. A bad chunk never reaches the disk.
5. The store has a lock because 4 download threads write while upload threads read.
6. At the end the whole file is hashed once more.

## Your task
```bash
pip install -r requirements.txt
pytest -v
```
All 25 must pass. Screenshot the output for Hamza.
Then open `tests/test_failures.py` and be ready to explain `test_download_survives_killed_peer` and `test_corrupted_chunks_are_rejected_and_refetched`. These two prove the proposal's main promises.

## Likely viva questions
- **Why SHA-256 and not a checksum like CRC?** CRC catches accidental errors only. SHA-256 also stops deliberate tampering, because nobody can craft different data with the same hash.
- **What if the file size is not a multiple of 256 KB?** The last chunk is simply shorter. `chunk_length()` handles it and a test covers it.
- **Why hash each chunk and not only the whole file?** With one hash a single bad byte means re-downloading everything. Per-chunk hashes tell us exactly which chunk to fetch again.
- **Why pre-allocate the file?** Chunks arrive in random order, so we must be able to write chunk 150 before chunk 3.
- **What is the bitmap?** A list of 0/1, one per chunk. 1 means "I hold it". Peers exchange it to know who has what.
- **Who do we trust?** Only the `.mtorrent` file. Peers are never trusted.
- **How does the corrupt-peer test work?** A fake store flips one byte in every chunk it uploads. The test checks that at least one hash failure was counted and the final file is still correct.
