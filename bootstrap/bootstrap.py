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
from datetime import date
from typing import Callable

import psycopg

from bootstrap import generation
from generator import public as generator
from asset_model import history_anchor
from qa_tools.common import qa_store, supply_db
from qa_tools.common.streams import (  # noqa: F401 - the bootstrap's names for them
    HISTORY_REFUSAL,
    StreamRefused,
    holds_history,
    streams,
)


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
    #: The checkpoint taken, if one was asked for - repeated in the closing
    #: summary so it is not lost in the run's output (#133 B6).
    checkpoint: str | None = None
    #: Every targeted supply whose recorded verdict differed from what it
    #: was built to (REQ-GEN-186 criterion 3). Non-empty fails the
    #: bootstrap, though nothing it recorded is changed (criterion 6).
    disagreements: tuple[str, ...] = ()
    #: The whole bootstrap's wall clock, generation to target agreement
    #: (REQ-PIPE-250 criterion 3) - what the budget line is measured on.
    wall_seconds: float = 0.0
    #: The digest of the configuration pinned for the run (REQ-GEN-399
    #: criterion 4), printed as 'Configuration pinned: <first 12>'.
    pin_digest: str | None = None
    #: Each started process that ran under a different pin, and which files
    #: differed (REQ-GEN-399 criterion 3). Non-empty fails the bootstrap.
    pin_differences: tuple[str, ...] = ()
    #: Each collection whose delivery tree changed mid-replay, with its
    #: folders (REQ-PIPE-430 criterion 3). Non-empty fails the bootstrap.
    tree_changes: tuple[str, ...] = ()
    #: (the date the history was generated up to, how it was chosen) - the
    #: closing line's 'generated up to' (REQ-GEN-399 criterion 4).
    generated_up_to: tuple | None = None


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


#: REQ-PIPE-250 (Keith, 2026-10-15): "a hard 12 minutes" from empty on this
#: sandbox - an acceptance measurement and a printed line, never a CI gate
#: (Keith, 2026-10-18), because a runner's timing varies by runner.
BUDGET_SECONDS = 12 * 60


#: How budget_line begins, so a screen can tell it from a step (cli/app.py).
OVER_BUDGET, WITHIN_BUDGET = "OVER BUDGET", "Within budget"


def budget_line(seconds: float) -> str:
    """The wall clock against the 12-minute budget, plainly over or within
    (REQ-PIPE-250 criterion 3)."""
    took = f"{seconds:.0f}s of wall clock against the 12-minute budget ({BUDGET_SECONDS}s)"
    if seconds > BUDGET_SECONDS:
        return (f"{OVER_BUDGET}: this bootstrap took {took} - "
                f"{seconds - BUDGET_SECONDS:.0f}s over.")
    return f"{WITHIN_BUDGET}: this bootstrap took {took}."


def bootstrap(collection: str = "all", force: bool = False,
              sequential: bool = False,
              on_step: Callable[[str], None] | None = None,
              checkpoint_before: int | None = None,
              skip_target_trial: bool = False,
              try_targets: Callable[[str], object] | None = None,
              anchor: str | date | None = None,
              roll_anchor: bool = False) -> BootstrapResult:
    """Ensure this environment's database has data and QA results.

    THE ANCHOR (REQ-GEN-404, REQ-GEN-405): the fixed test anchor unless
    `anchor` names another date or `roll_anchor` rolls to today on the asset's
    clock - both refused under test and CI, and refused over a database that
    already holds a history. Installed for the whole run, handed to every
    process it starts, and recorded in the qa schema.

    `force` runs even when staging already holds tables - but NEVER over
    recorded QA history (REQ-PIPE-144 criterion 38): that is refused,
    with nothing run and nothing deleted, because a re-run would stack
    on top of the history rather than replace it. `--force` NEVER WIPES -
    wiping is `mothman env reset-synthetic`'s alone.

    SYNTHETIC ONLY (REQ-GEN-381 criterion 2; Q5 SETTLED by Keith 2026-11-02):
    an asset that does not declare `synthetic: true` is refused before
    anything is generated - a real asset's first run is `mothman pipeline run`.

    `try_targets(collection_id)` runs a collection's target trial - the
    command's, handed in by cli/, which this package may not import.
    """
    # AN ANCHOR INSTALLED BEFORE THE FIRST CONFIGURATION READ (REQ-GEN-404
    # criterion 12, REQ-GEN-406 criterion 3): a synthetic asset's offset dates
    # resolve against it, and with no anchor file a sandbox could not read its
    # own configuration. The date asked for - or the fixed test anchor - until
    # the run's own anchor is settled below; the retired variable refused first.
    try:
        generator.refuse_the_retired_variable()
    except generator.AnchorRefused as exc:
        return BootstrapResult(populated=False, staged_before=0, staged_after=0,
                               refused=True, reason=str(exc))
    with history_anchor.anchored(_provisional(anchor)):
        return _bootstrap(collection, force, sequential, on_step, checkpoint_before,
                          skip_target_trial, try_targets, anchor, roll_anchor)


def _provisional(anchor) -> date:
    """The date `--anchor` names, if it is one, else the fixed test anchor -
    what configuration reads resolve against until the anchor is validated."""
    if isinstance(anchor, date):
        return anchor
    try:
        return date.fromisoformat(str(anchor).strip()) if anchor is not None \
            else history_anchor.FIXED_TEST_ANCHOR
    except ValueError:
        return history_anchor.FIXED_TEST_ANCHOR


def _bootstrap(collection, force, sequential, on_step, checkpoint_before,
               skip_target_trial, try_targets, anchor, roll_anchor) -> BootstrapResult:
    say = on_step or (lambda _msg: None)
    wall_started = time.monotonic()

    refused = not_synthetic()
    if refused:
        return BootstrapResult(populated=False, staged_before=0, staged_after=0,
                               refused=True, reason=refused)
    from bootstrap import anchoring

    try:
        anchoring.requested(anchor, roll_anchor)
        dated = anchoring.chosen_without_roll(anchor)
    except generator.AnchorRefused as exc:
        return BootstrapResult(populated=False, staged_before=0, staged_after=0,
                               refused=True, reason=str(exc))
    if roll_anchor and checkpoint_before is not None:
        # PROVISIONAL (2026-11-16): a checkpoint is a test-development tool and
        # a roll is a demo regeneration; the arrival numbers a checkpoint is
        # checked against would be worked out before the roll's date is known.
        return BootstrapResult(populated=False, staged_before=0, staged_after=0,
                               refused=True,
                               reason="--checkpoint-before is not taken with --roll-anchor - "
                                      "take checkpoints on a bootstrap at the fixed test "
                                      "anchor, or with --anchor <date>")

    # A CHECKPOINT IS OF ONE COLLECTION, on a synthetic asset (REQ-TEST-159):
    # both side by side are never both between arrivals at once.
    if checkpoint_before is not None:
        from bootstrap import checkpoints
        if collection not in _shorts():
            return BootstrapResult(populated=False, staged_before=0, staged_after=0,
                                   refused=True,
                                   reason="a checkpoint is taken of one collection at a time - "
                                          "choose " + " or ".join(
                                              f"--collection {s}" for s in _shorts()))
        reads = reads_others(collection)
        if reads:
            return BootstrapResult(populated=False, staged_before=0, staged_after=0,
                                   refused=True, reason=reads)
        try:
            checkpoints.require_synthetic()
            # THE NAMES FIT, CHECKED FIRST (post-build-review #346): a name past
            # PostgreSQL's limit would otherwise be refused at the copy, after
            # the replay up to arrival N-1.
            checkpoints.require_names_fit(collection, checkpoint_before)
            # N IS CHECKED BEFORE ANYTHING IS TOUCHED (post-build-review #133
            # B3): against a regeneration somewhere of its own, so a refusal
            # never follows a rewritten data/ tree.
            say("Checking where the checkpoint can be taken")
            # AT THE ANCHOR THIS BOOTSTRAP GENERATES AT (REQ-GEN-404 criterion 6).
            with history_anchor.anchored(dated.anchor):
                found = checkpoints.arrivals_of(_collection(collection).id)
            checkpoints.snapped(found, checkpoint_before)
        except checkpoints.CheckpointRefused as exc:
            return BootstrapResult(populated=False, staged_before=0, staged_after=0,
                                   refused=True, reason=str(exc))

    # EVERY COLLECTION TO BE RUN HAS AN ADAPTER, OR NOTHING RUNS (REQ-PIPE-240
    # criterion 6): refused by name before anything is generated, rather than
    # part-way through, after the collections before it.
    from qa_tools import collections as _collections

    chosen = with_what_it_reads([n for n in _shorts() if collection in ("all", n)], say)
    for name in chosen:
        try:
            _adapter(name)
        except _collections.NoAdapterError as exc:
            return BootstrapResult(populated=False, staged_before=0, staged_after=0,
                                   refused=True, reason=str(exc))

    # THE STREAMS, OR NOTHING RUNS (REQ-PIPE-262 criterion 9): a collection
    # whose calendar cannot be resolved is refused before anything is
    # generated, naming the collection and the dataset.
    try:
        groups = streams(chosen)
    except StreamRefused as exc:
        return BootstrapResult(populated=False, staged_before=0, staged_after=0,
                               refused=True, reason=str(exc))

    say("Checking what this environment already holds")
    with supply_db.connect(label="mothman:bootstrap") as conn:
        supply_db.ensure_schemas(conn)
        before = staged_table_count(conn)
        history = holds_history(conn)
        recorded_anchor = qa_store.history_anchor(conn)

    if (roll_anchor or anchor is not None) and (before or history):
        # A DATE ASKED OF A POPULATED DATABASE IS REFUSED (REQ-GEN-405
        # criterion 6; CLI finding 2), naming what is there and what replaces it.
        flag = "--roll-anchor" if roll_anchor else f"--anchor {anchor}"
        there = recorded_anchor.isoformat() if recorded_anchor else "not recorded"
        return BootstrapResult(
            populated=False, staged_before=before, staged_after=before, refused=True,
            reason=f"{flag} was given, and this database already holds a history (anchor: "
                   f"{there}) - nothing was generated. To replace it, run `mothman env "
                   f"reset-synthetic`, then `mothman pipeline bootstrap {flag}` again")

    if checkpoint_before is not None and before:
        # ASKED FOR A CHECKPOINT AND GOT NONE is a refusal, not "nothing to
        # do" (#133 B5): a checkpoint is taken during a bootstrap from empty.
        return BootstrapResult(
            populated=False, staged_before=before, staged_after=before, refused=True,
            reason=f"this database already holds {before} staged table(s), and a checkpoint "
                   "is taken during a bootstrap from an empty database - nothing was run. "
                   "Create an empty database, point MOTHMAN_SUPPLY_DSN at it, run `mothman "
                   "env mark` (it asks you to type <data asset>/<environment>), then run "
                   "this bootstrap again")

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

    if roll_anchor:
        # THE ROLL, SAID BEFORE THE LONG PART (REQ-GEN-405 criteria 3 and 5; CLI
        # finding 7): after the populated check, before generation.
        say("Working out the date to roll to")
        try:
            dated = anchoring.roll()
        except generator.AnchorRefused as exc:
            return BootstrapResult(populated=False, staged_before=before,
                                   staged_after=before, refused=True, reason=str(exc))
        say(dated.said)

    # THE PASS LOCK (REQ-PIPE-151 criterion 16): a bootstrap and a
    # processing pass against one database would each process the same
    # arrivals. Refused at once, naming the holder, with nothing changed.
    from qa_tools.common import processing_pass

    taken: list[str] = []
    try:
        lock = processing_pass.pass_lock("bootstrap")
        held = lock.__enter__()
    except processing_pass.PassLockHeld as exc:
        return BootstrapResult(populated=False, staged_before=before,
                               staged_after=before, refused=True, reason=str(exc))
    # THE ASSET'S CONFIGURATION PINNED FOR THE WHOLE RUN (REQ-GEN-398 criterion
    # 2, REQ-GEN-399 criteria 1 and 6): installed here, by the bootstrap's own
    # call, as it installs the replay clock - before the first collection is
    # generated, around the replay, and through the confirmations and the
    # target agreement after it - and released only when the bootstrap
    # returns. Every process it starts is handed this snapshot
    # (assets.handoff), never a fresh read. PROVISIONAL (2026-11-16): one pin
    # spans generation and replay, so the replay reads exactly the
    # configuration the history was generated from.
    # ONE STACK, SO NOTHING IS LEFT HELD (post-build-review #396): a pin that
    # cannot be installed still lets go of the pass lock - in the TUI's
    # long-lived process it would otherwise be held until the process exits.
    # _populate lets go of the lock itself once the replay is done; a second
    # exit of a finished lock is a no-op.
    from contextlib import ExitStack

    from asset_model import config_pin

    with ExitStack() as stack:
        stack.callback(lock.__exit__, None, None, None)
        # THE ANCHOR INSTALLED FOR THE WHOLE RUN (REQ-GEN-404 criterion 10),
        # handed to every process it starts with the pin (assets.handoff).
        stack.enter_context(history_anchor.anchored(dated.anchor))
        snapshot = stack.enter_context(config_pin.pinned())
        return _populate(dated=dated, names=chosen, groups=groups, collection=collection,
                         sequential=sequential, say=say, held=held, lock=lock,
                         taken=taken, before=before, checkpoint_before=checkpoint_before,
                         skip_target_trial=skip_target_trial, try_targets=try_targets,
                         snapshot=snapshot, wall_started=wall_started)


def _populate(*, dated, names, groups, collection, sequential, say, held, lock, taken, before,
              checkpoint_before, skip_target_trial, try_targets, snapshot,
              wall_started) -> BootstrapResult:
    """The bootstrap's work once it holds the pass lock and the pin."""
    differences: tuple[str, ...] = ()
    tree = _Trees()
    # THE ANCHOR RECORDED IN THE QA SCHEMA, ONCE PER HISTORY (REQ-GEN-404
    # criterion 4), before the first run - so a checkpoint copied mid-replay
    # carries it, and a resume regenerates at it (criterion 6).
    with supply_db.connect(label="mothman:bootstrap") as conn:
        qa_store.record_history_anchor(conn, dated.anchor)
    try:
        # THE COLLECTIONS COME FROM THE REGISTRY (REQ-PIPE-240), each run
        # through its adapter - imported lazily, because the orchestrators
        # pull in all four QA tools, several seconds of import time that a
        # caller only checking `already_populated()` should not pay.
        started = time.monotonic()
        generating = 0.0

        trialling = 0.0

        def timed_trial(collection_id: str):
            # THE TARGET TRIALS' OWN TIME (REQ-PIPE-403 criterion 1): inside
            # generation's, and reported beside it as 'of it target trials'.
            nonlocal trialling
            began = time.monotonic()
            try:
                return try_targets(collection_id)
            finally:
                trialling += time.monotonic() - began

        trying = timed_trial if try_targets is not None else None

        def generate(name: str) -> None:
            nonlocal generating
            say(f"Generating synthetic data ({_label(name)})")
            began = time.monotonic()
            _generate(name, trial=not skip_target_trial, try_targets=trying, say=say)
            generating += time.monotonic() - began

        if checkpoint_before is not None or len(names) < 2:
            # ONE COLLECTION - what a checkpoint, and a one-collection
            # bootstrap, always replay (REQ-PIPE-262's Q1: left as is, Keith,
            # 2026-10-19; plans/running-thoughts.md #111).
            timings = {}
            for name in names:
                # EACH COLLECTION'S TREE SNAPSHOT AFTER ITS OWN GENERATION, and
                # released before the next one's (REQ-PIPE-430 criterion 2).
                tree.release()
                generate(name)
                tree.install([_collection(name).id])
                after_each = None
                if checkpoint_before is not None:
                    after_each = _checkpoint_hook(name, checkpoint_before, held, say,
                                                  taken.append)
                say(f"Running the real checks against every {_label(name)} supply")
                timings[name] = _run_collection(name, sequential, record_deliveries=True,
                                                after_each=after_each)
        else:
            # BY STREAM (REQ-PIPE-262): collections sharing a calendar are one
            # receipt-ordered stream, as the live pass is, so who opens a
            # period never depends on which process ran ahead.
            # GENERATION FIRST, all of it, so no pipeline recognises a delivery
            # tree a generator is still writing. NOT CHEAP ANY MORE (REQ-GEN-298
            # NFR 4, correcting the old '4.6s measured'): the whole history took
            # 416s to generate on this sandbox before the geocoding trials
            # (2026-11-01), and those trials run the real tools over about 50
            # supplies before anything is kept, on the quarterly bootstrap's
            # critical path - their wall clock is the 'Took' line's generation
            # entry (REQ-GEN-398 criterion 3).
            for name in names:
                generate(name)
            # THE TREE SNAPSHOT ONCE GENERATION IS DONE, NEVER DURING IT
            # (REQ-PIPE-430 criterion 1, REQ-GEN-398 criterion 4): every
            # collection replayed recognised once, here, and handed to each
            # stream process with the configuration pin.
            tree.install([_collection(n).id for n in names])
            keys = [_stream_key(g) for g in groups]
            if sequential:
                # ONE STREAM AFTER ANOTHER (criterion 7): --sequential changes
                # concurrency only, never which collection reaches a period first.
                timings = {}
                for key in keys:
                    say(f"Running the real checks against every {_label(key)} supply")
                    timings[key] = _run_stream(key, sequential)
            else:
                # SIDE BY SIDE, A PROCESS PER STREAM (criterion 6), each
                # reporting the pin it ran under (REQ-GEN-399 criterion 3).
                say("Running the real checks against every supply - "
                    + " beside ".join(_label(k) for k in keys))
                timings, reports = _run_concurrently(keys, sequential)
                differences = pin_differences(snapshot, reports)
            # THE DELIVERIES NO STREAM CLAIMED, once all are done.
            _record_deliveries()
        if collection == "all":
            # EACH DUE CORRECTION CONFIRMED ONCE BOTH COLLECTIONS ARE REPLAYED
            # (Keith, 2026-10-11, (n)): asset-wide, so after both - and only
            # then, as a one-collection bootstrap has not replayed the other's
            # supplies a correction can move (PROVISIONAL).
            began = time.monotonic()
            _confirm_corrections(say)
            confirming = time.monotonic() - began
        else:
            confirming = None
        tree.release()
        # GENERATION IS AN ENTRY OF THE ONE 'Took' LINE (REQ-GEN-398 criterion
        # 3; CLI finding 4), first, as it ran first - and the target trials
        # beside it, the confirmations after the streams (REQ-PIPE-403
        # criterion 1), so every stage it measures is on the line.
        trials = ({TRIALS: trialling}
                  if try_targets is not None and not skip_target_trial else {})
        confirmations = {CONFIRMATIONS: confirming} if confirming is not None else {}
        timings = {GENERATION: generating, **trials, **timings, **confirmations,
                   "total": time.monotonic() - started}
        say(took_line(timings))
    finally:
        tree.release(check=False)
        lock.__exit__(None, None, None)

    say("Comparing every targeted supply's recorded verdict with what it was built to")
    disagreements = targets_agree(names)
    with supply_db.connect(label="mothman:bootstrap") as conn:
        after = staged_table_count(conn)
    wall = time.monotonic() - wall_started
    say(budget_line(wall))
    return BootstrapResult(populated=True, staged_before=before, staged_after=after,
                           timings=timings, checkpoint=taken[0] if taken else None,
                           disagreements=disagreements, wall_seconds=wall,
                           pin_digest=snapshot.digest, pin_differences=differences,
                           tree_changes=tuple(tree.changes),
                           generated_up_to=generated_up_to(dated))


class _Trees:
    """The bootstrap's delivery-tree snapshot (REQ-PIPE-430): installed after
    a generation, released before the next one or once the replay is done,
    each release checking the tree against the digest taken at install."""

    def __init__(self):
        self.held = None
        self.changes: list[str] = []

    def install(self, collection_ids) -> None:
        from asset_model import arrivals

        self.held = arrivals.TreeSnapshot(collection_ids).install()

    def release(self, *, check: bool = True) -> None:
        if self.held is None:
            return
        held, self.held = self.held, None
        changed = held.release(check=check)
        self.changes += [tree_change(held, cid) for cid in changed]


def tree_change(held, collection_id: str) -> str:
    """One collection whose delivery tree changed mid-replay, named with its
    folders (REQ-PIPE-430 criterion 3)."""
    return (f"{_label(_collection_short(collection_id))}: {_shown(str(held.deliveries_dir))} "
            f"and {_shown(str(held.receipts_dir))}")


def tree_changed_message(changes) -> str | None:
    """The one wording every bootstrap caller gives when a delivery tree
    changed while the replay read it from its snapshot (REQ-PIPE-430
    criterion 3; CLI finding 10) - the CLI and the TUI alike."""
    if not changes:
        return None
    return ("The delivery tree changed while this bootstrap was replaying it:\n"
            + "\n".join(f"  - {c}" for c in changes)
            + "\nThe replay read every arrival from the tree as it stood once generation "
              "finished, so what changed was not replayed. The likely cause is a hand "
              "filing, or a generation run in another terminal, during the run. The "
              "history it recorded is kept but is not to be trusted - replace it with "
              "`mothman env reset-synthetic` then `mothman pipeline bootstrap`.")


#: The 'Took' line's entry for generation (REQ-GEN-398 criterion 3).
GENERATION = "generation"


@dataclass(frozen=True)
class Measured:
    """A from-empty bootstrap's measured wall clock on the development
    sandbox (REQ-PIPE-403 criterion 6), as recorded with the measurement."""

    seconds: float
    on: date
    commit: str


#: Each asset's measured bootstrap, beside its other synthetic-only
#: configuration (REQ-GEN-370): read by the bootstrap and nothing else.
MEASURED_FILE = "bootstrap.yaml"


def measured_bootstrap() -> Measured | None:
    """The selected asset's measured from-empty bootstrap, or None where
    none is recorded - the first-run promise is the measured one, never a
    guess (REQ-PIPE-403 criterion 6; CLI finding 4)."""
    from asset_model import assets, config_yaml

    path = assets.selected().synthetic / MEASURED_FILE
    if not path.exists():
        return None
    got = (config_yaml.load(path) or {}).get("measured") or {}
    if not got:
        return None
    on = got["date"]
    return Measured(seconds=float(got["seconds"]),
                    on=on if isinstance(on, date) else date.fromisoformat(str(on)),
                    commit=str(got.get("commit", "")))


def first_run_prompt() -> str:
    """What the menu asks before a bootstrap: the measured figure for the
    selected asset where one is recorded, and says so where none is."""
    from qa_tools.common.display_time import format_elapsed

    measured = measured_bootstrap()
    if measured is None:
        return ("This has not been measured for this asset - it can take a long "
                "while. Continue?")
    return (f"This takes about {format_elapsed(measured.seconds)} from empty "
            f"(measured on the development sandbox, {measured.on.isoformat()}). Continue?")


TRIALS = "of it target trials"
CONFIRMATIONS = "confirmations"


def took_line(timings: dict[str, float]) -> str:
    """The one 'Took ...' line: each stage's wall clock, generation first and
    the total last - a statement, so it ends with a full stop and never
    trails off (REQ-GEN-399 criterion 4)."""
    # THE SHARED RUN-TIME FORMAT (REQ-TEST-416 criterion 5): '1m 04s', never
    # '64s' - the one formatter the dashboard's own fmtElapsed is held equal to.
    from qa_tools.common.display_time import format_elapsed

    return "Took " + ", ".join(f"{_label(k)} {format_elapsed(v)}"
                               for k, v in timings.items()) + "."


def pinned_line(digest: str) -> str:
    """'Configuration pinned: <first 12 characters of the digest>'
    (REQ-GEN-399 criterion 4), printed dimmed after the budget line."""
    return f"Configuration pinned: {digest[:12]}"


def generated_up_to(dated) -> tuple[str, str]:
    """(the anchor, how it was chosen) for the closing line - 'rolled-back' for
    a roll that stepped back from today (post-build-review #437)."""
    how = "rolled-back" if dated.how == "rolled" and dated.days_back else dated.how
    return dated.anchor.isoformat(), how


def closing_line(result: "BootstrapResult") -> str:
    """The closing line after the pinned digest (REQ-GEN-399 criterion 4,
    REQ-DASH-407 criterion 7): the staged tables and the date the history was
    generated up to - '(the fixed test anchor)', or for a roll '(rolled to
    today on <zone>'s clock; `--anchor <date>` reproduces it)'. An anchor given
    with --anchor says so (PROVISIONAL (2026-11-16): the criterion names only
    the two)."""
    up_to, how = result.generated_up_to or (None, None)
    tail = ""
    if up_to is not None:
        if how == "fixed":
            said = "the fixed test anchor"
        elif how == "rolled":
            said = (f"rolled to today on {generator.zone_name()}'s clock; "
                    f"`--anchor {up_to}` reproduces it")
        elif how == "rolled-back":
            said = (f"rolled to the latest day whose planned receipts had all passed on "
                    f"{generator.zone_name()}'s clock; `--anchor {up_to}` reproduces it")
        else:
            said = f"given with `--anchor {up_to}`"
        tail = f", generated up to {up_to} ({said})"
    return f"{result.staged_after} staged table(s) in this environment{tail}."


def pin_report() -> tuple[str | None, dict[str, str]]:
    """What a process this bootstrap started reports of the pin it ran under
    (REQ-GEN-399 criterion 3): its digest and each file's own digest, so a
    difference can be named file by file. TOP LEVEL, so a spawned process can
    run it by name."""
    import hashlib

    from asset_model import config_pin

    held = config_pin.installed()
    if held is None:
        return None, {}
    return held.digest, {path: hashlib.sha256(text.encode("utf-8")).hexdigest()
                         for path, text in held.texts.items()}


def pin_differences(snapshot, reports) -> tuple[str, ...]:
    """Each started process whose reported pin differs from the bootstrap's,
    naming the process and the files that differed. `reports` maps a stream's
    key to what pin_report() returned in its process."""
    import hashlib

    mine = {path: hashlib.sha256(text.encode("utf-8")).hexdigest()
            for path, text in snapshot.texts.items()}
    out = []
    for process, (digest, files) in reports.items():
        if digest == snapshot.digest:
            continue
        if digest is None:
            out.append(f"{_label(process)}'s process ran with no configuration pinned")
            continue
        differed = sorted({p for p in mine.keys() | files.keys()
                           if mine.get(p) != files.get(p)})
        out.append(f"{_label(process)}'s process ran under {digest[:12]}, not "
                   f"{snapshot.digest[:12]} - differing: "
                   + ", ".join(_shown(p) for p in differed or ["(no file differs)"]))
    return tuple(out)


def _shown(path: str) -> str:
    from pathlib import Path

    from asset_model import assets

    try:
        return str(Path(path).relative_to(assets.ROOT))
    except ValueError:
        return path


def pin_mismatch_message(differences) -> str | None:
    """The one wording every bootstrap caller gives when a started process
    ran under another pin (REQ-GEN-399 criterion 3; CLI finding 10) - the CLI
    and the TUI alike."""
    if not differences:
        return None
    return ("A process this bootstrap started ran under a different configuration "
            "snapshot from the bootstrap's own. This is a fault in mothman's hand-off "
            "of the pinned configuration, not anything you did:\n"
            + "\n".join(f"  - {d}" for d in differences)
            + "\nThe history it recorded is kept but is not to be trusted - replace it "
              "with `mothman env reset-synthetic` then `mothman pipeline bootstrap`.")


def _collection(short: str):
    from asset_model import collections as declared_collections
    return declared_collections.by_short(short)


def with_what_it_reads(names: list[str], say=lambda _m: None) -> list[str]:
    """`names` and every collection whose tables their checks read, in
    registry order (REQ-PIPE-336 criterion 7; Keith, 2026-10-30: added
    automatically, and said). A partial bootstrap of a collection reading
    others would otherwise read every one of their tables as absent and
    record a whole history of could-not-run reds."""
    from asset_model import hierarchy
    from qa_tools.common import run_reads

    wanted = set(names)
    why: dict[str, set[str]] = {}
    for name in names:
        for table in run_reads.reads_for(_collection(name).id).foreign:
            other = _collection_short(hierarchy.dataset_for_table(table).collection_id)
            if other not in wanted:
                why.setdefault(other, set()).add(name)
    for other, readers in sorted(why.items()):
        say(f"Adding {_label(other)}: {', '.join(_label(r) for r in sorted(readers))}'s "
            f"checks read its tables.")
    wanted |= set(why)
    return [n for n in _shorts() if n in wanted]


def reads_others(short: str) -> str | None:
    """Why a checkpoint or resume of `short` is refused, or None
    (REQ-PIPE-336 criterion 7; Keith, 2026-10-30: refuse by name for now). A
    checkpoint counts one collection's own arrivals, so a collection whose
    checks read other collections would be replayed without them and read
    their tables as absent - a history of could-not-run reds no real run
    records. Replaying the whole receipt-ordered stream from a checkpoint is
    not built."""
    from asset_model import hierarchy
    from qa_tools.common import run_reads

    coll = _collection(short)
    others = sorted({_label(_collection_short(hierarchy.dataset_for_table(t).collection_id))
                     for t in run_reads.reads_for(coll.id).foreign})
    if not others:
        return None
    return (f"The checks of {_label(short)} read {' and '.join(others)}, and a checkpoint is of one "
            f"collection's own arrivals, so replaying it alone would read their tables as "
            f"absent - nothing was copied or replayed. Bootstrap from empty instead: "
            f"`mothman pipeline bootstrap`")


def _collection_short(collection_id: str) -> str:
    from asset_model import collections as declared_collections
    return declared_collections.by_id(collection_id).short


def _shorts() -> list[str]:
    """Every collection's short name, hierarchy order (REQ-PIPE-240)."""
    from asset_model import collections as declared_collections
    return [c.short for c in declared_collections.all_collections()]


def _adapter(short: str):
    from qa_tools import collections
    return collections.adapter(_collection(short))


def not_synthetic() -> str | None:
    """Why the bootstrap is refused on this asset, or None (REQ-GEN-381
    criterion 2): read through the one reader of `synthetic: true`
    (REQ-PIPE-382 criterion 7), worded as `mothman env reset-synthetic`'s
    refusal is."""
    from asset_model import asset_time, assets

    if asset_time.declared_synthetic():
        return None
    return (f"{assets.selected().name} is not declared synthetic in "
            f"{assets.config_dir()}/data-asset.yaml - the bootstrap replays a synthetic "
            f"history, and nothing was generated. A real asset's first run is "
            f"`mothman pipeline run`.")


def _generate(short: str, *, trial: bool, try_targets=None, say=print) -> None:
    """Generate one collection's synthetic history through the generator's
    public module (REQ-GEN-381 criterion 3). Its target trial runs only where
    its provider declares one (REQ-GEN-246 criterion 5) - asking it of one
    without would be refused."""
    collection_id = _collection(short).id
    generation.generate_collection(
        collection_id, trial=trial and generator.has_target_trial(collection_id),
        try_targets=try_targets, say=say)


def _label(key: str) -> str:
    """How a collection's work is named when it is reported - a stream's by
    each of its collections (REQ-PIPE-262 criterion 10) - or the total."""
    if key == "total":
        return "in total"
    if key in (GENERATION, TRIALS, CONFIRMATIONS):
        return key
    return " and ".join(_adapter(k).label for k in key.split(STREAM_JOIN))


#: A stream's key: its collections' shorts, joined (REQ-PIPE-262).
STREAM_JOIN = "+"


def _stream_key(group: list[str]) -> str:
    return STREAM_JOIN.join(group)


def _run_stream(key: str, sequential: bool) -> float:
    """Run one stream's pipeline (REQ-PIPE-262); return how long it took.
    A stream of one collection is that collection's own run. TOP LEVEL, so a
    spawned process can import it by name.

    ON THE REPLAY'S CLOCK, installed here around the bootstrap's own call
    (REQ-PIPE-382 criterion 11), with ONE COMBINED PLAYER built here and passed
    in (REQ-PIPE-383 criterion 2): every collection's scripted decisions,
    played before ANY arrival of the stream received after a decision's
    instant (REQ-PIPE-262 criterion 4)."""
    names = key.split(STREAM_JOIN)
    if len(names) == 1:
        return _run_collection(names[0], sequential)
    started = time.monotonic()
    from bootstrap import decision_player, replay_clock
    from qa_tools.tools import orchestrate

    ids = [_adapter(n).collection_id for n in names]
    with replay_clock.replaying():
        player = decision_player.StreamPlayer(decision_player.Player(cid) for cid in ids)
        orchestrate.run_stream(ids, sequential=sequential, record_deliveries=False,
                               player=player)
    return time.monotonic() - started


def targets_agree(names) -> tuple[str, ...]:
    """Each targeted supply of the collections just replayed, its RECORDED
    verdict as the promotion gate reads it against what it was built to
    (REQ-GEN-186 criterion 3) - injected targets, their green lead-in and
    following days, and every ordinary amber, in both collections. Reads
    recorded results only and changes nothing (criterion 6).

    What each supply was built to comes from the generator's public module
    (generated_targets), because no QA module may read the generator's
    bookkeeping (REQ-GEN-043 criterion 7)."""
    from bootstrap import target_agreement

    # Which datasets' targets each collection's replay records - declared
    # once, on its generator provider (REQ-GEN-246 criterion 5).
    wanted = {d for n in names for d in generator.target_datasets(_collection(n).id)}
    try:
        built = [b for b in generator.generated_targets() if b.dataset_id in wanted]
    except ValueError as exc:
        # A RECORD THAT DOES NOT ADD UP is a disagreement, said in one line,
        # not a traceback (post-build-review #157 finding 7).
        return (f"what the generator built could not be read: {exc}",)
    with supply_db.connect(label="mothman:bootstrap") as conn:
        failing, reported = target_agreement.replay_report(conn, built)
        # REPORTED, NEVER A FAILURE (REQ-GEN-273 criterion 2): a supply whose
        # own checks matched its target, read otherwise only because a
        # package-mate was held back or a table could not be read.
        for r in reported:
            print(f"note: {r}")
        # AND EACH DECLARED GATE OUTCOME (criterion 3), a failure where the
        # record differs - declared by the scenarios, read through the
        # generator's public module.

        # BY COLLECTION, NOT BY TARGET DATASET: a declared gate outcome names
        # any table of its package (Notifications held back beside Clients),
        # and Child Protection's providers declare only cp-clients' targets -
        # filtering by `wanted` dropped every other dataset's declaration in
        # silence (found building REQ-GEN-273 criterion 4, 2026-10-25).
        replayed = {_collection(n).id for n in names}
        declared = [o for o in generator.generated_gate_outcomes()
                    if _collection_of_dataset(o.dataset_id) in replayed]
        failing = [*failing, *target_agreement.gate_outcome_differences(conn, declared)]
        return tuple(str(d) for d in failing)


def _collection_of_dataset(dataset_id: str) -> str | None:
    from asset_model import hierarchy

    try:
        return hierarchy.dataset(dataset_id).collection_id
    except hierarchy.UnknownDatasetError:
        return None


def _confirm_corrections(say) -> None:
    from bootstrap import correction_replay, replay_clock

    # STAMPED WHERE THE REPLAYED HISTORY ENDS, not the wall clock
    # (post-build-review #177) - the bootstrap is synthetic-only, so its
    # confirmations are always on the replay's clock (REQ-GEN-381 criterion 2).
    with replay_clock.replaying():
        with supply_db.connect(label="mothman:bootstrap") as conn:
            end = correction_replay.history_end(conn)
        done = correction_replay.confirm_due(history_end=end, say=say)
        if done:
            _run_what_the_confirmations_owe(say)
    if done:
        for short in _shorts():
            _rebuild_results(short)


def _run_what_the_confirmations_owe(say) -> None:
    """REQ-GEN-205 criterion 8: each moved or placed supply's re-check and
    gate, and the knock-on re-evaluation of each period a move left or
    reached, run here - inside the bootstrap's pass lock and under the
    replay clock - rather than left owed in a history that ends. A run that
    does not complete stops the bootstrap, as a refused scripted decision
    does; one the backstop froze stays owed and is not a failure."""
    from qa_tools.common import recheck
    from scenarios.scripted_decisions import ScriptRefused

    with supply_db.connect(label="mothman:bootstrap") as conn:
        n = len([o for o in recheck.owed(conn)
                 if o.kind in (recheck.RECHECK, recheck.REEVALUATE)])
    if not n:
        return
    say(f"Running the {n} run(s) the confirmed corrections owe - each takes about a minute")
    outcomes = recheck.run_all_owed(kinds=(recheck.RECHECK, recheck.REEVALUATE))
    # NOT JUDGED IS A RED THAT STAYS OWED, not a run that did not complete
    # (Keith, 2026-10-25, post-build-review #274 D2).
    failed = [o for o in outcomes if not o.completed and not o.frozen and not o.not_judged]
    if failed:
        raise ScriptRefused(
            "The bootstrap stopped: a run the confirmed corrections owe did not complete - "
            + "; ".join(f"{o.run_key or f'owed item {o.owed_id}'} ({o.message})"
                        for o in failed))


def _record_deliveries() -> None:
    from bootstrap import replay_clock
    from qa_tools.common import delivery_log

    # Each delivery stamped as received (REQ-PIPE-081 criteria 27-31) - the
    # replay's first records.
    with replay_clock.replaying():
        delivery_log.record_all()


def _run_collection(name: str, sequential: bool, record_deliveries: bool = False,
                    *, player=None, **replay) -> float:
    """Run one collection's whole pipeline; return how long it took.
    `replay` is start_at / after_each, for a checkpoint or a resume.

    ON THE REPLAY'S CLOCK, installed around this call (REQ-PIPE-382 criterion
    11), with THE COLLECTION'S PLAYER built here - or a resume's, given - and
    passed in (REQ-PIPE-383 criterion 2): the real pipeline builds none.

    TOP LEVEL, so a spawned process can import it by name.
    """
    started = time.monotonic()
    from bootstrap import decision_player, replay_clock
    from qa_tools.tools import orchestrate

    collection_id = _adapter(name).collection_id
    with replay_clock.replaying():
        orchestrate.run_pipeline(
            collection_id, sequential=sequential, record_deliveries=record_deliveries,
            player=player if player is not None else decision_player.Player(collection_id),
            **replay)
    return time.monotonic() - started


def _checkpoint_hook(name: str, before: int, held, say, on_name=None):
    """The after_each that takes the checkpoint, with `before` snapped back
    to where its delivery or receipt instant begins - said aloud when it
    moves, and every arrival named with its delivery (#133 B4)."""
    from asset_model import arrivals
    from bootstrap import checkpoints

    collection_id = _collection(name).id
    found = arrivals.arrivals_for(collection_id, "")
    at = checkpoints.snapped(found, before)
    if at != before:
        say(f"{checkpoints.named(found, before).capitalize()} belongs with the arrivals before "
            f"it (the same delivery or the same receipt instant), so the checkpoint is taken "
            f"before {checkpoints.named(found, at)}, where they begin.")

    def taken(cp) -> None:
        say(f"Checkpoint {cp.name} taken before {checkpoints.named(found, cp.before)}.")
        if on_name is not None:
            on_name(cp.name)
    return checkpoints.taking_checkpoint(collection_id, at, held.paused, on_taken=taken)


@dataclass(frozen=True)
class ResumeResult:
    """What a resume did. `dsn` is the resume's own database - None when
    nothing was replayed."""

    replayed: bool
    reason: str
    dsn: str | None = None
    first_affected: int | None = None
    refused: bool = False
    #: As BootstrapResult's: a resume is a replay too (REQ-GEN-186
    #: criterion 3), compared in the resume's own database.
    disagreements: tuple[str, ...] = ()
    #: As BootstrapResult's (REQ-PIPE-430 criterion 3).
    tree_changes: tuple[str, ...] = ()


def resume(name: str, sequential: bool = False,
           on_step: Callable[[str], None] | None = None) -> ResumeResult:
    """REQ-TEST-159 criteria 2 to 4 and 6: copy a checkpoint into a database
    of its own and replay into it arrival N onwards - once REQ-TEST-160 has
    found nothing changed before N. Refusals change nothing.

    WITH THE ASSET'S CONFIGURATION PINNED (REQ-GEN-399 criterion 1), as a
    bootstrap is: one snapshot from the regeneration it compares through the
    replay and the confirmations. An asset that is not synthetic is refused
    in the resume's own words first, so nothing is pinned for it."""
    from asset_model import asset_time, config_pin

    if not asset_time.declared_synthetic():
        return _resume(name, sequential, on_step)
    with config_pin.pinned():
        return _resume(name, sequential, on_step)


def _resume(name: str, sequential: bool, on_step) -> ResumeResult:

    from bootstrap import checkpoints

    say = on_step or (lambda _msg: None)
    try:
        checkpoints.require_synthetic()
        cp = checkpoints.find(name)
        if cp.collection_id:
            from asset_model import collections as _c

            # THE RESUME'S NAME FITS, before anything is regenerated (#346).
            checkpoints.require_names_fit(_c.by_id(cp.collection_id).short, cp.before)
    except checkpoints.CheckpointRefused as exc:
        return ResumeResult(replayed=False, refused=True, reason=str(exc))

    if cp.collection_id:
        from asset_model import collections as _colls

        reads = reads_others(_colls.by_id(cp.collection_id).short)
        if reads:
            return ResumeResult(replayed=False, refused=True, reason=reads)

    if not cp.recorded.readable or not cp.collection_id:
        # AN UNREADABLE DESCRIPTION IS A REFUSAL, never a crash (#133 B2):
        # nothing says where a change begins, so it would be the first
        # arrival - before any checkpoint.
        return ResumeResult(
            replayed=False, refused=True, first_affected=1,
            reason=f"{name}'s record of what it was made from cannot be read, so a resume "
                   "would have to start from the first arrival, which is before this "
                   "checkpoint - nothing was copied or replayed. Start again with a "
                   "bootstrap from empty")

    # THE ANCHOR THE HISTORY WAS GENERATED AT, NEVER TODAY'S (REQ-GEN-404
    # criterion 6): every regeneration below - the comparison's and the
    # replay's - is at it, and a checkpoint recording none is refused.
    anchor = checkpoints.recorded_anchor(cp)
    if anchor is None:
        return ResumeResult(
            replayed=False, refused=True,
            reason=f"{name} records no anchor for the history it copied (it was taken before "
                   f"REQ-GEN-404), so its deliveries cannot be regenerated as they were - "
                   f"nothing was copied or replayed. Run `mothman env reset-synthetic` then "
                   f"`mothman pipeline bootstrap`")
    with history_anchor.anchored(anchor):
        return _resume_at(name, cp, sequential, say)


def _resume_at(name, cp, sequential: bool, say) -> ResumeResult:
    import os

    from bootstrap import checkpoints, decision_player, replay_inputs
    from qa_tools.common import processing_pass

    from scenarios import scripted_decisions
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

    from asset_model import collections as declared_collections

    short = declared_collections.by_id(cp.collection_id).short
    say("Generating the synthetic data the replay reads")
    # NO TRIAL HERE (post-build-review #157 finding 3): this runs before the
    # resume has a database of its own, so a trial would write - and discard -
    # a run in the database the person was pointed at, which a resume never
    # writes to. The comparison after the replay below still runs.
    for collection_id in generator.generated_collections():
        generation.generate_collection(collection_id, trial=False, say=say)
    total = len(dict.fromkeys(a.run_id for a in cp.recorded.arrivals))
    # SAID BEFORE THE COPY, so a wrong resume can be stopped early (#133 B9).
    say(f"{first.reason}. Replaying arrivals {cp.before} to {total} of {_label(short)} into "
        f"a new database of the resume's own, copied from {cp.name}.")
    dsn = checkpoints.copy_for_resume(cp)
    resume_db = psycopg.conninfo.conninfo_to_dict(dsn)["dbname"]

    previous = os.environ.get(supply_db.SUPPLY_DSN_ENV)
    os.environ[supply_db.SUPPLY_DSN_ENV] = dsn
    supply_db.release_connections()
    tree = _Trees()
    try:
        with processing_pass.pass_lock("resume"):
            player = decision_player.Player(
                cp.collection_id,
                scripts=[scripted_decisions.Script(**s) for s in cp.pending_scripts])
            # THE TREE SNAPSHOT AFTER THE RESUME'S GENERATION (REQ-PIPE-430
            # criterion 1), released once its replay is done.
            tree.install([cp.collection_id])
            say(f"Replaying {_label(short)} from arrival {cp.before}")
            _run_collection(short, sequential, record_deliveries=True,
                            start_at=cp.before, player=player)
            # AS A BOOTSTRAP FROM EMPTY DOES (REQ-GEN-205 criterion 19): the
            # copy holds every other collection's replay already.
            _confirm_corrections(say)
            tree.release()
        _rebuild_results(short)
        say("Comparing every targeted supply's recorded verdict with what it was built to")
        disagreements = targets_agree([short])
    except BaseException:
        # A FAILED RESUME NAMES WHAT IT LEFT (#131 D5): its database is kept
        # for whoever investigates, and listed by `checkpoint list`.
        say(f"The resume stopped part-way; its database {resume_db} is left as it stood - "
            f"`mothman pipeline checkpoint delete {resume_db}` removes it.")
        raise
    finally:
        tree.release(check=False)
        supply_db.release_connections()
        if previous is None:
            os.environ.pop(supply_db.SUPPLY_DSN_ENV, None)
        else:
            os.environ[supply_db.SUPPLY_DSN_ENV] = previous
    return ResumeResult(replayed=True, dsn=dsn, first_affected=first.arrival,
                        reason=f"{first.reason}; replayed from arrival {cp.before}",
                        disagreements=disagreements, tree_changes=tuple(tree.changes))


def _rebuild_results(short: str) -> None:
    """A resume processed only part of the collection, so its results file
    is rebuilt from the whole recorded history rather than left partial.
    QUIETLY: its own count line, printed beside the replay's, read as two
    disagreeing totals (post-build-review #133 B12)."""
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        from qa_tools.tools import results_history

        results_history.build_results_from_history(_adapter(short).collection_id)


def _run_concurrently(names: list[str], sequential: bool):
    """Each collection in a process of its own; ({stream: seconds}, {stream:
    the pin it ran under}).

    PROCESSES, NOT THREADS. The four QA tools run in-process and keep
    process-wide state - Soda Core reloads `.env` into os.environ on its
    first scan (plans/tooling.md #26), and dbt and datacontract-cli were
    never written to share an interpreter. A process each is the
    isolation the two pipelines already had when run one after the
    other. SPAWNED rather than forked, so neither inherits the other's
    half-initialised connections or imported tool state.

    A failure in either fails the bootstrap: `.result()` re-raises it.

    EACH PROCESS IS HANDED THE ASSET BESIDE ITS COLLECTIONS (REQ-PIPE-369
    criterion 4), AND THE LAYOUT IT WAS FOUND IN (assets.handoff): a spawned
    interpreter never sees this one's selection or a use_root/use_folder
    layout, and adopts both itself before it loads any adapter by path - never an
    adapter object, which a path-loaded module cannot be unpickled into.
    """
    with stream_pool(len(names)) as pool:
        # _run_stream LOOKED UP HERE and handed by reference, so the process
        # runs whatever this module names it now.
        futures = {n: pool.submit(_reporting, _run_stream, n, sequential) for n in names}
        ran = {n: f.result() for n, f in futures.items()}
    return {n: r[0] for n, r in ran.items()}, {n: r[1] for n, r in ran.items()}


def stream_pool(workers: int):
    """The bootstrap's own process pool: SPAWNED, each process handed the
    asset, its layout and the pinned configuration through the one hand-off
    (assets.handoff; REQ-PIPE-397 criterion 12), never re-read."""
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    from asset_model import assets

    return ProcessPoolExecutor(max_workers=workers,
                               mp_context=multiprocessing.get_context("spawn"),
                               initializer=_adopt_for_stream, initargs=assets.handoff())


#: A hand-off the stream process refused (config_pin.PinMismatch), kept to be
#: raised by its first task rather than breaking the pool (post-build-review
#: #398): an initializer that raises surfaces only as BrokenProcessPool.
_REFUSED_HANDOFF: BaseException | None = None


def _adopt_for_stream(*handed) -> None:
    """assets.adopt, its refusal of a mismatched snapshot kept for the task."""
    global _REFUSED_HANDOFF
    from asset_model import assets, config_pin

    try:
        assets.adopt(*handed)
    except config_pin.PinMismatch as exc:
        _REFUSED_HANDOFF = exc


def _reporting(run, *args):
    """`run(*args)` in a started process, with the pin it ran under
    (REQ-GEN-399 criterion 3). TOP LEVEL, so a spawned process can import it
    by name. A refused hand-off is raised here, as itself."""
    if _REFUSED_HANDOFF is not None:
        raise _REFUSED_HANDOFF
    return run(*args), pin_report()
