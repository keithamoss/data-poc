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
round, before its 18:00 due time (PROVISIONAL; Keith 2026-10-30, moved from 14:00
because Emergency Department's files land 15:00 to 17:00) and after the
arrivals it reads. A replay's invented promotion lag for a supply this
product reads ends before this delivery's receipt (promotion.next_receipt),
so an ordinary quarter's supply is promoted when the release is checked.

SYNTHETIC ONLY: every key is a scrambled token from this provider's seed.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, time, timedelta

from generator.collections.base import Job, Plan, Provider

DATASET_ID = "linkage-keys"
TABLE = "linkage_keys"
FILE = f"{TABLE}.csv"
#: id_2 IS EVERY FILE'S, BLANK ORDINARILY (REQ-GEN-335 (c), PROVISIONAL): every
#: linked dataset declares one identifier, so a surplus one needs a column to
#: arrive in - the contract's id_2, which check (4) reads.
COLUMNS = ["linkage_key", "dataset", "id_1", "id_2"]

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


def _ids(rows, column: str) -> list[str]:
    """A source supply's identifier values as text, as the checks cast them -
    null and blank ones dropped, since they can match no linkage row."""
    values = rows[column]
    out = [str(v) for v in values[values.notna()].tolist()]
    return [v for v in out if v.strip() != ""]


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
    by = {}
    for name, did in parsed:
        by.setdefault(name, []).append(did)
    frames, sources = [], {}
    for did, code, cols in linked():
        rows = sources_before.get(did)
        if rows is None:
            continue
        source = _ids(rows, cols[0])
        sources[did] = (code, source)
        band = (COVERAGE["amber"] if did in by.get("coverage_amber", ())
                else COVERAGE["red"] if did in by.get("coverage_red", ())
                else COVERAGE["ordinary"])
        ids = _link(source, band, rng, f"{where}, {did}")
        frames.append(pd.DataFrame({"linkage_key": [_token(code, v) for v in ids],
                                    "dataset": code, "id_1": ids, "id_2": ""}))
    df = (pd.concat(frames, ignore_index=True) if frames
          else pd.DataFrame(columns=COLUMNS))
    for name, did in parsed:
        if did is not None and did not in sources:
            raise CannotGenerate(f"{where}: row fault {name}@{did} - the release describes no "
                                 f"{did} supply in its quarter; nothing was written")
    df = _apply_faults(df, parsed, sources, rng, where)
    return df[COLUMNS].reset_index(drop=True)


def _apply_faults(df, parsed, sources, rng, where):
    import pandas as pd

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
            others = df.loc[(df["dataset"] == df.at[k, "dataset"]) & (df.index != k), "id_1"]
            df.loc[k, "id_2"] = others.iloc[0] if len(others) else f"{df.at[k, 'id_1']}-2"
        elif name == "double_link":
            k = one_row(did)
            twin = df.loc[[k]].copy()
            twin["linkage_key"] = _token(twin.iloc[0]["dataset"], f"{twin.iloc[0]['id_1']}#2")
            df = pd.concat([df, twin], ignore_index=True)
        elif name == "dangling_id":
            code, source = sources[did]
            value = f"{source[int(rng.integers(len(source)))]}9"
            if value in set(source):
                raise CannotGenerate(f"{where}: the dangling identifier {value!r} matches a "
                                     f"{did} record; nothing was written")
            df = pd.concat([df, pd.DataFrame({"linkage_key": [_token(code, value)],
                                              "dataset": [code], "id_1": [value],
                                              "id_2": [""]})], ignore_index=True)
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
    collection_id = "linkage-products"
    dataset_id = DATASET_ID
    amber_dataset = DATASET_ID
    seed_ranges = ((70_000, 71_000),)
    generating_note = "one linkage release a quarter"

    @property
    def depends_on(self) -> tuple[str, ...]:
        from qa_tools.common import hierarchy

        out = []
        for did, _code, _cols in linked():
            coll = hierarchy.dataset(did).collection_id
            if coll not in out:
                out.append(coll)
        return tuple(out)

    def seed_schedule(self) -> list[tuple[str, int, int]]:
        n = len(self._periods())
        return [("the key token", KEY_SEED, KEY_SEED), ("the run plan", RUN_PLAN_SEED,
                                                       RUN_PLAN_SEED)] + [
            (f"lp_slot_{i:02d}", BASE_SEED + i, BASE_SEED + i + RESUPPLY_SPAN)
            for i in range(1, n + 1)]

    def _sources(self) -> dict:
        """{dataset id: its generated supplies}, refused naming both where a
        provider this one depends on is absent (criterion 6)."""
        from generator import collections
        from generator.collections import base

        cache = getattr(self, "_cache", None)
        if cache is not None:
            return cache
        out = {}
        for did, _code, _cols in linked():
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

        wanted = {s.period for supplies in self._sources().values() for s in supplies}
        return [p for p in schedule.periods_for_dataset(DATASET_ID, until=get_anchor_date())
                if p.name in wanted]

    def generated_periods(self) -> list:
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
        severities = _place_reds(targeting.outside_hold(
            run_plan(len(periods)), [p.round_date for p in periods], DATASET_ID,
            keep_clean=frozenset({0}), unavailable=owned), owned)
        jobs = [Job(f"lp_slot_{i:02d}", BASE_SEED + i, sev, p)
                for i, (sev, p) in enumerate(zip(severities, periods), start=1)]
        plan = Plan(jobs=jobs, resolved=resolved, injected_by_period=injected,
                    state={"sources": sources, "suppressed": suppressed, "deliveries": {}})
        arrivals = {job.slot_id: self._arrivals(plan, job) for job in jobs}
        plan.state["arrivals"] = arrivals
        for injection, placement in resolved:
            for extra in injection.arrivals:
                for fault in extra.row_faults:
                    parse_fault(fault, injection.scenario_id)
        _refuse_unschedulable(jobs, sources, arrivals)
        _refuse_unmet_preconditions(jobs, sources, arrivals, injected)
        # EVERY RELEASE BUILT ONCE BEFORE THE FIRST WRITE (REQ-GEN-335
        # criterion 5): a fault that cannot be placed refuses here.
        plan.state["rows"] = {job.slot_id: [self._rows(plan, job, n) for n in
                                            range(len(arrivals[job.slot_id]))]
                              for job in jobs}
        return plan

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

        arrivals = plan.state["arrivals"][job.slot_id]
        if not arrivals:
            return None  # a scenario's quarter with no release at all ((k))
        return [Delivery(received_date=asset_time.local_date(at), severity=sev,
                         payload=plan.state["rows"][job.slot_id][n])
                for n, (at, _faults, sev) in enumerate(arrivals)]

    def entries(self, plan: Plan, job: Job, deliveries: list, run_index_start: int) -> list[dict]:
        return [{"run_id": f"{self.run_prefix}{run_index_start + n:03d}",
                 "run_index": run_index_start + n, "slot_id": job.slot_id,
                 "period": job.period.name, "received_at": None,
                 "dirty_severity": d.severity, "seed": job.seed,
                 "row_counts": {TABLE: int(len(d.payload))}}
                for n, d in enumerate(deliveries, start=1)]

    def received_at(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict) -> str:
        from qa_tools.common import asset_time

        return asset_time.isoformat(plan.state["arrivals"][job.slot_id][n - 1][0])

    def files(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict, name: str):
        from qa_tools.common import asset_time

        plan.state["deliveries"].setdefault(job.period.name, []).append(name)
        return ({FILE: delivery_obj.payload[COLUMNS].to_csv(index=False)},
                asset_time.parse_instant(entry["received_at"], entry["run_id"]))

    def describe(self, entry: dict, delivery_obj) -> str:
        return f"{entry['row_counts'][TABLE]:6d} linkage keys"

    def extra_placements(self, plan: Plan) -> list:
        """(j), NAMED, NOT PLANTED (REQ-GEN-335 criterion 7)."""
        return named_placements(self, plan)


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


def _refuse_unschedulable(jobs, sources, arrivals) -> None:
    """Criteria 12 and 13, before anything is written: each quarter's release
    arrives after the same quarter's ordinary first supply of each linked
    dataset received that day, its promotion taking effect before the release
    by the one function the gate uses (promotion.effective_at_for, capped at
    the release); and no release shares a receipt instant with any supply it
    reads."""
    from qa_tools.common import asset_time, promotion

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
        if not arrivals[job.slot_id]:
            continue
        at = arrivals[job.slot_id][0][0]
        for did, supplies in sources.items():
            mine = [s for s in supplies if s.period == job.period.name]
            if not mine:
                continue
            first = asset_time.parse_instant(mine[0].received_at, did)
            if asset_time.local_date(first) != job.period.round_date:
                continue        # filed a round earlier, as Child Protection's are
            took = promotion.effective_at_for(first, now=at, seed=did, before=at)
            if first >= at or took >= at:
                raise CannotGenerate(
                    f"the {job.period.name} linkage release ({at.isoformat()}) cannot be "
                    f"received after {did}'s promotion for that quarter takes effect "
                    f"({took.isoformat()}) and within its due time - nothing was written")


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
