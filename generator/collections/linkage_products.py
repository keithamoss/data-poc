"""Linkage Products' synthetic generator (REQ-GEN-334): one linkage delivery a
quarter, linkage_keys.csv, on the quarter's own round, built from each linked
dataset's last generated supply filed to that quarter and received before it.

A PROVIDER OF THE SHARED DRIVER (REQ-GEN-246), and GENERIC: which datasets it
links, by which code and identifier columns, is the linked_datasets declared
beside linkage-keys in contract/data-asset.yaml; whose rows it reads is the
providers of those datasets' collections, through the base module's declared
row interface (generated_supplies) - never data/deliveries. Importable
without pandas or numpy.

WHEN IT ARRIVES (criteria 8 and 12, Keith 2026-10-30 'cap the lag'): on the
round, before its 18:00 due time (Keith 2026-10-30, moved from 14:00 because
Emergency Department's files land 15:00 to 17:00; settled by his signing of
REQ-GEN-334 criterion 8's amendment A4, 2026-10-31) and after the
arrivals it reads. A replay's invented promotion lag for a supply this
product reads ends before this delivery's receipt (promotion.next_receipt),
so an ordinary quarter's supply is promoted when the release is checked.

SYNTHETIC ONLY: every key is a scrambled token from this provider's seed.

TWO DELIVERY STREAMS (REQ-GEN-295 criterion 1): the linkage stream above, and
the GEOCODING STREAM - for every quarter, one delivery of its own holding one
file per code-less linked dataset (REQ-QAC-294 criterion 2), due 19:00 and
received 18:05 to 18:55, an hour after the linkage release, each file built
from its source's last generated supply filed to the quarter and received
before it. GENERIC over that declaration: which datasets it writes, the one
source each geocodes and its identifier columns come from the hierarchy; the
columns a record is placed by from contract/synthetic_inputs.yaml; the set of
years each record is written for from the list setting its set-member checks
name. Each stream has its own seeds, slot ids, numbering and bookkeeping, and
the linkage stream's jobs run first, in today's order.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, time, timedelta

from generator.collections.base import Job, Plan, Provider, Stream

COLLECTION_ID = "linkage-products"
DATASET_ID = "linkage-keys"
TABLE = "linkage_keys"
FILE = f"{TABLE}.csv"


def columns() -> list[str]:
    """The release's columns: linkage_key, dataset and every id_ column the
    contract declares, id_1 to id_N in order (REQ-QAC-330 criterion 3). The
    contract's id_N runs one past the most identifiers any linked dataset
    declares, so a surplus one (REQ-GEN-335 (c), PROVISIONAL) has a column to
    arrive in; blank ordinarily."""
    import re

    from qa_tools.common import hierarchy, linked_datasets

    ds = hierarchy.dataset(DATASET_ID)
    ids = [c for c in linked_datasets._columns(linked_datasets.REPO, ds.contract, ds.table)
           if re.fullmatch(r"id_\d+", c or "")]
    return ["linkage_key", "dataset", *sorted(ids, key=lambda c: int(c[3:]))]

#: Seeds 70001.. a quarter, each plus its resupply's +500; the key token's
#: secret and the ordinary severity draw beside them.
BASE_SEED = 70_000
RESUPPLY_SPAN = 500
KEY_SEED = 70_999
RUN_PLAN_SEED = 70_998
#: The ordinary link rate (criterion 7, Keith 2026-10-28): 90 to 96 percent of
#: each linked dataset's rows.
LINK_RATE = (0.90, 0.96)
#: COVERAGE BANDS AS THE CHECKS STATE THEM (REQ-QAC-333 criterion 2): amber
#: below 90 percent, red below 85. A fault's rate is drawn inside its band.
COVERAGE = {"ordinary": (90.0, 96.5), "amber": (85.5, 89.5), "red": (78.0, 84.0)}
#: LARGE KEY GROUPS (REQ-QAC-333 criterion 1 (6)): more than 50 records on one
#: key; amber above 2 percent of distinct keys, red above 4. The sizes cycle
#: through several of the check's histogram bins, so its bars are not one.
LARGE_GROUP = 50
LARGE_GROUPS = {"amber": ((2.0, 4.0), (51, 64, 110, 72, 160, 58, 230, 90)),
                "red": ((4.0, 100.0), (51, 52, 55, 60, 53, 70))}
#: Received on the round between 17:05 and 17:55, after the afternoon's
#: Emergency Department arrivals (15:00 to 17:00) and before the 18:00 due time.
RECEIVED_FROM = time(17, 5)

#: THE DELIVERY STREAMS (REQ-GEN-295 criterion 1), by the name each job carries.
LINKAGE_STREAM, GEO_STREAM = "linkage", "geocoding"
#: THE GEOCODING STREAM'S SEEDS, its own range [71000, 72000) (criterion 14):
#: 71001.. a quarter, and the keyed hash's secret.
GEO_BASE_SEED = 71_000
GEO_KEY_SEED = 71_999
#: Received on the round between 18:05 and 18:55, before its 19:00 due time and
#: an hour after the linkage release (criterion 9; Keith, 2026-10-31, Q9 a).
GEO_RECEIVED_FROM = time(18, 5)
#: The synthetic geocoder's own failures, independently of the source: 0.5 to
#: 1.5 percent of a supply's records not placed (criterion 6).
GEOCODER_FAILURE = (0.005, 0.015)
#: THE GEOCODING STREAM'S ORDINARY SEVERITY DRAW (REQ-GEN-295 criterion 13),
#: from the stream's own seed - never the linkage stream's RUN_PLAN_SEED.
GEO_RUN_PLAN_SEED = 71_998
#: A geocoding slot's fault draw is its seed plus this, and a red's resupply
#: its seed plus one more (REQ-GEN-298), so the rows every clean quarter is
#: built from are drawn exactly as before.
GEO_FAULT_SPAN = 500
#: THE UNEXPECTED CENSUS YEAR (REQ-GEN-298 criterion 5; Keith, Q14, as moved
#: in the v5 round): 2026 joins the set only from 2027-Q3, after the history
#: ends, so in every quarter only the unexpected-year check catches it.
UNEXPECTED_YEAR = 2026
#: RECORDS LEFT OUT, as a percentage of the source supply's records
#: (REQ-GEN-298 criterion 4): the coverage check's amber and red routes.
LEFT_OUT = {"amber": (0.5, 1.5), "red": (3.0, 6.0)}
#: Where inside the share check's band a share fault aims, as margins from
#: its warn and fail bounds, in percentage points (criterion 1): amber
#: between warn + 1 and fail - 1, red between fail + 2 and fail + 8.
SHARE_AIM = {"amber": (1.0, -1.0), "red": (2.0, 8.0)}

#: THE GEOCODING STREAM'S NAMED ROW FAULTS (REQ-GEN-298 criteria 1 and 4),
#: named as data as ROW_FAULTS are - each "name@<geocoding dataset id>", the
#: dataset the fault is applied to. A SHAPE OF THE FILE'S ROWS, NEVER A
#: VERDICT: the real tools decide, and the generation-time trial confirms.
GEO_ROW_FAULTS = {
    "missing_year": "one census year's rows dropped for chosen records (two or more years "
                    "in force)",
    "duplicate_year": "one census year's row repeated, identical in every column, for "
                      "chosen records",
    "unexpected_year": f"a row for census year {UNEXPECTED_YEAR}, outside the set in force, "
                       f"for chosen records",
    "not_geocoded_amber": "whole records turned 'not geocoded' in every year until the share "
                          "lies in the share check's amber band",
    "not_geocoded_red": "whole records turned 'not geocoded' in every year until the share "
                        "lies in the share check's red band",
    "left_out_amber": "0.5 to 1.5 percent of the source's records left out in every year",
    "left_out_red": "3 to 6 percent of the source's records left out in every year",
    "orphan_record": "one record's rows, in every year, naming a record the quarter's source "
                     "does not hold",
    "empty_file": "the file holds no rows at all",
}
#: The verdict each fault is built to; the share faults' is the share's own,
#: banded by the check (planned_verdict).
GEO_FAULT_VERDICT = {"missing_year": "red", "duplicate_year": "red", "unexpected_year": "red",
                     "left_out_amber": "amber", "left_out_red": "red",
                     "orphan_record": "red", "empty_file": "red"}
#: THE CHECK EACH FAULT IS AIMED AT (criterion 7), by the end of its check id
#: - "{source}" the source dataset's id - so a named scenario's trial refuses
#: when any other check of its file moves.
GEO_FAULT_AIMS = {"missing_year": "census_year.missing_set_members_dbt",
                  "duplicate_year": "census_year.duplicated_set_members_dbt",
                  "unexpected_year": "census_year.unexpected_set_members_dbt",
                  "not_geocoded_amber": "match_level.value_share_soda",
                  "not_geocoded_red": "match_level.value_share_soda",
                  "left_out_amber": "{source}.coverage_soda",
                  "left_out_red": "{source}.coverage_soda",
                  "orphan_record": "{source}.referential_soda",
                  "empty_file": "{source}.coverage_soda"}
#: THE PRESETS (criterion 2): an ordinary amber raises the share into the
#: amber band; an ordinary red takes one of these, the missing year only
#: where two or more years are in force.
GEO_AMBER_PRESET = "not_geocoded_amber"
GEO_RED_PRESETS = ("missing_year", "duplicate_year", "unexpected_year", "not_geocoded_red")
#: The synthetic code pools, in the ABS ASGS formats - never a real
#: correspondence (REQ-QAC-294 NFR 4): nine-digit SA2 and five-digit LGA codes,
#: each led by Western Australia's state digit.
SA2_POOL, LGA_POOL = 400, 60

#: THE NAMED ROW FAULTS a scenario's arrival may ask for (ExtraArrival.
#: row_faults; REQ-GEN-335). Each a SHAPE of the release's rows, never a
#: verdict - the real checks decide. "@<dataset id>" names the linked dataset
#: a fault is about. `awaits_resupply` changes no row: it is a precondition,
#: refused where the linked dataset's quarter has no resupply received after
#: the release (criterion 3).
ROW_FAULTS = {
    "empty_key": "one row's linkage_key is empty (a)",
    "undeclared_code": "every row of the dataset carries a code nobody declared - the "
                       "dataset as good as missing from the release (b)",
    "surplus_id": "one row of the dataset carries an id_2, one identifier more than it "
                  "declares (c)",
    "double_link": "one record of the dataset linked twice, under two keys (d)",
    "dangling_id": "one row of the dataset whose identifier matches no record of the "
                   "quarter (e, i)",
    "coverage_amber": "the dataset linked at 85.5 to 89.5 percent (f)",
    "coverage_red": "the dataset linked at 78 to 84 percent (g, and the ordinary reds)",
    "large_groups_amber": "large key groups at just over 2 percent of keys (m)",
    "large_groups_red": "large key groups at just over 4 percent of keys (n)",
    "blank_id": "one row of the dataset whose id_1 is blank (o)",
    "awaits_resupply": "no change: the dataset's quarter is resupplied after the release",
}
_PER_DATASET = {"undeclared_code", "surplus_id", "double_link", "dangling_id",
                "coverage_amber", "coverage_red", "blank_id", "awaits_resupply"}


class CannotGenerate(ValueError):
    """Refused before anything is written (criteria 6, 12 and 13; REQ-GEN-335
    criteria 5 and 6)."""


def linked() -> tuple:
    """(dataset id, code, id columns) for every dataset linkage-keys links."""
    from qa_tools.common import hierarchy

    return hierarchy.dataset(DATASET_ID).linked


def geocoded() -> list[tuple[str, str, tuple[str, ...]]]:
    """(dataset id, the one source it geocodes, the source's identifier
    columns) for every code-less linked dataset of this collection, in
    hierarchy order (REQ-QAC-294 criterion 2)."""
    from qa_tools.common import hierarchy

    return [(d.dataset_id, d.linked[0][0], d.linked[0][2])
            for d in hierarchy.datasets_in_collection(COLLECTION_ID)
            if len(d.linked) == 1 and d.linked[0][1] is None]


def _hash_unit(*parts) -> float:
    """A keyed hash of the stream's seed and `parts`, as a number in [0, 1)."""
    digest = hashlib.sha256(":".join(str(p) for p in (GEO_KEY_SEED, *parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64


def _pool(name: str, size: int, digits: int) -> list[str]:
    """A synthetic pool of distinct codes in an ABS format: the state digit
    then `digits - 1` digits from the keyed hash."""
    out: list[str] = []
    k = 0
    while len(out) < size:
        code = "5" + str(int(_hash_unit("pool", name, k) * 10 ** (digits - 1))).zfill(digits - 1)
        if code not in out:
            out.append(code)
        k += 1
    return out


_POOLS: dict = {}


def area_codes(dataset_id: str, record: str, year) -> tuple[str, str]:
    """(SA2 code, LGA code) for one record in one census year - from a keyed
    hash of the stream's seed, the dataset and the record's identifiers, the
    year changing only the codes (criterion 5): never a random draw's state,
    so the same record carries the same codes in every quarter and resupply."""
    if not _POOLS:
        _POOLS["sa2"], _POOLS["lga"] = _pool("sa2", SA2_POOL, 9), _pool("lga", LGA_POOL, 5)
    sa2 = _POOLS["sa2"][int(_hash_unit(dataset_id, record, year, "sa2") * SA2_POOL)]
    # THE LGA IS THE SA2'S (post-build-review #299 item 6): derived from the
    # SA2 code alone, so an SA2 always sits inside one LGA.
    lga = _POOLS["lga"][int(_hash_unit("lga-of", sa2) * LGA_POOL)]
    return sa2, lga


def member_setting_of(dataset_id: str) -> tuple[str, str]:
    """(the member column, the list setting) the dataset's set-member checks
    name - which years a record is written for is that setting's in force."""
    from qa_tools.common import list_setting_members

    found = {(c.column, c.member_setting) for c in list_setting_members.declared()
             if c.dataset_id == dataset_id and c.column and c.member_setting}
    if len(found) != 1:
        raise CannotGenerate(f"{dataset_id}'s set-member checks name {sorted(found) or 'no'} "
                             f"member setting - one is needed to know which years to write; "
                             f"nothing was written")
    return next(iter(found))


def members_in_force(dataset_id: str, period) -> tuple:
    """The members in force for the period, on its ROUND DATE (REQ-QAC-300
    criterion 4) - refused where no version covers it."""
    from qa_tools.common import amber_setting

    _column, setting = member_setting_of(dataset_id)
    r = amber_setting.resolve_on_date(dataset_id, period.round_date,
                                      key=(amber_setting.LIST_SETTINGS, setting))
    if r is None:
        raise CannotGenerate(f"{dataset_id}: no version of {setting} covers {period.name} - "
                             f"nothing was written")
    return tuple(r.value)


def geo_columns(dataset_id: str) -> list[str]:
    """The geocoding table's columns, in its contract's order."""
    from qa_tools.common import hierarchy, linked_datasets

    ds = hierarchy.dataset(dataset_id)
    return linked_datasets._columns(linked_datasets.REPO, ds.contract, ds.table)


def geocode_rows(dataset_id: str, source_rows, id_columns, years, failure_rate: float):
    """One geocoding file's rows for one source supply (criteria 4 to 6):
    exactly one row for each DISTINCT set of identifier values and each year
    in force - a source row whose identifiers are null or blank written
    nowhere, a repeat written once. A record is placed by the finest of its
    declared address columns that holds a value, else written unplaced, codes
    empty; a further share of records, from the keyed hash, the geocoder
    could not place. A record is placed or not for all its years together."""
    import pandas as pd

    from generator import synthetic_inputs

    placing = synthetic_inputs.placings()[dataset_id]
    member_col, _setting = member_setting_of(dataset_id)
    out_cols = geo_columns(dataset_id)
    ids = [c for c in out_cols if c.startswith("id_")]
    seen: dict[tuple, dict] = {}
    if source_rows is not None and len(source_rows):
        for row in source_rows.to_dict("records"):
            values = tuple(row.get(c) for c in id_columns)
            text = tuple("" if v is None or str(v).lower() == "nan" else str(v).strip()
                         for v in values)
            if any(t == "" for t in text):
                continue
            seen.setdefault(text, row)
    rows = []
    for record, row in seen.items():
        joined = _joined(record)
        failed = _hash_unit(dataset_id, joined, "failure") < failure_rate
        level = placing.unplaced_value if failed else placing.value_for(row)
        for year in years:
            sa2, lga = (("", "") if level == placing.unplaced_value
                        else area_codes(dataset_id, joined, year))
            out = {c: (record[i] if i < len(record) else "") for i, c in enumerate(ids)}
            out.update({member_col: year, "sa2_code": sa2, "lga_code": lga,
                        placing.placed_column: level})
            rows.append(out)
    return pd.DataFrame(rows, columns=out_cols)


def planned_verdict(dataset_id: str, rows, catalogue) -> str:
    """The supply's planned verdict on its value-share check, banded by the
    check's own bands as the catalogue reads them (criterion 7): the share of
    rows holding the unplaced value. green where no row exists."""
    from generator import synthetic_inputs

    placing = synthetic_inputs.placings()[dataset_id]
    checks = [c for c in catalogue.checks if c.dataset_id == dataset_id
              and c.check_id.endswith(".value_share_soda")]
    if len(checks) != 1:
        raise CannotGenerate(f"{dataset_id} declares {len(checks)} value-share checks - one is "
                             f"needed to plan its supplies' verdicts; nothing was written")
    total = int(len(rows))
    bad = int((rows[placing.placed_column] == placing.unplaced_value).sum()) if total else 0
    if total and checks[0].fails(bad, total):
        return "red"
    if total and checks[0].warns(bad, total):
        return "amber"
    return "green"


_RANK = {"green": 0, "amber": 1, "red": 2}


def worst(*verdicts: str) -> str:
    """The worst of several planned verdicts."""
    return max(verdicts, key=lambda v: _RANK[v]) if verdicts else "green"


def parse_geo_fault(fault: str, where: str, dataset_id: str) -> str:
    """A geocoding row fault's name, refused naming the scenario where the
    name is unknown or it names a dataset other than the one it is applied
    to (REQ-GEN-298 criterion 1)."""
    name, _, did = fault.partition("@")
    if name not in GEO_ROW_FAULTS:
        raise CannotGenerate(f"{where}: unknown geocoding row fault {name!r} - known faults "
                             f"are {', '.join(sorted(GEO_ROW_FAULTS))}; nothing was written")
    if did != dataset_id:
        raise CannotGenerate(f"{where}: geocoding row fault {fault!r} must name the dataset "
                             f"it is applied to ({name}@{dataset_id}); nothing was written")
    return name


def _share_check(dataset_id: str, catalogue):
    checks = [c for c in catalogue.checks if c.dataset_id == dataset_id
              and c.check_id.endswith(".value_share_soda")]
    if len(checks) != 1:
        raise CannotGenerate(f"{dataset_id} declares {len(checks)} value-share checks - one is "
                             f"needed to plan its supplies' verdicts; nothing was written")
    return checks[0]


def _keys(rows, ids: list[str]):
    """Each row's record, its identifier values joined as one text value."""
    import pandas as pd

    if not len(rows):
        return pd.Series([], dtype=str, index=rows.index)
    return rows[ids].astype(str).agg("\x1f".join, axis=1)


def apply_geo_faults(dataset_id: str, rows, faults, *, source_rows, id_columns, years,
                     rng, where: str, catalogue, seed: int):
    """One geocoding file's rows with its named faults applied (REQ-GEN-298
    criteria 1, 4 and 6), and the verdict the file is built to: the share's
    own band (planned_verdict) and each fault's. Pure: the same inputs and
    draw give the same rows. Refused - never shifted or relaxed - where a
    fault cannot be placed. `seed` is the declared seed `rng` was made from,
    handed on to generator/dirty.py, which seeds its own draw (REQ-GEN-246
    criterion 2: no seed outside the provider's declared schedule)."""
    import pandas as pd

    from generator import dirty, synthetic_inputs

    placing = synthetic_inputs.placings()[dataset_id]
    member_col, _setting = member_setting_of(dataset_id)
    ids = [c for c in rows.columns if c.startswith("id_")][:len(id_columns)]
    level = placing.placed_column
    unplaced = placing.unplaced_value
    rows = rows.copy()
    built: list[str] = []

    def records():
        key = _keys(rows, ids)
        order = list(dict.fromkeys(key.tolist()))
        placed_all = (rows[level] != unplaced).groupby(key).all() if len(rows) else {}
        return key, order, [k for k in order if bool(placed_all[k])]

    def share() -> float:
        return 100.0 * int((rows[level] == unplaced).sum()) / len(rows) if len(rows) else 0.0

    for fault in faults:
        name = parse_geo_fault(fault, where, dataset_id)
        key, order, placed = records()
        if not order and name != "empty_file":
            raise CannotGenerate(f"{where}: {dataset_id} has no record to carry {name}; "
                                 f"nothing was written")
        if name in ("missing_year", "duplicate_year", "unexpected_year"):
            pool = placed or order
            k = min(len(pool), int(rng.integers(1, 4)))
            chosen = {pool[i] for i in sorted(rng.choice(len(pool), size=k, replace=False))}
            mask = key.isin(chosen)
            if name == "missing_year":
                if len(years) < 2:
                    raise CannotGenerate(
                        f"{where}: a missing census year needs two or more years in force, "
                        f"and {dataset_id}'s quarter holds {list(years)} - dropping its only "
                        f"year would leave the record out, which is coverage's fault; nothing "
                        f"was written")
                year = years[int(rng.integers(len(years)))]
                rows = rows[~(mask & (rows[member_col].astype(str) == str(year)))]
            elif name == "duplicate_year":
                year = years[int(rng.integers(len(years)))]
                one = rows[mask & (rows[member_col].astype(str) == str(year))]
                # generator/dirty.py's duplicate, IDENTICAL IN EVERY COLUMN: no
                # near-duplicate columns (criterion 1).
                twice = dirty.inject_duplicate_rows(one, 1.0, seed)
                rows = pd.concat([rows, twice.iloc[len(one):]], ignore_index=True)
            else:
                extra = rows[mask].drop_duplicates(subset=ids, keep="last").copy()
                extra[member_col] = UNEXPECTED_YEAR
                for k2 in extra.index:
                    if extra.at[k2, level] != unplaced:
                        rec = "\x1f".join(str(extra.at[k2, c]) for c in ids)
                        extra.at[k2, "sa2_code"], extra.at[k2, "lga_code"] = area_codes(
                            dataset_id, rec, UNEXPECTED_YEAR)
                rows = pd.concat([rows, extra], ignore_index=True)
            built.append(GEO_FAULT_VERDICT[name])
        elif name in ("not_geocoded_amber", "not_geocoded_red"):
            band = name.rsplit("_", 1)[1]
            check = _share_check(dataset_id, catalogue)
            warn, fail = check.warn[0].value, check.fail[0].value
            lo, hi = ((warn + SHARE_AIM["amber"][0], fail + SHARE_AIM["amber"][1])
                      if band == "amber" else
                      (fail + SHARE_AIM["red"][0], fail + SHARE_AIM["red"][1]))
            want = float(rng.uniform(lo, hi))
            # WHOLE RECORDS, every year, codes emptied (criterion 6): so only
            # the share check catches it.
            per_record = key.value_counts()
            bad = int((rows[level] == unplaced).sum())
            turned = []
            for i in rng.permutation(len(placed)):
                if 100.0 * bad / len(rows) >= want:
                    break
                turned.append(placed[int(i)])
                bad += int(per_record[placed[int(i)]])
            m = key.isin(set(turned))
            rows.loc[m, level] = unplaced
            rows.loc[m, "sa2_code"] = ""
            rows.loc[m, "lga_code"] = ""
            if planned_verdict(dataset_id, rows, catalogue) != band:
                raise CannotGenerate(f"{where}: {dataset_id}'s not-geocoded share {share():.2f} "
                                     f"percent is not in the share check's {band} band; "
                                     f"nothing was written")
        elif name in ("left_out_amber", "left_out_red"):
            band = name.rsplit("_", 1)[1]
            lo, hi = LEFT_OUT[band]
            # MEASURED AS THE COVERAGE CHECK MEASURES IT: the share of the
            # source supply's rows whose record has no geocoding row.
            source = [_joined(r) for r in _records(source_rows, id_columns)] \
                if source_rows is not None else []
            if not source:
                raise CannotGenerate(f"{where}: {dataset_id}'s source holds no record to leave "
                                     f"out; nothing was written")
            counts: dict = {}
            for v in source:
                counts[v] = counts.get(v, 0) + 1
            want = float(rng.uniform(lo, hi))
            out, gone = set(), 0
            for i in rng.permutation(len(order)):
                rec = order[int(i)]
                if 100.0 * gone / len(source) >= want:
                    break
                n = counts.get(rec, 0)
                if 100.0 * (gone + n) / len(source) > hi:
                    continue
                out.add(rec)
                gone += n
            left = 100.0 * gone / len(source)
            if not lo <= left <= hi:
                raise CannotGenerate(f"{where}: {left:.2f} percent of {dataset_id}'s source "
                                     f"records left out, outside {lo} to {hi}; nothing was "
                                     f"written")
            # WHOLE RECORDS, every year (criterion 6): the missing-year check
            # counts only records present, so it does not catch it.
            rows = rows[~key.isin(out)]
            built.append(GEO_FAULT_VERDICT[name])
        elif name == "orphan_record":
            source = ({_joined(r) for r in _records(source_rows, id_columns)}
                      if source_rows is not None else set())
            rec = (placed or order)[int(rng.integers(len(placed or order)))]
            parts = rec.split("\x1f")
            new = parts[:-1] + [f"{parts[-1]}9"]
            if _joined(tuple(new)) in source or _joined(tuple(new)) in set(order):
                raise CannotGenerate(f"{where}: the orphan identifier {_joined(tuple(new))!r} "
                                     f"matches a record; nothing was written")
            # ADDED, never renamed: a renamed record would also leave its
            # source record uncovered, a second fault in the supply.
            extra = rows[key == rec].copy()
            for c, v in zip(ids, new):
                extra[c] = v
            for k2 in extra.index:
                if extra.at[k2, level] != unplaced:
                    extra.at[k2, "sa2_code"], extra.at[k2, "lga_code"] = area_codes(
                        dataset_id, _joined(tuple(new)), extra.at[k2, member_col])
            rows = pd.concat([rows, extra], ignore_index=True)
            built.append(GEO_FAULT_VERDICT[name])
        elif name == "empty_file":
            if source_rows is None or not len(source_rows):
                raise CannotGenerate(f"{where}: an empty {dataset_id} file needs a source "
                                     f"supply holding rows (REQ-QAC-340 criterion 4); nothing "
                                     f"was written")
            rows = rows.iloc[0:0]
            built.append(GEO_FAULT_VERDICT[name])
    rows = rows.reset_index(drop=True)
    return rows, worst(planned_verdict(dataset_id, rows, catalogue), *built)


def _token(code: str, value: str) -> str:
    """The same source record carries the same key in every quarter."""
    digest = hashlib.sha256(f"{KEY_SEED}:{code}:{value}".encode()).hexdigest()
    return f"LK{digest[:16].upper()}"


def parse_fault(fault: str, where: str) -> tuple[str, str | None]:
    """(name, dataset id or None), refused naming the scenario where the name is
    unknown, a per-dataset fault names no dataset, or the dataset is not linked."""
    name, _, did = fault.partition("@")
    if name not in ROW_FAULTS:
        raise CannotGenerate(f"{where}: unknown row fault {name!r} - known faults are "
                             f"{', '.join(sorted(ROW_FAULTS))}; nothing was written")
    if (name in _PER_DATASET) != bool(did):
        raise CannotGenerate(f"{where}: row fault {name!r} "
                             f"{'names no' if name in _PER_DATASET else 'takes no'} linked "
                             f"dataset (name@<dataset id>); nothing was written")
    if did and did not in {d for d, _c, _cols in linked()}:
        raise CannotGenerate(f"{where}: row fault {fault!r} names {did}, which "
                             f"{DATASET_ID} does not link; nothing was written")
    return name, did or None


def run_plan(n: int) -> list:
    """Each quarter's drawn severity, oldest first: the collections' mix - about
    a quarter amber, two reds, the oldest clean (REQ-GEN-335 criterion 1)."""
    import numpy as np

    if n < 4:
        return [None] * n
    rng = np.random.default_rng(RUN_PLAN_SEED)
    n_amber = max(1, round(n * 0.25))
    rest = [None] * ((n - 1) - n_amber - 2) + ["amber"] * n_amber + ["red"] * 2
    rng.shuffle(rest)
    return [None] + rest


def _records(rows, cols) -> list[tuple[str, ...]]:
    """A source supply's identifier values, one tuple per row over `cols` in
    order, each as text as the checks cast them - a row with any of them null
    or blank dropped, since it can match no linkage row."""
    present = rows[list(cols)].notna().all(axis=1)
    out = []
    for values in zip(*(rows.loc[present, c].tolist() for c in cols)):
        text = tuple(str(v) for v in values)
        if all(t.strip() != "" for t in text):
            out.append(text)
    return out


def _ids(rows, column: str) -> list[str]:
    """One source column's identifier values as text (_records of one)."""
    return [t[0] for t in _records(rows, [column])]


def _joined(record: tuple[str, ...]) -> str:
    """A record's identifiers as one value - the value itself for one."""
    return "\x1f".join(record)


def _coverage(source: list[str], linked_ids: set) -> float:
    return 100.0 * sum(1 for v in source if v in linked_ids) / len(source) if source else 0.0


def _link(source: list[str], band: tuple[float, float], rng, where: str) -> list[str]:
    """Distinct ids linked so that the share of the source's rows linked - the
    coverage check's own measure - lands inside `band`; refused otherwise."""
    distinct = list(dict.fromkeys(source))
    if not distinct:
        return []
    want = rng.uniform(*band)
    order = [distinct[k] for k in rng.permutation(len(distinct))]
    counts = {}
    for v in source:
        counts[v] = counts.get(v, 0) + 1
    chosen, covered = [], 0
    for v in order:
        if 100.0 * covered / len(source) >= want:
            break
        if 100.0 * (covered + counts[v]) / len(source) > band[1]:
            continue  # an identifier repeated in the source would overshoot the band
        chosen.append(v)
        covered += counts[v]
    got = _coverage(source, set(chosen))
    if not band[0] <= got <= band[1]:
        raise CannotGenerate(f"{where}: coverage {got:.2f} percent falls outside "
                             f"{band[0]} to {band[1]} - nothing was written")
    return sorted(chosen, key=distinct.index)


def build_rows(sources_before: dict, faults: tuple, rng, where: str):
    """One release's rows from each linked dataset's described supply
    ({dataset id: its rows}) with the named faults applied. Pure: the same
    inputs give the same rows."""
    import pandas as pd

    parsed = [parse_fault(f, where) for f in faults]
    out_cols = columns()
    by = {}
    for name, did in parsed:
        by.setdefault(name, []).append(did)
    frames, sources = [], {}
    for did, code, cols in linked():
        rows = sources_before.get(did)
        if rows is None:
            continue
        source = _records(rows, cols)
        sources[did] = (code, source)
        band = (COVERAGE["amber"] if did in by.get("coverage_amber", ())
                else COVERAGE["red"] if did in by.get("coverage_red", ())
                else COVERAGE["ordinary"])
        ids = _link(source, band, rng, f"{where}, {did}")
        frame = {"linkage_key": [_token(code, _joined(v)) for v in ids], "dataset": code}
        for j, c in enumerate(out_cols[2:]):
            frame[c] = [v[j] for v in ids] if j < len(cols) else ""
        frames.append(pd.DataFrame(frame))
    df = (pd.concat(frames, ignore_index=True) if frames
          else pd.DataFrame(columns=out_cols))
    for name, did in parsed:
        if did is not None and did not in sources:
            raise CannotGenerate(f"{where}: row fault {name}@{did} - the release describes no "
                                 f"{did} supply in its quarter; nothing was written")
    df = _apply_faults(df, parsed, sources, rng, where, out_cols)
    return df[out_cols].reset_index(drop=True)


def _apply_faults(df, parsed, sources, rng, where, out_cols):
    import pandas as pd

    ids = out_cols[2:]
    width = {code: len(cols) for _did, code, cols in linked()}

    def joined(k):
        return _joined(tuple(df.at[k, c] for c in ids[:width[df.at[k, "dataset"]]]))

    def one_row(did):
        code = sources[did][0]
        idx = df.index[df["dataset"] == code].tolist()
        if not idx:
            raise CannotGenerate(f"{where}: no {did} row to carry a fault; nothing was written")
        return idx[int(rng.integers(len(idx)))]

    for name, did in parsed:
        if name == "empty_key":
            df.loc[df.index[int(rng.integers(len(df)))], "linkage_key"] = ""
        elif name == "undeclared_code":
            df.loc[df["dataset"] == sources[did][0], "dataset"] = f"{sources[did][0]}_V2"
        elif name == "surplus_id":
            k = one_row(did)
            n = width[sources[did][0]]
            if n >= len(ids):
                raise CannotGenerate(f"{where}: {did} declares {n} identifier(s), as many as "
                                     f"the contract's id columns, so no surplus one has a "
                                     f"column to arrive in; nothing was written")
            others = df.loc[(df["dataset"] == df.at[k, "dataset"]) & (df.index != k), "id_1"]
            df.loc[k, ids[n]] = others.iloc[0] if len(others) else f"{df.at[k, 'id_1']}-2"
        elif name == "double_link":
            k = one_row(did)
            twin = df.loc[[k]].copy()
            twin["linkage_key"] = _token(twin.iloc[0]["dataset"], f"{joined(k)}#2")
            df = pd.concat([df, twin], ignore_index=True)
        elif name == "dangling_id":
            code, source = sources[did]
            picked = source[int(rng.integers(len(source)))]
            value = (*picked[:-1], f"{picked[-1]}9")
            if value in set(source):
                raise CannotGenerate(f"{where}: the dangling identifier {_joined(value)!r} "
                                     f"matches a {did} record; nothing was written")
            row = {"linkage_key": [_token(code, _joined(value))], "dataset": [code]}
            for j, c in enumerate(ids):
                row[c] = [value[j] if j < len(value) else ""]
            df = pd.concat([df, pd.DataFrame(row)], ignore_index=True)
        elif name == "blank_id":
            df.loc[one_row(did), "id_1"] = ""
        elif name in ("large_groups_amber", "large_groups_red"):
            df = _large_groups(df, name.rsplit("_", 1)[1], rng, where)
    return df


def large_group_share(df) -> float:
    """The check's own value: the share of distinct keys carrying more than
    LARGE_GROUP records, counted across every dataset."""
    sizes = df.groupby("linkage_key").size()
    return 100.0 * int((sizes > LARGE_GROUP).sum()) / len(sizes) if len(sizes) else 0.0


def _large_groups(df, band_name: str, rng, where: str):
    """Records re-keyed into groups of the band's sizes until the share of
    distinct keys that are large groups passes the band's floor; refused where
    it then lies outside the band."""
    (low, high), sizes = LARGE_GROUPS[band_name]
    order = [int(k) for k in rng.permutation(len(df))]
    df = df.copy()
    at, g = 0, 0
    while large_group_share(df) <= low:
        size = sizes[g % len(sizes)]
        if at + size > len(order):
            raise CannotGenerate(f"{where}: too few rows ({len(df)}) for large key groups "
                                 f"above {low} percent; nothing was written")
        df.loc[order[at:at + size], "linkage_key"] = _token("GROUP", f"{where}:{g}")
        at, g = at + size, g + 1
    share = large_group_share(df)
    if not low < share <= high:
        raise CannotGenerate(f"{where}: large key groups at {share:.2f} percent, outside "
                             f"{low} to {high}; nothing was written")
    return df


def _delay(rng) -> int:
    """A resupply's turnaround after the release it corrects: five to twenty
    days, sooner more likely - Emergency Department's own curve."""
    import numpy as np

    days = np.arange(5, 21)
    weights = 0.8 ** (days - 5)
    return int(rng.choice(days, p=weights / weights.sum()))


class LinkageProducts(Provider):
    collection_id = COLLECTION_ID
    dataset_id = DATASET_ID
    amber_dataset = DATASET_ID
    # THE GENERATION-TIME TRIAL (REQ-GEN-298 criterion 10), in each tried
    # supply's slot's period: every geocoding amber, red and scenario file.
    target_trial = True
    # A SECOND RANGE FOR THE GEOCODING STREAM (criterion 14).
    seed_ranges = ((70_000, 71_000), (71_000, 72_000))
    generating_note = "one linkage release and one geocoding release a quarter"

    @property
    def target_datasets(self) -> tuple[str, ...]:
        """Linkage Keys and every geocoding dataset - each geocoding supply's
        planned verdict is recorded as a target (criterion 7)."""
        return (DATASET_ID, *(d for d, _src, _cols in geocoded()))

    def streams(self) -> tuple[Stream, ...]:
        geo = tuple(d for d, _src, _cols in geocoded())
        return ((Stream(LINKAGE_STREAM, (DATASET_ID,)),)
                + ((Stream(GEO_STREAM, geo),) if geo else ()))

    def _read(self) -> list[str]:
        """Every dataset either stream reads, linkage's first."""
        return list(dict.fromkeys([*(d for d, _c, _cols in linked()),
                                   *(src for _d, src, _cols in geocoded())]))

    @property
    def depends_on(self) -> tuple[str, ...]:
        from qa_tools.common import hierarchy

        out = []
        for did in self._read():
            coll = hierarchy.dataset(did).collection_id
            if coll not in out:
                out.append(coll)
        return tuple(out)

    def seed_schedule(self) -> list[tuple[str, int, int]]:
        # COUNTED FROM THE CALENDAR, NOT THE SOURCES (2026-10-30): the quarters
        # a release is generated for are a subset of the calendar's to date, so
        # this covers every seed the plan derives - without generating Child
        # Protection's and Emergency Department's histories (and importing
        # pandas) just to check seed ranges.
        from generator.anchor_date import get_anchor_date
        from qa_tools.common import schedule

        n = len(schedule.periods_for_dataset(DATASET_ID, until=get_anchor_date()))
        geo = len({p.name for d, _src, _cols in geocoded()
                   for p in schedule.periods_for_dataset(d, until=get_anchor_date())})
        return [("the key token", KEY_SEED, KEY_SEED), ("the run plan", RUN_PLAN_SEED,
                                                       RUN_PLAN_SEED)] + [
            (f"lp_slot_{i:02d}", BASE_SEED + i, BASE_SEED + i + RESUPPLY_SPAN)
            for i in range(1, n + 1)] + ([
                ("the geocoding stream's keyed hash", GEO_KEY_SEED, GEO_KEY_SEED),
                ("the geocoding stream's severity draw", GEO_RUN_PLAN_SEED,
                 GEO_RUN_PLAN_SEED)] if geo else []) + [
            (f"geo_slot_{i:02d}", GEO_BASE_SEED + i, GEO_BASE_SEED + i + GEO_FAULT_SPAN + 1)
            for i in range(1, geo + 1)]

    def _sources(self) -> dict:
        """{dataset id: its generated supplies}, refused naming both where a
        provider this one depends on is absent (criterion 6)."""
        from generator import collections
        from generator.collections import base

        cache = getattr(self, "_cache", None)
        if cache is not None:
            return cache
        out = {}
        for did in self._read():
            try:
                dep = collections.for_dataset(did)
            except collections.NoProviderError as exc:
                raise CannotGenerate(
                    f"{self.collection_id} reads {did}, whose collection has no generator "
                    f"provider ({exc}) - nothing was written") from None
            out[did] = base.generated_supplies(dep, did)
        self._cache = out
        return out

    def _periods(self) -> list:
        """Every quarter any linked dataset has a generated supply filed to,
        whose round has come (criterion 2)."""
        from generator.anchor_date import get_anchor_date
        from qa_tools.common import schedule

        sources = self._sources()
        wanted = {s.period for did, _c, _cols in linked() for s in sources[did]}
        return [p for p in schedule.periods_for_dataset(DATASET_ID, until=get_anchor_date())
                if p.name in wanted]

    def _geo_periods(self, dataset_id: str | None = None) -> list:
        """Every quarter a geocoding dataset's source has a generated supply
        filed to, whose round has come (criterion 8) - for one dataset, or
        any."""
        from generator.anchor_date import get_anchor_date
        from qa_tools.common import schedule

        sources = self._sources()
        found: dict = {}
        for d, src, _cols in geocoded():
            if dataset_id is not None and d != dataset_id:
                continue
            have = {s.period for s in sources[src]}
            for p in schedule.periods_for_dataset(d, until=get_anchor_date()):
                if p.name in have:
                    found.setdefault(p.name, p)
        return sorted(found.values(), key=lambda p: p.date)

    def generated_periods(self) -> list:
        return self._periods()

    def generated_periods_for(self, dataset_id: str) -> list:
        if dataset_id in {d for d, _src, _cols in geocoded()}:
            return self._geo_periods(dataset_id)
        return self._periods()

    def _received(self, job: Job) -> datetime:
        """An ordinary release's receipt: on the round, 17:05 to 17:55."""
        from qa_tools.common import asset_time

        minute = (job.seed * 37) % 50
        hhmm = (datetime.combine(job.period.round_date, RECEIVED_FROM)
                + timedelta(minutes=minute)).strftime("%H:%M")
        return asset_time.wall_clock(job.period.round_date, hhmm)

    def _arrivals(self, plan: Plan, job: Job) -> list[tuple[datetime, tuple, str | None]]:
        """(receipt, row faults, severity) for each of the quarter's releases,
        decided before anything is written: a scenario's own arrivals, an
        ordinary red's release and its green resupply, or one release."""
        import numpy as np

        from qa_tools.common import asset_time

        if job.period.name in plan.state["suppressed"]:
            return []
        injected = plan.injected_by_period.get(job.period.name)
        if injected is not None:
            return [(asset_time.wall_clock(job.period.round_date
                                           + timedelta(days=a.day_offset), a.at),
                     a.row_faults, a.severity) for a in injected[0].arrivals]
        first = self._received(job)
        if job.severity is None:
            return [(first, (), None)]
        rng = np.random.default_rng(job.seed + RESUPPLY_SPAN)
        present = [did for did, _c, _cols in linked()
                   if any(s.period == job.period.name for s in plan.state["sources"][did])]
        did = present[int(rng.integers(len(present)))]
        fault = (f"coverage_{job.severity}@{did}",)
        if job.severity == "amber":
            return [(first, fault, "amber")]
        again = asset_time.wall_clock(job.period.round_date + timedelta(days=_delay(rng)),
                                      first.strftime("%H:%M"))
        return [(first, fault, "red"), (again, (), None)]

    def plan(self) -> Plan:
        from generator import scenario_injection, targeting

        self._cache = None
        sources = self._sources()
        periods = self._periods()
        mine = scenario_injection.for_dataset(DATASET_ID)
        scenario_injection.no_two_scenarios_share_a_period(mine, {DATASET_ID: periods})
        resolved = [(i, scenario_injection.resolve(i, periods)) for i in mine]
        injected = {p.period: (i, p) for i, p in resolved}
        suppressed = {name for _i, p in resolved for name in p.suppressed}
        _refuse_scenario_quarters(resolved)
        owned = frozenset(k for k, p in enumerate(periods)
                          if p.name in injected or p.name in suppressed)
        # A QUARTER A CORRECTION IT RIDES ALTERS IS CLEAN TOO (lp_boot,
        # 2026-10-30, PROVISIONAL): the correction moves a source's supply
        # there, so the cross-collection checks carrying an ordinary
        # severity cannot run when the release arrives.
        ridden = _ridden_quarters()
        clean = owned | frozenset(k for k, p in enumerate(periods) if p.name in ridden)
        severities = _place_reds(targeting.outside_hold(
            run_plan(len(periods)), [p.round_date for p in periods], DATASET_ID,
            keep_clean=frozenset({0}), unavailable=clean), clean)
        jobs = [Job(f"lp_slot_{i:02d}", BASE_SEED + i, sev, p, stream=LINKAGE_STREAM)
                for i, (sev, p) in enumerate(zip(severities, periods), start=1)]
        plan = Plan(jobs=jobs, resolved=resolved, injected_by_period=injected,
                    state={"sources": sources, "suppressed": suppressed, "deliveries": {}})
        arrivals = {job.slot_id: self._arrivals(plan, job) for job in jobs}
        plan.state["arrivals"] = arrivals
        for injection, placement in resolved:
            for extra in injection.arrivals:
                for fault in extra.row_faults:
                    parse_fault(fault, injection.scenario_id)
        _refuse_unschedulable(jobs, sources, arrivals, injected)
        _refuse_unmet_preconditions(jobs, sources, arrivals, injected)
        # EVERY RELEASE BUILT ONCE BEFORE THE FIRST WRITE (REQ-GEN-335
        # criterion 5): a fault that cannot be placed refuses here.
        plan.state["rows"] = {job.slot_id: [self._rows(plan, job, n) for n in
                                            range(len(arrivals[job.slot_id]))]
                              for job in jobs}
        # THE GEOCODING STREAM, AFTER EVERY LINKAGE JOB (criterion 1): its own
        # slots, seeds and numbering, so no linkage run or entry moves.
        self._plan_geocoding(plan)
        return plan

    # ---- the geocoding stream (REQ-GEN-295) -------------------------------

    def _geo_received(self, job: Job) -> datetime:
        """A geocoding release's receipt: on the round, 18:05 to 18:55."""
        from qa_tools.common import asset_time

        minute = (job.seed * 37) % 50
        hhmm = (datetime.combine(job.period.round_date, GEO_RECEIVED_FROM)
                + timedelta(minutes=minute)).strftime("%H:%M")
        return asset_time.wall_clock(job.period.round_date, hhmm)

    def _plan_geocoding(self, plan: Plan) -> None:
        """The geocoding stream's jobs, every file built before the first
        write: its rows from its source's last supply received before it
        (REQ-GEN-295), then the faults on purpose (REQ-GEN-298) - a named
        scenario's own, or the presets an ordinary amber or red is drawn to -
        each file's planned verdict, which files the generation-time trial
        tries, and the source supply the warehouse holds when it arrives."""
        import numpy as np

        from generator import scenario_injection, targeting
        from qa_tools.common import asset_time, check_bands, hierarchy

        geo = geocoded()
        if not geo:
            return
        sources = plan.state["sources"]
        catalogue = check_bands.catalogue()
        jobs = [Job(f"geo_slot_{i:02d}", GEO_BASE_SEED + i, None, p, stream=GEO_STREAM)
                for i, p in enumerate(self._geo_periods(), start=1)]
        owes = {d: {p.name for p in self._geo_periods(d)} for d, _src, _cols in geo}
        ridden = _ridden_quarters()
        # THE NAMED SCENARIOS, ONE FAULT EACH (REQ-GEN-298 criteria 3 and 4),
        # refused before anything is written where criterion 7 says so.
        injected: dict = {}
        resolved = []
        for d, _src, _cols in geo:
            mine = scenario_injection.for_dataset(d)
            periods_d = self._geo_periods(d)
            scenario_injection.no_two_scenarios_share_a_period(mine, {d: periods_d})
            for inj in mine:
                placement = scenario_injection.resolve(inj, periods_d)
                if placement.period in injected:
                    raise CannotGenerate(
                        f"{inj.scenario_id}: {placement.period}'s geocoding delivery already "
                        f"carries {injected[placement.period][0].scenario_id} - one geocoding "
                        f"scenario a quarter; nothing was written")
                injected[placement.period] = (inj, placement)
                resolved.append((inj, placement))
        _refuse_geocoding_scenario_quarters(resolved, plan.resolved, ridden)
        tables = {d: hierarchy.dataset(d).table for d, _src, _cols in geo}
        base, rates = {}, {}
        for job in jobs:
            hit = injected.get(job.period.name)
            if hit is not None:
                first = hit[0].arrivals[0]
                at = asset_time.wall_clock(job.period.round_date
                                           + timedelta(days=first.day_offset), first.at)
            else:
                at = self._geo_received(job)
            rng = np.random.default_rng(job.seed)
            files = {}
            for d, src, cols in geo:
                rate = float(rng.uniform(*GEOCODER_FAILURE))
                # THE LAST SOURCE SUPPLY FILED TO THE QUARTER AND RECEIVED
                # BEFORE THIS DELIVERY (criterion 3).
                before = _before(sources[src], src, job.period.name, at)
                if job.period.name not in owes[d] or not before:
                    continue
                rates[(job.slot_id, d)] = rate
                rows = geocode_rows(d, before[-1].rows, cols,
                                    members_in_force(d, job.period), rate)
                files[tables[d]] = (d, rows, planned_verdict(d, rows, catalogue))
            base[job.slot_id] = (at, files) if files else None
        _refuse_geocoding_unschedulable(jobs, sources, base, plan.state["arrivals"], plan.jobs)

        # WHAT THE WAREHOUSE HOLDS FOR EACH SOURCE WHEN THE FILE ARRIVES
        # (criterion 11): the source supply the plan promotes there before
        # the receipt, or none.
        warehouse = {}
        for job in jobs:
            if base[job.slot_id] is None:
                continue
            at, files = base[job.slot_id]
            for _t, (d, _rows, _v) in files.items():
                src = hierarchy.dataset(d).linked[0][0]
                warehouse[(job.slot_id, d)] = in_warehouse(src, job.period.name, at,
                                                           sources[src])
        named = _named_held_sources(plan.resolved, jobs, base, warehouse)

        # THE ORDINARY SEVERITIES, FROM THE STREAM'S OWN SEED (REQ-GEN-295
        # criterion 13): the collections' mix per geocoding dataset, kept off
        # every quarter where a drawn fault could not be told apart from
        # something else - a correction's rounds, a scenario of the dataset or
        # of its source, a source the warehouse does not hold, a file already
        # planned worse than green from its source's own rows.
        claims = {src: _claimed_by(src) for _d, src, _cols in geo}
        draw = np.random.default_rng(GEO_RUN_PLAN_SEED)
        severity: dict = {}
        for d, src, _cols in geo:
            mine = [job for job in jobs if base[job.slot_id] is not None
                    and tables[d] in base[job.slot_id][1]]
            blocked = frozenset(
                k for k, job in enumerate(mine)
                if job.period.name in ridden or job.period.name in injected
                or (d, job.period.name) in named or job.period.name in claims[src]
                or warehouse[(job.slot_id, d)] is None
                or base[job.slot_id][1][tables[d]][2] != "green")
            drawn = targeting.outside_hold(
                _draw(len(mine), draw), [job.period.round_date for job in mine], d,
                keep_clean=frozenset({0}), unavailable=blocked)
            for job, sev in zip(mine, _place_reds(drawn, blocked)):
                if sev is not None:
                    severity[(job.slot_id, d)] = sev

        state, resupply, meta, applied = {}, {}, {}, {}
        for job in jobs:
            if base[job.slot_id] is None:
                state[job.slot_id] = None
                continue
            at, files = base[job.slot_id]
            hit = injected.get(job.period.name)
            rng = np.random.default_rng(job.seed + GEO_FAULT_SPAN)
            out, tried, reds = {}, [], []
            for table, (d, rows, verdict) in files.items():
                src = hierarchy.dataset(d).linked[0][0]
                years = members_in_force(d, job.period)
                sev = severity.get((job.slot_id, d))
                if hit is not None and hit[0].dataset_id == d:
                    faults = hit[0].arrivals[0].row_faults
                    where = hit[0].scenario_id
                elif sev == "amber":
                    faults, where = (f"{GEO_AMBER_PRESET}@{d}",), f"the {job.period.name} {d} amber"
                elif sev == "red":
                    usable = [f for f in GEO_RED_PRESETS if f != "missing_year" or len(years) >= 2]
                    faults = (f"{usable[int(rng.integers(len(usable)))]}@{d}",)
                    where = f"the {job.period.name} {d} red"
                    reds.append(d)
                else:
                    faults, where = (), ""
                if faults:
                    applied[(job.slot_id, d)] = tuple(faults)
                    rows, verdict = apply_geo_faults(
                        d, rows, faults, source_rows=_before(sources[src], src, job.period.name,
                                                             at)[-1].rows,
                        id_columns=hierarchy.dataset(d).linked[0][2], years=years, rng=rng,
                        where=where, catalogue=catalogue, seed=job.seed + GEO_FAULT_SPAN)
                out[table] = (d, rows, verdict)
                # TRIED AT GENERATION (criterion 13): every amber or red, every
                # named scenario's file and each file criterion 8 names.
                if (verdict != "green" or (hit is not None and hit[0].dataset_id == d)
                        or (d, job.period.name) in named):
                    tried.append(d)
            state[job.slot_id] = (at, out)
            meta[(job.slot_id, 1)] = _meta(tried, out, warehouse, job.slot_id)
            if hit is not None:
                # ONE FAULT, AIMED AT ONE CHECK (criteria 3 and 7): every other
                # check of the scenario's file must stay green in its trial.
                d = hit[0].dataset_id
                src = hierarchy.dataset(d).linked[0][0]
                meta[(job.slot_id, 1)]["aimed"] = {d: sorted(
                    GEO_FAULT_AIMS[f.partition("@")[0]].format(source=src)
                    for f in hit[0].arrivals[0].row_faults)}
            if reds:
                # A GREEN RESUPPLY FIVE TO TWENTY DAYS LATER (REQ-GEN-295
                # criterion 13), of the red files alone, each built from its
                # source's last supply received before it.
                again = asset_time.wall_clock(
                    job.period.round_date + timedelta(days=_delay(
                        np.random.default_rng(job.seed + GEO_FAULT_SPAN + 1))),
                    at.strftime("%H:%M"))
                files2 = {}
                for d in reds:
                    src, cols = hierarchy.dataset(d).linked[0][0], hierarchy.dataset(d).linked[0][2]
                    rows = geocode_rows(d, _before(sources[src], src, job.period.name,
                                                   again)[-1].rows, cols,
                                        members_in_force(d, job.period),
                                        rates[(job.slot_id, d)])
                    files2[tables[d]] = (d, rows, planned_verdict(d, rows, catalogue))
                resupply[job.slot_id] = (again, files2)
                meta[(job.slot_id, 2)] = _meta([], files2, {}, job.slot_id)
        plan.jobs.extend(jobs)
        plan.state["geocoding"] = state
        plan.state["geo_resupply"] = resupply
        plan.state["geo_meta"] = meta
        plan.state["geo_named"] = named
        # WHICH FAULTS EACH FILE CARRIES, by (slot, dataset) - what a reader
        # of the plan needs to tell a fault from the rows' own shape.
        plan.state["geo_faults"] = applied
        plan.resolved.extend(resolved)
        plan.injected_by_stream[GEO_STREAM] = injected

    def _geo_arrivals(self, plan: Plan, job: Job) -> list:
        """(receipt, files) for each of a geocoding quarter's deliveries."""
        first = plan.state["geocoding"][job.slot_id]
        if first is None:
            return []
        again = plan.state.get("geo_resupply", {}).get(job.slot_id)
        return [first] + ([again] if again is not None else [])

    def _rows(self, plan: Plan, job: Job, n: int):
        import numpy as np

        from qa_tools.common import asset_time

        at, faults, _sev = plan.state["arrivals"][job.slot_id][n]
        # THE LAST SUPPLY FILED TO THE QUARTER AND RECEIVED BEFORE THIS
        # DELIVERY (criterion 5): a release cannot describe a later file.
        described = {}
        for did, _code, _cols in linked():
            before = [s for s in plan.state["sources"][did] if s.period == job.period.name
                      and asset_time.parse_instant(s.received_at, did) < at]
            if before:
                described[did] = before[-1].rows
        injected = plan.injected_by_period.get(job.period.name)
        where = (injected[0].scenario_id if injected is not None
                 else f"the {job.period.name} linkage release")
        rng = np.random.default_rng(job.seed + (RESUPPLY_SPAN + 1 if n else 0))
        return build_rows(described, faults, rng, where)

    def slot(self, plan: Plan, job: Job) -> list | None:
        from generator.resupply import Delivery
        from qa_tools.common import asset_time

        if job.stream == GEO_STREAM:
            found = self._geo_arrivals(plan, job)
            if not found:
                return None
            return [Delivery(received_date=asset_time.local_date(at), severity=None,
                             payload={t: rows for t, (_d, rows, _v) in files.items()})
                    for at, files in found]
        arrivals = plan.state["arrivals"][job.slot_id]
        if not arrivals:
            return None  # a scenario's quarter with no release at all ((k))
        return [Delivery(received_date=asset_time.local_date(at), severity=sev,
                         payload=plan.state["rows"][job.slot_id][n])
                for n, (at, _faults, sev) in enumerate(arrivals)]

    def entries(self, plan: Plan, job: Job, deliveries: list, run_index_start: int) -> list[dict]:
        if job.stream == GEO_STREAM:
            # NUMBERED WITHIN ITS STREAM, and each file's planned verdict
            # recorded, green included (criterion 7).
            out = []
            for n, (_at, files) in enumerate(self._geo_arrivals(plan, job), start=1):
                entry = {"run_id": f"{self.run_prefix}{GEO_STREAM}_{run_index_start + n:03d}",
                         "run_index": run_index_start + n, "slot_id": job.slot_id,
                         "period": job.period.name, "received_at": None,
                         "dirty_severity": None, "seed": job.seed,
                         "row_counts": {t: int(len(rows)) for t, (_d, rows, _v) in files.items()},
                         "planned": {d: v for _t, (d, _rows, v) in files.items()}}
                # WHAT THE GENERATION-TIME TRIAL TRIES, AND AGAINST WHICH SOURCE
                # (REQ-GEN-298 criteria 11 and 13) - recorded only where a file
                # is tried, so an untried entry reads as it always has.
                entry.update(plan.state["geo_meta"].get((job.slot_id, n)) or {})
                out.append(entry)
            return out
        return [{"run_id": f"{self.run_prefix}{run_index_start + n:03d}",
                 "run_index": run_index_start + n, "slot_id": job.slot_id,
                 "period": job.period.name, "received_at": None,
                 "dirty_severity": d.severity, "seed": job.seed,
                 "row_counts": {TABLE: int(len(d.payload))}}
                for n, d in enumerate(deliveries, start=1)]

    def received_at(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict) -> str:
        from qa_tools.common import asset_time

        if job.stream == GEO_STREAM:
            return asset_time.isoformat(self._geo_arrivals(plan, job)[n - 1][0])
        return asset_time.isoformat(plan.state["arrivals"][job.slot_id][n - 1][0])

    def files(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict, name: str):
        from qa_tools.common import asset_time

        if job.stream == GEO_STREAM:
            if n == 1:
                # WHERE CRITERION 8's NAMED FILES ARE (geo_named_placements).
                plan.state.setdefault("geo_delivery", {})[job.slot_id] = name
            return ({f"{t}.csv": rows.to_csv(index=False)
                     for t, rows in delivery_obj.payload.items()},
                    asset_time.parse_instant(entry["received_at"], entry["run_id"]))
        plan.state["deliveries"].setdefault(job.period.name, []).append(name)
        return ({FILE: delivery_obj.payload[columns()].to_csv(index=False)},
                asset_time.parse_instant(entry["received_at"], entry["run_id"]))

    def describe(self, entry: dict, delivery_obj) -> str:
        if TABLE not in entry["row_counts"]:
            return f"{sum(entry['row_counts'].values()):6d} geocodes"
        return f"{entry['row_counts'][TABLE]:6d} linkage keys"

    def extra_placements(self, plan: Plan) -> list:
        """(j), NAMED, NOT PLANTED (REQ-GEN-335 criterion 7); and the geocoding
        files whose source a source-side scenario keeps out of the warehouse
        (REQ-GEN-298 criterion 8)."""
        return named_placements(self, plan) + geo_named_placements(self, plan)


#: (j)'s scenario id (REQ-GEN-335 criterion 7): named on the first generated
#: quarter a linked dataset's scripted mark-not-supplied puts out of scope,
#: riding the correction that emptied it - never a quarter of its own.
NAMED_NOT_SUPPLIED = "TS-95"


def marked_quarters(periods) -> list[tuple[str, str]]:
    """(dataset id, period) for every generated quarter whose linked dataset a
    scripted ordinary-chain entry marks not supplied, oldest first."""
    from qa_tools.common import scripted_decisions

    names = [p.name for p in periods]
    linked_ids = {d for d, _c, _cols in linked()}
    found = {(s.dataset_id, s.period) for s in scripted_decisions.load()
             if s.operation == scripted_decisions.CHAIN_MARK and s.period
             and s.dataset_id in linked_ids and s.period in names}
    return sorted(found, key=lambda x: (names.index(x[1]), x[0]))


def named_placements(provider, plan: Plan) -> list:
    from generator import scenario_injection
    from qa_tools.common import arrivals as arrivals_mod

    periods = [job.period for job in plan.jobs]
    marked = marked_quarters(periods)
    if not marked:
        raise CannotGenerate(f"{NAMED_NOT_SUPPLIED}: no generated quarter has a linked dataset "
                             f"marked not supplied by script - nothing to name")
    did, period = marked[0]
    p = next(x for x in periods if x.name == period)
    names = plan.state["deliveries"].get(period) or []
    placement = scenario_injection.Placement(
        scenario_id=NAMED_NOT_SUPPLIED, dataset=DATASET_ID, period=period,
        period_date=p.round_date,
        config=(f"quarterly; {did} has no supply for {period}, which a correction emptied "
                f"and a scripted person marked not supplied (contract/scripted_decisions."
                f"yaml), so the {period} release's {did} checks are out of scope while the "
                f"other linked datasets' are evaluated. Nothing planted; it rides the "
                f"correction's claim."),
        arrivals=tuple({"date": p.round_date.isoformat(), "at": "", "delivery": n}
                       for n in names))
    from generator.driver import DELIVERIES_DIR, RECEIPTS_DIR

    recognised = arrivals_mod.arrivals_for(provider.collection_id, provider.run_prefix,
                                           DELIVERIES_DIR, RECEIPTS_DIR)
    scenario_injection.resolve_run_ids([placement], recognised)
    return [placement]


# ---- the geocoding stream's faults on purpose (REQ-GEN-298) ----------------

#: CRITERION 8's FILES, NAMED NOT PLANTED: each ordinary geocoding file of a
#: quarter whose source a source-side scenario keeps out of the warehouse when
#: it is checked - (its scenario id, the geocoding dataset, the linkage
#: scenario placed in that quarter). Lettered siblings of the scenarios that
#: hold the source (PROVISIONAL, REQ-GEN-298's decisions).
NAMED_HELD_SOURCE = (("TS-93c", "geo-cp-clients", "TS-93b"),
                     ("TS-100c", "geo-cp-clients", "TS-100b"),
                     ("TS-101b", "geo-ed-presentations", "TS-101"))


def _before(supplies, dataset_id: str, period: str, at) -> list:
    """The source's supplies filed to `period` and received before `at`,
    oldest first."""
    from qa_tools.common import asset_time

    return [s for s in supplies if s.period == period
            and asset_time.parse_instant(s.received_at, dataset_id) < at]


def _claimed_by(dataset_id: str) -> dict[str, list[str]]:
    """{period: the scenario ids of `dataset_id` claiming it}."""
    from generator import scenario_injection

    out: dict[str, list[str]] = {}
    for inj in scenario_injection.INJECTIONS:
        if inj.dataset_id != dataset_id:
            continue
        for name in scenario_injection.claimed_periods(
                inj, scenario_injection.generated_periods(inj.dataset_id)):
            out.setdefault(name, []).append(inj.scenario_id)
    return out


def in_warehouse(dataset_id: str, period: str, at, supplies):
    """THE SOURCE SUPPLY THE PLAN PROMOTES INTO `period` BEFORE `at`
    (REQ-GEN-298 criterion 11), or None where it promotes none: of the
    quarter's supplies received before `at`, the last the gate promotes by
    rule - a clean one, or an amber where the amber setting in force at its
    receipt promotes (REQ-PIPE-122) - with the scripted decisions about the
    source in that quarter played in (REQ-GEN-135). The effective instant of a
    same-round promotion is before `at` by construction
    (_refuse_geocoding_unschedulable). Refused, naming the supply, where a
    scripted decision's instant cannot be said."""
    from qa_tools.common import amber_setting, asset_time, scripted_decisions

    quarter = [s for s in supplies if s.period == period]
    events = []
    for s in quarter:
        received = asset_time.parse_instant(s.received_at, dataset_id)
        if received >= at:
            continue
        promotes = s.severity is None or (
            s.severity == "amber"
            and amber_setting.resolve(dataset_id, received).value != amber_setting.HOLD)
        events.append((received, "promote" if promotes else "hold", s))
    claimed = set(_claimed_by(dataset_id).get(period, ()))
    for script in scripted_decisions.load():
        if (script.dataset_id != dataset_id or script.scenario not in claimed
                or script.operation not in scripted_decisions.CHAIN_OPERATIONS):
            continue
        if script.supply_index is None or not 0 <= script.supply_index < len(quarter):
            raise CannotGenerate(
                f"{script.scenario}'s scripted {script.operation} of {dataset_id} names supply "
                f"{script.supply_index}, which its {period} plan does not hold, so whether the "
                f"source is in the warehouse at {at.isoformat()} cannot be said; nothing was "
                f"written")
        target = quarter[script.supply_index]
        received = asset_time.parse_instant(target.received_at, dataset_id)
        when = (asset_time.wall_clock(asset_time.local_date(received)
                                      + timedelta(days=script.day_offset), script.at)
                if script.at else received + timedelta(hours=script.after_hours))
        if when < at:
            events.append((when, script.operation, target))
    held = None
    for _when, what, supply in sorted(events, key=lambda e: e[0]):
        if what == "promote":
            held = supply
        elif what == "reject" and held is supply:
            held = None
    return held


def _draw(n: int, rng) -> list:
    """The collections' mix (REQ-GEN-335 criterion 1), from the given draw:
    about a quarter amber, two reds, the oldest clean."""
    if n < 4:
        return [None] * n
    n_amber = max(1, round(n * 0.25))
    rest = [None] * ((n - 1) - n_amber - 2) + ["amber"] * n_amber + ["red"] * 2
    rng.shuffle(rest)
    return [None] + rest


def _meta(tried, files: dict, warehouse: dict, slot_id: str) -> dict:
    """What a geocoding entry records for the generation-time trial: the
    datasets tried, and for each the source table and the receipt of the
    source supply the warehouse holds then - None where it holds none."""
    if not tried:
        return {}
    from qa_tools.common import hierarchy

    out = {}
    for d in tried:
        src = hierarchy.dataset(d).linked[0][0]
        held = warehouse.get((slot_id, d))
        out[d] = {"dataset": src, "table": hierarchy.dataset(src).table,
                  "received_at": held.received_at if held is not None else None}
    return {"tried": sorted(tried), "sources": out}


def _named_held_sources(resolved, jobs, base, warehouse) -> dict:
    """{(geocoding dataset, period): scenario id} for criterion 8's files,
    refused where the quarter's file is not there or its source is in the
    warehouse after all - a name that would point at nothing."""
    by_scenario = {inj.scenario_id: placement.period for inj, placement in resolved}
    out = {}
    for sid, d, linkage_sid in NAMED_HELD_SOURCE:
        period = by_scenario.get(linkage_sid)
        job = next((j for j in jobs if j.period.name == period), None)
        if period is None or job is None or base.get(job.slot_id) is None or \
                (job.slot_id, d) not in warehouse:
            raise CannotGenerate(f"{sid}: no {d} file in {period or linkage_sid + 's quarter'} "
                                 f"to name; nothing was written")
        if warehouse[(job.slot_id, d)] is not None:
            raise CannotGenerate(f"{sid}: {d}'s {period} source is in the warehouse when the "
                                 f"file arrives, so it shows nothing of {linkage_sid}; nothing "
                                 f"was written")
        out[(d, period)] = sid
    return out


def geo_named_placements(provider, plan: Plan) -> list:
    """Criterion 8's files as placements, nothing planted (REQ-GEN-045)."""
    from generator import scenario_injection
    from qa_tools.common import arrivals as arrivals_mod, asset_time

    named = plan.state.get("geo_named") or {}
    if not named:
        return []
    out = []
    by_period = {j.period.name: j for j in plan.jobs if j.stream == GEO_STREAM}
    for (d, period), sid in sorted(named.items(), key=lambda x: x[1]):
        job = by_period[period]
        at, _files = plan.state["geocoding"][job.slot_id]
        src = _source_name(d)
        out.append(scenario_injection.Placement(
            scenario_id=sid, dataset=d, period=period, period_date=job.period.round_date,
            config=(f"quarterly, due 19:00 on the round; the {period} geocoding delivery is an "
                    f"ordinary one, received at {asset_time.localise(at).strftime('%H:%M')} while "
                    f"{src} is not in the warehouse for {period}. Nothing planted."),
            arrivals=({"date": asset_time.local_date(at).isoformat(),
                       "at": asset_time.localise(at).strftime("%H:%M"),
                       "delivery": plan.state.get("geo_delivery", {}).get(job.slot_id, "")},)))
    from generator.driver import DELIVERIES_DIR, RECEIPTS_DIR

    recognised = arrivals_mod.arrivals_for(provider.collection_id, provider.run_prefix,
                                           DELIVERIES_DIR, RECEIPTS_DIR)
    scenario_injection.resolve_run_ids(out, recognised)
    return out


def _source_name(dataset_id: str) -> str:
    from qa_tools.common import hierarchy

    return hierarchy.dataset(hierarchy.dataset(dataset_id).linked[0][0]).dataset_name


def _refuse_geocoding_scenario_quarters(resolved, linkage_resolved, ridden) -> None:
    """REQ-GEN-298 criterion 7, before anything is written: a geocoding
    scenario never on a round REQ-GEN-205's corrections alter, nor in a
    quarter holding another scenario of its source dataset or of the linkage
    delivery - said, and never moved."""
    from qa_tools.common import hierarchy

    linkage = {placement.period: inj.scenario_id for inj, placement in linkage_resolved}
    for inj, placement in resolved:
        if placement.period in ridden:
            raise CannotGenerate(f"{inj.scenario_id}: {placement.period} is a round "
                                 f"REQ-GEN-205's correction alters - choose another quarter "
                                 f"(its anchor is not moved for you); nothing was written")
        src = hierarchy.dataset(inj.dataset_id).linked[0][0]
        others = list(_claimed_by(src).get(placement.period, ()))
        if placement.period in linkage:
            others.append(linkage[placement.period])
        if others:
            raise CannotGenerate(
                f"{inj.scenario_id}: {placement.period} already holds {', '.join(others)}, so "
                f"its outcome would depend on theirs - choose another quarter (its anchor is "
                f"not moved for you); nothing was written")


def _ridden_quarters() -> set[str]:
    """The quarters of this dataset that a correction it rides alters
    (scenario_injection.CORRECTION_RIDERS) - read from the declarations."""
    from generator import correction_claims, scenario_injection

    out: set[str] = set()
    for reference, datasets in scenario_injection.CORRECTION_RIDERS.items():
        if DATASET_ID in datasets:
            out |= correction_claims.altered(reference, [DATASET_ID]).get(DATASET_ID, set())
    return out


def _place_reds(severities: list, owned: frozenset) -> list:
    """A drawn red on a scenario's quarter moved to the next clean ordinary one
    (PROVISIONAL, as outside_hold moves ambers), so two reds are generated."""
    out = list(severities)
    for i, sev in enumerate(out):
        if sev != "red" or i not in owned:
            continue
        j = next((j for j in list(range(i + 1, len(out))) + list(range(1, i))
                  if out[j] is None and j not in owned), None)
        if j is None:
            raise CannotGenerate("an ordinary red falls on a scenario's quarter and no clean "
                                 "quarter is left to take it - nothing was written")
        out[i], out[j] = None, "red"
    return out


def _refuse_scenario_quarters(resolved) -> None:
    """REQ-GEN-335 criterion 6: a linkage scenario's quarter holds no scenario of
    a dataset it links but its own sibling (the same TS number) - said with the
    nearest free quarter, and never moved there."""
    import re

    from generator import scenario_injection

    linked_ids = {d for d, _c, _cols in linked()}
    from qa_tools.common import hierarchy

    ours = {d.dataset_id for did in linked_ids
            for d in hierarchy.datasets_in_collection(hierarchy.dataset(did).collection_id)}
    taken: dict[str, list[str]] = {}
    for inj in scenario_injection.INJECTIONS:
        if inj.dataset_id not in ours:
            continue
        for name in scenario_injection.claimed_periods(
                inj, scenario_injection.generated_periods(inj.dataset_id)):
            taken.setdefault(name, []).append(inj.scenario_id)

    def number(sid):
        return re.match(r"TS-(\d+)", sid).group(1)

    for inj, placement in resolved:
        others = [s for s in taken.get(placement.period, ())
                  if number(s) != number(inj.scenario_id)]
        if others:
            raise CannotGenerate(
                f"{inj.scenario_id}: {placement.period} already holds {', '.join(others)}, "
                f"so its outcome would depend on theirs - choose another quarter (its anchor "
                f"is not moved for you); nothing was written")


def _refuse_unschedulable(jobs, sources, arrivals, injected) -> None:
    """Criteria 12 and 13, before anything is written.

    13: no release shares a receipt instant with any supply it reads.

    12, for each ORDINARY quarter's release (a scenario's quarter keeps what
    it plants): received within its own due time and grace, and after each
    same-round source supply's promotion takes effect - that instant computed
    as the gate computes it (orchestrate.effective_at_of): the one function,
    promotion.effective_at_for, seeded by the arrival's run id, capped at the
    source dataset's next receipt and at the first release reading its period
    (promotion.next_receipt's lag cap), within its claim window. Refused
    naming the quarter, the release and the effective instant."""
    from datetime import timedelta

    from qa_tools.common import asset_time, hierarchy, promotion, schedule, slots

    # ONLY THE DATASETS THE LINKAGE RELEASE READS: a source only the
    # geocoding stream reads is that stream's refusal's (REQ-GEN-295).
    sources = {did: sources[did] for did, _c, _cols in linked() if did in sources}
    instants = {}
    for did, supplies in sources.items():
        for s in supplies:
            instants[asset_time.parse_instant(s.received_at, did)] = f"{did} {s.received_at}"
    for job in jobs:
        for at, _faults, _sev in arrivals[job.slot_id]:
            if at in instants:
                raise CannotGenerate(f"the {job.period.name} linkage release ({at.isoformat()}) "
                                     f"and {instants[at]} would share one receipt instant - "
                                     f"nothing was written")
    releases = sorted((at, job.period.name) for job in jobs
                      for at, _f, _s in arrivals[job.slot_id])
    for job in jobs:
        if not arrivals[job.slot_id] or job.period.name in injected:
            continue
        at = arrivals[job.slot_id][0][0]
        slot = next(s for s in slots.slots_for_dataset(
            DATASET_ID, until=job.period.round_date + timedelta(days=1))
            if s.period.name == job.period.name)
        for did, supplies in sources.items():
            mine = [s for s in supplies if s.period == job.period.name]
            if not mine:
                continue
            first = asset_time.parse_instant(mine[0].received_at, did)
            if asset_time.local_date(first) != job.period.round_date:
                continue        # filed a round earlier, as Child Protection's are
            later = [t for t in (asset_time.parse_instant(s.received_at, did)
                                 for s in supplies) if t > first]
            readers = [t for t, name in releases if t > first and name == job.period.name]
            caps = [min(c) for c in (later, readers) if c]
            took = promotion.effective_at_for(
                first, seed=f"{hierarchy.dataset(did).table}__{asset_time.arrival_key(first)}",
                before=min(caps) if caps else None,
                within=schedule.claim_window(did, on=asset_time.local_date(first)))
            if first >= at or took >= at or at > slot.late_after:
                raise CannotGenerate(
                    f"the {job.period.name} linkage release ({at.isoformat()}) cannot be "
                    f"received after {did}'s promotion for that quarter takes effect "
                    f"({took.isoformat()}) and within its due time and grace (by "
                    f"{slot.late_after.isoformat()}) - nothing was written")


def _refuse_geocoding_unschedulable(jobs, sources, state, linkage_arrivals,
                                    linkage_jobs) -> None:
    """REQ-GEN-334 criteria 12 and 13 applied to the geocoding delivery
    (REQ-GEN-295 criterion 9), before anything is written: no geocoding
    release shares an instant with a supply it reads, and each is received
    within each of its files' due time and grace and after the effective
    instant of each same-round source promotion - computed as the gate
    computes it, capped at the source's next receipt and at the first release
    of either stream reading the period. Refused naming the quarter."""
    from datetime import timedelta

    from qa_tools.common import asset_time, hierarchy, promotion, schedule, slots

    instants = {asset_time.parse_instant(s.received_at, did): f"{did} {s.received_at}"
                for did, supplies in sources.items() for s in supplies}
    releases = sorted([(at, job.period.name) for job in linkage_jobs
                       for at, _f, _s in linkage_arrivals.get(job.slot_id, ())]
                      + [(found[0], job.period.name) for job in jobs
                         if (found := state[job.slot_id]) is not None])
    for job in jobs:
        found = state[job.slot_id]
        if found is None:
            continue
        at, files = found
        if at in instants:
            raise CannotGenerate(f"the {job.period.name} geocoding release ({at.isoformat()}) "
                                 f"and {instants[at]} would share one receipt instant - "
                                 f"nothing was written")
        for _table, (d, _rows, _v) in files.items():
            src = hierarchy.dataset(d).linked[0][0]
            slot = next(s for s in slots.slots_for_dataset(
                d, until=job.period.round_date + timedelta(days=1))
                if s.period.name == job.period.name)
            mine = [s for s in sources[src] if s.period == job.period.name]
            first = asset_time.parse_instant(mine[0].received_at, src)
            took = first
            if asset_time.local_date(first) == job.period.round_date:
                later = [t for t in (asset_time.parse_instant(s.received_at, src)
                                     for s in sources[src]) if t > first]
                readers = [t for t, name in releases if t > first and name == job.period.name]
                caps = [min(c) for c in (later, readers) if c]
                took = promotion.effective_at_for(
                    first, seed=f"{hierarchy.dataset(src).table}__{asset_time.arrival_key(first)}",
                    before=min(caps) if caps else None,
                    within=schedule.claim_window(src, on=asset_time.local_date(first)))
            if first >= at or took >= at or at > slot.late_after:
                raise CannotGenerate(
                    f"the {job.period.name} geocoding release ({at.isoformat()}) cannot be "
                    f"received after {src}'s promotion for that quarter takes effect "
                    f"({took.isoformat()}) and within {d}'s due time and grace (by "
                    f"{slot.late_after.isoformat()}) - nothing was written")


def _refuse_unmet_preconditions(jobs, sources, arrivals, injected) -> None:
    """`awaits_resupply@<dataset>` (REQ-GEN-335 criterion 3): the dataset's
    quarter must have a supply received after the release - its resupply - and
    one before it; refused naming the scenario otherwise, never moved."""
    from qa_tools.common import asset_time

    for job in jobs:
        hit = injected.get(job.period.name)
        if hit is None or not arrivals[job.slot_id]:
            continue
        at = arrivals[job.slot_id][0][0]
        for fault in (f for a in hit[0].arrivals for f in a.row_faults):
            name, _, did = fault.partition("@")
            if name != "awaits_resupply":
                continue
            times = [asset_time.parse_instant(s.received_at, did) for s in sources.get(did, ())
                     if s.period == job.period.name]
            if not (any(t < at for t in times) and any(t > at for t in times)):
                raise CannotGenerate(
                    f"{hit[0].scenario_id}: {did}'s {job.period.name} supply is not resupplied "
                    f"after the release at {at.isoformat()} - the same-round red it shows "
                    f"would not be there; nothing was written")


PROVIDER = LinkageProducts()
