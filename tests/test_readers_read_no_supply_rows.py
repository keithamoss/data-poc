"""The dashboard build and the readers on its path read recorded QA
results and configuration - never supply rows, and never anything else.

THE RULE (CLAUDE.md, "CI ... must never depend on live data access"):
a build may read recorded QA results, never actual data. It used to be
held by thirteen source greps, one per module, each with its own word
list - "staging", "period_", "SELECT", "candidates_in" - which disagreed
about whether a docstring counts, and none of which could see SQL built
at run time (docs/test-review-pass2.md, B-CONSOLIDATE).

THIS RUNS THEM INSTEAD, as the role that holds the rule in production.
`qa_store.ensure_publisher_role` grants USAGE on the metadata schema and
nothing else, so every read of a staging, period, rejected or sample
schema is refused by PostgreSQL with InsufficientPrivilege, whatever the
spelling. The database is populated first, as the owner, with a small
real history AND real supply rows in a staging table and a period
schema, so a reader that reached for them would find something there.

A REFUSAL IS CAUGHT EVEN WHEN A READER SWALLOWS IT. Some readers turn a
failure into a softer answer on purpose - `agreement_drift.refusals()`
collects one dataset's error and moves on - so a raised exception alone
would let a forbidden read go green. Every statement executed while the
readers run is therefore observed at the driver: one refused statement
fails the test, and so does one issued by any role other than the
publisher (a reader that opened an owner connection of its own would
otherwise bypass the whole point).

One grep of the same rule is KEPT for now: `test_promotion_state.py::
TestItReadsRecordsAndNeverSupplyRows` is named in REQ-DASH-056's
`linked_tests`, and retiring it means editing that requirement.
promotion_state is exercised below all the same, through the build and
directly.

What is NOT here, because it is a different rule rather than a weaker
spelling of this one - each keeps its own test:
- `test_assignment.py`'s "never touches the warehouse": `assign()` takes
  no connection at all, so its rule is purity, including files;
- `test_scenario_map.py`'s "reads nothing under data/ except the record":
  a filesystem rule;
- `test_sample_data.py`'s "nothing that computes a period reads it":
  about owner-privileged period arithmetic, which this role cannot run;
- `test_recheck.py`'s "no build path imports the executor": an import
  rule about a writer, not a read;
- `test_period_schema.py`'s replay test, trimmed to its "re-runs no tool"
  half - replaying a recorded verdict rather than re-deriving it is not
  a privilege question.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
import yaml

import filing_support
import rebuild_support
from qa_tools.common import (agreement, assignment, asset_time, period_schema, qa_store,
                             supply_db)

PASSWORD = "readers-publisher-password"
PERTH = timezone(timedelta(hours=8))
DATASET = "cp-clients"
SLOT = "2023-Q3"
SUPPLY = "readers-s"
RECEIVED = datetime(2023, 8, 1, 12, tzinfo=PERTH)
AT = datetime(2026, 10, 11, tzinfo=timezone.utc)
BDM = "qa_tools.bdm.build_results_from_history"
CP = "qa_tools.cp.build_results_from_history"


def _record_history() -> None:
    """A finished run per collection, through the real writer, carrying
    the fields the dashboard build reads rather than the minimum the
    rebuild needs."""
    from qa_tools.common.qa_results_writer import finish_run, open_run, write_qa_result

    when = "2023-08-01T12:00:00+08:00"
    by = "tests@example.gov.au"
    for module, table in ((BDM, "birth_registrations"), (CP, "cp_clients")):
        agency, collection = rebuild_support.ids(module)
        run_id = f"readers_{module.split('.')[1]}_run_1"
        record = dict(rebuild_support.check(module, "id", "dbt"), **{
            "column_name": "(table)", "check_name": "dbt:row_count", "dimension": "volume",
            "label": "Row count", "metric_value": 1, "unit": "count",
            "warn_threshold": None, "fail_threshold": None, "row_count_total": 1,
            "row_count_invalid": 0, "run_id": run_id})
        open_run(agency, collection, run_id, when, by)
        write_qa_result(agency, collection, run_id, when, "dataset_stats", {
            "arrival_record": {"run_id": run_id, "run_index": 1, "delivery": "readers-delivery",
                               "received_at": when},
            "row_count": 1, "row_counts": {table: 1}, "value_counts": {},
            "check_aggregates": {}}, run_by=by)
        write_qa_result(agency, collection, run_id, when, "dbt", {}, verified=[record],
                        run_by=by)
        finish_run(run_id)


def _place_supply_rows(conn) -> None:
    """Real rows where the extract lives, so a forbidden read finds data
    rather than an empty name."""
    period = period_schema.period_schema(SLOT)
    for schema in (supply_db.STAGING_SCHEMA, period):
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        conn.execute(f'CREATE TABLE IF NOT EXISTS "{schema}".readers_probe '
                     "(id int, surname text)")
        conn.execute(f'INSERT INTO "{schema}".readers_probe VALUES (1, \'Citizen\')')


@pytest.fixture
def publisher(supply_dsn, worker_id, clean_qa_history, monkeypatch):
    """This worker's database with a small history, and every connection
    from here on made as the publisher role. Yields that role's own
    connection, for the readers that take one."""
    owner = clean_qa_history
    owner.execute(f'TRUNCATE "{qa_store.SCHEMA}".filing CASCADE')
    _record_history()
    filing_support.file(assignment.Assignment(
        dataset_id=DATASET, supply_id=SUPPLY, slot=SLOT, branch=assignment.OPEN_UNFILLED,
        considered=(SLOT,), received_at=RECEIVED))
    _place_supply_rows(owner)
    role = f"mothman_publisher_readers_{worker_id}"
    qa_store.ensure_publisher_role(owner, role, PASSWORD)

    fields = supply_db.connection_fields()
    dsn = (f"postgresql://{role}:{PASSWORD}@{fields['host']}:{fields['port']}"
           f"/{fields['dbname']}")
    monkeypatch.setenv(supply_db.SUPPLY_DSN_ENV, dsn)
    with supply_db.connect(read_only=True, label="test-readers-publisher") as conn:
        yield role, conn


@pytest.fixture
def statements(publisher, monkeypatch):
    """Every statement executed from here on: (role, sql, refused)."""
    seen: list[tuple[str, str, bool]] = []
    original = psycopg.Cursor.execute

    def observed(self, query, *args, **kwargs):
        sql = query if isinstance(query, str) else repr(query)
        try:
            result = original(self, query, *args, **kwargs)
        except psycopg.errors.InsufficientPrivilege:
            seen.append((self.connection.info.user, sql, True))
            raise
        seen.append((self.connection.info.user, sql, False))
        return result

    monkeypatch.setattr(psycopg.Cursor, "execute", observed)
    return seen


def _assert_only_the_publisher_read(role: str, seen: list) -> None:
    assert seen, "nothing was read - the readers did not run against the database"
    refused = [sql for _, sql, was in seen if was]
    assert not refused, (
        "a reader on the build path was refused - it reached beyond recorded "
        f"QA results: {refused}")
    others = {user for user, _, _ in seen} - {role}
    assert not others, f"a reader connected as {others} rather than the publisher"


def _docs():
    """The committed agreement and asset, with no corrections declared."""
    # THE CONFIGURATION AS IT STOOD BEFORE REQ-GEN-207's GROWTH: these cases
    # edit the version that governs the judged supplies (tests/before_growth.py).
    from tests import before_growth

    cal = before_growth.calendar(copy.deepcopy(yaml.safe_load(agreement.CALENDAR_YAML.read_text())))
    asset = before_growth.asset(copy.deepcopy(yaml.safe_load(asset_time.DATA_ASSET_YAML.read_text())))
    for owner in (cal.get("calendars") or []) + (cal.get("datasets") or []) \
            + (cal.get("collections") or []):
        owner.pop("corrections", None)
    return cal, asset


def _grace_one_hour(cal) -> None:
    """A correction that re-judges the filed supply, so the re-judgement
    and trial paths do real work rather than returning early."""
    entry = next(d for d in cal["datasets"] if d["id"] == DATASET)
    entry["participation"]["versions"] = copy.deepcopy(entry["participation"]["versions"])
    entry["participation"]["versions"][0]["grace"] = "1h"


class TestTheDashboardBuild:
    """`mothman dashboard rebuild-results` then `build-data`, both
    collections. On its way it runs agreement_drift, slot_timeline,
    corrections (with verdict and correction_trial behind it),
    promotion_state, acknowledgements and closed_slots."""

    def test_it_builds_as_the_publisher(self, publisher, statements, tmp_path, monkeypatch):
        from pipeline import build_cp_dashboard_data, build_dashboard_data

        role, _ = publisher
        for module_name, builder, reads in ((BDM, build_dashboard_data, "REAL_RESULTS_PATH"),
                                            (CP, build_cp_dashboard_data, "RESULTS_PATH")):
            module = __import__(module_name, fromlist=["_"])
            results = tmp_path / f"{module_name.split('.')[1]}.json"
            monkeypatch.setattr(module, "RESULTS_PATH", str(results))
            module.build_results_from_history()
            monkeypatch.setattr(builder, reads, str(results))
            assert builder.build(), f"{builder.__name__} built nothing"
        _assert_only_the_publisher_read(role, statements)


class TestEachReaderOnItsOwnEntryPoint:
    """The readers the build reaches only on some data, called directly.
    Read paths only: each module's writes (recording a re-judgement,
    applying a correction) are the owner's, and are not under test."""

    def test_outstanding(self, publisher, statements):
        from qa_tools.common import outstanding

        role, conn = publisher
        outstanding.survey(conn)
        _assert_only_the_publisher_read(role, statements)

    def test_agreement_drift(self, publisher, statements):
        from qa_tools.common import agreement_drift

        role, conn = publisher
        errors: list = []
        agreement_drift.refusals(conn, errors=errors)
        assert not errors, errors
        _assert_only_the_publisher_read(role, statements)

    def test_verdict_re_judgement(self, publisher, statements):
        from qa_tools.common import verdict

        role, conn = publisher
        cal, _ = _docs()
        _grace_one_hour(cal)
        corrected = agreement.from_doc(cal)
        assert verdict.rejudged(conn, DATASET, corrected), "nothing was re-judged"
        verdict.compared(conn, DATASET, corrected)
        _assert_only_the_publisher_read(role, statements)

    def test_correction_trial(self, publisher, statements):
        from qa_tools.common import correction_trial

        role, conn = publisher
        cal, asset = _docs()
        _grace_one_hour(cal)
        trial = correction_trial.trial(conn, _docs(), (cal, asset), at=AT,
                                       dataset_ids=[DATASET])
        assert trial.verdicts, "the trial computed nothing"
        correction_trial.declared(conn)
        _assert_only_the_publisher_read(role, statements)

    def test_dashboard_corrections_and_slot_timeline(self, publisher, statements):
        from pipeline import corrections, slot_timeline
        from qa_tools.common import promotion_state

        role, conn = publisher
        corrections.for_dataset(DATASET, conn)
        corrections.applied_feed(conn)
        timeline = slot_timeline.for_dataset(DATASET, conn)
        slot_timeline.with_runs(timeline, DATASET, conn)
        slot_timeline.supply_states(DATASET, conn)
        slot_timeline.run_states(DATASET, conn)
        promotion_state.state_for(DATASET, conn)
        _assert_only_the_publisher_read(role, statements)
