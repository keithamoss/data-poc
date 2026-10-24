"""Tests for dashboard/snapshot_dashboard.py - the "time travel" archiving
mechanism (plans/dashboard.md #5, scoped 2026-09-16). Real requirements this
covers, per that scoping: a snapshot must be byte-for-byte recoverable
(gzip round-trip integrity - the whole point is a self-contained artifact
someone can trust years from now), its filename must be safe on Windows
(plans/wider.md #8's own flag that this needs to run on Windows EC2s
eventually - no colons), and the SNAPSHOT_DASHBOARD=1 gate must actually
gate (off by default, since this PoC has no real "scheduled run" vs.
"developer iterating" distinction to key off automatically)."""
from __future__ import annotations

import gzip
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dashboard import snapshot_dashboard


def _write_fake_dashboard(tmp_path, content: str = "<html>fake dashboard</html>\nconst SNAPSHOT_MANIFEST = [];\n"):
    html_path = tmp_path / "qa-reporting-dashboard.html"
    html_path.write_text(content)
    return html_path


def test_take_snapshot_round_trips_to_identical_bytes(tmp_path):
    html_path = _write_fake_dashboard(tmp_path, "<html>hello world</html>\nconst SNAPSHOT_MANIFEST = [];\n")
    original_bytes = html_path.read_bytes()  # captured BEFORE take_snapshot - it re-embeds
    # the manifest into html_path afterward (see test_take_snapshot_re_embeds_manifest_into_html_path
    # below), so html_path itself is no longer a reliable source of "what got archived" post-call.
    snapshots_dir = tmp_path / "snapshots"

    out_path = snapshot_dashboard.take_snapshot(html_path=html_path, snapshots_dir=snapshots_dir)

    assert out_path.exists()
    with gzip.open(out_path, "rb") as f:
        recovered = f.read()
    assert recovered == original_bytes, \
        "gunzipping a snapshot must reproduce the ORIGINAL (pre-snapshot) HTML byte-for-byte"


def test_take_snapshot_filename_has_no_windows_unsafe_characters(tmp_path):
    html_path = _write_fake_dashboard(tmp_path)
    snapshots_dir = tmp_path / "snapshots"

    out_path = snapshot_dashboard.take_snapshot(html_path=html_path, snapshots_dir=snapshots_dir)

    name = out_path.name
    # Windows forbids < > : " / \ | ? * in filenames - colons are the one
    # a plain ISO-8601 timestamp would otherwise introduce.
    windows_unsafe = set('<>:"/\\|?*')
    offenders = windows_unsafe.intersection(name)
    assert not offenders, f"snapshot filename {name!r} contains Windows-unsafe characters: {offenders}"
    assert re.match(r"^\d{8}T\d{6}Z_[0-9a-f]{7}\.html\.gz$", name) or re.match(r"^\d{8}T\d{6}Z_nogit\.html\.gz$", name), \
        f"unexpected snapshot filename shape: {name!r}"


def test_take_snapshot_uses_the_given_timestamp(tmp_path):
    html_path = _write_fake_dashboard(tmp_path)
    snapshots_dir = tmp_path / "snapshots"
    now = datetime(2026, 9, 16, 5, 45, 12, tzinfo=timezone.utc)

    out_path = snapshot_dashboard.take_snapshot(html_path=html_path, snapshots_dir=snapshots_dir, now=now)

    assert out_path.name.startswith("20260916T054512Z_")


def test_take_snapshot_appends_a_manifest_entry(tmp_path):
    html_path = _write_fake_dashboard(tmp_path, "<html>abc</html>\nconst SNAPSHOT_MANIFEST = [];\n")
    original_size = len(html_path.read_bytes())
    snapshots_dir = tmp_path / "snapshots"

    out_path = snapshot_dashboard.take_snapshot(html_path=html_path, snapshots_dir=snapshots_dir)

    manifest = json.loads((snapshots_dir / "manifest.json").read_text())
    assert len(manifest) == 1
    entry = manifest[0]
    assert entry["file"] == out_path.name
    assert entry["raw_size_bytes"] == original_size
    assert entry["compressed_size_bytes"] == out_path.stat().st_size
    assert entry["commit_sha"]  # non-empty - either a real short sha or "nogit"
    assert entry["taken_at"]


def test_take_snapshot_re_embeds_manifest_into_html_path(tmp_path):
    html_path = _write_fake_dashboard(tmp_path)
    snapshots_dir = tmp_path / "snapshots"
    now = datetime(2026, 9, 16, 6, 0, 0, tzinfo=timezone.utc)

    snapshot_dashboard.take_snapshot(html_path=html_path, snapshots_dir=snapshots_dir, now=now)

    updated_html = html_path.read_text()
    match = re.search(r"const SNAPSHOT_MANIFEST = (\[.*?\]);", updated_html)
    assert match, "expected an updated SNAPSHOT_MANIFEST const in the live dashboard file"
    embedded = json.loads(match.group(1))
    on_disk_manifest = json.loads((snapshots_dir / "manifest.json").read_text())
    assert embedded == on_disk_manifest, \
        "the dashboard's embedded SNAPSHOT_MANIFEST must match manifest.json exactly"
    assert len(embedded) == 1 and embedded[0]["taken_at"] == now.isoformat()


def test_take_snapshot_embedded_manifest_does_not_include_itself_in_its_own_archive(tmp_path):
    # A snapshot's own archived copy should reflect the manifest as it
    # stood BEFORE that snapshot was taken - it never needs to know about
    # itself (or, obviously, future snapshots).
    html_path = _write_fake_dashboard(tmp_path)
    snapshots_dir = tmp_path / "snapshots"
    first = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
    second = datetime(2026, 9, 8, 0, 0, 0, tzinfo=timezone.utc)

    first_out = snapshot_dashboard.take_snapshot(html_path=html_path, snapshots_dir=snapshots_dir, now=first)
    snapshot_dashboard.take_snapshot(html_path=html_path, snapshots_dir=snapshots_dir, now=second)

    with gzip.open(first_out, "rt") as f:
        first_archived_html = f.read()
    match = re.search(r"const SNAPSHOT_MANIFEST = (\[.*?\]);", first_archived_html)
    assert match, "the first snapshot's own archive should still carry its own (empty) manifest"
    assert json.loads(match.group(1)) == [], \
        "the first snapshot's archive must not know about the second snapshot taken after it"


def test_take_snapshot_raises_if_manifest_placeholder_missing(tmp_path):
    html_path = _write_fake_dashboard(tmp_path, "<html>no placeholder here</html>")
    snapshots_dir = tmp_path / "snapshots"
    try:
        snapshot_dashboard.take_snapshot(html_path=html_path, snapshots_dir=snapshots_dir)
        assert False, "expected a RuntimeError when the SNAPSHOT_MANIFEST placeholder is missing"
    except RuntimeError as e:
        assert "SNAPSHOT_MANIFEST" in str(e)


def test_take_snapshot_manifest_accumulates_across_multiple_snapshots(tmp_path):
    html_path = _write_fake_dashboard(tmp_path)
    snapshots_dir = tmp_path / "snapshots"

    first = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
    second = datetime(2026, 9, 8, 0, 0, 0, tzinfo=timezone.utc)
    snapshot_dashboard.take_snapshot(html_path=html_path, snapshots_dir=snapshots_dir, now=first)
    snapshot_dashboard.take_snapshot(html_path=html_path, snapshots_dir=snapshots_dir, now=second)

    manifest = json.loads((snapshots_dir / "manifest.json").read_text())
    assert len(manifest) == 2
    assert manifest[0]["file"] != manifest[1]["file"], \
        "two snapshots taken at different times must not collide on filename"


def test_take_snapshot_raises_if_dashboard_html_missing(tmp_path):
    missing_html = tmp_path / "does-not-exist.html"
    snapshots_dir = tmp_path / "snapshots"
    try:
        snapshot_dashboard.take_snapshot(html_path=missing_html, snapshots_dir=snapshots_dir)
        assert False, "expected FileNotFoundError for a missing dashboard HTML file"
    except FileNotFoundError:
        pass


def test_main_is_a_noop_without_the_env_flag(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SNAPSHOT_DASHBOARD", raising=False)
    monkeypatch.setattr(snapshot_dashboard, "sync_local_snapshots", lambda *a, **k: [])
    calls = []
    monkeypatch.setattr(snapshot_dashboard, "take_snapshot", lambda *a, **k: calls.append(1))

    snapshot_dashboard.main()

    assert calls == [], "main() must not take a snapshot when SNAPSHOT_DASHBOARD isn't set to 1"
    assert "skipping" in capsys.readouterr().out.lower()


def test_main_is_a_noop_when_flag_is_not_exactly_one(monkeypatch):
    for value in ("0", "true", "yes", ""):
        monkeypatch.setenv("SNAPSHOT_DASHBOARD", value)
        monkeypatch.setattr(snapshot_dashboard, "sync_local_snapshots", lambda *a, **k: [])
        calls = []
        monkeypatch.setattr(snapshot_dashboard, "take_snapshot", lambda *a, **k: calls.append(1))
        snapshot_dashboard.main()
        assert calls == [], f"SNAPSHOT_DASHBOARD={value!r} must not trigger a snapshot - only '1' should"


def test_main_takes_a_snapshot_when_flag_is_set(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SNAPSHOT_DASHBOARD", "1")
    monkeypatch.setattr(snapshot_dashboard, "sync_local_snapshots", lambda *a, **k: [])
    fake_out = tmp_path / "fake-snapshot.html.gz"
    calls = []
    monkeypatch.setattr(snapshot_dashboard, "take_snapshot", lambda *a, **k: calls.append(1) or fake_out)

    snapshot_dashboard.main()

    assert calls == [1]
    assert str(fake_out) in capsys.readouterr().out


def test_main_syncs_local_snapshots_even_without_the_env_flag(monkeypatch, capsys):
    # The whole point of the fix: a plain `./run_pipeline.sh` with no
    # SNAPSHOT_DASHBOARD flag set must still backfill local decompressed
    # copies of whatever snapshots already exist (e.g. right after a
    # fresh clone) - not just when actively taking a new one.
    monkeypatch.delenv("SNAPSHOT_DASHBOARD", raising=False)
    monkeypatch.setattr(snapshot_dashboard, "take_snapshot", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("take_snapshot should not be called without the flag set")))
    sync_calls = []
    monkeypatch.setattr(snapshot_dashboard, "sync_local_snapshots",
                         lambda *a, **k: sync_calls.append(1) or [Path("fake.html")])

    snapshot_dashboard.main()

    assert sync_calls == [1]
    assert "synced 1 local snapshot" in capsys.readouterr().out.lower()


def test_sync_local_snapshots_decompresses_gz_files_missing_a_local_copy(tmp_path):
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()
    gz_path = snapshots_dir / "20260916T000000Z_abc1234.html.gz"
    with gzip.open(gz_path, "wb") as f:
        f.write(b"<html>archived content</html>")

    written = snapshot_dashboard.sync_local_snapshots(snapshots_dir)

    expected_html = snapshots_dir / "20260916T000000Z_abc1234.html"
    assert written == [expected_html]
    assert expected_html.read_bytes() == b"<html>archived content</html>"


def test_sync_local_snapshots_skips_gz_files_that_already_have_a_local_copy(tmp_path):
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()
    gz_path = snapshots_dir / "20260916T000000Z_abc1234.html.gz"
    with gzip.open(gz_path, "wb") as f:
        f.write(b"<html>archived content</html>")
    html_path = snapshots_dir / "20260916T000000Z_abc1234.html"
    html_path.write_bytes(b"<html>a stale or hand-edited local copy</html>")

    written = snapshot_dashboard.sync_local_snapshots(snapshots_dir)

    assert written == []
    assert html_path.read_bytes() == b"<html>a stale or hand-edited local copy</html>", \
        "an existing local .html must never be overwritten by sync"


def test_sync_local_snapshots_returns_empty_list_when_snapshots_dir_missing(tmp_path):
    missing_dir = tmp_path / "does-not-exist"
    assert snapshot_dashboard.sync_local_snapshots(missing_dir) == []


def test_sync_local_snapshots_is_idempotent(tmp_path):
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()
    with gzip.open(snapshots_dir / "20260916T000000Z_abc1234.html.gz", "wb") as f:
        f.write(b"<html>archived content</html>")

    first = snapshot_dashboard.sync_local_snapshots(snapshots_dir)
    second = snapshot_dashboard.sync_local_snapshots(snapshots_dir)

    assert len(first) == 1
    assert second == [], "a second call must find nothing left to decompress"


def test_take_snapshot_also_writes_a_local_decompressed_copy(tmp_path):
    html_path = _write_fake_dashboard(tmp_path, "<html>local copy check</html>\nconst SNAPSHOT_MANIFEST = [];\n")
    snapshots_dir = tmp_path / "snapshots"

    out_path = snapshot_dashboard.take_snapshot(html_path=html_path, snapshots_dir=snapshots_dir)

    local_copy = out_path.with_suffix("")
    assert local_copy.exists(), \
        "take_snapshot() must leave a locally-openable .html copy, not just the .gz archive"
    with gzip.open(out_path, "rb") as f:
        assert local_copy.read_bytes() == f.read()


def test_prepare_deploy_site_copies_dashboard_as_index(tmp_path):
    html_path = _write_fake_dashboard(tmp_path, "<html>the live dashboard</html>\nconst SNAPSHOT_MANIFEST = [];\n")
    site_dir = tmp_path / "_site"

    snapshot_dashboard.prepare_deploy_site(site_dir, html_path=html_path, snapshots_dir=tmp_path / "snapshots")

    assert (site_dir / "index.html").read_text() == html_path.read_text()


def test_prepare_deploy_site_decompresses_every_committed_snapshot(tmp_path):
    html_path = _write_fake_dashboard(tmp_path)
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()
    with gzip.open(snapshots_dir / "20260916T000000Z_abc1234.html.gz", "wb") as f:
        f.write(b"<html>archived snapshot one</html>")
    with gzip.open(snapshots_dir / "20260916T010000Z_def5678.html.gz", "wb") as f:
        f.write(b"<html>archived snapshot two</html>")
    (snapshots_dir / "manifest.json").write_text('[{"file": "irrelevant"}]')
    site_dir = tmp_path / "_site"

    snapshot_dashboard.prepare_deploy_site(site_dir, html_path=html_path, snapshots_dir=snapshots_dir)

    site_snapshots_dir = site_dir / "snapshots"
    assert (site_snapshots_dir / "20260916T000000Z_abc1234.html").read_bytes() == b"<html>archived snapshot one</html>"
    assert (site_snapshots_dir / "20260916T010000Z_def5678.html").read_bytes() == b"<html>archived snapshot two</html>"
    assert (site_snapshots_dir / "manifest.json").read_text() == '[{"file": "irrelevant"}]'


def test_prepare_deploy_site_embeds_the_real_manifest_into_index_html(tmp_path):
    # The actual bug (found 2026-09-17, Keith: "I'm not seeing any
    # snapshots on the live published dashboard"): prepare_deploy_site()
    # used to byte-copy html_path straight through, so the deployed
    # site's SNAPSHOT_MANIFEST const stayed at the template's empty `[]`
    # placeholder forever - embed_dashboard_data.py deliberately never
    # touches that const (it owns the other 3), and _embed_snapshot_manifest
    # was only ever called from take_snapshot(), which never runs in CI.
    # Every snapshot .gz file landed correctly in _site/snapshots/, but
    # the picker panel on the live page had nothing to list.
    html_path = _write_fake_dashboard(tmp_path, "<html>the live dashboard</html>\nconst SNAPSHOT_MANIFEST = [];\n")
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()
    with gzip.open(snapshots_dir / "20260916T000000Z_abc1234.html.gz", "wb") as f:
        f.write(b"<html>archived snapshot one</html>")
    real_manifest = [{
        "file": "20260916T000000Z_abc1234.html.gz",
        "taken_at": "2026-09-16T00:00:00+00:00",
        "commit_sha": "abc1234",
        "raw_size_bytes": 100,
        "compressed_size_bytes": 40,
    }]
    (snapshots_dir / "manifest.json").write_text(json.dumps(real_manifest))
    site_dir = tmp_path / "_site"

    snapshot_dashboard.prepare_deploy_site(site_dir, html_path=html_path, snapshots_dir=snapshots_dir)

    index_html = (site_dir / "index.html").read_text()
    match = re.search(r"const SNAPSHOT_MANIFEST = (\[.*?\]);", index_html)
    assert match, "expected a SNAPSHOT_MANIFEST const in the deployed index.html"
    assert json.loads(match.group(1)) == real_manifest, \
        "the deployed index.html must embed the real committed manifest.json, not the template's empty placeholder"
    # html_path itself (the committed/gitignored dashboard file, never
    # the deploy artifact) must stay untouched - only the site copy gets it.
    assert "const SNAPSHOT_MANIFEST = [];" in html_path.read_text()


def test_prepare_deploy_site_is_a_clean_noop_for_snapshots_when_none_exist(tmp_path):
    html_path = _write_fake_dashboard(tmp_path)
    site_dir = tmp_path / "_site"

    snapshot_dashboard.prepare_deploy_site(site_dir, html_path=html_path, snapshots_dir=tmp_path / "no-such-dir")

    assert (site_dir / "index.html").exists()
    assert not (site_dir / "snapshots").exists()


def test_prepare_deploy_site_copies_fonts_and_vendor_into_the_site(tmp_path):
    # Real bug found live 2026-09-19 while building the Demo tab (plans/
    # tooling.md #1 Phase 6): neither dashboard/fonts/ nor the new
    # dashboard/vendor/ was ever copied into _site/, so the deployed site
    # silently fell back to system fonts (a missing woff2 degrades
    # quietly, no error) and would have 404'd on the Demo tab's own
    # vendored asciinema-player.min.js/css. Confirmed live before the fix:
    # `uv run mothman dashboard snapshot --prepare-site <dir>` produced no
    # fonts/ or vendor/ subdirectory at all.
    html_path = _write_fake_dashboard(tmp_path)
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    (fonts_dir / "public-sans-regular.woff2").write_bytes(b"fake-woff2-bytes")
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "asciinema-player.min.js").write_text("/* fake player */")
    (vendor_dir / "asciinema-player.css").write_text("/* fake css */")
    site_dir = tmp_path / "_site"

    snapshot_dashboard.prepare_deploy_site(
        site_dir, html_path=html_path, snapshots_dir=tmp_path / "no-such-dir",
        fonts_dir=fonts_dir, vendor_dir=vendor_dir)

    assert (site_dir / "fonts" / "public-sans-regular.woff2").read_bytes() == b"fake-woff2-bytes"
    assert (site_dir / "vendor" / "asciinema-player.min.js").read_text() == "/* fake player */"
    assert (site_dir / "vendor" / "asciinema-player.css").read_text() == "/* fake css */"


def test_prepare_deploy_site_is_a_clean_noop_when_fonts_and_vendor_dont_exist(tmp_path):
    html_path = _write_fake_dashboard(tmp_path)
    site_dir = tmp_path / "_site"

    snapshot_dashboard.prepare_deploy_site(
        site_dir, html_path=html_path, snapshots_dir=tmp_path / "no-such-dir",
        fonts_dir=tmp_path / "no-fonts", vendor_dir=tmp_path / "no-vendor")

    assert not (site_dir / "fonts").exists()
    assert not (site_dir / "vendor").exists()


def test_prepare_deploy_site_and_sync_local_snapshots_use_the_same_decompression(tmp_path):
    # The whole point of unifying these (Keith's own ask): a snapshot
    # decompressed locally and one decompressed for deploy must be
    # byte-for-byte identical, because they're produced by the exact
    # same code path, not two implementations that happen to agree today.
    html_path = _write_fake_dashboard(tmp_path)
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()
    with gzip.open(snapshots_dir / "20260916T000000Z_abc1234.html.gz", "wb") as f:
        f.write(b"<html>identical decompression check</html>")

    snapshot_dashboard.sync_local_snapshots(snapshots_dir)
    site_dir = tmp_path / "_site"
    snapshot_dashboard.prepare_deploy_site(site_dir, html_path=html_path, snapshots_dir=snapshots_dir)

    local_html = (snapshots_dir / "20260916T000000Z_abc1234.html").read_bytes()
    deployed_html = (site_dir / "snapshots" / "20260916T000000Z_abc1234.html").read_bytes()
    assert local_html == deployed_html == b"<html>identical decompression check</html>"


def test_main_prepare_site_flag_calls_prepare_deploy_site(monkeypatch, tmp_path, capsys):
    # This is exactly how .github/workflows/deploy-pages.yml invokes this
    # module: `python3 -m dashboard.snapshot_dashboard --prepare-site _site`.
    site_dir = tmp_path / "_site"
    monkeypatch.setattr(sys, "argv", ["snapshot_dashboard.py", "--prepare-site", str(site_dir)])
    calls = []
    monkeypatch.setattr(snapshot_dashboard, "prepare_deploy_site",
                         lambda *a, **k: calls.append((a, k)))

    snapshot_dashboard.main()

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert kwargs.get("site_dir") == site_dir or (args and args[0] == site_dir)
    assert str(site_dir) in capsys.readouterr().out


def test_main_prepare_site_flag_requires_a_directory_argument(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["snapshot_dashboard.py", "--prepare-site"])
    monkeypatch.setattr(snapshot_dashboard, "prepare_deploy_site", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("prepare_deploy_site should not be called without a directory argument")))

    try:
        snapshot_dashboard.main()
        assert False, "expected SystemExit for a missing --prepare-site argument"
    except SystemExit as e:
        assert e.code == 2


# --- REQ-DASH-292: a snapshot inlines its data files; the site splits them back

def _split_built_page(tmp_path, *, budget=None, size=4000):
    """A page in the built page's shape with its data files beside it -
    two collections and the Requirements and Plans file."""
    from dashboard import data_files

    files = []
    for cid in ("civil-registration", "child-protection"):
        files += data_files.encode(data_files.collection_key(cid),
                                   {"datasets": [{"id": cid, "pad": "y" * size}]},
                                   kind="collection", collection=cid, budget=budget)
    files += data_files.encode(data_files.REQUIREMENTS_PLANS_KEY,
                               {"requirements": [{"id": "REQ-X"}], "plans": {"items": []}},
                               kind=data_files.REQUIREMENTS_PLANS_KEY, budget=budget)
    html = ("<html>\n<!-- mothman:data-files -->\n<script>\nconst DATA_FILES = null;\n"
            "const COLLECTION_DATA = null;\nconst SNAPSHOT_MANIFEST = [];\n</script>\n</html>\n")
    page = tmp_path / "qa-reporting-dashboard.html"
    page.write_text(data_files.embed_into_page(html, data_files.manifest(files)))
    data_files.write(files, tmp_path / "data")
    return page, files


def _archived(out_path) -> str:
    with gzip.open(out_path, "rb") as f:
        return f.read().decode("utf-8")


def test_a_snapshot_inlines_every_data_file_each_block_marked(tmp_path):
    """Criterion 1: the Requirements and Plans file included, and no
    sibling file referenced."""
    page, files = _split_built_page(tmp_path)
    out = snapshot_dashboard.take_snapshot(html_path=page, snapshots_dir=tmp_path / "snapshots")
    html = _archived(out)
    assert 'src="data/' not in html
    for f in files:
        marker = f'data-mothman-key="{f.entry["key"]}" data-mothman-file="{f.entry["name"]}">'
        assert html.count(marker) == 1, f.entry["name"]
        assert f.content.decode("ascii") + "</script>" in html
    assert ('<script type="text/plain" data-mothman-key="requirements-plans"' in html), \
        "the on-demand file is inlined inert, to be run when asked for"


def test_a_snapshot_refuses_a_missing_or_altered_file_and_writes_nothing(tmp_path):
    """Criterion 3."""
    import pytest
    from dashboard import data_files

    page, files = _split_built_page(tmp_path)
    (tmp_path / "data" / files[0].entry["name"]).unlink()
    altered = tmp_path / "data" / files[1].entry["name"]
    altered.write_bytes(altered.read_bytes().replace(b"yyy", b"zzz", 1))
    snapshots = tmp_path / "snapshots"
    with pytest.raises(data_files.DataFileError) as refused:
        snapshot_dashboard.take_snapshot(html_path=page, snapshots_dir=snapshots)
    said = str(refused.value)
    assert files[0].entry["name"] in said and files[1].entry["name"] in said
    assert not snapshots.exists()


def _site_with_a_snapshot(tmp_path, *, budget=None, size=4000):
    page, files = _split_built_page(tmp_path, size=size)
    snapshots = tmp_path / "snapshots"
    out = snapshot_dashboard.take_snapshot(html_path=page, snapshots_dir=snapshots)
    site = tmp_path / "_site"
    snapshot_dashboard.prepare_deploy_site(site, html_path=page, snapshots_dir=snapshots,
                                           budget=budget)
    return page, files, out, site


def test_the_site_carries_the_live_pages_files(tmp_path):
    page, files, _out, site = _site_with_a_snapshot(tmp_path)
    for f in files:
        assert (site / "data" / f.entry["name"]).read_bytes() == f.content


def test_the_site_carries_each_snapshot_split_back_byte_for_byte(tmp_path):
    """Criteria 4 and 5, and the fingerprint risk: a split one byte off
    would fail the page's own list and make every publish count as
    changed (REQ-PIPE-255 criterion 24)."""
    import hashlib
    from dashboard import data_files

    page, files, out, site = _site_with_a_snapshot(tmp_path)
    stem = out.name[: -len(".html.gz")]
    placed = site / "snapshots" / f"{stem}.html"
    html = placed.read_text()
    assert "data-mothman-file" in html and "</script>" in html
    assert not re.search(r'data-mothman-file="[^"]+">\(window', html), "a block was left inline"
    listed = data_files.page_manifest(html)["files"]
    for e in listed:
        content = (site / "snapshots" / f"{stem}.data" / e["name"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == e["sha256"]
        assert len(content) <= data_files.BUDGET_BYTES
    assert data_files.read_page(html, placed.parent).problems == []
    assert {e["name"]: e["sha256"] for e in listed} == \
        {f.entry["name"]: f.entry["sha256"] for f in files}


def test_a_snapshot_fingerprints_the_same_as_the_page_it_archived(tmp_path):
    """REQ-PIPE-255 criteria 22 and 24, as REQ-DASH-292 amends them: the
    newest snapshot, its inlined files read back out, fingerprints exactly
    as the build it archived - and a one-byte change in a data file does
    not."""
    page, files = _split_built_page(tmp_path)
    before = snapshot_dashboard.page_fingerprint(page)
    out = snapshot_dashboard.take_snapshot(html_path=page, snapshots_dir=tmp_path / "snapshots")
    assert snapshot_dashboard.snapshot_fingerprint(out) == before
    # take_snapshot re-embedded SNAPSHOT_MANIFEST into the live page, which
    # the fingerprint deliberately ignores.
    assert snapshot_dashboard.page_fingerprint(page) == before
    path = tmp_path / "data" / files[0].entry["name"]
    path.write_bytes(path.read_bytes().replace(b"yyy", b"yyz", 1))
    from dashboard import data_files
    import pytest

    with pytest.raises(data_files.DataFileError):
        snapshot_dashboard.page_fingerprint(page)


def test_a_block_over_the_budget_is_split_into_parts_within_it(tmp_path):
    """Criterion 6."""
    from dashboard import data_files

    budget = 3000
    page, files, out, site = _site_with_a_snapshot(tmp_path, budget=budget, size=9000)
    stem = out.name[: -len(".html.gz")]
    placed = site / "snapshots" / f"{stem}.html"
    listed = data_files.page_manifest(placed.read_text())["files"]
    assert len(listed) > len(files)
    for e in listed:
        assert (site / "snapshots" / f"{stem}.data" / e["name"]).stat().st_size <= budget
    got = data_files.read_page(placed.read_text(), placed.parent)
    assert got.problems == []
    whole = data_files.read_page(_archived(out), tmp_path / "nowhere")
    assert got.collections == whole.collections


def test_a_snapshot_from_before_the_split_is_placed_as_it_is(tmp_path):
    """Criterion 7."""
    page, _files = _split_built_page(tmp_path)
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    old = b"<html>\nconst COLLECTION_DATA = {\"x\":{\"datasets\":[]}};\n</html>\n"
    with gzip.open(snapshots / "20261022T000000Z_abc1234.html.gz", "wb") as f:
        f.write(old)
    site = tmp_path / "_site"
    snapshot_dashboard.prepare_deploy_site(site, html_path=page, snapshots_dir=snapshots)
    assert (site / "snapshots" / "20261022T000000Z_abc1234.html").read_bytes() == old
    assert not (site / "snapshots" / "20261022T000000Z_abc1234.data").exists()


def test_a_local_snapshot_copy_is_still_decompressed_whole(tmp_path):
    """Criterion 8."""
    page, _files = _split_built_page(tmp_path)
    snapshots = tmp_path / "snapshots"
    out = snapshot_dashboard.take_snapshot(html_path=page, snapshots_dir=snapshots)
    local = out.with_suffix("")
    assert local.read_text() == _archived(out)
    assert not (snapshots / (local.stem + ".data")).exists()


def test_a_reused_site_directory_publishes_none_of_its_stale_files(tmp_path):
    """post-build-review #268 D1: `mothman dashboard publish` reuses `_site/`,
    and the site was never cleared, so a data file or snapshot directory
    from an earlier build stayed in it and was published again on every
    publish after. Only what this build lists is on the site afterwards."""
    page, files, out, site = _site_with_a_snapshot(tmp_path)
    stale = [site / "data" / "collection-gone.0123456789ab.js",
             site / "snapshots" / "20200101T000000Z_old.data" / "x.js",
             site / "snapshots" / "20200101T000000Z_old.html"]
    for path in stale:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stale")
    snapshot_dashboard.prepare_deploy_site(site, html_path=page, snapshots_dir=tmp_path / "snapshots")
    assert [p for p in stale if p.exists()] == []
    assert sorted(p.name for p in (site / "data").iterdir()) == sorted(f.entry["name"] for f in files)
    assert (site / "snapshots" / out.with_suffix("").name).is_file()


def test_clearing_the_site_touches_nothing_it_does_not_write(tmp_path):
    """The other half of D1: `mothman dashboard prepare-site` takes any
    directory, so only what the site is made of is cleared - never the
    directory itself or a file beside it."""
    page, _files = _split_built_page(tmp_path)
    site = tmp_path / "_site"
    site.mkdir()
    (site / "keep.txt").write_text("not ours")
    snapshot_dashboard.prepare_deploy_site(site, html_path=page, snapshots_dir=tmp_path / "snapshots")
    assert (site / "keep.txt").read_text() == "not ours"
