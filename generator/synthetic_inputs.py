"""What a synthetic product is built from, beyond what the hierarchy says
(REQ-QAC-294 criterion 3): contract/synthetic_inputs.yaml.

GENERATOR-ONLY CONFIGURATION, as contract/scripted_decisions.yaml is - read by
the generator, never by a QA tool, the pipeline or the dashboard. GENERIC: for
any declaring dataset, the source columns a record is placed by (finest
first) and the value each yields, the column the value goes in, and the
value for a record none places. Nothing here names a collection, a dataset or
a column; the providers gate holds the file to the contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from qa_tools.common import assets as _assets

REPO = Path(__file__).resolve().parent.parent
NAME = "synthetic_inputs.yaml"


def _path(root: Path) -> Path:
    """The selected asset's synthetic_inputs.yaml in the checkout at `root`,
    asked of the resolver at call time (REQ-PIPE-342 criterion 6; it was the
    import-time constant PATH)."""
    from qa_tools.common.linked_datasets import _asset_folder

    return _asset_folder(root) / "synthetic" / NAME


@dataclass(frozen=True)
class Placing:
    """How a declaring dataset's records are placed from its source's columns."""

    dataset: str
    placed_column: str
    unplaced_value: str
    #: (source column, the value it yields), finest first
    place_by: tuple[tuple[str, str], ...]

    def value_for(self, row) -> str:
        """The value a source row is placed at: the first declared column
        holding a value - blank and null hold none - else the unplaced value."""
        for column, value in self.place_by:
            v = row.get(column)
            if v is not None and str(v).strip() != "" and str(v).lower() != "nan":
                return value
        return self.unplaced_value


def _doc(root: Path) -> dict:
    path = _path(root)
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}


def placings(root: Path = REPO) -> dict[str, Placing]:
    """Every declared dataset's placing, by dataset id."""
    out = {}
    for entry in _doc(root).get("datasets") or []:
        out[str(entry.get("dataset"))] = Placing(
            dataset=str(entry.get("dataset")),
            placed_column=str(entry.get("placed_column")),
            unplaced_value=str(entry.get("unplaced_value")),
            place_by=tuple((str(p.get("column")), str(p.get("value")))
                           for p in entry.get("place_by") or ()))
    return out


def _table(root: Path, contract: str, table: str) -> dict:
    from qa_tools.common.linked_datasets import _asset_folder

    doc = yaml.safe_load((_asset_folder(root) / contract).read_text()) or {}
    return next((t for t in doc.get("schema") or [] if t.get("name") == table), {}) or {}


def _allowed(prop: dict) -> list | None:
    """A property's allowed values, as ODCS v3.2.0 declares them (enum)."""
    enum = prop.get("enum")
    return None if enum is None else [e.get("value") if isinstance(e, dict) else e for e in enum]


def problems(root: Path = REPO) -> list[str]:
    """REQ-QAC-294 criterion 3's gate: each declared column is in the source's
    contract, and each declared value is among the placed column's allowed
    values; naming the dataset and the column or value."""
    from qa_tools.common import assets
    from qa_tools.common.linked_datasets import _asset_folder, _walk

    asset = yaml.safe_load((_asset_folder(root) / "data-asset.yaml").read_text()) or {}
    where = {ds.get("id"): (coll, ds) for _a, coll, ds in _walk(asset)}
    out = []
    for p in placings(root).values():
        head = f"{assets.folder_rel()}/synthetic/{NAME}: {p.dataset}"
        if p.dataset not in where:
            out.append(f"{head} is not in the hierarchy ({_assets.config_dir()}/data-asset.yaml).")
            continue
        coll, ds = where[p.dataset]
        linked = ds.get("linked_datasets") or []
        if len(linked) != 1 or linked[0].get("dataset") not in where:
            out.append(f"{head} declares no single linked source to place records from.")
            continue
        src_coll, src = where[linked[0]["dataset"]]
        src_cols = {q.get("name") for q in _table(root, src_coll.get("contract", ""),
                                                   src.get("table")).get("properties") or []}
        own = {q.get("name"): q for q in _table(root, coll.get("contract", ""),
                                                ds.get("table")).get("properties") or []}
        if not p.place_by:
            out.append(f"{head} declares no place_by column.")
        if p.placed_column not in own:
            out.append(f"{head} places into the column {p.placed_column!r}, which its contract "
                       f"does not declare.")
            continue
        allowed = _allowed(own[p.placed_column])
        for column, value in p.place_by:
            if column not in src_cols:
                out.append(f"{head} places by the column {column!r}, which "
                           f"{linked[0]['dataset']}'s contract does not declare.")
        for value in [v for _c, v in p.place_by] + [p.unplaced_value]:
            if allowed is None or value not in allowed:
                out.append(f"{head} declares the value {value!r}, which is not among "
                           f"{p.placed_column}'s allowed values {allowed}.")
    return out
