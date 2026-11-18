"""The premise the runway tests on the real quarterly calendar were written
against: Child Protection's cp-case-workers, owed two months in four, is the
first dataset on that calendar to run out (REQ-PIPE-053).

Cancer Notifications (REQ-QAC-348), owed once a year, now runs out first -
the right answer, and post-build-review #478's open question is only whether
an annual dataset should count differently. A test of the runway's mechanics
states its premise by reading the asset without the annual dataset - the
hierarchy's list of datasets, which runway and these tests' own counts both
walk - rather than by hoping the real calendar still answers as it did."""
from __future__ import annotations

#: Datasets on the quarterly calendar these tests leave out, and why.
LEFT_OUT = {"cancer-notifications": "owed once a year (REQ-QAC-348; #478)"}


def child_protections_calendar(monkeypatch) -> None:
    from asset_model import hierarchy

    real = hierarchy.all_datasets
    monkeypatch.setattr(hierarchy, "all_datasets",
                        lambda *a, **k: [d for d in real(*a, **k) if d.dataset_id not in LEFT_OUT])
