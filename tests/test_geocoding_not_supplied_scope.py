"""REQ-QAC-340 criterion 8's second half for the GEOCODING checks: where a
person has marked the source not supplied for the period, the geocoding
supply's checks of that source are left out of scope (REQ-PIPE-332
criterion 7), never red.

The generated history never holds the case - Client Register is marked not
supplied only in 2015-Q2 to Q4, where its geocodes are marked not supplied
too (evidence walk-through [18], 2026-11-14) - so Keith chose a test rather
than a planted scenario. It drives the run step's own scope decision
(unrunnable.out_of_agreement, which orchestrate._out_of_agreement calls)
with the REAL declarations of the quarterly asset's geocoding checks and a
REAL not-supplied mark recorded in a private database."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.asset("quarterly")

PERIOD = "2020-Q2"
SOURCE, SOURCE_TABLE = "cp-clients", "cp_clients"
GEO, GEO_TABLE = "geo-cp-clients", "geo_cp_clients"


def _scope(mark: bool):
    from qa_tools.common import not_supplied, qa_store, supply_db, tables_read, unrunnable

    now = datetime.now(timezone.utc)
    with supply_db.connect(label="pytest-geo-scope") as conn:
        supply_db.ensure_schemas(conn)
        qa_store.ensure_schema(conn)
        if mark:
            not_supplied.mark(conn, agency_id="child-protection-family-support",
                              collection_id="child-protection", dataset_id=SOURCE,
                              period=PERIOD, actor="fixture@example.org",
                              reason="the supplier confirmed there was nothing",
                              effective_at=now.isoformat())
        reads = tables_read.declared_reads()
        resolution = supply_db.Resolution(run_id="geo_cp_clients__test", schema="run_test",
                                         resolved={GEO_TABLE: GEO_TABLE}, absent=[SOURCE_TABLE])
        out = unrunnable.out_of_agreement(
            conn, own_table=GEO_TABLE, own_dataset=GEO, period=PERIOD,
            resolution=resolution, reads=reads, as_at=now)
    readers = sorted(c for c, tables in reads.items()
                     if f".{GEO}." in c and SOURCE_TABLE in tables)
    return readers, out


def test_a_marked_source_leaves_its_geocoding_checks_out_of_scope(private_supply_dsn):
    from qa_tools.common import unrunnable

    readers, out = _scope(mark=True)
    assert len(readers) >= 2, "the geocoding checks of the Client Register are declared"
    assert set(readers) <= set(out), sorted(set(readers) - set(out))
    for check in readers:
        assert out[check]["code"] == unrunnable.NOT_SUPPLIED_BY_DECISION, (check, out[check])
        assert out[check]["reason"] == f"not supplied for {PERIOD}, by decision"


def test_without_the_mark_they_stay_in_scope(private_supply_dsn):
    """The control that makes the first test able to fail: an owed source
    that simply has not arrived is not left out - it reads red, could not
    run (REQ-PIPE-270)."""
    readers, out = _scope(mark=False)
    assert readers
    assert not set(readers) & set(out), sorted(set(readers) & set(out))
