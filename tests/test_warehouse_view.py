"""A promoted supply's status counts a cross-table verdict only when every
supply THAT CHECK read is the one in the warehouse, and a check that could
not run counts only against the table that asks (REQ-PIPE-269).

Against this worker's own database, recorded as the pipeline records it -
record_results with the reads qa.check_read keeps (REQ-PIPE-279 criterion
1), and the decision log saying what each period holds. Each test mints its
own period, so the warehouse one test builds answers no other test.

The gate, the knock-on, red_promoted and the dashboard build all ask
supply_status.results_about (criterion 7), so asserting through it, through
supply_status.status and promotion.status_of, and through the build's
red-promoted timeline is asserting what each of those readers sees.
"""
from __future__ import annotations

import uuid

import pytest

from qa_tools.common import decision_log as dl, knock_on, promotion, qa_store, recheck
from qa_tools.common import supply_db, supply_status
from test_results_about import (CHECK, CLIENT_REF, CLIENTS_OWN, KEYS, _key, _read, _result,
                                _run)

NOTIFICATIONS_OWN = f"{CHECK}.cp-notifications.notification_id.unique_dbt"
PLACEMENTS_CLIENT_REF = f"{CHECK}.cp-placements.cp_client_id.relationships_dbt"
PLACEMENTS_OWN = f"{CHECK}.cp-placements.placement_id.unique_dbt"

NOW = supply_status.View()


@pytest.fixture
def conn(clean_qa_history):
    supply_db.ensure_schemas(clean_qa_history)
    yield clean_qa_history


@pytest.fixture
def period():
    return f"2099-W{uuid.uuid4().hex[:6]}"


def _supply(dataset_id: str) -> str:
    return f"{dataset_id}@{_key()}"


def _decide(conn, action: str, dataset_id: str, supply: str, period: str, at: str, *,
            kind: str = dl.RULE, reason: str = "pytest", **extra) -> int:
    slot = {"from_slot": period} if action in (dl.DEMOTE, dl.UN_INHERIT) else {"to_slot": period}
    with dl.decision_transaction(conn):
        with dl.apply_decision(conn, dl.Decision(
                **KEYS, dataset_id=dataset_id, action=action, supply=supply,
                actor="k@x" if kind == dl.PERSON else "promotion rule", actor_kind=kind,
                effective_at=at, reason=reason, **slot, **extra)):
            pass
    return conn.execute(f"SELECT max(id) FROM {dl.TABLE}").fetchone()[0]


def _promote(conn, dataset_id, supply, period, at, **kw) -> int:
    return _decide(conn, dl.PROMOTE, dataset_id, supply, period, at,
                   promoted_status="green", **kw)


def _withhold(conn, dataset_id, supply, period, at) -> int:
    """Held back: the gate refused it, so the period's table is unchanged."""
    with conn.raw.transaction():
        return dl.record_automatic(conn, dl.Decision(
            **KEYS, dataset_id=dataset_id, action=dl.PROMOTION_WITHHELD, supply=supply,
            actor="promotion rule", actor_kind=dl.RULE, effective_at=at, to_slot=period,
            reason="its status is red"))


def _uid(prefix: str) -> str:
    return f"pytest-{prefix}-{uuid.uuid4().hex[:8]}"


def _own(conn, dataset_id, supply, check, status, at, **kw) -> str:
    return _run(conn, _uid(dataset_id[3:6]), dataset_id=dataset_id, supply=supply, at=at,
                own=[_result(check, dataset_id, status)], **kw)


def _client_ref(conn, *, under: str, supply: str, clients, notifications, status: str, at: str,
                not_evaluated: bool = False, scope: str = "arrival", decision=None) -> str:
    """The Client reference (declared on Notifications, reads cp_clients)
    recorded under `under`'s run of `supply`, reading the two supplies
    named - or ABSENT where one is None."""
    record = _result(CLIENT_REF, "cp-notifications", status)
    if not_evaluated:
        record["unrunnable_reason"] = "no Client Register supply this run may read"
    reads = (_read("cp_clients", clients) if clients
             else _read("cp_clients", None, qa_store.ABSENT),
             _read("cp_notifications", notifications) if notifications
             else _read("cp_notifications", None, qa_store.ABSENT))
    return _run(conn, _uid("x"), dataset_id=under, supply=supply, at=at, scope=scope,
                decision=decision, cross=[(record, reads)])


def _status(conn, dataset_id, supply, view=NOW):
    return supply_status.status(conn, dataset_id, supply, view=view)


def _counted(conn, dataset_id, supply, check, view=NOW) -> list[dict]:
    return [r for r in supply_status.latest_results(conn, dataset_id, supply, view=view)
            if r["check_id"] == check]


# ---------------------------------------------------------------------------
# S4 and its other direction (criteria 1 and 2)
# ---------------------------------------------------------------------------

class TestHeldBackPartnerDoesNotCount:

    def test_promoted_clients_unaffected_by_a_held_back_notifications(self, conn, period):
        """S4. Clients v1 and Notifications v1 promoted green; Notifications
        v2 arrives alone pointing at missing clients, its Client reference
        red, and is held back. Clients v1 stays green - through
        supply_status, promotion.status_of and the build's red-promoted
        timeline, at a date after the hold-back. Before this requirement
        runs_about/results_about counted Notifications v2's arrival run
        toward Clients v1."""
        from pipeline import red_promoted

        c1, n1, n2 = _supply("cp-clients"), _supply("cp-notifications"), \
            _supply("cp-notifications")
        c1_run = _own(conn, "cp-clients", c1, CLIENTS_OWN, "pass", "2099-01-01T09:00:00+08:00")
        _own(conn, "cp-notifications", n1, NOTIFICATIONS_OWN, "pass", "2099-01-01T09:00:00+08:00")
        _client_ref(conn, under="cp-notifications", supply=n1, clients=c1, notifications=n1,
                    status="pass", at="2099-01-01T09:00:00+08:00")
        _promote(conn, "cp-clients", c1, period, "2099-01-01T10:00:00+08:00")
        _promote(conn, "cp-notifications", n1, period, "2099-01-01T10:00:00+08:00")
        _client_ref(conn, under="cp-notifications", supply=n2, clients=c1, notifications=n2,
                    status="fail", at="2099-01-05T09:00:00+08:00")
        _withhold(conn, "cp-notifications", n2, period, "2099-01-05T10:00:00+08:00")

        after = supply_status.View(as_at="2099-01-06T23:59:59+08:00")
        assert _status(conn, "cp-clients", c1) == "green"
        assert _status(conn, "cp-clients", c1, after) == "green"
        reads = promotion._declared_reads()
        assert promotion.status_of("cp-clients", supply_status.latest_results(
            conn, "cp-clients", c1, view=after), reads=reads) == "green"
        health = red_promoted.for_dataset("cp-clients", conn=conn)[c1_run]
        assert red_promoted.status_on(health, "2099-01-06") == "green"
        # STILL SHOWN on the supply it describes (AUDITABILITY): nothing is
        # deleted, it only stops counting.
        about = supply_status.results_about(conn, "cp-clients", c1, view=after)
        assert any(r["check_id"] == CLIENT_REF and r["status"] == "fail" for r in about.shown)
        assert not any(r["check_id"] == CLIENT_REF and r["status"] == "fail"
                       for r in about.counted)

    def test_promoted_notifications_unaffected_by_a_held_back_clients(self, conn, period):
        """Keith's 2026-10-20 case: Notifications promoted green, a Clients
        v2 red on its own checks held back - Notifications' status and its
        rows show the verdict against the Clients in the warehouse."""
        c1, c2, n1 = _supply("cp-clients"), _supply("cp-clients"), _supply("cp-notifications")
        _own(conn, "cp-clients", c1, CLIENTS_OWN, "pass", "2099-01-01T09:00:00+08:00")
        _own(conn, "cp-notifications", n1, NOTIFICATIONS_OWN, "pass", "2099-01-01T09:00:00+08:00")
        warehouse_verdict = _client_ref(
            conn, under="cp-notifications", supply=n1, clients=c1, notifications=n1,
            status="pass", at="2099-01-01T09:00:00+08:00")
        _promote(conn, "cp-clients", c1, period, "2099-01-01T10:00:00+08:00")
        _promote(conn, "cp-notifications", n1, period, "2099-01-01T10:00:00+08:00")
        _own(conn, "cp-clients", c2, CLIENTS_OWN, "fail", "2099-01-05T09:00:00+08:00")
        # Clients v2's arrival re-evaluates its readers against itself.
        _client_ref(conn, under="cp-clients", supply=c2, clients=c2, notifications=n1,
                    status="fail", at="2099-01-05T09:00:00+08:00")
        _withhold(conn, "cp-clients", c2, period, "2099-01-05T10:00:00+08:00")

        assert _status(conn, "cp-notifications", n1) == "green"
        (row,) = _counted(conn, "cp-notifications", n1, CLIENT_REF)
        assert row["run_id"] == warehouse_verdict


# ---------------------------------------------------------------------------
# S2: promoted together, counted with no re-run
# ---------------------------------------------------------------------------

class TestPromotedTogether:

    def test_one_verdict_counts_toward_both(self, conn, period):
        """A first-time zip promotes Clients v2 and Notifications v2
        together: the single Client reference verdict counts toward both, and
        the knock-on has nothing to re-run."""
        c2, n2 = _supply("cp-clients"), _supply("cp-notifications")
        _own(conn, "cp-clients", c2, CLIENTS_OWN, "pass", "2099-02-01T09:00:00+08:00")
        _own(conn, "cp-notifications", n2, NOTIFICATIONS_OWN, "pass", "2099-02-01T09:00:00+08:00")
        verdict = _client_ref(conn, under="cp-notifications", supply=n2, clients=c2,
                              notifications=n2, status="pass", at="2099-02-01T09:00:00+08:00")
        _promote(conn, "cp-clients", c2, period, "2099-02-01T10:00:00+08:00")
        _promote(conn, "cp-notifications", n2, period, "2099-02-01T10:00:00+08:00")

        assert [r["run_id"] for r in _counted(conn, "cp-clients", c2, CLIENT_REF)] == [verdict]
        assert [r["run_id"] for r in _counted(conn, "cp-notifications", n2, CLIENT_REF)] == [
            verdict]
        readers = knock_on.readers(conn, period, ["cp_clients", "cp_notifications"],
                                   promotion._declared_reads())
        assert readers and not any(r.stale for r in readers)


# ---------------------------------------------------------------------------
# Criterion 4: a could-not-run counts only against the table that asks
# ---------------------------------------------------------------------------

class TestCouldNotRunCountsTowardTheAsker:

    def test_an_absent_clients_reddens_only_the_asker(self, conn, period):
        """Clients absent: Notifications' Client reference could not run and
        counts toward Notifications only - and an earlier Clients supply of
        another period is coloured by nothing."""
        n1, c0 = _supply("cp-notifications"), _supply("cp-clients")
        _own(conn, "cp-clients", c0, CLIENTS_OWN, "pass", "2099-01-01T09:00:00+08:00")
        _own(conn, "cp-notifications", n1, NOTIFICATIONS_OWN, "pass", "2099-03-01T09:00:00+08:00")
        _client_ref(conn, under="cp-notifications", supply=n1, clients=None, notifications=n1,
                    status="fail", not_evaluated=True, at="2099-03-01T09:00:00+08:00")
        assert _status(conn, "cp-notifications", n1) == "red"
        assert _status(conn, "cp-clients", c0) == "green"

    def test_an_absent_placements_leaves_clients_alone(self, conn, period):
        """The other way round: Placements' Client reference re-run by
        Clients' own arrival with no Placements to read is not evaluated - it
        counts toward Placements, which is not there, so toward nothing."""
        c2 = _supply("cp-clients")
        _own(conn, "cp-clients", c2, CLIENTS_OWN, "pass", "2099-03-01T09:00:00+08:00")
        record = _result(PLACEMENTS_CLIENT_REF, "cp-placements", "fail")
        record["unrunnable_reason"] = "no Placements supply this run may read"
        _run(conn, _uid("c"), dataset_id="cp-clients", supply=c2, at="2099-03-01T09:00:00+08:00",
             cross=[(record, (_read("cp_clients", c2),
                              _read("cp_placements", None, qa_store.ABSENT)))])
        assert _status(conn, "cp-clients", c2) == "green"
        _promote(conn, "cp-clients", c2, period, "2099-03-01T10:00:00+08:00")
        assert _status(conn, "cp-clients", c2) == "green"
        # Shown on Clients all the same - it describes Clients' relationships.
        about = supply_status.results_about(conn, "cp-clients", c2, view=NOW)
        assert [r["check_id"] for r in about.shown].count(PLACEMENTS_CLIENT_REF) == 1


# ---------------------------------------------------------------------------
# Criteria 5 and 6: an owed re-check reads red; a check not owed counts nothing
# ---------------------------------------------------------------------------

def _warehouse(conn, period):
    """Clients v2 promoted beside Notifications v1, every verdict green,
    and a Notifications v2 that read the older Clients v1 waiting."""
    c1, c2 = _supply("cp-clients"), _supply("cp-clients")
    n1, n2 = _supply("cp-notifications"), _supply("cp-notifications")
    _own(conn, "cp-clients", c2, CLIENTS_OWN, "pass", "2099-04-02T09:00:00+08:00")
    _own(conn, "cp-notifications", n1, NOTIFICATIONS_OWN, "pass", "2099-04-01T09:00:00+08:00")
    _own(conn, "cp-notifications", n2, NOTIFICATIONS_OWN, "pass", "2099-04-01T12:00:00+08:00")
    _client_ref(conn, under="cp-notifications", supply=n2, clients=c1, notifications=n2,
                status="pass", at="2099-04-01T12:00:00+08:00")
    _client_ref(conn, under="cp-clients", supply=c2, clients=c2, notifications=n1,
                status="pass", at="2099-04-02T09:00:00+08:00")
    _promote(conn, "cp-notifications", n1, period, "2099-04-01T10:00:00+08:00")
    _promote(conn, "cp-clients", c2, period, "2099-04-02T10:00:00+08:00")
    return c2, n1, n2


class TestOwedRecheck:

    def test_owed_recheck_reads_red_and_raises_nothing(self, conn, period):
        """A person promotes Notifications v2 and its knock-on fails: Clients
        v2 has no verdict about the warehouse as it now stands, reads red
        with reason 'recheck-owed' naming that promotion, and nothing is
        raised about it; once the re-check runs green it reads green."""
        c2, n1, n2 = _warehouse(conn, period)
        assert _status(conn, "cp-clients", c2) == "green"
        with conn.raw.transaction():
            for o in recheck.owed(conn):
                if o.period == period:
                    recheck.clear(o.id, "pytest/earlier")
        promote = _decide(conn, dl.PROMOTE, "cp-notifications", n2, period,
                          "2099-04-03T10:00:00+08:00", kind=dl.PERSON, promoted_status="green",
                          reason="looked at it")
        (owed,) = [o for o in recheck.owed(conn) if o.period == period]
        recheck.fail(owed.id, "RuntimeError: made to fail")
        decisions_before = conn.execute(
            f"SELECT count(*) FROM {dl.TABLE} WHERE to_slot = ? AND action = ?",
            [period, dl.STILL_FAILING]).fetchone()[0]

        assert _status(conn, "cp-clients", c2) == "red"
        (row,) = _counted(conn, "cp-clients", c2, CLIENT_REF)
        assert row["warehouse_reason"] == supply_status.RECHECK_OWED
        assert row["owed_by_decision"] == promote
        assert row["owed_since"].startswith("2099-04-03")
        assert conn.execute(
            f"SELECT count(*) FROM {dl.TABLE} WHERE to_slot = ? AND action = ?",
            [period, dl.STILL_FAILING]).fetchone()[0] == decisions_before == 0
        # The as-at view agrees: before the promotion took effect nothing was owed.
        before = supply_status.View(as_at="2099-04-03T09:00:00+08:00")
        assert _status(conn, "cp-clients", c2, before) == "green"

        _client_ref(conn, under="cp-clients", supply=c2, clients=c2, notifications=n2,
                    status="pass", at="2099-04-03T11:00:00+08:00", scope="full",
                    decision=promote)
        recheck.clear(owed.id, "pytest/rechecked")
        assert _status(conn, "cp-clients", c2) == "green"

    def test_an_uninherit_owes_the_same(self, conn, period):
        """A person un-inherits a table from a period whose Notifications is
        promoted, and the knock-on fails: Notifications reads 'recheck-owed'
        naming the un-inherit."""
        earlier = f"{period}-a"
        c1, n1 = _supply("cp-clients"), _supply("cp-notifications")
        _own(conn, "cp-clients", c1, CLIENTS_OWN, "pass", "2099-05-01T09:00:00+08:00")
        _promote(conn, "cp-clients", c1, earlier, "2099-05-01T10:00:00+08:00")
        _decide(conn, dl.INHERIT, "cp-clients", c1, period, "2099-05-02T08:00:00+08:00",
                stands_on=earlier)
        _own(conn, "cp-notifications", n1, NOTIFICATIONS_OWN, "pass", "2099-05-02T09:00:00+08:00")
        _client_ref(conn, under="cp-notifications", supply=n1, clients=c1, notifications=n1,
                    status="pass", at="2099-05-02T09:00:00+08:00")
        _promote(conn, "cp-notifications", n1, period, "2099-05-02T10:00:00+08:00")
        assert _status(conn, "cp-notifications", n1) == "green"
        uninherit = _decide(conn, dl.UN_INHERIT, "cp-clients", c1, period,
                            "2099-05-03T10:00:00+08:00", kind=dl.PERSON, reason="not ours")
        for o in recheck.owed(conn):
            if o.period == period and o.caused_by_decision == uninherit:
                recheck.fail(o.id, "RuntimeError: made to fail")
        assert _status(conn, "cp-notifications", n1) == "red"
        (row,) = _counted(conn, "cp-notifications", n1, CLIENT_REF)
        assert (row["warehouse_reason"], row["owed_by_decision"]) == (
            supply_status.RECHECK_OWED, uninherit)

    def test_nothing_owed_and_nothing_current_reads_no_current_result(self, conn, period):
        c2, n1, n2 = _warehouse(conn, period)
        _decide(conn, dl.PROMOTE, "cp-notifications", n2, period, "2099-04-03T10:00:00+08:00",
                kind=dl.PERSON, promoted_status="green", reason="looked at it")
        for o in recheck.owed(conn):
            if o.period == period:
                recheck.clear(o.id, "pytest/cleared-without-a-run")
        (row,) = _counted(conn, "cp-clients", c2, CLIENT_REF)
        assert row["warehouse_reason"] == supply_status.NO_CURRENT_RESULT
        assert _status(conn, "cp-clients", c2) == "red"


# ---------------------------------------------------------------------------
# Per check, not per run (architect v4 B2, v5 B1)
# ---------------------------------------------------------------------------

class TestCountedPerCheck:

    def test_a_held_back_table_uncounts_only_the_checks_that_read_it(self, conn, period):
        """S14's six-table first-time zip with Placements v2 held back: every
        run of the zip resolved cp_placements, but Notifications' Client
        reference reads only cp_clients, so it still counts toward
        Notifications v2 and Clients v2 - and toward no Placements or Carers
        supply. Placements' own Client reference, which read the held-back
        Placements, counts toward neither."""
        c2, n2, p2 = _supply("cp-clients"), _supply("cp-notifications"), \
            _supply("cp-placements")
        carers = _supply("cp-carers")
        at = "2099-06-01T09:00:00+08:00"
        _own(conn, "cp-clients", c2, CLIENTS_OWN, "pass", at)
        _own(conn, "cp-notifications", n2, NOTIFICATIONS_OWN, "pass", at)
        _own(conn, "cp-placements", p2, PLACEMENTS_OWN, "fail", at)
        resolved = {"cp_placements": (f"cp_placements__{p2.split('@')[1]}", p2),
                    "cp_carers": (f"cp_carers__{carers.split('@')[1]}", carers)}
        verdict = _run(conn, _uid("n"), dataset_id="cp-notifications", supply=n2, at=at,
                       physical=resolved,
                       cross=[(_result(CLIENT_REF, "cp-notifications", "pass"),
                               (_read("cp_clients", c2), _read("cp_notifications", n2)))])
        _run(conn, _uid("p"), dataset_id="cp-placements", supply=p2, at=at, physical=resolved,
             cross=[(_result(PLACEMENTS_CLIENT_REF, "cp-placements", "pass"),
                     (_read("cp_clients", c2), _read("cp_placements", p2)))])
        _promote(conn, "cp-clients", c2, period, "2099-06-01T10:00:00+08:00")
        _promote(conn, "cp-notifications", n2, period, "2099-06-01T10:00:00+08:00")
        _withhold(conn, "cp-placements", p2, period, "2099-06-01T10:00:00+08:00")

        for ds, supply in (("cp-clients", c2), ("cp-notifications", n2)):
            assert [r["run_id"] for r in _counted(conn, ds, supply, CLIENT_REF)] == [verdict]
        assert _counted(conn, "cp-placements", p2, CLIENT_REF) == []
        assert _counted(conn, "cp-carers", carers, CLIENT_REF) == []
        assert _counted(conn, "cp-clients", c2, PLACEMENTS_CLIENT_REF) == []
        assert _status(conn, "cp-clients", c2) == "green"

    def test_clean_clients_promoted_alone_is_not_red(self, conn, period):
        """V4-Q1's first-time case: Clients v2 in the warehouse, no
        Notifications, reads green with nothing counted for Client reference
        - although a Notifications that was then held back read it."""
        c2, n2 = _supply("cp-clients"), _supply("cp-notifications")
        _own(conn, "cp-clients", c2, CLIENTS_OWN, "pass", "2099-07-01T09:00:00+08:00")
        _client_ref(conn, under="cp-notifications", supply=n2, clients=c2, notifications=n2,
                    status="fail", at="2099-07-01T09:00:00+08:00")
        _promote(conn, "cp-clients", c2, period, "2099-07-01T10:00:00+08:00")
        _withhold(conn, "cp-notifications", n2, period, "2099-07-01T10:00:00+08:00")
        assert _status(conn, "cp-clients", c2) == "green"
        assert _counted(conn, "cp-clients", c2, CLIENT_REF) == []


# ---------------------------------------------------------------------------
# B1: a reader that could not read a table is re-run, not only re-gated
# ---------------------------------------------------------------------------

class TestKnockOnStaleness:

    def test_not_evaluated_reader_is_rerun_not_only_regated(self, conn, period):
        """A knock-on owed for cp_clients in a period that still holds no
        Clients: the waiting Notifications' Client reference was not
        evaluated, so its reading checks run again. Before this requirement
        knock_on.readers compared what it read (None) with what the period
        holds (None) and only re-gated it."""
        n2 = _supply("cp-notifications")
        _own(conn, "cp-notifications", n2, NOTIFICATIONS_OWN, "pass", "2099-08-01T09:00:00+08:00")
        _client_ref(conn, under="cp-notifications", supply=n2, clients=None, notifications=n2,
                    status="fail", not_evaluated=True, at="2099-08-01T09:00:00+08:00")
        import filing_support

        delivery = f"pytest-n-{uuid.uuid4().hex[:6]}"
        filing_support.ensure_delivery(delivery, "cp-notifications", None)
        filing_support.place(conn, "cp-notifications", n2, period, delivery)
        (reader,) = [r for r in knock_on.readers(conn, period, ["cp_clients"],
                                                 promotion._declared_reads())
                     if r.supply == n2]
        assert reader.waiting and reader.stale


# ---------------------------------------------------------------------------
# The view's instant (criterion 9): only what was recorded by then
# ---------------------------------------------------------------------------

class TestAsAtTheView:

    def test_a_result_recorded_after_the_instant_does_not_count(self, conn, period):
        """Post-build-review #266 D1. Clients v1 and Notifications v1 are
        promoted green on 1 January; a later run of the same two supplies,
        recorded on 10 January, finds the Client reference failing. As at 5
        January the status is green - the 10 January result did not exist
        yet, which is how the dashboard's as-of clip reads it. Before the
        fix results_about clipped the warehouse to the instant but not the
        results, and read red."""
        c1, n1 = _supply("cp-clients"), _supply("cp-notifications")
        _own(conn, "cp-clients", c1, CLIENTS_OWN, "pass", "2099-01-01T09:00:00+08:00")
        _own(conn, "cp-notifications", n1, NOTIFICATIONS_OWN, "pass", "2099-01-01T09:00:00+08:00")
        first = _client_ref(conn, under="cp-notifications", supply=n1, clients=c1,
                            notifications=n1, status="pass", at="2099-01-01T09:00:00+08:00")
        _promote(conn, "cp-clients", c1, period, "2099-01-01T10:00:00+08:00")
        _promote(conn, "cp-notifications", n1, period, "2099-01-01T10:00:00+08:00")
        later = _client_ref(conn, under="cp-clients", supply=c1, clients=c1, notifications=n1,
                            status="fail", at="2099-01-10T09:00:00+08:00")

        on_5th = supply_status.View(as_at="2099-01-05T23:59:59+08:00")
        assert _status(conn, "cp-clients", c1, on_5th) == "green"
        assert _status(conn, "cp-notifications", n1, on_5th) == "green"
        assert [r["run_id"] for r in _counted(conn, "cp-clients", c1, CLIENT_REF, on_5th)] == [
            first]
        about = supply_status.results_about(conn, "cp-clients", c1, view=on_5th)
        assert later not in {r["run_id"] for r in about.shown}
        # And from the 10th on, and now, the later result is the one counted.
        on_10th = supply_status.View(as_at="2099-01-10T09:00:00+08:00")
        assert _status(conn, "cp-clients", c1, on_10th) == "red"
        assert _status(conn, "cp-clients", c1) == "red"
