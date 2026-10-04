"""One definition of what a slot holds, in the database (REQ-PIPE-130
criteria 8 and 9).

`qa.slot_holds(dataset, as_at)` is the only place the rule lives now. This
holds it to the rule as it was written in Python before the move
(post-build-review #84's walk, kept here as the ORACLE): thousands of
random decision sequences, compared slot by slot and instant by instant.
A rule stated twice drifts; stated once and tested against the old
statement, the move is proven rather than hoped.
"""
from __future__ import annotations

import random
import uuid

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import qa_store, supply_db

FILLS = (dl.PROMOTE, dl.REFILE, dl.SUBSTITUTE)
EMPTIES_IF_ITS_OWN = (dl.REJECT, dl.DEMOTE, dl.REFILE)
REFUSALS = (dl.PROMOTION_WITHHELD, dl.INHERIT_REFUSED)


def oracle(rows, slot):
    """The rule as decision_log.promoted_into() walked it in Python
    (2026-10-04, post-build-review #84): (fills, id of the last entry that
    changed the slot)."""
    fills, last = None, None
    for r in rows:
        if r["action"] in REFUSALS or slot not in (r["to_slot"], r["from_slot"]):
            continue
        if r["to_slot"] == slot:
            fills = r["supply"] if r["action"] in FILLS else None
            last = r["id"]
        elif (r["action"] in EMPTIES_IF_ITS_OWN and fills
              and r["supply"] != fills):
            continue
        else:
            fills, last = None, r["id"]
    return fills, last


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
             f"2099-01-01T00:{i // 60:02d}:{i % 60:02d}+00:00", stands_on])
    return [dict(zip(("id", "action", "supply", "from_slot", "to_slot", "effective_at"), r))
            for r in conn.execute(
                f"SELECT id, action, supply, from_slot, to_slot, effective_at "
                f"FROM {dl.TABLE} WHERE dataset_id = ? ORDER BY effective_at, id",
                [dataset]).fetchall()]


def _view(conn, dataset, as_at=None):
    return {slot: (fills, last) for slot, fills, last in conn.execute(
        f'SELECT slot, fills, decision_id FROM "{qa_store.SCHEMA}".slot_holds(?, ?)',
        [dataset, as_at]).fetchall()}


@pytest.mark.parametrize("seed", range(40))
def test_the_view_agrees_with_the_rule_it_replaced(conn, seed):
    rng = random.Random(seed)
    dataset = f"cp-{uuid.uuid4().hex[:10]}"
    rows = _insert(conn, dataset, [random_decision(rng) for _ in range(rng.randint(1, 25))])
    got = _view(conn, dataset)
    for slot in SLOTS:
        expected = oracle(rows, slot)
        if expected == (None, None):
            assert slot not in got or got[slot][1] is None, (seed, slot)
        else:
            assert got.get(slot) == expected, (seed, slot, rows)
    # AND AS AT EVERY INSTANT IN THE SEQUENCE (criterion 8's as-at form).
    for cut in range(len(rows)):
        prefix = rows[:cut + 1]
        got = _view(conn, dataset, prefix[-1]["effective_at"])
        for slot in SLOTS:
            expected = oracle(prefix, slot)
            if expected != (None, None):
                assert got.get(slot) == expected, (seed, cut, slot)


def test_one_dataset_s_history_is_not_read_for_another(conn):
    a, b = (f"cp-{uuid.uuid4().hex[:10]}" for _ in range(2))
    _insert(conn, a, [(dl.PROMOTE, "s1", None, "2099-Q1", None)])
    assert _view(conn, b) == {}
