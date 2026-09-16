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
- Picker/browse UI for opening past snapshots is explicitly NOT part of
  this build - scoped as a separate, later follow-up once snapshots
  actually exist to browse.
"""
from __future__ import annotations

import gzip
import json
import os
import subprocess
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
    doesn't exist yet (embed_dashboard_data.py hasn't run)."""
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

    _append_manifest_entry(snapshots_dir, {
        "file": name,
        "taken_at": now.isoformat(),
        "commit_sha": sha,
        "raw_size_bytes": len(html_bytes),
        "compressed_size_bytes": out_path.stat().st_size,
    })
    return out_path


def _append_manifest_entry(snapshots_dir: Path, entry: dict) -> None:
    """A plain, minimal record of what's been snapshotted - bookkeeping
    for this script itself (and something tests/test_snapshot_dashboard.py
    can assert against), NOT the cross-snapshot query/comparison feature
    the module docstring explains was scoped OUT of this build. A future
    picker UI (deliberately not built here) would likely read this rather
    than re-deriving it by listing the directory."""
    manifest_path = snapshots_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    manifest.append(entry)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def main() -> None:
    if os.environ.get("SNAPSHOT_DASHBOARD") != "1":
        print("SNAPSHOT_DASHBOARD not set to 1 - skipping the dashboard snapshot "
              "(pass SNAPSHOT_DASHBOARD=1 to take one for this run).")
        return
    out_path = take_snapshot()
    print(f"Dashboard snapshot written -> {out_path}")


if __name__ == "__main__":
    main()
