"""The extraction: the first one-off kind (REQ-PIPE-439, REQ-PIPE-440), its
plug-in registered with asset_model.one_off_kinds (REQ-PIPE-446 criterion 2).

Its folders are one-offs/extraction/<id>/, each generated from a recipe
package; its template, one-offs/extraction/_template/, holds what every
extraction reads live (REQ-PIPE-440 criterion 13).
"""
from __future__ import annotations

from asset_model import one_off_kinds
from asset_model.kinds import extraction_recipe

#: WHICH PER-ASSET GATES APPLY TO AN EXTRACTION (REQ-PIPE-448 criterion 1;
#: matched to cli/check.py's gates, its decision 'THE EXTRACTION KIND'S
#: DECLARATIONS'). Every per-asset gate is named, True or False - no default.
GATES = {
    "hierarchy": True, "collections": True, "schedule": True, "patterns": True,
    "soda": True, "columns": True, "people": True,
    # Synthetic, a database, or docs with nothing of a one-off in them.
    "caches": False, "providers": False, "scenarios": False, "scenario map": False,
    "guard": False, "plans": False, "requirements": False, "sprints": False,
    "provisional": False, "changelog": False, "feedback": False, "premise": False,
}


def _generate(package, root):
    from asset_model.kinds import extraction_folder

    return extraction_folder.generate(package, root)


def _default_layer_problems(template) -> list[str]:
    """The template's default check layer reads (REQ-QAC-441 criterion 1):
    every default assertion defined once, with its words and a tool it takes."""
    from asset_model.kinds import extraction_checks

    try:
        extraction_checks.read_template(template)
    except extraction_checks.TemplateRefused as exc:
        return exc.problems
    return []


def _package_checks(template) -> dict:
    """The one-off's package checks, read live from its kind's template
    (REQ-QAC-441 criteria 1 to 3) - file_check_definitions reads them."""
    from pathlib import Path

    from asset_model.kinds import extraction_checks

    # NO TEMPLATE, NO PACKAGE CHECKS TO READ - said by the template's own gate
    # (REQ-PIPE-448 criterion 6) and refused by the load, never a crash here.
    if not (Path(template) / extraction_checks.DEFAULT_LAYER_FILE).is_file():
        return None
    return extraction_checks.package_checks(extraction_checks.read_template(template))


def _layer_of(check_key: str) -> str | None:
    """'kind' for a recipe check, 'default' for every other check an extraction
    gets - the default layer's and the shared file checks, which every
    extraction gets alike (REQ-DASH-444 criterion 10). The key's name is the
    segment before its tool (extraction_checks.check_id)."""
    from asset_model.kinds import extraction_checks

    if check_key == "no_rule_defined":
        return None
    name = check_key.rsplit("_", 1)[0]
    return "kind" if name in extraction_checks.RECIPE_ASSERTIONS else "default"


def _declaration(folder) -> dict:
    """What the recipe declared, for the page (REQ-DASH-447 criteria 1 and 2):
    read from the extraction's COMMITTED FOLDER, which REQ-PIPE-440 criterion 2
    generated from it - never the recipe file."""
    from pathlib import Path

    from asset_model import config_yaml
    from asset_model.kinds import extraction_checks

    folder = Path(folder)
    doc = config_yaml.load(folder / "data-asset.yaml") or {}
    calendar = config_yaml.load(folder / "calendar.yaml") or {}
    recipe = doc.get("recipe") or {}
    names = {}
    for agency in doc["hierarchy"]["agencies"]:
        for coll in agency["collections"]:
            for ds in coll["datasets"]:
                names[ds["id"]] = (agency["name"], coll["name"], ds["name"])
    def keys(assertion):
        # Every check key the assertion is rendered as; the page shows those
        # that were recorded.
        return [f"{extraction_checks.CHECK_NAME[assertion]}_{tool}"
                for tool in extraction_checks.ASSERTION_TOOLS[assertion]]

    tables = {}
    for t in extraction_checks.declared(doc, calendar):
        agency, collection, dataset = names[t.dataset_id]
        tables[t.dataset_id] = {
            "file": t.file, "table": t.table,
            "placement": {"agency": agency, "collection": collection, "dataset": dataset},
            "derived": t.derived,
            "columns": [{"name": c["name"], "type": c["type"],
                         "identifier": bool(c["primary_identifier"]),
                         "checks": keys("declared_type")} for c in t.columns],
            "cohort": [{**dict(b), "checks": keys("cohort_bounds")} for b in t.cohort],
            "expectedRows": t.expected_rows,
            "expectedRowsChecks": keys("expected_rows") if t.expected_rows is not None else []}
    from asset_model import file_check_definitions

    # The package check's key on the page: the file check's name and its tool.
    return {"undeclaredCheck": f"{file_check_definitions.UNDECLARED_FILE}_file",
            "recipe": {"formatVersion": recipe.get("format_version"),
                       "digest": recipe.get("digest"), "filter": recipe.get("filter")},
            "tables": tables}


#: WHAT GATES THE TEMPLATE (REQ-PIPE-448 criterion 6): its default check layer.
#: The publishing destination (REQ-PIPE-443) is every kind's, added by
#: one_off_gating.template_pass.
TEMPLATE_GATES = {"default check layer": _default_layer_problems}


EXTRACTION = one_off_kinds.register(one_off_kinds.Kind(
    name="extraction", singular="extraction", plural="extractions", layer="Recipe check",
    reader=extraction_recipe.read, generator=_generate, gates=GATES,
    template_gates=TEMPLATE_GATES, file_checks=_package_checks, layer_of=_layer_of,
    declaration=_declaration))
