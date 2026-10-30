"""Linkage Products' synthetic generator (REQ-GEN-334): one linkage delivery a
quarter, linkage_keys.csv, on the quarter's own round, built from each linked
dataset's last generated supply filed to that quarter and received before it.

A PROVIDER OF THE SHARED DRIVER (REQ-GEN-246), and GENERIC: which datasets it
links, by which code and identifier columns, is the linked_datasets declared
beside linkage-keys in contract/data-asset.yaml; whose rows it reads is the
providers of those datasets' collections, through the base module's declared
row interface (generated_supplies) - never data/deliveries. Importable
without pandas or numpy.

WHEN IT ARRIVES (criteria 8 and 12, Keith 2026-10-30 'cap the lag'): on the
round, before its 18:00 due time (PROVISIONAL; Keith 2026-10-30, moved from 14:00
because Emergency Department's files land 15:00 to 17:00) and after the
arrivals it reads. A replay's invented promotion lag for a supply this
product reads ends before this delivery's receipt (promotion.next_receipt),
so an ordinary quarter's supply is promoted when the release is checked.

SYNTHETIC ONLY: every key is a scrambled token from this provider's seed.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, time, timedelta

from generator.collections.base import Job, Plan, Provider

DATASET_ID = "linkage-keys"
TABLE = "linkage_keys"
FILE = f"{TABLE}.csv"
COLUMNS = ["linkage_key", "dataset", "id_1"]

#: Seeds 70001.. a quarter; the key token's secret and the link-rate draws
#: derive from them.
BASE_SEED = 70_000
KEY_SEED = 70_999
#: The ordinary link rate (criterion 7, Keith 2026-10-28): 90 to 96 percent of
#: each linked dataset's rows.
LINK_RATE = (0.90, 0.96)
#: Received on the round between 17:05 and 17:55, after the afternoon's
#: Emergency Department arrivals (15:00 to 17:00) and before the 18:00 due time.
RECEIVED_FROM = time(17, 5)


class CannotGenerate(ValueError):
    """Refused before anything is written (criteria 6, 12 and 13)."""


def linked() -> tuple:
    """(dataset id, code, id columns) for every dataset linkage-keys links."""
    from qa_tools.common import hierarchy

    return hierarchy.dataset(DATASET_ID).linked


def _token(code: str, value: str) -> str:
    """The same source record carries the same key in every quarter."""
    digest = hashlib.sha256(f"{KEY_SEED}:{code}:{value}".encode()).hexdigest()
    return f"LK{digest[:16].upper()}"


class LinkageProducts(Provider):
    collection_id = "linkage-products"
    dataset_id = DATASET_ID
    seed_ranges = ((70_000, 71_000),)
    generating_note = "one linkage release a quarter"

    @property
    def depends_on(self) -> tuple[str, ...]:
        from qa_tools.common import hierarchy

        out = []
        for did, _code, _cols in linked():
            coll = hierarchy.dataset(did).collection_id
            if coll not in out:
                out.append(coll)
        return tuple(out)

    def seed_schedule(self) -> list[tuple[str, int, int]]:
        n = len(self._periods())
        return [("the key token", KEY_SEED, KEY_SEED)] + [
            (f"lp_slot_{i:02d}", BASE_SEED + i, BASE_SEED + i) for i in range(1, n + 1)]

    def _sources(self) -> dict:
        """{dataset id: its generated supplies}, refused naming both where a
        provider this one depends on is absent (criterion 6)."""
        from generator import collections
        from generator.collections import base

        cache = getattr(self, "_cache", None)
        if cache is not None:
            return cache
        out = {}
        for did, _code, _cols in linked():
            try:
                dep = collections.for_dataset(did)
            except collections.NoProviderError as exc:
                raise CannotGenerate(
                    f"{self.collection_id} reads {did}, whose collection has no generator "
                    f"provider ({exc}) - nothing was written") from None
            out[did] = base.generated_supplies(dep, did)
        self._cache = out
        return out

    def _periods(self) -> list:
        """Every quarter any linked dataset has a generated supply filed to,
        whose round has come (criterion 2)."""
        from generator.anchor_date import get_anchor_date
        from qa_tools.common import schedule

        wanted = {s.period for supplies in self._sources().values() for s in supplies}
        return [p for p in schedule.periods_for_dataset(DATASET_ID, until=get_anchor_date())
                if p.name in wanted]

    def generated_periods(self) -> list:
        return self._periods()

    def _received(self, job: Job) -> datetime:
        from qa_tools.common import asset_time

        minute = (job.seed * 37) % 50
        hhmm = (datetime.combine(job.period.round_date, RECEIVED_FROM)
                + timedelta(minutes=minute)).strftime("%H:%M")
        return asset_time.wall_clock(job.period.round_date, hhmm)

    def plan(self) -> Plan:
        self._cache = None
        sources = self._sources()
        jobs = [Job(f"lp_slot_{i:02d}", BASE_SEED + i, None, p)
                for i, p in enumerate(self._periods(), start=1)]
        _refuse_unschedulable(jobs, sources, self._received)
        return Plan(jobs=jobs, state={"sources": sources})

    def slot(self, plan: Plan, job: Job) -> list:
        import numpy as np
        import pandas as pd

        from generator.resupply import Delivery
        from qa_tools.common import asset_time

        at = self._received(job)
        rng = np.random.default_rng(job.seed)
        frames = []
        for did, code, cols in linked():
            # THE LAST SUPPLY FILED TO THE QUARTER AND RECEIVED BEFORE THIS
            # DELIVERY (criterion 5): a release cannot describe a later file.
            before = [s for s in plan.state["sources"][did] if s.period == job.period.name
                      and asset_time.parse_instant(s.received_at, did) < at]
            if not before:
                continue
            ids = before[-1].rows[cols[0]].astype(str).drop_duplicates().tolist()
            rate = rng.uniform(*LINK_RATE)
            keep = sorted(rng.choice(len(ids), size=int(len(ids) * rate), replace=False))
            frames.append(pd.DataFrame({"linkage_key": [_token(code, ids[k]) for k in keep],
                                        "dataset": code, "id_1": [ids[k] for k in keep]}))
        payload = (pd.concat(frames, ignore_index=True) if frames
                   else pd.DataFrame(columns=COLUMNS))
        return [Delivery(received_date=job.period.round_date, severity=None, payload=payload)]

    def entries(self, plan: Plan, job: Job, deliveries: list, run_index_start: int) -> list[dict]:
        return [{"run_id": f"{self.run_prefix}{run_index_start + n:03d}",
                 "run_index": run_index_start + n, "slot_id": job.slot_id,
                 "period": job.period.name, "received_at": None, "dirty_severity": None,
                 "seed": job.seed, "row_counts": {TABLE: int(len(d.payload))}}
                for n, d in enumerate(deliveries, start=1)]

    def received_at(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict) -> str:
        from qa_tools.common import asset_time

        return asset_time.isoformat(self._received(job))

    def files(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict, name: str):
        from qa_tools.common import asset_time

        return ({FILE: delivery_obj.payload[COLUMNS].to_csv(index=False)},
                asset_time.parse_instant(entry["received_at"], entry["run_id"]))

    def describe(self, entry: dict, delivery_obj) -> str:
        return f"{entry['row_counts'][TABLE]:6d} linkage keys"


def _refuse_unschedulable(jobs, sources, received) -> None:
    """Criteria 12 and 13, before anything is written: each quarter's release
    arrives after the same quarter's ordinary first supply of each linked
    dataset received that day, its promotion taking effect before the release
    by the one function the gate uses (promotion.effective_at_for, capped at
    the release); and no release shares a receipt instant with any supply it
    reads."""
    from qa_tools.common import asset_time, promotion

    instants = {}
    for did, supplies in sources.items():
        for s in supplies:
            instants[asset_time.parse_instant(s.received_at, did)] = f"{did} {s.received_at}"
    for job in jobs:
        at = received(job)
        if at in instants:
            raise CannotGenerate(f"the {job.period.name} linkage release ({at.isoformat()}) and "
                                 f"{instants[at]} would share one receipt instant - nothing "
                                 f"was written")
        for did, supplies in sources.items():
            mine = [s for s in supplies if s.period == job.period.name]
            if not mine:
                continue
            first = asset_time.parse_instant(mine[0].received_at, did)
            if asset_time.local_date(first) != job.period.round_date:
                continue        # filed a round earlier, as Child Protection's are
            took = promotion.effective_at_for(first, now=at, seed=did, before=at)
            if first >= at or took >= at:
                raise CannotGenerate(
                    f"the {job.period.name} linkage release ({at.isoformat()}) cannot be "
                    f"received after {did}'s promotion for that quarter takes effect "
                    f"({took.isoformat()}) and within its due time - nothing was written")


PROVIDER = LinkageProducts()
