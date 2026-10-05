"""The census: the decision log and the warehouse compared (REQ-PIPE-081
criteria 12 to 16).

WHY IT STAYS NOW THEY SHARE A DATABASE: the log and the warehouse can
disagree, and one database does not make them agree. A promotion whose
table was later dropped or moved by hand is exactly what this finds -
REQ-PIPE-091's one-transaction rule keeps the log honest about a promotion
that failed, not about anything done afterwards.

ONLY DISCREPANCIES ARE KEPT (criterion 12), normally none - an inventory of
what is present would be a second copy of the catalogue that nobody reads.
A census row records that one was taken, so "none found" is a recorded
answer rather than the absence of one.

TAKEN WHERE A CONNECTION IS LEGITIMATELY OPEN - after a QA run, and after
every decision that moves a table (criterion 13) - and never by the
dashboard build, which reads the recorded answer (criterion 14) and warns
on it without failing (criterion 16).

Three kinds:
  missing     the log says a period holds a table or view; the warehouse
              holds nothing by that name there
  wrong-kind  the log says promoted and the period holds a view, or says
              substituted/inherited and it holds a table
  stray       the period holds a table or view that no decision put there
"""
from __future__ import annotations

from dataclasses import dataclass

from qa_tools.common import period_schema, qa_store, supply_db

MISSING, WRONG_KIND, STRAY = "missing", "wrong-kind", "stray"

#: What a slot's held_as says the period holds for that table.
_EXPECTED_TYPE = {"promoted": "BASE TABLE", "substituted": "VIEW", "inherited": "VIEW"}


@dataclass(frozen=True)
class Discrepancy:
    kind: str
    period: str
    dataset_id: str | None
    table_name: str
    supply: str | None
    detail: str

    def as_record(self) -> dict:
        return {"kind": self.kind, "period": self.period, "datasetId": self.dataset_id,
                "table": self.table_name, "supply": self.supply, "detail": self.detail}


def compare(conn: supply_db.SupplyConnection,
            periods: list[str] | None = None) -> list[Discrepancy]:
    """What the log names against what the warehouse holds, now. Scoped to
    `periods` where given, else every period."""
    from qa_tools.common import hierarchy

    expected: dict[tuple[str, str], tuple[str, str, str, str | None]] = {}
    for dataset_id, slot, held_as, holder in conn.execute(
            f'SELECT dataset_id, slot, held_as, holder FROM "{qa_store.SCHEMA}".slot_holds_now '
            "WHERE held_as IS NOT NULL").fetchall():
        if periods is not None and slot not in periods:
            continue
        try:
            table = hierarchy.dataset(dataset_id).table
        except Exception:  # noqa: BLE001 - a dataset the tree no longer knows
            continue
        expected[(period_schema.period_schema(slot), table)] = (slot, dataset_id, held_as,
                                                                holder)

    schemas = ({period_schema.period_schema(p) for p in periods} if periods is not None
               else None)
    actual: dict[tuple[str, str], str] = {}
    for schema, name, kind in conn.execute(
            "SELECT table_schema, table_name, table_type FROM information_schema.tables "
            "WHERE table_schema LIKE 'period\\_%' "
            "AND table_schema NOT LIKE '%\\_superseded'").fetchall():
        if schemas is not None and schema not in schemas:
            continue
        actual[(schema, name)] = kind

    out: list[Discrepancy] = []
    for (schema, table), (slot, dataset_id, held_as, holder) in sorted(expected.items()):
        found = actual.get((schema, table))
        want = _EXPECTED_TYPE.get(held_as)
        if found is None:
            out.append(Discrepancy(
                MISSING, slot, dataset_id, table, holder,
                f"the decision log says {slot} holds {table} ({held_as}, {holder}); "
                f"{schema} has nothing by that name"))
        elif want and found != want:
            out.append(Discrepancy(
                WRONG_KIND, slot, dataset_id, table, holder,
                f"the decision log says {slot}'s {table} is {held_as}; {schema} holds a "
                f"{found.lower()}"))
    slot_of_schema = {schema: slot for (schema, _t), (slot, *_rest) in expected.items()}
    for (schema, name), kind in sorted(actual.items()):
        if (schema, name) in expected:
            continue
        period = slot_of_schema.get(schema) or period_schema.period_of(schema) or schema
        try:
            owner = hierarchy.dataset_for_table(name).dataset_id
        except Exception:  # noqa: BLE001 - a table no dataset claims
            owner = None
        out.append(Discrepancy(
            STRAY, period, owner, name, None,
            f"{schema}.{name} ({kind.lower()}) is there, and no decision put it there"))
    return out


def take(conn: supply_db.SupplyConnection, *, trigger: str, run_key: str | None = None,
         periods: list[str] | None = None) -> int | None:
    """Compare and record (criteria 12 and 13). Returns the census id, or
    None where it was not taken.

    NOT INSIDE ANOTHER TRANSACTION: a move half-way through one - a
    supersession before its promotion - is not a state anybody should be
    told about. The caller that owns that transaction takes it after."""
    import psycopg

    if conn.raw.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
        return None
    qa_store.ensure_schema(conn)
    # ONE SNAPSHOT (#113): the log and the catalogue are read in one
    # REPEATABLE READ transaction, so a decision committing between the two
    # reads is not reported as a discrepancy it never was.
    with conn.raw.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        found = compare(conn, periods)
        census_id = conn.execute(
            f'INSERT INTO "{qa_store.SCHEMA}".census (trigger, run_key, periods) '
            "VALUES (?, ?, ?) RETURNING id", [trigger, run_key, periods]).fetchall()[0][0]
        for d in found:
            conn.execute(
                f'INSERT INTO "{qa_store.SCHEMA}".census_discrepancy '
                "(census_id, kind, period, dataset_id, table_name, supply, detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [census_id, d.kind, d.period, d.dataset_id, d.table_name, d.supply,
                 d.detail])
    return int(census_id)


def after_move(conn, *, trigger: str, period: str | None) -> None:
    """A decision that moved a table is checked when it is taken (criterion
    13). Never raises: the decision is already recorded, and a census that
    could not be taken is no reason to report it as failed."""
    if not period:
        return
    try:
        take(conn, trigger=trigger, periods=[period])
    except Exception as exc:  # noqa: BLE001 - see the docstring
        print(f"note: the census after this {trigger} could not be taken "
              f"({type(exc).__name__}: {exc}).")


def change_points(conn) -> list[dict]:
    """Every census whose findings differ from the one before it, oldest
    first - what an "as at T" reader needs (criterion 14) without one entry
    per decision. Each carries its discrepancies.

    A SCOPED CENSUS ANSWERS FOR ITS OWN PERIODS ONLY, so the standing set
    is folded forward: a census of one period replaces what was known
    about that period and leaves the rest as they were."""
    rows = conn.execute(
        f'SELECT c.id, c.taken_at, c.periods FROM "{qa_store.SCHEMA}".census c '
        "ORDER BY c.taken_at, c.id").fetchall()
    found: dict[int, list[dict]] = {}
    for census_id, kind, period, dataset_id, table, supply, detail in conn.execute(
            "SELECT census_id, kind, period, dataset_id, table_name, supply, detail "
            f'FROM "{qa_store.SCHEMA}".census_discrepancy ORDER BY census_id, period, '
            "table_name").fetchall():
        found.setdefault(census_id, []).append(
            {"kind": kind, "period": period, "datasetId": dataset_id, "table": table,
             "supply": supply, "detail": detail})
    standing: dict[str, list[dict]] = {}
    out: list[dict] = []
    previous = None
    for census_id, taken_at, periods in rows:
        mine = found.get(census_id, [])
        if periods is None:
            standing = {}
            for d in mine:
                standing.setdefault(d["period"], []).append(d)
        else:
            for p in periods:
                standing.pop(p, None)
            # A stray's period is the schema's normalised name, so it is
            # folded under that rather than the authored one.
            for p in {period_schema.period_of(period_schema.period_schema(x)) for x in periods}:
                standing.pop(p, None)
            for d in mine:
                standing.setdefault(d["period"], []).append(d)
        now = sorted((d for ds in standing.values() for d in ds),
                     key=lambda d: (d["period"], d["table"], d["kind"]))
        if now != previous:
            out.append({"takenAt": taken_at.isoformat(), "discrepancies": now})
            previous = now
    return out


def for_datasets(dataset_ids: set[str]) -> list[dict]:
    """The change points as one collection's page sees them - its own
    datasets' findings, plus any no dataset owns (criterion 15). Read from
    the RECORDED census through a read-only connection; never raises - a
    census that cannot be read is said, and the build still publishes."""
    try:
        with supply_db.connect(read_only=True, label="mothman:census-read") as conn:
            if not conn.execute(
                    f"SELECT to_regclass('{qa_store.SCHEMA}.census')").fetchall()[0][0]:
                return []
            points = change_points(conn)
    except Exception as exc:  # noqa: BLE001 - see the docstring
        print(f"note: the census could not be read ({type(exc).__name__}: {exc}).")
        return []
    out, previous = [], None
    for p in points:
        mine = [d for d in p["discrepancies"]
                if d["datasetId"] is None or d["datasetId"] in dataset_ids]
        if mine != previous:
            out.append({"takenAt": p["takenAt"], "discrepancies": mine})
            previous = mine
    return out


def build_warnings() -> list[str]:
    """The dashboard build's WARNING lines (criterion 16), asset-wide, from
    the recorded census - one call on every build path."""
    from qa_tools.common import hierarchy

    return warn(for_datasets({d.dataset_id for d in hierarchy.all_datasets()}))


def warn(points: list[dict]) -> list[str]:
    """The build's WARNING lines for the latest census (criterion 16) -
    the build still publishes."""
    if not points or not points[-1]["discrepancies"]:
        return []
    return [f"warning: census {points[-1]['takenAt']}: {d['detail']}"
            for d in points[-1]["discrepancies"]]
