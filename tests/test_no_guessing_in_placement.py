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
  - the template's point functions are read whole;
  - in a read-whole function, every SQL ORDER BY orders by a recorded key
    (ORDER_KEYS) and every sort with no key is one named in BARE_SORTS, which
    sort names rather than runs (post-build-review #262 T6) - a bare
    sorted(run_ids) is the run-id text order this rule exists to remove;
  - the template's supply history and column drawer are read in their sort
    comparators, since they also date and name rows for display.

DELIBERATELY NOT READ: qa_results_reader.canonical_order, which sorts a
results FILE by run id so a live write and a rebuild produce the same bytes
(REQ-PIPE-038). It decides nothing about which result is newer or where one
is placed - the build re-orders by rank - so the rule has no claim on it.
Nothing else is excepted: an arrival run's dataset is passed to open_run by
the orchestrator from the arrival (Keith, 2026-10-24, provisional #23), and
_arrival_purpose, which records it with its supply, is read whole.
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
    # And the warehouse view's rule over them (REQ-PIPE-269 criterion 7).
    "qa_tools.common.supply_status": ("_shown", "results_about", "latest_results",
                                      "newest_per_check", "count", "counts_toward", "_matches",
                                      "_owed", "holdings_at", "owing"),
    "qa_tools.common.drift_reference": ("run_for",),
    "qa_tools.common.carried": ("siblings", "decide", "_evaluated_reads", "_supply_read"),
    "qa_tools.common.qa_results_writer": ("_arrival_purpose",),
}

#: WHAT AN ORDER BY IN A READ-WHOLE FUNCTION MAY ORDER BY, each a recorded key
#: and none a time or a run id's text: the opening order, a row's identity
#: within one run's recording, a table's name, and drift_reference.run_for's
#: preference for a run of the dataset itself.
ORDER_KEYS = ("run_seq", "id", "check_result_id", "logical_table",
              "(dataset_id IS DISTINCT FROM ?)")

#: Sorts with no key in read-whole functions, each sorting NAMES - tables,
#: datasets, checks, files - for stable output, never runs or results.
BARE_SORTS = {
    ("pipeline.build_dashboard_data", "share_cross_table_results"):
        ('sorted((r.get("reads") or {}).items())',),
    ("pipeline.build_dashboard_data", "_between"):
        ("sorted({hierarchy.dataset_for_table(t).dataset_id for t in reads}",),
    ("qa_tools.common.qa_results_reader", "read_check_reads"): ("sorted(files or ())",),
    ("qa_tools.common.carried", "decide"):
        ("sorted(_evaluated_reads(conn, sibling, open_).items())",),
    ("qa_tools.common.carried", "_evaluated_reads"): ("sorted(check_ids)",),
    ("qa_tools.common.supply_status", "_shown"): ("sorted(files or ())",),
    ("qa_tools.common.supply_status", "holdings_at"): ("sorted(set(dataset_ids))",),
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

#: The template's functions that also date and name rows for display, read in
#: their sort comparators only - which may not order by a time, a day or a run
#: id (post-build-review #262 T6). A chain of supplies is still ordered by its
#: PERIOD's date, which is not a run order.
JS_SORTED = ("buildSupplyHistory",)
JS_SORT_FORBIDDEN = ("recorded_at", "recordedAt", "Date.parse", "assetDateStrOf", "run_date",
                     "run_id", "runId", "toISOString", ".date")
#: Read whole, beside JS_FUNCTIONS: the column drawer's run dots.
JS_WHOLE_TOO = ("statusHistoryForColumn",)


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


def _order_by_violations(source: str) -> list[str]:
    """Each ORDER BY term not in ORDER_KEYS, a table alias dropped."""
    bad = []
    for clause in re.findall(r"ORDER BY (.*?)(?:LIMIT|\"|'|$)", source, re.S | re.M):
        for term in clause.split(","):
            term = re.sub(r"\b\w+\.(\w+)", r"\1", term.strip())
            term = re.sub(r"\s+(DESC|ASC)$", "", term)
            if term and term not in ORDER_KEYS:
                bad.append(term)
    return bad


def _bare_sorts(source: str) -> list[str]:
    """The source of every sorted, .sort, max or min given no key."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(
            node.func, "id", None)
        if name in ("sorted", "sort") and not any(k.arg == "key" for k in node.keywords):
            out.append(ast.get_source_segment(source, node))
    return out


def _unlisted_bare_sorts(module: str, name: str, source: str) -> list[str]:
    allowed = BARE_SORTS.get((module, name), ())
    return [s for s in _bare_sorts(source) if not any(s.startswith(a) for a in allowed)]


def _js_sort_comparators(text: str) -> list[str]:
    """The argument of every `.sort(` in a function, by parentheses."""
    out, i = [], 0
    while (i := text.find(".sort(", i)) != -1:
        start = i = i + len(".sort(")
        depth = 1
        while depth:
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            i += 1
        out.append(text[start:i - 1])
    return out


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

    @pytest.mark.parametrize("module, name", [(m, n) for m, ns in WHOLE.items() for n in ns])
    def test_placement_code_orders_by_recorded_keys_alone(self, module, name):
        source = _source_of(module, name)
        assert _order_by_violations(source) == [], f"{module}.{name}"
        assert _unlisted_bare_sorts(module, name, source) == [], f"{module}.{name}"

    def test_every_listed_bare_sort_is_still_there(self):
        """A BARE_SORTS entry whose sort has gone is a hole someone can walk a
        new sort through unnoticed."""
        for (module, name), sorts in BARE_SORTS.items():
            found = _bare_sorts(_source_of(module, name))
            assert all(any(s.startswith(a) for s in found) for a in sorts), (module, name)

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

    @pytest.mark.parametrize("name", JS_FUNCTIONS + JS_WHOLE_TOO)
    def test_the_templates_point_code_reads_no_time_or_day(self, name):
        assert _forbidden_in(_js_function(name), JS_FORBIDDEN) == [], name

    @pytest.mark.parametrize("name", JS_SORTED)
    def test_the_supply_history_sorts_by_no_time_day_or_run_id(self, name):
        comparators = _js_sort_comparators(_js_function(name))
        assert comparators, f"{name} sorts nothing - this reads nothing"
        assert [c for c in comparators if _forbidden_in(c, JS_SORT_FORBIDDEN)] == [], comparators

    def test_the_points_are_sorted_by_rank_alone(self):
        comparators = re.findall(r"\.sort\(\(a, ?b\)\s*=>(.*?)\);", _js_function("unitCounts"), re.S)
        assert comparators, "unitCounts sorts nothing - this reads nothing"
        assert all(".date" not in c and "runId" not in c for c in comparators), comparators


class TestTheGuardCanFail:
    """Rule 3: a guard over source has to be shown to catch what it is for -
    each against a deliberately broken copy of a real function's source, so
    a guard that stopped reading the real thing would fail here too (T6)."""

    def test_a_sort_by_recording_time_is_caught(self):
        real = _source_of("pipeline.build_dashboard_data", "build_one_table")
        keys = _ordering_keys(real)
        assert keys and not [k for k in keys if _forbidden_in(k)], "test precondition"
        assert f"key={keys[0]}" in real, "test precondition"
        broken = real.replace(f"key={keys[0]}", "key=lambda x: x['recorded_at']", 1)
        assert [k for k in _ordering_keys(broken) if _forbidden_in(k)]

    def test_a_run_id_parse_is_caught(self):
        real = _source_of("qa_tools.common.qa_results_writer", "_arrival_purpose")
        assert not _forbidden_in(real), "test precondition"
        broken = real.replace("res = supply_db.resolution_for(conn, run_id)",
                              "res = supply_db.resolution_for(conn, run_id)\n"
                              "    parts = supply_db.split_staged(run_id)", 1)
        assert broken != real and _forbidden_in(broken) == ["split_staged"]

    def test_an_order_by_run_key_is_caught(self):
        real = _source_of("qa_tools.common.supply_status", "_shown")
        assert _order_by_violations(real) == [], "test precondition"
        broken = real.replace("ORDER BY r.run_seq, c.id", "ORDER BY r.run_key, c.id")
        assert broken != real and _order_by_violations(broken) == ["run_key"]

    def test_a_bare_sort_of_run_ids_is_caught(self):
        real = _source_of("qa_tools.common.carried", "siblings")
        assert _unlisted_bare_sorts("qa_tools.common.carried", "siblings", real) == [], \
            "test precondition"
        assert real.count("return [row[0]") == 1 and real.rstrip().endswith("]"), \
            "test precondition"
        broken = real.replace("return [row[0]", "return sorted([row[0]", 1).rstrip() + ")"
        assert _unlisted_bare_sorts("qa_tools.common.carried", "siblings", broken)

    def test_a_supply_history_sorted_by_day_and_run_id_is_caught(self):
        real = _js_function("buildSupplyHistory")
        assert real.count("byRankThenSeen(") == 1, "test precondition"
        broken = real.replace("byRankThenSeen(a.r, a.i, b.r, b.i)",
                              "a.r.run_date.localeCompare(b.r.run_date) || "
                              "a.r.run_id.localeCompare(b.r.run_id)")
        assert [c for c in _js_sort_comparators(broken) if _forbidden_in(c, JS_SORT_FORBIDDEN)]
