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

BDM = "birth-registrations"
CP_CLIENTS = "cp-clients"

#: Four-character postcodes no supplier would send and no reader treats as
#: missing - and numeric, because the loader stages the column as a number
#: and a word would change a clean column's type (REQ-QAC-187's decision).
UNRECOGNISED_POSTCODES = tuple(str(9990 + i) for i in range(10))


class TargetError(ValueError):
    """A target no combination of rules can meet. Loud by design: a supply
    that demonstrates something other than what was asked is worse than
    none (REQ-GEN-044 criterion 4)."""


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
        if (rule.dataset_id, rule.category, rule.measure) != (BDM, "completeness", "rows") \
                or not rule.column or rule.column not in df.columns:
            continue
        for band in rule.amber(rows):
            want = _target(band, int(df[rule.column].isna().sum()))
            if want is not None:
                options.append((rule.column, want))
    if not options:
        raise TargetError(f"{where or BDM}: amber was asked for, and no null-rate rule has "
                          f"room left in an amber band at {rows} rows")
    column, want = options[int(rng.integers(len(options)))]
    out = df.copy()
    present = [i for i in singles if pd.notna(out.at[i, column])]
    need = want - int(out[column].isna().sum())
    if need > len(present):
        raise TargetError(f"{where or BDM}: {column} needs {need} more blanks for amber, and "
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
        return {"verdict": self.verdict, "rules": list(self.rules)}


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

    cat = catalogue or _catalogue()
    if dataset_id != BDM:
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
    rows = check_bands.default_rows(BDM, cat)
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

    A COLUMN IS A LEVER ONLY IF EVERY SINGLE-TIER CHECK READING IT IS ITS
    OWN or one blanking leaves alone by construction: a check on that
    same column (which reads the values a blank or a fill leaves valid),
    or a multiple-birth sibling check, which reads only twins' rows and
    twins are never touched. Any other reader - a SQL check that joins on
    the column, say - would be broken by a blank, so the rule is refused
    rather than moved."""
    readers = cat.single_tier_readers(BDM)
    columns_of = {c.check_id: c.column for c in cat.checks}
    usable, refused = [], {}
    for rule in cat.rules():
        if (rule.dataset_id, rule.category, rule.measure) != (BDM, "completeness", "rows") \
                or not rule.column or (df is not None and rule.column not in df.columns):
            continue
        others = [r for r in readers.get(rule.column, [])
                  if columns_of.get(r) != rule.column and ".is_multiple_birth." not in r]
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
    where = where or BDM
    rng = np.random.default_rng(seed)
    if rows is not None and len(df) > rows:
        singles = df.index[~df["is_multiple_birth"].astype(bool)]
        df = df.drop(rng.choice(np.array(singles), size=len(df) - rows, replace=False))
    n = len(df)
    levers, refused = _levers(cat, df)
    by_key = {rule_key(r): r for r in levers}
    moved: list[dict] = []

    out = df
    for rule in levers:
        trip = _first(rule, n, lambda c, x, r: c.warns(x, r) or c.fails(x, r))
        now = int(out[rule.column].isna().sum())
        if trip is not None and now >= trip:
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
        now = int(out[rule.column].isna().sum())
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
                      "of_rows": n, "was": now})
    return out, moved


def cp_target(payload: dict[str, pd.DataFrame], target: Target, seed: int, catalogue=None,
              where: str = "") -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """An injected Child Protection delivery built to `target`. Green is
    the delivery as built; amber is the ordinary amber's lever, client
    postcodes; red has no lever yet - the scenarios that need one (TS-48,
    49 and 51) are out of this requirement's scope (Keith, 2026-10-11)."""
    where = where or CP_CLIENTS
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
    clients = payload["cp_clients"]
    rows = len(clients)
    rule = cat.rule(CP_CLIENTS, "postcode", "conformity")
    bands = rule.amber(rows)
    if not bands:
        raise TargetError(f"{where or CP_CLIENTS}: amber was asked for, and client postcodes "
                          f"have no amber band at {rows} clients")
    want = _target(bands[0], 0)
    rng = np.random.default_rng(seed)
    present = clients.index[clients["postcode"].notna()]
    if want > len(present):
        raise TargetError(f"{where or CP_CLIENTS}: {want} unrecognised postcodes are needed "
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
