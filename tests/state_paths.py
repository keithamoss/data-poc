"""A test's way to point one of the resolver's call-time state paths
somewhere else (REQ-PIPE-342 criterion 6).

The deliveries, receipts, bookkeeping, scenario placements and reports
folders were module constants a test reassigned; they are functions now,
asked at call time, so a test replaces the function with one answering a
fixed path:

    monkeypatch.setattr(delivery, "default_deliveries_dir", fixed(tmp_path / "d"))
"""


def fixed(value):
    """A call-time lookup that always answers `value`."""
    return lambda: value
