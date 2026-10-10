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


def _soda_limits() -> set[int]:
    import yaml

    limits = set()
    for path in soda_common.SODA_CHECK_FILES:
        doc = yaml.safe_load(open(path)) or {}
        for key, checks in doc.items():
            for item in checks if key.startswith("checks for") else []:
                for cfg in (item.values() if isinstance(item, dict) else []):
                    if isinstance(cfg, dict) and "samples limit" in cfg:
                        limits.add(cfg["samples limit"])
    return limits


def test_soda_is_asked_for_enough_rows_to_pick_the_lowest(supply_dsn):
    """The edge #129 left open: our checks capped Soda at five rows, so past
    five failing rows Soda chose WHICH five before our sort saw them. Real
    Soda, the real files' limit, rows stored so the first five are not the
    lowest five."""
    from soda.scan import Scan

    # THE TIGHTEST LIMIT ANY CHECK SETS - the "failed rows" checks ask for
    # far more on purpose (sodadata/soda-core#1985), so it binds elsewhere.
    limit = min(_soda_limits())
    with supply_db.connect(label="test-samples-soda") as conn:
        conn.execute("DROP SCHEMA IF EXISTS sample_probe_soda CASCADE")
        conn.execute("CREATE SCHEMA sample_probe_soda")
        conn.execute("CREATE TABLE sample_probe_soda.t (pk text, col text)")
        for k in KEYS:
            conn.execute("INSERT INTO sample_probe_soda.t VALUES (?, NULL)", [k])
    try:
        scan = Scan()
        scan.set_data_source_name("probe")
        scan.add_configuration_yaml_str(supply_db.soda_config_yaml("probe", "sample_probe_soda"))
        scan.add_sodacl_yaml_str(
            f"checks for t:\n  - missing_count(col) = 0:\n      samples limit: {limit}\n")
        sampler = soda_common.CaptureSampler()
        scan.sampler = sampler
        scan.disable_telemetry()
        soda_common.execute_scan(scan)
        (name,) = sampler.captured
        assert soda_common.failing_sample_keys(sampler.captured, name, "pk") == WANT
    finally:
        with supply_db.connect(label="test-samples-soda") as conn:
            conn.execute("DROP SCHEMA sample_probe_soda CASCADE")
    assert limit >= soda_common.SODA_SAMPLES_LIMIT


def test_the_dashboards_fine_print_states_the_real_limits():
    """The page says 100 for Soda and 5 for datacontract-cli; both are
    somebody else's number, so a change to either must move the page too."""
    import re
    from pathlib import Path

    from datacontract.engines.ibis import ibis_check_execute

    page = (Path(__file__).resolve().parent.parent / "dashboard"
            / "qa-reporting-dashboard.template.html").read_text()
    stated = dict(re.findall(r"^const (SODA_SAMPLES_ASKED|DATACONTRACT_SAMPLES_RETURNED) = (\d+);",
                             page, re.M))
    assert int(stated["SODA_SAMPLES_ASKED"]) == soda_common.SODA_SAMPLES_LIMIT
    assert int(stated["DATACONTRACT_SAMPLES_RETURNED"]) == ibis_check_execute._FAILED_SAMPLE_LIMIT
