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
                                                "checks": ["c"] * checks})


def _log(**states) -> ctn.Log:
    log = ctn.Log()
    log.gate_instants = {I2: [(_at(AT), "promotion-refused", None, {})],
                         N2: [_withheld(I2)], C2: [_withheld(N2)]}
    log.state_instants = states
    return log


def _words(segs):
    return g.words_of(segs)


class TestTheNotice:

    def test_one_step_names_the_package_mate(self):
        n = hb._notice(_log(), N2, hb._end_of("2024-08-05"), RECEIPTS)
        assert n["form"] == "package" and n["root"] == I2
        assert _words(n["head"]) == "Held back with the Investigations received with it."
        assert "3 cross-table checks fail against it" in _words(n["body"])

    def test_a_chain_names_the_root_first(self):
        n = hb._notice(_log(), C2, hb._end_of("2024-08-05"), RECEIPTS)
        assert n["form"] == "chain" and n["root"] == I2
        assert _words(n["head"] + n["body"]).startswith(
            "Held back with its delivery: the Investigations file was held back, and the "
            "Notifications with it.")

    def test_could_not_be_checked_is_not_this_notice(self):
        log = _log()
        log.gate_instants[C2] = [_withheld(N2, failed=False)]
        assert hb._notice(log, C2, hb._end_of("2024-08-05"), RECEIPTS) is None

    def test_turned_down_and_replaced_reword_from_the_log(self):
        down = _log(**{N2: [(_at("2024-08-07T10:00:00+08:00"), "reject", None)]})
        n = hb._notice(down, C2, hb._end_of("2024-08-07"), RECEIPTS)
        assert _words(n["body"]) == ("The Notifications file received with it was turned down; "
                                    "this supply now needs its own decision.")
        assert hb._notice(down, C2, hb._end_of("2024-08-06"), RECEIPTS)["form"] == "chain"
        gone = _log(**{N2: [(_at("2024-08-07T10:00:00+08:00"), "supersede", N3)]})
        n = hb._notice(gone, C2, hb._end_of("2024-08-07"), RECEIPTS)
        assert _words(n["body"]) == ("The Notifications received with it has been replaced by the "
                                    "one received 10:00am Wednesday, 7 August 2024; this supply "
                                    "now needs its own decision.")


class TestTheRoot:

    def test_the_root_lists_everything_it_holds_back_and_the_card(self):
        log = _log()
        held, _days = hb.involved(log)
        h = hb._holding(log, I2, hb._end_of("2024-08-05"), RECEIPTS, held)
        assert _words(h["tail"]).startswith("Holding back with it: Client Register, Notifications.")
        assert _words(h["card"]) == ("Held back together: Investigations, Client Register and "
                                     "Notifications (one delivery, received 10:00am Monday, 5 "
                                     "August 2024)")

    def test_past_three_names_the_first_two_and_n_more(self):
        names = [[g.text(x)] for x in ("A", "B", "C", "D")]
        assert _words(g._names(names)) == "A, B and 2 more"
