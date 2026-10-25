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

from qa_tools.common import decision_log, promotion


@pytest.fixture
def captured(monkeypatch):  # noqa: D401
    """The call both orchestrators make into the gate - since REQ-PIPE-266
    the one package gate, gate.after_arrival, which names the rule as the
    actor of every promotion and hold-back it records."""
    from qa_tools.common import gate, knock_on

    seen = {}

    def fake_after_arrival(collection_id, arrival, **kw):
        seen.update(kw)
        return gate.Applied()

    monkeypatch.setattr(gate, "after_arrival", fake_after_arrival)
    monkeypatch.setattr(gate, "report", lambda outcome: None)
    monkeypatch.setattr(knock_on, "follow_up_stream", lambda *a, **k: [])
    return seen


ARRIVAL = SimpleNamespace(received_at=None, run_id="run_001")


@pytest.mark.parametrize("collection_id", ["civil-registration", "child-protection"],
                         ids=["bdm", "cp"])
def test_the_rule_not_the_operator_is_the_actor(collection_id, captured, monkeypatch):
    from qa_tools.tools import orchestrate

    monkeypatch.setattr(promotion, "effective_at_for",
                        lambda *a, **k: SimpleNamespace(isoformat=lambda: "2026-10-04T00:00:00+08:00"))
    orchestrate.promote_after(collection_id, ARRIVAL, [], "someone@example.org")

    # THE OPERATOR IS NEVER HANDED TO THE GATE AS AN ACTOR - only as who ran
    # the pipeline; the gate's own records name the rule.
    assert "actor" not in captured and "actor_kind" not in captured
    assert captured["run_by"] == "someone@example.org"
    import inspect

    from qa_tools.common import gate

    source = inspect.getsource(gate._decide) + inspect.getsource(gate._record_holdback)
    assert "actor=promotion.RULE_ACTOR" in source and "actor_kind=decision_log.RULE" in source
    assert decision_log.RULE == "rule"


def test_the_rule_has_a_name_of_its_own():
    assert promotion.RULE_ACTOR == "promotion rule"
