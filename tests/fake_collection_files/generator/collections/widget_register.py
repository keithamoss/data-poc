"""The fake Widget Register's synthetic generator (REQ-TEST-249).

Four quarters, one CSV each, the third with five widgets of no colour so
every tool has something to say. Installed only in a copy of the
repository; imports nothing heavier than the standard library.
"""
from __future__ import annotations

import csv
import io
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from generator.collections.base import Job, Plan, Provider

DATASET_ID = "widgets"
BASE_SEED = 950_000
N_QUARTERS = 4
N_ROWS = 120
COLOURS = ("red", "green", "blue")


@dataclass
class _Delivery:
    payload: list = field(default_factory=list)
    severity: str | None = None
    received_date: date | None = None


class WidgetRegister(Provider):
    collection_id = "widget-register"
    dataset_id = DATASET_ID
    seed_ranges = ((BASE_SEED, BASE_SEED + 100),)

    def seed_schedule(self):
        return [(f"widget_slot_{i:02d}", BASE_SEED + i, BASE_SEED + i)
                for i in range(1, N_QUARTERS + 1)]

    def generated_periods(self):
        from generator.anchor_date import get_anchor_date
        from qa_tools.common import schedule

        return schedule.periods_for_dataset(DATASET_ID, until=get_anchor_date())[-N_QUARTERS:]

    def plan(self) -> Plan:
        periods = self.generated_periods()
        return Plan(jobs=[Job(f"widget_slot_{i:02d}", BASE_SEED + i, "red" if i == 3 else None, p)
                          for i, p in enumerate(periods, start=1)])

    def slot(self, plan: Plan, job: Job) -> list:
        rng = random.Random(job.seed)
        rows = [{"widget_id": job.seed * 1000 + n,
                 "colour": rng.choice(COLOURS),
                 "made_on": (job.period.date - timedelta(days=rng.randint(1, 80))).isoformat()}
                for n in range(N_ROWS)]
        if job.severity == "red":
            for row in rows[:5]:
                row["colour"] = ""
        return [_Delivery(rows, job.severity, job.period.date)]

    def entries(self, plan: Plan, job: Job, deliveries: list, run_index_start: int) -> list[dict]:
        return [{"run_id": f"wreg_run_{run_index_start + n:03d}", "run_index": run_index_start + n,
                 "slot_id": job.slot_id, "period": job.period.name, "received_at": None,
                 "dirty_severity": d.severity, "seed": job.seed,
                 "row_counts": {"widgets": len(d.payload)}}
                for n, d in enumerate(deliveries, start=1)]

    def received_at(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict) -> str:
        from qa_tools.common import asset_time

        return asset_time.record_source_instant(
            datetime.combine(delivery_obj.received_date, time(8, 30)), f"received_at for {entry['run_id']}")

    def files(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict, name: str):
        from qa_tools.common import asset_time

        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=["widget_id", "colour", "made_on", "extract_timestamp"])
        writer.writeheader()
        stamp = entry["received_at"]
        for row in delivery_obj.payload:
            writer.writerow({**row, "extract_timestamp": stamp})
        return {"widgets.csv": out.getvalue()}, asset_time.parse_instant(stamp, entry["run_id"])

    def describe(self, entry: dict, delivery_obj) -> str:
        return f"{entry['row_counts']['widgets']:5d} widgets"


PROVIDER = WidgetRegister()
