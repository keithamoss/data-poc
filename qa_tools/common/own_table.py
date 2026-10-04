"""Why a run cannot read its OWN table, or that it can (REQ-PIPE-115
criteria 5, 6 and 9).

A run's own table is the one its arrival carried, so there are only
three ordinary reasons it is unreadable, and each is something the
ARRIVAL brought with it:

- HELD: the supply was filed to no period, because no slot of its
  dataset was open at its receipt instant (REQ-PIPE-131). Nobody has
  said which period it is for, so nothing may be judged against it.
- CONTESTED: the arrival carried two files for the table (REQ-PIPE-105
  criterion 6), and choosing between them is a person's job.
- REFUSED: the load refused the file (REQ-DASH-148), so there is no
  table to read.

Every check in such a run's scope is either the dataset's own or reads
its table, so nothing in it is evaluable - and running the tools anyway
recorded ordinary verdicts against a supply with no period, the defect
this module exists to stop. The dataset is signalled ONCE, by the
outstanding item it already raises, never by a red per check.

ANY OTHER REASON IS A FAILED RUN (criterion 9). A run whose own table
is simply missing with none of the three to explain it has been set up
wrong, and recording nothing for it would be the silent gap the whole
requirement is against.
"""
from __future__ import annotations

from qa_tools.common import supply_db

HELD = "held"
CONTESTED = "contested"
REFUSED = "refused-load"


class UnreadableOwnTable(RuntimeError):
    """A run's own table is missing for no reason the pipeline knows."""


def _refused(own_dataset: str | None, arrival_key: str | None) -> bool:
    if not own_dataset or not arrival_key:
        return False
    from qa_tools.common import load_log

    # EVERY CURRENT FAILURE, settled or not: a load a person has rejected
    # still could not be loaded, and its run is still not a failed run.
    for record in load_log.latest_by_table().values():
        if record.loaded or record.dataset_id != own_dataset:
            continue
        parts = supply_db.split_staged(record.physical)
        if parts and parts[1] == arrival_key:
            return True
    return False


def why_unreadable(conn, run_id: str, own_table: str, resolution, *,
                   own_dataset: str | None = None,
                   arrival_key: str | None = None) -> str | None:
    """HELD, CONTESTED or REFUSED where the run must not check its own
    table, None where it may.

    CONTESTED WINS OVER A READABLE VIEW. A contested table can fall
    through to the period's promoted version, so the view exists - but
    it is not this arrival's supply, and checking it would put a verdict
    about last quarter's data under this arrival's run (REQ-PIPE-079
    criterion 13 as amended by REQ-PIPE-115 criterion 22).
    """
    if own_table in resolution.held:
        return HELD
    if own_table in resolution.ambiguous:
        return CONTESTED
    if own_table in supply_db.readable_in(conn, run_id):
        return None
    if _refused(own_dataset, arrival_key):
        return REFUSED
    raise UnreadableOwnTable(
        f"{run_id}: its own table {own_table} cannot be read, and it is not held, "
        f"contested or refused at load - see its tables_read. A run that cannot "
        f"read the table its own arrival carried has been set up wrong.")


def describe(run_id: str, own_table: str, why: str) -> str:
    """One line per run, whatever the number of checks it leaves out."""
    words = {HELD: "its supply is held, waiting for a person to place it",
             CONTESTED: "two files claim it, waiting for a person to choose one",
             REFUSED: "the load refused the file"}[why]
    return (f"note: {run_id}: {own_table} cannot be read - {words} - so no tool runs "
            f"and nothing is checked; its dataset reads red until that is resolved.")
