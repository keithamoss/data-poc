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


def test_resolve_chromium_path_prefers_the_explicit_env_var(monkeypatch):
    """A real bug, 2026-09-19 (found by claude/playwright-mcp-verify-
    b2t4nb hitting exit 1 in a genuinely fresh sandbox): before this fix,
    an unset PLAYWRIGHT_CHROMIUM_PATH meant Playwright's own default
    channel lookup ran, which fails when the sandbox's installed
    Chromium build doesn't match what the pinned Playwright package
    expects."""
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_PATH", "/some/explicit/path")
    monkeypatch.setattr(cdr, "_SANDBOX_CHROMIUM_SYMLINK", "/does/not/matter")

    assert cdr._resolve_chromium_path() == "/some/explicit/path"


def test_resolve_chromium_path_falls_back_to_the_sandbox_symlink_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_PATH", raising=False)
    fake_symlink = tmp_path / "chromium"
    fake_symlink.write_text("")  # just needs to exist
    monkeypatch.setattr(cdr, "_SANDBOX_CHROMIUM_SYMLINK", str(fake_symlink))

    assert cdr._resolve_chromium_path() == str(fake_symlink)


def test_resolve_chromium_path_returns_none_when_neither_is_available(monkeypatch, tmp_path):
    monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_PATH", raising=False)
    monkeypatch.setattr(cdr, "_SANDBOX_CHROMIUM_SYMLINK", str(tmp_path / "does-not-exist"))

    assert cdr._resolve_chromium_path() is None
