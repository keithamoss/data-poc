"""One ticket and one still-failing record per root cause, naming everything
it holds back (REQ-PIPE-278).

Driven through the real lifecycle (tests/gate_support.py), then the real
ticket reconciler over a ticket service that remembers - its own pass,
slot_state.states_for and the one root function, as a scheduled pass runs
them. Each test has its own database.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from gate_support import CP, Scenario, cross_red, install_fake_tools, own_red, \
    pin_replacement_setting
from test_package_gate import Q3, Q4, _reject, established, first_time
from test_ticket_reconciler import FakeTickets


@pytest.fixture
def sc(private_supply_dsn, cp_raw_dir, tmp_path, monkeypatch):
    scenario = Scenario(root=tmp_path, raw_dir=Path(cp_raw_dir))
    install_fake_tools(monkeypatch, scenario)
    pin_replacement_setting(monkeypatch)
    return scenario


def _tickets(now=None, policy="needs-action") -> FakeTickets:
    from qa_tools.common import slot_state, supply_db, ticket_reconciler

    service = FakeTickets()
    with supply_db.connect(read_only=True, label="pytest-tickets") as conn:
        states = slot_state.states_for(conn, CP, now=_instant(now) if now else None)
        ticket_reconciler.reconcile(service, states, policy=policy,
                                    roots=ticket_reconciler.roots_for(conn, states))
    return service


def _instant(text):
    from qa_tools.common import asset_time

    return asset_time.parse_instant(text, "test")


def _still_failing(sc) -> list[dict]:
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(read_only=True, label="pytest") as conn:
        return qa_store._dicts(conn.execute(
            f'SELECT * FROM "{qa_store.SCHEMA}".decision WHERE action = \'still-failing\' '
            "ORDER BY id"))


def test_s2_strict_raises_one_ticket_naming_both(sc):
    """S2 strict as re-cast: Clients v2's ticket names Notifications v2;
    Notifications v2's slot has none."""
    first_time(sc)
    sc.rules.append(own_red("C2"))
    sc.deliver("2024-11-03T10:00:00+08:00", {"cp_clients": "C2", "cp_notifications": "N2"})
    sc.process()
    service = _tickets()
    assert f"cp-clients/{Q4}" in service.tickets
    assert f"cp-notifications/{Q4}" not in service.tickets
    body = service.bodies[f"cp-clients/{Q4}"]
    assert "Also held back by this:" in body and "(cp-notifications)" in body


def test_a_supply_whose_root_was_turned_down_is_its_own_root(sc):
    """A root turned down stops being the root: the held-back supply gets a
    ticket of its own, and the root's no longer names it. Observed where the
    slots are unfilled - a resupply waiting beside a promoted supply has no
    ticket under REQ-PIPE-083, whose slot reads PROMOTED - so the chain is S2
    strict's (Clients v2 the root, Notifications v2 held back), then Clients
    v2 rejected."""
    from qa_tools.common import root_cause, supply_db

    first_time(sc)
    sc.rules.append(own_red("C2"))
    v2 = sc.deliver("2024-11-03T10:00:00+08:00", {"cp_clients": "C2", "cp_notifications": "N2"})
    sc.process()
    before = _tickets()
    assert f"cp-notifications/{Q4}" not in before.tickets
    assert "(cp-notifications)" in before.bodies[f"cp-clients/{Q4}"]
    _reject(sc, v2["C2"], Q4)
    with supply_db.connect(read_only=True, label="pytest") as conn:
        assert root_cause.root_of(conn, "cp-notifications", v2["N2"], Q4) is None
    after = _tickets()
    assert f"cp-notifications/{Q4}" in after.tickets
    assert "(cp-notifications)" not in after.bodies.get(f"cp-clients/{Q4}", "")


def test_a_root_promoted_after_its_rejection_is_the_root_again(sc):
    """A rejection a later promotion reversed has not turned the root down
    (refiling._since_unrejected, the one reading of an un-reject - post-build-
    review #274): the held-back supply's root is Clients v2 again."""
    from qa_tools.common import root_cause, supply_db

    first_time(sc)
    sc.rules.append(own_red("C2"))
    v2 = sc.deliver("2024-11-03T10:00:00+08:00", {"cp_clients": "C2", "cp_notifications": "N2"})
    sc.process()
    _reject(sc, v2["C2"], Q4)
    with supply_db.connect(read_only=True, label="pytest") as conn:
        assert root_cause.root_of(conn, "cp-notifications", v2["N2"], Q4) is None
    from qa_tools.common import decision_log, promotion, supply_files

    with supply_db.connect(label="pytest-unreject") as conn:
        # A PERSON'S PROMOTION FROM THE REJECTED SCHEMA is how a rejection is
        # reversed (filing_decisions._promotable).
        promotion.promote(
            conn, agency_id="child-protection-family-support", collection_id=CP,
            dataset_id="cp-clients", supply=v2["C2"], period=Q4,
            physical_tables=supply_files.tables_in(conn, "cp-clients", v2["C2"],
                                                   supply_db.REJECTED_SCHEMA),
            from_schema=supply_db.REJECTED_SCHEMA, actor="fixture@example.org",
            actor_kind=decision_log.PERSON, effective_at="2024-11-21T10:00:00+08:00",
            reason="test: un-rejected", supply_is_red=True)
    assert sc.holder("cp-clients", Q4) == v2["C2"], "precondition: un-rejected"
    with supply_db.connect(read_only=True, label="pytest") as conn:
        root = root_cause.root_of(conn, "cp-notifications", v2["N2"], Q4)
    assert root is not None and root.supply == v2["C2"]


def test_staggered_order_b_red_raises_two_tickets(sc):
    """Clients v2's 9:00 hold-back is a real failure against Notifications v1
    naming no other supply; Notifications v2 at 9:05 is red on its own data.
    Each is its own root, and neither names the other as held back - Clients
    v2's own ticket says nothing of Notifications v2. (Notifications v2 waits
    beside its promoted v1, a slot that reads PROMOTED and so has no ticket
    under REQ-PIPE-083.)"""
    from qa_tools.common import root_cause, supply_db

    first_time(sc)
    n1 = sc.deliver("2024-10-27T10:00:00+08:00", {"cp_notifications": "N1"})["N1"]
    sc.process()
    sc.promote_by_hand(n1, Q4, at="2024-10-28T10:00:00+08:00")
    sc.rules += [own_red("N2"), cross_red("cp-notifications", "cp_clients",
                                          when={"cp_clients": "C2",
                                                "cp_notifications": "N1"})]
    c2 = sc.deliver("2024-11-05T09:00:00+08:00", {"cp_clients": "C2"})["C2"]
    sc.process()
    n2 = sc.deliver("2024-11-05T09:05:00+08:00", {"cp_notifications": "N2"})["N2"]
    sc.process()
    with supply_db.connect(read_only=True, label="pytest") as conn:
        assert root_cause.root_of(conn, "cp-clients", c2, Q4) is None
        assert root_cause.root_of(conn, "cp-notifications", n2, Q4) is None
    service = _tickets()
    assert f"cp-clients/{Q4}" in service.tickets
    assert "Also held back by this" not in service.bodies[f"cp-clients/{Q4}"]


def test_s14_placements_root_names_nothing_it_does_not_hold(sc):
    """Q13: a first-time zip of all six tables, Placements v2 red on its own
    data - only Placements is ticketed, naming nothing else."""
    sc.rules.append(own_red("P2"))
    # 2024-Q3, which every table owes (Case Workers owes February and August).
    got = sc.deliver("2024-07-25T10:00:00+08:00", {
        "cp_clients": "C2", "cp_notifications": "N2", "cp_investigations": "I2",
        "cp_placements": "P2", "cp_carers": "K2", "cp_case_workers": "W2"})
    sc.process()
    assert all(sc.holder(s.split("@")[0], Q3) == s for lab, s in got.items() if lab != "P2")
    service = _tickets(now="2024-07-30T10:00:00+08:00")
    mine = [k for k in service.tickets if k.endswith(Q3)]
    assert mine == [f"cp-placements/{Q3}"], mine
    assert "Also held back by this" not in service.bodies[f"cp-placements/{Q3}"]


def test_s1_green_writes_no_still_failing_record_about_unchanged_blank_values(sc):
    """S1 green: Clients v2's promotion re-checks its readers, and
    Notifications v2's own blank values - which nobody's promotion affected -
    get no still-failing record."""
    established(sc)
    sc.rules.append(own_red("N2"))
    sc.deliver("2024-08-05T10:00:00+08:00", {"cp_clients": "C2", "cp_notifications": "N2"})
    sc.process()
    assert _still_failing(sc) == []


def test_not_yet_due_root_raises_no_ticket_until_overdue(sc):
    """Notifications v2 red only because Clients is not due yet: no ticket for
    the hold-back at all; once Clients is overdue, its slot's ticket names
    Notifications v2."""
    first_time(sc)
    sc.deliver("2024-11-01T08:40:00+08:00", {"cp_notifications": "N2"})
    sc.process()
    early = _tickets(now="2024-11-01T08:50:00+08:00")
    assert f"cp-notifications/{Q4}" not in early.tickets
    assert f"cp-clients/{Q4}" not in early.tickets
    late = _tickets(now="2024-11-03T10:00:00+08:00")
    assert f"cp-notifications/{Q4}" not in late.tickets
    assert "(cp-notifications)" in late.bodies[f"cp-clients/{Q4}"]


def test_owed_recheck_raises_nothing(sc, monkeypatch):
    """A supply whose only red is an owed re-check - the knock-on of a
    person's promotion made to fail - gets no ticket and no still-failing
    record. ON AN UNFILLED PERIOD, where a waiting supply's slot does raise a
    ticket (post-build-review #274: written over an all-promoted period this
    test could not fail, since no slot there needs a person). Notifications v2
    waits, red for want of a Client Register; Clients v2 arrives red and a
    person promotes it, and the knock-on that would re-gate Notifications v2
    is made to fail - so its red is one the owed re-evaluation clears."""
    from qa_tools.common import knock_on, recheck

    first_time(sc)
    n = sc.deliver("2024-11-03T10:00:00+08:00", {"cp_notifications": "N2"})
    sc.process()
    assert _tickets(now="2024-11-03T12:00:00+08:00").tickets.get(f"cp-clients/{Q4}"), \
        "precondition: a Client Register is owed and overdue, so this period is ticketed"
    c = sc.deliver("2024-11-04T10:00:00+08:00", {"cp_clients": "C2"})
    sc.rules.append(own_red("C2"))
    sc.process()
    before = len(_still_failing(sc))

    def broken(item, **kw):
        recheck.fail(item.id, "made to fail (test)")
        return recheck.Outcome(item.id, "", False, "made to fail (test)")
    monkeypatch.setattr(knock_on, "complete", broken)
    sc.promote_by_hand(c["C2"], Q4, at="2024-11-10T10:00:00+08:00", follow_up=True)
    assert [o.period for o in sc.owed("reevaluate")] == [Q4], "precondition: owed"
    assert sc.holder("cp-notifications", Q4) is None, "precondition: N2 still waits"
    # RED ONLY FOR WANT OF A CLIENT REGISTER IS HELD BACK, NOT REFUSED (Keith,
    # 2026-10-25, answer 2a): another table's doing, not its own checks failing.
    assert sc.actions(n["N2"])[-1] == "promotion-withheld"
    service = _tickets(now="2024-11-20T10:00:00+08:00")
    assert f"cp-notifications/{Q4}" not in service.tickets
    assert len(_still_failing(sc)) == before


def test_an_owed_recheck_does_not_quiet_a_failure_of_its_own(sc, monkeypatch):
    """NO FALSE QUIET (NFR 3): the same owed re-evaluation, but Notifications
    v2 is ALSO red on its own data - its ticket is raised as today."""
    from qa_tools.common import knock_on, recheck

    first_time(sc)
    sc.rules.append(own_red("N2"))
    sc.deliver("2024-11-03T10:00:00+08:00", {"cp_notifications": "N2"})
    sc.process()
    c = sc.deliver("2024-11-04T10:00:00+08:00", {"cp_clients": "C2"})
    sc.rules.append(own_red("C2"))
    sc.process()

    def broken(item, **kw):
        recheck.fail(item.id, "made to fail (test)")
        return recheck.Outcome(item.id, "", False, "made to fail (test)")
    monkeypatch.setattr(knock_on, "complete", broken)
    sc.promote_by_hand(c["C2"], Q4, at="2024-11-10T10:00:00+08:00", follow_up=True)
    assert sc.owed("reevaluate"), "precondition: owed"
    assert f"cp-notifications/{Q4}" in _tickets(now="2024-11-20T10:00:00+08:00").tickets


def test_a_failed_recheck_against_the_warehouse_is_its_own_root(sc):
    """Keith, 2026-10-25, answer 3a (post-build-review #274 Q3): the root is
    the supply whose OWN check failed. Notifications v2 is held back because
    its re-check against Clients v1 in the warehouse FAILED - re-checked only
    because its package-mate Clients v2 was red - so its 'promotion-withheld'
    still names Clients v2 as the cause (REQ-PIPE-267 criterion 13), and it
    is its own root: ticketed in its own slot, in no other's list."""
    from qa_tools.common import root_cause, supply_db

    first_time(sc)
    c1 = sc.deliver("2024-10-26T10:00:00+08:00", {"cp_clients": "C1"})["C1"]
    sc.process()
    sc.promote_by_hand(c1, Q4, at="2024-10-27T10:00:00+08:00")
    sc.rules += [own_red("C2"), cross_red("cp-notifications", "cp_clients",
                                          when={"cp_clients": "C1",
                                                "cp_notifications": "N2"})]
    v2 = sc.deliver("2024-11-03T10:00:00+08:00", {"cp_clients": "C2", "cp_notifications": "N2"})
    sc.process()
    assert sc.holder("cp-clients", Q4) == c1
    withheld = [d for d in sc.decisions(v2["N2"]) if d["action"] == "promotion-withheld"]
    assert withheld and withheld[-1]["held_back_by"] == v2["C2"], "precondition: named"
    assert withheld[-1]["held_back_detail"]["failed"] is True
    with supply_db.connect(read_only=True, label="pytest") as conn:
        assert root_cause.root_of(conn, "cp-notifications", v2["N2"], Q4) is None
    service = _tickets(now="2024-11-04T10:00:00+08:00")
    assert f"cp-notifications/{Q4}" in service.tickets
    assert "Also held back by this" not in service.bodies[f"cp-notifications/{Q4}"]


def test_a_could_not_be_checked_hold_back_is_another_tables_doing(sc):
    """The other side of 3a: Notifications v2's re-check could not be checked
    at all - no Client Register in the warehouse - so its root stays its red
    package-mate Clients v2 (S2 strict), recorded failed: false."""
    from qa_tools.common import root_cause, supply_db

    first_time(sc)
    sc.rules.append(own_red("C2"))
    v2 = sc.deliver("2024-11-03T10:00:00+08:00", {"cp_clients": "C2", "cp_notifications": "N2"})
    sc.process()
    withheld = [d for d in sc.decisions(v2["N2"]) if d["action"] == "promotion-withheld"]
    assert withheld[-1]["held_back_detail"]["failed"] is False
    with supply_db.connect(read_only=True, label="pytest") as conn:
        root = root_cause.root_of(conn, "cp-notifications", v2["N2"], Q4)
    assert root is not None and root.supply == v2["C2"]


def test_a_root_whose_slot_raises_nothing_leaves_what_it_holds_back_ticketed(monkeypatch):
    """NO FALSE QUIET (NFR 3; post-build-review #274 D4): a supply held back
    by a root whose own slot raises nothing (it reads PROMOTED - a red
    resupply beside a promoted one) is ticketed on its own, never folded into
    a ticket that does not exist; only a root NOT YET DUE (criterion 3) holds
    it back with no ticket. On the folding rule itself, since under 3a the
    scenario that first showed it is its own root (the test above)."""
    from types import SimpleNamespace

    from qa_tools.common import root_cause, slot_state

    def state(dataset_id, supply, st, needs):
        return SimpleNamespace(key=f"{dataset_id}/{Q4}", supply=supply, state=st,
                               dataset_id=dataset_id, period=Q4, needs_action=needs)
    held = state("cp-notifications", "cp-notifications@n2", slot_state.AWAITING_DECISION,
                 True)
    root = root_cause.Root("supply", "cp-clients", Q4, supply="cp-clients@c2")
    monkeypatch.setattr(root_cause, "red_only_owed", lambda *a: False)
    monkeypatch.setattr(root_cause, "root_of",
                        lambda conn, ds, sup, p: root if ds == "cp-notifications" else None)
    promoted = state("cp-clients", "cp-clients@c1", slot_state.PROMOTED, False)
    assert root_cause.held_back_by_roots(None, [held, promoted]) == ({}, set())
    due_later = state("cp-clients", None, slot_state.NOT_YET_DUE, False)
    assert root_cause.held_back_by_roots(None, [held, due_later]) == (
        {f"cp-clients/{Q4}": [held]}, {held.key})


def test_a_failure_of_its_own_is_ticketed_naming_what_else_holds_it_back(sc):
    """Criterion 6: Notifications v2 red on its own data AND unable to run its
    Client reference for want of a Clients is ticketed as today, its ticket
    naming the missing table beside its own failure."""
    first_time(sc)
    sc.rules.append(own_red("N2"))
    sc.deliver("2024-11-03T10:00:00+08:00", {"cp_notifications": "N2"})
    sc.process()
    service = _tickets(now="2024-11-03T12:00:00+08:00")
    body = service.bodies[f"cp-notifications/{Q4}"]
    assert "Also held back for want of cp_clients" in body
