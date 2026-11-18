"""
experiments/run_experiment.py  --  OWNER: JUNAID
Experiment: random vs rarest-first chunk selection with 2, 3 and 4 source peers.

SCENARIO (same for both strategies, so the comparison is fair):
    * 1 full seeder that is SLOW   (it holds every chunk)
    * N-1 partial peers that are FAST (each holds a random 60 % of the chunks)
  Chunks that only the slow seeder holds are the RARE chunks.
  Every peer uploads one chunk at a time (a simulated bandwidth limit).

    python -m experiments.run_experiment          -> experiments/results/results.csv
    python -m experiments.plot_results            -> experiments/results/strategy_vs_peers.png
"""

import argparse  # command-line options
import csv  # writing the results table
import os  # paths
import random  # choosing which chunks the partial peers hold
import tempfile  # a throw-away working folder
import time  # the stopwatch

from peer import chunks  # metadata + ChunkStore
from peer.downloader import Downloader  # the engine being measured
from peer.network import PeerClient, TrackerClient  # networking
from tests.helpers import make_file, seeder_store, start_peer, start_tracker  # in-process swarm


def partial_store(meta, src, path, fraction, rng):
    """Build a peer store that holds a random 'fraction' of the chunks."""
    store = chunks.ChunkStore(meta, path)  # empty store
    n = meta["num_chunks"]  # total chunks
    for i in rng.sample(range(n), int(n * fraction)):  # pick the chunks this peer owns
        store.write_chunk(i, chunks.read_chunk(src, i, meta["chunk_size"]))  # copy them in
    return store  # ready to be served


def one_run(src, meta, work, strategy, num_peers, fast, slow, seed):
    """Run ONE download and return the time in seconds."""
    rng = random.Random(seed)  # same seed = same partial peers for both strategies
    _, tracker, tracker_addr = start_tracker()  # fresh tracker for this run
    servers = [start_peer(meta, seeder_store(meta, src), tracker_addr, slow)[0]]  # the slow full seeder
    for k in range(num_peers - 1):  # the fast partial peers
        store = partial_store(meta, src, os.path.join(work, "p%d_%d.bin" % (seed, k)), 0.6, rng)  # 60 %
        servers.append(start_peer(meta, store, tracker_addr, fast, role="downloader")[0])  # serve it
    out = os.path.join(work, "out_%s_%d_%d.bin" % (strategy, num_peers, seed))  # download target
    engine = Downloader(meta, chunks.ChunkStore(meta, out), PeerClient(), TrackerClient(tracker_addr, 1),
                        strategy=strategy, workers=4, max_per_peer=1, refresh_interval=0.5)  # the engine
    started = time.perf_counter()  # start the stopwatch
    ok = engine.run()  # download everything
    seconds = time.perf_counter() - started  # stop the stopwatch
    for s in servers + [tracker]:  # shut the swarm down
        s.stop()  # close sockets
    if not ok:  # a failed run would poison the results
        raise RuntimeError("download failed in experiment")  # stop loudly
    return seconds  # the measurement


def main():
    ap = argparse.ArgumentParser(description="random vs rarest-first experiment")  # options
    ap.add_argument("--chunks", type=int, default=64, help="file size in 256 KB chunks")  # 64 = 16 MB
    ap.add_argument("--trials", type=int, default=3, help="runs per configuration")  # averaged in the plot
    ap.add_argument("--fast", type=float, default=0.03, help="seconds per chunk for fast peers")  # fast delay
    ap.add_argument("--slow", type=float, default=0.09, help="seconds per chunk for the slow seeder")  # slow delay
    ap.add_argument("--out", default=os.path.join("experiments", "results", "results.csv"))  # CSV path
    args = ap.parse_args()  # read sys.argv

    os.makedirs(os.path.dirname(args.out), exist_ok=True)  # make the results folder
    rows = []  # one row per run
    with tempfile.TemporaryDirectory() as work:  # deleted automatically at the end
        src = make_file(os.path.join(work, "src.bin"), args.chunks * 262144)  # the test file
        meta = chunks.create_metadata(src)  # split + hash
        for num_peers in (2, 3, 4):  # number of source peers
            for trial in range(args.trials):  # repeat to average out noise
                for strategy in ("random", "rarest"):  # both strategies on the SAME swarm layout
                    seconds = one_run(src, meta, work, strategy, num_peers, args.fast, args.slow, seed=trial)  # run
                    rows.append([strategy, num_peers, trial + 1, round(seconds, 3)])  # remember
                    print("%-7s peers=%d trial=%d  %.2fs" % (strategy, num_peers, trial + 1, seconds))  # progress
    with open(args.out, "w", newline="") as f:  # newline="" is the csv module's rule
        writer = csv.writer(f)  # CSV writer
        writer.writerow(["strategy", "peers", "trial", "seconds"])  # header row
        writer.writerows(rows)  # the data
    print("saved", args.out)  # where the results are


if __name__ == "__main__":  # only when run as a program
    main()  # go
