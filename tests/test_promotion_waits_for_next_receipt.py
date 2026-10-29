"""Both orchestrators cap a replayed promotion at the next receipt
(REQ-PIPE-081, Keith's #117 D5) - post-build-review #122 found no test
failed if `before=next_receipt(...)` was dropped from either call site.

Driven through each real promote_after(), with the gate and the knock-on
stubbed: the instant it hands the promotion must land before the next
file of the same dataset arrived, never after it."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from qa_tools.common import knock_on, promotion
from qa_tools.tools import orchestrate

COLLECTIONS = ["civil-registration", "child-protection"]

RECEIVED = datetime(2023, 4, 3, 9, 0, tzinfo=timezone.utc)
NEXT = RECEIVED + timedelta(seconds=30)


@pytest.mark.parametrize("collection_id", COLLECTIONS, ids=["bdm", "cp"])
def test_the_promotion_lands_before_the_next_receipt(collection_id, monkeypatch):
    from qa_tools.common import gate

    stamped = []
    monkeypatch.setattr(promotion, "next_receipt", lambda arrival: NEXT)
    monkeypatch.setattr(gate, "after_arrival",
                        lambda collection_id, arrival, **k: stamped.append(k["effective_at"])
                        or gate.Applied())
    monkeypatch.setattr(gate, "report", lambda *a, **k: None)
    monkeypatch.setattr(knock_on, "follow_up", lambda *a, **k: [])
    # A run id whose seeded lag is far longer than thirty seconds, so the
    # cap is what keeps it before the next receipt.
    arrival = SimpleNamespace(received_at=RECEIVED, run_id="run_lag_probe")
    assert promotion.effective_at_for(RECEIVED, seed="run_lag_probe") > NEXT, (
        "test precondition - the uncapped lag must reach past the next receipt")
    orchestrate.promote_after(collection_id, arrival, [], "t@example.com")
    [effective] = stamped
    at = datetime.fromisoformat(effective)
    assert RECEIVED <= at < NEXT


class TestTheNextReceiptIsKnownInAReplay:
    """REQ-TEST-159 records each delivery at its FIRST ARRIVAL, so in a replay
    the next delivery is not yet in the database when this one is promoted.
    The cap must still see it - from the arrivals the replay is reading - or
    an invented lag runs past the next supply and two versions show waiting
    at once (Keith's #117 D5), which is what the whole-bootstrap comparison
    caught: 29 promotions' effective_at moved past the next receipt."""

    def _tree(self, root, rows):
        import json

        for seq, (name, received) in enumerate(rows, start=1):
            (root / "deliveries" / name).mkdir(parents=True)
            (root / "receipts" / name).mkdir(parents=True)
            (root / "deliveries" / name / "cp_clients.csv").write_text(
                "client_id,given_name\n1,Ann\n")
            (root / "receipts" / name / "cp_clients.csv.json").write_text(json.dumps({
                "delivery": name, "file": "cp_clients.csv", "received_at": received,
                "received_from": "storage", "sequence": seq,
                "filed_by": {"kind": "automated"}}))

    def test_an_unrecorded_next_arrival_in_the_tree_caps_the_lag(
            self, tmp_path, monkeypatch, clean_delivery_log):
        from qa_tools.common import arrivals, delivery

        self._tree(tmp_path, [("Extract A", "2023-04-03T09:00:00+00:00"),
                              ("Extract B", "2023-04-03T09:00:30+00:00")])
        monkeypatch.setattr(delivery, "DELIVERIES_DIR", tmp_path / "deliveries")
        monkeypatch.setattr(delivery, "RECEIPTS_DIR", tmp_path / "receipts")
        first, second = arrivals.arrivals_for("child-protection", "")
        assert promotion.next_receipt(first) == second.received_at
        assert promotion.next_receipt(second) is None


class TestWithinTheClaimWindowInAReplay:
    """A replayed rule decision takes effect within the dataset's claim
    window after receipt, as a scheduled pass would reach it (Keith,
    2026-10-11, REQ-GEN-185) - SPREAD across it, not piled on its edge
    (post-build-review #156: capping a 1-hour-to-3-day lag put 25 of 33
    promotions at exactly 4:00; Keith: spread 1h-4h). ON EVERY ROUTE, not
    only in a replay: the terminal and Lambda routes invent the same seeded
    lag for a past-dated receipt, and REQ-PIPE-086 criterion 11 needs the
    three to record the same decision (tests/test_kept_routes_agree.py)."""

    def test_the_lag_spreads_across_the_window(self):
        received = datetime(2026, 9, 17, 6, 0, tzinfo=timezone.utc)
        window = timedelta(hours=4)
        lags = [promotion.effective_at_for(received, seed=f"run_{n}", within=window) - received
                for n in range(60)]
        assert all(timedelta(hours=1) <= lag <= window for lag in lags)
        assert len(set(lags)) > 50, "the lag must spread, not sit on one value"
        assert sum(lag == window for lag in lags) <= 2

    def test_without_a_window_the_lag_is_as_it_was(self):
        received = datetime(2026, 9, 17, 6, 0, tzinfo=timezone.utc)
        assert promotion.effective_at_for(received, seed="run_lag_probe") == \
            promotion.effective_at_for(received, seed="run_lag_probe", within=None)

    @pytest.mark.parametrize("collection_id", COLLECTIONS, ids=["bdm", "cp"])
    @pytest.mark.parametrize("replaying", [True, False], ids=["replay", "live"])
    def test_both_collections_pass_it_on_every_route(self, collection_id, replaying,
                                                      monkeypatch):
        from qa_tools.common import replay_clock, schedule

        seen = {}
        real = promotion.effective_at_for

        def spy(received_at, **kw):
            seen.update(kw)
            return real(received_at, **kw)
        monkeypatch.setattr(replay_clock, "active", lambda: replaying)
        monkeypatch.setattr(promotion, "effective_at_for", spy)
        from qa_tools.common import gate

        monkeypatch.setattr(promotion, "next_receipt", lambda arrival: None)
        monkeypatch.setattr(gate, "after_arrival", lambda *a, **k: gate.Applied())
        monkeypatch.setattr(gate, "report", lambda *a, **k: None)
        monkeypatch.setattr(knock_on, "follow_up", lambda *a, **k: [])
        # The arrival carries ITS collection's dataset: the shared orchestrator
        # takes the window from the files carried (REQ-PIPE-243 criterion 2),
        # and only the adapter's claim-window dataset where none are named.
        dataset = "birth-registrations" if collection_id == "civil-registration" else "cp-clients"
        arrival = SimpleNamespace(received_at=RECEIVED, run_id="run_x",
                                  files_by_dataset={dataset: "x"})
        orchestrate.promote_after(collection_id, arrival, [], "t@example.com")
        expected = schedule.claim_window(dataset, on=RECEIVED.date())
        assert seen["within"] == expected


def test_no_supply_is_held_back_after_the_promotion_that_ended_it(deployment_history):
    """post-build-review #276, on the bootstrapped history: read by effective
    time, as the as-at view and the history read it, a staggered file's
    'promotion-withheld' never takes effect after the later application that
    promoted it. Eleven did on the bootstrap before the fix (3279bc8), TS-84's
    three among them; Keith's option (b), 2026-10-27, floors the promotion."""
    from qa_tools.common import supply_db

    with supply_db.connect(read_only=True, label="test-276") as conn:
        withheld = conn.execute(
            "SELECT count(*) FROM qa.decision WHERE action = 'promotion-withheld'").fetchone()[0]
        late = conn.execute(
            "SELECT w.supply, w.effective_at, p.effective_at FROM qa.decision w "
            "JOIN qa.decision p ON p.supply = w.supply AND p.action = 'promote' "
            "WHERE w.action = 'promotion-withheld' AND w.id < p.id "
            "AND w.effective_at > p.effective_at ORDER BY w.supply").fetchall()
    assert withheld, "the history holds no withheld promotion - the test would prove nothing"
    assert not late, late


def test_no_decision_about_a_supply_takes_effect_before_one_recorded_earlier(
        deployment_history):
    """post-build-review #284 (2), on the bootstrapped history: for EVERY
    ordered pair of decisions about one supply, the one recorded later never
    takes effect before the one recorded earlier - so the order the log was
    written in is the order read by effective time. The 2026-10-28 history had
    three inversions, each a person's decision recorded after a rule's lagged
    refusal: TS-67's re-file, TS-77a's promotion and TS-80's choose-file."""
    from qa_tools.common import supply_db

    with supply_db.connect(read_only=True, label="test-284") as conn:
        about_a_supply = conn.execute(
            "SELECT count(*) FROM qa.decision WHERE supply IS NOT NULL").fetchone()[0]
        inverted = conn.execute(
            "SELECT a.supply, a.action, a.effective_at, b.action, b.effective_at "
            "FROM qa.decision a JOIN qa.decision b ON b.dataset_id = a.dataset_id "
            "AND b.supply = a.supply AND b.id > a.id "
            "WHERE b.effective_at < a.effective_at ORDER BY a.supply, a.id, b.id").fetchall()
    assert about_a_supply, "the history holds no decision about a supply - nothing proved"
    assert not inverted, inverted


def test_every_gate_application_takes_one_instant(deployment_history):
    """post-build-review #284 (1), Keith's option (b), on the bootstrapped
    history: every promotion and hold-back one gate application writes takes
    ONE effective instant (REQ-PIPE-266 criterion 4). The per-member floor
    split four applications on the 2026-10-28 history (26, 173, 205, 216)."""
    from qa_tools.common import supply_db

    with supply_db.connect(read_only=True, label="test-284") as conn:
        applications = conn.execute(
            "SELECT count(DISTINCT gate_application) FROM qa.decision "
            "WHERE gate_application IS NOT NULL").fetchone()[0]
        split = conn.execute(
            "SELECT gate_application, count(DISTINCT effective_at), min(effective_at), "
            "max(effective_at) FROM qa.decision WHERE gate_application IS NOT NULL "
            "AND action IN ('promote', 'promotion-withheld', 'promotion-refused') "
            "GROUP BY gate_application "
            "HAVING count(DISTINCT effective_at) > 1 ORDER BY 1").fetchall()
    assert applications, "the history holds no gate application - nothing proved"
    assert not split, split


#: A PERSON'S ONE ACT as the log shows it, which has no act column: a person's
#: decision naming another person's as its cause (a settlement's per-file
#: entries name its choose-file), or two of one person's decisions written
#: back to back for one dataset and period with the same reason (a
#: promotion's de-substitute or supersession and the promotion itself).
_ONE_ACT = """
WITH d AS (
  SELECT id, dataset_id, actor, actor_kind, reason, effective_at,
         coalesce(to_slot, from_slot) AS period,
         lag(id) OVER w AS prev_id, lag(actor_kind) OVER w AS prev_kind,
         lag(actor) OVER w AS prev_actor, lag(reason) OVER w AS prev_reason,
         lag(coalesce(to_slot, from_slot)) OVER w AS prev_period
  FROM qa.decision WINDOW w AS (PARTITION BY dataset_id ORDER BY id))
SELECT prev_id AS first, id AS second FROM d
WHERE actor_kind = 'person' AND prev_kind = 'person' AND actor = prev_actor
  AND reason = prev_reason AND period = prev_period
UNION
SELECT c.id, d.id FROM qa.decision d JOIN qa.decision c ON c.id = d.caused_by_decision
  AND c.dataset_id = d.dataset_id
WHERE d.actor_kind = 'person' AND c.actor_kind = 'person'
"""


def test_a_persons_one_act_takes_one_instant(deployment_history):
    """post-build-review #284 (B), Keith 2026-10-30 (W2), on the bootstrapped
    history: every decision of one person's act takes ONE effective instant,
    the latest across the supplies it touches - widening the pair test above
    from decisions about one supply to an act over several. The 2026-10-29
    history split two: TS-77a's de-substitute (9 June 2023) and promotion (14
    June), and TS-80's choose-file (8 November 2020) and reject (2 November)."""
    from qa_tools.common import supply_db

    with supply_db.connect(read_only=True, label="test-284") as conn:
        pairs = conn.execute(f"SELECT count(*) FROM ({_ONE_ACT}) a").fetchone()[0]
        split = conn.execute(
            f"SELECT a.first, f.dataset_id, f.action, f.effective_at, s.action, s.effective_at "
            f"FROM ({_ONE_ACT}) a JOIN qa.decision f ON f.id = a.first "
            "JOIN qa.decision s ON s.id = a.second "
            "WHERE f.effective_at <> s.effective_at ORDER BY a.first").fetchall()
    assert pairs, "the history holds no person's act of two decisions - nothing proved"
    assert not split, split
