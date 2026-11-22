"""The file checks' DEFINITIONS (REQ-QAC-096, split by REQ-PIPE-380
criterion 2): which file checks the selected asset runs, their severities and
names, and the check id each gets per dataset.

ONE SHARED DEFAULT, BESIDE dbt_shared/ (REQ-QAC-387, SPLIT D2): the checks
every asset runs are the repository root's file-checks.yaml, read from the
code's own checkout so an asset folder outside the repository still gets them
(criterion 11). An asset's own file-checks.yaml, where it has one, ADDS a
check (a name the default does not hold), OVERRIDES one WHOLE by its `check:`
name - no field of the shared entry is inherited (Q3, Keith 2026-11-14) - or
retires one for itself with `retired_as_of` on its override. merged() is the
one reader every file-check reader goes through (criterion 6).

THE OTHER HALF IS qa_tools/common/file_checks.py, which evaluates a
delivered file's bytes and records the findings. The cut sits there because
the generator and the lifecycle gate read the definitions as configuration,
and only the real pipeline reads a supplier's file and writes results.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from asset_model import assets, config_yaml


#: The file's name, the shared default's at the repository root and an
#: asset's own in its folder alike.
FILE = "file-checks.yaml"

#: What a file check's entry may say (criterion 10): what it does, how it
#: reads and its lifecycle.
KEYS = frozenset({"check", "name", "severity", "formats", "category", "introduced_date",
                  "description", "failure_indicates", "technical_note", "changelog",
                  "retired_as_of", "retired_reason"})


class FileChecksError(ValueError):
    """A file-checks.yaml naming a key no file check allows, or one check
    twice - named by its file and entry."""


def shared_path() -> Path:
    """The shared default, in the code's own checkout (criterion 11)."""
    return assets.ROOT / FILE


def definitions_path() -> Path:
    """The selected asset's own file-checks.yaml, resolved now (REQ-PIPE-342
    criterion 6) - which may not exist: an asset with none runs the shared
    default unchanged (REQ-QAC-387 criterion 5)."""
    return assets.selected().file(FILE)


def _entries(doc, source: str) -> list[dict]:
    """A file's entries, each checked for its keys and its name once."""
    seen: set[str] = set()
    out = []
    for i, raw in enumerate((doc or {}).get("checks") or []):
        name = raw.get("check") if isinstance(raw, dict) else None
        where = f"{source}: checks[{i}]" + (f" ({name})" if name else "")
        if not name:
            raise FileChecksError(f"{where} names no `check:`")
        unknown = sorted(set(raw) - KEYS)
        if unknown:
            raise FileChecksError(f"{where} names {', '.join(unknown)}, which no file check "
                                  f"allows - allowed: {', '.join(sorted(KEYS))}")
        if name in ONE_OFF_NAMES and not _for_a_one_off():
            raise FileChecksError(f"{where} names {name!r}, which only a one-off's default "
                                  f"check layer runs - its load writes it (REQ-QAC-441)")
        if name not in NAMES and name not in ONE_OFF_NAMES:
            # ONLY A CHECK THE CODE CAN EVALUATE (REQ-QAC-387 criterion 3; Keith,
            # 2026-11-18): an unknown name passed this gate and then failed every
            # file at the file-check step with 'no evaluator for this check'.
            raise FileChecksError(f"{where} names {name!r}, and no file check of that name "
                                  f"exists - an asset adds, overrides or retires one of: "
                                  f"{', '.join(NAMES)}")
        if name in seen:
            raise FileChecksError(f"{where} names {name!r} a second time - one entry per check")
        seen.add(name)
        out.append(dict(raw))
    return out


def merged_entries(*, shared=None, own=None, shared_source: str | None = None,
                   own_source: str | None = None) -> list[tuple[dict, str]]:
    """Every check the asset runs, `(entry, source file)`: the shared
    default's in its order, each replaced WHOLE by the asset's entry of the
    same name, then the asset's additions in its order. `shared` and `own`
    are parsed documents (None for a file that does not exist)."""
    shared_source = shared_source or str(shared_path())
    own_source = own_source or str(definitions_path())
    mine = {e["check"]: e for e in _entries(own, own_source)}
    out = []
    for entry in _entries(shared, shared_source):
        override = mine.pop(entry["check"], None)
        out.append((override, own_source) if override is not None else (entry, shared_source))
    return out + [(e, own_source) for e in mine.values()]


def _load_if_present(path):
    path = Path(path)
    return config_yaml.load(path) if path.is_file() else None


def merged(own_path: Path | str | None = None, *, shared_text: str | None = None,
           from_text: bool = False) -> list[tuple[dict, str]]:
    """The selected asset's file checks as the working tree defines them -
    or, where `from_text` is set, the shared default from `shared_text` (a
    git ref's, which may be None) beside the asset's own at `own_path`."""
    own_path = Path(own_path) if own_path is not None else definitions_path()
    shared = (config_yaml.parse(shared_text, name=FILE) if shared_text else None) if from_text \
        else _load_if_present(shared_path())
    own = _load_if_present(own_path)
    if own is None:
        own = _one_offs_own()
    return merged_entries(shared=shared, own=own, own_source=str(own_path))


def _one_offs_own():
    """A selected one-off's own additions - its package checks - read live from
    its kind's template where its folder has no file-checks.yaml of its own
    (REQ-QAC-441 criterion 1): never copied into the folder."""
    try:
        asset = assets.selected()
    except assets.AssetError:
        return None
    if not asset.is_one_off:
        return None
    from asset_model import one_off_kinds

    kind = one_off_kinds.get(asset.kind)
    if kind is None or kind.file_checks is None:
        return None
    return kind.file_checks(assets.kind_template(asset.kind))


def problems() -> list[str]:
    """What the collections gate reports (criterion 10): a key no file check
    allows or a check named twice, in the shared default or the selected
    asset's own file."""
    try:
        merged()
    except FileChecksError as exc:
        return [str(exc)]
    return []


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

#: A ONE-OFF'S PACKAGE CHECKS (REQ-QAC-441 criteria 2 and 3): its default
#: layer's facts about the package, defined in the kind's template and
#: materialised into the one-off's check workspace as additions of its own -
#: never an enduring asset's. `table_arrived` is asked of each declared file as
#: it is screened, and passes there; the load records it failing for a declared
#: table whose file never arrived. `undeclared` (the template's `undeclared_file`) is asked of the PACKAGE as
#: a whole, by the load - its format is PACKAGE, so no file's screening runs it.
TABLE_ARRIVED = "table_arrived"
UNDECLARED_FILE = "undeclared"
ONE_OFF_NAMES = (TABLE_ARRIVED, UNDECLARED_FILE)
#: The format of a check asked of the whole package rather than one file.
PACKAGE = "package"


def _for_a_one_off() -> bool:
    try:
        return assets.selected().is_one_off
    except assets.AssetError:
        return False


@dataclass(frozen=True)
class Definition:
    check: str
    severity: str
    formats: tuple[str, ...]
    name: str
    retired: bool


def definitions(path: Path | str | None = None) -> list[Definition]:
    """Every file check the selected asset runs - the shared default merged
    with its own file (`path`, else the asset folder's) - in NAMES order,
    additions after."""
    out = [Definition(check=str(raw["check"]), severity=str(raw["severity"]),
                      formats=tuple(raw.get("formats") or ("csv",)),
                      name=str(raw.get("name") or raw["check"]).strip(),
                      retired=bool(raw.get("retired_as_of")))
           for raw, _source in merged(path)]
    order = {n: i for i, n in enumerate(NAMES + ONE_OFF_NAMES)}
    return sorted(out, key=lambda d: order.get(d.check, len(order)))


def active(fmt: str = "csv", path=None) -> list[Definition]:
    return [d for d in definitions(path) if not d.retired and fmt in d.formats]


def check_id_for(dataset, check: str) -> str:
    """Criterion 4: `<asset>.<agency>.<collection>.<dataset>.<check>_file`."""
    return (f"{dataset.data_asset_id}.{dataset.agency_id}.{dataset.collection_id}."
            f"{dataset.dataset_id}.{check}_{TOOL}")
