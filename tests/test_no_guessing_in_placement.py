"""No placement or ordering code reads a recording time, a run id's text or a
calendar day (REQ-PIPE-279 criterion 20).

AN ARCHITECTURE RULE, READ FROM THE SOURCE, and allowed to be (CLAUDE.md, "a
test earns its place", rule 1): the behaviour the rule protects is an ORDER
nobody wrote, which shows only on the day two runs tie on a time or two ids
sort the wrong way - 62 groups of runs on ed_probe shared a run instant, and
`__r10` sorted before `__r9`. The behavioural tests (tests 1 to 26) pin the
cases known today; this is what stops the next function quietly reaching for
`recorded_at` or a run id again, which no test of today's data would notice.

KEPT NARROW, so it fails for the right reason only:
  - a function whose whole job is placement or ordering is read whole;
  - a function that ALSO dates or names a result for display - which may read
    `recorded_at`, REQ-DASH-264 criterion 9 and REQ-PIPE-279 criterion 16 say
    so - is read only in the keys of its sorts, max and min;
  - the view qa.supply_current_run is read in its ORDER BY;
  - the template's point functions are read whole.

DELIBERATELY NOT READ: qa_results_reader.canonical_order, which sorts a
results FILE by run id so a live write and a rebuild produce the same bytes
(REQ-PIPE-038). It decides nothing about which result is newer or where one
is placed - the build re-orders by rank - so the rule has no claim on it.
"""
from __future__ import annotations

import ast
import importlib
import inspect
import io
import re
import textwrap
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "dashboard" / "qa-reporting-dashboard.template.html"

#: What placement and ordering code may not read, in Python and SQL: a
#: recording time, a run id's text, a calendar day.
FORBIDDEN = (
    "recorded_at", "run_timestamp", "run_instant", "created_at",
    "run_owner", "split_staged", "split_run", "RERUN_MARK", "_natural_sort_key", "LIKE",
    "run_index", "_run_date", "local_date", "assetDateStrOf", ".date()",
)

#: Read whole: their job is to place or order.
WHOLE = {
    "pipeline.build_dashboard_data": ("own_runs", "share_cross_table_results", "_supply_read",
                                      "_between"),
    "qa_tools.common.qa_results_reader": ("list_run_ids", "run_facts", "read_check_reads",
                                          "current_runs_only"),
    "qa_tools.common.qa_store": ("runs_for",),
    "qa_tools.common.supply_status": ("results_about", "latest_results"),
    "qa_tools.common.drift_reference": ("run_for",),
    "qa_tools.common.carried": ("siblings", "decide", "_evaluated_reads", "_supply_read"),
}

#: Read only in their sort, max and min keys: they also date results for display.
KEYS_ONLY = {
    "pipeline.build_dashboard_data": ("build_one_table", "build_datasets"),
    "qa_tools.tools.results_history": ("build_results_from_history",),
}

#: The template's point functions, read whole, and what they may not read.
JS_FUNCTIONS = ("unitCounts", "sameDelivery", "defaultCompareIndex", "historyPoints",
                "pointKey", "deliveryCount", "compareParamFor")
JS_FORBIDDEN = ("recorded_at", "recordedAt", "Date.parse", "assetDateStrOf", "run_date",
                "recordedDayOf", "localeCompare", "toISOString")


def _forbidden_in(text: str, forbidden=FORBIDDEN) -> list[str]:
    return [token for token in forbidden if token in text]


def _source_of(module: str, name: str) -> str:
    """The function's CODE: its comments and docstring dropped, which say
    what the rule replaced and would otherwise trip it, and its string
    literals kept, since its SQL is in them."""
    fn = getattr(importlib.import_module(module), name)
    source = textwrap.dedent(inspect.getsource(fn))
    assert source.strip(), f"{module}.{name} has no source to read"
    tree = ast.parse(source)
    body = tree.body[0].body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None),
                                                             ast.Constant):
        lines = source.splitlines(keepends=True)
        for i in range(body[0].lineno - 1, body[0].end_lineno):
            lines[i] = "\n"
        source = "".join(lines)
    code = [tok for tok in tokenize.generate_tokens(io.StringIO(source).readline)
            if tok.type != tokenize.COMMENT]
    return tokenize.untokenize(code)


def _ordering_keys(source: str) -> list[str]:
    """The source of every `key=` given to sorted, .sort, max or min."""
    keys = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(
            node.func, "id", None)
        if name not in ("sorted", "sort", "max", "min"):
            continue
        keys += [ast.get_source_segment(source, k.value) for k in node.keywords if k.arg == "key"]
    return keys


def _js_function(name: str) -> str:
    """One top-level `function name(...){...}` of the template, by braces."""
    text = TEMPLATE.read_text()
    start = text.index(f"function {name}(")
    depth, i = 0, text.index("{", start)
    for j in range(i, len(text)):
        depth += {"{": 1, "}": -1}.get(text[j], 0)
        if depth == 0:
            return text[start:j + 1]
    raise AssertionError(f"{name} never closes")


class TestTheRuleIsKept:

    @pytest.mark.parametrize("module, name", [(m, n) for m, ns in WHOLE.items() for n in ns])
    def test_placement_code_reads_no_time_run_id_or_day(self, module, name):
        assert _forbidden_in(_source_of(module, name)) == [], f"{module}.{name}"

    @pytest.mark.parametrize("module, name", [(m, n) for m, ns in KEYS_ONLY.items() for n in ns])
    def test_no_sort_orders_by_one(self, module, name):
        keys = _ordering_keys(_source_of(module, name))
        assert keys, f"{module}.{name} sorts nothing - this reads nothing"
        assert [k for k in keys if _forbidden_in(k)] == [], f"{module}.{name}"

    def test_a_supplys_current_run_is_ordered_by_run_seq_alone(self):
        from qa_tools.common import qa_store

        view = qa_store.DDL[qa_store.DDL.index('CREATE VIEW "{SCHEMA}".supply_current_run'
                                               .replace("{SCHEMA}", qa_store.SCHEMA)):]
        order = view[view.index("ORDER BY"):view.index(";")]
        assert _forbidden_in(order) == [] and "run_key" not in order, order

    @pytest.mark.parametrize("name", JS_FUNCTIONS)
    def test_the_templates_point_code_reads_no_time_or_day(self, name):
        assert _forbidden_in(_js_function(name), JS_FORBIDDEN) == [], name

    def test_the_points_are_sorted_by_rank_alone(self):
        comparators = re.findall(r"\.sort\(\(a, ?b\)\s*=>(.*?)\);", _js_function("unitCounts"), re.S)
        assert comparators, "unitCounts sorts nothing - this reads nothing"
        assert all(".date" not in c and "runId" not in c for c in comparators), comparators


class TestTheGuardCanFail:
    """Rule 3: a guard over source has to be shown to catch what it is for."""

    def test_a_sort_by_recording_time_is_caught(self):
        keys = _ordering_keys("def f(h):\n    return max(h, key=lambda x: x['recorded_at'])\n")
        assert [k for k in keys if _forbidden_in(k)] == ["lambda x: x['recorded_at']"]

    def test_a_run_id_parse_is_caught(self):
        assert _forbidden_in("parts = supply_db.split_staged(run_id)") == ["split_staged"]
