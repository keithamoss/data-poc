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

    data-asset-1.registry-services.civil-registration
        .birth-registrations.registration_number.unique_dbt
    |__________| |_____________| |_________________|
     data_asset       agency         collection
                  |___________________| |_________________| |________|
                         dataset               column          check

`column` is optional - a genuinely table-level check (a row count) has
none. Nothing else is.

THE GRAMMAR CHANGED ONCE, on 2026-09-23 (REQ-QAC-039), and this is the
only time it has. Two edits, both to `_SEGMENTS`:

- `collection` was ADDED. The identifier used to skip a level the rest
  of the system models - a dashboard URL is
  /agency/X/collection/Y/dataset/Z - so a check's collection could not
  be derived from its own id.
- `table` was REMOVED, and it was worse than merely redundant: it named
  the dbt STAGING MODEL, not the table. `stg_cp_clients` is a real dbt
  model doing `select * from` the raw `cp_clients` source, following
  dbt's own naming convention - so every check carried dbt's vocabulary,
  including the Soda, datacontract-cli and Evidently checks that have no
  staging model and read the real table. One tool's implementation
  detail in an identifier meant to be tool-neutral. Dropping it is safe
  because a dataset maps to exactly one logical table BY CONSTRUCTION
  under the supply model (plans/supply-model.md Thread F), not by
  today's accident.

`data_asset` stays, deliberately, even though it has one value in any
single deployment (Keith, 2026-09-22). This repo may end up holding one
set of shared configuration files for SEVERAL data assets, which will
probably carry the same table names and some of the same checks; the
segment is what keeps a check_id globally unique across them. A future
reader looking to simplify the grammar would see a segment with one
value and remove it, and the cost of that only appears when a second
asset arrives.

Renaming 258 ids needed its own explicit exception to the 2026-09-16
rule that a check_id is permanently unique and must never change -
approved by Keith on 2026-09-22, recorded on REQ-QAC-039's own
`decisions:`, and narrow: it licenses THIS one grammar change, not a
general freedom to renumber later. Measured before it was done: zero of
the 258 config_hashes change, because all four parsers exclude the
metadata block carrying the id (dbt's `meta`, Soda's `attributes`, the
ODCS rule's `customProperties`) and Evidently's id is a dict key that
never enters its config.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# The grammar, in order. `optional=True` marks a segment a check may
# legitimately omit. This list is the single definition - the regex
# below is built from it - so a grammar change is one edit here and
# every consumer follows. That property is load-bearing, not a
# nicety: it is what made REQ-QAC-039's change above two lines rather
# than a hand-edited regex to keep in step.
_SEGMENTS: tuple[tuple[str, bool], ...] = (
    ("data_asset", False),
    ("agency", False),
    ("collection", False),
    ("dataset", False),
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
    collection: str
    dataset: str
    column: str | None
    check_name: str
    tool: str

    @property
    def tail(self) -> str:
        """The final segment, `<check_name>_<tool>`.

        This is what a dashboard URL keys a check on, and it carries
        neither the dataset nor the column - which is why
        `validate_tail_uniqueness()` exists as its own rule rather than
        being assumed to follow from global check_id uniqueness. See
        that function."""
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
    is stated directly. A dashboard URL is
    /agency/<id>/collection/<id>/dataset/<id>/column/<name>/check/<tail>,
    so it keys the check on its tail alone. Two globally-unique checks
    that agree on everything a URL carries and differ only in something
    it does not would collide there, and whichever the lookup found
    first would win, silently - precisely the class of failure this
    requirement exists to remove.

    Concretely, after REQ-QAC-039 the one way two ids can collide here
    is by differing only in `data_asset` - which a URL does not carry.
    That is not hypothetical: the whole reason that segment stays is
    that this repo may end up holding one set of shared configuration
    files for several assets, carrying the same table names and some of
    the same checks.

    The caveat this docstring used to carry is now ANSWERED rather than
    outstanding. It said the collision could not happen only because
    every dataset happens to map to exactly one table and nothing
    enforced that. The supply model enforces it: a supply IS one table
    version and a slot is one (table, period) pair, so a dataset mapping
    to two tables has no coherent slot and the model cannot express it
    (plans/supply-model.md Thread F). That is also what made dropping
    the `table` segment safe in REQ-QAC-039 rather than merely tidy -
    note the precision, a dataset is 1:1 with one LOGICAL table, which
    has many physical versions.

    A collision is a hard failure at authoring time, deliberately, not a
    fallback to the full check_id for the colliding check: that would put
    two URL shapes on one page and hide the problem instead of fixing
    it."""
    by_key: dict[tuple, list[str]] = {}
    for cid in check_ids:
        parsed = try_parse(cid)
        if parsed is None:
            continue
        # Exactly what a dashboard URL carries, and nothing else. In
        # particular NOT data_asset: the URL does not carry it (see
        # REQ-QAC-039's own decisions), so two ids differing only in
        # that segment land on the same page. Including it in the key
        # would have made this rule a restatement of global check_id
        # uniqueness the moment the table segment went, since every
        # remaining segment would then be in the key - found by a test
        # that stopped being able to construct a collision.
        key = (parsed.agency, parsed.collection, parsed.dataset, parsed.column, parsed.tail)
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


def validate_hierarchy_agreement(check_ids) -> list[str]:
    """Every check_id whose own identity disagrees with the one
    hierarchy, as error strings (REQ-QAC-039).

    Grammar validation proves an id is SHAPED right. It cannot tell you
    the id names a dataset that exists, or that the agency and
    collection it claims are the ones that dataset actually sits under -
    and an id that validates and means nothing is worse than one that
    fails, because it looks resolved. A dashboard URL built from such an
    id leads nowhere, and a result filed under it is filed under a
    fiction.

    This is the check that makes the collection segment worth carrying:
    without it the segment would be a fourth unverified copy of the
    tree, which is what REQ-QAC-039 exists to stop, only now inside the
    identifier itself.

    Reports every offender rather than the first, same as its siblings
    here - someone fixing hand-authored YAML wants the whole list.
    Imported lazily so this module stays importable without config
    present, which its own tests rely on.
    """
    from qa_tools.common import hierarchy

    errors = []
    expected_asset = hierarchy.data_asset_id()
    for cid in check_ids:
        parsed = try_parse(cid)
        if parsed is None:
            continue  # already reported by validate_grammar
        if parsed.data_asset != expected_asset:
            errors.append(
                f"check_id {cid!r} names data asset {parsed.data_asset!r}, but this "
                f"deployment is {expected_asset!r}")
        try:
            entry = hierarchy.dataset(parsed.dataset)
        except hierarchy.UnknownDatasetError as exc:
            errors.append(f"check_id {cid!r} names a dataset the hierarchy does not define - {exc}")
            continue
        for segment, actual, expected in (
                ("agency", parsed.agency, entry.agency_id),
                ("collection", parsed.collection, entry.collection_id)):
            if actual != expected:
                errors.append(
                    f"check_id {cid!r} names {segment} {actual!r}, but the hierarchy puts "
                    f"dataset {parsed.dataset!r} under {expected!r}")
    return errors
