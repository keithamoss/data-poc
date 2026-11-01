"""REQ-DASH-299 criterion 17 and its decision (Keith, 2026-10-31, v7 round
(a)): 'notchecked' is DISPLAY ONLY - no tool may record it, and the results
store refuses a result carrying it, naming it, before anything is written.
A check that ran and errored stays Fail. Through qa_store.record_results,
the one writer of qa.check_result, against this worker's own database."""
from __future__ import annotations

import pytest

from attempt_support import ANY_CHECK
from qa_tools.common import qa_store, supply_db

WHEN = "2026-09-25T22:00:00+08:00"


@pytest.fixture
def conn(clean_qa_history):
    supply_db.ensure_schemas(clean_qa_history)
    yield clean_qa_history


def _run(conn, key):
    qa_store.record_run(conn, run_key=key, agency_id="a", collection_id="b", run_timestamp=WHEN)
    qa_store.set_run_purpose(conn, key, dataset_id="cp-clients", supply_id=None)


def _result(status):
    return {"check_id": "x.y", "check_name": "y", "dataset_id": "cp-clients", "status": status}


def test_a_result_recorded_notchecked_is_refused_and_nothing_lands(conn):
    _run(conn, "r299a")
    with pytest.raises(qa_store.DisplayOnlyStatus, match="notchecked"):
        qa_store.record_results(conn, "r299a", [_result("pass"), _result("notchecked")], tool="dbt",
                                agency_id="a", collection_id="b", fingerprints=ANY_CHECK)
    n = conn.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".check_result '
                     "WHERE run_key = 'r299a'").fetchone()[0]
    assert n == 0


def test_a_tool_error_is_still_recorded_as_one(conn):
    _run(conn, "r299b")
    assert qa_store.record_results(conn, "r299b", [_result("error")], tool="dbt",
                                   agency_id="a", collection_id="b", fingerprints=ANY_CHECK) == 1


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
