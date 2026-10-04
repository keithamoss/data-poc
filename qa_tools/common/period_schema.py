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

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from qa_tools.common import check_id as check_id_mod
from qa_tools.common import qa_store
from qa_tools.common import hierarchy
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
    """A period name as a readable, lowercase schema suffix.

    LOWERCASE IS THE LOAD-BEARING PART (REQ-PIPE-087), and it is the
    half to keep if this is ever revisited. PostgreSQL folds an UNQUOTED
    identifier to lower case, and while this module always quotes, dbt
    and Soda write the schema name into their own SQL unquoted. A schema
    created as "period_2026_Q3" (quoted, so the Q survives) is then
    invisible to those tools, and the symptom is brutal to read back to
    a capital letter: every check in the run reporting that the relation
    does not exist.

    IT USED TO HEX-ENCODE, and that was the wrong trade (Keith,
    2026-09-27: "why don't we just rename the schemas so they're valid
    Postgres schemas? Like use underscores rather than hyphens").
    Encoding every uppercase or non-alphanumeric character kept the name
    reversible, so "2026-Q3" and "2026-q3" could not collapse into one
    schema and silently merge two periods' promoted data. That risk is
    real and the encoding was not the way to manage it: it bought
    protection against a hypothetical authoring mistake by making every
    real schema name unreadable - `period_2026_2d_51_33` is what a
    person then sees in psql, in a log, and in every error message.

    So the collision is REFUSED where the names are authored instead -
    see collisions_in(), wired into the schedule validator. A calendar
    declaring both "2026-Q3" and "2026-q3" is a config error with a
    message naming both, which is a far better outcome than two schemas
    nobody can read. `2026-Q3` is now `period_2026_q3`.
    """
    return supply_db.normalise_ident_part(period_name)


def collisions_in(period_names: Iterable[str]) -> dict[str, list[str]]:
    """Authored period names that would share one schema, keyed by that
    schema - `{}` when every name is distinct.

    THIS IS THE GUARD THAT REPLACED THE HEX ENCODING. Normalising is not
    injective: "2026-Q3", "2026 q3" and "2026_Q3" all become
    `period_2026_q3`. For a GENERATED id that is acceptable, because
    something else makes it unique; for an AUTHORED calendar it is not,
    because two periods sharing a schema means promoted data merged with
    nothing to notice.

    Refusing it here rather than encoding around it also puts the error
    where a person can fix it - in the calendar they just edited, named
    in the message - instead of at the far end of a QA run.
    """
    by_schema: dict[str, list[str]] = {}
    for name in period_names:
        by_schema.setdefault(period_schema(name), []).append(name)
    return {schema: sorted(names) for schema, names in sorted(by_schema.items())
            if len(set(names)) > 1}


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
    """This schema's period, NORMALISED - not necessarily the authored
    name. None for a schema that is not a period schema at all.

    NO LONGER AN EXACT INVERSE, said plainly because it used to be and a
    caller could reasonably assume it still is. `period_schema("2026-Q3")`
    is `period_2026_q3`, and this returns `2026_q3` - close enough to
    identify the period to a person, not the string the calendar
    declared. Whoever needs the authored name reads it from
    contract/data-asset.yaml, which is where it lives; nothing in this
    repository needed the round trip, and buying it back cost every real
    schema name its legibility (see _encode).
    """
    if not schema.startswith(PERIOD_SCHEMA_PREFIX):
        return None
    return schema[len(PERIOD_SCHEMA_PREFIX):]


def ensure_period_schema(conn, period_name: str) -> str:
    """Create this period's schema if it does not exist, and return it.

    Creating one is cheap and idempotent. It is NOT promotion - an
    empty period schema says "nothing has been promoted into this
    period", which is a true and useful thing for a check to read.
    """
    schema = period_schema(period_name)
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    return schema


def opened(conn, period_name: str) -> bool:
    """Whether this period has been recorded as opened (criterion 3).

    A FACT, NOT AN INFERENCE FROM THE SCHEMA BEING PRESENT, and that is
    the whole reason the row exists. Inheritance happens once, at the
    moment a period is born, and "does the schema exist" cannot tell a
    period opened a second ago from one opened last year whose schema
    was dropped and rebuilt - the second would inherit all over again,
    from whatever is current now rather than from what was current then.
    """
    rows = conn.execute(
        f'SELECT 1 FROM "{qa_store.SCHEMA}".period WHERE name = ?',
        [period_name]).fetchall()
    return bool(rows)


def open_period(conn, period_name: str, *, opened_by: str,
                effective_at: str | None = None) -> bool:
    """Bring a period into existence, once, and fill what it owes
    nothing for. Returns True where THIS call opened it.

    ONE MECHANISM FOR BOTH WAYS IN (REQ-PIPE-098 criterion 4). A period
    is opened by the first promotion into it or by an explicit
    instruction, and afterwards the two are indistinguishable - which is
    what makes "open next quarter early so somebody can look at it"
    safe rather than a second kind of period.

    NOT INSIDE ANOTHER TRANSACTION. Inheritance writes decision-log
    entries of its own, so callers open the period BEFORE they begin
    their own decision. promotion.promote() and substitution.substitute()
    both do.

    ensure_period_schema() REMAINS THE PLAIN, UNRECORDED CREATE, and the
    two are not the same thing: that one is idempotent scaffolding a
    view needs, this one is an event.
    """
    from qa_tools.common import asset_time, inheritance

    schema = ensure_period_schema(conn, period_name)
    if opened(conn, period_name):
        return False
    conn.execute(
        f'INSERT INTO "{qa_store.SCHEMA}".period (name, opened_by) VALUES (?, ?) '
        "ON CONFLICT (name) DO NOTHING",
        [period_name, opened_by])
    if not opened(conn, period_name):
        # Somebody else won the race. Theirs inherited; ours must not.
        return False
    inheritance.inherit_into(conn, period_name,
                              effective_at=effective_at or asset_time.now().isoformat())
    return bool(schema)


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

    AMBIGUITY IN STAGING OFFERS NOTHING, AND THE PERIOD STILL ANSWERS
    (REQ-PIPE-105 criterion 8, REQ-PIPE-079 criteria 11-13). Two files
    claiming one logical name mean nobody has said which is the
    candidate, so neither is ever chosen between, for any purpose - but
    the view still resolves to the period's PROMOTED version, because a
    contested table is in exactly the position of a table the delivery
    did not bring at all.

    THIS USED TO BE A FLAT REFUSAL, and the reason given for it was
    real: falling back to the promoted table would QA the delivery
    against data it did not contain, which reads green and means
    nothing. That is true of the contested table's OWN checks and false
    of every check that merely READS it - a referential-integrity check
    filed against placements reading carers is making a claim about the
    period's carers, and reading them is the ordinary answer. So the
    safeguard is kept where it belongs rather than across the board:
    `ambiguous` still records the contest, and contested_own_checks()
    is what stops the table's own checks running. A caller that
    resolves the view and skips that gate has the false green back.

    "STAGING" IS THIS RUN'S OWN STAGING SCHEMA, not the shared
    constant (REQ-PIPE-103). A trial stages into a schema of its own
    and never writes into shared `staging` at all, so reading the
    constant here would find none of its tables - and every one of
    them would take the fall-through above to the period's PROMOTED
    version. The trial would then report on data the operator never
    handed us while appearing to check their file: a false green in
    the dangerous direction, and silent. Nothing calls this function
    yet; the line is here so that whoever wires it up inherits the
    right behaviour instead of that bug.
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
            # Recorded, then treated as though staging brought nothing:
            # the fall-through below is the whole of criterion 12, and
            # the record is the whole of criterion 13.
            res.ambiguous[logical] = candidates
            candidates = []
        if candidates:
            physical, source_schema, origin = (
                candidates[0], supply_db.staging_schema_for(run_id), FROM_STAGING)
        else:
            versions = promoted.get(logical) or ()
            # AN INHERITED TABLE IS A VIEW NAMED JUST `logical` (REQ-PIPE-098),
            # standing on an earlier period's supply - so it carries no
            # arrival key and newest() rightly will not order it. It is
            # the period's one answer for that table, and is read as such;
            # missing it left every check reading a non-participating
            # dataset red as "missing" (2026-10-02).
            physical = newest(versions) or (logical if logical in versions else None)
            source_schema, origin = period, FROM_PERIOD
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

#: WHY a table a check reads has no promoted supply (REQ-PIPE-079
#: criteria 14, 15 and 16). All four look identical from inside a
#: check - the table is not there - and each has a different next
#: action for whoever reads the result, which is the whole reason they
#: are told apart rather than collapsed into one red.
NOT_YET_DUE = "not-yet-due"
PAST_DUE = "past-due"
STAGED_AWAITING_DECISION = "staged-awaiting-decision"
#: TWO FILES CLAIM THE TABLE and nothing is promoted to fall through to
#: (REQ-PIPE-115 criteria 14 and 15). Outranks every slot reason: the
#: supplier has sent the file - twice - so "overdue" would send somebody
#: to chase them, and "no filled slot" hides that a person must choose.
CONTESTED = "contested"
#: THE FILE ARRIVED AND COULD NOT BE LOADED (REQ-DASH-148 criterion 6) -
#: first of all: the supplier has sent it, so no slot reason is true.
COULD_NOT_LOAD = "could-not-be-loaded"


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
        if self.reason == NOT_YET_DUE:
            return (f"{listed} has not been supplied for this period yet and is "
                     f"not yet overdue")
        if self.reason == PAST_DUE:
            return f"could not run - {listed} is overdue for this period"
        if self.reason == COULD_NOT_LOAD:
            return (f"could not run - {listed} arrived and could not be loaded")
        if self.reason == CONTESTED:
            return (f"could not run - two files claim {listed} for this period, waiting "
                     f"for a person to choose one")
        if self.reason == STAGED_AWAITING_DECISION:
            return (f"could not run - a supply for {listed} is staged awaiting a "
                     f"decision, so nothing is promoted for this period yet")
        return ("no data - no prior period was ever owed for this dataset, so there "
                 "is nothing to compare against yet")


#: Most specific first. Criterion 4 defers to "the more specific cases
#: in this requirement", and where several are true at once the one
#: reported should name an action the reader can actually take: a
#: staged supply means "go and decide", where "overdue" would send them
#: to chase a supplier who has already sent it.
_MISSING_PRECEDENCE = (COULD_NOT_LOAD, CONTESTED, STAGED_AWAITING_DECISION, PAST_DUE,
                       NOT_YET_DUE)


def _why_missing(missing: Sequence[str], supply_states: dict[str, str]) -> "Unrunnable":
    """Which of REQ-PIPE-079's cases explains these absent tables.

    NOT RED FOR A SUPPLY THAT IS NOT DUE YET (criterion 14). Nothing is
    wrong in that case, and a red that fires when nothing is wrong is
    how a check earns the reputation that makes people ignore it.
    """
    for reason in _MISSING_PRECEDENCE:
        named = sorted(n for n in missing if supply_states.get(n) == reason)
        if named:
            status = NODATA if reason == NOT_YET_DUE else RED
            return Unrunnable(status=status, reason=reason, names=tuple(named))
    # Criterion 4's fallback, and every caller that knows no state.
    return Unrunnable(status=RED, reason=MISSING_TABLE, names=tuple(sorted(missing)))


def check_readiness(depends_on: Sequence[str], resolution: PeriodResolution, *,
                     reference_period: str | None = None,
                     reference_filled: bool = False,
                     any_prior_period_owed: bool = True,
                     supply_states: dict[str, str] | None = None) -> Unrunnable | None:
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
        return _why_missing(missing, supply_states or {})
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


def contested_own_checks(contested: Iterable[str],
                         check_ids: Iterable[str]) -> frozenset[str]:
    """The checks that must not run because their OWN table is contested.

    REQ-PIPE-079 criterion 13, and the safeguard that makes criterion
    12's fall-through safe rather than a false green.

    THE SPLIT THIS DRAWS is between a check filed AGAINST a table and a
    check that merely READS it. Two files claim `cp_clients`, so nobody
    has said which one the supply is - and running cp_clients' own
    uniqueness check against the version already promoted last quarter
    would report on data the supplier did not send, in the green
    direction, while appearing to have checked their file. A
    referential-integrity check filed against cp_placements that reads
    cp_clients is in no such position: it is making a claim about the
    period's clients, and the period's clients are exactly what it
    reads (criterion 12).

    A DATASET MAPS TO ONE LOGICAL TABLE BY CONSTRUCTION under the
    supply model (plans/supply-model.md Thread F), which is what lets
    "this check's own table" be answered from the check_id's own
    dataset segment rather than from a second declaration that could
    disagree with it.

    LOUD ON A NAME NOTHING CLAIMS, rather than skipping it. Failing to
    suppress is the dangerous direction here, so a logical table no
    dataset owns raises hierarchy.UnknownDatasetError instead of
    quietly resolving to "not one of ours, let it run".
    """
    datasets = {hierarchy.dataset_for_table(table).dataset_id
                for table in contested}
    if not datasets:
        return frozenset()
    return frozenset(
        cid for cid in check_ids
        if check_id_mod.parse(cid).dataset in datasets)
