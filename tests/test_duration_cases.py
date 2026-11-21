"""The Python half of the shared run-time format (REQ-TEST-416 criterion 4).

Every case comes from duration-cases.json at the repo root, which neither
this suite nor tests-js/duration-cases.test.js owns - as display-time-cases
and status-cases are held."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_tools.common.display_time import format_elapsed

CASES = json.loads((Path(__file__).resolve().parent.parent
                    / "duration-cases.json").read_text())["cases"]


def test_the_table_is_not_empty():
    assert len(CASES) >= 10


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_each_case_reads_the_way_the_table_says(case):
    assert format_elapsed(case["seconds"]) == case["expect"]


pytestmark = pytest.mark.asset("quarterly")
