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

from dataclasses import dataclass
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

    `force` re-runs even when the database already holds staged tables -
    the pipeline is deterministic and seeded, so re-running is safe and
    reproduces the same content; it just is not free.
    """
    say = on_step or (lambda _msg: None)

    say("Checking what this environment already holds")
    with supply_db.connect(label="mothman:bootstrap") as conn:
        supply_db.ensure_schemas(conn)
        before = staged_table_count(conn)

    if before and not force:
        return BootstrapResult(
            populated=False, staged_before=before, staged_after=before,
            reason=f"{before} staged table(s) already present - nothing to do "
                   f"(use --force to rebuild anyway)")

    # IMPORTED HERE, NOT AT MODULE LEVEL. cli/ imports this module, and
    # these import the orchestrators, which pull in all four QA tools -
    # several seconds of import time that a caller only checking
    # `already_populated()` should not pay.
    from cli import bdm, cp
    from qa_tools.bdm.orchestrate_bdm import run_pipeline
    from qa_tools.cp.orchestrate_cp import run_pipeline_cp

    if collection in ("all", "bdm"):
        say("Generating synthetic data (Birth Registrations)")
        bdm.generate_synthetic_data()
        say("Running the real checks against every Birth Registrations supply")
        run_pipeline(sequential=sequential)
    if collection in ("all", "cp"):
        say("Generating synthetic data (Child Protection)")
        cp.generate_synthetic_data()
        say("Running the real checks against every Child Protection supply")
        run_pipeline_cp(sequential=sequential)

    with supply_db.connect(label="mothman:bootstrap") as conn:
        after = staged_table_count(conn)
    return BootstrapResult(populated=True, staged_before=before, staged_after=after)
