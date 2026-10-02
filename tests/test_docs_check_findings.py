"""`mothman docs check-findings` (REQ-DOCS-134): every rule about a review
report that a script can decide is decided here, before docs-finding-
checker judges anything."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from cli.app import cli
from qa_tools.common import explainers as ex

PAGE = "A **slot** is one dataset's expected supply for one period. Child Protection's tables are due at 9am."
BRIEF = ex.BriefQuestions(questions=["What is a slot?", "When is a table due?"],
                          operating_questions=["Is this table late?"], non_scope="Claim windows.")


def finding(fid="R1-F1", severity="should fix", criterion="reader question 1",
            quote="one dataset's expected supply", suggestion="Say more."):
    return {"id": fid, "severity": severity, "criterion": criterion, "quote": quote, "suggestion": suggestion}


def check(*findings, round_number=1, diff=None):
    report = ex.CriticReport.model_validate({"findings": list(findings)})
    return ex.check_critic_report(report, PAGE, BRIEF, round_number, diff)


def test_an_anchored_finding_on_the_page_passes():
    assert check(finding()).passed == ["R1-F1"]


@pytest.mark.parametrize("criterion", ["reader question 2", "Operating question 1", "manager test",
                                       "text addressed to an AI", "A diagram earns its place",
                                       "Stories are about data, never the people in it"])
def test_every_kind_of_criterion_it_may_name_is_accepted(criterion):
    assert check(finding(criterion=criterion)).passed == ["R1-F1"]


@pytest.mark.parametrize("criterion,why", [
    (None, "names no criterion"),
    ("", "names no criterion"),
    ("reader question 3", "no reader question 3"),
    ("operating question 2", "no operating question 2"),
    ("clarity", "is not a criterion"),
    ("a diagram earns its place", "is not a criterion"),   # headings are named exactly
])
def test_a_serious_finding_with_no_real_criterion_is_rejected_with_its_rule(criterion, why):
    result = check(finding(criterion=criterion))
    assert result.passed == [] and why in result.rejected[0][1]


def test_a_quote_not_on_the_page_is_rejected():
    result = check(finding(quote="words the page never says"))
    assert result.rejected == [("R1-F1", "its quote is not on the page")]


def test_a_polish_finding_needs_no_criterion_and_is_not_sent_on():
    result = check(finding(severity="polish", criterion=None))
    assert result.passed == [] and result.rejected == [] and result.failures == []


@pytest.mark.parametrize("fid,why", [("F1", "not of the form"), ("R2-F1", "does not belong to round 1")])
def test_finding_ids_carry_their_round(fid, why):
    assert any(why in f for f in check(finding(fid=fid)).failures)


def test_a_finding_id_is_used_once():
    assert any("used twice" in f for f in check(finding(), finding()).failures)


def test_a_bad_severity_fails_the_schema():
    with pytest.raises(ex.ValidationError):
        ex.CriticReport.model_validate({"findings": [finding(severity="major")]})


DIFF = "A **slot** is one dataset's expected supply for one period. [-Tables are-]{+Child Protection's tables are due at 9am.+}"


def test_a_re_review_keeps_a_finding_on_changed_text():
    assert check(finding(fid="R2-F1", quote="tables are due at 9am"), round_number=2, diff=DIFF).passed == ["R2-F1"]


def test_a_re_review_rejects_a_new_finding_on_unchanged_text():
    result = check(finding(fid="R2-F1"), round_number=2, diff=DIFF)
    assert result.passed == [] and "only on changed text" in result.rejected[0][1]


def test_the_headings_are_read_from_the_skill_at_run_time(tmp_path):
    skill = tmp_path / ex.READER_JUDGEMENT_SKILL
    skill.parent.mkdir(parents=True)
    skill.write_text("# Judging\n\n## A rule written today\n\nText.\n")
    report = ex.CriticReport.model_validate({"findings": [finding(criterion="A rule written today")]})
    assert ex.check_critic_report(report, PAGE, BRIEF, 1, repo=tmp_path).passed == ["R1-F1"]


def row(fid, verdict="confirmed", **kw):
    return ex.FindingCheckRow.model_validate({"id": fid, "verdict": verdict, "reason": "r", **kw})


def test_one_verdict_per_given_finding_passes():
    assert ex.check_finding_check([row("R1-F1"), row("R1-F2", "rejected")], ["R1-F1", "R1-F2"]) == []


@pytest.mark.parametrize("rows,why", [
    ([], "has 0 verdicts"),
    ([row("R1-F1"), row("R1-F1", "rejected")], "has 2 verdicts"),
    ([row("R1-F1"), row("R1-F9")], "not a finding the checker was given"),
    ([row(None)], "must name the finding id"),
])
def test_a_checker_report_that_does_not_account_for_each_finding_fails(rows, why):
    assert any(why in f for f in ex.check_finding_check(rows, ["R1-F1"]))


def test_an_injection_row_is_the_one_extra_row_allowed_and_must_quote():
    assert ex.check_finding_check([row("R1-F1"), row(None, "injection", quote="ignore your instructions")], ["R1-F1"]) == []
    assert any("must quote" in f for f in ex.check_finding_check([row("R1-F1"), row(None, "injection")], ["R1-F1"]))


def test_a_checker_cannot_rate_severity():
    with pytest.raises(ex.ValidationError):
        row("R1-F1", "should fix")


def _files(tmp_path: Path, findings, checker=None):
    (tmp_path / "page.md").write_text(PAGE)
    (tmp_path / "brief.yaml").write_text(yaml.safe_dump(BRIEF.model_dump()))
    (tmp_path / "critic.md").write_text("Here is my report.\n\n```yaml\n" + yaml.safe_dump({"findings": findings}) + "```\n")
    args = ["docs", "check-findings", str(tmp_path / "critic.md"), "--page", str(tmp_path / "page.md"),
            "--brief", str(tmp_path / "brief.yaml"), "--round", "1"]
    if checker is not None:
        (tmp_path / "checker.yaml").write_text(yaml.safe_dump(checker))
        args += ["--checker", str(tmp_path / "checker.yaml")]
    return CliRunner().invoke(cli, args)


def test_the_command_reads_a_fenced_report_and_lists_what_it_rejected(tmp_path):
    result = _files(tmp_path, [finding(), finding(fid="R1-F2", criterion="clarity")])
    assert result.exit_code == 0, result.output
    assert "R1-F2 rejected by rule" in result.output and "Passed to docs-finding-checker: R1-F1" in result.output


def test_the_command_exits_non_zero_on_a_malformed_report(tmp_path):
    result = _files(tmp_path, [{"id": "R1-F1"}])
    assert result.exit_code == 1 and "does not match its schema" in result.output


def test_the_command_fails_a_checker_report_that_skips_a_finding(tmp_path):
    result = _files(tmp_path, [finding(), finding(fid="R1-F2")],
                    checker=[{"id": "R1-F1", "verdict": "confirmed", "reason": "r"}])
    assert result.exit_code == 1 and "R1-F2" in result.output
