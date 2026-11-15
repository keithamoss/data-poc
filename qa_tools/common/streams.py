"""What real commands read that used to be the bootstrap's (REQ-GEN-381
criterion 5): how collections group into streams, and the refusal over
recorded history - so `mothman pipeline run` and the knock-on need nothing of
the bootstrap package, which a real deployment leaves out.

STREAMS (REQ-PIPE-262): collections whose datasets resolve to a shared
calendar are one receipt-ordered stream, as the live pass is, so who opens each
period first never depends on which collection ran first. The bootstrap
replays by stream; `pipeline run` runs by stream; the knock-on follows up a
whole stream (knock_on.follow_up_stream).

THE HISTORY REFUSAL (REQ-PIPE-144 criteria 38 and 39): one message for
`mothman pipeline run` and the bootstrap, because filings are write-once and the
decision log append-only, so a re-run ADDS to the history rather than replacing
it.
"""
from __future__ import annotations

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

    Asked of the database, and true of a qa schema from ANY version - an older
    one is history too, and is refused by ensure_schema with the same remedy.
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


class StreamRefused(ValueError):
    """A collection's datasets' calendars cannot be resolved, so which
    stream it belongs to is unknown (REQ-PIPE-262 criterion 9)."""


def _collection_datasets(short: str) -> list:
    from asset_model import collections, hierarchy

    return hierarchy.datasets_in_collection(collections.by_short(short).id)


def _calendar_name(dataset_id: str) -> str:
    from asset_model import schedule

    return schedule.calendar_for_dataset(dataset_id).name


def streams(names: list[str]) -> list[list[str]]:
    """The collections replayed together (REQ-PIPE-262 criteria 1 and 2):
    two share a stream whenever any dataset of one resolves to a calendar any
    dataset of the other resolves to, transitively. FROM CONFIGURATION ALONE -
    no list of collections or calendars is held here. A dataset declared to
    have no calendar joins nothing. Registry order, within and across
    streams."""
    from asset_model import schedule

    calendars: dict[str, set[str]] = {}
    for name in names:
        found = set()
        for d in _collection_datasets(name):
            try:
                found.add(_calendar_name(d.dataset_id))
            except schedule.NoCalendarAgreed:
                continue
            except (schedule.ScheduleConfigError, LookupError) as exc:
                raise StreamRefused(
                    f"collection {name!r}: the calendar of dataset {d.dataset_id!r} cannot be "
                    f"resolved ({exc}), so which stream it replays in is unknown - nothing "
                    f"was run") from exc
        calendars[name] = found
    groups: list[list[str]] = []
    for name in names:
        joined = [g for g in groups if any(calendars[name] & calendars[o] for o in g)]
        merged = [n for g in joined for n in g] + [name]
        groups = [g for g in groups if g not in joined] + [merged]
    order = {n: i for i, n in enumerate(names)}
    return sorted((sorted(g, key=order.get) for g in groups), key=lambda g: order[g[0]])
