"""Where each scenario actually landed (REQ-GEN-044 criterion 7; moved here
by REQ-GEN-386 criterion 4): the generator's placements record and its reader,
which the generator, the map writer and the bootstrap read and the real
pipeline never does.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from asset_model import assets
from scenarios.vocabulary import SUBJECTS, SUPPLY_HISTORY_ROW

#: Where the generator records what it placed (REQ-GEN-044 criterion 7).
#: Under data/, because it is generator bookkeeping - the same place
#: data/generator_bookkeeping.json lives, and for the same reason: the
#: pipeline may not read either.
PLACEMENTS_FILE = "scenario_placements.json"


def placements_path() -> Path:
    """The selected asset's placements record, asked of the resolver at call
    time (REQ-PIPE-342 criterion 6, REQ-PIPE-365 criterion 1)."""
    return assets.data_path(PLACEMENTS_FILE)


@dataclass(frozen=True)
class Placement:
    """Where one scenario actually landed."""

    scenario_id: str
    dataset: str
    supplies: tuple[str, ...]
    period: str
    in_place_on: str
    #: What each targeted arrival was built to, and the rules moved with
    #: their intended counts (REQ-GEN-184 criterion 12). Never a verdict.
    targets: tuple = ()
    #: What its link lands on (REQ-DASH-208 criterion 2). A placement written
    #: before the subject was recorded reads as its first supply's row.
    subject: str = SUPPLY_HISTORY_ROW

    @classmethod
    def of(cls, record: Mapping) -> "Placement":
        # A NAME OUTSIDE THE VOCABULARY FAILS HERE, at build time, rather than
        # reading on the page as "nothing to show" (post-build-review #202 F10).
        subject = str(record.get("subject") or SUPPLY_HISTORY_ROW)
        if subject not in SUBJECTS:
            raise ValueError(f"scenario {record.get('scenario_id')!r} names subject "
                             f"{subject!r}, which is not one of {sorted(SUBJECTS)}")
        return cls(
            scenario_id=str(record.get("scenario_id") or ""),
            dataset=str(record.get("dataset") or ""),
            supplies=tuple(record.get("supplies") or ()),
            period=str(record.get("period") or ""),
            # The key the generator wrote before the "In place on" rename
            # (REQ-PIPE-081 criterion 25) is still read, so a placements file
            # from an earlier bootstrap keeps its coordinates.
            in_place_on=str(record.get("in_place_on") or record.get("as" + "_of") or ""),
            targets=tuple(record.get("targets") or ()),
            subject=subject)

    @property
    def is_complete(self) -> bool:
        """A HALF-RECORDED PLACEMENT IS NOT A COORDINATE. Criterion 6
        says a scenario with no generated data behind it says so
        rather than emitting a coordinate that leads nowhere, and a
        record naming a dataset but no period leads exactly nowhere."""
        return bool(self.dataset and self.period and self.in_place_on)


def read_placements(path: Path | str | None = None) -> dict[str, Placement]:
    """What the generator recorded, keyed by scenario id.

    An ABSENT file is the ordinary state today, not an error: nothing
    injects yet. A malformed one is also empty rather than fatal -
    this builds a document, and a document that cannot be built stops
    a regeneration that had nothing else wrong with it.
    """
    source = Path(path or placements_path())
    if not source.is_file():
        return {}
    try:
        raw = json.loads(source.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    records = raw.get("placements") if isinstance(raw, dict) else raw
    out = {}
    for record in records or ():
        if isinstance(record, Mapping):
            placement = Placement.of(record)
            if placement.scenario_id:
                out[placement.scenario_id] = placement
    return out
