"""One definition of what a slot holds, in the database (REQ-PIPE-130
criteria 8 and 9).

`qa.slot_holds(dataset, as_at)` is the only place the rule lives now. This
holds it to the rule as it was written in Python before the move
(post-build-review #84's walk, kept here as the ORACLE): forty
random decision sequences, compared slot by slot and instant
by instant.
A rule stated twice drifts; stated once and tested against the old
statement, the move is proven rather than hoped.
"""
from __future__ import annotations

import random
import uuid

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import qa_store, supply_db

HELD_AS = {dl.PROMOTE: dl.PROMOTED, dl.REFILE: dl.PROMOTED,
           dl.SUBSTITUTE: dl.SUBSTITUTED, dl.INHERIT: dl.INHERITED}
CHANGES_A_SLOT = (dl.PROMOTE, dl.REFILE, dl.SUBSTITUTE, dl.INHERIT, dl.REJECT,
                  dl.DEMOTE, dl.DE_SUBSTITUTE, dl.UN_INHERIT)
MOVES_A_SUPPLY = (dl.REJECT, dl.DEMOTE, dl.REFILE)


def oracle(rows, slot):
    """The rule, as REQ-PIPE-130 states it: (held_as, holder, id of the
    last entry that changed the slot). It began as post-build-review
    #84's Python walk and was corrected overnight (delivery-critic,
    sprint 2): an entry about another supply leaves an INHERITED slot
    alone too, and only decisions that change a slot are read at all."""
    held_as, holder, last = None, None, None
    for r in rows:
        if r["action"] not in CHANGES_A_SLOT or slot not in (r["to_slot"], r["from_slot"]):
            continue
        if r["to_slot"] == slot:
            held_as, holder, last = HELD_AS.get(r["action"]), r["supply"], r["id"]
        elif r["action"] in MOVES_A_SUPPLY and holder and r["supply"] != holder:
            continue
        else:
            held_as, holder, last = None, None, r["id"]
    return held_as, holder, last


SLOTS = ("2099-Q1", "2099-Q2", "2099-Q3")
SUPPLIES = ("s1", "s2", "s3")


def random_decision(rng):
    action = rng.choice([dl.PROMOTE, dl.PROMOTE, dl.REJECT, dl.DEMOTE, dl.REFILE,
                         dl.SUBSTITUTE, dl.DE_SUBSTITUTE, dl.INHERIT,
                         dl.UN_INHERIT, dl.PROMOTION_WITHHELD])
    a, b = rng.sample(SLOTS, 2)
    shape = {
        dl.PROMOTE: (None, a, None), dl.PROMOTION_WITHHELD: (None, a, None),
        dl.REJECT: (a, None, None), dl.DEMOTE: (a, None, None),
        dl.REFILE: (a, b, None), dl.SUBSTITUTE: (None, a, b),
        dl.DE_SUBSTITUTE: (a, None, None), dl.INHERIT: (None, a, b),
        dl.UN_INHERIT: (a, None, None),
    }[action]
    return action, rng.choice(SUPPLIES), *shape


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-slot-holds") as c:
        qa_store.ensure_schema(c)
        yield c


def _insert(conn, dataset, seq):
    for i, (action, supply, from_slot, to_slot, stands_on) in enumerate(seq):
        conn.execute(
            f"INSERT INTO {dl.TABLE} (agency_id, collection_id, dataset_id, action, "
            "supply, from_slot, to_slot, actor, actor_kind, effective_at, stands_on) "
            "VALUES ('a', 'c', ?, ?, ?, ?, ?, 'test', 'rule', ?, ?)",
            [dataset, action, supply, from_slot, to_slot,
             # EVERY THIRD PAIR SHARES AN INSTANT, so the id tie-break at
             # equal effective_at is exercised, not assumed.
             f"2099-01-01T00:{(i - i // 3) // 60:02d}:{(i - i // 3) % 60:02d}+00:00",
             stands_on])
    return [dict(zip(("id", "action", "supply", "from_slot", "to_slot", "effective_at"), r))
            for r in conn.execute(
                f"SELECT id, action, supply, from_slot, to_slot, effective_at "
                f"FROM {dl.TABLE} WHERE dataset_id = ? ORDER BY effective_at, id",
                [dataset]).fetchall()]


def _view(conn, dataset, as_at=None):
    return {slot: (held_as, holder, last) for slot, held_as, holder, last in conn.execute(
        f'SELECT slot, held_as, holder, decision_id FROM "{qa_store.SCHEMA}".slot_holds(?, ?)',
        [dataset, as_at]).fetchall()}


@pytest.mark.parametrize("seed", range(40))
def test_the_view_agrees_with_the_rule_it_replaced(conn, seed):
    rng = random.Random(seed)
    dataset = f"cp-{uuid.uuid4().hex[:10]}"
    rows = _insert(conn, dataset, [random_decision(rng) for _ in range(rng.randint(1, 25))])
    got = _view(conn, dataset)
    for slot in SLOTS:
        expected = oracle(rows, slot)
        if expected == (None, None, None):
            assert slot not in got, (seed, slot)
        else:
            assert got.get(slot) == expected, (seed, slot, rows)
    # AND AS AT EVERY INSTANT IN THE SEQUENCE (criterion 8's as-at form).
    for cut in range(len(rows)):
        instant = rows[cut]["effective_at"]
        # As at an instant means EVERY decision effective by then, so
        # the expected answer reads every row sharing it too.
        prefix = [r for r in rows if r["effective_at"] <= instant]
        got = _view(conn, dataset, instant)
        for slot in SLOTS:
            expected = oracle(prefix, slot)
            if expected == (None, None, None):
                assert slot not in got, (seed, cut, slot)
            else:
                assert got.get(slot) == expected, (seed, cut, slot)


def test_one_dataset_s_history_is_not_read_for_another(conn):
    a, b = (f"cp-{uuid.uuid4().hex[:10]}" for _ in range(2))
    _insert(conn, a, [(dl.PROMOTE, "s1", None, "2099-Q1", None)])
    assert _view(conn, b) == {}


# ---------------------------------------------------------------------------
# The readers ask the view how a slot is held - never an action
# (delivery-critic, overnight sprint 2). Each of these reproduced a wrong
# answer against the code before the fix.
# ---------------------------------------------------------------------------


@pytest.fixture
def quarters(monkeypatch):
    from datetime import date

    from qa_tools.common import drift_reference, schedule
    dates = {"2099-Q1": date(2099, 1, 1), "2099-Q2": date(2099, 4, 1),
             "2099-Q3": date(2099, 7, 1), "2099-Q4": date(2099, 10, 1)}
    for mod in (schedule, drift_reference.schedule):
        monkeypatch.setattr(mod, "date_of", lambda name, ds: dates.get(name))
    return dates


REFILED_OUT = [(dl.PROMOTE, "s0", None, "2099-Q1", None),
               (dl.PROMOTE, "s1", None, "2099-Q2", None),
               (dl.REFILE, "s1", "2099-Q2", "2099-Q3", None)]


class TestARefileOutLeavesItsSlotEmptyForEveryReader:
    """Q2's last change is a re-file OUT, whose action is 'refile'.
    Reading that as "holds a supply" made the emptied Q2 read as
    promoted - to the queue, to substitution and to the drift
    reference."""

    def test_the_view_says_empty(self, conn):
        dataset = f"cp-{uuid.uuid4().hex[:10]}"
        _insert(conn, dataset, REFILED_OUT)
        h = dl.held(conn, dataset, "2099-Q2")
        assert h.held_as is None and h.action == dl.REFILE

    def test_the_queue_reads_it_as_returned_not_promoted(self, conn):
        from qa_tools.common import slot_state
        dataset = f"cp-{uuid.uuid4().hex[:10]}"
        _insert(conn, dataset, REFILED_OUT)
        state, _ = slot_state._state_from(dl.held(conn, dataset, "2099-Q2"))
        assert state == slot_state.RETURNED

    def test_substitution_may_fill_it_and_may_not_stand_on_it(self, conn):
        from qa_tools.common import substitution
        dataset = f"cp-{uuid.uuid4().hex[:10]}"
        _insert(conn, dataset, REFILED_OUT)
        # Filling the empty Q2 by substitution is allowed...
        substitution._refuse_unless_substitutable(
            conn, dataset_id=dataset, period="2099-Q2", stands_on="2099-Q1",
            supply="s0", participates=True)
        # ...standing on it is not: it holds nothing.
        with pytest.raises(substitution.SubstitutionRefused, match="holds no promoted supply"):
            substitution._refuse_unless_substitutable(
                conn, dataset_id=dataset, period="2099-Q4", stands_on="2099-Q2",
                supply="s1", participates=True)

    def test_the_drift_reference_is_not_the_supplys_own_file(self, conn, quarters):
        from qa_tools.common import drift_reference
        dataset = f"cp-{uuid.uuid4().hex[:10]}"
        _insert(conn, dataset, REFILED_OUT)
        got = drift_reference.reference_for(conn, dataset, "2099-Q3")
        assert (got.period, got.supply) == ("2099-Q1", "s0")


class TestTheReadersThatUsedToWalkTheLogThemselves:
    def test_newest_promoted_survives_a_withheld_note(self, conn):
        from qa_tools.common import promotion
        dataset = f"cp-{uuid.uuid4().hex[:10]}"
        _insert(conn, dataset, [(dl.PROMOTE, "s0", None, "2099-Q1", None),
                                (dl.PROMOTION_WITHHELD, "s9", None, "2099-Q1", None)])
        assert promotion.newest_promoted(conn, dataset, "2099-Q1") == "s0"

    def test_inheritance_never_points_at_a_demoted_supply(self, conn, quarters):
        from qa_tools.common import inheritance
        dataset = f"cp-{uuid.uuid4().hex[:10]}"
        _insert(conn, dataset, [(dl.PROMOTE, "s0", None, "2099-Q1", None),
                                (dl.PROMOTE, "s1", None, "2099-Q2", None),
                                (dl.DEMOTE, "s1", "2099-Q2", None, None)])
        assert inheritance._most_recent_promoted(conn, dataset, before="2099-Q4") == \
            ("2099-Q1", "s0")

    def test_inheritance_still_finds_a_period_with_a_withheld_note(self, conn, quarters):
        from qa_tools.common import inheritance
        dataset = f"cp-{uuid.uuid4().hex[:10]}"
        _insert(conn, dataset, [(dl.PROMOTE, "s0", None, "2099-Q1", None),
                                (dl.PROMOTION_WITHHELD, "s9", None, "2099-Q1", None)])
        assert inheritance._most_recent_promoted(conn, dataset, before="2099-Q3") == \
            ("2099-Q1", "s0")

    def test_the_newest_promoted_supply_falls_back_past_an_emptied_slot(self, conn):
        dataset = f"cp-{uuid.uuid4().hex[:10]}"
        _insert(conn, dataset, [(dl.PROMOTE, "s0", None, "2099-Q1", None),
                                (dl.PROMOTE, "s1", None, "2099-Q2", None),
                                (dl.DEMOTE, "s1", "2099-Q2", None, None)])
        assert dl.promoted_supply(conn, dataset)["supply"] == "s0"

    def test_a_reject_of_another_supply_leaves_an_inherited_slot_inherited(self, conn):
        dataset = f"cp-{uuid.uuid4().hex[:10]}"
        _insert(conn, dataset, [(dl.PROMOTE, "s0", None, "2099-Q1", None),
                                (dl.INHERIT, "s0", None, "2099-Q2", "2099-Q1"),
                                (dl.REJECT, "s7", "2099-Q2", None, None)])
        h = dl.held(conn, dataset, "2099-Q2")
        assert (h.held_as, h.holder) == (dl.INHERITED, "s0")
        assert dl.periods_standing_on(conn, dataset, "s0") == ("2099-Q2",)
