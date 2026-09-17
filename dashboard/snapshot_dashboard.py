"""
Archives the fully-embedded dashboard/qa-reporting-dashboard.html as a
gzipped, timestamped, self-contained snapshot in dashboard/snapshots/ -
the "time travel" build (plans/wider.md, scoped 2026-09-16 across several
rounds of AskUserQuestion with Keith before any code was written).

Scoping recap, since the design choices here aren't obvious from the code
alone:

- What gets frozen: the ENTIRE rendered dashboard HTML (shell + CSS + JS
  + embedded REAL_BIRTH_REG_DATA/REAL_CP_DATA), not just a data payload.
  Deliberately NOT a "data snapshot + shared shell" hybrid, and NOT a
  "raw inputs, rebuild on demand" scheme - both were considered and
  rejected. A snapshot must be openable with nothing but a browser,
  forever, for an audit/incident-debugging use case - that ruled out any
  approach depending on this repo's own tooling (dbt-core, Soda Core,
  this exact JS rendering code) still working correctly years from now.
  The check-defining thresholds (warn/fail) that determine each check's
  pass/fail status are already embedded in the data payload itself
  (`check.warn`/`check.fail` per check), so this single HTML file
  genuinely captures "data AND the check definitions in effect then" -
  the full check-definition YAML isn't embedded (nothing in the
  dashboard renders that today either - see plans/qa-pipeline.md #43),
  but the commit SHA in each snapshot's filename is enough to look it up
  in git if that's ever needed.
- Storage: gzip only, no thinning/retention policy - "keep everything for
  now," Keith's own words; revisit only if storage actually becomes a
  problem for whichever future storage backend (S3/SharePoint/
  Cloudflare/etc.) eventually replaces "just commit it to the repo."
- No separate JSON payload alongside each snapshot: cross-snapshot
  querying/comparison ("show me every snapshot where this check was
  red") was explicitly ruled OUT of scope for this mechanism - that's
  the LIVE dashboard's own trend-chart job, operating on its current
  rolling window, a genuinely different concern from an archived,
  opened-one-at-a-time forensic record.
- Trigger: gated on the SNAPSHOT_DASHBOARD=1 env var, off by default -
  not tied to run_pipeline.sh unconditionally, because this PoC has no
  real distinction yet between "a genuine scheduled data-refresh run"
  and "a developer iterating on code" (every regeneration uses the same
  script) - Keith's own call was a manual toggle rather than guessing at
  an automatic signal that doesn't actually exist here yet.
- Picker/browse UI (added 2026-09-16, a separate later round once real
  snapshots existed to browse): built INTO the live dashboard itself
  (`#snapshots-panel` in qa-reporting-dashboard.html), not a standalone
  page - Keith's own call. It reads a `SNAPSHOT_MANIFEST` const embedded
  directly into the dashboard HTML (this module re-embeds it every time
  a snapshot is taken - see `_embed_snapshot_manifest` below), not
  fetched at runtime: `fetch('manifest.json')` would silently fail under
  file:// (CORS), breaking the picker for exactly the offline/local-open
  workflow this project's own dev loop already depends on. Each entry
  links to a plain `snapshots/<name>.html` - resolves on the published
  GitHub Pages site (`.github/workflows/deploy-pages.yml` decompresses
  every `.html.gz` into `_site/snapshots/` at deploy time specifically
  for this - gzip stays the only format actually committed to git;
  nothing decompressed is ever checked in).
- Local/offline viewing (added 2026-09-16, later the same day - a real
  gap Keith spotted: a developer running the pipeline locally, then
  opening the dashboard straight from `dashboard/qa-reporting-
  dashboard.html` via `file://`, would 404 on every "Open" link, since
  `dashboard/snapshots/` on disk only ever held the gzipped originals -
  nothing decompressed the picker's links until GitHub Pages did, at
  deploy time, for the published site only). `sync_local_snapshots()`
  below closes this: it decompresses any `*.html.gz` in `dashboard/
  snapshots/` that doesn't already have a local `.html` sibling, writing
  to the exact same relative path (`dashboard/snapshots/<name>.html`)
  the picker's existing links already point at - so the dashboard's JS/
  markup needed zero changes, locally or on Pages, the same relative
  link now resolves either way. Called unconditionally from `main()`
  (so a plain `./run_pipeline.sh`, with no `SNAPSHOT_DASHBOARD` flag,
  still backfills local copies for whatever snapshots already exist in
  the repo - e.g. right after a fresh clone) and again at the end of
  `take_snapshot()` (so a snapshot just taken is immediately locally
  openable too, even if `take_snapshot()` is called directly rather than
  through `main()`). The decompressed `.html` copies are gitignored
  (`dashboard/snapshots/*.html`) and regenerated from the committed
  `.gz` originals, never committed themselves - one source of truth per
  snapshot, same as `data/`/`reports/` elsewhere in this repo.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DASHBOARD_HTML = Path(__file__).parent / "qa-reporting-dashboard.html"
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


def _git_short_sha(cwd: Path) -> str:
    """The dashboard-code version a snapshot's rendering logic came from -
    the audit trail's link back to exactly which commit's check-definition
    files (contract/, Soda YAML, dbt schema.yml) and rendering JS produced
    this snapshot, without needing to embed that content directly (see
    module docstring). Falls back to a fixed placeholder rather than
    raising - a missing git binary/repo shouldn't be able to break the
    snapshot itself, just its provenance tag."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            capture_output=True, text=True, check=True, cwd=cwd,
        )
        return result.stdout.strip() or "nogit"
    except Exception:
        return "nogit"


def take_snapshot(html_path: Path = DASHBOARD_HTML, snapshots_dir: Path = SNAPSHOTS_DIR,
                   now: Optional[datetime] = None) -> Path:
    """Gzips a copy of `html_path` (the fully re-embedded dashboard, real
    data already baked in by embed_dashboard_data.py) into `snapshots_dir`,
    named `<UTC timestamp>_<git short sha>.html.gz`. The timestamp format
    (`%Y%m%dT%H%M%SZ` - no colons) is deliberately Windows-filesystem-safe,
    given plans/wider.md #25's own flag that this needs to run on Windows
    EC2s eventually - a colon-bearing ISO-8601 timestamp would work today
    (Linux) but silently become a real problem there.

    `html_path`/`snapshots_dir`/`now` are injectable so this is testable
    without touching the real dashboard file or writing into the real
    repo's snapshots directory - see tests/test_snapshot_dashboard.py.
    Returns the path written; raises FileNotFoundError if `html_path`
    doesn't exist yet (embed_dashboard_data.py hasn't run).

    Side effect on `html_path` itself, not just `snapshots_dir`: after
    archiving, this also re-embeds the updated snapshot manifest back
    into `html_path` (its `SNAPSHOT_MANIFEST` const) so the live
    dashboard's own "past snapshots" picker panel immediately knows
    about the one just taken - see `_embed_snapshot_manifest`. Requires
    `html_path` to already contain a `const SNAPSHOT_MANIFEST = ...;`
    placeholder line; raises if it doesn't."""
    if not html_path.exists():
        raise FileNotFoundError(
            f"{html_path} doesn't exist - run dashboard/embed_dashboard_data.py first "
            "so there's a fully up-to-date dashboard to snapshot."
        )
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    sha = _git_short_sha(cwd=html_path.parent)
    name = f"{stamp}_{sha}.html.gz"

    snapshots_dir.mkdir(parents=True, exist_ok=True)
    out_path = snapshots_dir / name
    html_bytes = html_path.read_bytes()
    with gzip.open(out_path, "wb") as f:
        f.write(html_bytes)

    manifest = _append_manifest_entry(snapshots_dir, {
        "file": name,
        "taken_at": now.isoformat(),
        "commit_sha": sha,
        "raw_size_bytes": len(html_bytes),
        "compressed_size_bytes": out_path.stat().st_size,
    })
    # Re-embed AFTER archiving, not before: html_bytes above is exactly
    # what existed before this snapshot (including whatever
    # SNAPSHOT_MANIFEST it already had) - this snapshot's own archive
    # correctly reflects only the snapshots that existed BEFORE it, and
    # the live file on disk gets the freshly updated list, including
    # itself, so the picker can link to it going forward.
    _embed_snapshot_manifest(html_path, manifest)
    sync_local_snapshots(snapshots_dir)
    return out_path


def _decompress_snapshot(gz_path: Path, dest_path: Path) -> None:
    """The one place a snapshot `.gz` becomes a plain `.html` file - used
    identically by `sync_local_snapshots()` (local dev) and
    `prepare_deploy_site()` (the GitHub Pages deploy workflow) below, so a
    local sync is a genuine dry run of exactly what deploy will do, not a
    second, parallel reimplementation (e.g. a shell `gunzip` loop) that
    could quietly drift from this one. Scoped 2026-09-16, Keith's own ask
    once the local-sync gap above was fixed: "I would want it to be using
    the same code paths as the deployment pipeline... then we can treat
    the sync as a way to locally test how the CI/CD pipeline will unzip.\""""
    with gzip.open(gz_path, "rb") as f:
        dest_path.write_bytes(f.read())


def sync_local_snapshots(snapshots_dir: Path = SNAPSHOTS_DIR) -> list[Path]:
    """Decompresses every `*.html.gz` in `snapshots_dir` that doesn't
    already have a local `.html` sibling, so the live dashboard's "past
    snapshots" picker (each row links to `snapshots/<name>.html`) resolves
    locally too, not just on the published GitHub Pages site (which
    already does this at deploy time, via the same `_decompress_snapshot`
    this calls - see `prepare_deploy_site` and `.github/workflows/deploy-
    pages.yml`). See the module docstring's "Local/offline viewing"
    section for the fuller rationale.

    Idempotent and safe to call repeatedly/unconditionally: a `.gz` that
    already has a decompressed sibling is left untouched. Returns the
    `.html` paths newly written (empty list if nothing needed it, or if
    `snapshots_dir` doesn't exist at all - e.g. no snapshot has ever been
    taken)."""
    if not snapshots_dir.exists():
        return []
    written = []
    for gz_path in sorted(snapshots_dir.glob("*.html.gz")):
        html_path = gz_path.with_suffix("")  # strips only the trailing .gz
        if html_path.exists():
            continue
        _decompress_snapshot(gz_path, html_path)
        written.append(html_path)
    return written


def prepare_deploy_site(site_dir: Path, html_path: Path = DASHBOARD_HTML,
                         snapshots_dir: Path = SNAPSHOTS_DIR) -> None:
    """Builds the `_site/` tree `.github/workflows/deploy-pages.yml`
    uploads to GitHub Pages: `index.html` (the live dashboard) plus every
    committed snapshot decompressed into `_site/snapshots/`, alongside a
    copy of `manifest.json` for direct inspection. Deliberately the SAME
    `_decompress_snapshot()` call `sync_local_snapshots()` uses above -
    this function replaced an earlier version of this step written as a
    standalone `gunzip` loop directly in the workflow YAML, which worked
    but was a second implementation of the exact same logic that could
    have quietly drifted from the local path. Now there is exactly one
    "how does a snapshot get decompressed" implementation, exercised by
    both `uv run python3 -m dashboard.snapshot_dashboard` locally and
    this deploy step in CI - running the local command really is a dry
    run of what deploy will do, not just something that resembles it.

    Doesn't need this project's full `uv`-managed dependency set (dbt-
    core, Soda Core, datacontract-cli, Evidently, ...) - everything used
    here is Python stdlib. CI still runs this through `uv run
    --no-project` rather than a bare `python3`, per this repo's own
    convention of never trusting whatever interpreter happens to be
    preinstalled on a machine (CLAUDE.md) - `--no-project` gets uv's
    pinned Python without triggering a full dependency sync for what's
    otherwise just a file-copy step. (An earlier version of this
    docstring said CI should use a bare `python3` here since nothing but
    stdlib is needed - wrong: "doesn't need extra packages" and "so skip
    uv" aren't the same thing. Corrected 2026-09-16, Keith's own catch.)

    Also embeds the real, committed manifest.json into the copy of
    `html_path` written to `site_dir/index.html` - a real bug found
    2026-09-17 (Keith: "I'm not seeing any snapshots on the live
    published dashboard") had this NOT happening: embed_dashboard_data.py
    deliberately leaves SNAPSHOT_MANIFEST alone (it owns the other 3
    consts only - see its own docstring), and this function used to just
    byte-copy html_path straight through, so the deployed site's picker
    always saw the template's empty `[]` placeholder, never the real
    manifest - even though every snapshot file itself was correctly
    landing in _site/snapshots/. `html_path` on disk is untouched by
    this - only the site copy gets the embed, same one-way relationship
    as embed_dashboard_data.py's own gitignored build output."""
    site_dir.mkdir(parents=True, exist_ok=True)
    manifest = _read_manifest(snapshots_dir)
    html = _embed_snapshot_manifest_into_html(
        html_path.read_text(), manifest, f"{html_path} (deploy site copy)"
    )
    (site_dir / "index.html").write_text(html)

    if not snapshots_dir.exists():
        return
    site_snapshots_dir = site_dir / "snapshots"
    site_snapshots_dir.mkdir(parents=True, exist_ok=True)
    for gz_path in sorted(snapshots_dir.glob("*.html.gz")):
        dest_name = gz_path.with_suffix("").name  # strips only the trailing .gz
        _decompress_snapshot(gz_path, site_snapshots_dir / dest_name)

    manifest_path = snapshots_dir / "manifest.json"
    if manifest_path.exists():
        (site_snapshots_dir / "manifest.json").write_bytes(manifest_path.read_bytes())


def _append_manifest_entry(snapshots_dir: Path, entry: dict) -> list:
    """A plain, minimal record of what's been snapshotted - bookkeeping
    for this script itself (and something tests/test_snapshot_dashboard.py
    can assert against), NOT the cross-snapshot query/comparison feature
    the module docstring explains was scoped OUT of this build. The
    picker UI reads this list too (via the embedded copy - see
    `_embed_snapshot_manifest`), rather than re-deriving it by listing
    the directory. Returns the full, updated manifest."""
    manifest_path = snapshots_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    manifest.append(entry)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def _embed_snapshot_manifest_into_html(html: str, manifest: list, source_desc: str) -> str:
    """Returns `html` with its `const SNAPSHOT_MANIFEST = [...];` line
    replaced - same mechanism as dashboard/embed_dashboard_data.py's
    REAL_BIRTH_REG_DATA/REAL_CP_DATA replacement (a single-line const,
    regex-replaced with a lambda substitution so any special characters
    already in the JSON are never reinterpreted as regex backreferences).
    `source_desc` is just for the error message, identifying which HTML
    (a path, or "the deploy site's index.html") failed to match.

    Shared by `_embed_snapshot_manifest` (mutates a dev's local
    qa-reporting-dashboard.html after `take_snapshot()`) and
    `prepare_deploy_site` (embeds into the CI-built _site/index.html) -
    see prepare_deploy_site's own docstring for why the latter needs
    this at all: embed_dashboard_data.py deliberately never touches
    SNAPSHOT_MANIFEST (it owns the other 3 consts only), so without this
    call here too, the deployed site's picker would always see the
    template's empty placeholder, never the real committed manifest -
    a real bug found 2026-09-17 (Keith: "I'm not seeing any snapshots on
    the live published dashboard") despite every snapshot file itself
    being correctly decompressed into _site/snapshots/."""
    manifest_json = json.dumps(manifest, separators=(",", ":"))
    new_line = f"const SNAPSHOT_MANIFEST = {manifest_json};\n"

    pattern = re.compile(r"const SNAPSHOT_MANIFEST = .*?;\n")
    html, n = pattern.subn(lambda _m: new_line, html, count=1)
    if n != 1:
        raise RuntimeError(
            f"Could not find exactly one 'const SNAPSHOT_MANIFEST = ...;' line in {source_desc} "
            f"to replace (found {n}) - has the dashboard's structure changed?"
        )
    return html


def _embed_snapshot_manifest(html_path: Path, manifest: list) -> None:
    """Regenerates `html_path`'s own `SNAPSHOT_MANIFEST` const in place -
    see `_embed_snapshot_manifest_into_html` for the actual replacement
    logic, shared with `prepare_deploy_site`."""
    html = _embed_snapshot_manifest_into_html(html_path.read_text(), manifest, str(html_path))
    html_path.write_text(html)


def _read_manifest(snapshots_dir: Path) -> list:
    manifest_path = snapshots_dir / "manifest.json"
    return json.loads(manifest_path.read_text()) if manifest_path.exists() else []


def main() -> None:
    # `--prepare-site DIR`: the GitHub Pages deploy workflow's entry
    # point (.github/workflows/deploy-pages.yml), kept as a flag on this
    # same script rather than a separate one so there's no risk of it
    # importing a stale copy of _decompress_snapshot() - one module, one
    # decompression implementation, used by both this and the plain
    # local-dev path below.
    if len(sys.argv) >= 2 and sys.argv[1] == "--prepare-site":
        if len(sys.argv) != 3:
            print("usage: snapshot_dashboard.py --prepare-site <site_dir>", file=sys.stderr)
            raise SystemExit(2)
        prepare_deploy_site(site_dir=Path(sys.argv[2]))
        print(f"Site prepared -> {sys.argv[2]}")
        return

    # Unconditional, regardless of the SNAPSHOT_DASHBOARD flag below - a
    # plain local run (no flag set) still needs to backfill decompressed
    # copies of whatever snapshots already exist in the repo (e.g. right
    # after a fresh clone), so the live dashboard's picker works offline -
    # and, per Keith's own framing, doubles as a local dry run of exactly
    # what --prepare-site above will do in CI, since both call the same
    # _decompress_snapshot().
    synced = sync_local_snapshots()
    if synced:
        print(f"Synced {len(synced)} local snapshot copy/copies for offline viewing.")

    if os.environ.get("SNAPSHOT_DASHBOARD") != "1":
        print("SNAPSHOT_DASHBOARD not set to 1 - skipping the dashboard snapshot "
              "(pass SNAPSHOT_DASHBOARD=1 to take one for this run).")
        return
    out_path = take_snapshot()
    print(f"Dashboard snapshot written -> {out_path}")


if __name__ == "__main__":
    main()
