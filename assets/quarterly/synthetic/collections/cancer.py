"""The Cancer collection's synthetic generator (REQ-GEN-349): one table, one CSV
per supply, owed once a year in the August round, drawn with the collections'
severity mix - about a quarter amber, a red with a passing resupply five to
twenty days later, the oldest supply clean - from seeds of its own.

A PROVIDER OF THE SHARED DRIVER (REQ-GEN-246), and nothing else: the slot
loop, bookkeeping, delivery and receipt writing and scenario placement are
generator/driver.py's. Importable without pandas or numpy; each hook imports
what it needs.

SYNTHETIC ONLY: a test dataset made to exercise annual participation, standing
in for no real supply. Postcodes come from generator/names_au.py's WA pool,
every other value from a seeded draw.
"""
from __future__ import annotations

import functools
from datetime import date, datetime, time, timedelta

from generator.collections.base import Job, Plan, Provider

DATASET_ID = "cancer-notifications"
TABLE = "cancer_notifications"
FILE = f"{TABLE}.csv"

#: The seed range Keith settled (2026-11-01): [73000, 74000). Slots draw
#: 73001.., each plus its largest derived offset - the resupply chain's churns
#: and dirty rolls (+900 and up, at most eight attempts).
BASE_SEED = 73_000
_RUN_PLAN_SEED = 73_952
SEED_SPAN = 909
#: About fifteen hundred notifications a supply - a year of a small registry.
N_ROWS = 1_500

COLUMNS = ["notification_id", "diagnosis_date", "notification_date", "primary_site", "stage",
           "sex", "age_group", "postcode", "basis_of_diagnosis"]
SITES = ["Breast", "Colorectal", "Lung", "Prostate", "Melanoma", "Lymphoma", "Other"]
_SITE_WEIGHTS = [0.14, 0.12, 0.10, 0.13, 0.11, 0.05, 0.35]
STAGES = ["I", "II", "III", "IV", "Unknown"]
_STAGE_WEIGHTS = [0.30, 0.25, 0.18, 0.15, 0.12]
AGE_GROUPS = ["0-14", "15-29", "30-44", "45-59", "60-74", "75+"]
_AGE_WEIGHTS = [0.01, 0.03, 0.09, 0.24, 0.38, 0.25]
BASES = ["Histology", "Cytology", "Clinical", "Death certificate only"]
_BASIS_WEIGHTS = [0.85, 0.07, 0.07, 0.01]


@functools.cache
def _postcodes() -> tuple[str, ...]:
    from generator.names_au import SUBURBS

    return tuple(sorted({postcode for _suburb, postcode in SUBURBS}))


def _delay():
    """A resupply's turnaround after the arrival it corrects: five to twenty
    days, sooner more likely."""
    import numpy as np

    days = np.arange(5, 21)
    weights = 0.8 ** (days - 5)
    return days, weights / weights.sum()


class Rows:
    """The resupply chain's view of a supply (generator/resupply.py's
    DatasetProvider): one DataFrame of notifications."""

    def generate(self, run_date: date, seed: int, n_rows: int, id_offset: int):
        import numpy as np
        import pandas as pd

        rng = np.random.default_rng(seed)
        n = N_ROWS + int(rng.integers(-150, 151))
        # The year before the supply: diagnosed, then notified 5 to 90 days on.
        start = run_date - timedelta(days=455)
        diagnosed = np.sort(rng.integers(0, 360, size=n))
        lag = rng.integers(5, 91, size=n)
        return pd.DataFrame({
            "notification_id": [f"CAN{seed:05d}{i:05d}" for i in range(n)],
            "diagnosis_date": [(start + timedelta(days=int(d))).isoformat() for d in diagnosed],
            "notification_date": [(start + timedelta(days=int(d + g))).isoformat()
                                  for d, g in zip(diagnosed, lag)],
            "primary_site": rng.choice(SITES, size=n, p=_SITE_WEIGHTS),
            "stage": rng.choice(STAGES, size=n, p=_STAGE_WEIGHTS),
            "sex": rng.choice(["M", "F", "X"], size=n, p=[0.52, 0.475, 0.005]),
            "age_group": rng.choice(AGE_GROUPS, size=n, p=_AGE_WEIGHTS),
            "postcode": rng.choice(_postcodes(), size=n),
            "basis_of_diagnosis": rng.choice(BASES, size=n, p=_BASIS_WEIGHTS),
        })

    def dirty(self, payload, severity: str, seed: int, previous_row_count=None):
        """Amber trips the warning bands; red trips the failures as well."""
        import numpy as np

        rng = np.random.default_rng(seed)
        df = payload.copy()
        n = len(df)

        def rows(k: int):
            return rng.choice(n, size=k, replace=False)

        df["postcode"] = df["postcode"].astype(object)
        if severity == "amber":
            df.loc[rows(int(n * 0.03)), "postcode"] = None
            df.loc[rows(1), "basis_of_diagnosis"] = "Unknown"
        else:
            df.loc[rows(int(n * 0.08)), "postcode"] = None
            df.loc[rows(int(n * 0.02)), "basis_of_diagnosis"] = "Unknown"
            df.loc[rows(6), "stage"] = "V"
            df.loc[rows(4), "primary_site"] = "Kidney"
            moved = rows(5)
            df.loc[moved, "notification_date"] = [
                (date.fromisoformat(d) - timedelta(days=30)).isoformat()
                for d in df.loc[moved, "diagnosis_date"]]
        return df

    def churn(self, payload, seed: int, run_date: date, id_offset: int):
        """A resupply of the same year: the same notifications, a few of
        them since staged."""
        import numpy as np

        rng = np.random.default_rng(seed)
        df = payload.copy()
        unknown = df.index[df["stage"] == "Unknown"]
        if len(unknown):
            staged = rng.choice(unknown, size=max(1, len(unknown) // 10), replace=False)
            df.loc[staged, "stage"] = "II"
        return df

    def resupply_subset(self, payload, previous_dirty_seed: int, seed: int):
        return payload


def run_plan() -> tuple:
    """Each owed period's drawn severity, oldest first: about a quarter amber,
    one red, the oldest clean. Drawn on every call, never cached - its length
    is the calendar's (post-build-review #282 (7))."""
    import numpy as np

    n = len(generated_periods())
    rng = np.random.default_rng(_RUN_PLAN_SEED)
    n_amber, n_red = max(1, round(n * 0.25)), 1
    rest = [None] * ((n - 1) - n_amber - n_red) + ["amber"] * n_amber + ["red"] * n_red
    rng.shuffle(rest)
    return tuple([None] + rest)


def generated_periods() -> list:
    """Every period the dataset owes - each August round's - up to the anchor."""
    from generator.anchor_date import get_anchor_date
    from asset_model import schedule

    return schedule.periods_for_dataset(DATASET_ID, until=get_anchor_date())


def _plan_injections(periods):
    """Where each Cancer scenario lands, resolved before anything is written
    (REQ-GEN-044 criterion 4)."""
    from generator import scenario_injection

    mine = [i for i in scenario_injection.INJECTIONS if i.dataset_id == DATASET_ID]
    scenario_injection.no_two_scenarios_share_a_period(mine, {DATASET_ID: periods})
    resolved = [(i, scenario_injection.resolve(i, periods)) for i in mine]
    suppressed = {name for _i, placement in resolved for name in placement.suppressed}
    return resolved, {placement.period: (i, placement) for i, placement in resolved}, suppressed


def _injected_chain(rows: Rows, injection, period, seed: int):
    """The arrivals one injected scenario needs, in place of the ordinary
    chain, each after the first churned from the one before."""
    from generator.resupply import Delivery

    out, payload = [], rows.generate(period.round_date, seed, 0, 0)
    for n, extra in enumerate(injection.arrivals):
        if n:
            payload = rows.churn(payload, seed + 900 + n, period.round_date, 0)
        this = rows.dirty(payload, extra.severity, seed + 800 + n) if extra.severity else payload
        out.append(Delivery(received_date=period.round_date + timedelta(days=extra.day_offset),
                            severity=extra.severity, payload=this))
    return out


class Cancer(Provider):
    collection_id = "cancer"
    dataset_id = DATASET_ID
    seed_ranges = ((73_000, 74_000),)
    generating_note = "one table, yearly"
    target_datasets = (DATASET_ID,)
    amber_dataset = DATASET_ID

    def seed_schedule(self) -> list[tuple[str, int, int]]:
        out = [("the run plan", _RUN_PLAN_SEED, _RUN_PLAN_SEED)]
        out += [(f"can_slot_{i:02d}", BASE_SEED + i, BASE_SEED + i + SEED_SPAN)
                for i in range(1, len(generated_periods()) + 1)]
        return out

    def generated_periods(self) -> list:
        return generated_periods()

    def plan(self) -> Plan:
        from generator import targeting

        periods = generated_periods()
        resolved, injected, suppressed = _plan_injections(periods)
        owned = frozenset(i for i, p in enumerate(periods)
                          if p.name in injected or p.name in suppressed)
        severities = targeting.outside_hold(list(run_plan()), [p.date for p in periods],
                                            DATASET_ID, keep_clean=frozenset({0}),
                                            unavailable=owned)
        jobs = [Job(f"can_slot_{i:02d}", BASE_SEED + i, sev, p)
                for i, (sev, p) in enumerate(zip(severities, periods), start=1)]
        return Plan(jobs=jobs, resolved=resolved, injected_by_period=injected,
                    state={"rows": Rows(), "suppressed": suppressed})

    def slot(self, plan: Plan, job: Job) -> list | None:
        from generator.resupply import run_slot_chain

        if job.period.name in plan.state["suppressed"]:
            return None
        rows = plan.state["rows"]
        injected = plan.injected_by_period.get(job.period.name)
        if injected is not None:
            return _injected_chain(rows, injected[0], job.period, job.seed)
        days, weights = _delay()
        return list(run_slot_chain(rows, job.period.round_date, job.seed, id_offset=0, n_rows=0,
                                   first_severity=job.severity, previous_row_count=None,
                                   delay_days=days, delay_weights=weights))

    def entries(self, plan: Plan, job: Job, deliveries: list, run_index_start: int) -> list[dict]:
        return [{"run_id": f"{self.run_prefix}{run_index_start + n:03d}",
                 "run_index": run_index_start + n, "slot_id": job.slot_id,
                 "period": job.period.name, "received_at": None,
                 "dirty_severity": d.severity, "seed": job.seed,
                 "row_counts": {TABLE: int(len(d.payload))}}
                for n, d in enumerate(deliveries, start=1)]

    def received_at(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict) -> str:
        from asset_model import asset_time

        injected = plan.injected_by_period.get(job.period.name)
        if injected is not None:
            extra = injected[0].arrivals[n - 1]
            return asset_time.isoformat(asset_time.wall_clock(delivery_obj.received_date, extra.at))
        # Early morning, the minute drawn from the slot, so no two deliveries
        # share a receipt instant (REQ-GEN-334 criterion 13).
        # ON THE ASSET'S CLOCK (REQ-GEN-349 criterion 2): before the 09:00
        # due time, inside the claim window.
        minute = (job.seed * 41 + n * 13) % 50
        at = (datetime.combine(delivery_obj.received_date, time(6, 0))
              + timedelta(minutes=minute)).strftime("%H:%M")
        return asset_time.isoformat(asset_time.wall_clock(delivery_obj.received_date, at))

    def arrival_files(self, plan: Plan, job: Job, n: int, delivery_obj) -> dict[str, str]:
        """The one Notifications file, before any scenario shape."""
        return {FILE: delivery_obj.payload[COLUMNS].to_csv(index=False)}

    def files(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict, name: str):
        from generator import receipt_instants, scenario_injection
        from asset_model import asset_time

        csvs = self.arrival_files(plan, job, n, delivery_obj)
        first = asset_time.parse_instant(entry["received_at"], entry["run_id"])
        injected = plan.injected_by_period.get(job.period.name)
        if injected is not None:
            return scenario_injection.apply_file_shape(
                injected[0].arrivals[n - 1].file_shape, csvs), first
        return csvs, receipt_instants.instants_for(csvs, first, name)

    def describe(self, entry: dict, delivery_obj) -> str:
        return f"{entry['row_counts'][TABLE]:5d} notifications"


PROVIDER = Cancer()
