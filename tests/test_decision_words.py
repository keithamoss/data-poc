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


def test_the_terminal_listing_uses_the_words(supply_dsn, monkeypatch):
    from cli import supply as supply_cli
    from qa_tools.common import qa_store, supply_db

    monkeypatch.setattr(supply_cli.console, "_width", 400)
    with supply_db.connect(label="test-decision-words") as conn:
        qa_store.ensure_schema(conn)
        with dl.apply_decision(conn, dl.Decision(
                agency_id="child-protection-family-support", collection_id="child-protection",
                dataset_id="cp-investigations", action=dl.PROMOTE, to_slot="2026-Q3",
                supply="cp_investigations__20260801090000000000", actor="keith@example.gov.au",
                actor_kind=dl.PERSON, effective_at="2026-08-01T09:30:00+08:00")):
            pass
    got = CliRunner().invoke(supply_cli.supply_group,
                             ["decisions", "--dataset", "cp-investigations"])
    assert got.exit_code == 0, got.output
    rows = [line for line in got.output.splitlines()
            if "cp_investigations__2026080109" in line and "2026-Q3" in line
            and not line.startswith("Currently")]
    assert len(rows) == 1 and "  promoted  " in rows[0]
