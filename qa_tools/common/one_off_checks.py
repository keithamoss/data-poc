"""A one-off's CHECK WORKSPACE: the configuration its load hands the four
tools - its committed folder with the kind's default check layer, read live
from the template, merged into each collection's check files (REQ-QAC-441
criterion 1; REQ-PIPE-440 criterion 13).

COPY NOTHING INTO THE FOLDER, MATERIALISE INTO SCRATCH (Keith 2026-11-21 and
2026-11-22). The default layer is defined once in one-offs/<kind>/_template/
and never written into a one-off's folder; what the tools must read as files
is written to data/<id>/qa/config/, rebuilt from the folder and the template
at every load and removed with the rest of data/<id>/ by the drop
(REQ-PIPE-442 criterion 6). It is the only copy of the merged layers, and is
never read as configuration of record: the folder and the template are.

ONE WORKSPACE, EVERY TOOL: the selected one-off reads its configuration
folder and dbt project from the workspace while it is in use
(assets.use_workspace), so dbt-core, Soda Core, datacontract-cli and Evidently
each read their own file there exactly as they read an enduring asset's, and
dbt writes its target/, logs/ and dbt_packages there rather than into the
committed folder.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import yaml

from asset_model import assets, config_yaml

#: Under the one-off's own data/<id>/.
WORKSPACE = Path("qa") / "config"
#: What is never carried from the folder into the workspace.
_LEFT_OUT = {"target", "logs", "dbt_packages", "package-lock.yml"}


def workspace_of(asset) -> Path:
    return asset.data / WORKSPACE


def _dump(doc) -> str:
    return yaml.safe_dump(doc, sort_keys=False, width=100, allow_unicode=True)


def materialise(dbt_utils: Path | None = None) -> Path:
    """Build the selected one-off's check workspace from its committed folder
    and its kind's template as they read now, and return it. Refused, naming
    every problem, where the template's default layer cannot be read."""
    from asset_model.kinds import extraction_checks as checks
    from asset_model import collections

    folder = assets.committed_folder()
    asset = assets.selected()
    template = assets.kind_template(asset.kind)
    defaults = checks.read_template(template)
    out = workspace_of(asset)
    if out.exists():
        shutil.rmtree(out)
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder)
        if not path.is_file() or _LEFT_OUT & set(rel.parts):
            continue
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out / rel)
    doc = config_yaml.load(folder / "data-asset.yaml") or {}
    calendar = config_yaml.load(folder / "calendar.yaml") or {}
    tables = checks.declared(doc, calendar)
    layers = checks.default_layer(asset.name, tables, defaults)
    assets.use_workspace(out)
    try:
        for coll in collections.all_collections():
            layer = layers.get(coll.id)
            if layer is None:
                continue
            names = [d.table for d in coll.datasets]
            _merge_contract(out / _rel(coll.check_file("contract")), layer)
            _merge_soda(out / _rel(coll.check_file("soda")), layer, names)
            _merge_evidently(out / _rel(coll.check_file("evidently")), layer)
            _merge_dbt(out / "dbt" / "models" / coll.id / "schema.yml", layer, names)
    finally:
        assets.use_workspace(None)
    _point_dbt(out / "dbt", dbt_utils)
    return out


def _rel(on_disk: str) -> str:
    """A collection's check file relative to the configuration folder."""
    return on_disk.split(f"{assets.folder_on_disk()}/", 1)[-1]


def _merge_contract(path: Path, layer) -> None:
    from asset_model.kinds import extraction_checks as checks

    path.write_text(_dump(checks.contract_doc(config_yaml.load(path), layer)))


def _merge_soda(path: Path, layer, tables: list[str]) -> None:
    doc = config_yaml.load(path) if path.is_file() else {}
    doc = doc or {}
    for t in tables:
        extra = layer.soda.get(t) or []
        if extra:
            doc.setdefault(f"checks for {t}", [])
            doc[f"checks for {t}"] = list(doc[f"checks for {t}"] or []) + extra
    path.write_text(_dump(doc))


def _merge_evidently(path: Path, layer) -> None:
    from asset_model.kinds import extraction_checks as checks

    doc = (config_yaml.load(path) if path.is_file() else None) or {"checks": []}
    doc["checks"] = list(doc.get("checks") or []) + checks.evidently_doc(layer)["checks"]
    path.write_text(_dump(doc))


def _merge_dbt(path: Path, layer, tables: list[str]) -> None:
    doc = (config_yaml.load(path) if path.is_file() else None) or {"version": 2, "models": []}
    models = {m["name"]: m for m in doc.get("models") or []}
    for t in tables:
        model = models.get(f"stg_{t}")
        if model is None:
            model = {"name": f"stg_{t}", "columns": []}
            doc.setdefault("models", []).append(model)
            models[model["name"]] = model
        columns = {c["name"]: c for c in model.setdefault("columns", []) or []}
        for col, tests in (layer.dbt.get(t) or {}).items():
            entry = columns.get(col)
            if entry is None:
                entry = {"name": col, "tests": []}
                model["columns"].append(entry)
                columns[col] = entry
            entry["tests"] = list(entry.get("tests") or []) + tests
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump(doc))


def _point_dbt(project: Path, dbt_utils: Path | None) -> None:
    """The workspace's dbt project reaches dbt_shared from where it now is,
    and names the deployment's local dbt_utils copy by path (REQ-PIPE-440
    criterion 12) - no network fetch."""
    doc = config_yaml.load(project / "dbt_project.yml")
    shared = os.path.relpath(assets.ROOT / assets.DBT_SHARED, project)
    doc["macro-paths"] = [f"{shared}/macros"]
    doc["test-paths"] = ["tests", f"{shared}/tests"]
    (project / "dbt_project.yml").write_text(_dump(doc))
    if dbt_utils is not None:
        (project / "packages.yml").write_text(_dump({"packages": [{"local": str(dbt_utils)}]}))
