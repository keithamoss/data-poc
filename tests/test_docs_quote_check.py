"""`mothman docs quote-check` (REQ-DOCS-128 criteria 13 and 14): every
quote in a saved fact-checker report must be in the source it names."""
from __future__ import annotations

import yaml
from click.testing import CliRunner

from cli.app import cli
from qa_tools.common import explainers as ex


def row(source, quote, verdict="supported"):
    return {"claim": "c", "verdict": verdict, "source": source, "quote": quote}


def test_a_requirement_quote_matches_its_parsed_fields_across_folded_lines():
    """The YAML folds and quotes long strings; the check reads the parsed
    value, so a true quote spanning a fold still passes."""
    assert ex.quote_check([row("REQ-PIPE-052", "THE SYSTEM SHALL create one slot per dataset per period,"
                                               "   so that a collection of six datasets")]) == []


def test_a_paraphrase_is_caught():
    problems = ex.quote_check([row("REQ-PIPE-052", "one slot for every table in every quarter")])
    assert problems and "the quote is not in REQ-PIPE-052" in problems[0]


def test_a_file_and_line_source_reads_the_file():
    assert ex.quote_check([row("contract/data-asset.yaml:9", "anchored on the 1st of February, May, August and November")]) == []


def test_an_unknown_requirement_or_file_is_flagged():
    problems = ex.quote_check([row("REQ-PIPE-999", "x"), row("nope/missing.yaml:3", "x")])
    assert "REQ-PIPE-999 is not in requirements.yaml" in problems[0]
    assert "not a file in the repository" in problems[1]


def test_a_path_outside_the_repository_is_refused():
    assert "not a file in the repository" in ex.quote_check([row("../../etc/passwd", "root")])[0]


def test_rows_without_a_quote_are_skipped():
    assert ex.quote_check([row("REQ-PIPE-052", "", verdict="not found"), {"verdict": "exempt"}]) == []


def test_a_story_row_needs_no_source_or_quote():
    """REQ-DOCS-128: an invented story sentence is listed, never checked."""
    assert ex.quote_check([{"claim": "Sam opens the dashboard on 3 August 2026.", "verdict": "story"}]) == []


def test_the_command_exits_non_zero_on_a_bad_quote(tmp_path):
    report = tmp_path / "facts.yaml"
    report.write_text(yaml.safe_dump([row("REQ-PIPE-052", "invented words")]))
    result = CliRunner().invoke(cli, ["docs", "quote-check", str(report)])
    assert result.exit_code == 1 and "the quote is not in" in result.output
    report.write_text(yaml.safe_dump([row("REQ-PIPE-052", "SHALL NOT require a slot to be authored")]))
    result = CliRunner().invoke(cli, ["docs", "quote-check", str(report)])
    assert result.exit_code == 0, result.output


# The forms docs-fact-checker actually wrote on its first eval run
# (REQ-DOCS-123, 2026-10-02). Every row was refused as "not a file", so
# quote-check reported a whole correct report as failing.

def test_a_requirement_with_a_location_note_reads_the_requirement():
    assert ex.quote_check([row("REQ-PIPE-075 (requirements.yaml:13251-13253)",
                               "THE SYSTEM SHALL treat a slot as filled only where a supply has been promoted into it")]) == []


def test_a_file_with_a_line_range_reads_the_file():
    assert ex.quote_check([row("contract/data-asset.yaml:125-127",
                               "anchored on the 1st of February, May, August and November")]) == []


def test_two_sources_and_two_quotes_each_quote_must_be_in_one_of_them():
    good = row("contract/data-asset.yaml:60; REQ-PIPE-052 (requirements.yaml:8526)",
               "THE DATES ARE THE SUPPLIER AGREEMENT. / THE SYSTEM SHALL create one slot per dataset per period")
    assert ex.quote_check([good]) == []
    bad = row("contract/data-asset.yaml:60; REQ-PIPE-052",
              "THE DATES ARE THE SUPPLIER AGREEMENT. / words neither source says")
    assert ex.quote_check([bad]) and "words neither source says" in ex.quote_check([bad])[0]


def test_a_location_note_cannot_smuggle_in_an_unknown_requirement():
    assert "REQ-PIPE-999 is not in requirements.yaml" in ex.quote_check([row("REQ-PIPE-999 (requirements.yaml:1)", "x")])[0]
