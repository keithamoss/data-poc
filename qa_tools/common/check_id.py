"""
The check_id grammar, defined once (REQ-QAC-023).

A check_id names a check globally, and until now its shape lived only in
prose - `plans/publishing-and-history.md` Thread D describes it, and
every reader that needed a piece of one took that piece by ad hoc string
splitting. That is the same failure mode this requirement exists to
remove elsewhere: a structure that is real but never stated, so nothing
can check it and every consumer re-derives it slightly differently.

This module PARSES AND VALIDATES ONLY. It deliberately does not build
check_ids, and that was a decision rather than an omission: 254 of them
are authored by hand in YAML where a Python constructor cannot help,
against 3 in production Python. Correctness everywhere comes from
validating what was written, not from a constructor serving 1% of cases.

    data-asset-1.registry-services.birth-registrations
        .stg_birth_registrations.registration_number.unique_dbt
    |__________| |_____________| |___________________|
     data_asset       agency            dataset
                  |______________________| |_________________| |________|
                           table                  column          check

`column` is optional - a genuinely table-level check (a row count) has
none. Nothing else is.

KNOWN GAP, stated rather than hidden: there is no `collection` segment,
while a dashboard URL is /agency/X/collection/Y/dataset/Z. The
identifier skips a level the rest of the system models, so a check's
collection cannot be derived from its own id. Resolving that is the
first piece of work under `plans/publishing-and-history.md` item 6 and
may change this grammar - which is why `_SEGMENTS` below is a list the
pattern is BUILT from, not a hand-written regex. Adding a segment is one
edit there, and every consumer follows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# The grammar, in order. `optional=True` marks a segment a check may
# legitimately omit. Adding `collection` here (see the KNOWN GAP above)
# is the single edit that changes the grammar everywhere.
_SEGMENTS: tuple[tuple[str, bool], ...] = (
    ("data_asset", False),
    ("agency", False),
    ("dataset", False),
    ("table", False),
    ("column", True),
)

# Every segment is word characters and hyphens - never a dot, which is
# what makes the grammar parseable at all.
_SEGMENT = r"[A-Za-z0-9_-]+"

# The four real tools. The trailing segment is `<name>_<tool>`, and
# anchoring on the tool suffix is what disambiguates a 5-segment id
# (no column) from a 6-segment one without counting dots.
TOOLS = ("dbt", "soda", "datacontract", "evidently")

def _build_pattern() -> re.Pattern[str]:
    """Builds the grammar's regex from `_SEGMENTS`, so the segment list
    above is the single definition and this is only its mechanical
    consequence. Hand-writing the regex instead would mean two places to
    keep in step, which is the shape of bug this whole requirement is
    about."""
    parts = []
    for i, (name, optional) in enumerate(_SEGMENTS):
        group = f"(?P<{name}>{_SEGMENT})"
        if optional:
            parts.append(f"(?:\\.{group})?")
        else:
            parts.append(group if i == 0 else f"\\.{group}")
    tail = rf"\.(?P<check_name>{_SEGMENT})_(?P<tool>{'|'.join(TOOLS)})"
    return re.compile("^" + "".join(parts) + tail + "$")


_PATTERN = _build_pattern()

SEGMENT_NAMES: tuple[str, ...] = tuple(name for name, _ in _SEGMENTS) + ("check_name", "tool")


class InvalidCheckIdError(ValueError):
    """A check_id that does not match the grammar. Always names the
    offending id - a validation error a reader cannot act on is barely
    better than none."""


@dataclass(frozen=True)
class CheckId:
    """One parsed check_id. `column` is None for a table-level check."""

    check_id: str
    data_asset: str
    agency: str
    dataset: str
    table: str
    column: str | None
    check_name: str
    tool: str

    @property
    def tail(self) -> str:
        """The final segment, `<check_name>_<tool>`.

        This is what a dashboard URL keys a check on, and it carries no
        table segment - which is why `validate_tail_uniqueness()` exists
        as its own rule rather than being assumed to follow from global
        check_id uniqueness. See that function."""
        return f"{self.check_name}_{self.tool}"


def parse(check_id: str) -> CheckId:
    """Parses a check_id, or raises InvalidCheckIdError naming it.

    Every consumer that needs one piece of a check_id goes through here
    rather than splitting on dots and indexing, so there is exactly one
    place that knows the shape."""
    m = _PATTERN.match(check_id or "")
    if not m:
        raise InvalidCheckIdError(
            f"check_id {check_id!r} does not match the grammar "
            f"<{'>.<'.join(n for n, _ in _SEGMENTS)}>.<check_name>_<tool> "
            f"(column optional; tool one of {', '.join(TOOLS)})")
    g = m.groupdict()
    return CheckId(check_id=check_id, **{k: g[k] for k in SEGMENT_NAMES})


def try_parse(check_id: str) -> CheckId | None:
    """`parse()` for callers that want to skip rather than fail - used by
    the validator, which reports EVERY bad id rather than stopping at the
    first."""
    try:
        return parse(check_id)
    except InvalidCheckIdError:
        return None


def validate_grammar(check_ids) -> list[str]:
    """Every check_id that does not match the grammar, as error strings.

    Returns all of them rather than raising on the first - someone fixing
    a batch of hand-authored YAML wants the whole list, not one at a
    time."""
    errors = []
    for cid in check_ids:
        try:
            parse(cid)
        except InvalidCheckIdError as e:
            errors.append(str(e))
    return errors


def validate_column_matches(attachments) -> list[str]:
    """`attachments` is an iterable of `(check_id, column_or_None)` - the
    column the rule is ACTUALLY attached to in its source file.

    A check_id names a column; the rule sits under a column in the
    contract's schema. Nothing kept those two honest, and the whole point
    of this requirement is that a check's column comes from structure
    rather than from prose - so a check_id claiming a different column
    from the one it is attached to is a real error, not a cosmetic one.
    A reader trusting the id would be sent to the wrong place."""
    errors = []
    for cid, attached_column in attachments:
        parsed = try_parse(cid)
        if parsed is None:
            continue  # already reported by validate_grammar
        if attached_column is None or parsed.column is None:
            continue  # table-level either side - nothing to disagree about
        if parsed.column != attached_column:
            errors.append(
                f"check_id {cid!r} names column {parsed.column!r} but its rule is "
                f"attached to column {attached_column!r}")
    return errors


def validate_tail_uniqueness(check_ids) -> list[str]:
    """Two checks on the same dataset and column must not share a tail.

    This does NOT follow from global check_id uniqueness, which is why it
    is stated directly. Two checks could differ only in their `table`
    segment, be globally unique, and still collide in a dashboard URL -
    which carries agency, collection, dataset and column but no table,
    keying the check on its tail alone. Whichever the lookup found first
    would win, silently, which is precisely the class of failure this
    requirement exists to remove.

    It cannot happen today only because every dataset maps to exactly one
    table, and nothing enforces that - so the guarantee is stated here
    rather than inherited from a coincidence of the current data model.
    A collision is a hard failure at authoring time, deliberately, not a
    fallback to the full check_id for the colliding check: that would put
    two URL shapes on one page and hide the problem instead of fixing
    it."""
    by_key: dict[tuple, list[str]] = {}
    for cid in check_ids:
        parsed = try_parse(cid)
        if parsed is None:
            continue
        key = (parsed.data_asset, parsed.agency, parsed.dataset, parsed.column, parsed.tail)
        by_key.setdefault(key, []).append(cid)
    errors = []
    # `column` is None for a table-level check, so sort on a coerced
    # key rather than the raw tuple - str and None do not compare.
    for (_, _, dataset, column, tail), ids in sorted(
            by_key.items(), key=lambda kv: tuple(x or "" for x in kv[0])):
        if len(ids) > 1:
            errors.append(
                f"{len(ids)} checks on dataset {dataset!r} column {column!r} share the "
                f"final check_id segment {tail!r}, which is what a dashboard URL keys on: "
                + ", ".join(sorted(ids)))
    return errors
