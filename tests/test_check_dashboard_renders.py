"""Tests for dashboard/check_dashboard_renders.py's structural check
(the embedded-JSON half of Phase 3's CI gate) - not the real-browser
render half. That half now IS covered under pytest, just not in this
file: tests/test_dashboard_e2e.py's TestBuiltDashboardRenders/
test_raw_template_renders_with_zero_console_errors (Phase 6 step 6,
plans/publishing-and-history.md) cover the same real-browser ground
this script's own _check_render() does, as a side effect of that
suite's real user-flow tests. check_dashboard_renders.py itself is
left in place as deploy-pages.yml's own separate pre-publish gate
rather than folded away - see that test module's own docstring and
the step 6 write-up for why."""
from __future__ import annotations

from dashboard import check_dashboard_renders as cdr


def _write_dashboard(path, birth_reg_json="{}", cp_json="{}"):
    path.write_text(
        "<html><script>\n"
        f"const REAL_BIRTH_REG_DATA = {birth_reg_json};\n"
        f"const REAL_CP_DATA = {cp_json};\n"
        "</script></html>\n"
    )


def test_check_embedded_json_passes_for_valid_json(tmp_path, monkeypatch):
    dashboard_path = tmp_path / "dashboard.html"
    _write_dashboard(dashboard_path, birth_reg_json='{"a": 1}', cp_json='{"b": [1, 2]}')
    monkeypatch.setattr(cdr, "DASHBOARD_PATH", dashboard_path)

    assert cdr._check_embedded_json() == []


def test_check_embedded_json_flags_invalid_json(tmp_path, monkeypatch):
    dashboard_path = tmp_path / "dashboard.html"
    _write_dashboard(dashboard_path, birth_reg_json='{"a": 1,}')  # trailing comma - invalid JSON
    monkeypatch.setattr(cdr, "DASHBOARD_PATH", dashboard_path)

    errors = cdr._check_embedded_json()

    assert len(errors) == 1
    assert "REAL_BIRTH_REG_DATA" in errors[0]


def test_check_embedded_json_flags_a_missing_const(tmp_path, monkeypatch):
    dashboard_path = tmp_path / "dashboard.html"
    dashboard_path.write_text("<html><script>\nconst REAL_BIRTH_REG_DATA = {};\n</script></html>\n")
    monkeypatch.setattr(cdr, "DASHBOARD_PATH", dashboard_path)

    errors = cdr._check_embedded_json()

    assert len(errors) == 1
    assert "REAL_CP_DATA" in errors[0]


def test_main_fails_fast_when_the_dashboard_was_never_built(tmp_path, monkeypatch):
    monkeypatch.setattr(cdr, "DASHBOARD_PATH", tmp_path / "does-not-exist.html")

    assert cdr.main() == 1
