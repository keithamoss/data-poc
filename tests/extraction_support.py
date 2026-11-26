"""A synthetic extraction package in a temporary folder, for REQ-PIPE-439 and
REQ-PIPE-440's tests. Not REQ-TEST-437's committed fixture package."""
from __future__ import annotations

import copy
import json
from pathlib import Path

AGENCY = {"id": "health-agency", "name": "Health Agency"}
COLLECTION = {"id": "cohort-study", "name": "Cohort Study"}

RECIPE = {
    "recipe_format_version": 1,
    "extraction_id": "cohort-2026-a",
    "project": "The 2026 cohort study",
    "filter": "Everyone first seen between 2020 and 2024; DROP TABLE nothing;",
    "tables": [
        {"file": "people.csv", "format": "csv", "agency": AGENCY, "collection": COLLECTION,
         "dataset": {"id": "cohort-people", "name": "People", "table": "cohort_people"},
         "derived": False,
         "columns": [{"name": "person_id", "type": "string", "primary_identifier": True},
                     {"name": "first_seen", "type": "date", "primary_identifier": False}],
         "cohort": [{"column": "first_seen", "lower": "2020-01-01", "upper": "2024-12-31"}],
         "expected_rows": 3},
        {"file": "visits.csv", "format": "csv", "agency": AGENCY, "collection": COLLECTION,
         "dataset": {"id": "cohort-visits", "name": "Visits", "table": "cohort_visits"},
         "derived": True,
         "columns": [{"name": "visit_id", "type": "string", "primary_identifier": True},
                     {"name": "person_id", "type": "string", "primary_identifier": False},
                     {"name": "cost", "type": "number", "primary_identifier": False}],
         "cohort": []},
    ],
}


def recipe(**changes) -> dict:
    doc = copy.deepcopy(RECIPE)
    doc.update(changes)
    return doc


def package(root: Path, doc: dict | None = None, *, files=("people.csv", "visits.csv"),
            raw: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "recipe.json").write_text(raw if raw is not None else json.dumps(doc or RECIPE))
    for name in files:
        (root / name).write_text("a\n1\n")
    return root
