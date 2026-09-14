"""
Generic resupply-chain orchestration - the delay/retry/chaining behaviour
of "a delivery that fails QA gets a resupply some working days later,
which might itself still be broken" (see plans/wider.md #12 for the
original scoping, #13 for why this got pulled out of generate_runs.py).

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
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterator, Optional, Protocol

import numpy as np
import pandas as pd

MAX_ATTEMPTS = 8  # a hard ceiling so a pathological chain can't run forever
STILL_RED_PROB = 0.60  # per-attempt chance a resupply is ALSO red - a chain
# needing 5+ attempts to resolve happens ~13% of the time a delivery goes
# red at all (0.6**4), matching Keith's own framing: "sometimes, in a
# really bad scenario" - most resolve within 1-2 resupplies.

# Delay (in working days) until the next attempt arrives: skewed toward
# fast, geometrically decaying so days 1-3 carry ~79% of the probability
# mass and the remaining ~21% tails off out to day 10 - "most suppliers
# land either the next day or within three days, with a longish tail
# going out to around 10 working days" (Keith's own calibration).
_DELAY_DAYS = np.arange(1, 11)
_DELAY_WEIGHTS = 0.6 ** (_DELAY_DAYS - 1)
_DELAY_WEIGHTS = _DELAY_WEIGHTS / _DELAY_WEIGHTS.sum()


class DatasetProvider(Protocol):
    """What resupply orchestration needs from a dataset - nothing else.
    A future replacement for daily_batch.py/dirty.py only needs to
    implement this to plug into the exact same chain logic."""

    def generate(self, run_date: date, seed: int, n_rows: int, id_offset: int) -> pd.DataFrame:
        """This delivery's first-attempt rows."""
        ...

    def dirty(self, df: pd.DataFrame, severity: str, seed: int,
              previous_row_count: Optional[int]) -> pd.DataFrame:
        """Apply this dataset's failure-injection presets at the given severity."""
        ...

    def churn(self, df: pd.DataFrame, seed: int, run_date: date, id_offset: int) -> pd.DataFrame:
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
class Attempt:
    attempt_number: int
    arrived_date: date
    is_resupply: bool
    severity: Optional[str]  # this attempt's own outcome: None | "amber" | "red"
    df: pd.DataFrame


def run_delivery_chain(provider: DatasetProvider, delivery_date: date, seed: int,
                        id_offset: int, n_rows: int, first_severity: Optional[str],
                        previous_row_count: Optional[int]) -> Iterator[Attempt]:
    """Walks one delivery through its full attempt chain, yielding each
    attempt in order. Stops as soon as an attempt isn't red, or after
    MAX_ATTEMPTS. The caller owns everything about *identity* (run_id,
    delivery_id, supersedes_run_id, manifest/file writing) - this only
    knows attempt numbers and dates."""
    df = provider.generate(delivery_date, seed, n_rows, id_offset)
    if first_severity:
        df = provider.dirty(df, first_severity, seed + 500, previous_row_count)

    attempt_number = 1
    arrived_date = delivery_date
    severity = first_severity

    while True:
        yield Attempt(attempt_number, arrived_date, attempt_number > 1, severity, df)

        if severity != "red":
            return  # resolved (or was never red to begin with)
        if attempt_number >= MAX_ATTEMPTS:
            return  # giving up - hit the hard ceiling

        resupply_rng = np.random.default_rng(seed + 700 + attempt_number)
        delay_days = int(resupply_rng.choice(_DELAY_DAYS, p=_DELAY_WEIGHTS))
        arrived_date = _add_business_days(arrived_date, delay_days)
        attempt_number += 1

        df = provider.churn(df, seed + 800 + attempt_number, delivery_date,
                             id_offset + 50_000 + attempt_number * 100)
        if resupply_rng.random() < STILL_RED_PROB:
            df = provider.dirty(df, "red", seed + 900 + attempt_number, previous_row_count)
            severity = "red"
        else:
            severity = None
