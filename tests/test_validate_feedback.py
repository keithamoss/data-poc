"""REQ-DOCS-219: every road-testing entry carries a well-formed feedback card,
checked by `mothman dashboard validate-feedback` through the one parser the
dashboard build uses too.

Fixture files for each rule, and one run over the real committed file."""
from __future__ import annotations

import textwrap

import pytest
import yaml

from dashboard.plans_md import parse_feedback_cards
from qa_tools.common import validate_feedback as vf

INTRO = textwrap.dedent("""\
    # Road testing

    - **Sprint 3 - "what actually changed?" (#9; L).** One distribution component.
    """)


def _entry(number=1, card="", status="todo", date="2026-09-24"):
    return (f"{number}. **[{status}, {date}]** **[Dashboard UI]** **A sighting.**\n"
            f"    More of the opening paragraph.\n\n{card}\n\n    The analysis prose.\n")


GOOD = textwrap.dedent("""\
    - **You told us:** Something was unclear.
    - **What we heard:** It should say what it means.
    - **What we built:** It says so now.
    - **Evidence:** REQ-DASH-001; sprint 3; [the page](#/agency/ag)""")


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "plans").mkdir()
    (tmp_path / "requirements.yaml").write_text(yaml.safe_dump({"requirements": [
        {"id": "REQ-DASH-001", "status": "built"},
        {"id": "REQ-DASH-002", "status": "retired", "retired": {"replaced_by": ["REQ-DASH-001"]}},
    ]}))
    (tmp_path / "data-asset.yaml").write_text(yaml.safe_dump({"hierarchy": {"agencies": [
        {"id": "ag", "collections": [{"id": "col", "datasets": [{"id": "ds"}]}]}]}}))

    def run(*entries):
        (tmp_path / "plans" / "road-testing.md").write_text(INTRO + "\n" + "\n".join(entries))
        return vf.problems(tmp_path / "plans", tmp_path / "requirements.yaml", tmp_path / "data-asset.yaml")
    return run


def _only(errors, *needles):
    assert len(errors) == 1, errors
    for n in needles:
        assert n in errors[0], errors[0]


def test_a_well_formed_card_passes_and_is_parsed(repo):
    cards, errors = repo(_entry(card=GOOD))
    assert errors == []
    (card,) = cards
    assert card["firstLabel"] == "You told us" and card["date"] == "2026-09-24"
    assert [i["kind"] for i in card["evidence"]] == ["req", "sprint", "link"]


def test_an_entry_with_no_card_fails_naming_it(repo):
    _, errors = repo(_entry(number=7, card="    Just prose."))
    _only(errors, "entry #7", "no feedback card")


def test_what_we_heard_is_required(repo):
    _, errors = repo(_entry(card="- **We noticed:** A thing."))
    _only(errors, "entry #1", "What we heard")


@pytest.mark.parametrize("card,needle", [
    ("- **What we heard:** b\n- **You told us:** a", "exactly one"),
    ("- **You told us:** a\n- **We noticed:** a\n- **What we heard:** b", "exactly one"),
    ("- **You told us:** a\n- **What we heard:** b\n- **What we heard:** c", "twice"),
    ("- **You told us:** a\n- **What we heard:** b\n- **Card status:** parked\n- **What we built:** c", "out of order"),
])
def test_labels_come_once_each_in_order(repo, card, needle):
    _, errors = repo(_entry(card=card))
    assert any(needle in e and "entry #1" in e for e in errors), errors


def test_not_built_is_an_absent_line_not_a_placeholder(repo):
    cards, errors = repo(_entry(card="- **You told us:** a\n- **What we heard:** b"))
    assert errors == [] and cards[0]["built"] is None


def test_a_build_claim_needs_evidence(repo):
    _, errors = repo(_entry(card="- **You told us:** a\n- **What we heard:** b\n- **What we built:** c"))
    _only(errors, "needs Evidence")


@pytest.mark.parametrize("item,needle", [
    ("https://example.com/x", "not a requirement id"),
    ("[x](https://example.com)", "relative dashboard address"),
    ("[x](javascript:alert(1))", "evidence item"),
    ("abc1234", "not a requirement id"),
    ("[x](?panel=requirements&req=REQ-DASH-001)", "write the bare id 'REQ-DASH-001'"),
    ("[x](?in-place-on=yesterday#/)", "not a YYYY-MM-DD date"),
])
def test_evidence_items_are_ids_sprints_or_relative_links(repo, item, needle):
    card = f"- **You told us:** a\n- **What we heard:** b\n- **Evidence:** {item}"
    _, errors = repo(_entry(card=card))
    _only(errors, needle)


def test_a_past_date_link_is_accepted(repo):
    card = "- **You told us:** a\n- **What we heard:** b\n- **Evidence:** [then](?in-place-on=2023-08-05#/agency/ag)"
    _, errors = repo(_entry(card=card))
    assert errors == []


def test_the_shared_parser_itself_refuses_a_non_relative_target(tmp_path):
    """Criterion 22: the build reads cards through this parser, so the check
    holds even when the gate is skipped."""
    p = tmp_path / "road-testing.md"
    p.write_text(_entry(card="- **You told us:** a\n- **What we heard:** b\n- **Evidence:** [x](//evil.example)"))
    cards, errors = parse_feedback_cards(p)
    assert cards == [] and any("relative dashboard address" in e for e in errors)


@pytest.mark.parametrize("item,needle", [
    ("REQ-DASH-999", "not in requirements.yaml"),
    ("REQ-DASH-002", "retired - cite REQ-DASH-001"),
    ("sprint 9", "not in the introduction's list"),
    ("[x](#/agency/nope)", "agency 'nope'"),
    ("[x](#/agency/ag/collection/col/dataset/zzz)", "dataset 'zzz'"),
    ("[x](#/nowhere)", "not one the dashboard has"),
])
def test_evidence_is_checked_against_configuration(repo, item, needle):
    card = f"- **You told us:** a\n- **What we heard:** b\n- **Evidence:** {item}"
    _, errors = repo(_entry(card=card))
    _only(errors, needle)


@pytest.mark.parametrize("card,needle", [
    ("- **You told us:** a\n- **What we heard:** b\n- **Card status:** done", "is not one of"),
    ("- **You told us:** a\n- **What we heard:** b\n- **What we built:** c\n- **Evidence:** REQ-DASH-001\n"
     "- **Card status:** fixed", "takes its status from it"),
    ("- **You told us:** a\n- **What we heard:** b\n- **Card status:** wont-do", "says why"),
])
def test_card_status_rules(repo, card, needle):
    _, errors = repo(_entry(card=card))
    _only(errors, needle)


def test_a_parked_card_says_why_without_evidence(repo):
    card = "- **You told us:** a\n- **What we heard:** b\n- **What we built:** Not yet - waiting.\n- **Card status:** parked"
    _, errors = repo(_entry(card=card))
    assert errors == []


def test_a_missing_file_or_an_empty_one_fails(tmp_path):
    assert parse_feedback_cards(tmp_path / "road-testing.md")[1]
    (tmp_path / "road-testing.md").write_text("# Road testing\n\nNo entries.\n")
    assert parse_feedback_cards(tmp_path / "road-testing.md")[1]


def test_the_committed_file_passes():
    cards, errors = vf.problems()
    assert cards, "precondition: plans/road-testing.md has cards"
    assert errors == []
    assert {c["firstLabel"] for c in cards} == {"You told us", "We noticed"}
