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
    record."""
    from qa_tools.common import knock_on

    established(sc)
    v2 = sc.deliver("2024-08-05T10:00:00+08:00", {"cp_notifications": "N2"})
    sc.rules.append(own_red("N2"))
    sc.process()

    def broken(item, **kw):
        from qa_tools.common import recheck

        recheck.fail(item.id, "made to fail (test)")
        return recheck.Outcome(item.id, "", False, "made to fail (test)")
    monkeypatch.setattr(knock_on, "complete", broken)
    sc.promote_by_hand(v2["N2"], Q3, at="2024-09-20T10:00:00+08:00", follow_up=True)
    assert sc.owed("reevaluate"), "precondition: the re-check is owed"
    service = _tickets()
    assert not [k for k in service.tickets if k.endswith(Q3)]
    assert _still_failing(sc) == []


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
