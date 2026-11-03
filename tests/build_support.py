"""Run facts for a hand-built results file (REQ-PIPE-279 criteria 16 and 17).

The build reads what each run IS from the results file's `run_facts`, which
the rebuild writes from qa.run, and refuses a file without them. A test that
writes its own results file states them here: each run ranked in the order
it is listed, belonging to the dataset, supply and scope the test says - and
to no supply where it says none, the shape a fixture's or a trial's run has.
"""
from __future__ import annotations


def facts_for(runs, *, datasets=None, supplies=None, scopes=None) -> dict[str, dict]:
    """{run id: facts} for `runs` (arrival records), ranked in list order."""
    datasets, supplies, scopes = datasets or {}, supplies or {}, scopes or {}
    out = {}
    for rank, m in enumerate(runs, start=1):
        run_id = m["run_id"]
        supply = supplies.get(run_id)
        out[run_id] = {"dataset_id": datasets.get(run_id), "scope": scopes.get(run_id, "arrival"),
                       "supply_id": supply, "rank": rank,
                       "cause": f"arrival:{run_id}" if supply else None}
    return out
