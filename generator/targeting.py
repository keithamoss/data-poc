"""Building a supply to land on a verdict by construction, from the rules the
checks define (REQ-GEN-184; Keith, 2026-10-11, plans/running-thoughts.md #63).

NOT BY TRIAL AND ERROR. The blunt 'amber' preset blanks columns that a
single-tier check fails on any single null, so an "amber" supply read red as a
whole; and a rebuild was the only way to find out. This reads the catalogue of
every check's bands (qa_tools/common/check_bands.py, REQ-GEN-183) and changes
only what a rule's own band allows, inside it with a margin.

WHAT IS PROTECTED, said exactly: an ordinary amber protects multiple-birth
rows, because the sibling checks are today the only single-tier checks that
read the columns it blanks besides those columns' own checks, which ignore
nulls (post-build-review #154 confirmed it against single_tier_readers). The
general guard - leave alone whatever any single-tier check's reads_columns
names - is criterion 5's, built with the injected targets in part B.

ORDINARY AMBERS, WITHIN ONE SUPPLY (criteria 6-8; Keith, 2026-10-11): an
ordinary Birth Registrations amber pushes one null-rate rule into its band,
blanking only rows outside a multiple-birth group (the sibling check matches
twins on the same columns); an ordinary Child Protection amber writes a few
unrecognised client postcodes inside REQ-QAC-187's tolerance. Neither moves a
row count, an identifier or a value distribution, so the cross-supply checks
read them as they read a clean supply.

KEPT OUT OF THE HOLD ERA (criterion 9): a genuinely amber supply drawn into a
period whose amber setting is `hold` would wait for a person nobody scripted,
leaving a gap every later supply's drift and volume checks read red against.

AIMING IS NOT JUDGING (Keith, 2026-10-11): nothing here records or emits a
verdict. The real tools decide; REQ-GEN-186 checks they agreed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

TABLE = "birth_registrations"
TWIN_FLAG = "is_multiple_birth"
#: The authored name the three tools' multiple-birth sibling checks share.
SIBLING_RULE = "Multiple-birth sibling match"
#: The two lever sets a provider may declare (generator/collections/base.py's
#: `target_levers`): null-rate rules on one table, and unrecognised client
#: postcodes.
NULL_RATE = "null-rate"
CLIENT_POSTCODES = "client-postcodes"

#: Four-character postcodes no supplier would send and no reader treats as
#: missing - and numeric, because the loader stages the column as a number
#: and a word would change a clean column's type (REQ-QAC-187's decision).
UNRECOGNISED_POSTCODES = tuple(str(9990 + i) for i in range(10))


class TargetError(ValueError):
    """A target no combination of rules can meet. Loud by design: a supply
    that demonstrates something other than what was asked is worse than
    none (REQ-GEN-044 criterion 4)."""


def lever_dataset(levers: str) -> str:
    """The dataset a lever set builds targets on - read from the provider
    that declares it (REQ-GEN-246 criterion 6), never written down here.
    Refused when no provider declares it."""
    from generator import collections

    for provider in collections.providers():
        if provider.target_levers == levers:
            return provider.amber_dataset
    raise TargetError(f"no collection's generator provider declares the {levers} levers, so "
                      f"no target can be built with them")


def levers_for(dataset_id: str, where: str) -> str:
    """Which lever set builds `dataset_id`'s targets, from its collection's
    provider - REFUSED NAMING THE COLLECTION where it has none, which
    replaced treating every dataset that was not Birth Registrations as
    Child Protection (REQ-GEN-246 criterion 6)."""
    from generator import collections
    from qa_tools.common import hierarchy

    try:
        provider = collections.for_dataset(dataset_id)
    except collections.NoProviderError as exc:
        raise TargetError(f"{where}: {exc}") from None
    if provider.target_levers is None:
        raise TargetError(f"{where}: {hierarchy.dataset(dataset_id).collection_id} declares no "
                          f"target levers, so no target can be built for {dataset_id}")
    return provider.target_levers


def _catalogue():
    from qa_tools.common import check_bands

    return check_bands.catalogue()


def _target(band: tuple[int, int], now: int) -> int | None:
    """The middle of what is left of `band` above `now`, or None where the
    supply already sits at or past its top."""
    lo, hi = max(band[0], now + 1), band[1]
    return None if lo > hi else (lo + hi) // 2


def bdm_amber(df: pd.DataFrame, seed: int, catalogue=None, where: str = "",
              rows: int | None = None) -> pd.DataFrame:
    """One null-rate rule pushed into its amber band, the rest untouched.

    Which rule is the seed's choice among those with room to rise into
    their band, so the history's ambers are not all the same column. Only
    rows outside a multiple-birth group are blanked: the sibling check
    matches twins on these very columns, and a value removed from one twin
    and not the other fails it in three tools (criterion 5)."""
    cat = catalogue or _catalogue()
    bdm = lever_dataset(NULL_RATE)
    rng = np.random.default_rng(seed)
    if rows is not None and len(df) > rows:
        # THE SIZE OF THE SUPPLY BEFORE IT (Keith, 2026-10-11), exactly: a
        # batch comes out a little longer than asked, so the excess is
        # dropped - single-birth rows only, so no twin loses its sibling.
        singles = df.index[~df["is_multiple_birth"].astype(bool)]
        df = df.drop(rng.choice(np.array(singles), size=len(df) - rows, replace=False))
    rows = len(df)
    singles = df.index[~df["is_multiple_birth"].astype(bool)]
    options = []
    for rule in cat.rules():
        if (rule.dataset_id, rule.category, rule.measure) != (bdm, "completeness", "rows") \
                or not rule.column or rule.column not in df.columns:
            continue
        for band in rule.amber(rows):
            want = _target(band, int(df[rule.column].isna().sum()))
            if want is not None:
                options.append((rule.column, want))
    if not options:
        raise TargetError(f"{where or bdm}: amber was asked for, and no null-rate rule has "
                          f"room left in an amber band at {rows} rows")
    column, want = options[int(rng.integers(len(options)))]
    out = df.copy()
    present = [i for i in singles if pd.notna(out.at[i, column])]
    need = want - int(out[column].isna().sum())
    if need > len(present):
        raise TargetError(f"{where or bdm}: {column} needs {need} more blanks for amber, and "
                          f"only {len(present)} single-birth rows carry a value")
    chosen = rng.choice(np.array(present), size=need, replace=False)
    out.loc[chosen, column] = pd.NA
    return out


# ---- injected targets (part B: criteria 1-5, 11, 12) ----------------------

VERDICTS = ("green", "amber", "red")


@dataclass(frozen=True)
class Target:
    """What an injected arrival's rows are built to (criterion 2): green,
    amber or red, with the rules that must warn (amber) or fail (red).

    A RULE IS NAMED BY ITS KEY - its authored name, or `column.category`
    for an unnamed rule - because one rule runs in up to four tools and
    they move together (Keith, 2026-10-11, question 1)."""

    verdict: str
    rules: tuple[str, ...] = ()

    def __post_init__(self):
        if self.verdict not in VERDICTS:
            raise TargetError(f"a target is one of {', '.join(VERDICTS)}, not "
                              f"{self.verdict!r}")
        if self.verdict == "green" and self.rules:
            raise TargetError("a green target names no rules - nothing is to warn or fail")

    def as_record(self) -> dict:
        """`built_to`, never `verdict` (post-build-review #155): this is
        what the rows were aimed at, and criterion 12 forbids recording a
        verdict - a key that reads like one invites the mistake."""
        return {"built_to": self.verdict, "rules": list(self.rules)}


def rule_key(rule) -> str:
    """How a target names a rule: its authored name, else column and
    category - and the measure where that is not bad rows."""
    if rule.name:
        return rule.name
    key = f"{rule.column or '(table)'}.{rule.category}"
    return key if rule.measure == "rows" else f"{key}.{rule.measure}"


def check_target(target: Target, dataset_id: str, where: str, catalogue=None) -> None:
    """Refuse, BEFORE ANYTHING IS WRITTEN, a target no lever can meet
    (criterion 11: fail generation, never emit the history). Checked at
    the contract's ordinary size; a band that closes only at the real
    supply's size still refuses during generation, which stops it too."""
    from qa_tools.common import check_bands

    levers = levers_for(dataset_id, where)
    cat = catalogue or _catalogue()
    if levers == CLIENT_POSTCODES:
        if target.verdict == "red":
            raise TargetError(f"{where}: red cannot be built for Child Protection - no "
                              f"lever exists yet (TS-48, 49 and 51 are out of "
                              f"REQ-GEN-184's scope)")
        if any(r != "postcode.conformity" for r in target.rules):
            raise TargetError(f"{where}: amber on {list(target.rules)} cannot be built: "
                              f"client postcodes (postcode.conformity) are the only Child "
                              f"Protection lever")
        return
    levers, refused = _levers(cat, None)
    by_key = {rule_key(r): r for r in levers}
    rows = check_bands.default_rows(dataset_id, cat)
    for key in target.rules:
        rule = by_key.get(key)
        if rule is None:
            why = refused.get(key, "no lever moves it - only null-rate rules on Birth "
                                   "Registrations can be targeted today")
            raise TargetError(f"{where}: {target.verdict} on {key!r} cannot be built: {why}")
        if target.verdict == "amber" and not rule.amber(rows):
            raise TargetError(f"{where}: amber on {key!r} cannot be built: it has no amber "
                              f"band at {rows} rows")


def _levers(cat, df: pd.DataFrame | None) -> tuple[list, dict[str, str]]:
    """The null-rate rules on Birth Registrations a target may move, and
    why each other one may not (criterion 5).

    A COLUMN IS A LEVER ONLY IF EVERY SINGLE-TIER CHECK READING IT IS ONE
    A BLANK OR A FILL LEAVES ALONE BY CONSTRUCTION: a check of the rule
    itself; a value check on that same column reading nothing else (a
    blank is not a value, a fill is one the column already carries); or a
    multiple-birth sibling check, named as such, which reads only twins'
    rows, never touched. NOT a uniqueness check, which a fill from the
    column's own values can break, nor a check that also reads another
    column (post-build-review #155). Any other reader refuses the rule.

    THE TWIN FLAG ITSELF IS NEVER A LEVER: twin protection reads it, and
    a blank in a boolean column is not a blank (#155 - it crashed)."""
    bdm = lever_dataset(NULL_RATE)
    readers = cat.single_tier_readers(bdm)
    by_id = {c.check_id: c for c in cat.checks}

    def harmless(check_id: str, rule) -> bool:
        c = by_id.get(check_id)
        if c is None:
            return False
        if c in rule.checks or c.name == SIBLING_RULE:
            return True
        own = {f"{TABLE}.{rule.column}"}
        return (c.column == rule.column and c.category != "uniqueness"
                and set(c.reads_columns) <= own)

    usable, refused = [], {}
    for rule in cat.rules():
        if (rule.dataset_id, rule.category, rule.measure) != (bdm, "completeness", "rows") \
                or not rule.column or (df is not None and rule.column not in df.columns):
            continue
        if rule.column == TWIN_FLAG:
            refused[rule_key(rule)] = (f"{TWIN_FLAG} is what keeps twins whole, so it is "
                                       f"never moved")
            continue
        others = [r for r in readers.get(rule.column, []) if not harmless(r, rule)]
        if others:
            refused[rule_key(rule)] = ("a single-tier check reads its column: "
                                       + ", ".join(o.rsplit(".", 1)[-1] for o in others))
        else:
            usable.append(rule)
    return usable, refused


def _first(rule, rows: int, trips) -> int | None:
    """The smallest null count at which `trips(check, x, rows)` holds for
    any of the rule's checks, or None."""
    return next((x for x in range(rows + 1) if any(trips(c, x, rows) for c in rule.checks)),
                None)


def _set_nulls(df: pd.DataFrame, column: str, want: int, rng, where: str) -> pd.DataFrame:
    """`column` with exactly `want` nulls, changing single-birth rows only:
    blanking present values, or filling blanks with values the column
    already carries - valid by construction for its own checks."""
    singles = df.index[~df["is_multiple_birth"].astype(bool)]
    now = int(df[column].isna().sum())
    out = df.copy()
    if want > now:
        present = [i for i in singles if pd.notna(out.at[i, column])]
        need = want - now
        if need > len(present):
            raise TargetError(f"{where}: {column} needs {need} more blanks, and only "
                              f"{len(present)} single-birth rows carry a value")
        out.loc[rng.choice(np.array(present), size=need, replace=False), column] = pd.NA
    elif want < now:
        blank = [i for i in singles if pd.isna(out.at[i, column])]
        need = now - want
        if need > len(blank):
            raise TargetError(f"{where}: {column} needs {need} blanks filled, and only "
                              f"{len(blank)} are in single-birth rows")
        pool = out[column].dropna().to_numpy()
        chosen = rng.choice(np.array(blank), size=need, replace=False)
        out.loc[chosen, column] = rng.choice(pool, size=need)
    return out


def bdm_target(df: pd.DataFrame, target: Target, seed: int, catalogue=None,
               where: str = "", rows: int | None = None) -> tuple[pd.DataFrame, list[dict]]:
    """An injected Birth Registrations arrival built to `target`, and what
    was moved (criteria 1-5; criterion 12 records the second value).

    GREEN FIRST, ALWAYS. A clean batch already trips some rules by itself -
    registering_parent_2_name carries about 600 blanks in 2,078 rows, past
    dbt's 550 - so every lever is first brought clear of its first warning
    (criterion 4: every rule not perturbed stays passing). Amber then
    places each chosen rule inside its band, red past its first failure,
    each with a margin; a rule nobody named is the seed's choice. The
    supply is `rows` long when given - the size of the supply before it -
    so the cross-supply checks read it as they read any other.

    NO PRESET, EVER (criterion 1), and nothing here decides a verdict:
    the real tools do (Keith, 2026-10-11)."""
    cat = catalogue or _catalogue()
    where = where or lever_dataset(NULL_RATE)
    rng = np.random.default_rng(seed)
    if rows is not None and len(df) > rows:
        singles = df.index[~df["is_multiple_birth"].astype(bool)]
        df = df.drop(rng.choice(np.array(singles), size=len(df) - rows, replace=False))
    n = len(df)
    levers, refused = _levers(cat, df)
    by_key = {rule_key(r): r for r in levers}
    moved: list[dict] = []
    original = {r.column: int(df[r.column].isna().sum()) for r in levers}

    out = df
    for rule in levers:
        trip = _first(rule, n, lambda c, x, r: c.warns(x, r) or c.fails(x, r))
        now = int(out[rule.column].isna().sum())
        # A MARGIN EVERYWHERE, not only past the first warning: 550 blanks
        # against dbt's "> 550" passes with none (post-build-review #155).
        if trip is not None and now > (trip - 1) * 9 // 10:
            want = max(0, (trip - 1) * 9 // 10)
            out = _set_nulls(out, rule.column, want, rng, where)
            moved.append({"rule": rule_key(rule), "to": "green", "nulls": want, "of_rows": n})
    if target.verdict == "green":
        return out, moved

    for key in target.rules:
        if key not in by_key:
            why = refused.get(key, "no lever moves it - only null-rate rules on Birth "
                                   "Registrations can be targeted today")
            raise TargetError(f"{where}: {target.verdict} on {key!r} cannot be built: {why}")
    if target.verdict == "amber":
        options = [r for r in levers if r.amber(n)]
    else:
        options = [r for r in levers if _first(r, n, lambda c, x, rr: c.fails(x, rr)) is not None]
    chosen = [by_key[k] for k in target.rules] or (
        [options[int(rng.integers(len(options)))]] if options else [])
    if not chosen:
        raise TargetError(f"{where}: {target.verdict} was asked for, and no null-rate rule "
                          f"can be moved there at {n} rows")
    for rule in chosen:
        if target.verdict == "amber":
            bands = rule.amber(n)
            if not bands:
                raise TargetError(f"{where}: amber on {rule_key(rule)!r} cannot be built: it "
                                  f"has no amber band at {n} rows - closed by "
                                  + ", ".join(c.rsplit(".", 1)[-1] for c in rule.closed_by(n)))
            want = _target(bands[0], -1)
        else:
            first_fail = _first(rule, n, lambda c, x, r: c.fails(x, r))
            if first_fail is None:
                raise TargetError(f"{where}: red on {rule_key(rule)!r} cannot be built: no "
                                  f"check of it fails at any count in {n} rows")
            want = min(n, first_fail + max(1, first_fail // 10))
        out = _set_nulls(out, rule.column, want, rng, where)
        moved = [m for m in moved if m["rule"] != rule_key(rule)]
        moved.append({"rule": rule_key(rule), "to": target.verdict, "nulls": want,
                      "of_rows": n, "was": original[rule.column]})
    return out, moved


def cp_target(payload: dict[str, pd.DataFrame], target: Target, seed: int, catalogue=None,
              where: str = "") -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """An injected Child Protection delivery built to `target`. Green is
    the delivery as built; amber is the ordinary amber's lever, client
    postcodes; red has no lever yet - the scenarios that need one (TS-48,
    49 and 51) are out of this requirement's scope (Keith, 2026-10-11)."""
    where = where or lever_dataset(CLIENT_POSTCODES)
    if target.verdict == "green":
        return payload, []
    if target.verdict == "red":
        raise TargetError(f"{where}: red cannot be built for Child Protection - no lever "
                          f"exists yet (TS-48, 49 and 51 are out of REQ-GEN-184's scope)")
    if any(r != "postcode.conformity" for r in target.rules):
        raise TargetError(f"{where}: amber on {list(target.rules)} cannot be built: client "
                          f"postcodes (postcode.conformity) are the only Child Protection "
                          f"lever")
    out = cp_amber(payload, seed, catalogue, where)
    bad = int(out["cp_clients"]["postcode"].isin(UNRECOGNISED_POSTCODES).sum())
    return out, [{"rule": "postcode.conformity", "to": "amber", "values": bad,
                  "of_rows": len(out["cp_clients"])}]


def cp_amber(payload: dict[str, pd.DataFrame], seed: int, catalogue=None,
             where: str = "") -> dict[str, pd.DataFrame]:
    """A few unrecognised client postcodes, inside the band REQ-QAC-187's
    tolerance gives with Soda's and dbt's, at the middle of it - and nothing
    else of the delivery changed (criteria 7 and 8)."""
    cat = catalogue or _catalogue()
    clients_dataset = lever_dataset(CLIENT_POSTCODES)
    clients = payload["cp_clients"]
    rows = len(clients)
    rule = cat.rule(clients_dataset, "postcode", "conformity")
    bands = rule.amber(rows)
    if not bands:
        raise TargetError(f"{where or clients_dataset}: amber was asked for, and client postcodes "
                          f"have no amber band at {rows} clients")
    want = _target(bands[0], 0)
    rng = np.random.default_rng(seed)
    present = clients.index[clients["postcode"].notna()]
    if want > len(present):
        raise TargetError(f"{where or clients_dataset}: {want} unrecognised postcodes are needed "
                          f"for amber, and only {len(present)} clients carry a postcode")
    chosen = rng.choice(np.array(present), size=want, replace=False)
    out = clients.copy()
    out["postcode"] = out["postcode"].astype("object")
    for n, i in enumerate(sorted(chosen)):
        out.at[i, "postcode"] = UNRECOGNISED_POSTCODES[n % len(UNRECOGNISED_POSTCODES)]
    return {**payload, "cp_clients": out}


def outside_hold(severities: list, dates: list[date], dataset_id: str,
                 keep_clean: frozenset[int] = frozenset(),
                 unavailable: frozenset[int] = frozenset()) -> list:
    """`severities` with every 'amber' that cannot be generated where it was
    drawn moved to the next clean entry that can take it, so the number of
    ordinary ambers GENERATED equals the number drawn (criterion 9).

    An entry cannot carry an ordinary amber when its date falls under a
    `hold` amber setting, or when it is in `unavailable` - a period an
    injected scenario owns or empties, where the generator ignores the
    drawn severity altogether (post-build-review #154: moving ambers
    without knowing that generated three of six). `keep_clean` names
    positions that must stay clean whatever - a collection's own
    bookends."""
    from qa_tools.common import amber_setting, asset_time

    def held(i: int) -> bool:
        at = asset_time.start_of_day(dates[i])
        return amber_setting.resolve(dataset_id, at).value == amber_setting.HOLD

    def blocked(i: int) -> bool:
        return i in unavailable or held(i)

    out = list(severities)
    for i, sev in enumerate(out):
        if sev != "amber" or not blocked(i):
            continue
        swap = next((j for j in list(range(i + 1, len(out))) + list(range(0, i))
                     if out[j] is None and j not in keep_clean and not blocked(j)), None)
        if swap is None:
            why = ("falls in the hold era" if held(i)
                   else "falls on a period an injected scenario owns")
            raise TargetError(f"{dataset_id}: an ordinary amber {why} on {dates[i]} and "
                              f"no clean period outside the hold era is left to take it")
        out[i], out[swap] = None, "amber"
    return out
