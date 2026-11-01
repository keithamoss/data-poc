"""REQ-PIPE-341 criterion 7: REQ-TEST-239's before-and-after compare of a
from-empty bootstrap shows no recorded sample of Birth Registrations, Child
Protection or Emergency Department changed, lists what changed for Linkage
Keys, and shows the failing linkage referential results post-build-review
#291 found recorded empty now record their failing rows as dataset code and
identifier values - which meets REQ-QAC-333 criterion 6.

ON DEMAND, and WRITTEN BEFORE IT COULD RUN: each side is a from-empty
bootstrap of about half an hour or more, deferred to the end-of-run bootstrap
(2026-11-01 build run). Capture the two baselines first:

    mothman debug equivalence capture <commit before the build> req-pipe-341-before
    mothman debug equivalence capture <the build's commit> req-pipe-341-after

THE ONE DELIBERATE CHANGE OUTSIDE LINKAGE, and why it is allowed here
(criterion 7 as amended 2026-11-01, Keith, post-build-review #294 D1): a null
key is now recorded as null, an empty key part, in every tool. It was the text
'None' in datacontract-cli's samples (`str(s[pk_column])`) and dropped by Soda
and dbt. So an after-sample whose non-null keys equal the before-sample's keys
other than 'None' - nulls, last, the only difference - is that one correction,
and each such result is listed rather than hidden.
"""
from __future__ import annotations

import json
import os

import pytest

from qa_tools.common import equivalence as eq

pytestmark = pytest.mark.on_demand

BEFORE = os.environ.get("REQ_PIPE_341_BEFORE", "req-pipe-341-before")
AFTER = os.environ.get("REQ_PIPE_341_AFTER", "req-pipe-341-after")
LINKAGE = "linkage-products"
UNCHANGED = ("civil-registration", "child-protection", "emergency-department")
KEY_COLUMNS = ["dataset", "id_1", "id_2"]


def _samples(baseline: dict) -> dict[tuple, dict]:
    """(collection, run, tool, check_id, occurrence) -> {samples, columns,
    invalid}, from the baseline's qa.check_result rows."""
    table = baseline["surfaces"]["S1"]["qa.check_result"]
    cols = table["columns"]
    at = {c: i for i, c in enumerate(cols)}
    out: dict[tuple, dict] = {}
    for row, count in table["rows"]:
        values = [json.loads(v) for v in row]
        extra = values[at["extra"]] or {}
        if isinstance(extra, str):
            extra = json.loads(extra)
        base = (values[at["collection_id"]], values[at["run_key"]], values[at["tool"]],
                values[at["check_id"]])
        for n in range(count):
            out[base + (n,)] = {"samples": extra.get("failing_sample_keys"),
                                "columns": extra.get("failing_sample_key_columns"),
                                "invalid": values[at["row_count_invalid"]]}
    return out


@pytest.fixture(scope="module")
def sides():
    before, after = _samples(eq.load(BEFORE)), _samples(eq.load(AFTER))
    assert before and after, "a baseline holds no check results - this would prove nothing"
    assert set(before) == set(after), "the two bootstraps recorded different results"
    return before, after


def test_no_sample_of_the_other_collections_changed(sides):
    before, after = sides
    seen, none_dropped, changed = 0, [], []
    for key, was in before.items():
        if key[0] not in UNCHANGED:
            continue
        seen += 1
        now = after[key]
        if now["samples"] == was["samples"] and now["columns"] is None:
            continue
        if (now["columns"] is None and isinstance(was["samples"], list)
                and [k for k in now["samples"] if k is not None]
                == [k for k in was["samples"] if k != "None"]):
            none_dropped.append(key)
            continue
        changed.append((key, was["samples"], now["samples"]))
    assert seen, "no result of the other collections - this would prove nothing"
    print(f"\n{len(none_dropped)} result(s) changed only by a null key now recorded as null: "
          f"{none_dropped[:20]}")
    assert not changed, changed[:10]


def test_what_changed_for_linkage_keys_is_listed(sides):
    before, after = sides
    rows = [(key, before[key]["samples"], after[key]["samples"])
            for key in before if key[0] == LINKAGE
            and before[key]["samples"] != after[key]["samples"]]
    print(f"\nLinkage Keys: {len(rows)} result(s) whose samples changed")
    for key, was, now in rows:
        print(f"  {key[1]} {key[3].rsplit('.', 2)[-2:]}: {was} -> {now}")
    for key in after:
        if key[0] == LINKAGE and after[key]["invalid"] is not None:
            assert after[key]["columns"] == KEY_COLUMNS, key


def test_the_referential_results_found_empty_now_name_their_records(sides):
    """linkage_keys__201808011730000800 (ed-presentations),
    linkage_keys__202205011730000800 and linkage_keys__202211011730000800
    (cp-clients), or their counterparts in the new bootstrap."""
    before, after = sides
    failing = {k: v for k, v in after.items()
               if k[0] == LINKAGE and k[3].endswith(".referential_soda") and (v["invalid"] or 0) > 0}
    assert failing, "no failing linkage referential result - this would prove nothing"
    empty_before = [k for k in failing if not before[k]["samples"]]
    assert empty_before, "none was recorded empty before - not the #291 shape"
    for key, now in failing.items():
        code = "DOC_CLIENTS" if ".cp-clients." in key[3] else "EDDC_PRESENTATION"
        assert now["samples"], key
        for sample in now["samples"]:
            assert isinstance(sample, list) and len(sample) == len(KEY_COLUMNS), (key, sample)
            assert sample[0] == code and sample[1] not in (None, "", "None"), (key, sample)
