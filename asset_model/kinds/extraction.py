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


EXTRACTION = one_off_kinds.register(one_off_kinds.Kind(
    name="extraction", singular="extraction", plural="extractions", layer="Recipe check",
    reader=extraction_recipe.read, generator=_generate, gates=GATES))
