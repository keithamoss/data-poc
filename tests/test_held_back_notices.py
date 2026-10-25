"""The build's half of REQ-DASH-275 (pipeline/held_back_notices.py): a supply
held back with its delivery after a failed re-check against the warehouse,
the chain to its root, what a root holds back, and the card line - from the
gate's structured 'promotion-withheld' entries and the decision log, as at a
date. In memory; the page is tests/test_dashboard_e2e.py's
TestHeldBackWithItsDelivery."""
from __future__ import annotations

from pipeline import cross_table_grid as g
from pipeline import cross_table_notices as ctn
from pipeline import held_back_notices as hb
from qa_tools.common import asset_time

I2 = "cp-investigations@202408051000000800"
N2 = "cp-notifications@202408051000000800"
C2 = "cp-clients@202408051000000800"
N3 = "cp-notifications@202408071000000800"
AT = "2024-08-05T10:30:00+08:00"
RECEIPTS = g.Receipts({I2: "2024-08-05T10:00:00+08:00", N2: "2024-08-05T10:00:00+08:00",
                       C2: "2024-08-05T10:00:00+08:00", N3: "2024-08-07T10:00:00+08:00"})


def _at(text):
    return asset_time.parse_instant(text, "test")


def _withheld(by, *, failed=True, came="package-mate", checks=3):
    return (_at(AT), "promotion-withheld", by, {"failed": failed, "came": came,
                                                "by_received": "2024-08-05T02:00:00+00:00",
                                                "checks": [f"c{i}" for i in range(checks)]})


def _log(**states) -> ctn.Log:
    log = ctn.Log()
    log.gate_instants = {I2: [(_at(AT), "promotion-refused", None, {})],
                         N2: [_withheld(I2)], C2: [_withheld(N2)]}
    log.state_instants = states
    return log


def _unchecked(**states) -> ctn.Log:
    """As _log, but each re-check could not be checked: Investigations v2 the
    root of both."""
    log = _log(**states)
    log.gate_instants[N2] = [_withheld(I2, failed=False)]
    log.gate_instants[C2] = [_withheld(N2, failed=False)]
    return log


def _words(segs):
    return g.words_of(segs)


class TestTheNotice:

    def test_one_step_names_the_package_mate(self):
        n = hb._notice(_log(), N2, hb._end_of("2024-08-05"), RECEIPTS)
        assert n["form"] == "package" and n["root"] == N2, "its own root (Keith Q1 = A)"
        assert _words(n["head"]) == "Held back with the Investigations received with it."
        assert "3 cross-table checks fail against it" in _words(n["body"])
        # "AN Investigations" (a defect found fixing the UX critic's findings on
        # 7093c20): the article agrees with the name that follows it.
        assert "checked again by itself once an Investigations supply is promoted." \
            in _words(n["body"]), _words(n["body"])

    def test_one_check_run_by_three_tools_is_one_check(self):
        """B2 (UX critic on 7093c20; Keith Q2 = a, PROVISIONAL): the notice counts
        checks as the grid's rows do, never each tool's result."""
        log = _log()
        ids = [f"x.y.z.cp-notifications.cp_client_id.relationships_{t}"
               for t in ("dbt", "soda", "datacontract")]
        log.gate_instants[N2] = [(_at(AT), "promotion-withheld", I2,
                                  {"failed": True, "came": "package-mate",
                                   "by_received": "2024-08-05T02:00:00+00:00", "checks": ids})]
        n = hb._notice(log, N2, hb._end_of("2024-08-05"), RECEIPTS)
        assert "and one cross-table check fails against it." in _words(n["body"])

    def test_a_failed_re_check_is_its_own_root(self):
        """ROOT NAMING (functional critic on 7093c20; Keith Q1 = A, PROVISIONAL,
        following answer 3a as root_cause.root_of does for the tickets): a
        supply whose re-check against the warehouse FAILED is its own root - its
        notice names its immediate package-mate, never a chain to another root."""
        n = hb._notice(_log(), C2, hb._end_of("2024-08-05"), RECEIPTS)
        assert n["form"] == "package" and n["root"] == C2, n
        assert _words(n["head"]) == "Held back with the Notifications received with it."
        assert "Investigations" not in _words(n["head"] + n["body"])

    def test_could_not_be_checked_is_not_this_notice(self):
        log = _log()
        log.gate_instants[C2] = [_withheld(N2, failed=False)]
        assert hb._notice(log, C2, hb._end_of("2024-08-05"), RECEIPTS) is None

    def test_turned_down_and_replaced_reword_from_the_log(self):
        down = _log(**{N2: [(_at("2024-08-07T10:00:00+08:00"), "reject", None)]})
        n = hb._notice(down, C2, hb._end_of("2024-08-07"), RECEIPTS)
        assert _words(n["body"]) == ("The Notifications file received with it was turned down; "
                                    "this supply now needs its own decision.")
        assert hb._notice(down, C2, hb._end_of("2024-08-06"), RECEIPTS)["form"] == "package"
        gone = _log(**{N2: [(_at("2024-08-07T10:00:00+08:00"), "supersede", N3)]})
        n = hb._notice(gone, C2, hb._end_of("2024-08-07"), RECEIPTS)
        assert _words(n["body"]) == ("The Notifications received with it has been replaced by the "
                                    "one received 10:00am Wednesday, 7 August 2024; this supply "
                                    "now needs its own decision.")


class TestTheRoot:

    def test_a_root_holds_back_only_what_could_not_be_checked(self):
        """ROOT NAMING A: a supply whose own re-check failed is its own root, so
        it is not on another root's holding list."""
        log = _log()
        held, _days = hb.involved(log)
        assert hb._holding(log, I2, hb._end_of("2024-08-05"), RECEIPTS, held) is None
        assert hb._holding(log, N2, hb._end_of("2024-08-05"), RECEIPTS, held) is None

    def test_a_rejected_root_holds_nothing_back(self):
        """D2 (functional critic on 7093c20): once the ROOT is turned down, what
        it held back is its own root - no holding list under it, and no notice
        naming it on a supply further down the chain."""
        log = _unchecked(**{I2: [(_at("2024-08-07T10:00:00+08:00"), "reject", None)]})
        held, _days = hb.involved(log)
        assert hb._holding(log, I2, hb._end_of("2024-08-06"), RECEIPTS, held) is not None
        assert hb._holding(log, I2, hb._end_of("2024-08-07"), RECEIPTS, held) is None
        assert hb.root_as_at(log, C2, hb._end_of("2024-08-06")) == I2
        # As root_cause.root_of for the tickets: the Notifications is its own
        # root once its cause is turned down, and still holds the Client
        # Register back.
        assert hb.root_as_at(log, C2, hb._end_of("2024-08-07")) == N2
        assert hb.root_as_at(log, N2, hb._end_of("2024-08-07")) is None

    def test_the_root_lists_everything_it_holds_back_and_the_card(self):
        log = _unchecked()
        held, _days = hb.involved(log)
        h = hb._holding(log, I2, hb._end_of("2024-08-05"), RECEIPTS, held)
        assert _words(h["tail"]) == "Holding back with it: Client Register and Notifications."
        # ONE ORDER FOR EVERY LIST OF DATASETS, the hierarchy's (UX critic on
        # 7093c20, S3).
        assert _words(h["card"]) == ("Held back together: Client Register, Notifications and "
                                     "Investigations (one delivery, received 10:00am Monday, 5 "
                                     "August 2024)")

    def test_past_three_names_the_first_two_and_n_more(self):
        names = [[g.text(x)] for x in ("A", "B", "C", "D")]
        assert _words(g._names(names)) == "A, B and 2 more"


class TestForDataset:

    def test_each_supply_gets_its_points_from_the_day_its_hold_back_changed(self):
        """for_dataset: a point from the first day anything about the hold-back
        changed, none repeated while nothing changes, and a later point once the
        cause is turned down."""
        log = _log(**{I2: [(_at("2024-08-07T10:00:00+08:00"), "reject", None)]})
        got = hb.for_dataset("cp-notifications", [N2], log, RECEIPTS, hb.involved(log))
        points = got[N2]
        assert [p["on"] for p in points] == ["2024-08-05", "2024-08-07"], points
        assert points[0]["notice"]["form"] == "package"
        assert points[1]["notice"]["form"] == "turned-down"
        assert all(p["holding"] is None for p in points)

    def test_a_supply_never_held_back_has_no_points(self):
        log = _log()
        assert hb.for_dataset("cp-notifications", [N3], log, RECEIPTS, hb.involved(log)) == {}
