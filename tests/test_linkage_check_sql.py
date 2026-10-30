"""The Linkage Keys check SQL holds whatever type staging infers for an id.

REQ-QAC-330 criterion 3 and REQ-QAC-333 criterion 3: every id column is
compared as TEXT whatever the source column's type. Staging infers a column's
type from the file (qa_tools/common/supply_db.py), so a linkage file whose
id_1 holds only digits stages it as a number - and the referential, coverage,
expected-identifiers and no-surplus queries must still run, with the same
answers as for the alphanumeric identifiers the synthetic history carries.

These run the REAL queries out of the committed check file, against
temporary tables, so a query edited in the file is the query tested.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from qa_tools.common import supply_db

CHECKS = (Path(__file__).resolve().parent.parent / "contract" / "department-of-health"
          / "linkage-products-soda-checks.yml")


def _queries() -> dict[str, str]:
    """check_id tail -> the SQL Soda runs for it."""
    doc = yaml.safe_load(CHECKS.read_text())
    out: dict[str, str] = {}
    for key, body in doc.items():
        if not key.startswith("checks for"):
            continue
        for entry in body:
            (head, spec), = entry.items()
            if not isinstance(spec, dict):
                continue
            tail = spec.get("attributes", {}).get("check_id", "").rsplit(".", 2)
            tail = ".".join(tail[-2:])
            if "fail query" in spec:
                out[tail] = spec["fail query"]
            elif f"{head} query" in spec:
                out[tail] = spec[f"{head} query"]
    return out


QUERIES = _queries()
KINDS = ("id_1.expected_ids_soda", "id_1.no_surplus_ids_soda",
         "cp-clients.referential_soda", "cp-clients.coverage_soda",
         "ed-presentations.referential_soda", "ed-presentations.coverage_soda")


def test_every_kind_is_found_in_the_file():
    assert set(KINDS) <= set(QUERIES), sorted(QUERIES)


def _load(conn, id_type: str, source_type: str, ids: list, sources: list) -> None:
    conn.execute(f"CREATE TEMP TABLE linkage_keys (linkage_key text, dataset text,"
                 f" id_1 {id_type}, id_2 {id_type})")
    for code, i, j in ids:
        conn.execute("INSERT INTO linkage_keys VALUES ('k', ?, ?, ?)", (code, i, j))
    conn.execute(f"CREATE TEMP TABLE cp_clients (cp_client_id {source_type})")
    conn.execute(f"CREATE TEMP TABLE ed_presentations (presentation_id {source_type})")
    for s in sources:
        conn.execute("INSERT INTO cp_clients VALUES (?)", (s,))
        conn.execute("INSERT INTO ed_presentations VALUES (?)", (s,))


def _run(conn) -> dict[str, object]:
    out = {}
    for kind in KINDS:
        rows = conn.execute(QUERIES[kind]).fetchall()
        out[kind] = rows[0][0] if kind.endswith("coverage_soda") else len(rows)
    return out


EXPECTED = {
    # one row of each code carries a surplus id_2; one link (4) matches nothing
    "id_1.expected_ids_soda": 0,
    "id_1.no_surplus_ids_soda": 2,
    "cp-clients.referential_soda": 1,
    "ed-presentations.referential_soda": 1,
}


@pytest.mark.parametrize("id_type,source_type,ids,sources", [
    ("bigint", "bigint",
     [("DOC_CLIENTS", 1, None), ("DOC_CLIENTS", 2, 9), ("DOC_CLIENTS", 4, None),
      ("EDDC_PRESENTATION", 1, None), ("EDDC_PRESENTATION", 2, 9),
      ("EDDC_PRESENTATION", 4, None)],
     [1, 2, 3]),
    ("text", "text",
     [("DOC_CLIENTS", "A1", None), ("DOC_CLIENTS", "A2", "Z"), ("DOC_CLIENTS", "A4", ""),
      ("EDDC_PRESENTATION", "A1", None), ("EDDC_PRESENTATION", "A2", "Z"),
      ("EDDC_PRESENTATION", "A4", None)],
     ["A1", "A2", "A3"]),
], ids=["numeric-ids", "alphanumeric-ids"])
def test_the_four_kinds_run_whatever_the_staged_id_type(id_type, source_type, ids, sources):
    with supply_db.connect(label="test-linkage-sql") as conn:
        _load(conn, id_type, source_type, ids, sources)
        got = _run(conn)
    for kind, n in EXPECTED.items():
        assert got[kind] == n, (kind, got)
    for kind in ("cp-clients.coverage_soda", "ed-presentations.coverage_soda"):
        assert float(got[kind]) == pytest.approx(200 / 3), (kind, got)
