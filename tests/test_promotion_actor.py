"""post-build-review #81 - an automatic promotion's actor is the RULE.

REQ-PIPE-074 decided the actor of an automatic decision is the rule's
name, with actor kind `rule`. Both orchestrators passed the git identity
that ran the pipeline instead, so 69 promotions and 9 withholds in a
bootstrapped database named a person-shaped address as the decider while
saying a rule decided. Inheritance already got this right
("inheritance rule"), which is the shape copied here.

Asserted at the call both orchestrators make into the promotion step,
because that is where the identity is chosen; what promotion.py does
with the actor it is given is covered by its own tests.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from qa_tools.bdm import orchestrate_bdm
from qa_tools.common import decision_log, promotion
from qa_tools.cp import orchestrate_cp


@pytest.fixture
def captured(monkeypatch):
    seen = {}

    def fake_after_runs(arrivals, results, **kw):
        seen.update(kw)
        return promotion.AfterRun(promoted=(), refused={}, failed={})

    monkeypatch.setattr(promotion, "after_runs", fake_after_runs)
    monkeypatch.setattr(promotion, "report", lambda outcome: None)
    return seen


ARRIVAL = SimpleNamespace(received_at=None, run_id="run_001")


@pytest.mark.parametrize("module", [orchestrate_bdm, orchestrate_cp],
                         ids=["bdm", "cp"])
def test_the_rule_not_the_operator_is_the_actor(module, captured, monkeypatch):
    monkeypatch.setattr(promotion, "effective_at_for",
                        lambda *a, **k: SimpleNamespace(isoformat=lambda: "2026-10-04T00:00:00+08:00"))
    module.promote_after(ARRIVAL, [], "someone@example.org")

    assert captured["actor_kind"] == decision_log.RULE
    assert captured["actor"] == promotion.RULE_ACTOR
    assert captured["actor"] != "someone@example.org"


def test_the_rule_has_a_name_of_its_own():
    assert promotion.RULE_ACTOR == "promotion rule"
