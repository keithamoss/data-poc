"""The dashboard's file-check panel data (REQ-DASH-097) - exercised by no
test outside the e2e build until post-build-review #118."""
from __future__ import annotations

from pipeline import file_check_panel
from qa_tools.common import qa_results_reader as reader


def _row(received, attempt=1):
    return {"check_id": "data-asset-1.child-protection-family-support.child-protection."
                        "cp-carers.encoding_file",
            "run_id": "r1", "received_at": received, "status": "pass", "finding": "fine",
            "filename": "cp_carers.csv", "delivery": "d", "load_attempt": attempt}


def test_a_receipt_is_dated_on_the_assets_own_calendar(monkeypatch):
    """#118 D-A: 17:30 UTC on the 8th is 01:30 on the 9th in Perth, and the
    date page's 'in place on' filter reads this date."""
    monkeypatch.setattr(reader, "read_file_results",
                        lambda *a, **k: [_row("2026-09-08T17:30:00+00:00")])
    panel = file_check_panel.for_dataset("cp-carers")
    (point,) = next(c for c in panel["checks"] if c["key"] == "encoding_file")["history"]
    assert point["run_date"] == "2026-09-09"
    assert point["receivedAt"] == "2026-09-08T17:30:00+00:00"


def test_every_defined_check_is_listed_even_with_no_results(monkeypatch):
    monkeypatch.setattr(reader, "read_file_results", lambda *a, **k: [])
    panel = file_check_panel.for_dataset("cp-carers")
    assert {c["key"] for c in panel["checks"]} >= {"encoding_file", "fields_per_row_file"}
