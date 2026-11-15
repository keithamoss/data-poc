"""The file checks' DEFINITIONS (REQ-QAC-096, split by REQ-PIPE-380
criterion 2): which file checks the selected asset's file-checks.yaml
declares, their severities and names, and the check id each gets per
dataset.

THE OTHER HALF IS qa_tools/common/file_checks.py, which evaluates a
delivered file's bytes and records the findings. The cut sits there because
the generator and the lifecycle gate read the definitions as configuration,
and only the real pipeline reads a supplier's file and writes results.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from asset_model import assets, config_yaml


def definitions_path() -> Path:
    """The selected asset's file-checks.yaml, resolved now (REQ-PIPE-342 criterion
    6; it was the import-time constant DEFINITIONS_PATH)."""
    return assets.selected().file("file-checks.yaml")


#: The fifth tool suffix (check_id.TOOLS) and the value of `qa.check_result.tool`.
TOOL = "file"

#: How much a finding matters (criterion 18): a FAILURE refuses the file, a
#: WARNING is recorded and the file loads.
FAILURE = "failure"
WARNING = "warning"

ENCODING = "encoding"
DELIMITER = "delimiter"
HEADER_ROW = "header_row"
HEADER_NAMES_UNIQUE = "header_names_unique"
FIELDS_PER_ROW = "fields_per_row"
COLUMN_ORDER = "column_order"
#: Evaluation order, which is also reading order on the page.
NAMES = (ENCODING, DELIMITER, HEADER_ROW, HEADER_NAMES_UNIQUE, FIELDS_PER_ROW, COLUMN_ORDER)


@dataclass(frozen=True)
class Definition:
    check: str
    severity: str
    formats: tuple[str, ...]
    name: str
    retired: bool


def definitions(path: Path | str | None = None) -> list[Definition]:
    """Every file check in the committed configuration, in NAMES order."""
    doc = config_yaml.load(path or definitions_path()) or {}
    out = [Definition(check=str(raw["check"]), severity=str(raw["severity"]),
                      formats=tuple(raw.get("formats") or ("csv",)),
                      name=str(raw.get("name") or raw["check"]).strip(),
                      retired=bool(raw.get("retired_as_of")))
           for raw in doc.get("checks") or []]
    order = {n: i for i, n in enumerate(NAMES)}
    return sorted(out, key=lambda d: order.get(d.check, len(order)))


def active(fmt: str = "csv", path=None) -> list[Definition]:
    return [d for d in definitions(path) if not d.retired and fmt in d.formats]


def check_id_for(dataset, check: str) -> str:
    """Criterion 4: `<asset>.<agency>.<collection>.<dataset>.<check>_file`."""
    return (f"{dataset.data_asset_id}.{dataset.agency_id}.{dataset.collection_id}."
            f"{dataset.dataset_id}.{check}_{TOOL}")
