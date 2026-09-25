"""A duplicate YAML key is loud at READ time (qa_tools/common/yaml_io.py).

The bug this closes has happened twice in this repo, five days apart,
and the second time is the instructive one: a read-back check ran
straight after the edit - the discipline CLAUDE.md asks for - and
reported a healthy result, because it was built on the same silent
primitive as the bug.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from qa_tools.common import yaml_io

ROOT = Path(__file__).resolve().parent.parent


class TestADuplicateKeyRaises:
    def test_pyyaml_itself_is_silent_which_is_why_this_exists(self):
        """Not a test of PyYAML - a statement of the premise, so that
        if a future version ever starts raising, this file says what it
        was for."""
        assert yaml.safe_load("a: 1\na: 2") == {"a": 2}

    def test_the_strict_loader_refuses(self):
        with pytest.raises(yaml_io.DuplicateKeyError, match="duplicate key 'a'"):
            yaml_io.load("a: 1\na: 2")

    def test_it_names_both_lines(self):
        """The useful question is never "is there a duplicate" but
        "which one did I mean to keep"."""
        with pytest.raises(yaml_io.DuplicateKeyError) as caught:
            yaml_io.load("first: 1\nother: 2\nfirst: 3\n")
        message = str(caught.value)
        assert "line 1" in message and "line 3" in message

    def test_it_catches_a_duplicate_nested_deep_in_a_document(self):
        """Both real incidents were a repeated key on ONE requirement
        inside a list of hundreds, not at the top level."""
        source = (
            "requirements:\n"
            "  - id: REQ-ONE\n"
            "    decisions: [a]\n"
            "  - id: REQ-TWO\n"
            "    unmet_criteria:\n"
            "      - criterion: first\n"
            "    unmet_criteria:\n"
            "      - criterion: second\n")
        with pytest.raises(yaml_io.DuplicateKeyError, match="unmet_criteria"):
            yaml_io.load(source)

    def test_ordinary_yaml_is_unaffected(self):
        assert yaml_io.load("a: 1\nb:\n  - x\n  - y\n") == {"a": 1, "b": ["x", "y"]}

    def test_it_reads_a_path_as_well_as_a_string(self, tmp_path):
        path = tmp_path / "thing.yaml"
        path.write_text("a: 1\n")
        assert yaml_io.load(path) == {"a": 1}


class TestTheRealFilesStillLoad:
    """A strictness change that breaks the corpus it guards is not a
    guard, so this names the files rather than trusting the swap."""

    @pytest.mark.parametrize("name", [
        "requirements.yaml", "CHANGELOG.yaml", "contract/data-asset.yaml",
        ".yamllint", ".pre-commit-config.yaml"])
    def test_it_parses(self, name):
        assert yaml_io.load(ROOT / name) is not None


class TestNoProductionCodeUsesTheSilentLoader:
    """The structural half, and the reason this is a test rather than a
    convention.

    A list of places to be careful rots - somebody adds the
    thirtieth call site and nothing says it is the one unguarded read
    in the repo. A denial does not rot. Same shape as the fixture that
    keeps tests out of the committed history trees, and for the same
    reason.
    """

    #: Walked on the FILESYSTEM rather than with `git grep`, which sees
    #: only tracked files - a brand-new module is untracked exactly
    #: while it is being written, which is when this guard is most
    #: worth having. It also keeps the test independent of clone
    #: depth, which CLAUDE.md records as its own class of CI-only
    #: failure.
    PRODUCTION = ("qa_tools", "pipeline", "dashboard", "cli", "generator",
                   "synthetic_data_generator")

    def _offenders(self) -> list[str]:
        found = []
        for package in self.PRODUCTION:
            for path in (ROOT / package).rglob("*.py"):
                if path == ROOT / "qa_tools" / "common" / "yaml_io.py":
                    continue
                for number, line in enumerate(path.read_text().splitlines(), start=1):
                    if "yaml.safe_load(" in line:
                        found.append(f"{path.relative_to(ROOT)}:{number}")
        return sorted(found)

    def test_nothing_outside_yaml_io_calls_safe_load(self):
        offenders = self._offenders()
        assert offenders == [], (
            "these read YAML with the loader that accepts a duplicate key silently:\n  "
            + "\n  ".join(offenders)
            + "\nUse qa_tools.common.yaml_io.load() instead - it raises, at the moment "
              "the file is read rather than at the next gate.")

    def test_the_guard_would_notice_one(self, tmp_path, monkeypatch):
        """A search that matches nothing is indistinguishable from a
        clean repo, so give it something real to find."""
        package = tmp_path / "pretend_package"
        package.mkdir()
        (package / "reader.py").write_text("import yaml\nd = yaml.safe_load('a: 1')\n")
        monkeypatch.setattr(self, "PRODUCTION", ("pretend_package",), raising=False)
        monkeypatch.setattr(type(self), "PRODUCTION", ("pretend_package",))
        monkeypatch.setitem(globals(), "ROOT", tmp_path)
        assert self._offenders() == ["pretend_package/reader.py:2"]
