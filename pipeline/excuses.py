"""Which supplies' lateness a person excused, for the dashboard
(REQ-DASH-162, consuming REQ-PIPE-161's excuse).

THE INSTANTS TRAVEL, NOT THE RULE - the same decision as
pipeline/acknowledgements.py. Each excuse is embedded with when it was
recorded, its withdrawal if any, and its lapse if any, and the page compares
those with the date on show (criterion 5). The excuse is carried BESIDE the
arrival classification, never as a new arrival status (criterion 7).

RECORDED QA METADATA ONLY: qa.decision, qa.filing_current and qa.verdict.
Keyed by the RUN that checked the supply, through slot_timeline's one
mapping from a supply to its run, so it sits on the row it describes.
"""
from __future__ import annotations

from qa_tools.common import decision_log, excuse, supply_db


def _named(record: dict) -> dict:
    """The person by NAME (REQ-PIPE-147 criterion 7), as everywhere else."""
    from qa_tools.common import people

    out = {**record, "actor": people.display_name(record["actor"])}
    if record.get("withdrawn"):
        out["withdrawn"] = {**record["withdrawn"],
                            "actor": people.display_name(record["withdrawn"]["actor"])}
    return out


def for_dataset(dataset_id: str,
                conn: supply_db.SupplyConnection | None = None) -> dict[str, list[dict]]:
    """{run_id: [excuse, ...]} oldest first, for every supply ever excused."""
    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:excuses") as opened:
            return for_dataset(dataset_id, opened)
    from pipeline import slot_timeline

    supplies = [r[0] for r in conn.execute(
        f"SELECT DISTINCT supply FROM {decision_log.TABLE} WHERE dataset_id = ? "
        "AND action = ?", [dataset_id, decision_log.EXCUSE_LATENESS]).fetchall()]
    out: dict[str, list[dict]] = {}
    for supply in supplies:
        run_id = slot_timeline._run_for(conn, dataset_id, supply)
        if run_id:
            out[run_id] = [_named(e.as_record())
                           for e in excuse.history(conn, dataset_id, supply)]
    return out
