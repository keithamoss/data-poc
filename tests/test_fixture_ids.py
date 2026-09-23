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
    assert found == [fixture_ids.CP_REF_RUN_ID, fixture_ids.CP_DIRTY_RUN_ID], (
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
