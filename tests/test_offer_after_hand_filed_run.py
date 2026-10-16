"""post-build-review #82 - REQ-GHUB-082 criterion 17 on the HAND-FILED
routes.

Criterion 17: a run that leaves its supply waiting on a decision offers
that decision in its own flow. The offer was wired only on the synthetic
route; a supply kept from a local file, a folder or S3 ended at
`_finish_supply` and never asked. Whether there is anything to decide,
and whether the terminal is interactive, is offer_after_run's own
business and covered by its own tests - this asserts only that the
hand-filed routes ask it, for a KEPT run, and never for a trial.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from cli import bdm, cp, filing_tui


@pytest.fixture
def offers(monkeypatch):
    calls = []
    monkeypatch.setattr(filing_tui, "offer_after_run",
                        lambda collection_id, run_key: calls.append((collection_id, run_key)))
    return calls


@pytest.mark.parametrize("module", [bdm, cp], ids=["bdm", "cp"])
def test_a_kept_hand_filed_run_offers_the_decision(module, offers, monkeypatch):
    monkeypatch.setattr(module, "report_table", lambda results, run_id: "")
    filed = SimpleNamespace(run_id="handfiled_abc", delivery_name="handfiled-abc")

    module._finish_supply([], filed)

    assert offers == [(module.COLLECTION_ID, "handfiled_abc")]


@pytest.mark.parametrize("module", [bdm, cp], ids=["bdm", "cp"])
def test_a_trial_offers_nothing(module, offers, monkeypatch):
    monkeypatch.setattr(module, "report_table", lambda results, run_id: "")
    filed = SimpleNamespace(run_id="trial_abc", delivery_name=None)

    module._finish_supply([], filed)

    assert offers == []
