"""The configuration-time half of the road-testing sweep's #7 (Keith,
2026-10-06): a SodaCL check this project's Soda Core cannot run is refused
in CI, before any run, rather than discovered as a red run later."""
from __future__ import annotations

from qa_tools.common import validate_soda


def _write(tmp_path, body):
    path = tmp_path / "x-soda-checks.yml"
    path.write_text(body)
    return path


def test_the_real_check_files_pass():
    assert validate_soda.problems() == []


def test_a_check_that_needs_soda_cloud_is_refused(tmp_path):
    path = _write(tmp_path, "checks for t:\n  - change for row_count:\n      warn: when > 10\n"
                            "      attributes:\n        check_id: a.b.c\n")
    found = validate_soda.problems([path])
    assert len(found) == 1 and "Soda Cloud" in found[0] and "change for row_count" in found[0]


def test_a_check_soda_cannot_parse_is_refused(tmp_path):
    path = _write(tmp_path, "checks for t:\n  - row_cnt >>> 0\n")
    found = validate_soda.problems([path])
    assert found and "row_cnt" in found[0]


def test_it_is_a_mothman_check_gate():
    from cli import check

    assert any(name == "soda" for name, *_ in check._GATES)


def test_the_sightings_two_green_misconfigurations_are_refused(tmp_path):
    """The two cases road-testing #7 saw PASS at 0% invalid while checking
    nothing: an unsupported `valid sql`, and `valid min` given a date."""
    sql = _write(tmp_path, "checks for t:\n  - invalid_percent(c):\n      valid sql: \"c > 0\"\n"
                           "      fail: when > 1%\n")
    assert validate_soda.problems([sql])
    date = tmp_path / "y-soda-checks.yml"
    date.write_text("checks for t:\n  - invalid_percent(date_of_birth):\n"
                    "      valid min: 2020-01-01\n      fail: when > 1%\n")
    assert validate_soda.problems([date])
