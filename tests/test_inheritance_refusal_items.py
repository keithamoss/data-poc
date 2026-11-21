"""A dataset's refused inheritances are ONE queue item, its periods in date
order (post-build-review #493 M4): a weekly dataset's first days before any
supply it could stand on read as four separate 'No earlier supply to stand on'
items, Thursday sorted last."""
import pytest

from qa_tools.common import inheritance, outstanding

pytestmark = pytest.mark.asset("daily")


def test_one_item_per_dataset_its_days_in_order(monkeypatch):
    days = ["2026-09-03", "2026-09-01", "2026-09-02", "2026-09-04"]  # Thu, Tue, Wed, Fri
    monkeypatch.setattr(inheritance, "refusals", lambda conn=None: [
        inheritance.Refused(dataset_id="mental-health-contacts", period=d, reason="nothing earlier")
        for d in days])
    items = outstanding._from_inheritance_refusals()
    assert len(items) == 1, [i.headline for i in items]
    said = items[0].headline + " " + items[0].detail
    assert "4 days" in said, said
    # In date order: Tuesday 1 September first, Friday 4 September last.
    assert said.index("1 September") < said.index("4 September"), said


def test_one_refusal_still_names_its_period(monkeypatch):
    monkeypatch.setattr(inheritance, "refusals", lambda conn=None: [
        inheritance.Refused(dataset_id="mental-health-contacts", period="2026-09-01",
                            reason="nothing earlier")])
    items = outstanding._from_inheritance_refusals()
    assert len(items) == 1 and "1 September" in items[0].headline, items[0].headline
