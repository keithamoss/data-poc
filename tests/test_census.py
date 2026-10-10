"""The census: the decision log and the warehouse compared (REQ-PIPE-081
criteria 12 to 16). Against a real database; each test mints its own
periods and scopes its census to them, since other tests leave periods
behind on the same worker."""
from __future__ import annotations

import test_supersession as _base
from qa_tools.common import census, decision_log as dl, period_schema, promotion, qa_store
from test_supersession import DS, TABLE, WHEN, _filed

conn = _base.conn
period = _base.period

AG, COL = "child-protection-family-support", "child-protection"


def _promote(conn, supply, table, period):
    promotion.promote(conn, agency_id=AG, collection_id=COL, dataset_id=DS, supply=supply,
                      period=period, physical_tables=[table], actor="promotion rule",
                      actor_kind=dl.RULE, effective_at=WHEN, reason="because")


def _findings(conn, census_id):
    return [r[0] for r in conn.execute(
        "SELECT kind FROM qa.census_discrepancy WHERE census_id = ?", [census_id]).fetchall()]


class TestWhatTheCensusFinds:
    """Criterion 12: only discrepancies, and a census row either way."""

    def test_agreement_records_a_census_with_nothing_in_it(self, conn, period):
        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, supply, table, period)
        census_id = census.take(conn, trigger="test", periods=[period])
        assert census_id and _findings(conn, census_id) == []

    def test_a_table_dropped_by_hand_is_missing(self, conn, period):
        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, supply, table, period)
        conn.execute(f'DROP TABLE "{period_schema.period_schema(period)}"."{TABLE}"')
        (found,) = census.compare(conn, [period])
        assert (found.kind, found.period, found.table_name, found.supply) == (
            census.MISSING, period, TABLE, supply)

    def test_a_view_where_the_log_says_promoted_is_the_wrong_kind(self, conn, period):
        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, supply, table, period)
        schema = period_schema.period_schema(period)
        conn.execute(f'ALTER TABLE "{schema}"."{TABLE}" RENAME TO "{TABLE}_x"')
        conn.execute(f'CREATE VIEW "{schema}"."{TABLE}" AS SELECT * FROM "{schema}"."{TABLE}_x"')
        kinds = sorted(d.kind for d in census.compare(conn, [period]))
        assert kinds == [census.STRAY, census.WRONG_KIND]

    def test_a_table_no_decision_put_there_is_a_stray(self, conn, period):
        schema = period_schema.ensure_period_schema(conn, period)
        conn.execute(f'CREATE TABLE "{schema}"."handmade" (id int)')
        (found,) = census.compare(conn, [period])
        assert found.kind == census.STRAY and found.table_name == "handmade"


class TestTakenWhenATableMoves:
    """Criterion 13: a decision that moves a table is censused when taken,
    and never half-way through a transaction."""

    def test_a_promotion_records_a_census_of_its_period(self, conn, period):
        before = conn.execute("SELECT count(*) FROM qa.census").fetchall()[0][0]
        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, supply, table, period)
        rows = conn.execute("SELECT trigger, periods FROM qa.census ORDER BY id DESC "
                            "LIMIT 1").fetchall()
        assert conn.execute("SELECT count(*) FROM qa.census").fetchall()[0][0] > before
        assert rows[0] == ("promote", [period])

    def test_not_inside_someone_elses_transaction(self, conn, period):
        with conn.raw.transaction():
            assert census.take(conn, trigger="test", periods=[period]) is None


class TestTheAnswerIsTheRecordedOne:
    """Criterion 14: change points over recorded censuses, a scoped census
    answering for its own period only; criterion 16: the build's warning."""

    def test_change_points_fold_scoped_censuses_forward(self, conn, period):
        qa_store.ensure_schema(conn)
        conn.execute("DELETE FROM qa.census")
        schema = period_schema.ensure_period_schema(conn, period)
        conn.execute(f'CREATE TABLE "{schema}"."handmade" (id int)')
        census.take(conn, trigger="test", periods=[period])
        census.take(conn, trigger="test", periods=[period])     # unchanged
        conn.execute(f'DROP TABLE "{schema}"."handmade"')
        census.take(conn, trigger="test", periods=[period])
        points = census.change_points(conn)
        assert [len(p["discrepancies"]) for p in points] == [1, 0]
        assert census.warn(points) == []
        assert census.warn(points[:1])[0].startswith("warning: census")


class TestWhatAPageIsShown:
    """Criterion 15: a page sees its own datasets' findings and any no
    dataset owns; repeated states collapse."""

    def test_filtered_to_the_datasets_and_collapsed(self, conn, monkeypatch):
        mine = {"kind": "missing", "datasetId": "cp-carers", "period": "p", "table": "t"}
        other = {"kind": "missing", "datasetId": "cp-clients", "period": "p", "table": "u"}
        loose = {"kind": "stray", "datasetId": None, "period": "p", "table": "h"}
        monkeypatch.setattr(census, "change_points", lambda conn: [
            {"takenAt": "a", "discrepancies": [mine]},
            {"takenAt": "b", "discrepancies": [mine, other]},
            {"takenAt": "c", "discrepancies": [mine, other, loose]},
        ])
        got = census.for_datasets({"cp-carers"})
        assert [(p["takenAt"], len(p["discrepancies"])) for p in got] == [("a", 1), ("c", 2)]


class TestTheBuildWarns:
    """Criterion 16 on the mothman build path (#113 M1): the builders are
    called as modules there, so their __main__ never runs."""

    def test_build_data_prints_the_warning_and_still_writes(self, monkeypatch, tmp_path,
                                                            capsys):
        from cli import dashboard as cli_dashboard
        from pipeline import build_cp_dashboard_data, build_dashboard_data

        for module in (build_dashboard_data, build_cp_dashboard_data):
            monkeypatch.setattr(module, "build", lambda: {"datasets": []})
            monkeypatch.setattr(module, "OUT_PATH", str(tmp_path / f"{module.__name__}.json"))
        monkeypatch.setattr(census, "build_warnings",
                            lambda: ["warning: census x: the log says P holds t"])
        cli_dashboard._build_data()
        assert "warning: census x" in capsys.readouterr().out
        assert len(list(tmp_path.iterdir())) == 2


class TestTheCensusIsOneSnapshot:
    """#113 M3: the log and the catalogue are read as ONE snapshot, so a
    promotion committing between the two reads is not reported as a stray."""

    def test_a_promotion_between_the_two_reads_is_not_a_discrepancy(self, conn, period):
        from qa_tools.common import supply_db

        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")

        class Between:
            def __init__(self, inner):
                self.inner, self.fired = inner, False

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def execute(self, sql, *a, **k):
                out = self.inner.execute(sql, *a, **k)
                if "slot_holds_now" in sql and not self.fired:
                    self.fired = True
                    with supply_db.connect(label="test-census-between") as other:
                        _promote(other, supply, table, period)
                return out

        census_id = census.take(Between(conn), trigger="test", periods=[period])
        assert _findings(conn, census_id) == []
