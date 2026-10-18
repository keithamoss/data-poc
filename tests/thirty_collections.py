"""Thirty collections, in a copy of the tree (REQ-TEST-252 criterion 15).

The two real collections plus twenty-eight more across five more agencies,
with names that share leading words ("Emergency Department ...", "Hospital
...") so a reader has to tell similar names apart. One-table and N-table
collections, with and without the target-trial capability. Each has a QA
adapter and, for most, a generator provider - both importing no tool
library, as every real one must - and nothing else: help and the menus
read configuration only, so no contract, check file or database is needed.

Everything is written into a COPY of the tracked tree (tests/tree_copy.py);
the repository's own contract/, data/ and reports/ are never touched.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from tree_copy import copy_tracked_tree

#: (agency id, agency name, [(collection name, short, tables, has trial)]).
#: A table list of one is a one-table collection.
AGENCIES = [
    ("health-hospitals", "Department of Health - Hospitals", [
        ("Emergency Department Presentations", "edp", ["ed_presentations"], True),
        ("Emergency Department Admissions", "eda", ["ed_admissions"], False),
        ("Emergency Department Waiting Times", "edw", ["ed_waits", "ed_triage"], False),
        ("Hospital Admissions", "hadm", ["hospital_admissions"], True),
        ("Hospital Outpatient Appointments", "hout", ["outpatient_appointments"], False),
        ("Hospital Elective Surgery Waitlist", "hesw", ["elective_waitlist", "elective_removals"], False),
    ]),
    ("health-community", "Department of Health - Community", [
        ("Community Mental Health Contacts", "cmh", ["mental_health_contacts"], False),
        ("Community Mental Health Admissions", "cmha", ["mental_health_admissions"], True),
        ("Community Pharmacy Dispensing", "phd", ["pharmacy_dispensing"], False),
        ("Community Immunisation Register", "imm", ["immunisations", "immunisation_providers"], False),
        ("Community Dental Services", "dent", ["dental_visits"], False),
    ]),
    ("education", "Department of Education", [
        ("School Enrolments", "senr", ["school_enrolments"], True),
        ("School Attendance", "satt", ["school_attendance"], False),
        ("School Suspensions and Exclusions", "ssus", ["suspensions", "exclusions"], False),
        ("School Census Staffing", "sstf", ["school_staff"], False),
        ("Early Childhood Education Places", "ecep", ["ec_places"], False),
        ("Early Childhood Education Attendance", "ecea", ["ec_attendance"], True),
    ]),
    ("justice", "Department of Justice", [
        ("Court Lodgements", "clod", ["court_lodgements"], False),
        ("Court Finalisations", "cfin", ["court_finalisations", "court_outcomes"], False),
        ("Corrective Services Receptions", "csr", ["prison_receptions"], True),
        ("Corrective Services Community Orders", "csco", ["community_orders"], False),
        ("Youth Justice Detentions", "yjd", ["youth_detentions"], False),
    ]),
    ("communities", "Department of Communities", [
        ("Housing Applications", "happ", ["housing_applications"], False),
        ("Housing Tenancies", "hten", ["housing_tenancies", "tenancy_transfers"], True),
        ("Homelessness Services Support Periods", "hssp", ["support_periods"], False),
        ("Homelessness Services Turnaways", "hstw", ["turnaways"], False),
        ("Disability Services Plans", "dsp", ["disability_plans"], False),
        ("Disability Services Payments", "dspy", ["disability_payments"], False),
    ]),
]


def _module(collection_id: str) -> str:
    return collection_id.replace("-", "_")


def _id(name: str) -> str:
    return name.lower().replace(" and ", " ").replace(" - ", " ").replace(" ", "-")


def added() -> list[dict]:
    """Every added collection, flattened, in hierarchy order."""
    out = []
    for agency_id, agency_name, colls in AGENCIES:
        for name, short, tables, trial in colls:
            cid = _id(name)
            out.append({"agency_id": agency_id, "agency_name": agency_name, "id": cid,
                        "name": name, "short": short, "tables": tables, "trial": trial})
    return out


def build(dest: Path) -> Path:
    """Copy the tracked tree into `dest` and register the twenty-eight more."""
    copy_tracked_tree(dest)
    hierarchy_path = dest / "contract" / "data-asset.yaml"
    doc = yaml.safe_load(hierarchy_path.read_text())
    agencies = doc["hierarchy"]["agencies"]
    seed = 2_000_000
    for agency_id, agency_name, colls in AGENCIES:
        entries = []
        for name, short, tables, trial in colls:
            cid = _id(name)
            datasets = [{"id": t.replace("_", "-"), "name": t.replace("_", " ").title(), "table": t,
                         "arrival_pattern": rf"{t}[^/]*\.csv"} for t in tables]
            if len(tables) == 1:
                datasets[0]["name"] = name
            entries.append({"id": cid, "name": name, "short": short, "run_prefix": f"{short}_run_",
                            "contract": f"{agency_id}/{cid}-contract.yaml",
                            "delivery_boundary": "directory", "datasets": datasets})
            module = _module(cid)
            (dest / "qa_tools" / "collections" / f"{module}.py").write_text(
                "from qa_tools.collections.base import CollectionAdapter\n\n"
                f"ADAPTER = CollectionAdapter(collection_id={cid!r}, label={name!r})\n")
            if short.endswith("w") or short.endswith("s"):
                continue  # a collection with no synthetic generator, as a real one has
            first = datasets[0]["id"]
            (dest / "generator" / "collections" / f"{module}.py").write_text(
                "from generator.collections.base import Plan, Provider\n\n\n"
                "class _Fixture(Provider):\n"
                f"    collection_id = {cid!r}\n"
                f"    dataset_id = {first!r}\n"
                f"    seed_ranges = (({seed}, {seed + 1000}),)\n"
                f"    target_trial = {trial!r}\n"
                f"    target_datasets = ({first!r},) if {trial!r} else ()\n\n"
                "    def seed_schedule(self):\n"
                f"        return [('the fixture', {seed + 1}, {seed + 2})]\n\n"
                "    def generated_periods(self):\n"
                "        return []\n\n"
                "    def plan(self):\n"
                "        return Plan(jobs=[])\n\n\n"
                "PROVIDER = _Fixture()\n")
            seed += 1000
        agencies.append({"id": agency_id, "name": agency_name,
                         "short": agency_id.replace("-", "")[:8], "collections": entries})
    hierarchy_path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return dest
