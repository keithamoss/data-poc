"""A one-file run records only what it is FOR (REQ-PIPE-105 criterion
11; Keith, 2026-10-02: "own + readers").

The overlay lets a run read its whole period, so the tools evaluate every
sibling's checks too. Recording them would QA each supply once per sibling
- six copies per Child Protection delivery. What survives is the run's own
dataset's checks, plus the cross-table checks that declare they read its
table; and where its own table is contested, only the second.
"""
from __future__ import annotations

import pytest

from qa_tools.common import qa_results_writer as writer
from qa_tools.common import supply_db

PLACEMENTS_FK = "x.cp-placements.cp_client_id.relationships_dbt"
CLIENTS_OWN = "x.cp-clients.cp_client_id.unique_dbt"
CARERS_OWN = "x.cp-carers.carer_id.unique_dbt"
RUN = "cp_clients__202605010100000000"


@pytest.fixture
def scoped(monkeypatch):
    monkeypatch.setattr(writer, "_declared_reads_tables",
                        lambda: {PLACEMENTS_FK: ["cp_clients"]})

    def contested(ambiguous: dict):
        res = supply_db.Resolution(run_id=RUN, schema="s", ambiguous=ambiguous)
        monkeypatch.setattr(supply_db, "resolution_for", lambda conn, run_id: res)
        monkeypatch.setattr(supply_db, "connect", lambda **kw: _Closeable())

    contested({})
    return contested


class _Closeable:
    def close(self):
        pass


def _records():
    return [{"dataset_id": "cp-clients", "check_id": CLIENTS_OWN},
            {"dataset_id": "cp-placements", "check_id": PLACEMENTS_FK},
            {"dataset_id": "cp-carers", "check_id": CARERS_OWN}]


def test_own_checks_and_readers_survive_and_siblings_do_not(scoped):
    records = _records()
    writer._scope_to_run(records, RUN)
    assert [r["check_id"] for r in records] == [CLIENTS_OWN, PLACEMENTS_FK]


def test_it_filters_the_callers_own_list_in_place(scoped):
    """Every tool returns the list it passed the writer, and the
    orchestrator writes reports/results_*.json from that - a filtered
    copy recorded and an unfiltered one returned would be two answers."""
    records = _records()
    same = records
    writer._scope_to_run(records, RUN)
    assert same is records and len(same) == 2


def test_a_contested_own_table_keeps_only_its_readers(scoped):
    """REQ-PIPE-079 criterion 13: its view fell through to the period's
    promoted version, so its own checks would report on data this
    supplier did not send."""
    scoped({"cp_clients": ["cp_clients__a", "cp_clients__b"]})
    records = _records()
    writer._scope_to_run(records, RUN)
    assert [r["check_id"] for r in records] == [PLACEMENTS_FK]


@pytest.mark.parametrize("run_id", ["trial_20261002t010203", "cp_held_abc", "run_001"])
def test_a_run_that_names_no_table_is_not_scoped(scoped, run_id):
    """A trial checks a whole folder under one id and is never filed, so
    it keeps every result - as does any id this project did not mint
    from a staged table."""
    records = _records()
    writer._scope_to_run(records, run_id)
    assert len(records) == 3


def test_the_owner_is_read_off_the_run_id():
    assert writer.run_owner(RUN) == ("cp-clients", "cp_clients")
    assert writer.run_owner("birth_registrations__202601010600000000") == (
        "birth-registrations", "birth_registrations")
    assert writer.run_owner("trial_20261002t010203") is None


def test_a_sibling_check_kept_for_reading_this_table_names_this_arrival(scoped):
    """REQ-PIPE-079 criteria 6 and 7: a re-evaluated result says which
    arrival caused it; the run's own checks are not re-evaluations."""
    from qa_tools.common import reevaluation

    records = _records()
    writer._scope_to_run(records, RUN)
    by_id = {r["check_id"]: r for r in records}
    assert by_id[PLACEMENTS_FK][reevaluation.CAUSED_BY] == RUN
    assert reevaluation.CAUSED_BY not in by_id[CLIENTS_OWN]
