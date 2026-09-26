"""
Reads Phase 1's committed `qa_results/` tree back - the read side of
plans/publishing-and-history.md Thread B/Phase 2. Lets the dashboard
pipeline rebuild `reports/*.json` purely from committed history, with
no real tool re-run and no live per-run DuckDB/CSV access needed.

Deliberately dumb: each committed file's own `verified` field (written
by every `qa_tools/*/run_*.py` module via `qa_results_writer.py` - see
that module's own docstring for why `verified` exists, not `raw_output`
alone) already holds the fully-resolved, dashboard-ready check-result
records for that tool+run, built once at run time when a live DB
connection to that run's own per-run warehouse naturally exists. This
module's only job is finding and concatenating those already-resolved
records back into one flat list - not reshaping anything itself.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
QA_RESULTS_DIR = ROOT / "qa_results"

_DIGIT_RUN = re.compile(r"(\d+)")


def _natural_sort_key(name: str) -> tuple:
    """Sorts run_id-shaped strings ("run_5_2026-01-01", "cp_run_005_...",
    "run_120_2026-09-18_resupply2") in real numeric/chronological order
    regardless of how many digits any of their numbers happen to have -
    a plain string sort of these (what both this module's own callers
    used to do) silently breaks the moment a run number crosses a fixed
    zero-padding width (2026-09-17: generator/generate_runs.py's
    delivery/run numbering went 60->120 deliveries and immediately hit
    exactly this - "delivery_100" < "delivery_11" as plain strings - a
    real bug a test caught; see that module's own comment). Keith's own
    call once that surfaced: this dataset's real run count will keep
    growing into the thousands over the life of the project, so a wider
    FIXED width (":03d" instead of ":02d") is not a real fix, just a
    bigger version of the same bug waiting to reoccur - this splits the
    string into alternating text/number runs and compares numbers as
    ints instead, so it's correct at any width, forever, with no digit
    count to eventually outgrow."""
    return tuple(int(part) if part.isdigit() else part for part in _DIGIT_RUN.split(name))

# Matches orchestrate_bdm.py's/orchestrate_cp.py's own _run_one()
# construction order - keeps a history-rebuilt results list in the same
# run-then-tool order a live orchestrator run always produced, so a diff
# against a live run's own reports/*.json output is a real equivalence
# check, not noise from an incidental reordering.
TOOL_ORDER = ["dbt", "soda", "datacontract", "evidently"]

#: Every file a COMPLETE run writes AT COLLECTION LEVEL - the four real
#: tools' raw output plus the two pseudo-tools (REQ-PIPE-036 criterion
#: 12). A run missing any of these failed partway through, and the
#: point of deriving completeness this way rather than writing a marker
#: file is that there is no third state to get wrong: a run is complete
#: because everything it owes is there, not because something said so.
#:
#: These live in RAW_SCOPE since REQ-PIPE-038, which is what makes the
#: rule uniform - every invocation writes its raw output there whether
#: or not it produced a record for any given dataset.
EXPECTED_TOOLS = tuple(TOOL_ORDER) + ("dataset_stats", "tables_read")


def expected_tools_for(dataset: str) -> tuple[str, ...]:
    """The tools a given DATASET owes a file, derived from the checks
    actually defined against it (REQ-PIPE-038, Keith 2026-09-26).

    Not the fixed list above. Evidently defines exactly one check in
    the whole Child Protection collection, on cp-notifications, so a
    fixed rule would report the other five datasets permanently
    incomplete - and a completeness signal that is always false says
    nothing about the thing it exists to catch. Rejected writing an
    empty evidently.json under the other five: a file that exists
    asserts the tool ran, and it did not.

    Derived rather than configured, so adding a dataset's first
    Evidently check changes what that dataset owes with no list to
    remember.
    """
    from pipeline.dashboard_check_labels import try_parse
    from qa_tools.common.validate_check_lifecycle import collect_checks

    tools = set()
    for check in collect_checks(None):
        parsed = try_parse(check.check_id)
        if parsed and parsed.dataset == dataset:
            tools.add(_TOOL_OF_CHECK(check.check_id))
    return tuple(tool for tool in TOOL_ORDER if tool in tools)


def _TOOL_OF_CHECK(check_id: str) -> str:
    """Which of the four tools wrote a check, from its id's own tail -
    every tail ends `_dbt`, `_soda`, `_datacontract` or `_evidently`
    (REQ-QAC-023's naming rule, which the lifecycle gate enforces)."""
    tail = check_id.rsplit(".", 1)[-1]
    for tool in TOOL_ORDER:
        if tail.endswith(f"_{tool}"):
            return tool
    return ""


def _run_dirs(scope_dir: Path):
    """Every RUN directory under one scope.

    A RESERVED SCOPE IS A SIBLING OF A DATASET, not a run under one
    (REQ-QAC-037, REQ-PIPE-038). `_cross-table/` and `_raw/` each hold
    run directories of their own, so anything walking a COLLECTION has
    to skip them or it reads a scope as a run - which shows up as a run
    called "_raw" that is missing most of its files.
    """
    from qa_tools.common import tables_read as tables_read_mod

    if not scope_dir.is_dir():
        return []
    return [d for d in scope_dir.iterdir()
            if d.is_dir() and not tables_read_mod.is_reserved_scope(d.name)]


class PartialRunError(RuntimeError):
    """A run whose results are on disk but incomplete."""


def _raw_dir(agency: str, collection: str, qa_results_dir: Path | str) -> Path:
    from qa_tools.common import tables_read as tables_read_mod

    return Path(qa_results_dir) / agency / collection / tables_read_mod.RAW_SCOPE


def _datasets_on_disk(agency: str, collection: str,
                       qa_results_dir: Path | str = QA_RESULTS_DIR) -> list[str]:
    """The dataset scopes actually present under this collection.

    Read from the tree rather than from the hierarchy config on
    purpose: this answers "what did the runs write", and a dataset
    added to the config yesterday has no history yet.
    """
    from qa_tools.common import tables_read as tables_read_mod

    collection_dir = Path(qa_results_dir) / agency / collection
    if not collection_dir.is_dir():
        return []
    return sorted(d.name for d in collection_dir.iterdir()
                   if d.is_dir() and not tables_read_mod.is_reserved_scope(d.name))


def missing_tools(agency: str, collection: str, run_id: str,
                   qa_results_dir: Path | str = QA_RESULTS_DIR) -> list[str]:
    """What this run still owes, or [] where it owes nothing.

    TWO SCOPES SINCE REQ-PIPE-038, and each answers a different half.
    `_raw/` must hold all six files, because every invocation writes
    its raw output there whatever its records say - that is the half
    that catches a run which died between tools. Each DATASET must hold
    the tools that define a check against it, which is the half that
    catches a tool running but writing nothing.

    A dataset's owings are derived rather than fixed, so the five
    Child Protection datasets Evidently has no check for are not
    reported as permanently incomplete.
    """
    raw_dir = _raw_dir(agency, collection, qa_results_dir) / run_id
    missing = [f"_raw/{tool}" for tool in EXPECTED_TOOLS
                if not (raw_dir / f"{tool}.json").exists()]
    for dataset in _datasets_on_disk(agency, collection, qa_results_dir):
        dataset_run = Path(qa_results_dir) / agency / collection / dataset / run_id
        if not dataset_run.is_dir():
            continue
        missing += [f"{dataset}/{tool}" for tool in expected_tools_for(dataset)
                     if not (dataset_run / f"{tool}.json").exists()]
    return missing


def run_is_complete(agency: str, collection: str, run_id: str,
                     qa_results_dir: Path | str = QA_RESULTS_DIR) -> bool:
    return not missing_tools(agency, collection, run_id, qa_results_dir)


def incomplete_runs(agency: str, collection: str,
                     qa_results_dir: Path | str = QA_RESULTS_DIR) -> dict[str, list[str]]:
    """Every run under this collection that failed partway, and what
    each is missing."""
    out = {}
    for run_id in list_run_ids(agency, collection, qa_results_dir):
        missing = missing_tools(agency, collection, run_id, qa_results_dir)
        if missing:
            out[run_id] = missing
    return out


def read_one(agency: str, collection: str, run_id: str, tool: str,
             qa_results_dir: Path | str = QA_RESULTS_DIR,
             dataset: str | None = None) -> list[dict]:
    """The `verified` list from one committed `<tool>.json` file.

    With `dataset`, reads that one dataset's file. Without it, reads
    EVERY dataset under the collection and concatenates in dataset
    order - which is what a caller asking for "this run's dbt results"
    meant before REQ-PIPE-038 split them, and still means.

    `[]` where nothing was written, which is ordinary rather than an
    error: a tool with no check defined against a dataset writes that
    dataset no file at all.
    """
    if dataset is not None:
        datasets = [dataset]
    else:
        datasets = _datasets_on_disk(agency, collection, qa_results_dir)
    out: list[dict] = []
    for name in datasets:
        path = Path(qa_results_dir) / agency / collection / name / run_id / f"{tool}.json"
        if not path.exists():
            continue
        with open(path) as f:
            out.extend(json.load(f).get("verified") or [])
    return out


def read_raw(agency: str, collection: str, run_id: str, tool: str,
             qa_results_dir: Path | str = QA_RESULTS_DIR) -> dict | None:
    """The whole committed envelope from `_raw/<run_id>/<tool>.json` -
    `raw_output` plus its provenance fields - or None where that
    invocation wrote nothing."""
    path = _raw_dir(agency, collection, qa_results_dir) / run_id / f"{tool}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def list_run_ids(agency: str, collection: str,
                  qa_results_dir: Path | str = QA_RESULTS_DIR) -> list[str]:
    """Every run_id committed under this agency/collection, sorted.

    Listed from `_raw/` since REQ-PIPE-038, because that is the one
    scope every run writes to: a dataset directory is missing a run
    entirely if no tool had anything to say about that table, so a
    listing taken from one dataset would silently lose runs.
    """
    return sorted((p.name for p in _run_dirs(_raw_dir(agency, collection, qa_results_dir))),
                   key=_natural_sort_key)


def read_dataset_stats(agency: str, collection: str, run_id: str,
                        qa_results_dir: Path | str = QA_RESULTS_DIR) -> dict | None:
    """The precomputed value-counts/arrival/check-aggregate/manifest-entry
    data for one run (qa_tools/<bdm|cp>/dataset_stats.py's output),
    committed under the pseudo-tool name "dataset_stats" - not a real
    QA tool, just reusing qa_results_writer.write_qa_result()'s same
    file shape/writer for consistency. Returns None if this run has no
    committed dataset_stats.json (shouldn't happen for any run written
    since Phase 3 - see plans/publishing-and-history.md)."""
    committed = read_raw(agency, collection, run_id, "dataset_stats", qa_results_dir)
    return committed.get("raw_output") if committed else None


def read_run_provenance(agency: str, collection: str, run_id: str,
                         qa_results_dir: Path | str = QA_RESULTS_DIR) -> dict | None:
    """The `run_timestamp`/`run_by` envelope fields for one run - unlike
    read_dataset_stats() above (which returns only the `raw_output`
    payload, the shape every existing caller already expects), this
    reads the two provenance fields write_qa_result() stamps ALONGSIDE
    raw_output, not inside it. Added for qa_tools/common/changelog.py
    (plans/publishing-and-history.md Phase 3's changelog feature,
    2026-09-16) - a separate function rather than reshaping
    read_dataset_stats() itself, since that would break every existing
    caller's assumption that its return value IS the raw_output dict.
    Reads dataset_stats.json specifically since it's the one file
    guaranteed to exist for every run (orchestrate_bdm.py's/
    orchestrate_cp.py's own dataset_stats write is where run_by gets
    stamped - see write_qa_result()'s own docstring). Returns None if
    this run has no committed dataset_stats.json."""
    committed = read_raw(agency, collection, run_id, "dataset_stats", qa_results_dir)
    if committed is None:
        return None
    return {"run_timestamp": committed.get("run_timestamp"), "run_by": committed.get("run_by")}


def read_qa_results(agency: str, collection: str,
                     qa_results_dir: Path | str = QA_RESULTS_DIR) -> list[dict]:
    """Every committed run's every tool's `verified` records for one
    `agency`/`dataset` pair, concatenated in run-id then tool order.
    Only covers the tools that actually write under this exact dataset
    segment - Child Protection's Evidently check writes under its own
    table-scoped dataset id instead of the collection id the other 3
    tools use (see qa_results_writer.py callers' own AGENCY_ID/
    DATASET_ID/COLLECTION_ID constants), so a caller building CP's full
    result set calls this once per dataset segment and concatenates -
    same pattern qa_tools/cp/build_results_from_history.py uses."""
    all_results: list[dict] = []
    for run_id in list_run_ids(agency, collection, qa_results_dir):
        for tool in TOOL_ORDER:
            all_results.extend(read_one(agency, collection, run_id, tool, qa_results_dir))
    return all_results


def canonical_order(results: list[dict]) -> list[dict]:
    """One agreed ordering for a results list, so that a LIVE run and a
    rebuild from committed history produce the same file.

    They stopped agreeing at REQ-PIPE-038 and for a legitimate reason:
    a live Soda scan emits all six Child Protection tables interleaved
    in whatever order its checks ran, while the committed history holds
    them as six per-dataset files a rebuild reads one after another.
    Same records, same counts, different sequence - which would have
    quietly cost this project a real correctness check, since diffing a
    rebuild against a live run is how several behaviour-preserving
    refactors were actually verified.

    A STABLE sort on (run, tool, dataset) rather than a total one: the
    order of checks WITHIN one tool's output for one dataset is the
    tool's own, it carries real meaning, and it is identical down both
    paths already.
    """
    order = {tool: i for i, tool in enumerate(TOOL_ORDER)}
    return sorted(results, key=lambda r: (
        _natural_sort_key(str(r.get("run_id") or "")),
        order.get(_TOOL_OF_CHECK(str(r.get("check_id") or "")), len(order)),
        str(r.get("dataset_id") or ""),
    ))


def read_cross_table_results(agency: str, collection: str,
                              qa_results_dir: Path | str = QA_RESULTS_DIR) -> list[dict]:
    """Every committed cross-table check result for one collection
    (REQ-QAC-037 criterion 1).

    Read from the reserved scope beside the datasets rather than from
    any one of them, which is the whole point: a referential check
    between placements and carers is not cp-placements' result because
    cp-placements is where it happened to be declared.

    Empty where the scope does not exist, which is the ordinary state
    for a collection with no cross-table checks - and for every
    collection until the first run after this landed.
    """
    from qa_tools.common import tables_read as tables_read_mod

    scope_dir = Path(qa_results_dir) / agency / collection / tables_read_mod.CROSS_TABLE_SCOPE
    if not scope_dir.is_dir():
        return []
    out: list[dict] = []
    for run_dir in sorted((d for d in scope_dir.iterdir() if d.is_dir()),
                           key=lambda d: _natural_sort_key(d.name)):
        for tool in TOOL_ORDER:
            path = run_dir / f"{tool}.json"
            if not path.exists():
                continue
            try:
                out.extend(json.loads(path.read_text()).get("verified") or [])
            except (OSError, json.JSONDecodeError):
                continue
    return out
