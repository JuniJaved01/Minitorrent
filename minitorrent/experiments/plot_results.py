"""
experiments/plot_results.py  --  OWNER: JUNAID
Turn results.csv into a bar chart: average download time per strategy and peer count.

    python -m experiments.plot_results
"""

import csv  # reading the results table
import os  # paths
import sys  # optional CSV path argument

import matplotlib  # plotting library
matplotlib.use("Agg")  # draw to a file, no window needed
import matplotlib.pyplot as plt  # the plotting API

COLORS = {"random": "#eb6834", "rarest": "#2a78d6"}  # one fixed colour per strategy
LABELS = {"random": "Random", "rarest": "Rarest-first"}  # legend text


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("experiments", "results", "results.csv")  # input
    times = {}  # (strategy, peers) -> list of seconds
    with open(path, newline="") as f:  # open the CSV
        for row in csv.DictReader(f):  # every data row as a dict
            times.setdefault((row["strategy"], int(row["peers"])), []).append(float(row["seconds"]))  # collect
    peers = sorted({k[1] for k in times})  # e.g. [2, 3, 4]
    fig, ax = plt.subplots(figsize=(8, 4.5))  # one chart
    width = 0.36  # width of one bar
    for n, strategy in enumerate(("random", "rarest")):  # two bars per group
        means = [sum(times[(strategy, p)]) / len(times[(strategy, p)]) for p in peers]  # average per group
        xs = [i + (n - 0.5) * (width + 0.02) for i in range(len(peers))]  # bar positions side by side
        bars = ax.bar(xs, means, width, color=COLORS[strategy], label=LABELS[strategy])  # draw the bars
        ax.bar_label(bars, fmt="%.2fs", padding=3, fontsize=10)  # value on top of each bar
    ax.set_xticks(range(len(peers)))  # one tick per group
    ax.set_xticklabels(["%d peers" % p for p in peers], fontsize=11)  # group names
    ax.set_ylabel("Average download time (seconds)")  # y axis title
    ax.set_title("Random vs rarest-first: download time by number of peers", loc="left", fontweight="bold")  # title
    ax.spines[["top", "right"]].set_visible(False)  # remove the box lines we do not need
    ax.grid(axis="y", alpha=0.25)  # light horizontal grid
    ax.set_axisbelow(True)  # grid behind the bars
    ax.legend(frameon=False)  # which colour is which strategy
    out = os.path.join(os.path.dirname(path), "strategy_vs_peers.png")  # output image
    fig.tight_layout()  # no clipped labels
    fig.savefig(out, dpi=160)  # write the PNG
    print("saved", out)  # where the graph is


if __name__ == "__main__":  # only when run as a program
    main()  # go
