"""
Generic resupply-chain orchestration - the delay/retry/chaining behaviour
of "a supply that fails QA gets a resupply some working days later,
which might itself still be broken" (see plans/data-generation.md #5 for the
original scoping, #13 for why this got pulled out of generate_runs.py).

VOCABULARY, since this module is where the two words meet (REQ-GEN-042,
2026-09-23). A SLOT is the logical obligation - one (dataset, period)
pair actually expected, which is what `run_slot_chain` walks. A
DELIVERY is ONE PHYSICAL ARRIVAL of one or more files, which is what it
yields. One slot, many deliveries.

That is a real reversal of what this file used to say: "delivery" here
meant the logical obligation and "attempt" meant the arrival. The
design does not bend to the code (Keith, 2026-09-22) - the generator
adopts the model's vocabulary, because reading this module to learn how
a delivery works should teach the right concept rather than the
opposite one.

Deliberately knows NOTHING about how a dataset's rows are made. It drives
any dataset through DatasetProvider - three operations (generate the
initial attempt, dirty it to a severity, churn it forward into the next
attempt's starting point) that daily_batch.py/dirty.py currently implement
for Birth Registrations (see generate_runs.py's BirthRegistrationsProvider)
and that a future replacement generator (per
docs/synthetic-data-generation-tools-research.md) could implement without
this module changing at all.

Scoped (per Keith's own answers, 2026-09-13) as: build the seam now rather
than waiting for a second implementation; churn lives behind the provider,
not here, since it touches dataset-specific columns and calls the
dataset's own generator to manufacture "rows that should have been in the
original file"; Birth Registrations is still the only provider - this
module is deliberately generic but not yet exercised by a second dataset.

GENERICIZED 2026-09-18 (item 80/CP resupply simulation, plans/qa-
pipeline.md) once a second provider actually arrived: `DatasetProvider`/
`Delivery`/`run_slot_chain` are now generic over a payload type `T`
instead of hardcoding `pd.DataFrame` - Birth Registrations' payload is
still a single DataFrame, but Child Protection's is a whole delivery's
worth of tables at once (`dict[str, pd.DataFrame]`, one entry per real
table). The chain-walking loop itself never inspects payload internals -
it only calls the three provider methods and threads whatever they
return back into the next call - so this was a type-hint-only change,
not a behaviour change; the payload field was renamed from `df` since
it's no longer always a DataFrame (every call site updated alongside).
`delay_days`/`delay_weights` also became real parameters (still
defaulting to the exact BDM curve below, so BDM's own call site needed
no changes) rather than hardcoded module constants, so a second provider
with a genuinely different real-world turnaround (CP's slower full-
collection re-extract) can supply its own curve without forking this
module - see generate_cp_runs.py's own `_CP_DELAY_DAYS`/
`_CP_DELAY_WEIGHTS` for that curve and Keith's own calibration call
behind it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Generic, Iterator, Optional, Protocol, TypeVar

import numpy as np

MAX_ATTEMPTS = 8  # a hard ceiling so a pathological chain can't run forever
STILL_RED_PROB = 0.45  # per-attempt chance a resupply is ALSO red - a chain
# needing 5+ attempts to resolve happens ~4% of the time a delivery goes
# red at all (0.45**4), matching Keith's own framing: "sometimes, in a
# really bad scenario" - most resolve within 1-2 resupplies.
#
# Lowered from 0.60 on 2026-09-21, with Keith, for two reasons. The
# committed history was being trimmed toward ~145 runs, and chain length
# is the second lever on that after RED_SHARE. And at 0.60 the real
# generated history contained a chain that ran to depth 7 - a supplier
# failing seven times running is a stretch, and it was the tail this
# distribution was always least confident about.

# Delay (in working days) until the next attempt arrives: skewed toward
# fast, geometrically decaying so days 1-3 carry ~79% of the probability
# mass and the remaining ~21% tails off out to day 10 - "most suppliers
# land either the next day or within three days, with a longish tail
# going out to around 10 working days" (Keith's own calibration). Birth
# Registrations' own curve - the default every call site gets unless it
# passes its own (see generate_cp_runs.py for the one dataset that does).
_DELAY_DAYS = np.arange(1, 11)
_DELAY_WEIGHTS = 0.6 ** (_DELAY_DAYS - 1)
_DELAY_WEIGHTS = _DELAY_WEIGHTS / _DELAY_WEIGHTS.sum()

T = TypeVar("T")  # a delivery's own payload shape - one DataFrame (BDM) or
# a dict of them, one per real table (CP) - see this module's own
# docstring for why this became generic.


class DatasetProvider(Protocol[T]):
    """What resupply orchestration needs from a dataset - nothing else.
    A future replacement for daily_batch.py/dirty.py only needs to
    implement this to plug into the exact same chain logic."""

    def generate(self, run_date: date, seed: int, n_rows: int, id_offset: int) -> T:
        """This delivery's first-attempt payload."""
        ...

    def dirty(self, payload: T, severity: str, seed: int,
              previous_row_count: Optional[int]) -> T:
        """Apply this dataset's failure-injection presets at the given severity."""
        ...

    def churn(self, payload: T, seed: int, run_date: date, id_offset: int) -> T:
        """Small, dataset-specific add/modify/remove drift between one
        attempt and the next - the source system hasn't been frozen while
        we waited for a resupply."""
        ...


def _add_business_days(start: date, n: int) -> date:
    """start + n working days (Mon-Fri) - real supplier turnaround is
    quoted in working days, not calendar days. No public-holiday calendar
    is modelled - a known, documented simplification, not an oversight."""
    d = start
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:  # Mon=0 .. Fri=4
            added += 1
    return d


@dataclass
class Delivery(Generic[T]):
    """ONE PHYSICAL ARRIVAL of one or more files (REQ-GEN-042).

    That is the only thing the word "delivery" means in this repo now.
    It used to mean the logical obligation - the thing a supplier owes
    for a period, across however many attempts it takes - which is a
    SLOT. One slot, many deliveries.

    Note what this does NOT carry: no attempt_number, no is_resupply.
    They were not renamed, they were RETIRED. A resupply is an arrival
    landing in a slot that already has one - observed from the record,
    never recorded as a flag by the thing that produced it. Keeping a
    slot_-prefixed version of either would have preserved exactly the
    bookkeeping this model stops trusting.
    """

    received_date: date
    severity: Optional[str]  # this arrival's own outcome: None | "amber" | "red"
    payload: T


def run_slot_chain(provider: DatasetProvider[T], slot_date: date, seed: int,
                        id_offset: int, n_rows: int, first_severity: Optional[str],
                        previous_row_count: Optional[int],
                        delay_days: np.ndarray = _DELAY_DAYS,
                    delay_weights: np.ndarray = _DELAY_WEIGHTS) -> Iterator[Delivery[T]]:
    """Walks ONE SLOT through its deliveries, yielding each arrival in
    order. Stops as soon as one isn't red, or after MAX_ATTEMPTS.

    A SLOT is the logical obligation - one (dataset, period) pair
    actually expected. This walks the arrivals that fill it. The caller
    owns everything about identity (run_id, manifest/file writing); this
    only knows when each one landed. `delay_days`/`delay_weights`
    default to Birth Registrations' own curve above; a provider whose
    real-world turnaround differs (see generate_cp_runs.py) passes its
    own.

    Tracks two lineages, not one (real bug found and fixed 2026-09-15 -
    see plans/qa-pipeline.md #31): `clean_payload` is churned forward
    every attempt and NEVER has dirty() applied to it directly; each
    attempt's own yielded `payload` is a fresh `dirty(clean_payload, ...)`
    call when that attempt rolls red, or `clean_payload` itself when it
    resolves. Previously the payload was reused and mutated in place
    across the whole loop, so a resolved attempt silently inherited
    whatever dirty() had already baked into a prior red attempt, and a
    still-red attempt accumulated dirt on top of dirt rather than getting
    one fresh roll at that severity - confirmed via real output (two
    "clean" resupply attempts with ~78-89% facility nulls and invalid sex
    codes, matching RED-severity injection, not a clean run). Keeping
    `clean_payload` separate fixes both: a resolved attempt is genuinely
    clean, and every red attempt (first or Nth in a row) gets one fresh
    dirty() roll against the current (churned-forward, never-dirtied)
    lineage - still not "a fresh random draw" (churn() still evolves the
    same underlying rows attempt to attempt, per plans/data-generation.md #5's own
    design intent), just never carrying forward another attempt's
    injected defects."""
    clean_payload = provider.generate(slot_date, seed, n_rows, id_offset)
    payload = (provider.dirty(clean_payload, first_severity, seed + 500, previous_row_count)
               if first_severity else clean_payload)

    # An internal counter, not an emitted field. The chain has to know
    # how many arrivals it has produced to stop at MAX_ATTEMPTS and to
    # vary its own RNG streams - what criterion 4 retires is RECORDING
    # that number as an authority on the record.
    arrival_count = 1
    received_date = slot_date
    severity = first_severity

    while True:
        yield Delivery(received_date, severity, payload)

        if severity != "red":
            return  # resolved (or was never red to begin with)
        if arrival_count >= MAX_ATTEMPTS:
            return  # giving up - hit the hard ceiling

        resupply_rng = np.random.default_rng(seed + 700 + arrival_count)
        chosen_delay_days = int(resupply_rng.choice(delay_days, p=delay_weights))
        received_date = _add_business_days(received_date, chosen_delay_days)
        arrival_count += 1

        clean_payload = provider.churn(clean_payload, seed + 800 + arrival_count, slot_date,
                                        id_offset + 50_000 + arrival_count * 100)
        if resupply_rng.random() < STILL_RED_PROB:
            payload = provider.dirty(clean_payload, "red", seed + 900 + arrival_count, previous_row_count)
            severity = "red"
        else:
            payload = clean_payload
            severity = None
