"""Tables in a period schema take plain base names (REQ-PIPE-129).
Against a real database; each test mints its own periods."""
from __future__ import annotations

from contextlib import contextmanager

import pytest

import test_supersession as _base
from qa_tools.common import decision_log as dl, period_schema, promotion, rejection, supply_db
from test_supersession import DS, REAL_PERSON, TABLE, WHEN, _filed

conn = _base.conn
period = _base.period

AG, COL = "child-protection-family-support", "child-protection"


def _tables_in(conn, schema):
    return sorted(r[0] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = ? "
        "AND table_name <> '_manifest'",  # a period's own account (REQ-PIPE-130)
        [schema]).fetchall())


@contextmanager
def _guard_disabled(conn):
    """The database guard switched off for one block, so a test can prove
    another guard refuses on its own (criterion 12) or that a missing
    guard is reported (criterion 18)."""
    from qa_tools.common import period_tables

    present = period_tables.guard_installed(conn)
    if present:
        conn.execute(f"ALTER EVENT TRIGGER {period_tables.GUARD_TRIGGER} DISABLE")
        conn.execute(f"ALTER EVENT TRIGGER {period_tables.DROP_GUARD_TRIGGER} DISABLE")
    try:
        yield
    finally:
        if present:
            conn.execute(f"ALTER EVENT TRIGGER {period_tables.GUARD_TRIGGER} ENABLE")
            conn.execute(f"ALTER EVENT TRIGGER {period_tables.DROP_GUARD_TRIGGER} ENABLE")


def _promote(conn, supply, table, period, kind=dl.RULE):
    promotion.promote(conn, agency_id=AG, collection_id=COL, dataset_id=DS, supply=supply,
                      period=period, physical_tables=[table], actor="promotion rule"
                      if kind == dl.RULE else REAL_PERSON, actor_kind=kind,
                      effective_at=WHEN, reason="because")


class TestAPromotedTableTakesItsBaseName:
    """Criteria 1 and 2."""

    def test_promoted_is_named_cp_carers(self, conn, period):
        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, supply, table, period)
        assert _tables_in(conn, period_schema.period_schema(period)) == [TABLE]


class TestLeavingRestoresTheStampedName:
    """Criteria 3, 4 and 6: superseded, demoted and rejected each get the
    full stamped name back, rebuilt from the decision log."""

    def test_demoted_back_to_staging_stamped(self, conn, period):
        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, supply, table, period)
        rejection.demote(conn, agency_id=AG, collection_id=COL, dataset_id=DS, supply=supply,
                         physical_tables=[table], actor=REAL_PERSON, effective_at=WHEN,
                         reason="not yet", from_slot=period)
        assert table in _tables_in(conn, supply_db.STAGING_SCHEMA)
        assert _tables_in(conn, period_schema.period_schema(period)) == []

    def test_rejected_out_of_the_period_stamped(self, conn, period):
        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, supply, table, period)
        rejection.reject(conn, agency_id=AG, collection_id=COL, dataset_id=DS, supply=supply,
                         physical_tables=[table], actor=REAL_PERSON, effective_at=WHEN,
                         reason="wrong file", from_slot=period, promoted=True)
        assert table in _tables_in(conn, supply_db.REJECTED_SCHEMA)

    def test_superseded_by_a_promotion_stamped(self, conn, period):
        from qa_tools.common import supersession

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        b, b_table = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _promote(conn, b, b_table, period, kind=dl.PERSON)
        assert a_table in _tables_in(conn, supersession.superseded_schema(period))
        assert _tables_in(conn, period_schema.period_schema(period)) == [TABLE]


class TestADependentViewBlocksAMove:
    """Criteria 9, 10 and 12: each refusal on its own."""

    def _with_a_view_on(self, conn, period):
        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, supply, table, period)
        other = period_schema.period_schema(period + "x")
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{other}"')
        conn.execute(f'CREATE VIEW "{other}"."{TABLE}" AS SELECT * FROM '
                     f'"{period_schema.period_schema(period)}"."{TABLE}"')
        return supply, table, other

    def test_the_code_path_refuses_naming_the_view(self, conn, period):
        from qa_tools.common import period_tables

        supply, table, other = self._with_a_view_on(conn, period)
        with _guard_disabled(conn):
            with pytest.raises(period_tables.DependentView, match=other):
                with conn.raw.transaction():
                    period_tables.take_out(conn, period=period, logical=TABLE, supply=supply,
                                           to_schema=supply_db.STAGING_SCHEMA)

    def test_the_database_guard_refuses_on_its_own(self, conn, period):
        import psycopg

        from qa_tools.common import period_tables

        supply, table, other = self._with_a_view_on(conn, period)
        if not period_tables.guard_installed(conn):
            pytest.skip("the platform does not permit the database guard (criterion 18)")
        with pytest.raises(psycopg.Error, match="depends on it"):
            conn.execute(f'ALTER TABLE "{period_schema.period_schema(period)}"."{TABLE}" '
                         f'SET SCHEMA "{supply_db.STAGING_SCHEMA}"')

    def test_the_database_guard_refuses_a_rename_too(self, conn, period):
        import psycopg

        from qa_tools.common import period_tables

        supply, table, other = self._with_a_view_on(conn, period)
        if not period_tables.guard_installed(conn):
            pytest.skip("the platform does not permit the database guard (criterion 18)")
        with pytest.raises(psycopg.Error, match="depends on it"):
            conn.execute(f'ALTER TABLE "{period_schema.period_schema(period)}"."{TABLE}" '
                         f'RENAME TO "{TABLE}_moved"')

    def test_but_lets_any_other_change_through(self, conn, period):
        """Keith, 2026-10-05 (#113 M2): moves and renames only, as criterion
        11 says - an added column is not a move, and refusing it would block
        every schema change on a table a view stands on."""
        from qa_tools.common import period_tables

        supply, table, other = self._with_a_view_on(conn, period)
        if not period_tables.guard_installed(conn):
            pytest.skip("the platform does not permit the database guard (criterion 18)")
        conn.execute(f'ALTER TABLE "{period_schema.period_schema(period)}"."{TABLE}" '
                     f'ADD COLUMN IF NOT EXISTS extra text')

    def test_the_database_guard_refuses_a_cascading_drop(self, conn, period):
        import psycopg

        from qa_tools.common import period_tables

        supply, table, other = self._with_a_view_on(conn, period)
        if not period_tables.guard_installed(conn):
            pytest.skip("the platform does not permit the database guard (criterion 18)")
        with pytest.raises(psycopg.Error, match="view"):
            conn.execute(f'DROP TABLE "{period_schema.period_schema(period)}"."{TABLE}" CASCADE')


class TestTheStampedNameComesFromTheLog:
    """Criterion 4."""

    def test_stamped_name(self):
        from qa_tools.common import period_tables

        assert period_tables.stamped_name("cp_carers", "cp-carers@202605010100000000") == \
            "cp_carers__202605010100000000"


class TestATableOrAViewIsAskedOfTheCatalogue:
    """Criterion 8: under plain names a view and a table look alike, so a
    substitution or inheritance standing on one is judged by the catalogue."""

    def test_a_view_cannot_be_stood_on(self, conn, period):
        from qa_tools.common import inheritance, period_tables, substitution

        schema = period_schema.ensure_period_schema(conn, period)
        conn.execute(f'CREATE VIEW "{schema}"."{TABLE}" AS SELECT 1 AS id')
        try:
            assert period_tables.is_view(conn, schema, TABLE)
            with pytest.raises(substitution.SubstitutionRefused, match="is a view"):
                substitution._physical_in(conn, period=period, logical=TABLE)
            with pytest.raises(inheritance.InheritanceRefused, match="is a view"):
                inheritance._physical_in(conn, period=period, logical=TABLE)
        finally:
            conn.execute(f'DROP VIEW "{schema}"."{TABLE}"')


class TestARunRecordsTheSupplyAPeriodTableHeld:
    """Criterion 13: the plain name no longer identifies the supply, so
    what a run read records it - from the decision log."""

    def test_the_resolution_carries_the_supply_and_the_record_keeps_it(self, conn, period):
        import uuid

        from qa_tools.common import period_overlay, qa_store

        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, supply, table, period)
        res = period_schema.PeriodResolution(
            period=period, resolution=supply_db.Resolution(run_id="r", schema="qa_r"),
            source={TABLE: period_schema.FROM_PERIOD, "cp_clients": "staging"})
        held = period_overlay._supplies_held(conn, period, res)
        assert held == {TABLE: supply}

        run_key = f"pytest-tr-{uuid.uuid4().hex[:8]}"
        qa_store.record_run(conn, run_key=run_key, agency_id=AG, collection_id=COL,
                            run_timestamp="2026-05-01T01:00:00+00:00", run_by="t")
        qa_store.record_tables_read(conn, run_key, {TABLE: TABLE, "cp_clients": "x__1"},
                                    held)
        rows = dict(conn.execute("SELECT logical_table, supply FROM qa.tables_read "
                                 "WHERE run_key = ?", [run_key]).fetchall())
        assert rows == {TABLE: supply, "cp_clients": None}


class TestADecisionNeverHangs:
    """Criteria 15 and 16: the stood-on period is locked too, and a lock
    wait past the timeout is refused as a run in progress."""

    def test_a_move_waiting_on_a_reading_run_is_refused(self, conn, period, monkeypatch):
        monkeypatch.setattr(dl, "LOCK_TIMEOUT", "500ms")
        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, supply, table, period)
        schema = period_schema.period_schema(period)
        with supply_db.connect(label="test-reading-run") as reader:
            with reader.raw.transaction():
                reader.execute(f'LOCK TABLE "{schema}"."{TABLE}" IN ACCESS SHARE MODE')
                with pytest.raises(dl.DecisionRefused, match="retry"):
                    rejection.demote(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                                     supply=supply, physical_tables=[table],
                                     actor=REAL_PERSON, effective_at=WHEN,
                                     reason="not yet", from_slot=period)
        assert dl.promoted_into(conn, DS, period) == supply

    def test_a_substitution_waits_on_the_period_it_stands_on(self, conn, period,
                                                             monkeypatch):
        import uuid

        from qa_tools.common import substitution

        monkeypatch.setattr(dl, "LOCK_TIMEOUT", "500ms")
        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, supply, table, period)
        later = f"2099-T{uuid.uuid4().hex[:6]}"
        with supply_db.connect(label="test-other-decision") as other:
            with other.raw.transaction():
                dl.lock_slot(other, DS, period)
                with pytest.raises(dl.DecisionRefused, match="retry"):
                    substitution.substitute(
                        conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                        logical_table=TABLE, period=later, stands_on=period, supply=supply,
                        actor=REAL_PERSON, reason="late", effective_at=WHEN)


class TestAMissingGuardIsReported:
    """Criterion 18: reported, never raised - the other two still run."""

    def test_installed_says_nothing_and_missing_says_so(self, conn):
        from qa_tools.common import period_tables

        assert period_tables.guard_report(conn) is None
        with _guard_disabled(conn):
            problem = period_tables.guard_report(conn)
        assert problem and "NOT installed" in problem


class TestOnlyOneCodePathMovesAPeriodTable:
    """NFR 6: nothing outside period_tables moves or renames a table in a
    period schema. Read from the source, so a new mover fails here."""

    ROOTS = ("qa_tools", "pipeline", "cli", "dashboard", "generator")

    def _sources(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        for top in self.ROOTS:
            yield from sorted((root / top).rglob("*.py"))

    def test_rename_and_set_schema_are_said_only_there(self):
        allowed = {"period_tables.py", "supply_db.py"}
        offenders = []
        for path in self._sources():
            if path.name in allowed:
                continue
            code = "\n".join(line for line in path.read_text().splitlines()
                             if not line.lstrip().startswith("#"))
            for ddl in ("RENAME TO", "SET SCHEMA"):
                for i, line in enumerate(code.splitlines()):
                    if ddl in line and ("'" in line or '"' in line) and "..." not in line:
                        offenders.append(f"{path.name}: {line.strip()}")
        assert offenders == []

    def test_no_other_move_takes_a_period_schema(self):
        import ast

        offenders = []
        for path in self._sources():
            if path.name in ("period_tables.py", "supply_db.py"):
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "move_table"):
                    args = " ".join(ast.unparse(a) for a in node.args[1:])
                    if "period_schema" in args or "period" == args.split()[0]:
                        offenders.append(f"{path.name}:{node.lineno} {args}")
        assert offenders == []

    def test_and_a_bare_move_into_a_period_is_refused_at_run_time(self, conn, period):
        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        schema = period_schema.ensure_period_schema(conn, period)
        with pytest.raises(supply_db.SupplyDbError, match="only through period_tables"):
            supply_db.move_table(conn, table, supply_db.STAGING_SCHEMA, schema)


class TestTheResolutionRemembersTheSupply:
    """Criterion 13 for every record of what a run read: the resolution
    each run's records are written from carries the supply."""

    def test_round_trip(self, conn):
        import uuid

        run_id = f"cp_carers__{uuid.uuid4().int % 10**18:018d}"
        res = supply_db.Resolution(run_id=run_id, schema=supply_db.run_schema(run_id),
                                   resolved={TABLE: TABLE, "cp_clients": "cp_clients__1"},
                                   supply_of={TABLE: f"{DS}@000000000000000007"})
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
        supply_db.record_resolution(conn, res)
        back = supply_db.resolution_for(conn, run_id)
        assert back.supply_of == {TABLE: f"{DS}@000000000000000007"}
        assert back.as_record()["supply_of"] == back.supply_of

    def test_the_per_result_record_names_the_supply(self, monkeypatch):
        from qa_tools.common import qa_results_writer as w

        res = supply_db.Resolution(run_id="r", schema="x",
                                   resolved={TABLE: TABLE},
                                   supply_of={TABLE: f"{DS}@000000000000000007"})

        class Conn:
            def close(self):
                pass
        monkeypatch.setattr(supply_db, "connect", lambda **_k: Conn())
        monkeypatch.setattr(supply_db, "resolution_for", lambda conn, run_id: res)
        monkeypatch.setattr(w, "_declared_reads_tables", lambda: {"c1": [TABLE]})
        out = w._with_tables_read([{"check_id": "c1", "dataset_id": "cp-clients"}], "r")
        assert out[0]["tables_read"] == {TABLE: f"{TABLE}__000000000000000007"}


class TestOnlyTheHolderLeavesAPeriod:
    """#113 H2: a demote naming a supply the period does not hold emptied
    the period and gave its real table the wrong supply's name."""

    def test_a_demote_of_another_supply_is_refused(self, conn, period):
        from qa_tools.common import filing_decisions as fd, people

        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, supply, table, period)
        wrong = f"{DS}@111111111111111111"
        with pytest.raises(dl.DecisionRefused, match="does not hold"):
            fd.apply(fd.Request(operation=fd.DEMOTE, dataset_id=DS, period=period,
                                supply=wrong, reason="typo",
                                actor=people.person_by_email(REAL_PERSON)),
                     effective_at=WHEN, conn=conn)
        assert _tables_in(conn, period_schema.period_schema(period)) == [TABLE]
        assert dl.promoted_into(conn, DS, period) == supply

    def test_a_demote_whose_table_is_gone_is_loud(self, conn, period):
        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, supply, table, period)
        conn.execute(f'DROP TABLE "{period_schema.period_schema(period)}"."{TABLE}"')
        with pytest.raises(dl.DecisionRefused, match="moved or dropped"):
            rejection.demote(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                             supply=supply, physical_tables=[table], actor=REAL_PERSON,
                             effective_at=WHEN, reason="x", from_slot=period)
        assert dl.promoted_into(conn, DS, period) == supply


class TestASubstitutionIsJudgedAgainAfterItWaits:
    """#113 H3, criterion 15: a promotion that displaces the supply stood on
    while the substitution waits for the lock is seen under the lock."""

    def test_refused_rather_than_reading_the_newcomer(self, conn, period):
        import threading
        import time
        import uuid

        from qa_tools.common import substitution

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        b, b_table = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        later = f"2099-T{uuid.uuid4().hex[:6]}"
        outcome = {}

        def substitute():
            try:
                substitution.substitute(
                    conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                    logical_table=TABLE, period=later, stands_on=period, supply=a,
                    actor=REAL_PERSON, reason="late", effective_at=WHEN)
                outcome["done"] = True
            except Exception as exc:  # noqa: BLE001 - asserted below
                outcome["error"] = exc

        with supply_db.connect(label="test-displacer") as other:
            with other.raw.transaction():
                dl.lock_slot(other, DS, period)
                worker = threading.Thread(target=substitute)
                worker.start()
                time.sleep(1.0)
                _promote(other, b, b_table, period, kind=dl.PERSON)
            worker.join(30)
        assert isinstance(outcome.get("error"), substitution.SubstitutionRefused), outcome
        assert dl.held(conn, DS, later) is None


class TestTheGuardCanBePutBack:
    """#113: the missing-guard warning names a remedy, and the remedy works."""

    def test_install_guard_restores_a_dropped_guard(self, conn):
        from click.testing import CliRunner

        from cli.supply import supply_group
        from qa_tools.common import period_tables

        conn.execute(f"DROP EVENT TRIGGER IF EXISTS {period_tables.GUARD_TRIGGER}")
        assert "install-guard" in period_tables.guard_report(conn)
        result = CliRunner().invoke(supply_group, ["install-guard"])
        assert result.exit_code == 0, result.output
        assert period_tables.guard_installed(conn)

    def test_an_empty_database_is_not_called_guarded(self, monkeypatch, capsys):
        from qa_tools.common import period_tables

        class Empty:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, *a, **k):
                class R:
                    def fetchall(self):
                        return [(None,)]
                return R()
        monkeypatch.setattr(supply_db, "connect", lambda **_k: Empty())
        assert period_tables.main() == 0
        assert "nothing to guard" in capsys.readouterr().out
