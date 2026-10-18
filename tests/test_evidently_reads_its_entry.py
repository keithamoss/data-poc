"""REQ-QAC-223 criterion 3 (post-build-review #182): each drift check's
column is read from its CHECK_LIFECYCLE entry - both the run's own rows
and the recorded reference - so the entry is the one place it is said.

Confirmed failing first: BDM read `sex` and CP a module constant
`_COLUMN`, whatever the entry said."""

import contextlib

import pytest

from qa_tools import collections
from qa_tools.common import evidently_common, supply_db
from qa_tools.tools import run_evidently

COLLECTIONS = ["civil-registration", "child-protection"]


def _entry(collection_id):
    """The collection's drift check entry, its column changed - as an edit to
    the check file would change it."""
    checks = evidently_common.collection_checks(collection_id)
    entry = dict(checks.checks[checks.psi[0]], column="some_other_column")
    return collections.by_id(collection_id), entry, checks.psi[0]


class _Conn:
    def __init__(self, seen):
        self.seen = seen

    def execute(self, sql, *a):
        self.seen.append(sql)
        return self

    def fetchall(self):
        return [("a",), ("b",)]


@pytest.fixture
def fake_db(monkeypatch):
    seen = []

    @contextlib.contextmanager
    def connect(**_):
        yield _Conn(seen)

    monkeypatch.setattr(supply_db, "connect", connect)
    monkeypatch.setattr(supply_db, "run_schema", lambda run_id: "s")
    return seen


@pytest.mark.parametrize("collection_id", COLLECTIONS)
def test_the_runs_rows_are_read_from_the_entrys_column(collection_id, fake_db, monkeypatch):
    coll, entry, check_id = _entry(collection_id)
    result = run_evidently._psi_result(coll, entry, check_id, run_evidently._table_of(check_id),
                                       "run_x", "2026-01-01T00:00:00Z", None)
    assert any("SELECT some_other_column FROM" in sql for sql in fake_db)
    assert result["column_name"] == "some_other_column"


@pytest.mark.parametrize("collection_id", COLLECTIONS)
def test_the_reference_is_looked_up_by_the_entrys_column(collection_id, fake_db, monkeypatch):
    asked = []

    def counts(agency, collection, run_id, column):
        asked.append(column)
        return [["a", 3], ["b", 1]]

    monkeypatch.setattr(run_evidently, "reference_value_counts", counts)
    coll, entry, check_id = _entry(collection_id)
    frame = run_evidently._reference_frame(coll, "ref_run", run_evidently._table_of(check_id),
                                           entry["column"])
    assert asked == ["some_other_column"]
    assert list(frame.columns) == ["some_other_column"]
