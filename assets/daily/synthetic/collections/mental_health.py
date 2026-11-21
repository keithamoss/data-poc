"""The Mental Health collection's synthetic generator (REQ-GEN-351): one table,
one CSV per supply, owed once a week on Mondays, drawn with the collections'
severity mix - about a quarter amber, a red with a passing resupply the same
day, the oldest supply clean - from seeds of its own.

A PROVIDER OF THE SHARED DRIVER (REQ-GEN-246), and nothing else: the slot
loop, bookkeeping, delivery and receipt writing and scenario placement are
generator/driver.py's. Importable without pandas or numpy; each hook imports
what it needs.

SYNTHETIC ONLY: a test dataset made to exercise weekly participation on a daily
asset, standing in for no real supply. Postcodes come from generator/names_au.py's WA pool,
every other value from a seeded draw.
"""
from __future__ import annotations

import functools
from datetime import date, datetime, time, timedelta

from generator.collections.base import Job, Plan, Provider

DATASET_ID = "mental-health-contacts"
TABLE = "mental_health_contacts"
FILE = f"{TABLE}.csv"

#: The seed range Keith settled (2026-11-01): [74000, 75000). Slots draw
#: 74001.., each plus its largest derived offset - the resupply chain's churns
#: and dirty rolls (+900 and up, at most eight attempts).
BASE_SEED = 74_000
_RUN_PLAN_SEED = 74_950
SEED_SPAN = 909
#: About eight hundred contacts a supply - a week of a few community services.
N_ROWS = 800

COLUMNS = ["contact_id", "contact_date", "service_type", "referral_source", "sex", "age_group",
           "postcode", "contact_minutes"]
SERVICES = ["Community", "Inpatient", "Emergency", "Telehealth"]
_SERVICE_WEIGHTS = [0.55, 0.10, 0.10, 0.25]
REFERRALS = ["GP", "Self", "Hospital", "Police", "Other"]
_REFERRAL_WEIGHTS = [0.40, 0.20, 0.25, 0.05, 0.10]
AGE_GROUPS = ["0-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
_AGE_WEIGHTS = [0.12, 0.16, 0.20, 0.18, 0.15, 0.11, 0.08]


@functools.cache
def _postcodes() -> tuple[str, ...]:
    from generator.names_au import SUBURBS

    return tuple(sorted({postcode for _suburb, postcode in SUBURBS}))


def _delay():
    """A resupply comes the SAME DAY: a Monday's slot closes when Tuesday's
    claim window opens (REQ-PIPE-131), so a resend days later would find no
    slot open and be held - a different scenario (TS-117's shape)."""
    import numpy as np

    return np.array([0]), np.array([1.0])


class Rows:
    """The resupply chain's view of a supply (generator/resupply.py's
    DatasetProvider): one DataFrame of contacts."""

    def generate(self, run_date: date, seed: int, n_rows: int, id_offset: int):
        import numpy as np
        import pandas as pd

        rng = np.random.default_rng(seed)
        n = N_ROWS + int(rng.integers(-80, 81))
        # The seven days before the Monday it is supplied.
        days = rng.integers(1, 8, size=n)
        return pd.DataFrame({
            "contact_id": [f"MH{seed:05d}{i:05d}" for i in range(n)],
            "contact_date": [(run_date - timedelta(days=int(d))).isoformat() for d in days],
            "service_type": rng.choice(SERVICES, size=n, p=_SERVICE_WEIGHTS),
            "referral_source": rng.choice(REFERRALS, size=n, p=_REFERRAL_WEIGHTS),
            "sex": rng.choice(["M", "F", "X"], size=n, p=[0.46, 0.52, 0.02]),
            "age_group": rng.choice(AGE_GROUPS, size=n, p=_AGE_WEIGHTS),
            "postcode": rng.choice(_postcodes(), size=n),
            "contact_minutes": rng.gamma(2.0, 25.0, size=n).astype(int).clip(5, 240),
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
            df.loc[rows(2), "contact_minutes"] = 0
        else:
            df.loc[rows(int(n * 0.08)), "postcode"] = None
            df.loc[rows(10), "contact_minutes"] = 9_999
            df.loc[rows(5), "service_type"] = "Outreach"
            df.loc[rows(4), "referral_source"] = "School"
            late = rows(6)
            df.loc[late, "contact_date"] = [
                (date.fromisoformat(d) + timedelta(days=14)).isoformat()
                for d in df.loc[late, "contact_date"]]
        return df

    def churn(self, payload, seed: int, run_date: date, id_offset: int):
        """A resupply of the same week: the same contacts, a few of them since
        corrected."""
        import numpy as np

        rng = np.random.default_rng(seed)
        df = payload.copy()
        moved = rng.choice(len(df), size=max(1, len(df) // 100), replace=False)
        df.loc[moved, "contact_minutes"] = df.loc[moved, "contact_minutes"] + 5
        return df

    def resupply_subset(self, payload, previous_dirty_seed: int, seed: int):
        return payload


def run_plan() -> tuple:
    """Each owed Monday's drawn severity, oldest first: about a quarter amber,
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
    """Every day the dataset owes - each Monday - up to the anchor."""
    from generator.anchor_date import get_anchor_date
    from asset_model import schedule

    return schedule.periods_for_dataset(DATASET_ID, until=get_anchor_date())


def _plan_injections(periods):
    """Where each Mental Health scenario lands, resolved before anything is written
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


class MentalHealth(Provider):
    collection_id = "mental-health"
    dataset_id = DATASET_ID
    seed_ranges = ((74_000, 75_000),)
    generating_note = "one table, weekly"
    target_datasets = (DATASET_ID,)
    amber_dataset = DATASET_ID

    def seed_schedule(self) -> list[tuple[str, int, int]]:
        out = [("the run plan", _RUN_PLAN_SEED, _RUN_PLAN_SEED)]
        out += [(f"mh_slot_{i:02d}", BASE_SEED + i, BASE_SEED + i + SEED_SPAN)
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
        jobs = [Job(f"mh_slot_{i:02d}", BASE_SEED + i, sev, p)
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
        # The first before the 10:00 due time and inside the claim window, the
        # minute drawn from the slot, so no two deliveries share a receipt
        # instant (REQ-GEN-334 criterion 13).
        # Each resend of the day ninety minutes after the one before it, all
        # before Tuesday's claim window opens.
        minute = (job.seed * 41) % 30 + (n - 1) * 90
        at = (datetime.combine(delivery_obj.received_date, time(8, 0))
              + timedelta(minutes=minute)).strftime("%H:%M")
        return asset_time.isoformat(asset_time.wall_clock(delivery_obj.received_date, at))

    def arrival_files(self, plan: Plan, job: Job, n: int, delivery_obj) -> dict[str, str]:
        """The one Service Contacts file, before any scenario shape."""
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
        return f"{entry['row_counts'][TABLE]:5d} contacts"


PROVIDER = MentalHealth()
