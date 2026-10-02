"""REQ-PIPE-075 criterion 7 - a filing is recorded BEFORE any check runs.

The order is the requirement, so these observe the ORDER rather than the
outcome. Asserting that filings exist after a pipeline run would pass
just as well if filing happened last, which is the case the criterion
exists to rule out: a check classifies a supply as early, on time or
late against its SLOT, so a check running before the slot is recorded
has nothing to classify against.

THESE ASSERT ON THE AST, NOT ON THE SOURCE TEXT, and that is not
fastidiousness. The first version of this file searched
inspect.getsource() for "filing.file_arrivals(" - and passed against the
UNCHANGED orchestrators, because the old code mentioned that exact
string in a COMMENT explaining why the call was deliberately absent. A
test that a comment can satisfy is a test of nothing. Checked by
stashing the change and re-running, which is the only reason it was
found.

Both orchestrators are pinned, because they were changed together and
the cheapest way for this to regress is somebody editing one.
"""
from __future__ import annotations

import ast
import inspect


def _call_lines(module_name: str, func_name: str, dotted: str) -> list[int]:
    """Line numbers of every real CALL to `dotted` in this function.

    A comment mentioning the name is not a call and does not appear
    here, which is the whole point.
    """
    module = __import__(module_name, fromlist=[func_name])
    source = inspect.getsource(getattr(module, func_name))
    tree = ast.parse(source.lstrip() if source.startswith(" ") else source)
    wanted = dotted.split(".")
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        parts = []
        target = node.func
        while isinstance(target, ast.Attribute):
            parts.append(target.attr)
            target = target.value
        if isinstance(target, ast.Name):
            parts.append(target.id)
        if list(reversed(parts))[-len(wanted):] == wanted:
            found.append(node.lineno)
    return sorted(found)


class TestTheFilingCallComesBeforeTheToolRuns:
    """THE CALL MOVED, 2026-10-02 (REQ-PIPE-105). Filing now lives in each
    orchestrator's file_and_overlay(), which the batch's before-each hook
    calls and `mothman bdm/cp qa --commit` calls too - so a hand-filed
    supply and a batch one cannot be filed differently. What is pinned
    is the same order, one function further in: the batch reaches
    file_and_overlay before the manifest runs, and file_and_overlay files
    BEFORE it builds the period overlay, which needs the filing."""

    def test_cp_files_before_it_runs_the_manifest(self):
        filed = _call_lines("qa_tools.cp.orchestrate_cp", "run_pipeline_cp",
                            "file_and_overlay")
        ran = _call_lines("qa_tools.cp.orchestrate_cp", "run_pipeline_cp",
                          "parallel_orchestrate.run_manifest")
        assert filed, "filing is never actually called - a comment mentioning it is not a call"
        assert ran, "the manifest run could not be found, so the order cannot be judged"
        assert filed[0] < ran[0], \
            "a check running before the slot is recorded has nothing to classify against"

    def test_bdm_files_before_it_runs_the_manifest(self):
        filed = _call_lines("qa_tools.bdm.orchestrate_bdm", "run_pipeline",
                            "file_and_overlay")
        ran = _call_lines("qa_tools.bdm.orchestrate_bdm", "run_pipeline",
                          "parallel_orchestrate.run_manifest")
        assert filed, "filing is never actually called - a comment mentioning it is not a call"
        assert ran, "the manifest run could not be found, so the order cannot be judged"
        assert filed[0] < ran[0], \
            "a check running before the slot is recorded has nothing to classify against"

    def test_both_file_before_they_build_the_overlay(self):
        for module in ("qa_tools.cp.orchestrate_cp", "qa_tools.bdm.orchestrate_bdm"):
            filed = _call_lines(module, "file_and_overlay", "filing.file_arrivals")
            overlaid = _call_lines(module, "file_and_overlay",
                                   "period_overlay.rebuild_for_arrival")
            assert filed and overlaid, module
            assert filed[0] < overlaid[0], \
                f"{module}: the overlay reads the period the filing decides"


def _run_manifest_keywords(module_name: str, func_name: str) -> set[str]:
    module = __import__(module_name, fromlist=[func_name])
    source = inspect.getsource(getattr(module, func_name))
    tree = ast.parse(source.lstrip() if source.startswith(" ") else source)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "run_manifest"):
            return {kw.arg for kw in node.keywords if kw.arg}
    return set()


def _file_arrivals_arguments(module_name: str, func_name: str) -> list[ast.expr]:
    module = __import__(module_name, fromlist=[func_name])
    source = inspect.getsource(getattr(module, func_name))
    tree = ast.parse(source.lstrip() if source.startswith(" ") else source)
    out = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "file_arrivals" and node.args):
            out.append(node.args[0])
    return out


class TestFilingIsInterleavedRatherThanDoneUpFront:
    """The defect this class exists for, found by running the real
    pipeline against a scratch database.

    A supply is filed to the oldest slot no PROMOTION has filled. Filing
    every arrival before any of them is checked means no slot is ever
    filled while the filings are being made - so all 108 Child
    Protection supplies filed to 2023-Q1 and six promoted. One arrival
    at a time, they spread across all fifteen quarters and 67 promote.

    Criterion 7 is still satisfied, and more narrowly than before: the
    filing precedes the checks OF THAT ARRIVAL rather than of the batch.
    """

    def test_cp_hands_the_manifest_run_both_hooks(self):
        assert {"before_each", "after_each"} <= _run_manifest_keywords(
            "qa_tools.cp.orchestrate_cp", "run_pipeline_cp")

    def test_bdm_hands_the_manifest_run_both_hooks(self):
        assert {"before_each", "after_each"} <= _run_manifest_keywords(
            "qa_tools.bdm.orchestrate_bdm", "run_pipeline")

    def test_cp_does_not_file_the_whole_batch_at_once(self):
        args = _file_arrivals_arguments("qa_tools.cp.orchestrate_cp", "file_and_overlay")
        assert args, "filing is never actually called"
        for arg in args:
            assert isinstance(arg, ast.List) and len(arg.elts) == 1, \
                "filing the whole batch up front puts every supply in the first slot"

    def test_bdm_does_not_file_the_whole_batch_at_once(self):
        args = _file_arrivals_arguments("qa_tools.bdm.orchestrate_bdm", "file_and_overlay")
        assert args, "filing is never actually called"
        for arg in args:
            assert isinstance(arg, ast.List) and len(arg.elts) == 1, \
                "filing the whole batch up front puts every supply in the first slot"
