# Orientation for a new session

Read this first, then `plans/wider.md`, `plans/qa-pipeline.md`,
`plans/publishing-and-history.md`, and `plans/conceptual-design.md` in
full before doing anything else. This project is worked across many
separate chat sessions over a period of weeks - those files are the
actual persistent memory of the project, not this chat history. They're
kept current as work happens: design
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
- `plans/conceptual-design.md` - real conceptual/design tensions in how
  this PoC MODELS real-world concepts (e.g. whether a resupply chain
  should be derived from synthetic generator bookkeeping or from real,
  observable facts) - a different kind of question from a bug, a
  feature, or the publishing mechanism, and the other three files aren't
  the right place for it. Read this before touching resupply-chain/
  supply-history logic or anything about red/amber/green status
  semantics - it records real decisions already made (don't re-litigate
  them) and real questions deliberately left open (don't try to resolve
  them unprompted).
- `plans/running-thoughts.md` - a raw capture buffer for Keith's own
  forward-looking ideas (ticketing, gamification, staff adoption, an AWS
  MVP, etc.), landed in a batch and not yet scoped - not required
  reading up front like the four above, but check it before starting a
  new significant piece of work in case it's already something Keith's
  flagged there, and scope each item with him before building it, same
  as anywhere else in this project.

## Who this is for

Keith, Director of Data Technology at a Western Australian government
agency, working this as a proof-of-concept over **weeks**, not months -
don't assume a long timeline or plan around one. He gives feedback by
voice dictation fairly often; when a message reads oddly (garbled words,
self-contradicting mid-sentence), it's very likely a transcription
artifact, not a genuine ambiguity - read for intent rather than asking
him to repeat himself, unless the fork it implies is actually consequential.

**Keith is in Perth (AWST, UTC+8, no daylight saving) - this session's
own environment is not.** Real incident, 2026-09-18: a session wrote
several genuinely-correct "2026-09-18" dates (in `plans/running-
thoughts.md`, dictated on Keith's real Perth morning run), then
"corrected" them to 2026-09-17 based on this environment's own `date -u`
- which was still showing the 17th because AWST is 8 hours ahead and it
was between UTC 16:00 and 24:00, i.e. already past midnight in Perth.
Caught only when Keith asked directly. **When "today"'s real calendar
date matters** (a `plans/*.md`/`CHANGELOG.md` entry timestamp, "is this
still today's work," anything date-sensitive) - **use Keith's own real
local date, not this environment's bare `date`/`date -u`**: `TZ=Australia/Perth
date '+%Y-%m-%d'` (or equivalent). This matters most in the roughly
8-hour UTC window (16:00-23:59 UTC) where the two calendars disagree -
easy to hit late in a working session, exactly when this incident
happened.

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
| `tests-js/` | Vitest coverage for the dashboard template's own inline JS (Phase 6 step 5, `plans/publishing-and-history.md`, 2026-09-18) - a genuinely separate toolchain from the Python `tests/` above (`package.json`/`package-lock.json`/`vitest.config.js` at repo root, `npm test` to run, `npm ci` in CI). `tests-js/support/loadDashboard.js` loads the REAL, committed `dashboard/qa-reporting-dashboard.template.html` into a real jsdom `Window` (`runScripts:"dangerously"`) exactly as a browser would - every top-level `function foo(){}` in the template's own inline `<script>` becomes a callable `window.foo`, so this needs **no changes to the template itself** to become testable (the concrete "how" question this step was explicitly scoped as needing to resolve first - see that file's own docstring for the couple of jsdom gaps it stubs, `matchMedia`/`scrollTo`, both real jsdom "not implemented" gaps, not page bugs). Covers cadence math, status rollups, drill-down navigation, and supply-history grouping (`tests-js/cadence.test.js`/`status-rollups.test.js`/`navigation.test.js`/`supply-history.test.js`) plus the raw-template-with-illustrative-mock-data scenario itself (`tests-js/dashboard-loads.test.js` - the same "zero console errors" bar `dashboard/check_dashboard_renders.py`'s real-browser check already holds the BUILT output to, applied here to the template's own inline logic). Run in CI by `.github/workflows/test.yml`'s separate `js-tests` job (parallel to the Python `test` job, independent toolchain). No coverage threshold enforced here yet (unlike the Python side's `pytest-cov`) - this step's own scope was "cover these 4 named areas," not full-suite coverage parity. |
| `docs/` | Research and design-note docs - `data-contract-engines-landscape.md` (tooling survey), `synthetic-data-generation-tools-research.md`, `synthetic-data-generator-notes.md`, `remediation-workflow-design.md` (the bad-data ticketing/case-management design - deliberately out of this PoC's build scope, seam only) |
| `plans/` | Living project memory - see above. `plans/running-thoughts.md` specifically is the raw, not-yet-scoped capture buffer for Keith's own forward-looking ideas - see that file's own intro for how it differs from the other three. |

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
  `uv run pytest` and `uv run ruff check .` (a deliberately lean rule
  set - real bugs only, not style) before considering a change done.
  `pre-commit install` wires ruff into `git commit` automatically -
  plus, since 2026-09-18, a real `check-yaml` hook (pre-commit-hooks'
  own, `yaml.safe_load` against every staged `*.yml`/`*.yaml`) added
  after a real incident: a hand-edited `contract/*.yaml` changelog
  entry got shell-escape-style quoting instead of real YAML quote-
  doubling, still committable since ruff only checks Python, not caught
  until the next real tool run parsed the file. The
  suite is no longer just fast fixture-based smoke tests - Phase 6 of
  `plans/publishing-and-history.md` (2026-09-18) added real dbt-core/
  Soda Core/datacontract-cli/Evidently integration tests
  (`tests/test_run_*_{bdm,cp}.py`, against small real fixtures built by
  `tests/conftest.py`'s own session-scoped fixtures) alongside the
  original fixture-based ones, so the full suite takes real minutes now
  (~2 minutes, 302 tests as of the requirements-register work,
  2026-09-18 - down from ~2m43s/163s the same day, once `tests/
  test_generate_runs.py`'s own 6 tests were found - via a real
  `pytest --durations` profile, Keith's own question about local
  runtime - to each independently call the real generator fresh
  (~9s each, ~52s total for identical, deterministic output); now a
  single `scope="module"` fixture, real ~43s saved for zero coverage
  loss), not seconds - `pytest-xdist` (parallel test execution) is
  worth revisiting now that this has actually happened, not just
  flagged for someday (checked 2026-09-18: not yet installed - the
  real-tool integration fixtures in `tests/conftest.py` already use
  per-session `tmp_path_factory` dirs, but whether the real dbt
  subprocess calls those fixtures make would collide across PARALLEL
  workers - dbt's own shared `dbt_project/target/` default, the same
  class of problem `qa_tools/common/parallel_orchestrate.py` had to fix
  with a `--target-path` per run - hasn't been checked). CI
  (`.github/workflows/
  test.yml`) runs the full suite with `pytest-cov` on every push and
  enforces `pyproject.toml`'s `[tool.coverage.report] fail_under` - a
  real, measured threshold (not a guessed one - see
  `plans/publishing-and-history.md`'s Phase 6 "Build progress" note for
  how it was set), so real coverage can't silently regress. Run
  `uv run pytest --cov=qa_tools --cov=pipeline --cov=generator
  --cov=dashboard --cov-report=term-missing` locally to check the same
  gate before pushing, if a change might have reduced coverage. A
  SEPARATE toolchain, `npm test` (Vitest - `package.json`/`vitest.
  config.js` at repo root, `npm ci` once after cloning), covers the
  dashboard template's own inline JS - see `tests-js/`'s own table entry
  above. Touching `dashboard/qa-reporting-dashboard.template.html`
  itself should run both, PLUS `tests/test_dashboard_e2e.py` (Phase 6
  step 6, 2026-09-18) - real Playwright browser tests (as-of date
  picking, supply-history drill-down, dark mode persistence, plus the
  raw-template-with-mock-data render check absorbed from `dashboard/
  check_dashboard_renders.py`), included in `uv run pytest`'s normal
  run once `uv run playwright install chromium` has been done (same
  one-time step this project's other Playwright-based tools already
  need - see that dev dependency's own comment in `pyproject.toml`).
  These build the real dashboard first (the same CI-safe chain
  `deploy-pages.yml` runs - committed `qa_results/` history only, never
  `data/`), so expect this one test module to take longer than the rest
  of the suite.
- **A passing local `uv run pytest` is NOT evidence CI is green - after
  pushing to this branch, actually check the real GitHub Actions run
  (the GitHub MCP tools' `actions_list`/`get_job_logs`, or the Actions
  tab) before calling the work done.** Real incident, 2026-09-18: every
  `test.yml` run silently failed for 8+ commits/2+ hours (Phase 6 step
  2 through the start of Phase 7) because GitHub's `ubuntu-latest`
  runner resolved a different Python version than this session's local
  sandbox (no `.python-version` existed yet), and separately because
  `test.yml` never ran the documented one-time `dbt deps` step - both
  invisible locally since the local environment didn't have either gap.
  Keith caught it by checking the Actions tab himself, not because
  anything here noticed. The fix for both was real and specific (a
  committed `.python-version` pinning 3.11; the missing `dbt deps`
  step), but the STANDING process fix is this bullet: local passing is
  a necessary check, never a sufficient one, precisely because CI's
  environment can silently diverge from local on things neither
  `pytest` nor `ruff` would ever catch (interpreter version, one-time
  setup steps a local session already had installed from earlier work,
  etc.). Check the actual run after every push that touches CI-relevant
  files, not just once in a while.
  **Amended, 2026-09-18 (Keith's own explicit call): don't block on it.**
  The lesson above stands - a real, verified CI result is still required
  before calling CI-relevant work done, never just assumed from local
  `pytest` - but checking it is not a reason to sit idle waiting for a
  multi-minute run to finish. After a push, keep moving on other queued
  work in the same session, and check the real run's result at the next
  natural pause (or via a scheduled check-in) rather than blocking the
  turn on it. Report back proactively if it's actually red; a green run
  doesn't need its own announcement, just a passing mention next time
  it's relevant.
- **A push that ships anything release-note-worthy gets a `CHANGELOG.md`
  entry in the SAME push, not backfilled later.** "Release-note-worthy"
  is the same bar `CHANGELOG.md`'s own intro and item 62's original
  scoping already set (`plans/qa-pipeline.md`): a real feature, fix, or
  architectural change to the PoC itself - the whole repo's real
  history, not dashboard-features-only - curated prose, not a
  mechanical commit dump, so not every commit needs one (a `plans/*.md`
  update, a wording tweak, or this file's own conventions don't - those
  belong in the relevant `plans/*.md` file, not here). Add to that day's
  own `## <date>` section if one already exists (Keep a Changelog style
  - `### Added`/`### Fixed`/`### Changed`), matching the file's existing
  entries' voice and level of detail, rather than assuming a new date
  section is needed. Real incident, 2026-09-18: a full day of Phase 6/7
  work (test coverage, the resupply-chain redesign, two real CI fixes)
  shipped with zero `CHANGELOG.md` entries, only caught when Keith asked
  for them directly - the STANDING fix is this bullet, not just that
  one-off backfill. Concretely: before every commit that isn't purely
  `plans/*.md`/process-only, ask "does this meet the bar above" as a
  real step, the same way `pytest`/`ruff` are already a real step before
  considering a change done - not something to remember only when
  reminded. If the release-notes scope itself ever seems unclear for a
  specific change, ask Keith rather than guessing either way (include
  something too granular, or skip something real).
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
