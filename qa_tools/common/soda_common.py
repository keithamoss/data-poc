"""
Tool-generic Soda Core helpers, shared by qa_tools/bdm/run_soda_bdm.py
and qa_tools/cp/run_soda_cp.py. The actual check-to-dashboard-field
mapping (dimension/label per check, custom-name handling) is genuinely
different per dataset and stays in each dataset's own file - see
plans/qa-pipeline.md #84.
"""
from __future__ import annotations

import os

from soda.sampler.sampler import Sampler
from soda.sampler.sample_ref import SampleRef

def _defuse_sodas_dotenv_reload() -> None:
    """Build Soda's EnvHelper now, and put the environment back.

    WHY THIS RUNS AT IMPORT. Soda constructs a singleton `EnvHelper` the
    first time a scan needs it, and that constructor calls
    `dotenv.load_dotenv(override=True)` - it walks up from its own file,
    finds this repo's `.env`, and writes every name in it over whatever
    the process already had. `MOTHMAN_SUPPLY_DSN` is one of those names,
    so the first scan of a run silently moved the warehouse to whatever
    the file said: it discarded an operator's explicit
    `MOTHMAN_SUPPLY_DSN=... mothman pipeline run`, and in the test suite
    it sent every test after a Soda test on the same xdist worker at the
    developer's real database instead of its own isolated one. That is
    how ~14 pytest fixture tables came to be sitting in `supply`.

    IT HAPPENS DURING SCAN CONSTRUCTION, not during `execute()`, which
    is why containing `execute()` alone was not enough - and why this is
    here rather than in `execute_scan()` below. Getting the singleton
    built once, on our terms, means no scan anywhere can do it later: a
    rule that needs no discipline at any future call site.

    PUBLIC NAMES ONLY (`EnvHelper`, `Logs`), and both are singletons
    Soda itself reuses across scans, so this is indistinguishable from
    having run one scan already. It never raises: a Soda release that
    renames or drops this leaves a process that behaves exactly as it
    does today, and
    tests/test_soda_leaves_the_environment_alone.py is what says whether
    the invariant still holds.
    """
    before = dict(os.environ)
    try:
        from soda.common.env_helper import EnvHelper
        from soda.common.logs import Logs

        EnvHelper(Logs())
    except Exception:  # noqa: BLE001 - see the docstring: never fatal
        pass
    finally:
        if os.environ != before:
            os.environ.clear()
            os.environ.update(before)


_defuse_sodas_dotenv_reload()

ENGINE_TAG = "Soda Core 3.5"

# Matches datacontract-cli's own hardcoded _FAILED_SAMPLE_LIMIT (see
# datacontract_common.py) - one consistent cap across every tool's
# failing-row samples, not a per-tool guess. See plans/qa-pipeline.md #15.
FAILING_SAMPLE_LIMIT = 5


class CaptureSampler(Sampler):
    """Soda's own DefaultSampler computes failing-row samples then
    explicitly discards them ("Samples are not sent to Soda Cloud") -
    this captures them instead, keyed by check name, so
    evaluate_soda_bdm/evaluate_soda_cp can pull out just the identifier
    column after scan.execute() (never full row content - see
    plans/qa-pipeline.md #15's "flag it, not full row content" line).

    Triggered two ways: automatically for "failed rows" checks (Soda
    always samples those - confirmed empirically, not just documented),
    and opt-in via `samples limit:` in the checks YAML for ordinary
    metric checks (missing_count/invalid_percent/etc.) - one sampler
    instance handles both uniformly, replacing DefaultSampler either way.
    """

    def __init__(self):
        self.captured: dict[str, list[dict]] = {}

    def store_sample(self, sample_context) -> SampleRef:
        columns = [c.name for c in sample_context.sample.get_schema().columns]
        rows = sample_context.sample.get_rows()
        self.captured[sample_context.check_name] = [dict(zip(columns, row)) for row in rows[:FAILING_SAMPLE_LIMIT]]
        return SampleRef(
            name=sample_context.sample_name,
            schema=sample_context.sample.get_schema(),
            total_row_count=len(rows),
            stored_row_count=0,
            type=SampleRef.TYPE_NOT_PERSISTED,
            message="Captured in-process for the QA dashboard - never sent anywhere external.",
        )


def failing_sample_keys(captured: dict[str, list[dict]], check_name: str, pk_column: str) -> list[str]:
    """Pulls just pk_column's value out of whatever CaptureSampler captured
    for this check - a metric check's sample carries every table column
    (Soda doesn't pre-restrict the way datacontract-cli does), a "failed
    rows" check's sample usually already carries only the identifier
    column its own fail query selected. Either way, only pk_column's
    value ever leaves this function - never other row content."""
    rows = captured.get(check_name, [])
    return [str(row[pk_column]) for row in rows if row.get(pk_column) is not None]


def check_id_from_resource_attributes(check: dict) -> str | None:
    """Pulls `check_id` out of a real Soda scan result's own
    `resourceAttributes` - a list of `{name, value}` pairs Soda copies
    straight from the check's `attributes:` block in the checks YAML
    (confirmed against a real scan, 2026-09-16, not assumed) - one check
    result only ever carries its own attributes, so unlike dbt's schema.
    yml-wide lookup (see check_lifecycle.dbt_check_id_lookup()'s own
    docstring on the collision bug that needed guarding against), there's
    no cross-check ambiguity to resolve here."""
    for attr in check.get("resourceAttributes") or []:
        if attr.get("name") == "check_id":
            return attr.get("value")
    return None


def threshold(spec: dict | None) -> float | None:
    if not spec:
        return None
    for key in ("greaterThan", "greaterThanOrEqual"):
        if key in spec:
            return spec[key]
    # a lower-bound-only spec (row_count's warn/fail also carry a lessThan
    # side) - "upper bound wins for a single scalar" convention, same one
    # the now-removed equivalent engine's _numeric_threshold() used.
    return next(iter(spec.values()), None)


def execute_scan(scan):
    """Run a Soda scan and return its results, leaving nothing behind.

    TWO THINGS SODA DOES NOT CLEAN UP, both found on 2026-09-27 and both
    fixed here rather than at each call site, because a scan that raises
    leaks in exactly the same way and that is the case nobody is
    watching.

    THE CONNECTION - see close_scan_connections() below for the full
    account. Soda's own teardown iterates an empty dict, so every scan
    otherwise leaves a PostgreSQL backend sitting `idle in transaction`.

    THE ENVIRONMENT, which is the worse of the two. Soda builds a
    singleton `EnvHelper` on the first scan in a process, and its
    constructor calls `dotenv.load_dotenv(override=True)`: it walks up
    from its own file, finds this repo's `.env`, and writes every name
    in it over whatever the process already had. `MOTHMAN_SUPPLY_DSN` is
    one of those names, so the first scan of a run silently moved the
    warehouse to whatever the file said - discarding an operator's
    explicit `MOTHMAN_SUPPLY_DSN=... mothman pipeline run`, and, in the
    test suite, sending every test after a Soda test on the same worker
    at the developer's real database instead of its own.

    RESTORING THE WHOLE ENVIRONMENT rather than the one name we know
    about. The defect is not "Soda overwrites the DSN", it is "a library
    reloads a file over our process configuration"; `MOTHMAN_ENVIRONMENT`
    decides where a build publishes and is in the same file. Naming the
    variables here would mean remembering to add the next one.

    NOT A WORKAROUND FOR SOMETHING WE COULD ASK SODA TO STOP DOING -
    there is no configuration for it, and the alternative was
    pre-seeding a name-mangled private singleton so its constructor
    never ran. Containing the effect is both smaller and honest about
    what it is. The guard against Soda changing is
    tests/test_soda_leaves_the_environment_alone.py, which asserts the
    outcome rather than the mechanism.
    """
    before = dict(os.environ)
    try:
        scan.execute()
        return scan.get_scan_results()
    finally:
        close_scan_connections(scan)
        if os.environ != before:
            os.environ.clear()
            os.environ.update(before)


def close_scan_connections(scan) -> int:
    """Close the database connections a finished Soda scan leaves open.
    Returns how many were closed, so a caller or a test can assert on it.

    SODA'S OWN TEARDOWN MISSES THEM, and this is a real leak rather than
    tidiness (2026-09-27). `Scan.execute()` ends with `self._close()`,
    which calls `DataSourceManager.close_all_connections()`, which
    iterates `manager.connections` - and on this code path that dict is
    EMPTY. The live connection is held on the data source itself,
    `manager.data_sources[name].connection`, so the loop closes nothing
    and every scan leaves one PostgreSQL backend open. Verified directly:
    a single scan against a real server takes the count of unlabelled
    backends from 0 to 1, and it survives `del scan` and `gc.collect()`.

    WHAT THAT LEAK ACTUALLY BROKE, because "a spare connection" sounds
    harmless. Soda's connection is not autocommit, so the leaked backend
    sits `idle in transaction` holding ACCESS SHARE on every table the
    scan read. `DROP SCHEMA ... CASCADE` needs ACCESS EXCLUSIVE, so the
    orchestrator's own tidy-up of a run's view schema queued behind it -
    for thirty seconds, and then failed with a lock timeout. A pipeline
    run over ~40 arrivals accumulated ~40 such backends. Under the
    retired DuckDB engine none of this was visible: the tools shared one
    in-process file and the per-run database was discarded whole.

    WHY REACHING INTO `_data_source_manager` IS THE RIGHT FIX HERE
    rather than a workaround. The connection exists because we asked
    Soda to open it, so closing it is ours to do; the public API for
    that is `_close()` and it demonstrably does not work. The guard
    against Soda changing its internals is not defensive code here - it
    is tests/test_soda_leaves_no_connection.py, which asserts the
    OUTCOME (a completed scan leaves no open backend) rather than the
    mechanism. If a future Soda release fixes this or moves it, that
    test still says whether the invariant holds.
    """
    manager = getattr(scan, "_data_source_manager", None)
    closed = 0
    for data_source in getattr(manager, "data_sources", {}).values():
        connection = getattr(data_source, "connection", None)
        if connection is None or getattr(connection, "closed", False):
            continue
        try:
            connection.close()
            closed += 1
        except Exception:
            # A connection we cannot close is not worth failing a scan
            # whose results are already in hand - the backend will go
            # when the process does, and the test above is what notices
            # if this starts happening.
            pass
    return closed


def readable_checks_yaml(path: str, unreadable) -> str:
    """The SodaCL file at `path`, less every check this run cannot read.

    THE SODA HALF OF dbt_common.exclude_unreadable(), and the same
    latent defect one tool over (found 2026-10-02). A run's view schema
    can lack a table - held, contested with nothing promoted, or filed
    to another period, which REQ-PIPE-105 makes ordinary: one file is
    one arrival, and Case Workers' April file is not its siblings'
    period's to read. Handed checks over a relation that does not exist,
    Soda errors them, and the scan's caller fails the whole run - every
    readable table losing its QA for one that was never there.

    TWO THINGS GO: a `checks for <table>` section whose table is
    unreadable, and any check elsewhere whose `check_id` DECLARES that
    it reads one (a reference check, a cross-table failed-rows query).
    The declaration is the same one the promotion gate and the results
    writer use, so the three cannot disagree about what a check reads.
    Nothing is recorded for a check left out: it was not run, which is
    different from failing.
    """
    import yaml

    from qa_tools.common.qa_results_writer import _declared_reads_tables

    gone = set(unreadable)
    with open(path) as f:
        text = f.read()
    if not gone:
        # VERBATIM in the ordinary case, so a run that can read every
        # table is handed exactly the authored file and no round-trip.
        return text
    out, _ = _split(yaml.safe_load(text), gone, _declared_reads_tables())
    return yaml.safe_dump(out, sort_keys=False)


def left_out_checks(path: str, unreadable) -> list[str]:
    """The check ids readable_checks_yaml() leaves out, so the run can
    reconcile them against what it recorded as not evaluated
    (REQ-PIPE-115 criterion 17)."""
    import yaml

    from qa_tools.common.qa_results_writer import _declared_reads_tables

    gone = set(unreadable)
    if not gone:
        return []
    with open(path) as f:
        doc = yaml.safe_load(f)
    _, removed = _split(doc, gone, _declared_reads_tables())
    return removed


def _check_id_of(item) -> str | None:
    if isinstance(item, dict) and len(item) == 1:
        body = next(iter(item.values()))
        if isinstance(body, dict):
            return (body.get("attributes") or {}).get("check_id")
    return None


def _split(doc: dict, gone: set, declared: dict) -> tuple[dict, list[str]]:
    """(the document less every unreadable check, the ids taken out)."""
    out, removed = {}, []
    for key, checks in doc.items():
        if key.startswith("checks for ") and key[len("checks for "):].strip() in gone:
            if isinstance(checks, list):
                removed.extend(c for c in map(_check_id_of, checks) if c)
            continue
        if isinstance(checks, list):
            kept = []
            for item in checks:
                check_id = _check_id_of(item)
                if check_id and gone & set(declared.get(check_id, ())):
                    removed.append(check_id)
                    continue
                kept.append(item)
            checks = kept
        out[key] = checks
    return out, removed
