"""Opening an extraction generates one-offs/extraction/<id>/ from its recipe
alone (REQ-PIPE-440).

WHAT IS GENERATED, and only this (criteria 1 to 5): data-asset.yaml (the
hierarchy of the recipe's placements, a per-dataset arrival pattern, each
dataset's column types, identifier marks, cohort bounds and expected row count,
the project, filter, recipe format version and digest); a minimal
calendar.yaml (every dataset `no_calendar: never`, `derived: true` on a
derived product, nothing else); each collection's contract, its schema from
the recipe's columns; a presentation.yaml in the recipe's own names; a dbt
project reaching dbt_shared at the repository root from its own depth and
naming the deployment's local dbt_utils copy; and a digest of every file.

COPY NOTHING FROM THE KIND'S TEMPLATE (Keith 2026-11-21, criterion 13): no
people.yaml, no default check layer, no publishing destination - each is read
live from one-offs/extraction/_template/ at the step that needs it - and no
synthetic/ folder and no QA adapter module of its own (one shared adapter per
kind, qa_tools/kind_adapters/extraction.py). THE RECIPE CHECK LAYER IS
generated here (REQ-QAC-441 criteria 4 and 5), from
asset_model/kinds/extraction_checks.py, into each tool's own file.

CONFIGURATION ONLY: reads the recipe it is handed and the folder names under
assets/ and one-offs/, and writes the new folder. No database.
"""
from __future__ import annotations

import hashlib
from datetime import date
import json
import os
import re
from pathlib import Path

import yaml

from asset_model import assets

KIND = "extraction"
#: The file that records every generated file's digest (criterion 5).
DIGEST_FILE = "generated.sha256.json"
#: The environment variable the generated packages.yml reads the deployment's
#: local dbt_utils copy from (criterion 12) - set by the load from the
#: environment's configuration, so the committed folder names no machine's path.
DBT_UTILS_ENV = "MOTHMAN_ONE_OFF_DBT_UTILS"

_TABLE_PATTERN = re.compile(r"[a-z][a-z0-9_]*")


class FolderRefused(ValueError):
    """The folder cannot be generated. Its message names every problem."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("no folder was generated:\n"
                         + "\n".join(f"  - {p}" for p in self.problems))


def _refusals(recipe, root: Path) -> list[str]:
    """Criteria 6 and 7, before anything is written."""
    from asset_model import collections

    found = []
    rid = recipe.extraction_id
    held = []
    if (root / KIND / rid).exists():
        held.append(str(root / KIND / rid))
    if rid in assets.names():
        held.append(str(assets.ROOT / "assets" / rid))
    held += [str(root / k / n) for k, n in assets.one_offs() if n == rid and k != KIND]
    if held:
        found.append(f"{rid!r} is already a folder: {', '.join(held)}. A re-send is a new "
                     f"extraction, with an id of its own.")
    seen: dict[str, str] = {}
    for t in recipe.tables:
        if t.dataset_id in seen:
            found.append(f"tables {seen[t.dataset_id]!r} and {t.table!r} both claim the dataset "
                         f"placement {t.agency_id}/{t.collection_id}/{t.dataset_id}.")
        seen.setdefault(t.dataset_id, t.table)
        for what, value in (("agency", t.agency_id), ("collection", t.collection_id),
                            ("dataset", t.dataset_id)):
            if not collections.ID_PATTERN.fullmatch(value):
                found.append(f"{what} id {value!r} does not meet the hierarchy's naming rule "
                             f"(lowercase letters and digits, words joined by single hyphens, "
                             f"starting with a letter).")
        if not _TABLE_PATTERN.fullmatch(t.table):
            found.append(f"table {t.table!r} is not lowercase letters, digits and underscores.")
    tables = [t.table for t in recipe.tables]
    for name in sorted({n for n in tables if tables.count(n) > 1}):
        found.append(f"table {name!r} is declared more than once.")
    return found


def _deployment_facts() -> dict:
    """What an asset folder must state that a recipe does not: the zone its
    instants are read in, and the PostgreSQL major it targets. PROVISIONAL
    (2026-11-22): the zone in force and the major the enduring assets agree on;
    refused where they disagree."""
    zones, majors = set(), set()
    for a in assets.every():
        from asset_model import config_yaml

        doc = config_yaml.load(a.data_asset_yaml) or {}
        versions = (doc.get("timezone") or {}).get("versions") or []
        if versions:
            zones.add(versions[-1]["zone"])
        if doc.get("postgres_major") is not None:
            majors.add(doc["postgres_major"])
    if len(zones) != 1 or len(majors) != 1:
        raise FolderRefused([f"the enduring assets do not agree on one zone ({sorted(zones)}) "
                             f"and one PostgreSQL major ({sorted(majors)}) for a one-off to "
                             f"take."])
    return {"zone": zones.pop(), "postgres_major": majors.pop()}


def _hierarchy(recipe) -> dict:
    agencies: dict[str, dict] = {}
    for t in recipe.tables:
        agency = agencies.setdefault(t.agency_id, {
            "id": t.agency_id, "name": t.agency_name, "short": f"a{len(agencies) + 1}",
            "collections": []})
        coll = next((c for c in agency["collections"] if c["id"] == t.collection_id), None)
        if coll is None:
            n = sum(len(a["collections"]) for a in agencies.values()) + 1
            coll = {"id": t.collection_id, "name": t.collection_name, "short": f"c{n}",
                    "run_prefix": f"c{n}_run_",
                    "contract": f"{t.agency_id}/{t.collection_id}-contract.yaml",
                    "delivery_boundary": "directory", "datasets": []}
            agency["collections"].append(coll)
        coll["datasets"].append({
            "id": t.dataset_id, "name": t.dataset_name, "table": t.table,
            # ITS TABLE'S DECLARED FILE NAME ONLY (criterion 2; architect A2).
            "arrival_pattern": re.escape(t.file),
            "columns": [{"name": c.name, "type": c.type,
                         "primary_identifier": c.primary_identifier} for c in t.columns],
            "cohort": [{"column": b.column, "lower": b.lower, "upper": b.upper}
                       for b in t.cohort],
            **({"expected_rows": t.expected_rows} if t.expected_rows is not None else {})})
    return {"agencies": list(agencies.values())}


def _data_asset(recipe, facts: dict) -> dict:
    return {
        "data_asset_id": recipe.extraction_id,
        "project": recipe.project,
        "recipe": {"format_version": recipe.format_version, "digest": recipe.digest,
                   "filter": recipe.filter},
        "timezone": {"versions": [{"effective_from": "1970-01-01", "zone": facts["zone"],
                                   "changelog": [{"date": "1970-01-01", "author": "mothman one-off open",
                                                  "change": "The deployment's zone."}]}]},
        "postgres_major": facts["postgres_major"],
        "hierarchy": _hierarchy(recipe),
    }


def _calendar(recipe) -> dict:
    return {"calendars": [], "datasets": [
        {"id": t.dataset_id, "no_calendar": "never", **({"derived": True} if t.derived else {})}
        for t in recipe.tables]}


_LOGICAL_TO_PHYSICAL = {"string": "varchar", "integer": "bigint", "number": "numeric",
                        "date": "date", "timestamp": "timestamp", "boolean": "boolean"}


def _contract(recipe, collection_id: str) -> dict:
    tables = [t for t in recipe.tables if t.collection_id == collection_id]
    # A ONE-TABLE COLLECTION'S CONTRACT CARRIES ITS DATASET'S id AND name
    # (REQ-QAC-039), as every enduring asset's does; several tables, the
    # collection's.
    one = tables[0] if len(tables) == 1 else None
    return {
        "apiVersion": "v3.2.0", "kind": "DataContract",
        "id": one.dataset_id if one else collection_id,
        "status": "draft", "version": "1.0.0",
        "name": one.dataset_name if one else tables[0].collection_name,
        "domain": tables[0].agency_id,
        "description": {"purpose": f"Extraction {recipe.extraction_id} for {recipe.project}. "
                                   f"Filter: {recipe.filter}"},
        "schema": [{
            "name": t.table, "physicalType": "table", "description": t.dataset_name,
            "properties": [{"name": c.name, "logicalType": c.type,
                            "physicalType": _LOGICAL_TO_PHYSICAL[c.type],
                            "required": c.primary_identifier,
                            "description": c.name} for c in t.columns]}
            for t in tables],
    }


def _presentation(recipe) -> dict:
    return {
        "agencies": {t.agency_id: {"blurb": t.agency_name} for t in recipe.tables},
        "collections": {t.collection_id: {
            "provider": t.agency_name, "delivery_format": "CSV (extraction package)",
            "provenance": f"Extraction {recipe.extraction_id} for {recipe.project}. "
                          f"({{table_description}})"} for t in recipe.tables},
    }


def _dbt(recipe, folder: Path) -> dict[str, str]:
    """{relative path: text} for the dbt project (criterion 4)."""
    shared = os.path.relpath(assets.ROOT / assets.DBT_SHARED, folder / "dbt")
    project = {
        "name": f"mothman_{recipe.extraction_id.replace('-', '_')}",
        "version": "1.0.0", "config-version": 2, "profile": "mothman",
        "model-paths": ["models"],
        "macro-paths": [f"{shared}/macros"],
        "test-paths": ["tests", f"{shared}/tests"],
        "clean-targets": ["target", "dbt_packages"],
        "models": {f"mothman_{recipe.extraction_id.replace('-', '_')}": {"+materialized": "view"}},
        "data_tests": {"+schema": "audit"},
    }
    out = {"dbt/dbt_project.yml": yaml.safe_dump(project, sort_keys=False),
           # THE DEPLOYMENT'S LOCAL COPY, never a network fetch (criterion 12),
           # at the revision the enduring assets lock.
           "dbt/packages.yml": yaml.safe_dump({"packages": [
               {"local": "{{ env_var('" + DBT_UTILS_ENV + "') }}"}]}, sort_keys=False)}
    for coll in sorted({t.collection_id for t in recipe.tables}):
        tables = [t for t in recipe.tables if t.collection_id == coll]
        out[f"dbt/models/{coll}/sources.yml"] = yaml.safe_dump({"version": 2, "sources": [
            {"name": "raw", "schema": "{{ env_var('DBT_RUN_SCHEMA') }}",
             "tables": [{"name": t.table} for t in tables]}]}, sort_keys=False)
        for t in tables:
            out[f"dbt/models/{coll}/stg_{t.table}.sql"] = (
                f"with source as (\n    select * from {{{{ source('raw', '{t.table}') }}}}\n)\n\n"
                f"select * from source\n")
    return out


def files_for(recipe, folder: Path, facts: dict | None = None,
              introduced: str | None = None) -> dict[str, str]:
    """{path relative to the folder: text} for every generated file but the
    digest. `introduced` is the recipe checks' introduced_date - the day the
    folder is opened."""
    facts = facts or _deployment_facts()
    out = {"data-asset.yaml": yaml.safe_dump(_data_asset(recipe, facts), sort_keys=False),
           "calendar.yaml": yaml.safe_dump(_calendar(recipe), sort_keys=False),
           "presentation.yaml": yaml.safe_dump(_presentation(recipe), sort_keys=False)}
    out.update(_check_files(recipe, out["data-asset.yaml"], out["calendar.yaml"],
                            introduced or date.today().isoformat()))
    out.update(_dbt(recipe, folder))
    return out


def _check_files(recipe, data_asset: str, calendar: str, introduced: str) -> dict[str, str]:
    """Each collection's contract and THE RECIPE CHECK LAYER (REQ-QAC-441
    criteria 4 and 5), in each tool's own file: the contract's quality rules,
    the SodaCL checks, the Evidently checks and the dbt tests, each with its
    retired sibling (REQ-QAC-241) - empty, since nothing in a one-off is ever
    retired. The default layer is never written here: the load reads it from
    the kind's template (REQ-PIPE-440 criterion 13)."""
    from asset_model.kinds import extraction_checks as checks

    from asset_model import config_yaml

    tables = checks.declared(config_yaml.parse(data_asset, name="data-asset.yaml"),
                             config_yaml.parse(calendar, name="calendar.yaml"))
    layers = checks.recipe_layer(recipe.extraction_id, tables, introduced)
    out = {}
    for coll in dict.fromkeys(t.collection_id for t in recipe.tables):
        mine = [t for t in tables if t.collection_id == coll]
        stem = f"{mine[0].agency_id}/{coll}"
        layer = layers[coll]
        names = [t.table for t in mine]
        out[f"{stem}-contract.yaml"] = _dump(checks.contract_doc(_contract(recipe, coll), layer))
        out[f"{stem}-soda-checks.yml"] = _dump(checks.soda_doc(layer, names))
        out[f"{stem}-evidently-checks.yml"] = _dump(checks.evidently_doc(layer))
        for kind, suffix in (("contract", "contract-retired.yaml"),
                             ("soda", "soda-checks-retired.yml"),
                             ("evidently", "evidently-checks-retired.yml")):
            out[f"{stem}-{suffix}"] = _dump(checks.RETIRED[kind])
        out[f"dbt/models/{coll}/schema.yml"] = _dump(checks.dbt_schema_doc(layer, names))
    return out


def _dump(doc) -> str:
    return yaml.safe_dump(doc, sort_keys=False, width=100, allow_unicode=True)


def digest_of(folder: Path, names) -> dict[str, str]:
    return {n: hashlib.sha256((folder / n).read_bytes()).hexdigest() for n in sorted(names)}


def generate(package, root: Path | None = None) -> Path:
    """Generate one-offs/extraction/<id>/ (under `root`, the one-offs root by
    default) from the package's recipe, and return the folder."""
    root = Path(root) if root is not None else assets.one_offs_root()
    recipe = package.recipe
    problems = _refusals(recipe, root)
    if problems:
        raise FolderRefused(problems)
    folder = root / KIND / recipe.extraction_id
    files = files_for(recipe, folder)
    folder.mkdir(parents=True)
    for rel, text in files.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (folder / DIGEST_FILE).write_text(json.dumps(
        {"recipe_digest": recipe.digest, "files": digest_of(folder, files)}, indent=1) + "\n")
    return folder


def recorded(folder: Path) -> dict:
    """The digest record a folder carries."""
    return json.loads((Path(folder) / DIGEST_FILE).read_text())

