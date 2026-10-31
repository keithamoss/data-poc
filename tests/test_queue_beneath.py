"""The terminal's queue lists a supply held back only by another table
beneath that table's own item, says nothing needs deciding on it, and does
not count it (REQ-PIPE-210).

Driven through the real lifecycle with each tool's evaluation stood in for
(tests/gate_support.py), then through the real queue - `filing_tui.
queue_flow`, the Filing decisions queue - and the dashboard's outstanding
survey, which counts by the same one function (criteria 7 and 10).

READ THROUGH KEITH'S LATER ANSWER 3a (2026-10-25, post-build-review #274 Q3):
a supply whose re-check against the warehouse ran and FAILED is its own root,
so staggered S1 red is two counted rows, each its own decision; the case
listed beneath is the one that could not be checked.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from gate_support import (CP, CP_REF_RUN_ID, Scenario, cross_red, install_fake_tools, own_red,
                          pin_replacement_setting)
from test_package_gate import Q3, Q4, established, first_time


@pytest.fixture
def sc(private_supply_dsn, cp_raw_dir, tmp_path, monkeypatch):
    scenario = Scenario(root=tmp_path, raw_dir=Path(cp_raw_dir))
    install_fake_tools(monkeypatch, scenario)
    pin_replacement_setting(monkeypatch)
    return scenario


def _flat(text: str) -> str:
    return " ".join(re.sub(r"[│╭╮╰╯─]", " ", text).split())


def _queue(monkeypatch, capsys):
    """The Filing decisions queue as a person sees it: what it prints and
    the choices it offers."""
    from cli import common, filing_tui
    from qa_tools.common import filing_queue

    offered = []
    monkeypatch.setattr(common, "select",
                        lambda msg, choices, **k: offered.extend(choices) or None)
    # The fixture's own earlier periods, never filled, are period items.
    monkeypatch.setattr(filing_queue, "closed_gaps", lambda *a, **k: [])
    filing_tui.queue_flow(CP)
    return capsys.readouterr().out, offered


def _groups():
    from qa_tools.common import filing_queue, root_cause, supply_db

    with supply_db.connect(read_only=True, label="pytest") as conn:
        return root_cause.group_queue(conn, filing_queue.awaiting(conn, CP),
                                      held=filing_queue.held_in(conn, CP))


def _counted_on_the_card(dataset_id: str) -> int:
    """The dashboard's Child Protection card counts, from the outstanding
    survey's awaiting-decision items (criterion 10)."""
    from qa_tools.common import outstanding

    return sum(1 for i in outstanding.survey().items
               if i.kind == outstanding.AWAITING_DECISION and i.dataset_id == dataset_id)


def _pair_with(sc, readers: dict) -> dict:
    """first_time's 2025-Q1, then one zip: two Client Register files and the
    readers named ({table: label})."""
    from qa_tools.common import asset_time, delivery

    got = first_time(sc)
    at = asset_time.parse_instant("2024-11-03T10:00:00+08:00", "test")
    source = sc.raw_dir / CP_REF_RUN_ID
    clients = (source / "cp_clients.csv").read_text()
    files = {"cp_clients.csv": clients, "cp_clients_part2.csv": clients}
    for table in readers:
        files[f"{table}.csv"] = (source / f"{table}.csv").read_text()
    delivery.write_delivery("cp-pair-zip", files, received_at={n: at for n in files},
                            deliveries_dir=sc.deliveries, receipts_dir=sc.receipts)
    key = asset_time.arrival_key(at)
    out = {"pair": f"cp-clients@{key}#1", **got}
    for table, label in readers.items():
        supply = f"cp-{table[3:].replace('_', '-')}@{key}"
        sc.labels[supply] = label
        out[label] = supply
    sc.process()
    return out


class TestListedBeneathItsCause:

    def test_a_contested_pair_lists_its_three_readers_once_beneath_it(self, sc, monkeypatch,
                                                                      capsys):
        """A contested cp_clients pair and its three readers: listed once
        beneath the pair, not counted, not offered - and not counted on the
        dashboard's card either."""
        got = _pair_with(sc, {"cp_notifications": "N2", "cp_investigations": "I2",
                              "cp_placements": "P2"})
        groups = _groups()
        rows = {r.supply for r in groups.rows}
        assert got["pair"] in rows, rows
        beneath = [b.state.supply for v in groups.beneath.values() for b in v]
        assert sorted(beneath) == sorted(got[x] for x in ("N2", "I2", "P2")), beneath
        assert not rows & set(beneath)
        out, offered = _queue(monkeypatch, capsys)
        flat = _flat(out)
        assert (f"{groups.count} supply waiting on a decision in Child Protection "
                f"(3 more held back with it, listed beneath)") in flat, out
        for dataset_id in ("cp-notifications", "cp-investigations", "cp-placements"):
            assert not any(dataset_id in c for c in offered), offered
        # ONE LINE PER RESULTING OUTCOME: the three share theirs, each named once.
        assert flat.count("nothing needs deciding on this supply") == 1, out
        line = re.search(r"- ([\w, -]+?) nothing needs deciding on this supply", flat).group(1)
        assert sorted(line.split(", ")) == ["cp-investigations", "cp-notifications",
                                            "cp-placements"], line
        assert _counted_on_the_card("cp-notifications") == 0

    def test_s2_strict_lists_notifications_beneath_clients_with_the_override(
            self, sc, monkeypatch, capsys):
        """S2 strict as re-cast (V4-Q1 = A): Notifications v2 beneath Clients
        v2, not counted, not pickable, the complete override command shown
        whole on a line of its own, outside any table."""
        first_time(sc)
        sc.rules.append(own_red("C2"))
        v2 = sc.deliver("2024-11-03T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        out, offered = _queue(monkeypatch, capsys)
        flat = _flat(out)
        assert ("1 supply waiting on a decision in Child Protection (1 more held "
                "back with it, listed beneath)") in flat, out
        assert "- cp-notifications nothing needs deciding on this supply" in flat
        command = (f"mothman supply decide --operation promote --dataset cp-notifications "
                   f"--period {Q4} --supply {v2['N2']} --reason '<why>'")
        assert any(line.strip() == command for line in out.splitlines()), out
        assert f"or from the {Q4} door." in flat
        assert [c for c in offered if "cp-notifications" in c] == [], offered
        assert any("cp-clients" in c for c in offered), offered

    def test_once_clients_is_turned_down_notifications_is_its_own_counted_row(self, sc):
        """Clients v2 rejected: Notifications v2 becomes a counted row of its
        own, worded from the decision log as it stands - never a 'waiting
        for' that can no longer happen."""
        from test_package_gate import _reject

        first_time(sc)
        sc.rules.append(own_red("C2"))
        v2 = sc.deliver("2024-11-03T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        _reject(sc, v2["C2"], Q4)
        groups = _groups()
        assert v2["N2"] in {r.supply for r in groups.rows}
        said = groups.lines.get(("cp-notifications", Q4, v2["N2"])) or []
        assert ("The cp-clients file received with it was turned down; this supply now "
                "needs its own decision.") in said, said
        assert not any("nothing needs deciding" in line for line in said)

    def test_a_joined_supply_is_listed_as_held_back_by_it(self, sc, monkeypatch, capsys):
        """Staggered S2: Clients v2 alone at 9:00, red on its own data;
        Notifications v2 alone at 9:05 cannot be checked without it and is
        listed beneath it as 'held back by it'."""
        first_time(sc)
        sc.rules.append(own_red("C2"))
        sc.deliver("2024-11-03T09:00:00+08:00", {"cp_clients": "C2"})
        sc.process()
        sc.deliver("2024-11-03T09:05:00+08:00", {"cp_notifications": "N2"})
        sc.process()
        flat = _flat(_queue(monkeypatch, capsys)[0])
        assert "(1 more held back by it, listed beneath)" in flat, flat
        assert "held back by it: - cp-notifications nothing needs deciding" in flat, flat

    def test_staggered_s1_red_is_two_counted_rows_under_3a(self, sc):
        """Staggered S1 red: Notifications v2 at 8:40 red on its own data;
        Clients v2 at 9:00 re-checked against Notifications v1 and FAILED -
        its own root (3a), so both are counted rows, Clients v2's naming the
        package-mate's decision first in its door."""
        from cli import filing_tui
        from qa_tools.common import slot_state

        established(sc)
        sc.rules += [own_red("N2"), cross_red("cp-notifications", "cp_clients",
                                              when={"cp_clients": "C2",
                                                    "cp_notifications": "N1"})]
        n2 = sc.deliver("2024-08-05T08:40:00+08:00", {"cp_notifications": "N2"})["N2"]
        sc.process()
        c2 = sc.deliver("2024-08-05T09:00:00+08:00", {"cp_clients": "C2"})["C2"]
        sc.process()
        groups = _groups()
        assert {n2, c2} <= {r.supply for r in groups.rows}
        assert groups.beneath == {}
        note, offer_nothing = filing_tui.door_note(slot_state.SlotState(
            dataset_id="cp-clients", period=Q3, state=slot_state.AWAITING_DECISION,
            supply=c2))
        assert not offer_nothing
        assert f"Decide cp-notifications {Q3} (received " in note, note
        assert "Nothing needs deciding on this supply." not in note


class TestNothingToSitBeneath:

    def test_red_only_because_clients_is_overdue_is_an_ordinary_counted_row(
            self, sc, monkeypatch, capsys):
        """Notifications v2 red only because 2025-Q1's Clients is overdue, with
        no held-back supply to sit beneath: a counted, pickable row naming
        the overdue Clients, never 'nothing needs deciding' - and the
        dashboard's Child Protection card counts it as the terminal does."""
        first_time(sc)
        n2 = sc.deliver("2024-11-03T10:00:00+08:00", {"cp_notifications": "N2"})["N2"]
        sc.process()
        groups = _groups()
        assert n2 in {r.supply for r in groups.rows}, groups
        said = groups.lines.get(("cp-notifications", Q4, n2)) or []
        assert ("red because cp-clients for 2025-Q1 is overdue; its checks run again once "
                "one is promoted") in said, said
        out, offered = _queue(monkeypatch, capsys)
        assert any("cp-notifications" in c for c in offered), offered
        assert "nothing needs deciding" not in _flat(out)
        assert _counted_on_the_card("cp-notifications") == 1


class TestAFaultOfItsOwn:

    def test_a_reader_failing_a_check_of_its_own_is_listed_and_counted(self, sc):
        """NFR NO FALSE QUIET (criterion 5): a reader of the contested pair
        that also fails a check of its own is a counted row as today, with a
        line naming the other table's cause - never 'nothing needs
        deciding'."""
        sc.rules.append(own_red("P2"))
        got = _pair_with(sc, {"cp_notifications": "N2", "cp_placements": "P2"})
        groups = _groups()
        assert got["P2"] in {r.supply for r in groups.rows}
        said = groups.lines.get(("cp-placements", Q4, got["P2"])) or []
        assert any(line.startswith("Also held back for want of cp_clients") for line in said), \
            said
        beneath = [b.state.supply for v in groups.beneath.values() for b in v]
        assert got["P2"] not in beneath and got["N2"] in beneath
