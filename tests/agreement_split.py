"""Write a ONE-FILE schedule configuration out as the two files REQ-PIPE-110
split it into, for tests.

Many schedule tests were written against the asset file when it carried
everything - calendars at the top, each dataset's calendar, delivery
months, own dates and not_expected on the dataset in the hierarchy. Their
point is a rule about the schedule, not which file states it, so rather
than rewrite each one this turns that shape into contract/data-asset.yaml
plus contract/calendar.yaml. `merged_view()` is the reverse, the same view
the schedule gate builds for its own checks.

The new shape's own rules - plain-string changelogs refused, the retired
keys refused, the restate rule - are tested against the two files
directly, never through this.
"""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

from qa_tools.common import schedule
from qa_tools.common.validate_schedule import _merged_view, _walk_datasets

_MOVED = ("calendar", schedule.NO_CALENDAR_KEY, "delivery_months", "dates",
          "not_expected", "owes_from")

#: The author a test-written changelog entry carries.
TEST_AUTHOR = "a test"


def _structured(changelog):
    out = []
    for entry in changelog or []:
        if isinstance(entry, dict):
            out.append(entry)
            continue
        text = str(entry)
        when, _, change = text.partition(": ")
        out.append({"date": when if change else "1970-01-01", "author": TEST_AUTHOR,
                    "change": change or text})
    return out


def merged_view(contract_dir: Path) -> dict:
    asset = yaml.safe_load((contract_dir / "data-asset.yaml").read_text())
    cal = yaml.safe_load((contract_dir / "calendar.yaml").read_text())
    return _merged_view(asset, cal)


def split(merged: dict, calendar_doc: dict) -> tuple[dict, dict]:
    """(asset doc, calendar doc) for a one-file-shaped `merged`, starting
    from `calendar_doc`'s participation versions."""
    asset = copy.deepcopy(merged)
    cal = copy.deepcopy(calendar_doc)
    cal["calendars"] = copy.deepcopy(asset.pop("calendars", None) or [])
    for c in cal["calendars"]:
        for v in (c or {}).get("versions") or []:
            if isinstance(v, dict) and "changelog" in v:
                v["changelog"] = _structured(v["changelog"])
    entries = {d["id"]: d for d in cal.get("datasets") or []}
    collections = {c["id"]: c for c in cal.get("collections") or []}

    walked = list(_walk_datasets(asset))
    # A collection keeps its calendar only while every dataset in it that
    # declares no no-calendar still names it - a test that deletes a
    # dataset's calendar means "this dataset is on none".
    for cid, coll in list(collections.items()):
        members = [d for d, c in walked if (c or {}).get("id") == cid]
        named = coll.get("calendar")
        if any(not (d or {}).get("calendar") and (d or {}).get(schedule.NO_CALENDAR_KEY) is None
               for d in members):
            coll.pop("calendar", None)
            named = None
        coll["_named"] = named

    for dataset, collection in walked:
        if not isinstance(dataset, dict):
            continue
        moved = {k: dataset.pop(k) for k in _MOVED if k in dataset}
        did = dataset.get("id")
        entry = entries.get(did)
        if entry is None:
            entry = {"id": did}
            entries[did] = entry
            cal.setdefault("datasets", []).append(entry)
        coll = collections.get((collection or {}).get("id"), {})
        entry.pop("calendar", None)
        entry.pop(schedule.NO_CALENDAR_KEY, None)
        if moved.get(schedule.NO_CALENDAR_KEY) is not None:
            entry[schedule.NO_CALENDAR_KEY] = moved[schedule.NO_CALENDAR_KEY]
            if moved.get("delivery_months") is None:
                entry.pop("participation", None)
            if moved.get("calendar"):
                entry["calendar"] = moved["calendar"]
        elif moved.get("calendar") and moved["calendar"] != coll.get("_named"):
            entry["calendar"] = moved["calendar"]
        versions = ((entry.get("participation") or {}).get("versions")) or []
        versions = [copy.deepcopy(v) for v in versions]
        if not versions and (moved.get(schedule.NO_CALENDAR_KEY) is None
                             or moved.get("delivery_months") is not None):
            # A hand-written hierarchy has no participation to start from;
            # every dataset on a calendar needs one (criterion 3).
            versions = [{"effective_from": "1970-01-01", "expected_time": "09:00",
                         "grace": "0h",
                         "changelog": [{"date": "1970-01-01", "author": TEST_AUTHOR,
                                        "change": "a test's participation"}]}]
        for v in versions:
            v.pop("participates", None)
            v.pop("reason", None)
            if moved.get("delivery_months") is not None:
                v["participates"] = moved["delivery_months"]
                v["reason"] = "a test's partial participation"
        if "owes_from" in moved and versions:
            versions[0]["effective_from"] = str(moved["owes_from"])
        if versions:
            entry["participation"] = {"versions": versions}
        if "not_expected" in moved:
            entry["not_expected"] = moved["not_expected"]
        else:
            entry.pop("not_expected", None)
        if "dates" in moved:
            entry["dates"] = {"versions": [{
                "effective_from": "1970-01-01",
                "changelog": [{"date": "1970-01-01", "author": TEST_AUTHOR,
                               "change": "a test's own dates"}],
                "dates": moved["dates"]}]}
        else:
            entry.pop("dates", None)
    for coll in collections.values():
        coll.pop("_named", None)
    return asset, cal


#: The committed contract directory, the default base for a calendar file.
REAL_CONTRACT_DIR = Path(__file__).resolve().parent.parent / "contract"


def write(contract_dir: Path, merged: dict, base: dict | None = None) -> None:
    """Write `merged` out as the two files into `contract_dir`, taking
    participation versions from `base` if given, else its own
    calendar.yaml if it has one, else the committed one. Pass `base={}`
    for a hand-written hierarchy that shares nothing with the real one."""
    cal_path = contract_dir / "calendar.yaml"
    if base is None:
        source = cal_path if cal_path.exists() else REAL_CONTRACT_DIR / "calendar.yaml"
        base = yaml.safe_load(source.read_text())
    asset, cal = split(merged, base)
    (contract_dir / "data-asset.yaml").write_text(yaml.safe_dump(asset, sort_keys=False))
    cal_path.write_text(yaml.safe_dump(cal, sort_keys=False))


def clear_caches() -> None:
    """Forget every parsed copy of either file."""
    from qa_tools.common import agreement, asset_time, hierarchy

    agreement.current.cache_clear()
    hierarchy._load.cache_clear()
    asset_time.timezone_versions.cache_clear()


def repoint(monkeypatch, directory: Path, merged: dict, base: dict | None = None) -> Path:
    """Write `merged` as the two files into `directory` and point every
    reader at them - the hierarchy at the asset file, the agreement at the
    calendar file. Returns the asset file's path."""
    from qa_tools.common import agreement, hierarchy

    directory.mkdir(parents=True, exist_ok=True)
    write(directory, merged, base)
    asset_path = directory / "data-asset.yaml"
    monkeypatch.setattr(hierarchy, "DATA_ASSET_YAML", asset_path)
    monkeypatch.setattr(agreement, "CALENDAR_YAML", directory / "calendar.yaml")
    clear_caches()
    return asset_path


def participation(dataset_id: str, **version) -> dict:
    """A calendar-file base holding one dataset's single participation
    version - for a test that needs a value the default does not carry,
    like a claim-window override."""
    v = {"effective_from": "1970-01-01", "expected_time": "09:00", "grace": "0h",
         "changelog": [{"date": "1970-01-01", "author": TEST_AUTHOR,
                        "change": "a test's participation"}], **version}
    return {"datasets": [{"id": dataset_id, "participation": {"versions": [v]}}]}
