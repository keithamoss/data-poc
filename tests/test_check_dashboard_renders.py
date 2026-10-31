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


def _write_dashboard(path, collection_data):
    path.write_text("<html><script>\n"
                    f"const COLLECTION_DATA = {collection_data};\n"
                    "</script></html>\n")


def _every_collection() -> str:
    from qa_tools import collections

    ids = [c.id for c in collections.all_collections()]
    assert ids, "the registry must hold collections for these tests to mean anything"
    return "{" + ",".join(f'"{i}": {{"datasets": []}}' for i in ids) + "}"


def test_check_embedded_json_passes_when_every_collection_is_there(tmp_path, monkeypatch):
    dashboard_path = tmp_path / "dashboard.html"
    _write_dashboard(dashboard_path, _every_collection())
    monkeypatch.setattr(cdr, "DASHBOARD_PATH", dashboard_path)

    assert cdr._check_embedded_json() == []


def test_check_embedded_json_flags_invalid_json(tmp_path, monkeypatch):
    dashboard_path = tmp_path / "dashboard.html"
    _write_dashboard(dashboard_path, '{"a": 1,}')  # trailing comma - invalid JSON
    monkeypatch.setattr(cdr, "DASHBOARD_PATH", dashboard_path)

    errors = cdr._check_embedded_json()

    assert len(errors) == 1 and "COLLECTION_DATA" in errors[0]


def test_check_embedded_json_flags_a_missing_const(tmp_path, monkeypatch):
    dashboard_path = tmp_path / "dashboard.html"
    dashboard_path.write_text("<html><script>\nconst OTHER = {};\n</script></html>\n")
    monkeypatch.setattr(cdr, "DASHBOARD_PATH", dashboard_path)

    assert cdr._check_embedded_json() == ["COLLECTION_DATA: no embedded const found in the built HTML"]


def test_check_embedded_json_names_a_collection_that_is_not_in_it(tmp_path, monkeypatch):
    """REQ-DASH-244 criterion 9: the registry says which collections must be
    there, so a third one registered but not built is named."""
    import json

    dashboard_path = tmp_path / "dashboard.html"
    data = json.loads(_every_collection())
    dropped = next(iter(data))
    del data[dropped]
    _write_dashboard(dashboard_path, json.dumps(data))
    monkeypatch.setattr(cdr, "DASHBOARD_PATH", dashboard_path)

    assert cdr._check_embedded_json() == [f"COLLECTION_DATA: no entry for collection {dropped!r}"]


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


# REQ-DASH-291 criterion 14: the structural check reads COLLECTION_DATA
# through the one reader, and fails a missing file or one whose SHA-256
# differs from the page's list.

def _split_page(tmp_path):
    from dashboard import data_files
    from qa_tools import collections

    files = []
    for c in collections.all_collections():
        files += data_files.encode(data_files.collection_key(c.id), {"datasets": []},
                                   kind="collection", collection=c.id)
    html = ("<html>\n<!-- mothman:data-files -->\n<script>\nconst DATA_FILES = null;\n"
            "const COLLECTION_DATA = null;\n</script></html>\n")
    page = tmp_path / "dashboard.html"
    page.write_text(data_files.embed_into_page(html, data_files.manifest(files)))
    data_files.write(files, tmp_path / "data")
    return page, files


def test_check_embedded_json_reads_the_data_files(tmp_path, monkeypatch):
    page, _ = _split_page(tmp_path)
    monkeypatch.setattr(cdr, "DASHBOARD_PATH", page)
    assert cdr._check_embedded_json() == []


def test_check_embedded_json_fails_a_missing_data_file(tmp_path, monkeypatch):
    page, files = _split_page(tmp_path)
    (tmp_path / "data" / files[0].entry["name"]).unlink()
    monkeypatch.setattr(cdr, "DASHBOARD_PATH", page)
    errors = cdr._check_embedded_json()
    assert any(files[0].entry["name"] in e and "missing" in e for e in errors), errors


def test_check_embedded_json_fails_a_data_file_whose_sha256_differs(tmp_path, monkeypatch):
    page, files = _split_page(tmp_path)
    path = tmp_path / "data" / files[-1].entry["name"]
    path.write_bytes(path.read_bytes().replace(b"datasets", b"datasetz"))
    monkeypatch.setattr(cdr, "DASHBOARD_PATH", page)
    errors = cdr._check_embedded_json()
    assert any(files[-1].entry["name"] in e and "SHA-256" in e for e in errors), errors


def test_the_browser_check_fails_a_page_showing_its_data_file_error(tmp_path):
    """post-build-review #268 T3: REQ-DASH-291 criterion 14's browser half -
    a page that renders its missing-file error fails the gate whatever the
    console says. The real template, given a list naming a file that was
    never written, exactly as embed() would leave it; the raw template
    beside it is the control, so a gate that failed everything would fail
    here too."""
    from dashboard import data_files

    [missing] = data_files.encode(data_files.collection_key("civil-registration"),
                                  {"datasets": []}, kind="collection",
                                  collection="civil-registration")
    page = tmp_path / "page.html"
    page.write_text(data_files.embed_into_page(cdr.TEMPLATE_PATH.read_text(),
                                               data_files.manifest([missing])))
    errors = cdr.render_errors(page, "built output")
    assert any("shows its data-file error" in e and missing.entry["name"] in e
               for e in errors), errors
    control = cdr.render_errors(cdr.TEMPLATE_PATH, "template")
    assert not any("data-file error" in e for e in control), control
