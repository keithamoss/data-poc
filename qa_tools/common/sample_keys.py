"""What a failing-row sample records, the same in every tool (REQ-PIPE-341).

A table's sample key is an ordered list of columns, declared on its
collection's adapter (criterion 1). Every sampler - Soda's, dbt's two and
datacontract-cli's - records through this module, so the shape, the order and
the loudness are one rule rather than four:

- ONE COLUMN: the bare value as text, exactly as before; a row whose key is
  null is left out, as it always was (criterion 8), so no one-column sample
  of any collection changes.
- SEVERAL COLUMNS: an ordered list of that row's key values, each as text, a
  null part kept as null - never the text 'None' and never dropped (criteria
  2, 7 and 8 as AMENDED 2026-11-01, Keith, post-build-review #294). The page
  shows a null part as '(no value)'.
- ORDER: by the parts in key order, each compared as text by code point, a
  null part after every non-null part in its position - in Python by a sort
  key that never compares None with a string, in dbt's SQL by each column cast
  to text in the C collation with NULLS LAST (`order_by_sql`).
- LOUD: a sample that cannot be recorded as declared raises
  SampleNotRecordable, naming the check, the table and what was missing, so
  the tool's recording fails for the run rather than recording an empty
  sample (criterion 8). A check whose failure judges the whole table and names
  no row DECLARES `names_no_row: true` (a Soda attribute or a contract
  customProperty, decisions 2026-11-01) and records no sample.

Only key columns ever leave a sampler (criterion 6, plans/qa-pipeline.md #15).
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence

#: The most samples any result records - matches datacontract-cli's own
#: hardcoded _FAILED_SAMPLE_LIMIT, one cap across every tool.
FAILING_SAMPLE_LIMIT = 5


class SampleNotRecordable(RuntimeError):
    """A failing result's sample cannot be recorded as its table's key
    declares (REQ-PIPE-341 criterion 8)."""


def _text(value) -> str | None:
    return None if value is None else str(value)


def value_of(row: Mapping, columns: Sequence[str], *, check, table) -> str | list | None:
    """One row's sample: the bare text of a one-column key (None where it is
    null, which the caller leaves out), or the ordered list of every key
    column's text, null parts kept. Raises where a key column is absent."""
    if isinstance(columns, str):
        raise TypeError(f"a sample key is a list of columns, not the string {columns!r} "
                        "(REQ-PIPE-341 criterion 1)")
    missing = [c for c in columns if c not in row]
    if missing:
        raise SampleNotRecordable(
            f"check {check!r} on table {table!r}: its failing rows do not carry the "
            f"sample key column(s) {', '.join(missing)} (key: {', '.join(columns)}) - "
            f"select them in its query, or declare names_no_row: true if its failure "
            f"names no row (REQ-PIPE-341 criterion 8)")
    if len(columns) == 1:
        return _text(row[columns[0]])
    return [_text(row[c]) for c in columns]


def sort_key(sample):
    """Text by code point, a null part after every non-null one in its
    position - never comparing None with a string."""
    if isinstance(sample, list):
        return tuple((1, "") if p is None else (0, p) for p in sample)
    return ((0, sample),)


def pick(samples: Iterable, limit: int = FAILING_SAMPLE_LIMIT) -> list:
    """The samples a result records: one-column null values left out, then
    the lowest `limit` in the shared order."""
    kept = [s for s in samples if s is not None]
    return sorted(kept, key=sort_key)[:limit]


def recorded(columns: Sequence[str], samples: list) -> dict:
    """The fields a result carries: its samples, and - for a several-column
    key, on every result - the key's ordered column names, so the page lays a
    sample out without reading configuration (criterion 9)."""
    out = {"failing_sample_keys": samples}
    if len(columns) > 1:
        out["failing_sample_key_columns"] = list(columns)
    return out


def order_by_sql(columns: Sequence[str]) -> str:
    """dbt's sample ORDER BY: each column as text, C collation, nulls last."""
    return ", ".join(f'CAST({c} AS TEXT) COLLATE "C" NULLS LAST' for c in columns)


def select_sql(columns: Sequence[str]) -> str:
    """The sample's projection: a one-column key as stored (its order and text
    exactly as before), several columns each cast to text."""
    if len(columns) == 1:
        return columns[0]
    return ", ".join(f"CAST({c} AS TEXT)" for c in columns)


def names_no_row(value) -> bool:
    """A declared `names_no_row`, as YAML or a tool hands it over."""
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")
