"""One dataset's file checks, shaped for the dashboard's file section
(REQ-DASH-097).

A PSEUDO-COLUMN BESIDE `columns`, NEVER INSIDE IT. Being in `columns` is
what folds a check's verdict into the dataset's status (the scope sections
REQ-QAC-037 added rely on exactly that), and criterion 2 forbids it for a
file check. So this is `fileChecks` on the dataset: the page renders it in
a section of its own and opens each check in the same check panel, by the
same route, as any other - but nothing that rolls a dataset up ever walks
it.

RECORDED QA RESULTS ONLY (criterion 11): the file scope and the committed
check definitions, never a supply row.

Each history entry is one LOAD ATTEMPT of one file, dated by that file's
own receipt so the page can pick the attempt in force on the date on show.
"""
from __future__ import annotations

from qa_tools.common import dataset_status, file_checks, hierarchy
from qa_tools.common import qa_results_reader as reader

#: The pseudo-column's key in a URL (`/column/_file/check/<key>`). A leading
#: underscore cannot be a real column name: the contracts' columns are
#: plain identifiers, and the reserved-name gate already refuses `_`-names
#: for tables.
KEY = "_file"
NAME = "The file as delivered"


def for_dataset(dataset_id: str, conn=None) -> dict:
    from qa_tools.common.validate_check_lifecycle import collect_checks

    ds = hierarchy.dataset(dataset_id)
    lifecycle = {c.check_id: c for c in collect_checks(None) if c.tool == file_checks.TOOL}
    results = reader.read_file_results(ds.agency_id, ds.collection_id, dataset_id, conn=conn)
    by_check: dict[str, list[dict]] = {}
    for r in results:
        received = r["received_at"] or ""
        by_check.setdefault(r["check_id"], []).append({
            "run_id": r["run_id"],
            "run_date": received[:10],
            "receivedAt": received,
            "status": dataset_status._DASHBOARD_STATUS_BY_TOOL_STATUS.get(r["status"], "red"),
            "finding": r["finding"],
            "filename": r["filename"],
            "delivery": r["delivery"],
            "attempt": r["load_attempt"],
        })
    checks = []
    for definition in file_checks.definitions():
        check_id = file_checks.check_id_for(ds, definition.check)
        meta = lifecycle.get(check_id)
        history = by_check.get(check_id, [])
        checks.append({
            "check_id": check_id,
            "key": f"{definition.check}_{file_checks.TOOL}",
            "name": definition.name,
            "tool_ref": f"file:{definition.check}",
            "severity": definition.severity,
            "scope": "file",
            "retired_as_of": meta.retired_as_of if meta else None,
            "retired_reason": meta.retired_reason if meta else None,
            "description": meta.description if meta else None,
            # technical_note deliberately absent, as on every other check:
            # this dict is published.
            "failure_indicates": meta.failure_indicates if meta else None,
            "changelog": meta.changelog if meta else [],
            # The newest attempt's; the page reads the attempt in force on
            # the date on show instead. "nodata", never None: a check with
            # no file yet has measured nothing, and must not fall back to
            # the threshold arithmetic data checks use.
            "current_status": history[-1]["status"] if history else "nodata",
            "history": history,
        })
    return {"key": KEY, "name": NAME, "scope": "file", "checks": checks}
