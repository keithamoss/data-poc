"""
Shared "shape 2" aggregate failing-value computation for the dashboard's
check-detail panel: what specific values actually failed a closed-value-
set check (distinct invalid values + counts), or a numeric/date range
check (min/max among the failing values, the distinct failing values
themselves, and a binned histogram) - the "surface more about the nature
of the failure" idea scoped with Keith via AskUserQuestion (see
plans/qa-pipeline.md #17), the aggregate counterpart to item 15's
per-row PK-only samples.

Deliberately computed via a fresh, direct SQL query against each run's
own warehouse table, independent of which real tool (dbt/Soda/
datacontract-cli) actually flagged the check - all three point at the
same staging data for a given column, so there's one true answer
regardless of which engine's own internal sample/audit-table format
happens to carry it. Verified with real research, not assumed (see
plans/qa-pipeline.md #19): dbt's own accepted_values/unique
--store-failures audit table already has almost exactly this (value,
n_records) shape - reusing it directly would have worked for dbt
specifically, and wasn't a hard technical need there, just traded for
one uniform code path across all three tools instead of a different one
per tool. Soda's and datacontract-cli's own native sample caps (Soda
Core's real default is up to 100 rows, not the 5 this project's own
CaptureSampler self-imposes to match datacontract-cli's fixed cap) are
genuinely too small to give a true, exhaustive aggregate either way -
some additional mechanism actually was needed for those two.
`total_invalid` is computed as its own COUNT(*), not derived from the
(capped) values list, so it stays correct even past the cap.

Sensitive columns (a real ODCS `classification` property - see the
contract, matching datacontract-cli's own vocabulary) get their actual
VALUES suppressed before this ever reaches the dashboard JSON - the
count is still safe to show (a number on its own isn't personal data),
but the value labels are not. No currently-registered closed-value-set/
range check in this project actually sits on a classified column (names
are checked via a character-set pattern, not a closed value set or a
range) - this exists so the mechanism is correct and ready the day one
does, not exercised by real data today.
"""
from __future__ import annotations

from datetime import timedelta

import duckdb

# Both the categorical distinct-invalid-values list and the numeric/date
# distinct-outlier-values list - generous relative to every pool actually
# used in this project's dirty.py presets (4-7 distinct values), so this
# cap is a genuine safety ceiling, not something real data ever brushes.
AGGREGATE_VALUE_CAP = 20

HISTOGRAM_BINS = 6


def categorical_aggregate(conn: duckdb.DuckDBPyConnection, table: str, column: str, invalid_condition: str,
                           classification: str | None, params: list | None = None) -> dict:
    """Distinct invalid values + counts for a closed-value-set check.
    `invalid_condition` is a raw SQL boolean expression (e.g. "sex NOT IN
    ('M','F','X') OR sex IS NULL") - the caller owns the exact valid-value
    list so it can match whatever dbt/Soda/datacontract-cli actually
    enforce, rather than this module keeping its own possibly-drifting
    copy. `params` are extra `?` bind values `invalid_condition` refers to
    (e.g. a `run_id = ?` scope for a combined multi-run warehouse)."""
    params = list(params or [])
    total = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {invalid_condition}", params).fetchone()[0]
    suppressed = classification is not None
    values: list[dict] = []
    if not suppressed and total:
        rows = conn.execute(
            # ORDER BY n DESC, v - the `, v` is the fix for a real bug
            # (2026-09-25). Ordering by count alone left ties to
            # whatever order the engine produced, so the same data
            # stored differently aggregated differently. With a LIMIT
            # under it that does not merely reorder the list, it decides
            # which value a reader sees at all - and this repo is seeded
            # so that regenerating and diffing is a real correctness
            # check, which a query answering differently for the same
            # data quietly takes away.
            f"SELECT CAST({column} AS VARCHAR) AS v, COUNT(*) AS n FROM {table} WHERE {invalid_condition} "
            f"GROUP BY v ORDER BY n DESC, v LIMIT {AGGREGATE_VALUE_CAP}",
            params,
        ).fetchall()
        values = [{"value": v if v is not None else "(null)", "count": n} for v, n in rows]
    return {"type": "categorical", "suppressed": suppressed, "total_invalid": total, "values": values}


def numeric_date_aggregate(conn: duckdb.DuckDBPyConnection, table: str, column: str, invalid_condition: str,
                            classification: str | None, params: list | None = None,
                            n_bins: int = HISTOGRAM_BINS) -> dict:
    """min/max + distinct failing values + a binned histogram, for a
    numeric/date range check. Same `invalid_condition`/`params` contract
    as categorical_aggregate."""
    params = list(params or [])
    total = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {invalid_condition}", params).fetchone()[0]
    suppressed = classification is not None
    out = {"type": "numeric_date", "suppressed": suppressed, "total_invalid": total,
           "min": None, "max": None, "values": [], "histogram": []}
    if suppressed or not total:
        return out

    rows = conn.execute(
        f"SELECT {column} AS v, COUNT(*) AS n FROM {table} WHERE {invalid_condition} GROUP BY v ORDER BY v",
        params,
    ).fetchall()
    lo, hi = rows[0][0], rows[-1][0]
    out["min"] = str(lo)
    out["max"] = str(hi)
    out["values"] = [{"value": str(v), "count": n} for v, n in sorted(rows, key=lambda r: -r[1])[:AGGREGATE_VALUE_CAP]]
    out["histogram"] = _bin_dates(rows, lo, hi, n_bins)
    return out


def _bin_dates(rows: list[tuple], lo, hi, n_bins: int) -> list[dict]:
    if lo == hi:
        return [{"bucket": str(lo), "count": sum(n for _, n in rows)}]
    span_days = (hi - lo).days
    bin_days = max(1, span_days / n_bins)
    buckets = [0] * n_bins
    for v, n in rows:
        idx = min(n_bins - 1, int((v - lo).days / bin_days))
        buckets[idx] += n
    out = []
    for i, count in enumerate(buckets):
        if count == 0:
            continue
        start = lo + timedelta(days=int(i * bin_days))
        end = hi if i == n_bins - 1 else lo + timedelta(days=int((i + 1) * bin_days))
        label = start.isoformat() if start == end else f"{start.isoformat()} to {end.isoformat()}"
        out.append({"bucket": label, "count": count})
    return out
