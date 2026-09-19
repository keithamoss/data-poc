"""Tests for qa_tools/common/local_check.py - shared logic behind the
Thread A on-demand CLIs (plans/running-thoughts.md #5, 2026-09-19)."""
from __future__ import annotations
import os

from qa_tools.common.local_check import copy_into, format_report, run_id_from_path


def test_run_id_from_path_includes_the_source_stem():
    run_id = run_id_from_path("/home/keith/Downloads/birth_registrations_2026-09-19.csv")
    assert run_id.startswith("adhoc_birth_registrations_2026-09-19_")


def test_run_id_from_path_strips_a_trailing_slash_for_a_folder():
    run_id = run_id_from_path("/home/keith/Downloads/cp_delivery_09/", prefix="ref")
    assert run_id.startswith("ref_cp_delivery_09_")


def test_run_id_from_path_carries_a_real_utc_timestamp_suffix():
    import re
    run_id = run_id_from_path("x.csv")
    assert re.search(r"_\d{8}T\d{6}Z$", run_id), f"expected a real UTC timestamp suffix, got {run_id!r}"


def test_copy_into_creates_dest_dir_and_copies_content(tmp_path):
    src = tmp_path / "src.csv"
    src.write_text("id\n1\n")
    dest_dir = tmp_path / "nested" / "dest"

    dest_path = copy_into(str(src), str(dest_dir), "copied.csv")

    assert dest_path == os.path.join(str(dest_dir), "copied.csv")
    assert open(dest_path).read() == "id\n1\n"


def test_copy_into_is_a_no_op_when_src_already_is_dest(tmp_path):
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    existing = dest_dir / "same.csv"
    existing.write_text("id\n1\n")

    dest_path = copy_into(str(existing), str(dest_dir), "same.csv")

    assert dest_path == str(existing)
    assert open(dest_path).read() == "id\n1\n"


def _result(status, column_name="sex", label="Some check", metric_value=None, unit=None):
    return {"status": status, "column_name": column_name, "label": label, "metric_value": metric_value, "unit": unit}


def test_format_report_summarizes_counts_and_lists_failures():
    results = [_result("pass"), _result("pass"), _result("warn", column_name="place_of_birth_suburb"),
               _result("fail", column_name="date_of_birth", label="out of range", metric_value=3, unit="%")]

    report = format_report(results, "adhoc_run_01")

    assert "4 checks - 2 pass, 1 warn, 1 fail, 0 error" in report
    assert "[FAIL] date_of_birth - out of range (3%)" in report
    assert "[WARN] place_of_birth_suburb" in report


def test_format_report_says_no_failures_when_clean():
    results = [_result("pass"), _result("pass")]
    report = format_report(results, "adhoc_run_01")
    assert "No failures or errors." in report
