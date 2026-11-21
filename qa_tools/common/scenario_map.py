"""The scenario map's READER (REQ-GEN-045; REQ-GEN-386 criterion 5): where
the selected asset's committed SCENARIOS-<asset>.md is, and the structured
entries embedded in it, which the dashboard build reads. Nothing else of the
map lives in the real pipeline: its writer is the generator's
(generator/scenario_map_writer.py), and the register, placements and
vocabulary it is built from are scenarios/'s, which a real deployment leaves
out.

COORDINATES ONLY, NEVER A LINK: the dashboard constructs the link from what
this returns (REQ-DASH-046). A map with no data block, or none at all, reads
as no scenarios (REQ-PIPE-385 criterion 10).
"""
from __future__ import annotations

import json
from pathlib import Path

from asset_model import assets

ROOT = Path(__file__).resolve().parent.parent.parent

#: The committed maps, one per asset (REQ-PIPE-352 criterion 3).
MAP_STEM = "SCENARIOS"


def map_path() -> Path:
    """The selected asset's committed map, SCENARIOS-<asset>.md at the
    repository root, asked of the resolver at call time. One map per asset,
    each generated from that asset's own history (REQ-PIPE-352 criterion 3,
    SETTLED by Keith 2026-11-01); the register they are built from stays one."""
    return ROOT / f"{MAP_STEM}-{assets.selected().name}.md"


#: The machine-readable copy, inside the markdown rather than beside
#: it (REQ-DASH-046 criterion 5). ONE COMMITTED FILE, still markdown,
#: still self-explanatory to a person - an HTML comment renders as
#: nothing on GitHub - and the dashboard reads exact data rather than
#: re-parsing prose it would then have to keep in step.
#:
#: The alternative was a JSON sidecar, rejected because two files that
#: must agree is the shape this project keeps removing: one staleness
#: gate cannot cover both, and the pair drifts the first time somebody
#: regenerates one.
_DATA_OPEN = "<!-- scenario-map-data\n"
_DATA_CLOSE = "\n-->"


def read_map_data(map_path: Path | str | None = None) -> list[dict]:
    """The structured entries embedded in the committed map.

    Read by the dashboard build, which may open no data/ - so this
    reads the COMMITTED markdown and nothing else. A map with no data
    block returns nothing rather than raising, because the document is
    still a document without it - and AN ASSET WITH NO MAP AT ALL (no
    synthetic history, REQ-PIPE-385 criterion 10) reads as no scenarios.
    """
    source = Path(map_path or globals()["map_path"]())
    if not source.is_file():
        return []
    text = source.read_text()
    start = text.find(_DATA_OPEN)
    if start < 0:
        return []
    end = text.find(_DATA_CLOSE, start)
    if end < 0:
        return []
    try:
        raw = json.loads(text[start + len(_DATA_OPEN):end])
    except json.JSONDecodeError:
        return []
    return list(raw.get("scenarios") or ())
