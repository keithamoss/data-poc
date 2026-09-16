"""Tests for dashboard/snapshot_dashboard.py - the "time travel" archiving
mechanism (plans/wider.md, scoped 2026-09-16). Real requirements this
covers, per that scoping: a snapshot must be byte-for-byte recoverable
(gzip round-trip integrity - the whole point is a self-contained artifact
someone can trust years from now), its filename must be safe on Windows
(plans/wider.md #25's own flag that this needs to run on Windows EC2s
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


def test_prepare_deploy_site_is_a_clean_noop_for_snapshots_when_none_exist(tmp_path):
    html_path = _write_fake_dashboard(tmp_path)
    site_dir = tmp_path / "_site"

    snapshot_dashboard.prepare_deploy_site(site_dir, html_path=html_path, snapshots_dir=tmp_path / "no-such-dir")

    assert (site_dir / "index.html").exists()
    assert not (site_dir / "snapshots").exists()


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
