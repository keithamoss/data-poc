"""The period's door and the flag form both offer carry-forward, list its
consequences, and need the key with --yes (REQ-PIPE-280 criteria 1 and 7).

The decision itself is tests/test_carry_forward.py's; this is the two
terminal routes onto it.
"""
from __future__ import annotations

import re

from click.testing import CliRunner

import carry_forward_support
from carry_forward_support import CASE_WORKERS, NAME, entries

conn = carry_forward_support.conn
world = carry_forward_support.world
from qa_tools.common import decision_log as dl
from qa_tools.common import knock_on, people
from test_carry_forward import REAL_PERSON, _stale


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[│╭╮╰╯─]", " ", text))


def test_door_and_flags_offer_it_with_its_consequences(conn, world, monkeypatch, capsys):
    from cli import common, filing_tui
    from cli.supply import supply_group

    _stale(conn, world)
    monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                        lambda: people.person_by_email(REAL_PERSON))
    monkeypatch.setattr(knock_on, "follow_up", lambda *a, **k: [])

    # THE DOOR: the owed-nothing period is listed, carry-forward offered, and
    # its consequences shown above the one confirmation - declined here.
    picked = {}

    def select(message, choices, **kw):
        if message == "Which dataset?":
            return CASE_WORKERS
        if message.startswith("Which period"):
            return next(c for c in choices if c.startswith(world.q4))
        picked["offered"] = list(choices)
        return next(c for c in choices if c.startswith("carry forward"))

    monkeypatch.setattr(common, "select", select)
    monkeypatch.setattr(common, "text_prompt", lambda *a, **k: "current")
    asked = []
    monkeypatch.setattr(common, "confirm_change",
                        lambda message, **kw: asked.append(message) and False)
    capsys.readouterr()
    filing_tui.period_flow("child-protection")
    out = _flat(capsys.readouterr().out)
    assert any(c.startswith("un-inherit") for c in picked["offered"]), picked
    assert "This decision also does" in out
    assert f"{world.q4} stops carrying forward the {NAME} received" in out
    assert asked, "one confirmation, after the consequences"
    assert not entries(conn, world.q4, dl.CARRY_FORWARD), "declined: nothing recorded"

    # THE FLAG FORM: --yes alone is refused with the consequences and the key;
    # with the key it is recorded.
    monkeypatch.setattr(common, "confirm_change", lambda message, **kw: True)
    def decide(*extra):
        return CliRunner().invoke(supply_group, [
            "decide", "--operation", "carry-forward", "--dataset", CASE_WORKERS,
            "--period", world.q4, "--reason", "current", "--yes", *extra],
            env={"COLUMNS": "200"})

    got = decide()
    assert got.exit_code == 1, got.output
    flat = _flat(got.output)
    assert f"{world.q4} stops carrying forward the {NAME} received" in flat
    assert "There is no step back to the supply received" in flat
    key = re.search(r"--acknowledge ([0-9a-f]{10})", flat).group(1)
    assert not entries(conn, world.q4, dl.CARRY_FORWARD), "nothing recorded without the key"
    got = decide("--acknowledge", key)
    assert got.exit_code == 0, got.output
    (entry,) = entries(conn, world.q4, dl.CARRY_FORWARD)
    assert entry["actor"] == REAL_PERSON
