"""Cutting a collection's datasets short, for REQ-DASH-041's render tests.

The real history cannot show datasets arriving on their own schedules - the
generator emits one six-table delivery per period - so
`tests/test_dashboard_e2e.py`'s `dashboard_html_with_divergent_arrivals`
constructs the divergence by keeping only each named dataset's first N runs.

THE CUT IS ON `runs` AND EVERYTHING KEYED BY RUN, not on `runs` alone:
leaving a check's history pointing at a run the dataset no longer has is a
shape the real data can never produce, and a test built on one proves
nothing about the real page.
"""
from __future__ import annotations


def cut_datasets_short(data: dict, keep: dict[str, int]) -> dict:
    """Keep only the first `keep[id]` runs of each named dataset in a
    collection's dashboard file, and everything keyed by them. Mutates and
    returns `data`."""
    for dataset in data["datasets"]:
        n = keep.get(dataset["id"])
        if n is None:
            continue
        dataset["runs"] = dataset["runs"][:n]
        kept = {r["run_id"] for r in dataset["runs"]}
        dataset["arrivalHistory"] = [a for a in dataset.get("arrivalHistory") or []
                                     if a["run_id"] in kept]
        dataset["arrivalByRun"] = {k: v for k, v in (dataset.get("arrivalByRun") or {}).items()
                                   if k in kept}
        dataset["lastArrival"] = {
            **(dataset.get("lastArrival") or {}),
            "run_date": dataset["runs"][-1]["run_date"]}
        # A RESULT BELONGS TO THE SUPPLY IT IS ABOUT, not only to the run that
        # recorded it (post-build-review #269): a cross-table check is often
        # recorded under another table's run (#253), and since REQ-PIPE-265 a
        # same-instant sibling's run is its only record. Cutting by run alone
        # dropped those while `counted` still named them.
        supplies = {r["supply_id"] for r in dataset["runs"] if r.get("supply_id")}
        about_kept = lambda h: h["run_id"] in kept or h.get("supply_id") in supplies  # noqa: E731
        for column in dataset.get("columns") or []:
            for check in column.get("checks") or []:
                check["history"] = [h for h in check.get("history") or [] if about_kept(h)]
                if "superseded" in check:
                    check["superseded"] = [h for h in check["superseded"]
                                           if h.get("supply_run") in kept or about_kept(h)]
                if "contested_reads" in check:
                    check["contested_reads"] = [h for h in check["contested_reads"] if about_kept(h)]
                if "counted" in check:
                    check["counted"] = {k: v for k, v in check["counted"].items() if k in supplies}
            stats = column.get("stats") or {}
            stats["byRun"] = {k: v for k, v in (stats.get("byRun") or {}).items() if k in kept}
    return data
