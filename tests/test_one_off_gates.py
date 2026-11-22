"""`mothman check` and one-off folders (REQ-PIPE-448 criteria 1, 3 and 5).

Driven through the test kind of tests/one_off_support.py, as REQ-PIPE-446's
tests are. `mothman check` itself runs in a subprocess with the resolver
pointed at the test's one-offs root and the test kind registered, its gates
narrowed by --only to one cheap gate.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import one_off_support
from asset_model import assets, one_off_kinds
from cli import check

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def one_offs(tmp_path, monkeypatch):
    world = one_off_support.OneOffs(tmp_path, monkeypatch)
    yield world
    world.close()


def _declaring(**gates):
    kind = one_off_kinds.Kind(name="audit", singular="audit", plural="audits",
                              layer="Audit check", gates=gates)
    one_off_kinds.unregister("audit")
    one_off_kinds.register(kind)
    return kind


class TestEveryGateIsDeclaredPerKind:
    """Criterion 1."""

    def test_a_kind_with_folders_and_no_declaration_is_named(self, one_offs):
        one_offs.add("cohort-a")
        _declaring(hierarchy=True)
        assert check.undeclared("hierarchy") == []
        assert check.undeclared("schedule") == ["audit"]

    def test_a_repository_wide_gate_asks_no_kind(self, one_offs):
        one_offs.add("cohort-a")
        _declaring()
        assert check.undeclared("ruff") == []

    def test_a_kind_with_no_folders_is_not_asked(self, one_offs):
        _declaring()
        assert check.undeclared("schedule") == []

    def test_not_applicable_is_worded_for_the_kind(self, one_offs):
        kind = _declaring()
        assert check.not_applicable_text(kind) == "not applicable (audit)"
        assert check.NOT_APPLICABLE_TEXT == "not applicable (no synthetic/ folder)"


class TestTheNotApplicableLine:
    """Criterion 3's one line, and its silence where there are no one-offs."""

    def test_one_line_per_kind_listing_every_gate_that_does_not_apply(self, one_offs):
        one_offs.add("cohort-a")
        _declaring(**{g: g not in ("providers", "scenarios") for g in check.per_asset_gates()})
        assert check.not_applicable_lines() == ["not applicable (audit): providers, scenarios"]

    def test_nothing_where_there_are_no_one_offs(self, one_offs):
        _declaring(providers=False)
        assert check.not_applicable_lines() == []


_DRIVER = """
import sys, runpy
from pathlib import Path
from asset_model import assets, one_off_kinds
assets.use_one_offs_root(Path(sys.argv[1]))
one_off_kinds.register(one_off_kinds.Kind("audit", "audit", "audits", "Audit check",
                                          gates={"people": True}))
sys.argv = ["mothman", *sys.argv[2:]]
runpy.run_module("cli.app", run_name="__main__")
"""


class TestTheCommand:
    """Criterion 1's refusal, through `mothman check --only`."""

    def _check(self, root, gate):
        env = {k: v for k, v in os.environ.items() if k != assets.ASSET_ENV}
        done = subprocess.run([sys.executable, "-c", _DRIVER, str(root), "check", "--only", gate],
                              cwd=ROOT, env=env, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=300)
        return done.returncode, re.sub(r"[│╭╮╰╯─\s]+", " ", done.stdout + done.stderr)

    def test_an_undeclared_gate_is_refused_not_run(self, one_offs):
        one_offs.add("cohort-a")
        code, said = self._check(one_offs.root, "patterns")
        assert code != 0
        assert "not run - one-off kind(s) audit do not declare whether it applies" in said, said

    def test_a_declared_gate_runs_and_over_the_one_off_folder_too(self, one_offs):
        """The asset passes, then the one-off's row: a hand-made test folder has
        no recorded digest, so it is named failing - criterion 2 at work."""
        one_offs.add("cohort-a")
        code, said = self._check(one_offs.root, "people")
        assert "people validation OK" in said
        assert "people (audits: 1 in full, 0 by digest; failed: cohort-a)" in said, said
        assert "no generated.sha256.json" in said and code != 0


class TestNoWorkflowOrHookTouchesAOneOff:
    """Criterion 5. READS SOURCE ON PURPOSE: 'no CI workflow or session-start
    hook loops over, selects or loads a one-off' is an architecture rule with no
    behaviour to observe from here - the workflows run on GitHub's runners and
    the hook at session start. So every `run:` step of every workflow and the
    hook's script are read, and none may name the one-offs root, the one-off
    command group or a one-off id flag."""

    _TOUCHES = re.compile(r"one-offs/|mothman one-off|one_off|--id\b")

    def _runs(self) -> list[tuple[str, str]]:
        found = []
        for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            for job in (yaml.safe_load(wf.read_text()).get("jobs") or {}).values():
                for step in job.get("steps") or []:
                    if step.get("run"):
                        found.append((wf.name, step["run"]))
        settings = yaml.safe_load((ROOT / ".claude" / "settings.json").read_text())
        for entry in settings["hooks"]["SessionStart"]:
            for hook in entry["hooks"]:
                script = Path(hook["command"].replace("$CLAUDE_PROJECT_DIR", str(ROOT)))
                found.append((script.name, script.read_text()))
        return found

    def test_there_is_something_to_read(self):
        assert len(self._runs()) > 10

    def test_none_touches_a_one_off(self):
        touching = [(where, m.group(0)) for where, text in self._runs()
                    for m in [self._TOUCHES.search(text)] if m]
        assert touching == []


pytestmark = pytest.mark.asset("daily")


# ---- criterion 2 and 3's rows: changed folders in full, the rest by digest ----

import extraction_support as ex  # noqa: E402


@pytest.fixture
def extraction(tmp_path, monkeypatch):
    """One generated extraction folder, under a one-offs root pointed elsewhere."""
    from asset_model.kinds import extraction_folder as ef
    from asset_model.kinds import extraction_recipe as er

    root = tmp_path / "one-offs"
    root.mkdir()
    before = assets.use_one_offs_root(root)
    monkeypatch.delenv(assets.ASSET_ENV, raising=False)
    folder = ef.generate(er.read(str(ex.package(tmp_path / "pkg"))), root)
    yield folder
    assets.deselect_one_off()
    assets.restore(before)


class TestEachFolderIsGated:
    def test_a_changed_folder_is_gated_in_full_through_the_hidden_command(self, extraction):
        from qa_tools.common import one_off_gating

        code, said = one_off_gating.gate_folder("people", "cohort-2026-a")
        assert code == 0, said
        assert "people validation OK" in said

    def test_the_row_counts_in_full_and_by_digest(self, extraction, monkeypatch):
        from qa_tools.common import one_off_gating

        monkeypatch.setattr(one_off_gating, "changed", lambda folder, base=None: True)
        ((shown, code, *_rest, got),) = check.one_off_rows("people", "why", False)
        assert code == 0 and got == {"full": 1, "digest": 0, "failed": {}}
        assert shown == "people (extractions: 1 in full, 0 by digest)"

    def test_an_unchanged_folder_is_checked_by_digest(self, extraction, monkeypatch):
        from qa_tools.common import one_off_gating

        monkeypatch.setattr(one_off_gating, "changed", lambda folder, base=None: False)
        monkeypatch.setattr(one_off_gating, "gate_folder",
                            lambda *a: pytest.fail("gated in full"))
        ((shown, code, *_rest),) = check.one_off_rows("people", "why", False)
        assert code == 0 and shown == "people (extractions: 0 in full, 1 by digest)"

    def test_a_digest_failure_names_the_folder_and_the_first_file(self, extraction, monkeypatch):
        from qa_tools.common import one_off_gating

        monkeypatch.setattr(one_off_gating, "changed", lambda folder, base=None: False)
        (extraction / "presentation.yaml").write_text("edited by hand\n")
        ((shown, code, *_rest, got),) = check.one_off_rows("people", "why", False)
        assert code == 1 and "failed: cohort-2026-a" in shown
        assert "presentation.yaml differs" in got["failed"]["cohort-2026-a"]

    def test_an_untracked_file_counts_and_dbt_artefacts_do_not(self, extraction):
        from qa_tools.common import one_off_gating

        (extraction / "dbt" / "target").mkdir()
        (extraction / "dbt" / "target" / "manifest.json").write_text("{}")
        assert one_off_gating.digest_problem(extraction) is None
        (extraction / "notes.txt").write_text("added by hand")
        assert "notes.txt is not one of its generated files" in \
            one_off_gating.digest_problem(extraction)

    def test_a_gate_that_does_not_apply_gives_no_row(self, extraction):
        assert check.one_off_rows("providers", "why", False) == []

    def test_the_result_line_counts_them(self):
        line = check.result_line(tree="t", tree_after="t", counts=(1, 0, 0), coverage=None,
                                 floor=None, elapsed=1, failed_gates=[],
                                 one_offs=[{"full": 2, "digest": 5}, {"full": 1, "digest": 0}])
        assert "one-offs: 3 folder-gate(s) in full, 5 by digest" in line
        assert "one-offs" not in check.result_line(tree="t", tree_after="t", counts=(1, 0, 0),
                                                    coverage=None, floor=None, elapsed=1,
                                                    failed_gates=[])


class TestTheCollectionsGateAcceptsTheSharedAdapter:
    """Criterion 4: a one-off's collections are served by its kind's one shared
    adapter, resolved through the adapter registry - and an enduring asset's
    collection without an adapter of its own still fails."""

    def test_a_generated_extraction_passes_the_collections_gate(self, extraction):
        from qa_tools.common import one_off_gating

        code, said = one_off_gating.gate_folder("collections", "cohort-2026-a")
        assert code == 0, said
        assert "has no adapter" not in said and "outside every collection" not in said

    def test_the_registry_resolves_the_kinds_adapter(self, extraction):
        from qa_tools import collections

        assets.select_one_off("cohort-2026-a")
        got = collections.adapter("cohort-study")
        assert got.collection_id == "cohort-study"
        assert got.sample_key == {"cohort_people": ["person_id"],
                                  "cohort_visits": ["visit_id"]}
        assert collections.adapter_file("cohort-study").endswith(
            "qa_tools/collections/kinds/extraction.py")

    def test_an_enduring_assets_collection_without_one_still_fails(self, tmp_path):
        from qa_tools.common import validate_collections

        package = tmp_path / "adapters"
        package.mkdir()
        problems = validate_collections.config_problems(package)
        assert any("has no adapter" in p for p in problems), problems
