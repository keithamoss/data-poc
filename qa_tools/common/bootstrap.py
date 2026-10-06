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
              on_step: Callable[[str], None] | None = None,
              checkpoint_before: int | None = None) -> BootstrapResult:
    """Ensure this environment's database has data and QA results.

    `force` runs even when staging already holds tables - but NEVER over
    recorded QA history (REQ-PIPE-144 criterion 38): that is refused,
    with nothing run and nothing deleted, because a re-run would stack
    on top of the history rather than replace it. `--force` NEVER WIPES -
    wiping is `mothman env reset-synthetic`'s alone.
    """
    say = on_step or (lambda _msg: None)

    # A CHECKPOINT IS OF ONE COLLECTION, on a synthetic asset (REQ-TEST-159):
    # both side by side are never both between arrivals at once.
    if checkpoint_before is not None:
        from qa_tools.common import checkpoints
        if collection not in checkpoints.COLLECTIONS:
            return BootstrapResult(populated=False, staged_before=0, staged_after=0,
                                   refused=True,
                                   reason="a checkpoint is taken of one collection at a time - "
                                          "choose --collection bdm or --collection cp")
        try:
            checkpoints.require_synthetic()
        except checkpoints.CheckpointRefused as exc:
            return BootstrapResult(populated=False, staged_before=0, staged_after=0,
                                   refused=True, reason=str(exc))

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
        held = lock.__enter__()
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
                after_each = None
                if checkpoint_before is not None:
                    after_each = _checkpoint_hook(name, checkpoint_before, held, say)
                say(f"Running the real checks against every {_LABEL[name]} supply")
                timings[name] = _run_collection(name, sequential, record_deliveries=True,
                                                after_each=after_each)
        else:
            # SIDE BY SIDE (REQ-TEST-116 criterion 1). The two collections
            # share no dataset, slot or promotion, so neither's order depends
            # on the other's. GENERATION FIRST, both of it - 4.6s measured, not
            # worth overlapping - so neither pipeline recognises a delivery
            # tree the other generator is still writing. Each collection
            # records a delivery at its first arrival (REQ-TEST-159); THE
            # DELIVERIES NEITHER CLAIMED are recorded once both are done.
            for name in names:
                say(f"Generating synthetic data ({_LABEL[name]})")
                generate[name]()
            say("Running the real checks against every supply - "
                + " and ".join(_LABEL[n] for n in names) + " side by side")
            timings = _run_concurrently(names, sequential)
            _record_deliveries()
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


def _run_collection(name: str, sequential: bool, record_deliveries: bool = False,
                    **replay) -> float:
    """Run one collection's whole pipeline; return how long it took.
    `replay` is start_at / after_each / player, for a checkpoint or a resume.

    TOP LEVEL, so a spawned process can import it by name.
    """
    started = time.monotonic()
    if name == "bdm":
        from qa_tools.bdm.orchestrate_bdm import run_pipeline
        run_pipeline(sequential=sequential, record_deliveries=record_deliveries, **replay)
    else:
        from qa_tools.cp.orchestrate_cp import run_pipeline_cp
        run_pipeline_cp(sequential=sequential, record_deliveries=record_deliveries, **replay)
    return time.monotonic() - started


def _checkpoint_hook(name: str, before: int, held, say):
    """The after_each that takes the checkpoint, with `before` snapped back
    to the start of its receipt instant - said aloud when it moves."""
    from qa_tools.common import arrivals, checkpoints

    collection_id = checkpoints.COLLECTIONS[name]
    found = arrivals.arrivals_for(collection_id, "")
    at = checkpoints.snapped(found, before)
    if at != before:
        say(f"Arrival {before} belongs with the arrivals before it (the same delivery or the "
            f"same receipt instant), so the checkpoint is taken before arrival {at}, where "
            f"they begin")
    return checkpoints.taking_checkpoint(
        collection_id, at, held.paused,
        on_taken=lambda cp: say(f"Checkpoint {cp.name} taken before arrival {cp.before}"))


@dataclass(frozen=True)
class ResumeResult:
    """What a resume did. `dsn` is the resume's own database - None when
    nothing was replayed."""

    replayed: bool
    reason: str
    dsn: str | None = None
    first_affected: int | None = None
    refused: bool = False


def resume(name: str, sequential: bool = False,
           on_step: Callable[[str], None] | None = None) -> ResumeResult:
    """REQ-TEST-159 criteria 2 to 4 and 6: copy a checkpoint into a database
    of its own and replay into it arrival N onwards - once REQ-TEST-160 has
    found nothing changed before N. Refusals change nothing."""
    import os

    from qa_tools.common import checkpoints, processing_pass, replay_inputs, scripted_decisions

    say = on_step or (lambda _msg: None)
    try:
        checkpoints.require_synthetic()
        cp = checkpoints.find(name)
    except checkpoints.CheckpointRefused as exc:
        return ResumeResult(replayed=False, refused=True, reason=str(exc))

    say("Regenerating the deliveries to compare them with the checkpoint's")
    first = replay_inputs.first_affected(cp.recorded)
    if first.arrival is None:
        return ResumeResult(replayed=False, reason=first.reason)
    if first.arrival < cp.before:
        instead = ("Start again with a bootstrap from empty" if first.arrival < 2 else
                   f"Take a checkpoint before arrival {first.arrival} or earlier, or start "
                   f"again with a bootstrap from empty")
        return ResumeResult(
            replayed=False, refused=True, first_affected=first.arrival,
            reason=f"{first.reason}, which is before this checkpoint (arrival {cp.before}) - "
                   f"nothing was copied or replayed. {instead}.")

    from cli import bdm, cp as cp_cli

    short = next(k for k, v in checkpoints.COLLECTIONS.items() if v == cp.collection_id)
    say("Generating the synthetic data the replay reads")
    bdm.generate_synthetic_data()
    cp_cli.generate_synthetic_data()
    say(f"Copying {cp.name} into a database of the resume's own")
    dsn = checkpoints.copy_for_resume(cp)

    previous = os.environ.get(supply_db.SUPPLY_DSN_ENV)
    os.environ[supply_db.SUPPLY_DSN_ENV] = dsn
    supply_db.release_connections()
    try:
        with processing_pass.pass_lock("resume"):
            player = scripted_decisions.Player(
                cp.collection_id,
                scripts=[scripted_decisions.Script(**s) for s in cp.pending_scripts])
            say(f"Replaying {_LABEL[short]} from arrival {cp.before}")
            _run_collection(short, sequential, record_deliveries=True,
                            start_at=cp.before, player=player)
        _rebuild_results(short)
    finally:
        supply_db.release_connections()
        if previous is None:
            os.environ.pop(supply_db.SUPPLY_DSN_ENV, None)
        else:
            os.environ[supply_db.SUPPLY_DSN_ENV] = previous
    return ResumeResult(replayed=True, dsn=dsn, first_affected=first.arrival,
                        reason=f"{first.reason}; replayed from arrival {cp.before}")


def _rebuild_results(short: str) -> None:
    """A resume processed only part of the collection, so its results file
    is rebuilt from the whole recorded history rather than left partial."""
    if short == "bdm":
        from qa_tools.bdm.build_results_from_history import build_results_from_history
    else:
        from qa_tools.cp.build_results_from_history import build_results_from_history
    build_results_from_history()


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
