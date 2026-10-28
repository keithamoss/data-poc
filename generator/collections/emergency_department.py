"""Emergency Department's synthetic generator (REQ-GEN-232): one table, one
CSV per quarterly supply, drawn with Child Protection's severity mix - about a
quarter amber, two reds with resupply chains, the oldest supply clean - from
seeds of its own.

A PROVIDER OF THE SHARED DRIVER (REQ-GEN-246), and nothing else: the slot
loop, bookkeeping, delivery and receipt writing and scenario placement are
generator/driver.py's. Importable without pandas or numpy; each hook imports
what it needs.

SYNTHETIC ONLY: postcodes come from generator/names_au.py's WA pool, every
other value from a seeded draw. No real record, list or extract.
"""
from __future__ import annotations

import functools
from datetime import date, datetime, time, timedelta

from generator.collections.base import Job, Plan, Provider

DATASET_ID = "ed-presentations"
TABLE = "ed_presentations"
FILE = f"{TABLE}.csv"

#: Seeds 60001.. for the slots, each plus its largest derived offset.
BASE_SEED = 60_000
_RUN_PLAN_SEED = 69_000
#: The largest offset a slot's derivations add to its seed: the resupply
#: chain's dirty rolls (+500 and up) and churns (+900 and up).
SEED_SPAN = 1_999
#: About two thousand presentations a supply (the NFR's "a few thousand",
#: kept small so a quarter costs seconds, not tens of them).
N_ROWS = 2_000

COLUMNS = ["presentation_id", "arrival_datetime", "triage_category", "age_group", "sex",
           "postcode", "departure_status", "length_of_stay_minutes"]
AGE_GROUPS = ["0-4", "5-14", "15-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75-84", "85+"]
_AGE_WEIGHTS = [0.08, 0.09, 0.14, 0.14, 0.12, 0.11, 0.10, 0.09, 0.08, 0.05]
_TRIAGE_WEIGHTS = [0.01, 0.10, 0.33, 0.43, 0.13]
DEPARTURES = ["Admitted", "Discharged", "Transferred", "Did not wait", "Left at own risk",
              "Died in department"]
_DEPARTURE_WEIGHTS = [0.30, 0.58, 0.04, 0.05, 0.025, 0.005]


@functools.cache
def _postcodes() -> tuple[str, ...]:
    from generator.names_au import SUBURBS

    return tuple(sorted({postcode for _suburb, postcode in SUBURBS}))


def _delay():
    """A resupply's turnaround after the arrival it corrects, as Child
    Protection's: five to twenty days, sooner more likely."""
    import numpy as np

    days = np.arange(5, 21)
    weights = 0.8 ** (days - 5)
    return days, weights / weights.sum()


class Rows:
    """The resupply chain's view of a supply (generator/resupply.py's
    DatasetProvider): one DataFrame of presentations."""

    def generate(self, run_date: date, seed: int, n_rows: int, id_offset: int):
        import numpy as np
        import pandas as pd

        rng = np.random.default_rng(seed)
        n = N_ROWS + int(rng.integers(-150, 151))
        start = datetime.combine(run_date - timedelta(days=92), time())
        minutes = np.sort(rng.integers(0, 91 * 24 * 60, size=n))
        return pd.DataFrame({
            "presentation_id": [f"ED{seed:05d}{i:05d}" for i in range(n)],
            "arrival_datetime": [(start + timedelta(minutes=int(m))).isoformat(sep=" ")
                                 for m in minutes],
            "triage_category": rng.choice([1, 2, 3, 4, 5], size=n, p=_TRIAGE_WEIGHTS),
            "age_group": rng.choice(AGE_GROUPS, size=n, p=_AGE_WEIGHTS),
            "sex": rng.choice(["M", "F", "X"], size=n, p=[0.49, 0.50, 0.01]),
            "postcode": rng.choice(_postcodes(), size=n),
            "departure_status": rng.choice(DEPARTURES, size=n, p=_DEPARTURE_WEIGHTS),
            "length_of_stay_minutes": rng.gamma(2.0, 120.0, size=n).astype(int).clip(5, 2880),
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
            df.loc[rows(2), "length_of_stay_minutes"] = -int(rng.integers(5, 60))
            df.loc[rows(1), "departure_status"] = "Unknown"
        else:
            df.loc[rows(int(n * 0.08)), "postcode"] = None
            df.loc[rows(12), "length_of_stay_minutes"] = 9_999
            df.loc[rows(int(n * 0.02)), "departure_status"] = "Unknown"
            df.loc[rows(6), "triage_category"] = 0
            df.loc[rows(4), "sex"] = "U"
        return df

    def churn(self, payload, seed: int, run_date: date, id_offset: int):
        """A resupply of the same quarter: the same presentations, a few of
        them since corrected or completed."""
        import numpy as np

        rng = np.random.default_rng(seed)
        df = payload.copy()
        moved = rng.choice(len(df), size=max(1, len(df) // 100), replace=False)
        df.loc[moved, "departure_status"] = "Admitted"
        return df

    def resupply_subset(self, payload, previous_dirty_seed: int, seed: int):
        return payload


def run_plan() -> tuple:
    """Each period's drawn severity, oldest first: Child Protection's mix.
    Drawn on every call, never cached (post-build-review #282 (7)): its length
    is the calendar's, which a long-lived process may see edited."""
    import numpy as np

    n = len(generated_periods())
    rng = np.random.default_rng(_RUN_PLAN_SEED)
    n_amber, n_red = max(1, round(n * 0.25)), 2
    rest = [None] * ((n - 1) - n_amber - n_red) + ["amber"] * n_amber + ["red"] * n_red
    rng.shuffle(rest)
    return tuple([None] + rest)


def generated_periods() -> list:
    """Every quarterly period Emergency Department owes, up to the anchor."""
    from generator.anchor_date import get_anchor_date
    from qa_tools.common import schedule

    return schedule.periods_for_dataset(DATASET_ID, until=get_anchor_date())


def _plan_injections(periods):
    """Where every Emergency Department scenario lands, resolved before
    anything is written (REQ-GEN-044 criterion 4)."""
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

    out, payload = [], rows.generate(period.date, seed, 0, 0)
    for n, extra in enumerate(injection.arrivals):
        if n:
            payload = rows.churn(payload, seed + 900 + n, period.date, 0)
        this = rows.dirty(payload, extra.severity, seed + 800 + n) if extra.severity else payload
        out.append(Delivery(received_date=period.date + timedelta(days=extra.day_offset),
                            severity=extra.severity, payload=this))
    return out


class EmergencyDepartment(Provider):
    collection_id = "emergency-department"
    dataset_id = DATASET_ID
    seed_ranges = ((60_000, 70_000),)
    generating_note = "one table, quarterly"
    # ITS ORDINARY AMBERS ARE ITS ONE TABLE'S (post-build-review #248).
    target_datasets = (DATASET_ID,)
    amber_dataset = DATASET_ID

    def seed_schedule(self) -> list[tuple[str, int, int]]:
        out = [("the run plan", _RUN_PLAN_SEED, _RUN_PLAN_SEED)]
        out += [(f"ed_slot_{i:02d}", BASE_SEED + i, BASE_SEED + i + SEED_SPAN)
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
        jobs = [Job(f"ed_slot_{i:02d}", BASE_SEED + i, sev, p)
                for i, (sev, p) in enumerate(zip(severities, periods), start=1)]
        return Plan(jobs=jobs, resolved=resolved, injected_by_period=injected,
                    state={"rows": Rows(), "suppressed": suppressed})

    def slot(self, plan: Plan, job: Job) -> list | None:
        from generator.resupply import run_slot_chain

        if job.period.name in plan.state["suppressed"]:
            return None  # a scenario's period with no supply at all (TS-3b)
        rows = plan.state["rows"]
        injected = plan.injected_by_period.get(job.period.name)
        if injected is not None:
            return _injected_chain(rows, injected[0], job.period, job.seed)
        days, weights = _delay()
        return list(run_slot_chain(rows, job.period.date, job.seed, id_offset=0, n_rows=0,
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
        from qa_tools.common import asset_time

        injected = plan.injected_by_period.get(job.period.name)
        if injected is not None:
            extra = injected[0].arrivals[n - 1]
            return asset_time.isoformat(asset_time.wall_clock(delivery_obj.received_date, extra.at))
        # Early morning, before the 09:00 due time, the minute drawn from the slot.
        minute = (job.seed * 37 + n * 11) % 120
        return asset_time.record_source_instant(
            datetime.combine(delivery_obj.received_date, time(7, 0)) + timedelta(minutes=minute),
            f"received_at for {entry['run_id']}")

    def files(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict, name: str):
        from generator import receipt_instants, scenario_injection
        from qa_tools.common import asset_time

        csvs = {FILE: delivery_obj.payload[COLUMNS].to_csv(index=False)}
        first = asset_time.parse_instant(entry["received_at"], entry["run_id"])
        injected = plan.injected_by_period.get(job.period.name)
        if injected is not None:
            return scenario_injection.apply_file_shape(
                injected[0].arrivals[n - 1].file_shape, csvs), first
        return csvs, receipt_instants.instants_for(csvs, first, name)

    def describe(self, entry: dict, delivery_obj) -> str:
        return f"{entry['row_counts'][TABLE]:5d} presentations"


PROVIDER = EmergencyDepartment()

