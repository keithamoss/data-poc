"""Arbitrary, supplier-shaped delivery names (REQ-GEN-043 criterion 15).

THE POINT IS THAT THEY FOLLOW NO COMMON PATTERN, and the reason is a
testing argument rather than a modelling one. If we name the drop
ourselves in a shape we control, delivery recognition passes by parsing
a name we wrote, which proves nothing. Leaving the name arbitrary makes
recognition do real work against a boundary it did not choose.

So nothing downstream may derive the receipt time, the period, the
dataset or the ordering from one of these. If a change to this module
can break the pipeline, the pipeline was reading a name it had no
business reading - which is exactly the failure this is built to
expose.

DETERMINISTIC from a seed, like everything else in this generator: a
regeneration with unchanged configuration produces the same names
(REQ-GEN-042), so a re-run overwrites its own history rather than
writing a second one beside it.
"""
from __future__ import annotations

from datetime import date

import numpy as np

# Real shapes real suppliers use, in the deliberate absence of a
# convention. Each takes the slot's own date and a per-delivery RNG, so
# two arrivals filling the same slot get different names - a resupply is
# a separate drop, not a second file in the first one.
_SHAPES = (
    lambda d, rng: f"{rng.choice(['BDM', 'DCP', 'REG', 'EXTRACT'])}_{d:%Y%m%d}",
    lambda d, rng: f"{rng.choice(['upload', 'drop', 'batch', 'send'])}-{rng.integers(1000, 9999)}",
    lambda d, rng: f"{d:%Y-%m}-{rng.choice(['final', 'v2', 'corrected', 'resend'])}",
    lambda d, rng: f"{rng.choice(['quarterly', 'monthly', 'daily'])}_extract_{d:%b%Y}".lower(),
    lambda d, rng: "".join(rng.choice(list("0123456789abcdef"), size=12)),
    lambda d, rng: f"{d:%d%m%Y}_{rng.choice(['AGENCY', 'SRC', 'PROD'])}",
    lambda d, rng: f"Data Extract {d:%d %b %Y}",  # spaces are legal in a path
)


def delivery_name(slot_date: date, seed: int, attempt: int = 1,
                   taken: set[str] | None = None) -> str:
    """One arbitrary delivery name, unique among `taken`.

    `attempt` distinguishes the drops filling one slot without encoding
    anything a reader could rely on - two arrivals for the same slot
    simply draw different shapes.

    UNIQUENESS IS ENFORCED, not hoped for. These shapes genuinely do
    collide: several are coarse enough that two slots on the same date
    produce the same string, which was observed the first time this ran
    (`01022026_SRC` three times in eight draws). A collision would
    write two arrivals into ONE directory, silently merging deliveries
    that never arrived together - the one failure this module must not
    produce, and a corruption of the format's central claim rather than
    a cosmetic clash.

    Disambiguation redraws first and only falls back to a numeric
    suffix, so the names stay supplier-shaped rather than all ending up
    as `name_2`.
    """
    taken = taken if taken is not None else set()
    for extra in range(0, 40):
        rng = np.random.default_rng(seed * 100 + attempt + extra * 7919)
        shape = _SHAPES[int(rng.integers(0, len(_SHAPES)))]
        name = str(shape(slot_date, rng))
        if name not in taken:
            return name
    # Unreachable against any realistic history; a real guarantee beats
    # a probabilistic one when the failure is silent data merging.
    base, n = name, 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"
