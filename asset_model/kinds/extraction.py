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


#: WHAT GATES THE TEMPLATE (REQ-PIPE-448 criterion 6): its default check layer.
#: people.yaml (REQ-PIPE-435) and the destination (REQ-PIPE-443) add theirs.
TEMPLATE_GATES = {"default check layer": _default_layer_problems}


EXTRACTION = one_off_kinds.register(one_off_kinds.Kind(
    name="extraction", singular="extraction", plural="extractions", layer="Recipe check",
    reader=extraction_recipe.read, generator=_generate, gates=GATES,
    template_gates=TEMPLATE_GATES, file_checks=_package_checks))
