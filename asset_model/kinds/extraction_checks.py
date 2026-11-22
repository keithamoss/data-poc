"""An extraction's two check layers, as each real tool's own configuration
(REQ-QAC-441).

TWO LAYERS, SEPARATE FROM EVERY RECURRING DATASET'S CHECKS (criteria 1 to 7).
The RECIPE LAYER is derived from what the recipe declares - each column's
type, each table's cohort bounds and its expected row count - and is
generated into the one-off's folder when it is opened (REQ-PIPE-440 criterion
4). The DEFAULT LAYER is defined once, in the kind's template
(one-offs/extraction/_template/default-checks.yaml), and is read from it at
each load (REQ-PIPE-440 criterion 13): never copied into a one-off's folder.
Neither imports or shares anything from an enduring asset's check files.

STATED AS ASSERTIONS, EVALUATED BY ALL FOUR TOOLS AS EACH FITS (Keith
2026-11-22: 'all four tools evaluate a one-off, as for an enduring asset').
Which tool evaluates which assertion is this module's table, ASSERTION_TOOLS
below - the requirement names none (its MAINTAINABILITY NFR). Two default
assertions belong to no tool: a declared table that never arrived and an
undeclared file are facts about the package, so the load writes them
(qa_tools/common/one_off_package.py) as the file checks' results are
written.

EVERY CHECK CARRIES THE THREE PROSE FIELDS of docs/check-authoring-rules.md -
the recipe layer's words are written here, the default layer's in the
template, so a change to either reaches every extraction generated (recipe)
or loaded (default) after it.

CONFIGURATION ONLY: it builds dictionaries from the declarations a one-off's
data-asset.yaml carries. It runs no tool, opens no database and reads no file
but the template it is handed.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

#: The template file the default layer is defined in (criterion 1).
DEFAULT_LAYER_FILE = "default-checks.yaml"

#: Every assertion and the tools that evaluate it. `load` is the load's own
#: record of the package, not a tool's (criterion 3).
ASSERTION_TOOLS = {
    # The default layer (criterion 2).
    "table_arrived": ("load",),
    "undeclared_file": ("load",),
    "columns_arrived": ("soda",),
    "identifier_not_null": ("dbt", "soda", "datacontract", "evidently"),
    # The recipe layer (criteria 4 and 5).
    "declared_type": ("dbt", "soda", "datacontract"),
    "cohort_bounds": ("dbt", "soda", "datacontract"),
    "expected_rows": ("soda", "datacontract", "evidently"),
}
DEFAULT_ASSERTIONS = ("table_arrived", "undeclared_file", "columns_arrived",
                      "identifier_not_null")
RECIPE_ASSERTIONS = ("declared_type", "cohort_bounds", "expected_rows")
#: Each assertion's check name, the segment before the tool in its check id.
CHECK_NAME = {"table_arrived": "table_arrived", "undeclared_file": "undeclared_file",
              "columns_arrived": "columns_arrived", "identifier_not_null": "identifier_not_null",
              "declared_type": "declared_type", "cohort_bounds": "cohort_bounds",
              "expected_rows": "expected_rows"}

#: How PostgreSQL is asked whether a value reads as a declared type
#: (pg_input_is_valid, PostgreSQL 16). A string always does, so it has no
#: type check.
PG_TYPE = {"integer": "bigint", "number": "numeric", "date": "date",
           "timestamp": "timestamp", "boolean": "boolean"}

#: THE RECIPE LAYER'S WORDS (docs/check-authoring-rules.md): no figure, no
#: tool, no column of the check's own, 'supply' for a delivery.
RECIPE_WORDS = {
    "declared_type": {
        "name": "Declared type", "category": "conformity",
        "description": "Every value must read as the type the recipe declares.",
        "failure_indicates": "self-evident"},
    "cohort_bounds": {
        "name": "Inside the cohort", "category": "conformity",
        "description": "Every value must fall inside the cohort bounds the recipe declares.",
        "failure_indicates": ("The supply was drawn with a wider or different filter than "
                              "the recipe describes.")},
    "expected_rows": {
        "name": "Expected row count", "category": "completeness",
        "description": ("The supply must hold exactly as many rows as the recipe "
                        "declares."),
        "failure_indicates": ("The supply was cut short, or was drawn with a different "
                              "filter than the recipe describes.")},
}


class TemplateRefused(ValueError):
    """The kind's default layer cannot be read. Its message names every
    problem."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("the default check layer cannot be read:\n"
                         + "\n".join(f"  - {p}" for p in self.problems))


# ---- what a one-off declares ----------------------------------------------

@dataclass(frozen=True)
class Table:
    agency_id: str
    collection_id: str
    dataset_id: str
    table: str
    file: str
    derived: bool
    columns: tuple            # ({name, type, primary_identifier}, ...)
    cohort: tuple             # ({column, lower, upper}, ...)
    expected_rows: int | None

    @property
    def identifiers(self) -> list[str]:
        return [c["name"] for c in self.columns if c["primary_identifier"]]


def declared(data_asset: dict, calendar: dict | None = None) -> list[Table]:
    """Every table a one-off declares, read from its data-asset.yaml - what
    the recipe declared, carried into the folder (REQ-PIPE-440 criterion 2) -
    and its calendar.yaml for `derived` (REQ-PIPE-438 criterion 2)."""
    derived = {d["id"] for d in (calendar or {}).get("datasets") or [] if d.get("derived")}
    out = []
    for agency in data_asset["hierarchy"]["agencies"]:
        for coll in agency["collections"]:
            for ds in coll["datasets"]:
                out.append(Table(
                    agency_id=agency["id"], collection_id=coll["id"], dataset_id=ds["id"],
                    table=ds["table"], file=_file_of(ds["arrival_pattern"]),
                    derived=ds["id"] in derived,
                    columns=tuple(ds.get("columns") or ()),
                    cohort=tuple(ds.get("cohort") or ()),
                    expected_rows=ds.get("expected_rows")))
    return out


def _file_of(pattern: str) -> str:
    """The declared file name an arrival pattern matches - the generator
    writes re.escape(file), so this undoes exactly that."""
    import re

    return re.sub(r"\\(.)", r"\1", pattern)


def check_id(asset_id: str, t: Table, assertion: str, tool: str,
             column: str | None = None) -> str:
    parts = [asset_id, t.agency_id, t.collection_id, t.dataset_id]
    if column is not None:
        parts.append(column)
    return ".".join(parts) + f".{CHECK_NAME[assertion]}_{tool}"


# ---- the default layer's template ------------------------------------------

def read_template(template: Path) -> dict[str, dict]:
    """{assertion: its entry} from the kind's template, refused naming every
    problem. Every default assertion must be defined, with the prose fields
    and lifecycle metadata every check carries, and no tool its assertion
    does not take."""
    from asset_model import check_lifecycle, config_yaml

    path = Path(template) / DEFAULT_LAYER_FILE
    if not path.is_file():
        raise TemplateRefused([f"{path} is missing - the kind's default check layer lives "
                               f"there and is read at each load."])
    doc = config_yaml.load(path) or {}
    problems, found = [], {}
    for entry in doc.get("checks") or []:
        a = entry.get("assertion")
        if a not in DEFAULT_ASSERTIONS:
            problems.append(f"{path}: {a!r} is not a default assertion "
                            f"({', '.join(DEFAULT_ASSERTIONS)}).")
            continue
        if a in found:
            problems.append(f"{path}: {a!r} is defined twice.")
        for key in ("name", "category", "introduced_date", "description", "failure_indicates"):
            if not str(entry.get(key) or "").strip():
                problems.append(f"{path}: {a!r} has no {key}.")
        if entry.get("category") not in check_lifecycle.CHECK_CATEGORIES:
            problems.append(f"{path}: {a!r} has category {entry.get('category')!r}.")
        tools = tuple(entry.get("tools") or ASSERTION_TOOLS[a])
        bad = [x for x in tools if x not in ASSERTION_TOOLS[a]]
        if bad:
            problems.append(f"{path}: {a!r} cannot be evaluated by {', '.join(bad)} "
                            f"(it takes {', '.join(ASSERTION_TOOLS[a])}).")
        found[a] = {**entry, "tools": tools}
    for a in DEFAULT_ASSERTIONS:
        if a not in found and not any(a in p for p in problems):
            problems.append(f"{path}: the default assertion {a!r} is not defined.")
    if problems:
        raise TemplateRefused(problems)
    return found


# ---- one layer, as each tool's configuration -------------------------------

@dataclass
class Layer:
    """One layer's checks for one collection, in each tool's own shape."""

    #: {table: {"fields": {column: [rule]}, "model": [rule]}} - ODCS quality.
    contract: dict = field(default_factory=dict)
    #: {table: [SodaCL check]}
    soda: dict = field(default_factory=dict)
    #: [Evidently check entry]
    evidently: list = field(default_factory=list)
    #: {table: {column: [dbt test]}}
    dbt: dict = field(default_factory=dict)

    def extend(self, other: "Layer") -> "Layer":
        out = copy.deepcopy(self)
        for t, spec in other.contract.items():
            mine = out.contract.setdefault(t, {"fields": {}, "model": []})
            for c, rules in spec["fields"].items():
                mine["fields"].setdefault(c, []).extend(copy.deepcopy(rules))
            mine["model"].extend(copy.deepcopy(spec["model"]))
        for t, checks in other.soda.items():
            out.soda.setdefault(t, []).extend(copy.deepcopy(checks))
        out.evidently.extend(copy.deepcopy(other.evidently))
        for t, cols in other.dbt.items():
            for c, tests in cols.items():
                out.dbt.setdefault(t, {}).setdefault(c, []).extend(copy.deepcopy(tests))
        return out


def _meta(cid: str, words: dict, introduced: str, *, reads_columns=None) -> dict:
    out = {"check_id": cid, "name": words["name"], "category": words["category"],
           "introduced_date": str(introduced),
           "description": words["description"].strip(),
           "failure_indicates": str(words["failure_indicates"]).strip()}
    if words.get("technical_note"):
        out["technical_note"] = str(words["technical_note"]).strip()
    if reads_columns is not None:
        out["reads_columns"] = list(reads_columns)
    out["changelog"] = list(words.get("changelog") or [])
    return out


def _odcs(cid: str, meta: dict, rule: dict) -> dict:
    props = [{"property": k, "value": (v if k != "changelog" else "[]")}
             for k, v in meta.items() if k != "category"]
    return {"id": cid.replace(".", ":"), **rule, "dimension": meta["category"],
            "severity": "error", "customProperties": props}


def _literal(value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def _key_select(t: Table) -> str:
    """The failing rows' keys a failed-rows query returns - the table's
    declared identifiers only, never row content (criterion 9)."""
    return ", ".join(f'"{c}"' for c in t.identifiers)


def _bounds_condition(column: str, bound: dict) -> str:
    parts = []
    if bound.get("lower") is not None:
        parts.append(f'"{column}" < {_literal(bound["lower"])}')
    if bound.get("upper") is not None:
        parts.append(f'"{column}" > {_literal(bound["upper"])}')
    return " OR ".join(parts)


def default_layer(asset_id: str, tables: list[Table], template: dict[str, dict]) -> dict[str, Layer]:
    """{collection id: Layer} of the default layer (criteria 1 to 3)."""
    out: dict[str, Layer] = {}
    for t in tables:
        layer = out.setdefault(t.collection_id, Layer())
        # table_arrived and undeclared_file are the one-off's own file checks
        # (qa_tools/common/one_off_checks.package_checks), not a tool's.
        entry = template["columns_arrived"]
        if "soda" in entry["tools"]:
            meta = _meta(check_id(asset_id, t, "columns_arrived", "soda"), entry,
                         entry["introduced_date"])
            layer.soda.setdefault(t.table, []).append({"schema": {
                "fail": {"when required column missing": [c["name"] for c in t.columns]},
                "attributes": meta}})
        entry = template["identifier_not_null"]
        for col in t.identifiers:
            introduced = entry["introduced_date"]
            if "dbt" in entry["tools"]:
                layer.dbt.setdefault(t.table, {}).setdefault(col, []).append({"not_null": {
                    "meta": (_meta(check_id(asset_id, t, "identifier_not_null", "dbt", col),
                                       entry, introduced))}})
            if "soda" in entry["tools"]:
                meta = _meta(check_id(asset_id, t, "identifier_not_null", "soda", col),
                             entry, introduced)
                layer.soda.setdefault(t.table, []).append({f"missing_count({col}) = 0": {
                    "samples limit": 5, "attributes": meta}})
            if "datacontract" in entry["tools"]:
                cid = check_id(asset_id, t, "identifier_not_null", "datacontract", col)
                layer.contract.setdefault(t.table, {"fields": {}, "model": []})["fields"] \
                    .setdefault(col, []).append(_odcs(cid, _meta(cid, entry, introduced),
                                                      {"metric": "nullValues", "mustBe": 0}))
            if "evidently" in entry["tools"]:
                cid = check_id(asset_id, t, "identifier_not_null", "evidently", col)
                layer.evidently.append({**_meta(cid, entry, introduced), "column": col,
                                        "method": "missing"})
    return out


def recipe_layer(asset_id: str, tables: list[Table], introduced: str) -> dict[str, Layer]:
    """{collection id: Layer} of the recipe layer (criteria 4 and 5)."""
    out: dict[str, Layer] = {}
    for t in tables:
        layer = out.setdefault(t.collection_id, Layer())
        contract = layer.contract.setdefault(t.table, {"fields": {}, "model": []})
        keys = _key_select(t)
        for col in t.columns:
            name, kind = col["name"], col["type"]
            if kind not in PG_TYPE:
                continue
            words = RECIPE_WORDS["declared_type"]
            bad = (f'"{name}" IS NOT NULL AND NOT pg_input_is_valid("{name}"::text, '
                   f"'{PG_TYPE[kind]}')")
            reads = [f"{t.table}.{name}"] + [f"{t.table}.{k}" for k in t.identifiers
                                             if k != name]
            layer.dbt.setdefault(t.table, {}).setdefault(name, []).append({
                "dbt_utils.expression_is_true": {
                    "expression": (f"is null or pg_input_is_valid(\"{name}\"::text, "
                                   f"'{PG_TYPE[kind]}')"),
                    "meta": (_meta(check_id(asset_id, t, "declared_type", "dbt", name),
                                       words, introduced, reads_columns=[f"{t.table}.{name}"]))}})
            if keys:
                meta = _meta(check_id(asset_id, t, "declared_type", "soda", name), words,
                             introduced, reads_columns=reads)
                layer.soda.setdefault(t.table, []).append({"failed rows": {
                    "name": f"{name} {words['name'].lower()}",
                    "fail query": f"SELECT {keys} FROM {t.table} WHERE {bad}",
                    "fail": "when > 0", "samples limit": 100000,
                    "attributes": meta}})
            cid = check_id(asset_id, t, "declared_type", "datacontract", name)
            contract["fields"].setdefault(name, []).append(_odcs(
                cid, _meta(cid, words, introduced, reads_columns=[f"{t.table}.{name}"]),
                {"type": "sql", "query": f"SELECT COUNT(*) FROM {{model}} WHERE {bad}",
                 "mustBe": 0}))
        for bound in t.cohort:
            name = bound["column"]
            condition = _bounds_condition(name, bound)
            if not condition:
                continue
            words = RECIPE_WORDS["cohort_bounds"]
            rng = {k: v for k, v in (("min_value", bound.get("lower")),
                                     ("max_value", bound.get("upper"))) if v is not None}
            layer.dbt.setdefault(t.table, {}).setdefault(name, []).append({
                "dbt_utils.accepted_range": {
                    **{k: (v if isinstance(v, (int, float)) else _literal(v))
                       for k, v in rng.items()},
                    "meta": (_meta(check_id(asset_id, t, "cohort_bounds", "dbt", name),
                                       words, introduced))}})
            reads = [f"{t.table}.{name}"] + [f"{t.table}.{k}" for k in t.identifiers
                                             if k != name]
            if keys:
                meta = _meta(check_id(asset_id, t, "cohort_bounds", "soda", name), words,
                             introduced, reads_columns=reads)
                layer.soda.setdefault(t.table, []).append({"failed rows": {
                    "name": f"{name} {words['name'].lower()}",
                    "fail query": f"SELECT {keys} FROM {t.table} WHERE {condition}",
                    "fail": "when > 0", "samples limit": 100000,
                    "attributes": meta}})
            cid = check_id(asset_id, t, "cohort_bounds", "datacontract", name)
            contract["fields"].setdefault(name, []).append(_odcs(
                cid, _meta(cid, words, introduced, reads_columns=[f"{t.table}.{name}"]),
                {"type": "sql", "query": f"SELECT COUNT(*) FROM {{model}} WHERE {condition}",
                 "mustBe": 0}))
        if t.expected_rows is not None:
            words = RECIPE_WORDS["expected_rows"]
            n = int(t.expected_rows)
            meta = _meta(check_id(asset_id, t, "expected_rows", "soda"), words, introduced)
            layer.soda.setdefault(t.table, []).append({f"row_count = {n}": {
                "attributes": meta}})
            cid = check_id(asset_id, t, "expected_rows", "datacontract")
            contract["model"].append(_odcs(cid, _meta(cid, words, introduced),
                                           {"metric": "rowCount", "mustBe": n}))
            cid = check_id(asset_id, t, "expected_rows", "evidently")
            layer.evidently.append({**_meta(cid, words, introduced), "method": "row_count",
                                    "table": t.table, "expected": n})
    return out


# ---- rendering a layer into each tool's file --------------------------------

def contract_doc(base: dict, layer: Layer) -> dict:
    """The collection's contract with the layer's quality rules on its
    schema - `base` is the contract the folder's generator writes."""
    doc = copy.deepcopy(base)
    for obj in doc["schema"]:
        spec = layer.contract.get(obj["name"])
        if not spec:
            continue
        for prop in obj["properties"]:
            rules = spec["fields"].get(prop["name"])
            if rules:
                prop.setdefault("quality", []).extend(copy.deepcopy(rules))
        if spec["model"]:
            obj.setdefault("quality", []).extend(copy.deepcopy(spec["model"]))
    return doc


def soda_doc(layer: Layer, tables: list[str]) -> dict:
    return {f"checks for {t}": copy.deepcopy(layer.soda[t]) for t in tables if layer.soda.get(t)}


def evidently_doc(layer: Layer) -> dict:
    checks = []
    for e in layer.evidently:
        e = dict(e)
        e.pop("name", None)
        checks.append(e)
    return {"checks": checks}


def dbt_schema_doc(layer: Layer, tables: list[str]) -> dict:
    models = []
    for t in tables:
        cols = layer.dbt.get(t) or {}
        models.append({"name": f"stg_{t}",
                       "columns": [{"name": c, "tests": copy.deepcopy(tests)}
                                   for c, tests in cols.items()]})
    return {"version": 2, "models": models}


#: The retired siblings every collection's checks carry (REQ-QAC-241): empty,
#: since nothing in a one-off is ever retired.
RETIRED = {"contract": {"schema": []}, "soda": {}, "evidently": {"checks": []},
           "dbt": {"version": 2, "models": []}}
