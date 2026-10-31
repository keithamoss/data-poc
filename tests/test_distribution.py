"""A binned distribution any check may carry (REQ-QAC-333 criteria 9 and 10)."""
from __future__ import annotations

from pathlib import Path

from qa_tools.common import distribution

LP = (Path(__file__).resolve().parent.parent / "contract" / "department-of-health"
      / "linkage-products-soda-checks.yml")
CID = "data-asset-1.department-of-health.linkage-products.linkage-keys.linkage_key.large_key_groups_soda"


def test_the_large_key_groups_check_declares_its_bins():
    spec = distribution.declared(LP)
    assert list(spec) == [CID]
    assert spec[CID]["edges"] == [51, 101, 151, 201, 251, 501, 1001]


def test_bins_count_each_value_once_the_last_open_ended():
    got = distribution.bins([51, 99, 100, 101, 1000, 1001, 5000], [51, 101, 151, 201, 251, 501, 1001])
    assert [b["count"] for b in got] == [3, 1, 0, 0, 0, 1, 2]
    assert got[-1]["to"] is None and got[0]["to"] == 101


class _Conn:
    def __init__(self, values, population):
        self.values, self.population = values, population

    def execute(self, sql):
        rows = [(v,) for v in self.values] if "GROUP BY" in sql else [(self.population,)]
        return type("R", (), {"fetchall": lambda s: rows, "fetchone": lambda s: rows[0]})()


def test_measure_records_counts_only():
    spec = distribution.declared(LP)[CID]
    got = distribution.measure(_Conn([60, 120], 900), spec)
    assert got["count"] == 2 and got["population"] == 900
    assert sum(b["count"] for b in got["bins"]) == 2
    assert set(got) == {"bins", "count", "population"}
