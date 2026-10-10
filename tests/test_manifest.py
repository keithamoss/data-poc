"""Every period schema carries a `_manifest` view saying what each table is
and how it got there (REQ-PIPE-130). Against a real database; each test
mints its own period."""
from __future__ import annotations

import uuid

import pytest

import test_supersession as _base
from qa_tools.common import (amber_setting, decision_log as dl, period_schema, promotion,
                             substitution, supply_db)
from qa_tools.common.validate_hierarchy import reserved_table_errors
from test_supersession import DS, REAL_PERSON, TABLE, WHEN, _filed

conn = _base.conn
period = _base.period

AG, COL = "child-protection-family-support", "child-protection"
COLUMNS = ["table_name", "dataset_id", "kind", "supply", "received_at", "from_period",
           "decided_at", "decided_by", "acknowledged", "reason", "promoted_status"]


def _promote(conn, supply, table, period, *, kind=dl.RULE, status=None, amber=None):
    promotion.promote(conn, agency_id=AG, collection_id=COL, dataset_id=DS, supply=supply,
                      period=period, physical_tables=[table],
                      actor="promotion rule" if kind == dl.RULE else REAL_PERSON,
                      actor_kind=kind, effective_at=WHEN, reason="because", status=status,
                      amber=amber)


def _manifest(conn, period):
    cur = conn.execute(f'SELECT * FROM "{period_schema.period_schema(period)}"._manifest')
    return [dict(zip([d.name for d in cur.description], row)) for row in cur.fetchall()]


class TestOneRowPerObjectPresent:
    """Criteria 1, 2, 3 and 4."""

    def test_a_promoted_table_says_what_it_is_and_where_it_came_from(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, status="green")
        (row,) = _manifest(conn, period)
        assert list(row) == COLUMNS
        assert (row["table_name"], row["dataset_id"], row["kind"], row["supply"]) == (
            TABLE, DS, "promoted", a)
        assert row["received_at"].isoformat() == "2026-05-01T01:00:00+00:00"
        assert row["from_period"] is None and row["decided_by"] == "rule"
        assert row["promoted_status"] == "green" and row["acknowledged"] is None

    def test_an_object_no_decision_put_there_is_still_listed(self, conn, period):
        schema = period_schema.ensure_period_schema(conn, period)
        conn.execute(f'CREATE TABLE "{schema}".somebody_elses (id int)')
        rows = _manifest(conn, period)
        assert [(r["table_name"], r["kind"]) for r in rows] == [("somebody_elses", None)]

    def test_a_period_opened_by_instruction_has_one_too(self, conn, period):
        period_schema.open_period(conn, period, opened_by=REAL_PERSON, effective_at=WHEN)
        assert _manifest(conn, period) == []


class TestWhoNeverWhoseName:
    """Criterion 5, and criterion 11 for a person's promotion."""

    def test_a_person_is_a_person_and_never_named(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, kind=dl.PERSON)
        (row,) = _manifest(conn, period)
        assert row["decided_by"] == "person"
        assert not any(REAL_PERSON in str(v) for v in row.values())


class TestStandingOnAnotherPeriod:
    """Criteria 3 and 4: an inherited or substituted table names the period
    it stands on, and the status the supply it stands on was promoted on."""

    def test_a_substituted_table(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, status="amber")
        later = f"2099-L{uuid.uuid4().hex[:6]}"
        substitution.substitute(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                                logical_table=TABLE, period=later, stands_on=period,
                                supply=a, actor=REAL_PERSON, reason="late",
                                effective_at=WHEN)
        (row,) = _manifest(conn, later)
        assert (row["kind"], row["supply"], row["from_period"], row["promoted_status"]) == (
            "substituted", a, period, "amber")
        assert row["decided_by"] == "person" and row["reason"] == "late"


class TestAcknowledged:
    """Criterion 6."""

    def test_owed_then_given(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        owed = amber_setting.Resolved(value=amber_setting.PROMOTE_AND_ACKNOWLEDGE,
                                      level=amber_setting.ASSET, version="2023-01-01")
        _promote(conn, a, a_table, period, status="amber", amber=owed)
        assert _manifest(conn, period)[0]["acknowledged"] is False
        with conn.raw.transaction():
            with dl.apply_decision(conn, dl.Decision(
                    agency_id=AG, collection_id=COL, dataset_id=DS, action=dl.ACKNOWLEDGE,
                    supply=a, actor=REAL_PERSON, actor_kind=dl.PERSON, effective_at=WHEN,
                    to_slot=period, reason="looked")):
                pass
        assert _manifest(conn, period)[0]["acknowledged"] is True


class TestTheLogCarriesWhatTheManifestReads:
    """Criteria 10 and 11."""

    def test_every_entry_names_its_table_and_a_promotion_its_status(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, status="red")
        (name, status) = conn.execute(
            f"SELECT table_name, promoted_status FROM {dl.TABLE} WHERE dataset_id = ? "
            "AND supply = ? AND action = 'promote'", [DS, a]).fetchall()[0]
        assert (name, status) == (TABLE, "red")

    def test_a_persons_promotion_reads_the_recorded_status(self, conn, period, monkeypatch):
        from qa_tools.common import supply_status

        monkeypatch.setattr(supply_status, "status", lambda c, d, s, **k: "amber")
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, kind=dl.PERSON)
        assert _manifest(conn, period)[0]["promoted_status"] == "amber"


class TestLeastPrivilege:
    """NFR 2: a reader granted the period schema alone reads _manifest."""

    def test_a_period_only_reader(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, status="green")
        schema = period_schema.period_schema(period)
        role = f"pytest_reader_{uuid.uuid4().hex[:8]}"
        conn.execute(f'CREATE ROLE "{role}"')
        try:
            conn.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"')
            conn.execute(f'GRANT SELECT ON "{schema}"._manifest TO "{role}"')
            with conn.raw.transaction():
                conn.execute(f'SET LOCAL ROLE "{role}"')
                rows = conn.execute(f'SELECT supply FROM "{schema}"._manifest').fetchall()
                assert rows == [(a,)]
        finally:
            conn.execute(f'DROP OWNED BY "{role}"')
            conn.execute(f'DROP ROLE "{role}"')


class TestTheNameIsReserved:
    """Criterion 13."""

    def test_a_dataset_table_named_manifest_is_refused(self):
        assert reserved_table_errors([("x", "_manifest")])
        assert reserved_table_errors([("x", "cp_carers")]) == []


class TestTheCensusIgnoresIt:
    def test_the_manifest_is_not_a_stray(self, conn, period):
        from qa_tools.common import census

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, status="green")
        assert [d for d in census.compare(conn, periods=[period])] == []


@pytest.mark.needs_deployment
class TestParityWithThePipeline:
    """NFR 1: for every period of the bootstrapped deployment, _manifest
    agrees with what the pipeline itself resolves that period to."""

    def test_every_period(self, deployment_history):
        from qa_tools.common import hierarchy

        with supply_db.connect(read_only=True, label="test-manifest-parity") as conn:
            # BY AUTHORED NAME, from the record of each period's opening:
            # period_schemas() answers from schema names, and a schema name
            # is the authored one encoded (2023-Q1 -> 2023_q1).
            periods = [r[0] for r in conn.execute(
                "SELECT name FROM qa.period ORDER BY name").fetchall()]
            assert periods, "the deployment has no opened periods - bootstrap first"
            for p in periods:
                rows = {r["table_name"]: r for r in _manifest(conn, p)}
                for d in hierarchy.all_datasets():
                    h = dl.held(conn, d.dataset_id, p)
                    row = rows.get(d.table)
                    if h and h.held_as:
                        assert row is not None, (p, d.table)
                        assert (row["kind"], row["supply"]) == (h.held_as, h.holder), (p, d.table)
                    else:
                        assert row is None or row["kind"] is None, (p, d.table)


class TestTheDefinersSearchPathIsSafe:
    """post-build-review #116 D5: SECURITY DEFINER with search_path =
    pg_catalog alone searches pg_temp FIRST, so a caller's temporary pg_class
    could spoof the listing. pg_temp must come last."""

    def test_it(self, conn):
        (config,) = conn.execute(
            "SELECT proconfig FROM pg_proc WHERE proname = 'manifest_for'").fetchall()[0]
        assert any(c.replace(" ", "") == "search_path=pg_catalog,pg_temp" for c in config), config
