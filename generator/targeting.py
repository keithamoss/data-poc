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
