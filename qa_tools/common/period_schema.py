"""One period's schema, with the staged delivery overlaid
(REQ-PIPE-035).

ONE PERIOD, NEVER A COMPOSITION ACROSS PERIODS. The original design
assembled a warehouse from every table's current version wherever it
lived; plans/supply-model.md Thread J killed that, and what survives is
much smaller - pick the newest version WITHIN one period. Red-for-unrun
is what made cross-period assembly unnecessary: a cross-table check
only runs when every participating table has a filled slot for the
period, so the query reads ONE schema, and carry-forward was the only
reason to reach into another.

THE PERIOD IS NEVER READ FROM A FILE, and that is what dissolves the
question of how a mixed-period delivery is even recognised. Thread B
rejected deriving a period from content as circular - it would infer
the filing decision from the very data whose correctness is about to be
tested, so a bad extract files itself wrongly and is then QA'd against
the wrong period, failing silently. The period comes from arrival time
plus PER-DATASET slot state, so a mixed-period delivery arises with
nothing read from any file: two tables land at the same instant and
claim different periods because their slots were in different states.

A MIXED-PERIOD DELIVERY FANS OUT (criterion 2), one QA run per period,
rather than composing tables from different periods into one run.
Keith's own first instinct was table-by-table composition, picking a
different underlying period schema per table; he changed to fan-out on
the argument that the composed run produces a meaningless comparison -
a cross-table check reading August's clients against November's
notifications. His words: "we don't want to be munging things across
period schemas."

ONE SCHEMA PER PERIOD HOLDS THE WHOLE DATA ASSET (criterion 5), across
agencies and collections, so a cross-agency check is an ordinary
same-schema query rather than an assembly step. Rejected fencing per
collection, which would have covered every cross-table check that
exists today and kept the sensitive surface smallest - a cross-agency
check is arguably the point of a multi-agency data asset. Said plainly
because it is the most sensitive artefact this design creates: in a
real deployment one period schema holds Birth Registrations and Child
Protection records side by side. Today the data is synthetic.

NOTHING PROMOTES YET. Only a promotion puts a table in a period schema,
and promotion is the promotion sprint's. So every period schema is
empty today and the overlay resolves entirely from staging - which is
the CORRECT behaviour rather than a stub, and is exactly what an
unpromoted asset should look like. The mechanism is built against the
real rule so it lights up on its own.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from qa_tools.common import supply_db

#: A period schema carries this prefix so it is distinguishable from
#: the staging, rejected and per-run schemas by name alone - the same
#: reasoning RUN_SCHEMA_PREFIX has, and it matters more here because
#: these are the DURABLE ones: an orphan run schema is untidy, and a
#: mistaken write into a period schema is promoted data nobody decided
#: to promote.
PERIOD_SCHEMA_PREFIX = "period_"



class PeriodSchemaError(RuntimeError):
    """Raised where continuing would mean guessing which period
    something belongs to."""


def _encode(period_name: str) -> str:
    """Lossless, reversible, and SQL-safe.

    Every character that is not alphanumeric becomes `_<hex>_`, so
    "2026-Q3" and "2026_Q3" - two names a naive substitution would
    collapse into one schema - stay distinct. Collapsing them would
    merge two periods' promoted data with nothing to notice it.
    """
    return "".join(c if c.isalnum() else f"_{ord(c):02x}_" for c in period_name)


def _decode(encoded: str) -> str:
    return re.sub(r"_([0-9a-f]{2})_", lambda m: chr(int(m.group(1), 16)), encoded)


def period_schema(period_name: str) -> str:
    """The schema holding everything promoted into this period.

    THE EMPTY NAME IS THE ONLY ONE REFUSED, deliberately. The encoding
    above handles every other character losslessly, so a stricter rule
    here would be this module inventing a naming policy for calendars
    it does not own - and a period name is AUTHORED ("Nov-Jan window",
    "FY26/27"), so guessing which shapes are legitimate is exactly the
    kind of guess this project keeps removing. An empty name is
    different in kind: it identifies no period at all, and letting it
    through would give every nameless caller the same schema.
    """
    if not period_name:
        raise PeriodSchemaError("a period must be named - got an empty name")
    return PERIOD_SCHEMA_PREFIX + _encode(period_name)


def period_of(schema: str) -> str | None:
    """The inverse. None for a schema that is not a period schema."""
    if not schema.startswith(PERIOD_SCHEMA_PREFIX):
        return None
    return _decode(schema[len(PERIOD_SCHEMA_PREFIX):])


def ensure_period_schema(conn, period_name: str) -> str:
    """Create this period's schema if it does not exist, and return it.

    Creating one is cheap and idempotent. It is NOT promotion - an
    empty period schema says "nothing has been promoted into this
    period", which is a true and useful thing for a check to read.
    """
    schema = period_schema(period_name)
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    return schema


def period_schemas(conn) -> list[str]:
    """Every period schema in the database, by PERIOD NAME."""
    rows = conn.execute(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE ?",
        [PERIOD_SCHEMA_PREFIX + "%"]).fetchall()
    return sorted(filter(None, (period_of(r[0]) for r in rows)))


def newest(physical_names: Sequence[str]) -> str | None:
    """The newest of several versions of one logical table (criterion 4).

    A supply and its resupplies for the same period all sit in that
    period's schema, and the newest is the one that counts. Ordered by
    the ARRIVAL KEY the physical name carries, then by ordinal - not by
    the raw string, because a name without an ordinal must sort before
    the same name with one rather than lexically among them.

    Returns None for no candidates at all, which callers must treat as
    absence rather than as an error: absence is an ordinary state here
    and has its own criterion.
    """
    best, best_key = None, None
    for physical in physical_names:
        parts = supply_db.split_staged(physical)
        if parts is None:
            # A name this project did not mint. It cannot be ordered
            # against the others, so it never wins - being wrong about
            # WHICH version is read is the one outcome worth avoiding.
            continue
        _logical, arrival, ordinal = parts
        key = (arrival, ordinal or "")
        if best_key is None or key > best_key:
            best, best_key = physical, key
    return best


def promoted_in(conn, period_name: str, logical_names: Sequence[str]) -> dict[str, list[str]]:
    """Every version of these logical tables promoted into this period.

    Returns a LIST per name rather than the newest, so the caller can
    see that several versions exist. Deciding between them is
    newest()'s job and is a different question from finding them.
    """
    schema = period_schema(period_name)
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
        [schema]).fetchall()
    wanted = set(logical_names)
    found: dict[str, list[str]] = {name: [] for name in wanted}
    for (physical,) in rows:
        parts = supply_db.split_staged(physical)
        logical = parts[0] if parts else physical
        if logical in wanted:
            found[logical].append(physical)
    return found


#: Where the version a run read came from. Carried on the resolution
#: because "the candidate under test" and "a table already promoted"
#: are different claims, and a reader a year later cannot tell them
#: apart from a physical name alone.
FROM_STAGING = "staging"
FROM_PERIOD = "period"


@dataclass
class PeriodResolution:
    """What one period's QA run can read, and from where.

    Wraps supply_db.Resolution rather than replacing it, because the
    committed record's shape is REQ-PIPE-068 criterion 5's and must not
    fork: this adds the period and the per-name source, and changes
    nothing that was already recorded.
    """

    period: str
    resolution: supply_db.Resolution
    source: dict[str, str] = field(default_factory=dict)

    @property
    def run_id(self) -> str:
        return self.resolution.run_id

    @property
    def readable(self) -> list[str]:
        return self.resolution.readable

    def as_record(self) -> dict:
        record = self.resolution.as_record()
        record["period"] = self.period
        record["source"] = dict(sorted(self.source.items()))
        return record


def create_overlay_views(conn, run_id: str, period_name: str,
                          staged: Mapping[str, Sequence[str]],
                          promoted: Mapping[str, Sequence[str]] | None = None
                          ) -> PeriodResolution:
    """Build the run's view schema: this period's promoted state, with
    the staged delivery's own tables overlaid on it (criterion 3).

    A STAGED TABLE SHADOWS A PROMOTED ONE of the same name, which is
    what "the candidate under test alongside the tables already
    promoted" means: the delivery being QA'd wins for its own tables,
    and every other table the check needs is read as that period
    currently stands.

    AMBIGUITY IN STAGING IS STILL ABSENCE, and does NOT fall through to
    the promoted version. Two files claiming one logical name mean
    nobody has said which is the candidate, so the honest answer is
    that the table is unreadable for this run - falling back to the
    promoted table would silently QA the delivery against data it did
    not contain, which reads green and means nothing.
    """
    promoted = dict(promoted or {})
    schema = supply_db.run_schema(run_id)
    conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    conn.execute(f'CREATE SCHEMA "{schema}"')
    period = period_schema(period_name)

    res = supply_db.Resolution(run_id=run_id, schema=schema)
    out = PeriodResolution(period=period_name, resolution=res)

    for logical in sorted(set(staged) | set(promoted)):
        candidates = sorted(staged.get(logical) or ())
        if len(candidates) > 1:
            res.ambiguous[logical] = candidates
            continue
        if candidates:
            physical, source_schema, origin = candidates[0], supply_db.STAGING_SCHEMA, FROM_STAGING
        else:
            physical, source_schema, origin = (newest(promoted.get(logical) or ()),
                                                period, FROM_PERIOD)
            if physical is None:
                res.absent.append(logical)
                continue
        conn.execute(
            f'CREATE VIEW "{schema}"."{logical}" AS '
            f'SELECT * FROM "{source_schema}"."{physical}"')
        res.resolved[logical] = physical
        out.source[logical] = origin
    return out


# --------------------------------------------------------------------
# Red for unrun (criteria 6, 7, 8)
#
# A CHECK THAT COULD NOT RUN IS NOT A CHECK WITH NOTHING TO SAY, and
# that distinction is the whole of this section. Nodata is reserved for
# "nothing was owed" - which is why a brand-new dataset's drift checks
# are the one case that keeps it. Without that carve-out every new
# dataset starts life red on all its drift checks, which is how people
# learn to ignore a signal.
# --------------------------------------------------------------------

RED = "red"
NODATA = "nodata"

MISSING_TABLE = "missing-table"
MISSING_REFERENCE_PERIOD = "missing-reference-period"
NO_PRIOR_PERIOD = "no-prior-period"


@dataclass(frozen=True)
class Unrunnable:
    """Why a check could not be evaluated, and what that should read as.

    `names` is what the reader has to be told - the missing table or
    the missing period - because criteria 6 and 7 both ask for it BY
    NAME. A bare "could not run" sends somebody to a directory listing.
    """

    status: str
    reason: str
    names: tuple[str, ...] = ()

    def describe(self) -> str:
        listed = ", ".join(self.names)
        if self.reason == MISSING_TABLE:
            return (f"could not run - {listed} has no filled slot in this period and "
                     f"is not in the delivery under test")
        if self.reason == MISSING_REFERENCE_PERIOD:
            return (f"could not run - {listed} was owed but has no filled slot, so "
                     f"there is nothing to compare against")
        return ("no data - no prior period was ever owed for this dataset, so there "
                 "is nothing to compare against yet")


def check_readiness(depends_on: Sequence[str], resolution: PeriodResolution, *,
                     reference_period: str | None = None,
                     reference_filled: bool = False,
                     any_prior_period_owed: bool = True) -> Unrunnable | None:
    """Whether a check may be evaluated, or why not.

    Returns None where the check should run normally.

    `depends_on` is every logical table the check reads, its own
    included. PRESENCE MEANS RESOLVING TO EXACTLY ONE VERSION
    (REQ-PIPE-068 criterion 4) - a name with two candidates is absent
    here, not present, which is the hole an earlier wording left: two
    files ARE present, so read literally "not present in the staged
    delivery" would not fire and an implementer could conclude the
    table was available.

    `reference_period` is the period a temporal check compares against.
    Passing None means the check declares no temporal reference, which
    is most of them.
    """
    missing = [name for name in depends_on if name not in resolution.resolution.resolved]
    if missing:
        return Unrunnable(status=RED, reason=MISSING_TABLE, names=tuple(sorted(missing)))
    if reference_period is None:
        return None
    if reference_filled:
        return None
    # ORDER MATTERS HERE. "Never owed" has to be asked BEFORE "owed and
    # unfilled", because a brand-new dataset satisfies both readings of
    # an unfilled reference and only one of them is correct.
    if not any_prior_period_owed:
        return Unrunnable(status=NODATA, reason=NO_PRIOR_PERIOD)
    return Unrunnable(status=RED, reason=MISSING_REFERENCE_PERIOD,
                       names=(reference_period,))


def reference_view(conn, run_id: str, logical: str, reference_period: str,
                    promoted: Sequence[str]) -> str | None:
    """Expose a reference period's table to this run, as a view in the
    run's own schema (criterion 9).

    A CROSS-SCHEMA READ WITHIN THE SAME DATABASE, never a copy into a
    separate one. Both period schemas are in the one database, so this
    costs a view definition and no data movement - and a copy would
    make the comparison a snapshot of whenever the copy was taken
    rather than of the period.

    Named `<logical>__reference` so a check's own table and its
    reference cannot be confused for one another in a query somebody
    reads later.
    """
    physical = newest(promoted)
    if physical is None:
        return None
    name = f"{logical}__reference"
    conn.execute(
        f'CREATE OR REPLACE VIEW "{supply_db.run_schema(run_id)}"."{name}" AS '
        f'SELECT * FROM "{period_schema(reference_period)}"."{physical}"')
    return name


# --------------------------------------------------------------------
# Fan-out (criteria 1 and 2)
# --------------------------------------------------------------------

@dataclass(frozen=True)
class PeriodRun:
    """One QA run, over one period, for the tables of this delivery
    that claim it.

    `run_id` DERIVES FROM THE DELIVERY'S OWN RUN ID PLUS THE PERIOD,
    never from a counter over the fan-out. A positional number is
    exactly what REQ-PIPE-057 criterion 18 forbids for a run's identity,
    and the same argument applies one level down: adding a dataset to a
    delivery would renumber the other periods' runs.
    """

    run_id: str
    period: str
    tables: tuple[str, ...]
    datasets: tuple[str, ...]


def fan_out(base_run_id: str, filed: Mapping[str, str],
             table_of: Mapping[str, str]) -> list[PeriodRun]:
    """One run per period this delivery's tables claim (criterion 2).

    `filed` maps a dataset id to the period its supply was filed to.
    `table_of` maps a dataset id to its physical/logical table name.

    A DATASET WITH NO PERIOD IS NOT IN ANY RUN. That covers a held
    supply and an unfiled one alike: both are staged, neither has a
    period, and a check cannot be evaluated against a period nobody has
    chosen. Quietly folding them into the commonest period is the
    forward cascade wearing a different hat.

    THE ORDINARY CASE PRODUCES EXACTLY ONE RUN, and it is worth saying
    because it is easy to read this as always splitting: an ordinary
    six-table Child Protection delivery spans six SLOTS in ONE period,
    and that is one run. Thread H's TS-33b warning is the same trap one
    layer up - a gate keyed on slots rather than periods fires on every
    healthy multi-table delivery.
    """
    by_period: dict[str, list[str]] = {}
    for dataset_id, period in sorted(filed.items()):
        if not period:
            continue
        by_period.setdefault(period, []).append(dataset_id)

    out = []
    for period in sorted(by_period):
        datasets = tuple(by_period[period])
        tables = tuple(sorted(
            {table_of[d] for d in datasets if table_of.get(d)}))
        out.append(PeriodRun(run_id=f"{base_run_id}__{_encode(period)}",
                              period=period, tables=tables, datasets=datasets))
    return out
