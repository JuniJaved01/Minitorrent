# Junaid: Download engine

## Your files
| File | What it is |
|---|---|
| `peer/downloader.py` | the `Downloader` class: workers, lock, retries, resume |
| `peer/strategy.py` | `random_pick`, `rarest_first`, `count_availability` |
| `experiments/run_experiment.py` | random vs rarest-first with 2, 3, 4 peers → CSV |
| `experiments/plot_results.py` | CSV → bar chart |

## In simple words
You are the **manager of 4 delivery boys** (worker threads). There is one whiteboard (shared state) with a single marker (the lock). A boy takes the marker, writes "I am getting chunk 12 from peer A", puts the marker back, and goes. Nobody else will take chunk 12. If peer A's shop is closed, he comes back, erases his line, writes "avoid A for 10 seconds", and someone gets chunk 12 from another peer.

## Things to say in the demo
1. Ask the tracker for peers, then ask each peer for its bitmap.
2. Four worker threads. Each one: pick chunk → pick peer → fetch → verify → store.
3. One `threading.Lock` protects `needed`, `in_progress`, `load` and `banned`. The network call happens **outside** the lock, so downloads really run in parallel.
4. Rarest-first: count how many peers hold each chunk, pick the lowest.
5. The least busy peer that has the chunk is chosen, so load is spread.
6. Timeout or bad hash → chunk goes back, peer is banned for 10 s.
7. Resume: a `.progress` file is saved after every chunk. On restart each listed chunk is re-hashed from disk.

## Your tasks
1. Create the GitHub repo, push the code, add the other four.
2. Run the experiment and give the two result files to Hamza:
```bash
python -m experiments.run_experiment
python -m experiments.plot_results
```
3. Show resume: start a download, press Ctrl+C halfway, run the same command again. It continues instead of starting over.

## The experiment, explained
- One **slow** seeder holds everything. The other peers are **fast** but each holds only 60 % of the chunks.
- Chunks only the slow seeder has are the rare ones.
- **Random** wastes the slow seeder's time on chunks the fast peers could have served. The rare chunks pile up at the end and are fetched one by one.
- **Rarest-first** sends the slow seeder straight to the rare chunks while the fast peers handle the rest.
- Sample run: 4 peers, random ≈ 0.96 s vs rarest ≈ 0.67 s. More peers also means a faster download for both.

## Likely viva questions
- **What is a race condition here?** Two workers both see chunk 12 as needed and both download it. The lock plus `in_progress` prevents it.
- **Why not hold the lock while downloading?** Then only one worker could download at a time and parallelism would be gone.
- **Why rarest-first?** Rare chunks are most at risk of disappearing if a peer leaves, and their holders are the bottleneck.
- **What if every peer dies?** After 30 s with no progress the download stops. Progress is saved, so it can resume later.
- **Why ban instead of removing a peer forever?** Failures are often temporary. After 10 s it gets another chance.
- **Why re-hash chunks on resume?** The progress file could be wrong or the disk file damaged. We trust only hashes.
- **Why is the progress file written to `.tmp` first?** `os.replace` is atomic, so a crash never leaves a half-written file.
- **Why threads when Python has the GIL?** The work is network I/O. Threads release the GIL while waiting on sockets.
