"""REQ-PIPE-390: the order of the dataset statuses and the words for them are
held once, in asset_model/statuses.py, and every former copy reads them.

Criterion 3: each former copy ranks green, amber and red exactly as it did -
proven here by driving each READER, not by comparing tables: the dashboard
rollup (dataset_status.worst_of), the re-check's "is it worse"
(rechecking.is_worse), the target trial's "what does the target allow"
(target_agreement.responsible) and the Linkage Products provider's planned
verdict (worst). Each asserts the order the old {"green": 0, "amber": 1,
"red": 2} copy gave, and that a quiet status is still no verdict where it was
none. Criterion 2: status_words is the one set of words, read by the
pipeline and by the map writer's side through asset_model.
"""
from __future__ import annotations

import itertools

import pytest

from asset_model import statuses
from collection_modules import provider_module
from qa_tools.common import dataset_status, rechecking
from bootstrap import target_agreement

#: The data asset this module's tests act for (C11): the provider is the
#: quarterly asset's; the other readers read no asset.
pytestmark = pytest.mark.asset("quarterly")

VERDICTS = ("green", "amber", "red")
#: What the copies said, written out here rather than read from asset_model,
#: so a slip in the one table fails a test.
OLD = {"green": 0, "amber": 1, "red": 2}


def test_the_order_is_held_once_in_asset_model():
    assert statuses.ORDERED_STATUSES == {"nodata": -1, "green": 0, "amber": 1, "red": 2}
    assert statuses.VERDICT_ORDER == OLD
    # the pipeline's rollup reads the same object, not a copy of it
    assert dataset_status.ORDERED_STATUSES is statuses.ORDERED_STATUSES


@pytest.mark.parametrize("a,b", list(itertools.product(VERDICTS, repeat=2)))
def test_the_dashboard_rollup_ranks_as_it_did(a, b):
    assert dataset_status.worst_of([a, b]) == max((a, b), key=OLD.__getitem__)


def test_the_rollup_still_puts_nodata_below_green_and_refuses_the_unordered():
    assert dataset_status.worst_of(["nodata", "green"]) == "green"
    with pytest.raises(statuses.UnknownStatusError):
        dataset_status.worst_of(["exhausted"])


@pytest.mark.parametrize("before,now", list(itertools.product(VERDICTS, repeat=2)))
def test_a_recheck_is_worse_exactly_as_it_was(before, now):
    assert rechecking.is_worse(before, now) is (OLD[now] > OLD[before])


@pytest.mark.parametrize("quiet", ["nodata", None, "exhausted"])
def test_a_quiet_status_is_never_worse_for_a_recheck(quiet):
    """nodata is in the order but no verdict, as it was absent from the copy."""
    assert rechecking.is_worse("green", quiet) is False
    assert rechecking.is_worse(quiet, "red") is False


def _records(monkeypatch, verdicts):
    from qa_tools.common import promotion

    tool = {"green": "pass", "amber": "warn", "red": "fail", "nodata": "nodata"}
    records = [{"check_id": f"a.b.c.d.check{i}", "status": tool[v]} for i, v in enumerate(verdicts)]
    monkeypatch.setattr(promotion, "_contributing_records", lambda *a, **k: records)
    monkeypatch.setattr(promotion, "_gating_status", lambda r: r["status"])
    return records


@pytest.mark.parametrize("target", VERDICTS)
def test_a_target_trial_allows_what_it_did(monkeypatch, target):
    _records(monkeypatch, ["green", "amber", "red"])
    named = target_agreement.responsible("cp-clients", [], target, reads={})
    worse = sorted(v for v in VERDICTS if OLD[v] > OLD[target])
    if not worse:
        # nothing ranks above red: better than built is said, not left empty
        assert named == ("no check failed",), named
        return
    assert len(named) == len(worse), named
    for v in worse:
        assert any(statuses.status_words(v, "label") in n for n in named), (v, named)


def test_a_target_trial_still_reads_a_quiet_status_as_its_own_verdict(monkeypatch):
    _records(monkeypatch, ["nodata"])
    assert target_agreement.responsible("cp-clients", [], "red", reads={}) == ("check0 No data",)


@pytest.mark.parametrize("a,b", list(itertools.product(VERDICTS, repeat=2)))
def test_the_providers_planned_verdict_ranks_as_it_did(a, b):
    lp = provider_module("linkage-products")
    assert lp.worst(a, b) == max((a, b), key=OLD.__getitem__)
    assert lp.worst() == "green"


@pytest.mark.parametrize("value,form,said", [("red", "label", "Fail"), ("amber", "verb", "warning"),
                                             ("nodata", "count", "no data")])
def test_the_words_are_held_once_and_refuse_a_status_they_have_none_for(value, form, said):
    assert statuses.status_words(value, form) == said
    with pytest.raises(statuses.UnknownStatusError):
        statuses.status_words("purple")
