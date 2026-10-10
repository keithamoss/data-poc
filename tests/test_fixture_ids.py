"""Holds tests/fixture_ids.py's constants to what the real recogniser
actually assigns (REQ-GEN-043).

Those constants are literals, and a literal that encodes how something
else derives a value goes stale silently. When it did, the symptom was
a dozen `IO Error: Cannot open database ".../pytest_bdm_ref.duckdb"`
failures spread across six test modules, none of which named the actual
cause. This fails in one place, with the cause in the message.
"""
from __future__ import annotations

import fixture_ids

from qa_tools.common import arrivals


def test_bdm_fixture_run_ids_are_the_ones_recognition_actually_assigns(bdm_delivery_dirs):
    deliveries, receipts = bdm_delivery_dirs
    found = [a.run_id for a in arrivals.arrivals_for("civil-registration", "run_", deliveries, receipts)]
    assert found == [fixture_ids.BDM_REF_RUN_ID, fixture_ids.BDM_DIRTY_RUN_ID], (
        "tests/fixture_ids.py no longer matches what qa_tools.common.arrivals assigns to the "
        "BDM fixture's deliveries - update it there, not in each test module")


def test_cp_fixture_run_ids_are_the_ones_recognition_actually_assigns(cp_delivery_dirs):
    deliveries, receipts = cp_delivery_dirs
    found = [a.run_id for a in arrivals.arrivals_for("child-protection", "cp_run_", deliveries, receipts)]
    assert found == [*fixture_ids.CP_REF_RUN_IDS, *fixture_ids.CP_DIRTY_RUN_IDS], (
        "tests/fixture_ids.py no longer matches what qa_tools.common.arrivals assigns to the "
        "CP fixture's deliveries - update it there, not in each test module")


def test_recognised_run_ids_are_ordered_by_receipt_not_by_delivery_name(bdm_delivery_dirs):
    """The clean reference delivery is named "REF_20260101" and the
    dirty one "drop-9002" - alphabetically the wrong way round, on
    purpose. Receipt order is the only thing that may decide this."""
    deliveries, receipts = bdm_delivery_dirs
    found = arrivals.arrivals_for("civil-registration", "run_", deliveries, receipts)
    assert [a.delivery_name for a in found] == ["REF_20260101", "drop-9002"]
    assert [a.run_id for a in found] == [fixture_ids.BDM_REF_RUN_ID, fixture_ids.BDM_DIRTY_RUN_ID]
    assert found[0].received_at < found[1].received_at


def test_the_cp_reference_run_is_the_one_that_sees_the_whole_delivery(cp_duckdb_dir):
    """CP_REF_RUN_ID is not "the first file" or "any file" of the clean
    delivery: it is the run whose overlay reads all six clean tables
    (REQ-PIPE-105 criterion 5). Pinned here, against the real fixture,
    because a test passing against a run that silently reads one table
    is exactly the failure a wrong constant produces."""
    from qa_tools.common import supply_db

    with supply_db.connect(read_only=True) as conn:
        ref = supply_db.resolution_for(conn, fixture_ids.CP_REF_RUN_ID)
        dirty = supply_db.resolution_for(conn, fixture_ids.CP_DIRTY_RUN_ID)
    assert len(ref.resolved) == 6, ref.as_record()
    assert not ref.ambiguous, ref.ambiguous
    # Both deliveries are filed to periods of the fixture's own (see
    # conftest's _file_and_overlay_cp for why not through the assignment
    # rule), so the dirty delivery's last file reads all six dirty tables.
    assert len(dirty.resolved) == 6, dirty.as_record()
    assert not dirty.ambiguous, dirty.ambiguous
    assert all(p.endswith("__202604010600000000") for p in dirty.resolved.values()), \
        "the dirty run must read the DIRTY delivery's tables, not the reference ones"
