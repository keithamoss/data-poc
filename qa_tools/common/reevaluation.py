"""What a newly arrived table sets off (REQ-PIPE-079 criteria 6 and 7).

A cross-table check compares tables that belong together, and TOGETHER
MEANS ONE PERIOD. So when a table arrives, the checks that read it are
re-evaluated - but only within that table's own period. August's carers
arriving says nothing about May's placements, and re-running May's
check because August arrived would produce a fresh verdict computed
from unchanged data. That is worse than not running it, because it
looks like news.

AND THE RESULT SAYS WHAT CAUSED IT. A verdict that changed without
anybody touching that dataset is a mystery to whoever reads it next.
Naming the arrival turns "this went red overnight" into "this went red
when carers arrived", which is the difference between a question and an
answer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

#: The key a re-evaluated result carries its cause under.
#:
#: DELIBERATELY NOT A COLUMN. qa_store.write_results puts any key it
#: does not recognise into the `extra` jsonb column, so this needs no
#: DDL - but only while the name stays off _RESULT_COLUMNS and
#: _KEY_COLUMNS, which a test asserts rather than trusts.
CAUSED_BY = "reevaluated_after_arrival_of"
#: The decision a decision-triggered run was made for (REQ-PIPE-140
#: criterion 4), a different key from an arrival's on purpose, so the two
#: causes are distinguishable on every result (REQ-PIPE-079 criterion 7).
CAUSED_BY_DECISION = "reevaluated_after_decision"


@dataclass(frozen=True)
class Plan:
    """The checks one arrival sets off, and the single period they run in."""

    period: str
    check_ids: frozenset[str]

    @property
    def is_empty(self) -> bool:
        return not self.check_ids


def plan(*, table: str, period: str, reads: Mapping[str, list[str]]) -> Plan:
    """Which checks this arriving table sets off, within its own period.

    `reads` is check_id -> the logical tables that check declares it
    reads - what tables_read.declared_by_check_id() returns, and the
    same source promotion.status_of() and promotion.checks_reading()
    use. A fourth implementation of "which checks touch this table" is
    how the four come to disagree.

    THE PERIOD IS CARRIED, NOT DERIVED. A caller that already knows
    which period the table arrived into passes it; nothing here works
    it out, because working it out is where a re-evaluation would
    escape into a period the arrival says nothing about.
    """
    return Plan(period=period,
                check_ids=frozenset(
                    check_id for check_id, tables in reads.items() if table in tables))


def mark(record: Mapping[str, Any], *, caused_by: str) -> dict:
    """Name, on a re-evaluated result, the arrival that caused it.

    Returns a NEW record. Editing the caller's is how one result's
    provenance ends up on the next one - a class of bug that is
    invisible until somebody reads the history and finds every check
    blaming the same arrival.
    """
    return {**record, CAUSED_BY: caused_by}


def mark_decision(record: Mapping[str, Any], *, decision_id: int) -> dict:
    """Name, on a result of a decision-triggered run, the decision that
    caused it - never an arrival (post-build-review #114, D6). A new
    record, for mark()'s reason."""
    out = {k: v for k, v in record.items() if k != CAUSED_BY}
    out[CAUSED_BY_DECISION] = str(decision_id)
    return out
