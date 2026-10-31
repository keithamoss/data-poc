"""Which file, staged table, period and staging key a supply is
(REQ-PIPE-193 criterion 13) - the ONE resolver.

WHY ONE. Until a contested pair could be settled, a supply's id key, its
receipt, its staging key and its staged table all derived from ONE value
- the arrival key - so every path could take any of them from any other:
split the `#` off an id, take the key from a receipt instant, read `#N`
as the table's `__N`. A settlement makes them diverge (architect,
2026-10-13): the file settled as `#1` may be staged as `__2`, and a `#2`
filed on its own later receipt has a receipt instant whose key names no
table at all. Left to each path, a settled supply reads as contested and
is never checked. So every path asks here, and nothing else splits a
supply id or maps an ordinal to a table.

WHAT A SUPPLY RESOLVES TO:
  - an ordinary supply: its one staged table, `<table>__<key>`;
  - an OPEN pair's `#1`: BOTH of its tables (that is what makes it
    contested);
  - a SETTLED pair's supply: the one table of the file qa.decision_file
    says it is - or NONE, where the load refused that file;
  - its period: its current filing (qa.filing_current), never a lookup
    by receipt instant or arrival key.

FILE ORDER IS STATED ONCE (the requirement's NFR): a pair's staged
ordinals are the byte order the stager sorted the filenames in
(supply_db.expected_tables), reproduced here in Python - never a
database collation, which on CI's en_US.utf8 can put `-resend` and `.`
in a different order.

RECORDED METADATA ONLY: qa.filing, qa.delivery_file, qa.decision_file,
qa.decision and the load record. Never a schema holding supply rows.
"""
from __future__ import annotations

from dataclasses import dataclass

from qa_tools.common import qa_store, supply_db

_QA = f'"{qa_store.SCHEMA}"'


@dataclass(frozen=True)
class Supply:
    dataset_id: str
    supply_id: str
    #: The arrival key its staged tables carry - the key in its id.
    staging_key: str
    #: The staged physical names it owns, in staging form (`<table>__<key>`
    #: or `<table>__<key>__<n>`) - wherever they have since been moved. Empty
    #: for a file the load refused; both of an open pair's for its `#1`.
    tables: tuple[str, ...]
    #: The period it is filed to now, or None (held, or not filed).
    period: str | None
    delivery: str | None
    #: The file it is, where it is one file: always for an ordinary supply
    #: and a settled one; None for an open pair's `#1`.
    filename: str | None
    #: Whether a settlement (qa.decision_file) says which file it is.
    settled: bool
    #: Every staged name its file(s) took, a refused one included - so a
    #: caller can say "the load refused it" rather than "it has no table".
    own: tuple[str, ...] = ()

    @property
    def refused(self) -> tuple[str, ...]:
        """Its staged names the load refused."""
        return tuple(t for t in self.own if t not in self.tables)

    @property
    def is_pair(self) -> bool:
        """Two (or more) files claim it, and nothing says which it is - an
        open pair's `#1`, or one a later arrival superseded unsettled."""
        return not self.settled and len(self.own) > 1


def dataset_of(supply_id: str) -> str:
    """The dataset a supply id names - the part before `@`."""
    return supply_id.partition("@")[0]


def staging_key_of(supply_id: str) -> str:
    """The arrival key a supply id carries - THE ONE PLACE a supply id is
    split (the requirement's mechanical-enumeration NFR)."""
    text = supply_id or ""
    return text.rsplit("@", 1)[-1].split("#", 1)[0] if "@" in text else ""


def ordinal_of(supply_id: str) -> str:
    """The `#N` a supply id carries, or ''. An IDENTITY, never a table's
    ordinal: a settled `#1` may be staged as `__2`."""
    text = supply_id or ""
    return text.rsplit("@", 1)[-1].partition("#")[2] if "@" in text else ""


def arrival_of(supply_id: str) -> str:
    """`<dataset>@<key>` - the arrival a supply came in, shared by a pair's
    two supplies. For grouping by arrival; never a supply id of its own
    for a pair."""
    dataset, _, _key = (supply_id or "").rpartition("@")
    return f"{dataset}@{staging_key_of(supply_id)}" if dataset else (supply_id or "")


def pair_supply(supply_id: str) -> str:
    """The `#1` id a pair is filed under, from either of its supply ids."""
    dataset, _, key = (supply_id or "").rpartition("@")
    return f"{dataset}@{key.split('#', 1)[0]}#1"


def files_in_order(conn, dataset_id: str, delivery: str) -> list[str]:
    """This dataset's files in the delivery, in STAGED ORDINAL order - the
    byte order supply_db.expected_tables() staged them in (`sorted()`),
    never a database collation."""
    rows = conn.execute(
        f"SELECT filename FROM {_QA}.delivery_file WHERE delivery = ? AND dataset_id = ?",
        [delivery, dataset_id]).fetchall()
    return sorted(r[0] for r in rows)


def staged_name(logical: str, key: str, files: list[str], filename: str) -> str:
    """The staged table one file of a delivery took."""
    if len(files) <= 1:
        return f"{logical}__{key}"
    return f"{logical}__{key}__{files.index(filename) + 1}"


def settlement_of(conn, dataset_id: str, supply_id: str) -> dict | None:
    """The newest settlement row naming this supply: {decision_id,
    filename, outcome, to_slot, effective_at} - or None."""
    rows = conn.execute(
        "SELECT x.decision_id, x.filename, x.outcome, x.to_slot, d.effective_at "
        f"FROM {_QA}.decision_file x JOIN {_QA}.decision d ON d.id = x.decision_id "
        "WHERE d.dataset_id = ? AND x.supply_id = ? "
        "ORDER BY d.effective_at DESC, d.id DESC LIMIT 1",
        [dataset_id, supply_id]).fetchall()
    if not rows:
        return None
    decision_id, filename, outcome, to_slot, effective_at = rows[0]
    return {"decision_id": decision_id, "filename": filename, "outcome": outcome,
            "to_slot": to_slot, "effective_at": effective_at}


def _refused(conn, dataset_id: str, physicals) -> frozenset[str]:
    """Which of these tables' CURRENT load record says the load failed -
    one indexed row each (load_log.latest_for), never the whole log: this
    is asked per supply on the overlay's hot path."""
    from qa_tools.common import load_log

    out = set()
    for physical in physicals:
        record = load_log.latest_for(physical, conn=conn)
        if record is not None and not record.loaded and record.dataset_id == dataset_id:
            out.add(physical)
    return frozenset(out)


def resolve(conn, dataset_id: str, supply_id: str) -> Supply | None:
    """What this supply is. A supply never FILED (staged by hand, or one a
    decision names before any filing) has no period and no delivery, and is
    its one plain staged table - a pair's file cannot be told apart without
    the delivery, so an unfiled `#N` resolves to nothing. None only for a
    string that is not a supply id."""
    from qa_tools.common import filing, hierarchy

    if "@" not in (supply_id or ""):
        return None
    rows = conn.execute(
        f"SELECT slot, delivery FROM {filing.CURRENT} WHERE dataset_id = ? AND supply_id = ?",
        [dataset_id, supply_id]).fetchall()
    period, delivery = rows[0] if rows else (None, None)
    key = staging_key_of(supply_id)
    try:
        logical = hierarchy.dataset(dataset_id).table
    except hierarchy.UnknownDatasetError:
        logical = dataset_id
    files = files_in_order(conn, dataset_id, delivery) if delivery else []
    settled = settlement_of(conn, dataset_id, supply_id)
    if settled is not None:
        chosen = settled["filename"]
        own = (staged_name(logical, key, files, chosen),) if chosen in files else ()
        refused = _refused(conn, dataset_id, own)
        return Supply(dataset_id, supply_id, key, tuple(t for t in own if t not in refused),
                      period, delivery, chosen, True, own)
    if len(files) > 1:
        # AN OPEN (or never-settled) PAIR: its `#1` owns both files.
        own = tuple(staged_name(logical, key, files, f) for f in files)
        refused = _refused(conn, dataset_id, own)
        return Supply(dataset_id, supply_id, key, tuple(t for t in own if t not in refused),
                      period, delivery, None, False, own)
    filename = files[0] if files else None
    if not files and ordinal_of(supply_id):
        return Supply(dataset_id, supply_id, key, (), period, delivery, None, False, ())
    own = (f"{logical}__{key}",)
    refused = _refused(conn, dataset_id, own)
    return Supply(dataset_id, supply_id, key, tuple(t for t in own if t not in refused),
                  period, delivery, filename, False, own)


def supply_for_table(conn, dataset_id: str, physical: str) -> str | None:
    """The supply a staged table belongs to - the reverse of resolve(): a
    settled pair's `__2` may be its `#1`. None where no filed supply of
    this dataset owns it."""
    parts = supply_db.split_staged(physical)
    if not parts:
        return None
    key = parts[1]
    rows = conn.execute(
        f"SELECT supply_id FROM {_QA}.filing_current WHERE dataset_id = ? AND "
        "(supply_id = ? OR supply_id LIKE ?)",
        [dataset_id, f"{dataset_id}@{key}", f"{dataset_id}@{key}#%"]).fetchall()
    for (supply_id,) in sorted(rows):
        found = resolve(conn, dataset_id, supply_id)
        if found and physical in found.own:
            return supply_id
    # NOT FILED (yet): a plain staged name is its arrival's one supply; a
    # pair's file cannot be told apart without its filing and delivery.
    return None if parts[2] else f"{dataset_id}@{key}"


def run_id_of(dataset_id: str, supply_id: str) -> str:
    """The run id an arrival - or, for a settled pair's supply, its first
    own run - is named from: `<table>__<key>`, with `__<N>` for a pair's
    `#N`. AN IDENTITY FOR THE SUPPLY'S RUNS ALONE (criterion 14), never a
    way to find its table - resolve() is."""
    from qa_tools.common import hierarchy

    logical = hierarchy.dataset(dataset_id).table
    ordinal = ordinal_of(supply_id)
    return f"{logical}__{staging_key_of(supply_id)}" + (f"__{ordinal}" if ordinal else "")


def arrival_run_id_of(dataset_id: str, supply_id: str) -> str:
    """The run the supply's ARRIVAL recorded - one per arrival, so a pair's
    two supplies share it (it is the 'could not run' run) and its run_index
    is the one their own runs carry (criterion 14)."""
    from qa_tools.common import hierarchy

    return f"{hierarchy.dataset(dataset_id).table}__{staging_key_of(supply_id)}"


#: WHERE A PAIR IS SETTLED - THE ONE COPY of the TUI path (REQ-PIPE-193
#: NFR, REQ-PIPE-194 criterion 1): every refusal, item and ticket comment
#: that sends a person to settle a pair fills this, and a test asserts no
#: second copy exists. The TUI drives it (Keith, 2026-10-13), so it names
#: a place, never a command to paste.
#: Every step a menu label as shown (Keith, 2026-10-13, #170) - the
#: collection by its name, as the picker lists it.
SETTLE_AT = "mothman > Filing decisions > {collection} > Supplies waiting on a decision"


def where_to_settle(dataset_id: str) -> str:
    """SETTLE_AT for this dataset's collection, BY THE LABEL THE FILING MENU
    LISTS IT UNDER (Keith, 2026-10-18: one rule for a collection's label in
    every picker) - a one-table collection by its dataset's name. It named
    the collection's own name, which that menu no longer shows."""
    from qa_tools import collections
    from qa_tools.common import hierarchy

    try:
        collection = collections.by_id(hierarchy.dataset(dataset_id).collection_id).label
    except (hierarchy.UnknownDatasetError, KeyError, LookupError):
        collection = dataset_id
    return SETTLE_AT.format(collection=collection)


def open_contest(conn, dataset_id: str, supply_id: str):
    """The pair's contest where it is still OPEN, else None - by
    dataset_blockers' one judgement (REQ-PIPE-194 criteria 8 and 9), never
    by the shape of the supply id."""
    from qa_tools.common import dataset_blockers

    pair = pair_supply(supply_id)
    for blocker in dataset_blockers.contests(conn):
        if blocker.dataset_id == dataset_id and blocker.supply == pair and blocker.is_open:
            return blocker
    return None


def tables_in(conn, dataset_id: str, supply_id: str, schema: str) -> list[str]:
    """This supply's own staged tables that are in `schema` now - what a
    decision moving it out of staging, a superseded schema or the rejected
    schema moves. Never its pair's other file (criterion 13)."""
    found = resolve(conn, dataset_id, supply_id)
    if found is None or not found.tables:
        return []
    present = {r[0] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = ? "
        "AND table_name = ANY(?)", [schema, list(found.tables)]).fetchall()}
    return [t for t in found.tables if t in present]
