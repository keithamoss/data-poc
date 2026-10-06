"""Take an empty environment to one with data in it, idempotently.

WHY THIS EXISTS (Keith, 2026-09-27): "when we start a new Claude code
session, or indeed when a human checks out the repository and starts a
new dev container or uses it locally, we have a way to generate the
synth data and run a command to populate the warehouse with something
with QA checks - the stuff we're doing now through tests, but doing it
at startup or when a human chooses to run a command, via the TUI."

Before this, the only thing that put rows in a fresh database was the
TEST SUITE, as a side effect of its fixtures. That is backwards: the
tests should exercise the same path a person uses, not BE the path. A
new contributor who ran the dashboard before running pytest got an
empty warehouse and nothing to explain why.

ONE IMPLEMENTATION, THREE CALLERS, which is the whole point of it
living here rather than in cli/:
  - a person, via `mothman pipeline bootstrap` or the TUI's own menu;
  - a session or dev container starting up, via a hook;
  - CI, which under Keith's 2026-09-27 rule gets its own database spun
    up and populated for that run alone, because GitHub Actions is
    never allowed to reach a real one.
Three callers of one function cannot drift; three copies of the steps
would, and the CI copy is the one nobody would notice had.

IDEMPOTENT BY DEFAULT, because a startup hook that rebuilds the world
every time is a hook people disable. `already_populated()` asks the
database rather than a marker file - a marker can survive a database
that was dropped, and then the one command whose job is to guarantee
data would be the one confidently doing nothing.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from qa_tools.common import supply_db


@dataclass(frozen=True)
class BootstrapResult:
    """What bootstrap actually did, so a caller can say so rather than
    printing a hopeful message."""
    #: True when it ran the pipeline; False when it found data and stopped.
    populated: bool
    #: Staged tables found before it started.
    staged_before: int
    #: Staged tables present after.
    staged_after: int
    #: Why it did nothing, for the skip case.
    reason: str = ""
    #: Seconds per collection checked, and "total" (REQ-TEST-116
    #: criterion 6) - measured, so a speed-up is a number, not a feeling.
    timings: dict[str, float] = field(default_factory=dict)
    #: True where it REFUSED rather than found nothing to do - a database
    #: already holding QA history (REQ-PIPE-144 criterion 38).
    refused: bool = False


#: Why a re-run over recorded history is refused (REQ-PIPE-144 criteria
#: 38 and 39) - one message for both commands, sited beside each other.
#: Filings are write-once and the decision log append-only, so a re-run
#: ADDS to the history rather than replacing it: on 2026-10-02 a forced
#: bootstrap stacked on top of the last one and promoted 11 supplies
#: where a clean run promotes dozens, while its help text promised the
#: same content.
HISTORY_REFUSAL = (
    "this database already holds QA history. A re-run would ADD to it rather "
    "than replace it - filings are write-once and the decision log is "
    "append-only - so nothing was run and nothing was deleted. To start from "
    "empty, run `mothman env reset-synthetic` first.")

#: The tables whose rows ARE the recorded history.
_HISTORY_TABLES = ("run", "delivery", "filing", "decision")


def holds_history(conn) -> bool:
    """Whether this database already holds any recorded QA history.

    Asked of the database, like already_populated(), and true of a qa
    schema from ANY version - an older one is history too, and is refused
    by ensure_schema with the same remedy.
    """
    from qa_tools.common import qa_store

    for table in _HISTORY_TABLES:
        if not conn.execute(
                f"SELECT to_regclass('{qa_store.SCHEMA}.{table}')").fetchall()[0][0]:
            continue
        if conn.execute(
                f'SELECT EXISTS (SELECT 1 FROM "{qa_store.SCHEMA}".{table})').fetchall()[0][0]:
            return True
    return False


def staged_table_count(conn) -> int:
    """How many tables the staging schema holds.

    The honest measure of "is there anything here". Asked of the
    database itself rather than of a file, so a dropped or recreated
    database reads as empty the moment it is.
    """
    return conn.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = ?",
        [supply_db.STAGING_SCHEMA]).fetchone()[0]


def already_populated(conn) -> bool:
    return staged_table_count(conn) > 0


def bootstrap(collection: str = "all", force: bool = False,
              sequential: bool = False,
              on_step: Callable[[str], None] | None = None) -> BootstrapResult:
    """Ensure this environment's database has data and QA results.

    `force` runs even when staging already holds tables - but NEVER over
    recorded QA history (REQ-PIPE-144 criterion 38): that is refused,
    with nothing run and nothing deleted, because a re-run would stack
    on top of the history rather than replace it. `--force` NEVER WIPES -
    wiping is `mothman env reset-synthetic`'s alone.
    """
    say = on_step or (lambda _msg: None)

    say("Checking what this environment already holds")
    with supply_db.connect(label="mothman:bootstrap") as conn:
        supply_db.ensure_schemas(conn)
        before = staged_table_count(conn)
        history = holds_history(conn)

    if before and not force:
        return BootstrapResult(
            populated=False, staged_before=before, staged_after=before,
            reason=f"{before} staged table(s) already present - nothing to do "
                   f"(--force runs anyway, though never over recorded QA history: "
                   f"`mothman env reset-synthetic` starts from empty)")
    if history:
        return BootstrapResult(populated=False, staged_before=before,
                               staged_after=before, refused=True,
                               reason=HISTORY_REFUSAL[0].upper() + HISTORY_REFUSAL[1:])

    # THE PASS LOCK (REQ-PIPE-151 criterion 16): a bootstrap and a
    # processing pass against one database would each process the same
    # arrivals. Refused at once, naming the holder, with nothing changed.
    from qa_tools.common import processing_pass

    try:
        lock = processing_pass.pass_lock("bootstrap")
        lock.__enter__()
    except processing_pass.PassLockHeld as exc:
        return BootstrapResult(populated=False, staged_before=before,
                               staged_after=before, refused=True, reason=str(exc))
    try:
        # IMPORTED HERE, NOT AT MODULE LEVEL. cli/ imports this module, and
        # the orchestrators pull in all four QA tools - several seconds of
        # import time that a caller only checking `already_populated()`
        # should not pay.
        from cli import bdm, cp

        started = time.monotonic()
        names = [n for n in ("bdm", "cp") if collection in ("all", n)]
        generate = {"bdm": bdm.generate_synthetic_data, "cp": cp.generate_synthetic_data}

        if sequential or len(names) < 2:
            # ONE AFTER THE OTHER - the reference REQ-TEST-116 criterion 4
            # compares a parallel bootstrap against, and what a single
            # collection always was.
            timings = {}
            for name in names:
                say(f"Generating synthetic data ({_LABEL[name]})")
                generate[name]()
                say(f"Running the real checks against every {_LABEL[name]} supply")
                timings[name] = _run_collection(name, sequential, record_deliveries=True)
        else:
            # SIDE BY SIDE (REQ-TEST-116 criterion 1). The two collections
            # share no dataset, slot or promotion, so neither's order depends
            # on the other's. GENERATION FIRST, both of it - 4.6s measured, not
            # worth overlapping - so neither pipeline recognises a delivery
            # tree the other generator is still writing. THEN THE DELIVERY LOG,
            # once, for the reason run_pipeline's own comment gives.
            for name in names:
                say(f"Generating synthetic data ({_LABEL[name]})")
                generate[name]()
            _record_deliveries()
            say("Running the real checks against every supply - "
                + " and ".join(_LABEL[n] for n in names) + " side by side")
            timings = _run_concurrently(names, sequential)
        timings["total"] = time.monotonic() - started
        say("Took " + ", ".join(f"{_LABEL.get(k, k)} {v:.0f}s" for k, v in timings.items()))
    finally:
        lock.__exit__(None, None, None)

    with supply_db.connect(label="mothman:bootstrap") as conn:
        after = staged_table_count(conn)
    return BootstrapResult(populated=True, staged_before=before, staged_after=after,
                           timings=timings)


_LABEL = {"bdm": "Birth Registrations", "cp": "Child Protection", "total": "in total"}


def _record_deliveries() -> None:
    from qa_tools.common import delivery_log, replay_clock

    # Each delivery stamped as received, on a synthetic asset (REQ-PIPE-081
    # criteria 27-31) - the replay's first records.
    with replay_clock.replaying():
        delivery_log.record_all()


def _run_collection(name: str, sequential: bool, record_deliveries: bool = False) -> float:
    """Run one collection's whole pipeline; return how long it took.

    TOP LEVEL, so a spawned process can import it by name.
    """
    started = time.monotonic()
    if name == "bdm":
        from qa_tools.bdm.orchestrate_bdm import run_pipeline
        run_pipeline(sequential=sequential, record_deliveries=record_deliveries)
    else:
        from qa_tools.cp.orchestrate_cp import run_pipeline_cp
        run_pipeline_cp(sequential=sequential, record_deliveries=record_deliveries)
    return time.monotonic() - started


def _run_concurrently(names: list[str], sequential: bool) -> dict[str, float]:
    """Each collection in a process of its own.

    PROCESSES, NOT THREADS. The four QA tools run in-process and keep
    process-wide state - Soda Core reloads `.env` into os.environ on its
    first scan (plans/tooling.md #26), and dbt and datacontract-cli were
    never written to share an interpreter. A process each is the
    isolation the two pipelines already had when run one after the
    other. SPAWNED rather than forked, so neither inherits the other's
    half-initialised connections or imported tool state.

    A failure in either fails the bootstrap: `.result()` re-raises it.
    """
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=len(names), mp_context=context) as pool:
        futures = {n: pool.submit(_run_collection, n, sequential) for n in names}
        return {n: f.result() for n, f in futures.items()}
