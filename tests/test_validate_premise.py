"""The gate that stops a retired premise coming back (REQ-DOCS-101
criterion 7).

WHAT IT IS FOR, in one sentence: REQ-PIPE-089 put the QA history in the
database and REQ-PIPE-092 moved the publisher out of GitHub Actions, and
between them they falsified a premise stated in fifteen signed
requirements and three documents. A sweep fixed those. This gate is what
keeps them fixed, because the next requirement drafted from a stale
paragraph puts the contradiction straight back.

THESE TESTS HAVE TO STATE A RETIRED PREMISE IN ORDER TO CATCH ONE, which
is why this module is on the gate's own allowlist - and the gate's
negation markers mean most of them would pass anyway.
"""
from __future__ import annotations

from qa_tools.common import validate_premise as vp


class TestTheRepositoryIsClean:
    def test_nothing_in_the_repository_asserts_a_retired_premise(self):
        """The gate against the real tree. This is the assertion that makes
        the sweep durable rather than a one-off tidy."""
        problems = vp.findings()
        assert problems == [], "\n\n".join(problems)

    def test_it_is_a_gate_in_mothman_check(self):
        """A validator nobody runs is a validator that does not exist."""
        from cli.check import _GATES

        labels = [label for label, _, _, _ in _GATES]
        assert "premise" in labels


class TestItCatchesAnAssertion:
    """Written by planting one, because a gate that has never failed is a
    gate nobody knows the behaviour of."""

    def _scan(self, tmp_path, monkeypatch, body: str, name: str = "draft.md"):
        monkeypatch.setattr(vp, "ROOT", tmp_path)
        (tmp_path / name).write_text(body)
        return vp.findings()

    def test_a_plain_assertion_is_reported(self, tmp_path, monkeypatch):
        found = self._scan(tmp_path, monkeypatch,
                            "The history is committed to git, not gitignored.\n")
        assert len(found) == 1
        assert "draft.md:1" in found[0]

    def test_the_report_says_what_the_current_answer_is(self, tmp_path, monkeypatch):
        """A gate that says only "no" makes the reader guess, and the guess
        is how a second wrong account gets written."""
        found = self._scan(tmp_path, monkeypatch, "CI is the only publish path.\n")
        assert "the publisher runs where the data is" in found[0]

    def test_it_names_the_line_and_the_escape(self, tmp_path, monkeypatch):
        found = self._scan(tmp_path, monkeypatch, "qa_results/ is committed.\n")
        assert "AMENDED" in found[0], "the reader is not told how to mark it as history"


class TestItDoesNotFireOnHistory:
    """The allowlist and the markers are the load-bearing half. A gate that
    fires on every mention of a retired thing is a gate that forces its own
    history to be deleted, which is the opposite of criterion 5."""

    def _scan(self, tmp_path, monkeypatch, body: str, name: str = "draft.md"):
        monkeypatch.setattr(vp, "ROOT", tmp_path)
        (tmp_path / name).write_text(body)
        return vp.findings()

    def test_a_line_marked_AMENDED_passes(self, tmp_path, monkeypatch):
        assert self._scan(tmp_path, monkeypatch,
                           "AMENDED 2026-09-28: it read qa_results/ is committed.\n") == []

    def test_a_line_saying_it_used_to_passes(self, tmp_path, monkeypatch):
        assert self._scan(tmp_path, monkeypatch,
                           "This used to say CI is the only publish path.\n") == []

    def test_a_line_that_FORBIDS_the_premise_passes(self, tmp_path, monkeypatch):
        """REQ-DOCS-101's own criterion 1 is the case: it has to name the
        premise in order to forbid it, and the first draft of this gate
        reported the requirement that asked for the gate."""
        assert self._scan(tmp_path, monkeypatch,
                           "THE SYSTEM SHALL leave no requirement asserting that "
                           "qa_results/ is committed.\n") == []

    def test_a_negation_wrapped_onto_the_LINE_BEFORE_still_passes(
            self, tmp_path, monkeypatch):
        """YAML wraps a block scalar, so the negation and the phrase land on
        different lines - which is exactly what the one-line version of
        this gate got wrong, on three real criteria."""
        assert self._scan(tmp_path, monkeypatch,
                           "      - >\n"
                           "        THE SYSTEM SHALL NOT embed any\n"
                           "        part of it into committed QA results.\n",
                           name="draft.yaml") == []

    def test_a_decisions_field_is_never_read(self, tmp_path, monkeypatch):
        """Criterion 8. A decision records what was known when it was taken,
        and editing one to agree with a later design destroys the only
        account of the reasoning."""
        assert self._scan(tmp_path, monkeypatch,
                           "    decisions:\n"
                           "      - >\n"
                           "        Decided that qa_results/ is committed and never\n"
                           "        gitignored, because a history that can be pruned\n"
                           "        is not a history.\n",
                           name="requirements.yaml") == []

    def test_an_evidence_field_is_never_read_either(self, tmp_path, monkeypatch):
        """Not named by the requirement, and surfaced by the gate's first
        real run: an entry dated 2026-09-16 says a rebuild from committed
        qa_results/ was diffed byte-identical, and that is true of that
        day. Rewording it would claim a measurement nobody took."""
        assert self._scan(tmp_path, monkeypatch,
                           "    evidence:\n"
                           "      - >\n"
                           "        2026-09-16: rebuilt from committed qa_results/\n"
                           "        history alone, byte-identical.\n",
                           name="requirements.yaml") == []

    def test_an_ordinary_field_in_the_same_file_IS_read(self, tmp_path, monkeypatch):
        """Otherwise the exclusion above would be a hole rather than an
        exception - the rest of requirements.yaml is what the gate is
        for."""
        found = self._scan(tmp_path, monkeypatch,
                            "    acceptance_criteria:\n"
                            "      - >\n"
                            "        THE SYSTEM SHALL keep qa_results/ committed to\n"
                            "        git, not gitignored.\n",
                            name="requirements.yaml")
        assert len(found) == 1

    def test_the_plans_directory_is_allowed_wholesale(self, tmp_path, monkeypatch):
        """A real decision rather than laziness: plans/*.md records what was
        believed when written, and CLAUDE.md's rule is that it gets DELETED
        as its requirements land rather than rewritten. A gate forcing it
        into line would force history to be falsified."""
        monkeypatch.setattr(vp, "ROOT", tmp_path)
        (tmp_path / "plans").mkdir()
        (tmp_path / "plans" / "old.md").write_text("CI is the only publish path.\n")
        assert vp.findings() == []

    def test_a_build_output_is_not_scanned(self, tmp_path, monkeypatch):
        """It carries whatever the template said and is gitignored, so
        scanning one makes a stale local build fail the gate for a line
        nobody wrote."""
        monkeypatch.setattr(vp, "ROOT", tmp_path)
        built = tmp_path / "dashboard" / "qa-reporting-dashboard.html"
        built.parent.mkdir()
        built.write_text("CI is the only publish path.\n")
        assert vp.findings() == []


class TestEveryAllowanceSaysWhy:
    def test_each_allowlist_entry_carries_a_reason(self):
        """An allowlist without reasons becomes a list of things nobody
        dares remove."""
        for prefix, reason in vp.ALLOWED:
            assert prefix and reason and len(reason) > 20, (prefix, reason)

    def test_each_retired_premise_names_its_replacement(self):
        for pattern, correction in vp.RETIRED_PREMISES.items():
            assert "REQ-PIPE-" in correction, (pattern, correction)
