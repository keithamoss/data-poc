"""Every check's warn and fail band, read from the committed definitions the
four tools run (REQ-GEN-183 criteria 1-7, 13, 14).

WHY. The synthetic generator has to make a supply land on a verdict - amber,
say - by construction rather than by a 25-minute rebuild to find out
(REQ-GEN-184). To do that it must know, for each rule, where every tool that
implements it warns and where it fails. That knowledge already exists, in each
tool's own definitions; a second copy for the generator would drift (Keith,
2026-10-11: read the bands from each tool's own files).

A RULE IS THE CHECKS THAT IMPLEMENT IT ACROSS TOOLS. Checks sharing an
authored name are one rule, whatever column each hangs on; a check with no
name is grouped by dataset, column, category and what it measures (Keith,
2026-10-11, post-build-review #153 - grouping by column alone put the
escalation-completeness business rule in with notification_id's nulls, and
four file checks in one rule). Nothing new is authored. The same rule commonly runs
in up to four tools with different units and bounds, so its AMBER BAND is the
intersection: the metric values at which no implementing check fails and at
least one warns, honouring each tool's own unit and comparison operator. At
exactly 35% a contract's `mustBeLessThan 35` fails where Soda's `> 35%` does
not, and that difference is kept rather than smoothed over.

SINGLE-TIER (criterion 3) is a check that cannot warn without failing: a dbt
test whose warn and error conditions coincide (dbt defaults both to `!= 0`, so
one with only `error_if: ">5"` warns from 1 to 5), every contract rule of
severity error, every SQL-bodied check unless it states a band of its own.

EACH TOOL'S OWN ARITHMETIC: Soda rounds a percentage to two places before
comparing it (derived_metric.py), and a dbt `unique` test whose fail_calc
sums n_records counts the ROWS in duplicated groups where Soda and the
contract count the duplicated KEYS - a different quantity, so never one rule.

FAIL LOUDLY, NEVER DEFAULT (criterion 4): a threshold this cannot parse
raises, naming the check and its file. plans/qa-pipeline.md item 74 is the
reason - a missing fail threshold once defaulted to 0 and turned a check red
on almost every run.

CONFIGURATION ONLY (criterion 13): committed files and one Python module of
constants. No database, nothing under data/.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from qa_tools.common import config_yaml

ROOT = Path(__file__).resolve().parent.parent.parent

FILE_CHECKS = "contract/file-checks.yaml"

#: Units a bound is stated in. A rule mixing ROWS and PERCENT is compared at
#: a given row count; TABLE_ROWS bounds the table's size itself; RATIO and
#: DROP are the cross-supply measures Evidently computes.
ROWS, PERCENT, TABLE_ROWS, RATIO, DROP, FILE = (
    "rows", "percent", "table rows", "ratio", "drop", "file")
#: dbt's `unique` with fail_calc sum(n_records): every row of a duplicated
#: group, so two per duplicated pair - not the key count Soda and the
#: contract use.
DUP_ROWS = "rows in duplicated groups"


class CatalogueError(ValueError):
    """A threshold this cannot read - never a guessed bound."""


@dataclass(frozen=True)
class Bound:
    """`metric <op> value` is the condition the bound trips on."""

    op: str
    value: float
    unit: str

    def trips(self, metric: float) -> bool:
        return {">": metric > self.value, ">=": metric >= self.value,
                "<": metric < self.value, "<=": metric <= self.value,
                "=": metric == self.value, "!=": metric != self.value}[self.op]

    def text(self) -> str:
        v = int(self.value) if float(self.value).is_integer() else self.value
        return f"{self.op} {v}{'%' if self.unit == PERCENT else ''}"


@dataclass(frozen=True)
class Check:
    check_id: str
    tool: str
    dataset_id: str
    column: str | None
    category: str
    metric: str
    source: str
    warn: tuple[Bound, ...] = ()
    fail: tuple[Bound, ...] = ()
    reads_columns: tuple[str, ...] = ()
    name: str | None = None

    @property
    def single_tier(self) -> bool:
        return not self.warn and bool(self.fail)

    @property
    def unit(self) -> str:
        return (self.fail or self.warn)[0].unit if (self.fail or self.warn) else ROWS

    @property
    def measure(self) -> str:
        """What quantity it bounds: bad rows (whether stated as a count or a
        percentage, the same quantity at a given row count), the table's
        size, a drift ratio, a proportional drop, or the file."""
        return ROWS if self.unit in (ROWS, PERCENT) else self.unit

    def _value(self, bound: Bound, bad: float, rows: int) -> float:
        if bound.unit == PERCENT:
            pct = 100.0 * bad / rows if rows else 0.0
            # Soda compares the percentage rounded to two places.
            return round(pct, 2) if self.tool == "soda" else pct
        return bad

    def fails(self, bad: float, rows: int) -> bool:
        return any(b.trips(self._value(b, bad, rows)) for b in self.fail)

    def warns(self, bad: float, rows: int) -> bool:
        return any(b.trips(self._value(b, bad, rows)) for b in self.warn)


@dataclass
class Rule:
    dataset_id: str
    column: str | None
    category: str
    #: Within one dataset, column and category, checks of a different
    #: quantity are different rules: a table's size and its drop against the
    #: last supply share a category and no unit.
    measure: str = ROWS
    checks: list[Check] = field(default_factory=list)
    #: The authored name the checks share, for a rule grouped by it.
    name: str | None = None

    def _continuous(self) -> bool:
        return all(c.unit in (RATIO, DROP) for c in self.checks)

    def _domain(self, rows: int) -> range:
        if all(c.unit == TABLE_ROWS for c in self.checks):
            top = max((b.value for c in self.checks for b in c.warn + c.fail), default=0)
            return range(0, int(top * 2) + 2)
        return range(0, rows + 1)

    def amber(self, rows: int) -> list[tuple]:
        """The ranges of the metric where no check fails and one warns, at
        `rows` rows - bad rows for a row-or-percent rule, the table's size
        for a size rule, the ratio itself for a cross-supply one."""
        if self._continuous():
            warns = [b.value for c in self.checks for b in c.warn]
            fails = [b.value for c in self.checks for b in c.fail]
            lo, hi = (max(warns) if warns else None), (min(fails) if fails else math.inf)
            return [(lo, hi)] if lo is not None and lo < hi else []
        out: list[tuple] = []
        domain = self._domain(rows)
        for x in domain:
            size = x if all(c.unit == TABLE_ROWS for c in self.checks) else rows
            ok = not any(c.fails(x, size) for c in self.checks) and \
                any(c.warns(x, size) for c in self.checks)
            if ok and out and out[-1][1] == x - 1:
                out[-1] = (out[-1][0], x)
            elif ok:
                out.append((x, x))
        # A SIZE BAND NOTHING FAILS ABOVE IS OPEN-ENDED: the search stops
        # somewhere, the band does not (post-build-review #153).
        if out and out[-1][1] == domain[-1] and not any(
                b.op in (">", ">=", "!=") for c in self.checks for b in c.fail):
            out[-1] = (out[-1][0], math.inf)
        return out

    def closed_by(self, rows: int) -> list[str]:
        """Where there is no amber band, the checks that close it: those
        failing where the first warning would be, or - with no warning at
        all - every check, each single-tier."""
        if self._continuous():
            return [c.check_id for c in self.checks if c.fail]
        domain = self._domain(rows)
        size_rule = all(c.unit == TABLE_ROWS for c in self.checks)
        for x in domain:
            size = x if size_rule else rows
            if any(c.warns(x, size) for c in self.checks):
                return [c.check_id for c in self.checks if c.fails(x, size)]
        return [c.check_id for c in self.checks]


@dataclass
class Catalogue:
    checks: list[Check]

    def rules(self) -> list[Rule]:
        by: dict[tuple, Rule] = {}
        for c in self.checks:
            if c.name:
                key = ("name", c.dataset_id, c.name, c.measure)
                rule = by.setdefault(key, Rule(c.dataset_id, c.column, c.category,
                                               c.measure, name=c.name))
            else:
                key = (c.dataset_id, c.column, c.category, c.measure)
                rule = by.setdefault(key, Rule(*key))
            rule.checks.append(c)
        for rule in by.values():
            if rule.name:
                # A named rule can hang on several columns - dbt states a
                # date ordering at table level - so it takes the commonest.
                cols = [c.column for c in rule.checks if c.column]
                rule.column = max(set(cols), key=cols.count) if cols else None
        return list(by.values())

    def rule(self, dataset_id: str, column: str | None, category: str,
             measure: str = ROWS) -> Rule:
        """The unnamed rule on a column; failing that, the one named rule
        there is on it."""
        match = [r for r in self.rules()
                 if (r.dataset_id, r.column, r.category, r.measure)
                 == (dataset_id, column, category, measure)]
        found = [r for r in match if not r.name] or (match if len(match) == 1 else [])
        if not found:
            raise KeyError(f"no rule for {dataset_id} {column} {category}")
        return found[0]

    def named(self, dataset_id: str, name: str) -> Rule:
        found = [r for r in self.rules() if (r.dataset_id, r.name) == (dataset_id, name)]
        if not found:
            raise KeyError(f"no rule named {name!r} on {dataset_id}")
        return found[0]

    def single_tier_readers(self, dataset_id: str) -> dict[str, list[str]]:
        """{column: [check_id, ...]} - every single-tier check reading each
        column of this dataset's table, by its own column or reads_columns."""
        from qa_tools.common import hierarchy

        table = hierarchy.dataset(dataset_id).table
        out: dict[str, set[str]] = {}
        for c in self.checks:
            if not c.single_tier:
                continue
            cols = {e.split(".", 1)[1] for e in c.reads_columns if e.startswith(table + ".")}
            if c.dataset_id == dataset_id and c.column:
                cols.add(c.column)
            for col in cols:
                out.setdefault(col, set()).add(c.check_id)
        return {k: sorted(v) for k, v in sorted(out.items())}


# ---- reading each tool's own definitions ---------------------------------

_SODA_WHEN = re.compile(r"when\s*(>=|<=|!=|>|<|=)\s*(-?\d+(?:\.\d+)?)\s*(%)?")
_DBT_COND = re.compile(r"^\s*(>=|<=|!=|>|<|=)\s*(\d+(?:\.\d+)?)\s*$")


def _soda_when(text, unit: str, where: str) -> tuple[Bound, ...]:
    if text is None:
        return ()
    text = str(text)
    found = _SODA_WHEN.findall(text)
    if not found or _SODA_WHEN.sub("", text).strip():
        raise CatalogueError(f"{where}: cannot read the threshold {text!r}")
    return tuple(Bound(op, float(v), PERCENT if pct else unit) for op, v, pct in found)


def soda_bounds(path: Path) -> dict[str, tuple]:
    """{check_id: (metric, warn, fail)} for every check in a Soda file."""
    doc = config_yaml.parse(Path(path).read_text()) or {}
    out = {}
    for key, checks in doc.items():
        if not str(key).startswith("checks for"):
            continue
        for check in checks or []:
            (expr, cfg), = check.items()
            if expr == "attributes":
                continue
            cfg = cfg or {}
            check_id = (cfg.get("attributes") or {}).get("check_id")
            where = f"{check_id} ({path})"
            expr = str(expr)
            m = re.match(r"^(missing|invalid|duplicate)_(count|percent)\(", expr)
            if m:
                metric, unit = f"{m.group(1)}_{m.group(2)}", (
                    PERCENT if m.group(2) == "percent" else ROWS)
            elif expr.startswith("row_count"):
                metric, unit = "row_count", TABLE_ROWS
            elif expr.startswith("failed rows") or expr.startswith("values in"):
                metric, unit = ("failed_rows" if expr.startswith("failed") else "reference"), ROWS
            else:
                raise CatalogueError(f"{where}: no band can be read from a {expr!r} check")
            warn = _soda_when(cfg.get("warn"), unit, where)
            fail = _soda_when(cfg.get("fail"), unit, where)
            if not warn and not fail:
                if metric not in ("failed_rows", "reference"):
                    raise CatalogueError(f"{where}: a {metric} check states no threshold")
                fail = (Bound(">", 0, ROWS),)
            out[check_id] = (metric, warn, fail)
    return out


def _dbt_cond(text, where: str, unit: str = ROWS) -> tuple[Bound, ...]:
    m = _DBT_COND.match(str(text))
    if not m:
        raise CatalogueError(f"{where}: cannot read the dbt condition {text!r}")
    return (Bound(m.group(1), float(m.group(2)), unit),)


def _dbt_one(metric: str, cfg: dict, meta: dict, path) -> tuple[str, tuple]:
    conf = {**cfg, **(cfg.get("config") or {})}
    meta = meta or conf.get("meta") or {}
    check_id = meta.get("check_id")
    where = f"{check_id} ({path})"
    severity = str(conf.get("severity") or "error").lower()
    unit = DUP_ROWS if metric == "unique" and "n_records" in str(conf.get("fail_calc")) \
        else ROWS
    # dbt defaults BOTH warn_if and error_if to "!= 0" (dbt-core's
    # TestConfig). With neither stated they coincide, so the test fails on
    # any violation; with only error_if stated, the default warn_if warns
    # below it.
    if conf.get("warn_if"):
        warn = _dbt_cond(conf["warn_if"], where, unit)
    elif conf.get("error_if"):
        warn = (Bound("!=", 0, unit),)
    else:
        warn = ()
    fail = _dbt_cond(conf.get("error_if") or ">0", where, unit)
    if severity == "warn":
        warn, fail = warn or (Bound(">", 0, unit),), ()
    return check_id, (metric, warn, fail)


def dbt_bounds(path: Path) -> dict[str, tuple]:
    doc = config_yaml.parse(Path(path).read_text()) or {}
    out = {}
    for entry in doc.get("tests") or []:
        conf = entry.get("config") or {}
        cid, val = _dbt_one(str(entry.get("name")), conf, conf.get("meta") or {}, path)
        out[cid] = val
    for model in doc.get("models") or []:
        tests = [t for t in model.get("tests") or []]
        for col in model.get("columns") or []:
            tests += col.get("tests") or []
        for test in tests:
            if not isinstance(test, dict):
                continue
            (kind, cfg), = test.items()
            cfg = cfg or {}
            cid, val = _dbt_one(str(kind), cfg, cfg.get("meta") or {}, path)
            out[cid] = val
    return out


_MUST = {"mustBe": "!=", "mustBeLessThan": ">=", "mustBeLessOrEqualTo": ">",
         "mustBeGreaterThan": "<=", "mustBeGreaterOrEqualTo": "<"}


def contract_bounds(path: Path) -> dict[str, tuple]:
    doc = config_yaml.parse(Path(path).read_text()) or {}
    out = {}
    for table in doc.get("schema") or []:
        rules = list(table.get("quality") or [])
        for prop in table.get("properties") or []:
            rules += prop.get("quality") or []
        for rule in rules:
            props = {c.get("property"): c.get("value") for c in rule.get("customProperties") or []}
            check_id = props.get("check_id")
            where = f"{check_id} ({path})"
            metric = rule.get("metric") or rule.get("type") or "?"
            unit = TABLE_ROWS if metric == "rowCount" else (
                PERCENT if rule.get("unit") == "percent" else ROWS)
            bounds: list[Bound] = []
            for key, value in rule.items():
                if key == "mustBeBetween":
                    lo, hi = value
                    bounds += [Bound("<", float(lo), unit), Bound(">", float(hi), unit)]
                elif key in _MUST:
                    bounds.append(Bound(_MUST[key], float(value), unit))
                elif key.startswith("must"):
                    raise CatalogueError(f"{where}: cannot read {key}")
            if not bounds:
                raise CatalogueError(f"{where}: the rule states no threshold")
            severity = str(rule.get("severity") or "error").lower()
            if severity == "warning":
                out[check_id] = (metric, tuple(bounds), ())
            elif severity == "error":
                out[check_id] = (metric, (), tuple(bounds))
            else:
                raise CatalogueError(f"{where}: severity {severity!r} is neither error "
                                     f"nor warning")
    return out


def evidently_bounds(check_ids=None) -> dict[str, tuple]:
    """Evidently's bands, read where they live (Keith, 2026-10-11) - since
    REQ-QAC-223, each check's OWN entry in its collection's Evidently check
    file (REQ-QAC-241): its method, and its warn and fail bands, each
    tripping on a strict `>`. A check whose method is neither psi nor
    row_drop is refused rather than given some band."""
    from qa_tools import collections
    from qa_tools.common import check_lifecycle

    entries = {}
    for rel in collections.check_files("evidently"):
        entries.update(check_lifecycle.load_evidently_checks(ROOT / rel))
    if check_ids is None:
        check_ids = list(entries)
    out = {}
    for check_id in check_ids:
        entry = entries.get(check_id) or {}
        unit = {"psi": RATIO, "row_drop": DROP}.get(entry.get("method"))
        if unit is None:
            raise CatalogueError(f"{check_id}: an Evidently check whose method is neither psi nor "
                                 f"row_drop - no band is known for it")
        out[check_id] = (entry["method"], (Bound(">", entry["warn_threshold"], unit),),
                         (Bound(">", entry["fail_threshold"], unit),))
    return out


def file_bounds(metadata, doc=None) -> dict[str, tuple]:
    """A file check fails (severity failure) or only warns (warning) on any
    problem with the file - it has no band of its own. One file-checks.yaml
    does not name, or names with another severity, is refused."""
    if doc is None:
        doc = config_yaml.parse((ROOT / FILE_CHECKS).read_text()) or {}
    severity = {str(c.get("check")): str(c.get("severity")) for c in doc.get("checks") or []}
    out = {}
    for m in metadata:
        if m.tool != "file":
            continue
        name = m.check_id.rsplit(".", 1)[-1].removesuffix("_file")
        trip = (Bound(">", 0, FILE),)
        if severity.get(name) == "warning":
            out[m.check_id] = ("file", trip, ())
        elif severity.get(name) == "failure":
            out[m.check_id] = ("file", (), trip)
        else:
            raise CatalogueError(f"{m.check_id} ({FILE_CHECKS}): {name} has severity "
                                 f"{severity.get(name)!r}, neither failure nor warning")
    return out


_SODA_REFERENCE = re.compile(
    r"^values in \((\w+)\) must exist in (\w+) \((\w+)\)")


def soda_reference_reads(path: Path) -> dict[str, tuple[str, str]]:
    """{check_id: (child table.column, parent table.column)} for each Soda
    reference check - its columns are structured fields of the check
    itself, so it declares no reads_columns, and without this the parent's
    column would not list it among its single-tier readers."""
    doc = config_yaml.parse(Path(path).read_text()) or {}
    out = {}
    for key, checks in doc.items():
        if not str(key).startswith("checks for"):
            continue
        table = str(key).removeprefix("checks for").strip()
        for check in checks or []:
            (expr, cfg), = check.items()
            m = _SODA_REFERENCE.match(str(expr))
            if m:
                check_id = ((cfg or {}).get("attributes") or {}).get("check_id")
                out[check_id] = (f"{table}.{m.group(1)}", f"{m.group(2)}.{m.group(3)}")
    return out


def catalogue() -> Catalogue:
    """Every check in force, with its bands and what it reads (criteria 1, 2,
    5). Joined to check_lifecycle's own metadata, so a check is catalogued
    exactly when the lifecycle gate sees it."""
    from qa_tools import collections
    from qa_tools.common import validate_check_lifecycle as vcl

    metadata = [m for m in vcl.collect_checks(None) if not m.retired_as_of]
    bounds: dict[str, tuple] = {}
    references: dict[str, tuple[str, str]] = {}
    # Every collection's sources, from the registry (REQ-QAC-241).
    for rel in collections.check_files("soda"):
        bounds.update(soda_bounds(ROOT / rel))
        references.update(soda_reference_reads(ROOT / rel))
    for c in collections.all_collections():
        bounds.update(dbt_bounds(ROOT / c.dbt_schema))
    for rel in collections.check_files("contract"):
        bounds.update(contract_bounds(ROOT / rel))
    bounds.update(evidently_bounds())
    bounds.update(file_bounds(metadata))
    checks = []
    for m in metadata:
        if m.check_id not in bounds:
            raise CatalogueError(f"{m.check_id} ({m.source_file}): no band could be read")
        metric, warn, fail = bounds[m.check_id]
        parts = m.check_id.split(".")
        checks.append(Check(
            check_id=m.check_id, tool=m.tool, dataset_id=parts[3],
            column=parts[4] if len(parts) == 6 else None, category=m.category, metric=metric,
            source=m.source_file, warn=tuple(warn), fail=tuple(fail),
            reads_columns=tuple(m.reads_columns) + references.get(m.check_id, ()),
            name=m.name))
    return Catalogue(checks)


def default_rows(dataset_id: str, cat: Catalogue) -> int:
    """The row count a listing is computed at when none is given: the lower
    edge of the contract's own row-count band for the dataset - the smallest
    supply it calls ordinary. Where it states none, refused: a guessed size
    gives a guessed band."""
    for c in cat.checks:
        if c.dataset_id == dataset_id and c.metric == "rowCount":
            lows = [b.value for b in c.warn + c.fail if b.op == "<"]
            if lows:
                return int(max(lows))
    raise CatalogueError(f"{dataset_id}: its contract states no ordinary size to work "
                         f"the bands out at - pass --rows")
