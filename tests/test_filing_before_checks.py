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
    """THE CALL MOVED, 2026-10-02 (REQ-PIPE-105). Filing now lives in the
    orchestrator's file_and_overlay(), which the batch's before-each hook
    calls and `mothman bdm/cp qa --commit` calls too - so a hand-filed
    supply and a batch one cannot be filed differently. What is pinned
    is the same order, one function further in: the batch reaches
    file_and_overlay before the manifest runs, and file_and_overlay files
    BEFORE it builds the period overlay, which needs the filing."""



    def test_both_batches_go_through_the_lifecycle(self):
        for module, function in (("qa_tools.tools.orchestrate", "run_pipeline"),):
            assert _call_lines(module, function, "arrival_lifecycle.process_all"), module
            assert not _call_lines(module, function, "parallel_orchestrate.run_manifest"), \
                f"{module} composes a second copy of the lifecycle"

    def test_no_batch_or_hand_filed_path_composes_the_steps_itself(self):
        """The guard criterion 2 actually needs: a second composition
        written as a plain inline loop would pass the test above, so the
        step functions must not be called directly outside the lifecycle
        (delivery-critic, sprint 1)."""
        for module, function in (("qa_tools.tools.orchestrate", "run_pipeline"),
                                 ("qa_tools.tools.orchestrate", "run_arrivals")):
            assert _call_lines(module, function, "arrival_lifecycle.process_all"), \
                f"{module}.{function} does not go through the lifecycle"
            for step in ("file_and_overlay", "promote_after", "run_one"):
                assert not _call_lines(module, function, step), \
                    f"{module}.{function} calls {step} itself - a second composition"

    def test_both_file_before_they_build_the_overlay(self):
        for module in ("qa_tools.tools.orchestrate",):
            filed = _call_lines(module, "file_and_overlay", "filing.file_arrivals")
            overlaid = _call_lines(module, "file_and_overlay",
                                   "period_overlay.rebuild_for_arrival")
            assert filed and overlaid, module
            assert filed[0] < overlaid[0], \
                f"{module}: the overlay reads the period the filing decides"


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

    (Written under the old rule - a supply filed to the oldest slot no
    PROMOTION had filled. REQ-PIPE-131's open-slot rule still reads
    promotion state, to tell a fill from a resupply.) Filing
    every arrival before any of them is checked means no slot is ever
    filled while the filings are being made - so all 108 Child
    Protection supplies filed to 2023-Q1 and six promoted. One arrival
    at a time, they spread across all fifteen quarters and 67 promote.

    Criterion 7 is still satisfied, and more narrowly than before: the
    filing precedes the checks OF THAT ARRIVAL rather than of the batch.
    """

    def test_no_collection_files_the_whole_batch_at_once(self):
        """One shared file_and_overlay() (REQ-PIPE-243): under Birth
        Registrations' `orchestrate.files_one_arrival` flag the one arrival
        is filed, otherwise the arrivals sharing its receipt instant - and
        on neither branch is `among`, the whole pass, handed to filing."""
        args = _file_arrivals_arguments("qa_tools.tools.orchestrate", "file_and_overlay")
        assert args, "filing is never actually called"
        for arg in args:
            branches = [arg.body, arg.orelse] if isinstance(arg, ast.IfExp) else [arg]
            for branch in branches:
                assert not (isinstance(branch, ast.Name) and branch.id == "among"), \
                    "filing the whole batch up front puts every supply in the first slot"
                if isinstance(branch, ast.List):
                    assert len(branch.elts) == 1
                else:
                    assert isinstance(branch, ast.Call) and branch.func.id == "simultaneous_with"


class TestSimultaneousArrivalsAreFiledTogether:
    """REQ-PIPE-105 criterion 5, 2026-10-03 (Keith): files sharing ONE
    receipt instant - a zip - are all filed before any of them is checked.

    REAL DEFECT, found by the first regenerate with criterion 13 wired.
    Each file was filed just before its own run, and the overlay reads
    only FILED siblings, so the first file of a zip saw none of the rest
    and the last saw all of them. All 90 "could not be evaluated" reds in
    that regenerate were about a table the supply's own arrival carried.

    Still not the whole batch at once - the class above is why - and
    never a LATER arrival, which would be waiting under criterion 1.
    """

    @staticmethod
    def _arrivals():
        from datetime import datetime, timedelta, timezone
        from types import SimpleNamespace

        t = datetime(2026, 5, 27, 1, tzinfo=timezone.utc)
        mk = lambda name, at, seq: SimpleNamespace(  # noqa: E731
            run_id=name, received_at=at, sequence=seq, run_index=0)
        return [mk("cp_carers__a", t, 1), mk("cp_clients__a", t, 2),
                mk("cp_placements__a", t, 3),
                mk("cp_clients__b", t + timedelta(minutes=3), 4)]

    def _filed_by(self, monkeypatch, target, among):
        from qa_tools.common import filing, period_overlay

        calls: list[list[str]] = []
        monkeypatch.setattr(filing, "file_arrivals",
                            lambda arrivals: calls.append([a.run_id for a in arrivals]))
        monkeypatch.setattr(period_overlay, "rebuild_for_arrival", lambda *a, **k: None)
        from qa_tools.tools import orchestrate

        orchestrate.file_and_overlay("child-protection", target, among=among)
        return [r for call in calls for r in call]

    def test_the_first_file_of_a_zip_files_its_siblings_too(self, monkeypatch):
        arrivals = self._arrivals()
        filed = self._filed_by(monkeypatch, arrivals[0], arrivals)
        assert sorted(filed) == ["cp_carers__a", "cp_clients__a", "cp_placements__a"]

    def test_a_later_arrival_is_never_filed_early(self, monkeypatch):
        arrivals = self._arrivals()
        assert "cp_clients__b" not in self._filed_by(monkeypatch, arrivals[0], arrivals)

    def test_a_trickled_file_is_filed_alone(self, monkeypatch):
        arrivals = self._arrivals()
        assert self._filed_by(monkeypatch, arrivals[3], arrivals) == ["cp_clients__b"]

    def test_with_nothing_to_compare_against_it_files_itself(self, monkeypatch):
        arrivals = self._arrivals()
        assert self._filed_by(monkeypatch, arrivals[1], None) == ["cp_clients__a"]
