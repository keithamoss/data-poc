"""What a generator provider declares and implements (REQ-GEN-246).

THE SPLIT. generator/driver.py runs the one slot loop every collection
shares: it plans before the first write, clears what the collection wrote
last time, writes each arrival as a real delivery with its receipt, keeps
the bookkeeping and places the injected scenarios. A provider supplies only
what differs between collections, through the hooks below - how a slot's
arrivals are made, what each manifest entry records, when each arrival was
received and which files it carries.

DECLARATIONS ARE PLAIN ATTRIBUTES, so reading them never imports pandas or
numpy (criterion 7): a provider module defers every tool import to the
method that needs it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


#: The lever sets generator/targeting.py builds targets with, by name - here,
#: in the light module, so `mothman check`'s providers gate can name an
#: unknown one without importing pandas (post-build-review #232).
NULL_RATE = "null-rate"
CLIENT_POSTCODES = "client-postcodes"


class NoProviderError(LookupError):
    """A collection or dataset no generator provider makes - refused by name
    rather than generated with another collection's behaviour."""

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else ""


class SeedOutOfRange(ValueError):
    """A seed a provider derives outside the ranges it declares (criterion 2)."""


@dataclass
class Job:
    """One scheduled slot the driver fills: its id, base seed, the severity
    drawn for it and its period - plus whatever else the provider's own
    slot() needs, which the driver never reads."""

    slot_id: str
    seed: int
    severity: str | None
    period: Any
    extra: dict = field(default_factory=dict)


@dataclass
class Plan:
    """Everything resolved before the first write (REQ-GEN-044 criterion 4):
    the slots in the order they are written, every injected scenario and
    where it landed, and the provider's own planning state."""

    jobs: list[Job]
    #: (injection, placement) for every injected scenario of the collection.
    resolved: list = field(default_factory=list)
    #: period name -> (injection, placement)
    injected_by_period: dict = field(default_factory=dict)
    #: The provider's own planning and running state; the driver never reads it.
    state: dict = field(default_factory=dict)


class Provider:
    """A collection's synthetic generator. Subclasses set the declarations
    and implement the hooks; the driver calls them in a fixed order."""

    #: The collection it generates, as the hierarchy names it.
    collection_id: str = ""
    #: The dataset whose calendar the collection's slots follow, and the key
    #: its bookkeeping is recorded under.
    dataset_id: str = ""
    #: Every seed the provider derives lies in one of these half-open
    #: [low, high) ranges, and no two providers' ranges overlap (criteria 2
    #: and 3).
    seed_ranges: tuple[tuple[int, int], ...] = ()
    #: The TARGET-TRIAL CAPABILITY, declared once (criterion 5): whether
    #: generation tries each injected target against the real tools, and
    #: which datasets' built targets the replay's comparison reads.
    target_trial: bool = False
    target_datasets: tuple[str, ...] = ()
    #: Which lever set generator/targeting.py builds this collection's
    #: targets with ("null-rate" or "client-postcodes"), or None for none.
    target_levers: str | None = None
    #: The dataset an ordinary amber of this collection is measured on.
    amber_dataset: str | None = None
    #: What the TUI says while generating, in brackets after "Generating
    #: synthetic data" - empty for nothing (REQ-TEST-245, today's words).
    generating_note: str = ""

    @property
    def run_prefix(self) -> str:
        from qa_tools import collections

        return collections.by_id(self.collection_id).run_prefix

    # ---- the seed schedule (criterion 2) ----------------------------------

    def seed_schedule(self) -> list[tuple[str, int, int]]:
        """Every seed the provider derives, as (what it is for, first, last)
        - inclusive, the last covering the largest offset added to it."""
        raise NotImplementedError

    def check_seeds(self) -> None:
        """Refuse, naming the provider and the seed, any seed outside the
        declared ranges - before anything is written."""
        for label, first, last in self.seed_schedule():
            if not any(lo <= first and last < hi for lo, hi in self.seed_ranges):
                ranges = ", ".join(f"[{lo}, {hi})" for lo, hi in self.seed_ranges)
                raise SeedOutOfRange(
                    f"{self.collection_id}'s provider derives seed {first}"
                    f"{'' if last == first else f'..{last}'} for {label}, outside the "
                    f"ranges it declares ({ranges})")

    # ---- the period plan ---------------------------------------------------

    def generated_periods(self) -> list:
        """The periods this provider writes, oldest first."""
        raise NotImplementedError

    def plan(self) -> Plan:
        raise NotImplementedError

    # ---- the hooks the driver's slot loop calls, in this order ------------

    def slot(self, plan: Plan, job: Job) -> list | None:
        """The arrivals that fill `job`, or None for a slot written as no
        supply at all (the driver then moves on)."""
        raise NotImplementedError

    def entries(self, plan: Plan, job: Job, deliveries: list, run_index_start: int) -> list[dict]:
        """The bookkeeping entries for those arrivals, received_at unset."""
        raise NotImplementedError

    def received_at(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict) -> str:
        """Arrival `n`'s (1-based) receipt instant, as an ISO string."""
        raise NotImplementedError

    def files(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict,
              name: str) -> tuple[dict, Any]:
        """The delivery's files (filename -> text) and the receipt the
        driver records - one instant, or one per file."""
        raise NotImplementedError

    def describe(self, entry: dict, delivery_obj) -> str:
        """What the progress line says about one arrival's size."""
        return ""

    def after_slot(self, plan: Plan, job: Job, deliveries: list) -> None:
        """Called once a slot's arrivals are written."""

    def extra_placements(self, plan: Plan) -> list:
        """Placements recorded beside the injected ones (Child Protection's
        inheritance scenarios)."""
        return []
