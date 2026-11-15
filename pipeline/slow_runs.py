"""Which whole-supply runs were slow (REQ-PIPE-412).

ONE PURE FUNCTION OF A DATASET'S RUNS, called from the dashboard build: a run
is SLOW when its run time is STRICTLY MORE than twice the median run time of
the last WINDOW earlier whole-supply runs of its dataset (T3, TA Q2, TA Q3).

- WHOLE-SUPPLY RUNS ONLY: scope 'arrival' or 'full'. A readers-only run is
  neither judged nor counted in any baseline (TA Q2).
- A RUN TIME, OR NOTHING: a run counts only where it has one - its newest
  attempt completed (REQ-PIPE-409 criterion 7) - so no failed try is in any
  median (TR8), and a not-checked run is judged against nothing.
- EARLIER BY RANK ALONE: each run is judged against runs ranked before it, so
  its mark never changes when later runs are recorded and the as-of view shows
  the same past.
- FEWER THAN MINIMUM EARLIER RUNS: neither slow nor not slow - too few to
  judge.

THE MARK IS NEVER A STATUS (TR9): nothing here is read by a Pass/Warn/Fail,
the promotion gate, the 'needs a person' queue, a ticket, an exit status or
the terminal. No database access; no configuration per dataset (T3).
"""
from __future__ import annotations

#: The last 20 earlier whole-supply runs (TA Q3, SETTLED by Keith 2026-11-14,
#: option (b) - a choice rather than a measurement).
WINDOW = 20
#: At least 3 of them before a run is judged (TA Q3).
MINIMUM = 3
#: The scopes a whole-supply run has (TA Q2).
WHOLE_SUPPLY = ("arrival", "full")


def _twice_median(values: list[int]) -> int:
    """Twice the median, kept in whole milliseconds: an even-sized baseline's
    median is the mean of its two middle values, so twice it is their sum and
    'exactly twice is not slow' stays an exact integer comparison."""
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] * 2 if len(ordered) % 2 else ordered[mid - 1] + ordered[mid]


def marks(runs: list[dict]) -> list[dict]:
    """`runs` - one dataset's runs, each with its `rank`, `scope` and
    `run_time_ms` (None where it has none) - returned in rank order, each with
    `slow`: True, False, or None where it is not judged; `too_few` where it is
    a whole-supply run with a run time and fewer than MINIMUM earlier ones; and
    `median_ms` and `judged_against` only for a run marked slow and for the
    dataset's newest judged-or-too-few run (N9)."""
    ordered = sorted(runs, key=lambda r: r["rank"])
    earlier: list[int] = []
    out: list[dict] = []
    newest = None
    for run in ordered:
        mark = {**run, "slow": None, "too_few": False}
        took = run.get("run_time_ms")
        if run.get("scope") in WHOLE_SUPPLY and took is not None:
            baseline = earlier[-WINDOW:]
            if len(baseline) < MINIMUM:
                mark["too_few"] = True
            else:
                twice = _twice_median(baseline)
                # STRICTLY MORE THAN TWICE THE MEDIAN, in whole milliseconds.
                mark["slow"] = took > twice
                mark["_median"] = (twice / 2, len(baseline))
            newest = mark
            earlier.append(took)
        out.append(mark)
    for mark in out:
        median = mark.pop("_median", None)
        if median is not None and (mark["slow"] or mark is newest):
            value, count = median
            mark["median_ms"] = int(value) if value == int(value) else value
            mark["judged_against"] = count
    return out
