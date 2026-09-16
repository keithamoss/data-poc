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
from datetime import datetime, timezone

from dashboard import snapshot_dashboard


def _write_fake_dashboard(tmp_path, content: str = "<html>fake dashboard</html>"):
    html_path = tmp_path / "qa-reporting-dashboard.html"
    html_path.write_text(content)
    return html_path


def test_take_snapshot_round_trips_to_identical_bytes(tmp_path):
    html_path = _write_fake_dashboard(tmp_path, "<html>hello world</html>")
    snapshots_dir = tmp_path / "snapshots"

    out_path = snapshot_dashboard.take_snapshot(html_path=html_path, snapshots_dir=snapshots_dir)

    assert out_path.exists()
    with gzip.open(out_path, "rb") as f:
        recovered = f.read()
    assert recovered == html_path.read_bytes(), \
        "gunzipping a snapshot must reproduce the original HTML byte-for-byte"


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
    html_path = _write_fake_dashboard(tmp_path, "<html>abc</html>")
    snapshots_dir = tmp_path / "snapshots"

    out_path = snapshot_dashboard.take_snapshot(html_path=html_path, snapshots_dir=snapshots_dir)

    manifest = json.loads((snapshots_dir / "manifest.json").read_text())
    assert len(manifest) == 1
    entry = manifest[0]
    assert entry["file"] == out_path.name
    assert entry["raw_size_bytes"] == len(html_path.read_bytes())
    assert entry["compressed_size_bytes"] == out_path.stat().st_size
    assert entry["commit_sha"]  # non-empty - either a real short sha or "nogit"
    assert entry["taken_at"]


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
    calls = []
    monkeypatch.setattr(snapshot_dashboard, "take_snapshot", lambda *a, **k: calls.append(1))

    snapshot_dashboard.main()

    assert calls == [], "main() must not take a snapshot when SNAPSHOT_DASHBOARD isn't set to 1"
    assert "skipping" in capsys.readouterr().out.lower()


def test_main_is_a_noop_when_flag_is_not_exactly_one(monkeypatch):
    for value in ("0", "true", "yes", ""):
        monkeypatch.setenv("SNAPSHOT_DASHBOARD", value)
        calls = []
        monkeypatch.setattr(snapshot_dashboard, "take_snapshot", lambda *a, **k: calls.append(1))
        snapshot_dashboard.main()
        assert calls == [], f"SNAPSHOT_DASHBOARD={value!r} must not trigger a snapshot - only '1' should"


def test_main_takes_a_snapshot_when_flag_is_set(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SNAPSHOT_DASHBOARD", "1")
    fake_out = tmp_path / "fake-snapshot.html.gz"
    calls = []
    monkeypatch.setattr(snapshot_dashboard, "take_snapshot", lambda *a, **k: calls.append(1) or fake_out)

    snapshot_dashboard.main()

    assert calls == [1]
    assert str(fake_out) in capsys.readouterr().out
