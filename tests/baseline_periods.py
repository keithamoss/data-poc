"""The suite's made-up periods, declared on a TEST BASELINE (REQ-PIPE-345
criterion 5; Keith, 2026-11-15, option (a)).

A period schema is created only for a period the asset's baseline names, so
a test that files or promotes into a made-up period - `2099-Q1`,
`2099-A<tag>`, a uuid-suffixed one - declares it first. Declaring writes a
real calendar.yaml: a copy of the selected asset's, its baseline given one
more version, effective long after any real date, whose authored dates are
those periods. Nothing is exempted from the guard; the test's asset simply
has those periods on its baseline, as a real asset's would.

The selected asset is pointed at a copy of its folder for the rest of the
test (the suite's autouse `selected_asset` fixture puts it back). A test
already pointed at a copy of its own has the version added to that copy.
"""
from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path

import yaml

import asset_folders
from qa_tools.common import assets

#: Where an undated made-up period falls: August 2099 and on, a day apiece -
#: after every real date, and in a month every quarterly dataset owes (Child
#: Protection's case workers owe only February and August).
UNDATED_FROM = date(2099, 8, 1)
#: Marks the test version, so a second declaration finds it again.
CHANGE = "a test's made-up periods (tests/baseline_periods.py)"


def _is_real(folder: Path) -> bool:
    real = assets._DEFAULT.asset(assets.selected().name).folder
    return Path(folder).resolve() == real.resolve()


def _undated_from(versions: list) -> date:
    """Where undated made-up periods start. On authored dates, August 2099.
    ON A CADENCE RULE, two years from the asset's today: the test version
    ends the rule the day before, and every slot a dataset has unbounded is
    generated a day at a time - ending it in 2099 made each such call build
    some 27,000 daily slots (test_door_flag_parity's two-files case, about
    three minutes)."""
    from qa_tools.common import asset_time

    rule = any((v or {}).get("cadence") for v in versions
               if CHANGE not in str((v or {}).get("changelog")))
    if not rule:
        return UNDATED_FROM
    return asset_time.local_date(asset_time.now()) + timedelta(days=730)


def declare(*names: str, dates: dict | None = None, root: Path | None = None) -> None:
    """Put each of `names` on the selected asset's baseline, keeping every
    period already declared by this test. `dates` gives a name the date the
    test means for it (a test that also patches schedule.date_of should pass
    the same dates); others fall from August 2099 a day apiece. A name the
    real baseline already has is left as it is.

    The test version starts on the earliest declared date, so no real
    period's version of effect changes. On a cadence-rule baseline the rule
    then ends the day before - 2099, decades past any real date."""
    from qa_tools.common import schedule

    dates = {k: (v if isinstance(v, date) else date.fromisoformat(str(v)))
             for k, v in (dates or {}).items()}
    if _is_real(assets.selected().folder):
        folder = Path(tempfile.mkdtemp(prefix="test-baseline-", dir=root))
        asset_folders.point(folder)
    path = assets.selected().folder / "calendar.yaml"
    doc = yaml.safe_load(path.read_text())
    versions = doc["calendars"][0]["versions"]
    mine = next((v for v in versions
                 if any(CHANGE == (c or {}).get("change") for c in v.get("changelog") or [])),
                None)
    if mine is None:
        mine = {"effective_from": None, "claim_window": versions[-1].get("claim_window"),
                "changelog": [{"date": "2026-11-15", "author": "a test", "change": CHANGE}],
                "dates": []}
        versions.append(mine)
    held = {d["period"]: date.fromisoformat(str(d["date"])) for d in mine["dates"]}
    first_undated = _undated_from(versions)
    undated = sorted(d for d in held.values() if d >= first_undated)
    nxt = (undated[-1] + timedelta(days=1)) if undated else first_undated
    for name in names:
        if name in held:
            if name in dates:
                held[name] = dates[name]
            continue
        if schedule.on_baseline(name):
            continue
        if name in dates:
            held[name] = dates[name]
        else:
            while nxt in held.values() or nxt in dates.values():
                nxt += timedelta(days=1)
            held[name] = nxt
            nxt += timedelta(days=1)
    ordered = sorted(held.items(), key=lambda kv: kv[1])
    mine["dates"] = [{"period": n, "date": d.isoformat()} for n, d in ordered]
    mine["effective_from"] = ordered[0][1].isoformat()
    asset_folders.replace("calendar.yaml", yaml.safe_dump(doc, sort_keys=False))


def made_up(stem: str = "", width: int = 6) -> str:
    """A fresh made-up period - `2099-<stem><hex>`, unique to this call, as
    the suite has always named its isolated periods - declared on the test
    baseline so a period schema may be created for it."""
    import uuid

    name = f"2099-{stem}{uuid.uuid4().hex[:width]}"
    declare(name)
    return name
