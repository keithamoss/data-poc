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

    def test_cp_files_before_it_runs_the_manifest(self):
        filed = _call_lines("qa_tools.cp.orchestrate_cp", "run_pipeline_cp",
                            "filing.file_arrivals")
        ran = _call_lines("qa_tools.cp.orchestrate_cp", "run_pipeline_cp",
                          "parallel_orchestrate.run_manifest")
        assert filed, "filing is never actually called - a comment mentioning it is not a call"
        assert ran, "the manifest run could not be found, so the order cannot be judged"
        assert filed[0] < ran[0], \
            "a check running before the slot is recorded has nothing to classify against"

    def test_bdm_files_before_it_runs_the_manifest(self):
        filed = _call_lines("qa_tools.bdm.orchestrate_bdm", "run_pipeline",
                            "filing.file_arrivals")
        ran = _call_lines("qa_tools.bdm.orchestrate_bdm", "run_pipeline",
                          "parallel_orchestrate.run_manifest")
        assert filed, "filing is never actually called - a comment mentioning it is not a call"
        assert ran, "the manifest run could not be found, so the order cannot be judged"
        assert filed[0] < ran[0], \
            "a check running before the slot is recorded has nothing to classify against"
