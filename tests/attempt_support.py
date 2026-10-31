"""A fixture run opened the way qa_results_writer.open_run opens a real one
(REQ-PIPE-279 criterion 5), for a test that builds its runs straight into the
store rather than through the orchestrator.

complete_run refuses a run with no run_seq, and a fixture's run is no
exception: a completed run nobody can put in order against another is the
thing the refusal is there to stop. So a fixture draws one the same way -
an attempt begun and ended COMPLETED - rather than writing the column.
"""
from __future__ import annotations

from qa_tools.common import qa_store


def opened(conn, run_key: str) -> int:
    """Draw `run_key` a run_seq through a completed attempt, and return it.
    Call it after the run's results are written: a write into a run with a
    run_seq and no attempt running is refused (criterion 8)."""
    run_seq = qa_store.begin_attempt(conn, run_key)
    qa_store.set_run_seq(conn, run_key, run_seq)
    qa_store.end_attempt(conn, run_key, run_seq, qa_store.COMPLETED)
    return run_seq


class _AnyCheck(dict):
    """A fingerprints map (REQ-QAC-176 criterion 13) that names every check
    id with one fixed, well-formed fingerprint - for a test that writes
    results about invented check ids straight into the store and is not
    about the fingerprint. A test ABOUT the fingerprint passes a real map."""

    FINGERPRINT = "v1:" + "0" * 64

    def get(self, key, default=None):
        return self.FINGERPRINT if key else default

    def __getitem__(self, key):
        return self.FINGERPRINT

    def __contains__(self, key):
        return bool(key)


ANY_CHECK = _AnyCheck()
