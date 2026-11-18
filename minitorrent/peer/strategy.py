"""
peer/strategy.py  --  OWNER: JUNAID
Chunk selection strategies: WHICH chunk should a worker download next?

Both functions receive:
    candidates   : list of chunk indexes we still need and can get right now
    availability : dict {chunk_index: how many peers hold it}
and return ONE chunk index (or None if there is nothing to pick).
"""

import random  # random choice and random tie-breaking


def random_pick(candidates, availability=None):
    """Baseline strategy: pick any needed chunk at random."""
    if not candidates:  # nothing to choose from
        return None  # tell the worker to wait
    return random.choice(list(candidates))  # every candidate is equally likely


def rarest_first(candidates, availability):
    """BitTorrent-style strategy: pick the chunk that the FEWEST peers hold."""
    if not candidates:  # nothing to choose from
        return None  # tell the worker to wait
    lowest = min(availability.get(c, 0) for c in candidates)  # smallest holder count among candidates
    rarest = [c for c in candidates if availability.get(c, 0) == lowest]  # all chunks tied at that count
    return random.choice(rarest)  # break ties randomly so workers spread out


def count_availability(peer_bitmaps):
    """Count, for every chunk, how many peers hold it. peer_bitmaps = {addr: set_of_chunks}."""
    counts = {}  # chunk index -> number of holders
    for chunks in peer_bitmaps.values():  # look at every peer's chunk set
        for c in chunks:  # every chunk that peer holds
            counts[c] = counts.get(c, 0) + 1  # one more holder for chunk c
    return counts  # e.g. {0: 3, 1: 1, 2: 2}


STRATEGIES = {  # lets main.py choose a strategy by name
    "rarest": rarest_first,  # --strategy rarest
    "random": random_pick,  # --strategy random
}
