"""Thirty linked datasets and one linkage product reading them all, added to
a copy of the repository (REQ-TEST-339).

Five fake quarterly source collections of six datasets each - thirty linked
datasets - across two fake agencies, plus a fake linkage product in a third
reading every one of them. Each source dataset is identified by one column,
except `lks1-d2` (two) and `lks2-d3` (three), so the linkage product's
contract carries id_1 to id_3. The product's referential and coverage checks,
and its own-row checks, are GENERATED here from its `linked_datasets`, in the
shape the real Linkage Products' hand-written file has (REQ-QAC-333).

WHAT IS ADDED, AND WHERE (criterion 3): a contract and its check files per
collection under its agency's folder, a dbt folder per collection, a QA
adapter and a generator provider per collection - and inserts, as whole
blocks of text, into four configuration files: the hierarchy, the calendar,
the presentation words, and one scripted person decision (the move criterion
2 re-checks). Nothing else. `changed_product_files` is that criterion's
check, read from git in the copy.

ONE PERIOD: every source provider writes 2026-Q3 only, each collection one
delivery of six files on the round; the linkage product arrives at 17:05 the
same day; and one supply of `lks3-d1` is sent again two days later, which a
scripted person promotes over the first - moving it in the period, so the
knock-on re-runs the two linkage checks that read it (criterion 2).

Everything is written into a COPY of the tracked tree (tests/tree_copy.py);
the repository's own contract/, data/ and reports/ are never touched.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from tree_copy import copy_tracked_tree

PERIOD = "2026-Q3"
#: The fake agencies, each with its source collections: (collection number,
#: agency id).
SOURCE_AGENCIES = (
    ("lk-agency-north", "Department of Northern Records", (1, 2, 3)),
    ("lk-agency-south", "Department of Southern Records", (4, 5)),
)
DATASETS_PER_COLLECTION = 6
PRODUCT_AGENCY = ("lk-linkage-unit", "Linkage Unit for a Test")
PRODUCT = {"collection": "lk-linkage", "short": "lkp", "dataset": "lk-keys",
           "table": "lk_keys", "name": "Test Linkage Keys"}
#: The datasets identified by more than one column (criterion 1).
MULTI_ID = {"lks1-d2": ["site_code", "episode_no"],
            "lks2-d3": ["region", "site_code", "episode_no"]}
N_ID = max(len(c) for c in MULTI_ID.values())
#: The supply sent again and promoted over the first (criterion 2's move).
MOVED = "lks3-d1"
ROWS = 12
INTRODUCED = "2024-01-01"

#: Where a collection's own files may go (criterion 3), and the configuration
#: files that take an insert.
CONFIG_FILES = ("contract/data-asset.yaml", "contract/calendar.yaml",
                "contract/presentation.yaml", "contract/scripted_decisions.yaml")


def _agency_of(n: int) -> str:
    return next(a for a, _name, nums in SOURCE_AGENCIES if n in nums)


def sources() -> list[dict]:
    """The five source collections, each with its six datasets."""
    out = []
    for agency, _name, nums in SOURCE_AGENCIES:
        for n in nums:
            cid = f"lk-source-{n}"
            datasets = []
            for d in range(1, DATASETS_PER_COLLECTION + 1):
                did = f"lks{n}-d{d}"
                datasets.append({"id": did, "table": did.replace("-", "_"),
                                 "name": f"Source {n} Table {d}",
                                 "code": f"SRCX{n}{d:02d}",
                                 "id_columns": MULTI_ID.get(did, ["rec_id"])})
            out.append({"agency": agency, "id": cid, "short": f"lks{n}", "n": n,
                        "name": f"Linked Source {n}", "datasets": datasets})
    return out


def linked() -> list[dict]:
    return [d for c in sources() for d in c["datasets"]]


def own_paths() -> tuple[str, ...]:
    agencies = [a for a, _n, _x in SOURCE_AGENCIES] + [PRODUCT_AGENCY[0]]
    colls = [c["id"] for c in sources()] + [PRODUCT["collection"]]
    return (tuple(f"contract/{a}/" for a in agencies)
            + tuple(f"dbt_project/models/{c}/" for c in colls)
            + ("qa_tools/collections/", "generator/collections/"))


# ---- the source collections' files ----------------------------------------

def _source_contract(c: dict) -> str:
    schema = []
    for d in c["datasets"]:
        props = []
        for col in d["id_columns"]:
            integer = col == "episode_no"
            props.append({"name": col, "logicalType": "integer" if integer else "string",
                          "physicalType": "integer" if integer else "varchar(20)",
                          "required": True,
                          "description": f"Part of the record's identifier, {col}."})
        props.append({"name": "amount", "logicalType": "integer", "physicalType": "integer",
                      "required": True, "description": "A count the record carries."})
        schema.append({"name": d["table"], "physicalType": "table",
                       "description": f"One row per record of {d['name']}, per quarter.",
                       "properties": props})
    doc = {"apiVersion": "v3.2.0", "kind": "DataContract", "id": c["id"], "status": "draft",
           "version": "1.0.0", "name": c["name"], "domain": c["agency"],
           "description": {"purpose": f"A fake source collection for REQ-TEST-339, {c['name']}."},
           "servers": [{"server": "production", "type": "s3",
                        "location": f"s3://gov-data-exchange/{c['id']}/", "format": "csv",
                        "delimiter": "comma", "description": "A quarterly drop."}],
           "schema": schema,
           "customProperties": [{"property": "currentDeliveryFormat", "value": "csv"}]}
    return "# REQ-TEST-339: a fake source collection, in a copy only.\n" + yaml.safe_dump(
        doc, sort_keys=False)


def _source_soda(c: dict) -> str:
    doc = {}
    for d in c["datasets"]:
        doc[f"checks for {d['table']}"] = [{"row_count": {
            "fail": "when < 1",
            "attributes": {
                "check_id": f"data-asset-1.{c['agency']}.{c['id']}.{d['id']}.row_count_soda",
                "category": "completeness", "introduced_date": INTRODUCED,
                "description": "A supply must carry at least one row.",
                "failure_indicates": "self-evident", "changelog": []}}}]
    return "# REQ-TEST-339: a fake source collection's Soda checks.\n" + yaml.safe_dump(
        doc, sort_keys=False)


def _dbt(coll_id: str, tables: list[str]) -> dict[str, str]:
    out = {"sources.yml": "# REQ-TEST-339: a fake collection's dbt source.\n" + yaml.safe_dump(
        {"version": 2, "sources": [{"name": "raw",
                                    "schema": "{{ env_var('DBT_RUN_SCHEMA') }}",
                                    "tables": [{"name": t} for t in tables]}]}, sort_keys=False),
           "schema.yml": "# REQ-TEST-339: a fake collection's dbt models, no tests.\n"
           + yaml.safe_dump({"version": 2, "models": [
               {"name": f"stg_{t}", "description": f"{t} as delivered."} for t in tables]},
               sort_keys=False)}
    for t in tables:
        out[f"stg_{t}.sql"] = (f"-- REQ-TEST-339: {t} as delivered.\n"
                               f"select * from {{{{ source('raw', '{t}') }}}}\n")
    return out


def _source_adapter(c: dict) -> str:
    keys = {d["table"]: d["id_columns"][0] for d in c["datasets"]}
    return ("\"\"\"A fake source collection's adapter (REQ-TEST-339), in a copy only.\"\"\"\n"
            "from qa_tools.collections.base import CollectionAdapter, SodaSpec\n\n"
            f"ADAPTER = CollectionAdapter(collection_id={c['id']!r}, label={c['name']!r},\n"
            f"                            sample_key={keys!r},\n"
            f"                            soda=SodaSpec(data_source={c['short']!r}),\n"
            f"                            claim_window_dataset={c['datasets'][0]['id']!r})\n")


def _source_provider(c: dict) -> str:
    seed = 3_390_000 + c["n"] * 100
    datasets = [(d["id"], d["table"], d["id_columns"]) for d in c["datasets"]]
    resend = MOVED if any(d["id"] == MOVED for d in c["datasets"]) else None
    return f'''"""A fake source collection's generator (REQ-TEST-339), in a copy only.

One delivery of every table in {PERIOD}, received on the round at 09:0{c["n"]}; a
dataset in RESEND is sent again two days later. Standard library only.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, time, timedelta

from generator.collections.base import Job, Plan, Provider

DATASETS = {datasets!r}
RESEND = {resend!r}
ROWS = {ROWS}
SEED = {seed}


def rows_of(table, id_columns, seed):
    """The same records every time: what the fake linkage product links."""
    out = []
    for i in range(ROWS):
        row = {{}}
        for col in id_columns:
            row[col] = (i + 1) if col == "episode_no" else f"{{table.upper()}}-{{col[:2]}}{{i:03d}}"
        row["amount"] = (seed + i) % 97
        out.append(row)
    return out


@dataclass
class _Delivery:
    payload: dict = field(default_factory=dict)
    severity: str | None = None
    received_date: date | None = None
    at: time = time(9, {c["n"]})


class _Source(Provider):
    collection_id = {c["id"]!r}
    dataset_id = {c["datasets"][0]["id"]!r}
    seed_ranges = ((SEED, SEED + 100),)

    def seed_schedule(self):
        return [("the quarter", SEED + 1, SEED + 1)]

    def generated_periods(self):
        from qa_tools.common import schedule

        return [p for p in schedule.periods_for_dataset(self.dataset_id) if p.name == {PERIOD!r}]

    def plan(self):
        return Plan(jobs=[Job("{c["short"]}_slot_01", SEED + 1, None, p)
                          for p in self.generated_periods()])

    def slot(self, plan, job):
        first = _Delivery({{t: rows_of(t, cols, job.seed) for _d, t, cols in DATASETS}}, None,
                          job.period.round_date)
        if RESEND is None:
            return [first]
        table = next(t for d, t, _c in DATASETS if d == RESEND)
        return [first, _Delivery({{table: first.payload[table]}}, None,
                                 job.period.round_date + timedelta(days=2), time(9, 30))]

    def entries(self, plan, job, deliveries, run_index_start):
        return [{{"run_id": f"{c["short"]}_run_{{run_index_start + n:03d}}",
                 "run_index": run_index_start + n, "slot_id": job.slot_id,
                 "period": job.period.name, "received_at": None, "dirty_severity": None,
                 "seed": job.seed,
                 "row_counts": {{t: len(r) for t, r in d.payload.items()}}}}
                for n, d in enumerate(deliveries, start=1)]

    def received_at(self, plan, job, n, delivery_obj, entry):
        from qa_tools.common import asset_time

        return asset_time.isoformat(asset_time.wall_clock(
            delivery_obj.received_date, delivery_obj.at.strftime("%H:%M")))

    def files(self, plan, job, n, delivery_obj, entry, name):
        from qa_tools.common import asset_time

        out = {{}}
        for table, rows in delivery_obj.payload.items():
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
            out[f"{{table}}.csv"] = buf.getvalue()
        return out, asset_time.parse_instant(entry["received_at"], entry["run_id"])

    def describe(self, entry, delivery_obj):
        return f"{{sum(entry['row_counts'].values()):4d}} rows"

    def table_rows(self, delivery_obj, table):
        return delivery_obj.payload.get(table)


PROVIDER = _Source()
'''


# ---- the linkage product's files ------------------------------------------

def _id_cols(k: int) -> list[str]:
    return [f"id_{j}" for j in range(1, k + 1)]


def _product_contract() -> str:
    props = [{"name": "linkage_key", "logicalType": "string", "physicalType": "varchar(64)",
              "required": True, "description": "A scrambled key shared by one person's records."},
             {"name": "dataset", "logicalType": "string", "physicalType": "varchar(40)",
              "required": True, "description": "The supplier's own code for the dataset."}]
    for j in range(1, N_ID + 1):
        props.append({"name": f"id_{j}", "logicalType": "string", "physicalType": "varchar(64)",
                      "required": j == 1, "description": f"The record's identifier value {j}."})
    doc = {"apiVersion": "v3.2.0", "kind": "DataContract", "id": PRODUCT["dataset"],
           "status": "draft", "version": "1.0.0", "name": PRODUCT["name"],
           "domain": PRODUCT_AGENCY[0],
           "description": {"purpose": "A fake linkage product for REQ-TEST-339."},
           "servers": [{"server": "production", "type": "s3",
                        "location": "s3://gov-data-exchange/lk-linkage/", "format": "csv",
                        "delimiter": "comma", "description": "A quarterly linkage release."}],
           "schema": [{"name": PRODUCT["table"], "physicalType": "table",
                       "description": "One row per linked source record.",
                       "properties": props}]}
    return "# REQ-TEST-339: a fake linkage product, in a copy only.\n" + yaml.safe_dump(
        doc, sort_keys=False)


def check_id(tail: str) -> str:
    return (f"data-asset-1.{PRODUCT_AGENCY[0]}.{PRODUCT['collection']}."
            f"{PRODUCT['dataset']}.{tail}")


def referential_name(d: dict) -> str:
    return f"{d['name']} links match a record"


def _text(column: str) -> str:
    """BOTH SIDES AS TEXT. REQ-QAC-333 criterion 3 casts the source column;
    the linkage file's own id columns are typed by staging's inference, so
    id_3 holding only episode numbers stages as a number and is cast too."""
    return f"CAST({column} AS TEXT)"


def _product_soda() -> str:
    """REQ-QAC-333's shape, generated from the linked datasets: own-row checks
    (1) to (5), then a referential and a coverage check per linked dataset."""
    t = PRODUCT["table"]
    ds = linked()
    codes = [d["code"] for d in ds]
    counts = {d["code"]: len(d["id_columns"]) for d in ds}

    def missing(cols):
        return " OR ".join(f"{c} IS NULL OR TRIM({_text(c)}) = ''" for c in cols)

    expected = "\n   OR ".join(f"(dataset = '{d['code']}' AND ({missing(_id_cols(len(d['id_columns'])))}))"
                              for d in ds)
    surplus = "\n   OR ".join(
        f"(dataset = '{d['code']}' AND ("
        + " OR ".join(f"COALESCE(TRIM({_text(f'id_{j}')}), '') <> ''"
                      for j in range(len(d["id_columns"]) + 1, N_ID + 1)) + "))"
        for d in ds if len(d["id_columns"]) < N_ID)
    checks = [
        {"missing_count(linkage_key)": {"missing values": [""], "fail": "when > 0", "attributes": {
            "check_id": check_id("linkage_key.missing_count_soda"), "name": "Linkage key recorded",
            "category": "completeness", "introduced_date": INTRODUCED,
            "description": "This value must never be empty.",
            "failure_indicates": "self-evident", "changelog": []}}},
        {"invalid_count(dataset)": {"valid values": codes, "fail": "when > 0", "attributes": {
            "check_id": check_id("dataset.invalid_count_soda"), "name": "Known dataset code",
            "category": "conformity", "introduced_date": INTRODUCED, "linkage_codes": codes,
            "description": "Every row must name a dataset this release is agreed to link.",
            "failure_indicates": "self-evident", "changelog": []}}},
        {"failed rows": {"name": "Expected identifiers present",
                         "fail query": f"SELECT dataset, linkage_key FROM {t}\nWHERE {expected}\n",
                         "samples limit": 1000, "attributes": {
                             "check_id": check_id("id_1.expected_ids_soda"),
                             "reads_columns": [f"{t}.dataset", f"{t}.linkage_key"]
                             + [f"{t}.{c}" for c in _id_cols(N_ID)],
                             "category": "completeness", "introduced_date": INTRODUCED,
                             "id_counts": counts,
                             "description": "Each row must carry every identifier its dataset is identified by.",
                             "failure_indicates": "self-evident", "changelog": []}}},
        {"failed rows": {"name": "No surplus identifiers",
                         "fail query": f"SELECT dataset, linkage_key FROM {t}\nWHERE {surplus}\n",
                         "samples limit": 1000, "attributes": {
                             "check_id": check_id("id_1.no_surplus_ids_soda"),
                             "reads_columns": [f"{t}.dataset", f"{t}.linkage_key"]
                             + [f"{t}.{c}" for c in _id_cols(N_ID)][1:],
                             "category": "conformity", "introduced_date": INTRODUCED,
                             "id_counts": counts,
                             "description": "A row must carry no identifier beyond those its dataset is identified by.",
                             "failure_indicates": "self-evident", "changelog": []}}},
        {f"duplicate_count(dataset, {', '.join(_id_cols(N_ID))})": {
            "fail": "when > 0", "attributes": {
                "check_id": check_id("id_1.duplicate_count_soda"), "name": "Each record linked once",
                "category": "uniqueness", "introduced_date": INTRODUCED,
                "description": "A record must appear once in a release.",
                "failure_indicates": "self-evident", "changelog": []}}},
    ]
    for d in ds:
        cols = d["id_columns"]
        on_src = " AND ".join(f"{_text('s.' + c)} = {_text(f'l.id_{j}')}"
                              for j, c in enumerate(cols, 1))
        on_cov = " AND ".join(f"{_text(f'l.id_{j}')} = {_text('s.' + c)}"
                              for j, c in enumerate(cols, 1))
        lid = ", ".join(_id_cols(len(cols)))
        common = {"reads_tables": [d["table"]], "linked_dataset": d["id"],
                  "linkage_code": d["code"], "id_columns": cols,
                  "introduced_date": INTRODUCED, "changelog": []}
        checks.append({"failed rows": {
            "name": referential_name(d),
            "fail query": (f"SELECT l.dataset, l.id_1 FROM {t} l\n"
                           f"LEFT JOIN {d['table']} s ON {on_src}\n"
                           f"WHERE l.dataset = '{d['code']}' AND s.{cols[0]} IS NULL\n"),
            "samples limit": 1000,
            "attributes": {"check_id": check_id(f"{d['id']}.referential_soda"),
                           "reads_columns": [f"{t}.dataset", f"{t}.id_1"]
                           + [f"{d['table']}.{c}" for c in cols],
                           **common, "linked_check": "referential", "category": "consistency",
                           "description": f"Every row coded {d['code']} must match a record of {d['name']}.",
                           "failure_indicates": "self-evident"}}})
        metric = f"{d['table']}_coverage_percent"
        checks.append({metric: {
            f"{metric} query": (f"SELECT 100.0 * COUNT(l.id_1) / NULLIF(COUNT(*), 0)\n"
                                f"FROM {d['table']} s\n"
                                f"LEFT JOIN (SELECT DISTINCT {lid} FROM {t} "
                                f"WHERE dataset = '{d['code']}') l\n  ON {on_cov}\n"),
            "warn": "when < 90", "fail": "when < 85",
            "attributes": {"check_id": check_id(f"{d['id']}.coverage_soda"),
                           **common, "linked_check": "coverage", "unit": "percent",
                           "direction": "below", "category": "completeness",
                           "description": f"At least 90 percent of {d['name']}'s records must be linked.",
                           "failure_indicates": "self-evident"}}})
    return ("# REQ-TEST-339: the fake linkage product's Soda checks, generated from its\n"
            "# linked_datasets in the shape of the real Linkage Products' file.\n"
            + yaml.safe_dump({f"checks for {t}": checks}, sort_keys=False, width=1000))


def _product_adapter() -> str:
    names = {"Expected identifiers present": "id_1", "No surplus identifiers": "id_1"}
    names |= {referential_name(d): "id_1" for d in linked()}
    return ("\"\"\"The fake linkage product's adapter (REQ-TEST-339), in a copy only.\"\"\"\n"
            "from qa_tools.collections.base import CollectionAdapter, SodaSpec\n\n"
            f"ADAPTER = CollectionAdapter(\n"
            f"    collection_id={PRODUCT['collection']!r}, label={PRODUCT['name']!r},\n"
            f"    sample_key={{{PRODUCT['table']!r}: 'linkage_key'}},\n"
            f"    soda=SodaSpec(data_source={PRODUCT['short']!r}, column_by_name={names!r}),\n"
            f"    claim_window_dataset={PRODUCT['dataset']!r})\n")


def _product_provider() -> str:
    return f'''"""The fake linkage product's generator (REQ-TEST-339), in a copy only:
one release in {PERIOD}, at 17:05 on the round, linking every row of the last
supply of each linked dataset received before it, across id_1 to id_{N_ID}.
Generic over the linked datasets declared in contract/data-asset.yaml, read
through each source provider's declared rows (generated_supplies)."""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date

from generator.collections.base import Job, Plan, Provider

DATASET_ID = {PRODUCT["dataset"]!r}
TABLE = {PRODUCT["table"]!r}
N_ID = {N_ID}
COLUMNS = ["linkage_key", "dataset"] + [f"id_{{j}}" for j in range(1, N_ID + 1)]
SEED = 3_399_000


def linked():
    from qa_tools.common import hierarchy

    return hierarchy.dataset(DATASET_ID).linked


@dataclass
class _Delivery:
    payload: list = field(default_factory=list)
    severity: str | None = None
    received_date: date | None = None


class _Product(Provider):
    collection_id = {PRODUCT["collection"]!r}
    dataset_id = DATASET_ID
    seed_ranges = ((SEED, SEED + 100),)

    @property
    def depends_on(self):
        from qa_tools.common import hierarchy

        return tuple(dict.fromkeys(hierarchy.dataset(d).collection_id for d, _c, _x in linked()))

    def seed_schedule(self):
        return [("the release", SEED + 1, SEED + 1)]

    def generated_periods(self):
        from qa_tools.common import schedule

        return [p for p in schedule.periods_for_dataset(DATASET_ID) if p.name == {PERIOD!r}]

    def plan(self):
        from generator import collections
        from generator.collections import base

        sources = {{d: base.generated_supplies(collections.for_dataset(d), d)
                   for d, _c, _x in linked()}}
        return Plan(jobs=[Job("lkp_slot_01", SEED + 1, None, p) for p in self.generated_periods()],
                    state={{"sources": sources}})

    def slot(self, plan, job):
        from qa_tools.common import asset_time

        at = asset_time.wall_clock(job.period.round_date, "17:05")
        rows = []
        for did, code, cols in linked():
            before = [s for s in plan.state["sources"][did] if s.period == job.period.name
                      and asset_time.parse_instant(s.received_at, did) < at]
            for src in before[-1].rows:
                values = [str(src[c]) for c in cols]
                key = "LK" + hashlib.sha256(f"{{code}}:{{values}}".encode()).hexdigest()[:16].upper()
                row = {{"linkage_key": key, "dataset": code}}
                for j in range(1, N_ID + 1):
                    row[f"id_{{j}}"] = values[j - 1] if j <= len(values) else ""
                rows.append(row)
        return [_Delivery(rows, None, job.period.round_date)]

    def entries(self, plan, job, deliveries, run_index_start):
        return [{{"run_id": f"lkp_run_{{run_index_start + n:03d}}", "run_index": run_index_start + n,
                 "slot_id": job.slot_id, "period": job.period.name, "received_at": None,
                 "dirty_severity": None, "seed": job.seed, "row_counts": {{TABLE: len(d.payload)}}}}
                for n, d in enumerate(deliveries, start=1)]

    def received_at(self, plan, job, n, delivery_obj, entry):
        from qa_tools.common import asset_time

        return asset_time.isoformat(asset_time.wall_clock(job.period.round_date, "17:05"))

    def files(self, plan, job, n, delivery_obj, entry, name):
        from qa_tools.common import asset_time

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(delivery_obj.payload)
        return ({{f"{{TABLE}}.csv": buf.getvalue()}},
                asset_time.parse_instant(entry["received_at"], entry["run_id"]))

    def describe(self, entry, delivery_obj):
        return f"{{entry['row_counts'][TABLE]:5d}} linkage keys"


PROVIDER = _Product()
'''


# ---- the configuration inserts --------------------------------------------

def _hierarchy_block() -> str:
    agencies = []
    for agency, name, nums in SOURCE_AGENCIES:
        colls = [c for c in sources() if c["n"] in nums]
        agencies.append({"id": agency, "name": name, "short": agency.replace("lk-agency-", "lk")[:6],
                         "collections": [{
                             "id": c["id"], "name": c["name"], "short": c["short"],
                             "run_prefix": f"{c['short']}_run_",
                             "contract": f"{agency}/{c['id']}-contract.yaml",
                             "delivery_boundary": "directory",
                             "datasets": [{"id": d["id"], "name": d["name"], "table": d["table"],
                                           "arrival_pattern": rf"{d['table']}\.csv"}
                                          for d in c["datasets"]]} for c in colls]})
    agencies.append({"id": PRODUCT_AGENCY[0], "name": PRODUCT_AGENCY[1], "short": "lkunit",
                     "collections": [{
                         "id": PRODUCT["collection"], "name": PRODUCT["name"],
                         "short": PRODUCT["short"], "run_prefix": f"{PRODUCT['short']}_run_",
                         "contract": f"{PRODUCT_AGENCY[0]}/{PRODUCT['collection']}-contract.yaml",
                         "delivery_boundary": "directory",
                         "datasets": [{"id": PRODUCT["dataset"], "name": PRODUCT["name"],
                                       "table": PRODUCT["table"],
                                       "arrival_pattern": rf"{PRODUCT['table']}\.csv",
                                       "linked_datasets": [
                                           {"dataset": d["id"], "code": d["code"],
                                            "id_columns": d["id_columns"]} for d in linked()]}]}]})
    text = yaml.safe_dump(agencies, sort_keys=False, width=1000)
    return ("    # REQ-TEST-339: thirty linked datasets and a linkage product, in a copy only.\n"
            + "".join(f"    {line}\n" for line in text.splitlines()))


def _versions(change: str, **extra) -> dict:
    return {"versions": [{"effective_from": INTRODUCED, **extra,
                          "changelog": [{"date": "2026-10-30", "author": "REQ-TEST-339",
                                         "change": change}]}]}


def _calendar_blocks() -> tuple[str, str]:
    colls = [(c["id"], "09:00") for c in sources()] + [(PRODUCT["collection"], "18:00")]
    entries = [{"id": cid, "calendar": "quarterly",
                "files_go_to_period": _versions("Files go into the period they arrive in.", value=0),
                "participation_defaults": _versions(f"Owes a supply every quarter, due {due}.",
                                                    expected_time=due, grace="8h")}
               for cid, due in colls]
    datasets = [{"id": d, "participation": _versions("Owes supplies every quarter.")}
                for d in [x["id"] for x in linked()] + [PRODUCT["dataset"]]]

    def indent(doc):
        return "".join(f"  {line}\n" for line in yaml.safe_dump(doc, sort_keys=False).splitlines())

    head = "  # REQ-TEST-339: thirty linked datasets and a linkage product, in a copy only.\n"
    return head + indent(entries), head + indent(datasets)


def _presentation_blocks() -> tuple[str, str]:
    agencies = "".join(f"  {a}:\n    blurb: \"A fictional agency, for a test.\"\n"
                       for a in [a for a, _n, _x in SOURCE_AGENCIES] + [PRODUCT_AGENCY[0]])
    colls = "".join(
        f"  {cid}:\n    provider: \"A fictional supplier\"\n    delivery_format: \"CSV\"\n"
        f"    provenance: \"A fake collection for REQ-TEST-339. ({{table_description}})\"\n"
        for cid in [c["id"] for c in sources()] + [PRODUCT["collection"]])
    return agencies, colls


def _decision_block() -> str:
    return ("  # REQ-TEST-339: a person promotes the second supply of one linked dataset\n"
            "  # over the first, after the linkage product was checked - a move in the\n"
            "  # period that re-checks only the two linkage checks reading it.\n"
            f"  - operation: promote\n    dataset: {MOVED}\n    period: {PERIOD}\n"
            "    supply: 1\n    after_hours: 1\n"
            "    reason: \"The resent file is the supplier's corrected one; it replaces the first.\"\n")


def _insert_before(path: Path, marker: str, block: str) -> None:
    lines = path.read_text().splitlines(keepends=True)
    at = next(i for i, line in enumerate(lines) if line.startswith(marker))
    while at > 0 and not lines[at - 1].strip():
        at -= 1
    path.write_text("".join(lines[:at] + block.splitlines(keepends=True) + lines[at:]))


def _append(path: Path, block: str) -> None:
    path.write_text(path.read_text().rstrip("\n") + "\n" + block)


def install(tree: Path) -> Path:
    """Add the thirty, the product and their configuration to the copy."""
    def write(rel: str, text: str) -> None:
        dest = tree / rel
        assert not dest.exists(), f"{rel} already exists in the copy"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)

    for c in sources():
        stem = f"contract/{c['agency']}/{c['id']}"
        write(f"{stem}-contract.yaml", _source_contract(c))
        write(f"{stem}-soda-checks.yml", _source_soda(c))
        write(f"{stem}-evidently-checks.yml", "checks: []\n")
        write(f"{stem}-contract-retired.yaml", "schema: []\n")
        write(f"{stem}-soda-checks-retired.yml",
              "".join(f"checks for {d['table']}: []\n" for d in c["datasets"]))
        write(f"{stem}-evidently-checks-retired.yml", "checks: []\n")
        for name, text in _dbt(c["id"], [d["table"] for d in c["datasets"]]).items():
            write(f"dbt_project/models/{c['id']}/{name}", text)
        module = c["id"].replace("-", "_")
        write(f"qa_tools/collections/{module}.py", _source_adapter(c))
        write(f"generator/collections/{module}.py", _source_provider(c))

    stem = f"contract/{PRODUCT_AGENCY[0]}/{PRODUCT['collection']}"
    write(f"{stem}-contract.yaml", _product_contract())
    write(f"{stem}-soda-checks.yml", _product_soda())
    write(f"{stem}-evidently-checks.yml", "checks: []\n")
    write(f"{stem}-contract-retired.yaml", "schema: []\n")
    write(f"{stem}-soda-checks-retired.yml", f"checks for {PRODUCT['table']}: []\n")
    write(f"{stem}-evidently-checks-retired.yml", "checks: []\n")
    for name, text in _dbt(PRODUCT["collection"], [PRODUCT["table"]]).items():
        write(f"dbt_project/models/{PRODUCT['collection']}/{name}", text)
    module = PRODUCT["collection"].replace("-", "_")
    write(f"qa_tools/collections/{module}.py", _product_adapter())
    write(f"generator/collections/{module}.py", _product_provider())

    _append(tree / "contract/data-asset.yaml", _hierarchy_block())
    colls, datasets = _calendar_blocks()
    _insert_before(tree / "contract/calendar.yaml", "datasets:", colls)
    _append(tree / "contract/calendar.yaml", datasets)
    agencies, pcolls = _presentation_blocks()
    _insert_before(tree / "contract/presentation.yaml", "collections:", agencies)
    _append(tree / "contract/presentation.yaml", pcolls)
    _insert_before(tree / "contract/scripted_decisions.yaml", "corrections:", _decision_block())
    for rel in CONFIG_FILES:
        yaml.safe_load((tree / rel).read_text())
    return tree


def _git(tree: Path, *argv: str) -> str:
    return subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *argv],
                          cwd=tree, check=True, capture_output=True, text=True).stdout


def build(dest: Path) -> Path:
    """Copy the tracked tree into `dest`, commit it as the copy's baseline, then
    install the fixture - so `git status` in the copy is exactly what was added
    or changed since, ignored state (data/, reports/) aside."""
    copy_tracked_tree(dest)
    _git(dest, "init", "-q")
    _git(dest, "add", "-A")
    _git(dest, "commit", "-qm", "the tracked tree, as it stands")
    return install(dest)


def changed_product_files(tree: Path) -> list[str]:
    """Criterion 3: every file in the copy that differs from the tree it was
    copied from, outside configuration, check files, adapters and providers.
    A changed configuration file must have been added to only. Read from git,
    so files the repository ignores (data/, reports/, dbt's target) - state,
    not product - are not counted."""
    import difflib

    out = []
    status = _git(tree, "status", "--porcelain", "--untracked-files=all", "-z")
    entries = [e for e in status.split("\0") if e]
    assert entries, "git status shows nothing - the fixture installed nothing"
    for entry in entries:
        code, rel = entry[:2], entry[3:]
        if code == "??":
            if not rel.startswith(own_paths()):
                out.append(f"{rel} is new and outside a collection's own places")
            continue
        if rel not in CONFIG_FILES:
            out.append(f"{rel} changed ({code.strip()})")
            continue
        before = _git(tree, "show", f"HEAD:{rel}").splitlines()
        after = (tree / rel).read_text().splitlines()
        for op, a1, a2, _b1, _b2 in difflib.SequenceMatcher(
                None, before, after, autojunk=False).get_opcodes():
            if op not in ("equal", "insert"):
                out.append(f"{rel}: lines {a1 + 1}-{a2} were {op}d, not only added to")
    return out
