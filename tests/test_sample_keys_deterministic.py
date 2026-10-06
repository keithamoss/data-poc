"""The failing-row samples a check records are the same on every run of the
same data: the lowest keys, in key order (post-build-review #129). They were
the first rows a query without ORDER BY happened to return, so the whole-
bootstrap comparison for REQ-TEST-159 found 20 results whose samples differed
only in order - and past five failing rows, WHICH rows were sampled could
differ too."""
from __future__ import annotations

from types import SimpleNamespace

from qa_tools.common import datacontract_common, dbt_common, soda_common, supply_db

KEYS = ["K-07", "K-02", "K-09", "K-01", "K-05", "K-08", "K-03", "K-06"]
WANT = ["K-01", "K-02", "K-03", "K-05", "K-06"]


def test_dbt_samples_are_the_lowest_keys_in_order(supply_dsn):
    with supply_db.connect(label="test-samples") as conn:
        conn.execute("DROP TABLE IF EXISTS public.sample_probe")
        conn.execute("CREATE TABLE public.sample_probe (pk text)")
        for k in KEYS:
            conn.execute("INSERT INTO public.sample_probe VALUES (?)", [k])
        try:
            assert dbt_common.failing_sample_keys_direct(
                conn, "public.sample_probe", "pk") == WANT
            assert dbt_common.failing_sample_keys_via_values(
                conn, "public.sample_probe", "pk", "public.sample_probe", "pk", "pk") == WANT
        finally:
            conn.execute("DROP TABLE public.sample_probe")


def test_soda_samples_are_the_lowest_keys_in_order():
    captured = {"c": [{"pk": k, "other": 1} for k in KEYS]}
    assert soda_common.failing_sample_keys(captured, "c", "pk") == WANT


def test_datacontract_samples_are_in_key_order():
    """datacontract-cli bounds its own sample; only the order was ours."""
    check = SimpleNamespace(failedSamples=[{"pk": k} for k in KEYS])
    assert datacontract_common.failing_sample_keys(check, "pk") == sorted(KEYS)
