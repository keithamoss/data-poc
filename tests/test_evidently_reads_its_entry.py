"""REQ-QAC-223 criterion 3 (post-build-review #182): each drift check's
column is read from its CHECK_LIFECYCLE entry - both the run's own rows
and the recorded reference - so the entry is the one place it is said.

Confirmed failing first: BDM read `sex` and CP a module constant
`_COLUMN`, whatever the entry said."""

import contextlib

import pytest

from qa_tools.bdm import run_evidently_bdm
from qa_tools.common import evidently_common, supply_db
from qa_tools.cp import run_evidently_cp


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


@pytest.mark.parametrize("module", [run_evidently_bdm, run_evidently_cp])
def test_the_runs_rows_are_read_from_the_entrys_column(module, fake_db, monkeypatch):
    monkeypatch.setitem(module._PSI, "column", "some_other_column")
    frame = module._current_frame("run_x")
    assert any("SELECT some_other_column FROM" in sql for sql in fake_db)
    assert list(frame.columns) == ["some_other_column"]


@pytest.mark.parametrize("module", [run_evidently_bdm, run_evidently_cp])
def test_the_reference_is_looked_up_by_the_entrys_column(module, monkeypatch):
    asked = []

    def counts(agency, collection, run_id, column):
        asked.append(column)
        return [["a", 3], ["b", 1]]

    monkeypatch.setattr(evidently_common, "reference_value_counts", counts)
    monkeypatch.setitem(module._PSI, "column", "some_other_column")
    frame = module._reference_frame("ref_run")
    assert asked == ["some_other_column"]
    assert list(frame.columns) == ["some_other_column"]
