"""When each file of a generated delivery reached our storage
(REQ-GEN-044 criteria 12 to 14; Keith, 2026-10-02).

EVERY FILE GETS ITS OWN RECEIPT INSTANT, because storage gives every
object its own, and since REQ-PIPE-105 a file's instant names its run and
orders the pipeline. A corpus where six files always shared one instant
exercised none of that.

THE MIX IS KEITH'S, and is a design idea rather than just fidelity:
  - about 80% of multi-file deliveries land at PRECISELY ONE instant, as
    if unpacked from one archive - so the model meets the shape a future
    zip or bundle mechanism produces before any archive support exists;
  - the rest TRICKLE IN, every file within 10 minutes of the delivery's
    first, and in a varied order, so a file can arrive before a sibling
    it is checked against (criterion 14).

DETERMINISTIC FROM THE SEED (criterion 13): the same seed and delivery
give the same instants, which is what lets a regenerate be diffed.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

#: The share of multi-file deliveries whose files all land at one instant.
TOGETHER = 0.8

#: The furthest any file of a trickled delivery lands after its first.
WINDOW = timedelta(minutes=10)


def instants_for(filenames, first: datetime, seed_key: str) -> "datetime | dict[str, datetime]":
    """One instant for the whole delivery, or one per file.

    `first` is when the delivery's first file landed - every other file
    lands at it or within WINDOW after it, never before. A one-file
    delivery has nothing to spread and always gets the single instant.
    """
    names = sorted(filenames)
    rng = random.Random(f"receipt-instants:{seed_key}")
    if len(names) < 2 or rng.random() < TOGETHER:
        return first
    # A VARIED ORDER, then strictly increasing offsets inside the window,
    # so which dataset lands first is not always the same one (criterion
    # 14) and no two trickled files share an instant.
    rng.shuffle(names)
    window = int(WINDOW.total_seconds())
    offsets = sorted(rng.sample(range(1, window + 1), len(names) - 1))
    out = {names[0]: first}
    for name, seconds in zip(names[1:], offsets):
        out[name] = first + timedelta(seconds=seconds)
    return out
