# Orientation for a new session

Read this first, then `plans/wider.md`, `plans/qa-pipeline.md`, and
`plans/publishing-and-history.md` in full before doing anything else.
This project is worked across many separate chat sessions over a period
of weeks - those files are the actual persistent memory of the project,
not this chat history. They're kept current as work happens: design
decisions, the questions that were asked to scope them, what was
verified and how, and what's still open. Don't re-derive a decision
that's already recorded there, and don't re-propose something already
logged as `[investigate]`/`[todo]` without checking if it's already
scoped.

- `plans/wider.md` - the whole PoC: what exists and where, open
  architectural questions, parked thoughts for later.
- `plans/qa-pipeline.md` - specifically the birth-registrations QA
  pipeline: real bugs found running the real tools, check design,
  dashboard follow-ups.
- `plans/performance.md` - narrowly the real-tool orchestration scripts'
  runtime.
- `plans/publishing-and-history.md` - how QA results become a durable,
  committed, multi-person-publishable history (superseding today's
  gitignored `reports/*.json`), CI-gated publishing with no manual
  local-publish path, check retirement/definition-change versioning, and
  cadence-aware "as of" viewing (one data-asset-level offset, motivated
  by non-daily datasets but applied globally - see that file's Thread C
  for the 2026-09-16 correction on this point). Phases 1-4 are BUILT
  (results storage/check-lifecycle format, history-only dashboard
  rebuild, CI-gated publish with no local commit-back, and the as-of
  date picker itself); Phase 5 (check-lifecycle/changelog UI) and Phase
  6 (test coverage pass) are still open - see that file's own "Build
  order" section for the phase-by-phase detail. Read this before
  touching anything related to `reports/*.json` gitignore status, the
  dashboard's publish/deploy path, check lifecycle, or the as-of
  viewing/picker - the design already accounts for changes in this area
  that haven't all landed in code yet.

## Who this is for

Keith, Director of Data Technology at a Western Australian government
agency, working this as a proof-of-concept over **weeks**, not months -
don't assume a long timeline or plan around one. He gives feedback by
voice dictation fairly often; when a message reads oddly (garbled words,
self-contradicting mid-sentence), it's very likely a transcription
artifact, not a genuine ambiguity - read for intent rather than asking
him to repeat himself, unless the fork it implies is actually consequential.

## What this repo is

An end-to-end QA/data-pipeline PoC for a multi-agency government data
asset, built around one real feed (BDM Birth Registrations) plus a Child
Protection collection, both backed by synthetic data. `README.md` is the
detailed technical entry point (what's real vs. "equivalent", how to run
it, including the project's origin in a claude.ai session with no
internet access, later picked up by a Claude Code session with real
access to actually run the tools).

Rough layout:

| Path | What |
|---|---|
| `contract/` | Real ODCS contract + SodaCL check YAML - the actual source of truth for schema/quality rules. Also holds `data-asset.yaml` - genuinely data-asset-level (not per-dataset) config, currently just `data_asset_id`/`as_of_offset_days` (Thread C's "as of" viewing offset - one global value, corrected 2026-09-16 from an earlier, wrong per-dataset attachment - see `plans/publishing-and-history.md`) |
| `generator/` | Synthetic data generation (`daily_batch.py`, `generate_runs.py`, `resupply.py`, `dirty.py`, `names_au.py`, `presentation.py`) - Birth Registrations only; deliberately separate from `synthetic_data_generator/`'s population-scale generator, though the two share `dirty.py`/`names_au.py`/`presentation.py` (canonical here, imported from there - see `plans/wider.md`'s package-layout entry). A real package (`generator/__init__.py`) - run its scripts as `python3 -m generator.<module>`, not `python3 generator/<module>.py` (the latter can't resolve the absolute imports this needs - see that same entry for why). |
| `synthetic_data_generator/` | A separate, population-scale (millions), cross-agency-identity-linked synthetic data generator - not currently wired into the pipeline (see `plans/wider.md`). Also a real package, run as `python3 -m synthetic_data_generator.<module>`. |
| `pipeline/` | `orchestrate.py` generates + loads the combined DuckDB warehouse - used locally (`./run_pipeline.sh`) and by `qa_tools.bdm.orchestrate_bdm`, never by CI (see `qa_results/`'s own entry). `build_dashboard_data.py`/`build_cp_dashboard_data.py` reshape `reports/results_bdm.json`/`results_cp.json` (check results + `dataset_stats`, both from committed `qa_results/` history) into dashboard JSON - pure functions of that one file since Phase 3, no DuckDB import or live query of their own any more. Also a real package, run as `python3 -m pipeline.<module>`. |
| `qa_tools/` | The actual dbt-core/Soda Core/datacontract-cli/Evidently runs - the only pipeline path now (no more "_real" suffix on any of this - see `plans/wider.md` action 20's follow-up for why it dropped, once `engines/` was gone there was nothing left to distinguish it from). A proper Python package: `bdm/` and `cp/` (one per dataset, run as `python3 -m qa_tools.bdm.orchestrate_bdm` / `qa_tools.cp.orchestrate_cp`) plus `common/` (tool-generic subprocess/API invocation shared between them, including `qa_results_writer.py`, `qa_results_reader.py`, `check_lifecycle.py`, `git_identity.py`, and `changelog.py` - see the `qa_results/` entry below). `bdm/build_results_from_history.py`/`cp/build_results_from_history.py` rebuild `reports/results_bdm.json`/`results_cp.json` purely from committed `qa_results/` history, no real tool re-run needed - the Phase 2 counterpart to `orchestrate_bdm.py`/`orchestrate_cp.py`'s live-run path, same output shape either way (verified byte-identical, `generated_at` aside). (An earlier `engines/` directory of hand-written Python/DuckDB stand-ins, from before real tool access existed, was removed once it had drifted out of sync - see `plans/wider.md` action 18. Git history holds it if ever needed.) |
| `qa_results/` | Committed per-run raw tool output - one file per tool per dataset per run (`qa_results/<agency>/<dataset-or-collection>/<run_id>/<tool>.json`), written by every `qa_tools/*/run_*.py` module via `qa_tools/common/qa_results_writer.py`. Committed to git, not gitignored - unlike `reports/*.json` (still gitignored/ephemeral - a reshaped VIEW of this data, not the source of it), this is the real, permanent source of truth for QA history, potentially spanning years - see `plans/publishing-and-history.md` Thread B. Each file holds two things side by side: `raw_output` (that tool's native, genuinely unmodified output - a real dbt `run_results.json`, a real Soda `scan_results` dict, etc.) and `verified` (the same fully-resolved, dashboard-ready check-result records `evaluate_*()` builds in memory every run, captured here too so reading this history back later - `qa_tools/common/qa_results_reader.py`, Phase 2 - needs no live per-run DuckDB/CSV access; dbt's two known-bad-failure-count bugs (dbt-labs/dbt-core#11312, plus a second still-unexplained one - `plans/qa-pipeline.md` items 34/38) and Soda's missing row-count totals only resolve correctly via such a live connection, which won't exist once the run is over - see `qa_results_writer.py`'s own docstring for the full account). A 5th pseudo-tool file per run, `dataset_stats.json` (written the same way, `tool="dataset_stats"`, not a real QA tool), holds the presentation-layer data the dashboard needs (value-count distributions, arrival-lag stats, per-check failing-value aggregates, and that run's own manifest entry) - computed once by `orchestrate_bdm.py`/`orchestrate_cp.py` at the one point with a legitimate live warehouse connection (`qa_tools/bdm/dataset_stats.py`/`qa_tools/cp/dataset_stats.py`), so nothing downstream ever needs one - Phase 3, Keith's hard rule: CI must never touch data, real or (in this PoC) synthetic-standing-in-for-real. Every file also carries a top-level `run_by` field alongside `run_timestamp` (only the `dataset_stats` write passes it - one value per run is all the changelog feature below needs) - `qa_tools/common/git_identity.py`'s `get_run_by()` (the local `git config user.email`, read once per `orchestrate_bdm.py`/`orchestrate_cp.py` invocation, hard error if unset - never falls back to a placeholder). `qa_tools/common/changelog.py`'s `build_changelog(agency, dataset)` reshapes this into "who QA'd what, when" feed events - Phase 3's changelog/activity-feed DATA logic (its own UI is Phase 5): `run_by`/`run_timestamp` come straight from file content (grouped by `run_timestamp`, not by git commit, since one commit can legitimately bundle multiple datasets' events); `committed_at`/`commit_sha` are resolved by a single walk of that dataset's own git history (never self-recorded pre-push - see the module's own docstring for why a commit made locally can still be rebased before it reaches the shared branch, rewriting its SHA and committer date). Every check across all 4 tools also carries hand-authored lifecycle metadata (`check_id`/`introduced_date`/`description`/`changelog`) directly in its own definition (dbt's `meta:`, Soda's `attributes:`, the ODCS contract's `customProperties:`, a plain dict for Evidently) - parsed and validated by `qa_tools/common/check_lifecycle.py` (globally-unique `check_id`, no undocumented config changes) - see that file's own docstring and `plans/publishing-and-history.md` Thread D. |
| `dashboard/qa-reporting-dashboard.template.html` | The single-file static dashboard's real, committed source - hand-authored UI (HTML/CSS/JS), edited directly, with placeholder consts (`REAL_BIRTH_REG_DATA`/`REAL_CP_DATA`/`SNAPSHOT_MANIFEST`/`AS_OF_OFFSET_DAYS`/`CHANGELOG_FEED`/`RELEASE_NOTES` - `null`/`[]`/`null` here, never real data). **`dashboard/qa-reporting-dashboard.html` (no `.template`) is the BUILD OUTPUT - gitignored, never committed** (2026-09-16, Keith's call, `plans/publishing-and-history.md` Phase 3): `dashboard/embed_dashboard_data.py` reads the template, embeds real data from `reports/birth_registrations_dashboard.json`/`child_protection_dashboard.json` into the two `REAL_*` consts, `contract/data-asset.yaml` into `AS_OF_OFFSET_DAYS`, (Phase 5a, 2026-09-17) `qa_tools/common/changelog.py`'s `build_changelog()` output - merged across both real dataset scopes, newest-published-first, capped to 30 entries - into `CHANGELOG_FEED`, and (item 62, Phase 5h, 2026-09-17) the repo-root `CHANGELOG.md` - a hand-maintained, Keep-a-Changelog-style file tracking the PoC/tool's own development history (a genuinely different feed from `CHANGELOG_FEED`'s QA-publish activity), parsed by `dashboard/changelog_md.py`'s `parse_changelog()` - into `RELEASE_NOTES`, then writes the result to that gitignored path - what CI deploys to Pages and what `./run_pipeline.sh` builds for local viewing. Since `CHANGELOG_FEED` needs `qa_tools.common.changelog` importable, `embed_dashboard_data.py` is now always invoked as `python3 -m dashboard.embed_dashboard_data` (never the bare `python3 dashboard/embed_dashboard_data.py` it used to be run as in `run_pipeline.sh`/`deploy-pages.yml` - a bare script path only puts `dashboard/` on `sys.path`, not the repo root, so cross-package imports fail) - matches how `dashboard/check_dashboard_renders.py`/`dashboard/snapshot_dashboard.py` were already invoked. `dashboard/snapshot_dashboard.py` separately re-embeds `SNAPSHOT_MANIFEST` into that same built file from the real, committed `dashboard/snapshots/manifest.json`. Since this split (previously one hybrid file holding both hand-authored UI AND embedded real data, with the real-data half either committed directly or, briefly, committed back by CI - see `plans/publishing-and-history.md` Phase 3 for that full history) git can never see a diff on the build output to accidentally stage or commit - the earlier problem ("don't commit a local rebuild") is now structurally impossible rather than something to remember or a pre-commit hook has to catch. `.github/workflows/deploy-pages.yml` rebuilds the whole dashboard from committed `qa_results/` history on every relevant push (no real tool re-run - CI is the only publish path, per Thread A), gates the result (structural + check-lifecycle + real-browser render checks - see `qa_tools/common/validate_check_lifecycle.py`/`dashboard/check_dashboard_renders.py`), and only then deploys - it doesn't commit anything back to git either. "What was published when" is a deterministic rebuild from `qa_results/` (same pipeline CI runs) or GitHub Pages' own deployment history (tied to the exact commit SHA each deployment was built from) - `qa_results/` itself (the real source of truth, Thread B) is untouched by any of this. `dashboard/snapshots/*.html.gz` below remains the separate, unaffected point-in-time archive mechanism. |
| `dashboard/snapshots/` | "Time travel" archive - gzipped, timestamped, fully self-contained copies of the dashboard HTML (`dashboard/snapshot_dashboard.py`, opt-in via `SNAPSHOT_DASHBOARD=1`), each independently openable with nothing but a browser years from now. The `.html.gz` files are committed to git, not gitignored - unlike everything else generated by this pipeline, these are meant to accumulate, not get regenerated away. Decompressed `.html` siblings (same name, no `.gz`) also live alongside them for local/offline viewing - those ARE gitignored (`dashboard/snapshots/*.html`) and regenerated on every `./run_pipeline.sh` run via `sync_local_snapshots()`, same as any other generated artifact; only the `.gz` originals are the source of truth. Also touches `dashboard/`, so a commit adding one does trigger a (harmless, no-op-content) GitHub Pages redeploy alongside the real dashboard publish above - see `plans/wider.md`'s time-travel entry. |
| `docs/` | Research and design-note docs - `data-contract-engines-landscape.md` (tooling survey), `synthetic-data-generation-tools-research.md`, `synthetic-data-generator-notes.md`, `remediation-workflow-design.md` (the bad-data ticketing/case-management design - deliberately out of this PoC's build scope, seam only) |
| `plans/` | Living project memory - see above |

## Conventions worth knowing before touching anything

- `data/raw/`, `data/warehouse.duckdb`, `reports/*.json` etc. are
  gitignored and fully regenerated - never hand-edit or try to commit
  them. `dashboard/snapshots/*.html.gz` and `qa_results/` are the
  deliberate exceptions - both ARE committed, on purpose (see each
  path's own table entry above) - don't gitignore them or delete old
  entries as "generated cruft". `qa_results/` specifically holds the
  real per-run tool output history (plans/publishing-and-history.md
  Thread B) - every real pipeline run adds to it, nothing in it should
  ever be deleted or regenerated away the way `reports/*.json` is.
  Regenerate via `./run_pipeline.sh` (the whole pipeline end to
  end, ~45s) or `uv run python3 -m qa_tools.bdm.orchestrate_bdm` (just
  the real-tool check runs, if `data/raw/`/`data/warehouse.duckdb`
  already exist; `uv run python3 -m qa_tools.cp.orchestrate_cp` for
  Child Protection - not part of `run_pipeline.sh`, run separately).
  `qa_tools`, `generator`, `pipeline`, and `synthetic_data_generator` are
  all real Python packages now (`-m` invocation, e.g. `uv run python3 -m
  generator.generate_cp_runs`, never a bare script path like `python3
  generator/generate_cp_runs.py` - that can't resolve this project's
  absolute imports across packages) - both orchestration scripts run
  their manifest's runs in parallel by default (`qa_tools/common/
  parallel_orchestrate.py`) - add `--sequential` if debugging one
  specific run, since parallel workers interleave their print output and
  stack traces. Always through `uv run`, not a bare `python3` - this repo
  gets run on other people's machines as part of evaluating the PoC, so
  nothing should depend on an activated `.venv` or a system Python that
  happens to have the right packages (see README's "Development" section).
- Everything is seeded - regenerating reproduces the same output, so a
  diff against previous output is a real correctness check, not noise
  (used repeatedly to verify refactors are behaviour-preserving).
- Dependencies are managed with `uv` (`pyproject.toml` + `uv.lock`) -
  `uv sync --dev` installs everything including dev tooling. A real dbt
  test dependency too, not covered by `uv`: `uv run dbt deps
  --project-dir dbt_project --profiles-dir qa_tools/dbt_profiles`
  (one-time, only re-run if `dbt_project/packages.yml` changes) installs
  `dbt_utils` - several real dbt checks (`dbt_utils.accepted_range`/
  `expression_is_true`/`recency`, added in the 2026-09-15 dbt_utils
  switch - see `plans/qa-pipeline.md`) use macros that package ships,
  not dbt-core itself, so `dbt build` won't compile without it. Run
  `uv run pytest` (fast smoke tests - generator layer runs the real
  seeded generator, dashboard-builder layer uses fixtures, no slow
  real-tool run needed) and `uv run ruff check .` (a deliberately lean
  rule set - real bugs only, not style) before considering a change
  done. `pre-commit install` wires ruff into `git commit` automatically.
  Not needed yet, but flagged: once the suite runs long enough that
  wall-clock time actually matters (currently ~3s for 13 tests - `pytest-
  xdist` would add more overhead than it saves), switch to `pytest-xdist`
  for parallel test execution rather than just tolerating a slower suite.
- **CI (and any "read committed history" code path - `qa_tools/*/
  build_results_from_history.py`, `pipeline/build_*_dashboard_data.py`)
  must never depend on live data access, real or synthetic.** Not "must
  avoid touching real data" - the actual rule is narrower and stricter:
  no regenerating, opening, or querying `data/`/`data/raw/`/`data/
  cp_raw/`/any DuckDB warehouse, full stop, even though this PoC's data
  is fake and harmless to regenerate. The reasoning (Keith's own words,
  2026-09-16, after finding `deploy-pages.yml` was still regenerating
  synthetic warehouses so the dashboard's chart queries had something
  to query): a pipeline that's only safe because today's data happens
  to be synthetic isn't a pipeline that's actually safe - it's one
  accident away from being pointed at something real. See
  `plans/publishing-and-history.md`'s Phase 3 write-up for the full
  incident and fix (`qa_tools/*/dataset_stats.py` - any computation
  that needs a live connection gets computed once, at real-run time,
  by whichever `orchestrate_*.py` already has one legitimately open,
  and committed to `qa_results/` alongside that run's check results -
  never deferred to a later read). Before adding ANY new computation to
  the dashboard-build path, ask first whether it needs a live
  connection to anything under `data/` - if yes, it belongs in
  `orchestrate_bdm.py`'s/`orchestrate_cp.py`'s own run step and a
  committed `qa_results/` file, not in `pipeline/build_*_dashboard_
  data.py`.
- **Whenever an actual bug is found** (not a design gap, not a missing
  feature - a case where the code produces a genuinely wrong result),
  add a test to `tests/` that reproduces it and fails against the
  current (buggy) code first, confirm it actually fails, then fix the
  bug and confirm the same test now passes. Applies repo-wide, not just
  to files `tests/` currently covers - a bug outside that scope still
  gets a new test alongside the fix, not just a fix. Don't retrofit this
  onto bugs already fixed earlier in this project's history; it's a
  going-forward convention.
  **Exception, scoped 2026-09-15**: an environment/wiring bug - the
  wrong file/module gets resolved or loaded (import ordering, `sys.path`,
  a stale path/config constant, working-directory assumptions), as
  opposed to a logic bug (given correct inputs, the code computes the
  wrong value) - ask Keith before writing the regression test, right
  when the bug's been diagnosed, rather than writing one automatically.
  Reasoning: the real fix for this class of bug is often to remove the
  fragile mechanism entirely (e.g. deleting a duplicate file, making a
  directory a real package instead of a `sys.path` hack), which can make
  a "regression test" moot the moment it's written - it ends up
  documenting a hack that no longer exists rather than guarding an
  ongoing behaviour. A worked example: `generator/generate_cp_runs.py`
  importing the wrong `dirty.py` (2026-09-14) - the actual fix deleted
  the duplicate file and made `generator/` a proper package, so there
  was no longer a second `dirty.py` left to accidentally resolve to; the
  test written for it says as much in its own docstring. Logic bugs
  (the Evidently stale-reference-constant bug, the `"N/A"`-becomes-NULL
  bug, both same session) keep the automatic rule - the fragile mechanism
  in both cases still exists after the fix (a default-argument fallback;
  pandas'/DuckDB's own null-sentinel behaviour), so a regression test
  still has real, ongoing signal.
- The repo is public (Keith's own call, synthetic data only) - GitHub
  Pages hosting depends on that; see `plans/wider.md` #5 for the
  parked note about what happens if/when it goes private again.
- When a design decision has real forks (not just implementation
  detail), scope it with Keith via a couple of rounds of clarifying
  questions before building - this has been the working pattern all
  along, not a one-off. Bias toward proceeding once the real forks are
  resolved; don't re-ask what's already been answered.
- Commit and push to whatever branch the session was told to develop
  on; don't create a PR unless explicitly asked.
