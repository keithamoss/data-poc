"""Every past decision in words, in the terminal as on the page (REQ-PIPE-166
criterion 12 - Keith, 2026-10-15, morning report 5 Q17: it covers the
terminal's `mothman supply decisions` too, not only the page).

ONE WORDING, TWO TABLES THAT CANNOT DRIFT: the page keeps its own const,
because the raw template has to work with no build step, and this module is
the terminal's; the parity test reads the template's DECISION_DONE and
fails on any difference."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from qa_tools.common import decision_log as dl
from qa_tools.common import decision_words

TEMPLATE = Path(__file__).resolve().parent.parent / "dashboard" / "qa-reporting-dashboard.template.html"


def _page_table() -> dict[str, str]:
    src = TEMPLATE.read_text()
    body = re.search(r"const DECISION_DONE = \{(.*?)\};", src, re.S).group(1)
    body = re.sub(r"//[^\n]*", "", body)
    pairs = re.findall(r'("?[\w-]+"?)\s*:\s*"([^"]*)"', body)
    assert pairs, "the page's DECISION_DONE could not be read"
    return {k.strip('"'): v for k, v in pairs}


def test_the_terminal_and_the_page_word_every_action_alike():
    page = _page_table()
    assert len(page) > 20
    assert decision_words.DONE == page


def test_every_action_the_log_records_has_words():
    # EVERY ACTION THE LOG ACCEPTS, read from the log's own list - so a new
    # action with no words fails here, naming it (post-build-review #199 F9).
    assert len(dl.ACTIONS) > 20
    missing = sorted(set(dl.ACTIONS) - set(decision_words.DONE))
    assert not missing, f"no words for: {missing}"
    assert decision_words.said(dl.PROMOTE) == "promoted"
    assert decision_words.said("withdraw-not-supplied") == "no longer marked not supplied"
    # An action with no words yet is shown as it is, never dropped.
    assert decision_words.said("something-new") == "something-new"


def _promote(conn, supply, effective_at, reason=None):
    with dl.apply_decision(conn, dl.Decision(
            agency_id="child-protection-family-support", collection_id="child-protection",
            dataset_id="cp-investigations", action=dl.PROMOTE, to_slot="2026-Q3",
            supply=supply, actor="keith@example.gov.au", actor_kind=dl.PERSON,
            effective_at=effective_at, reason=reason)):
        pass


@pytest.mark.parametrize("slot_already_filled", [False, True],
                         ids=["a-fresh-database", "after-another-module-promoted-there"])
def test_the_terminal_listing_uses_the_words(supply_dsn, monkeypatch, slot_already_filled):
    """WITH A REASON, SO IT HOLDS WHATEVER SHARES THE WORKER (post-build-review
    #271). The worker's database is shared with every module the scheduler puts
    beside this one, and the decision log is append-only, so when an earlier
    module's pipeline run has already promoted a cp-investigations supply into
    2026-Q3 this routine promotion is a SUPERSESSION, which is refused without
    a reason. The dataset cannot be made unique - the listing accepts only
    datasets the hierarchy declares - and a reason makes the decision valid in
    both cases while it still reads "promoted" either way, which is what this
    test is about. The second case sets up exactly what the gate's neighbour
    left behind, so the test proves it holds rather than hoping."""
    import uuid

    from cli import supply as supply_cli
    from qa_tools.common import qa_store, supply_db

    mine = f"cp_investigations__2026080109{uuid.uuid4().int % 10**10:010d}"
    monkeypatch.setattr(supply_cli.console, "_width", 400)
    with supply_db.connect(label="test-decision-words") as conn:
        qa_store.ensure_schema(conn)
        if slot_already_filled:
            _promote(conn, f"cp-investigations@{uuid.uuid4().hex}", "2026-07-30T09:30:00+08:00",
                     reason="whatever was promoted there first")
        _promote(conn, mine, "2026-08-01T09:30:00+08:00", reason="the corrected August extract")
    got = CliRunner().invoke(supply_cli.supply_group,
                             ["decisions", "--dataset", "cp-investigations"])
    assert got.exit_code == 0, got.output
    rows = [line for line in got.output.splitlines()
            if mine in line and "2026-Q3" in line and not line.startswith("Currently")]
    assert len(rows) == 1 and "  promoted  " in rows[0]
