# Orientation for a new session

Read this first, then `plans/wider.md`, `plans/qa-pipeline.md`,
`plans/publishing-and-history.md`, `plans/supply-model.md`,
`plans/conceptual-design.md`, `plans/dashboard.md`,
`plans/data-generation.md`, and `plans/tooling.md`
in full before doing anything else. This project is worked across many separate chat
sessions over a period of weeks - those files are the actual persistent
memory of the project, not this chat history. They're kept current as
work happens: design decisions, the questions that were asked to scope
them, what was verified and how, and what's still open. Don't re-derive
a decision that's already recorded there, and don't re-propose something
already logged as `[investigate]`/`[todo]` without checking if it's
already scoped.

- `plans/wider.md` - genuinely cross-component strategic questions (ones
  that don't belong to any single part of the system - warehouse choice,
  pipeline observability, production-readiness, generalizing the whole
  architecture), plus orientation material and small process/
  housekeeping notes. Narrowed 2026-09-18 (see that file's own intro):
  used to be an undifferentiated 32-item dump covering everything
  outside the QA pipeline itself; split that day into the topic-specific
  files below (`plans/dashboard.md`, `plans/data-generation.md`) plus
  redistribution into `plans/qa-pipeline.md`/`plans/publishing-and-
  history.md` - if a new item is clearly about ONE component, it belongs
  in that component's own file, not here.
- `plans/dashboard.md` - the QA reporting dashboard itself: features,
  UI, hosting/deployment of the published site.
- `plans/data-generation.md` - synthetic data generation: `generator/`
  and `synthetic_data_generator/`.
- `plans/tooling.md` - real developer/testing tooling that doesn't belong
  to one dataset or pipeline stage: the unified `mothman` CLI/TUI design
  (covering every entry point across `qa_tools/`, `pipeline/`,
  `generator/`, `dashboard/`) and its supporting dev-only scripts. Split
  out of `plans/wider.md` 2026-09-19 once that one item had grown far
  larger than anything else there - read this, not `plans/wider.md`,
  before touching anything CLI/TUI-related.
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
  for the 2026-09-16 correction on this point). All phases (1-7,
  including Phase 5's check-lifecycle/changelog UI, Phase 6's test
  coverage pass, and Phase 7's CI-health fixes) are now BUILT - see
  that file's own "Build order" section for the phase-by-phase detail.
  Read this before
  touching anything related to `reports/*.json` gitignore status, the
  dashboard's publish/deploy path, check lifecycle, or the as-of
  viewing/picker - the design already accounts for changes in this area
  that haven't all landed in code yet.
- `plans/supply-model.md` - **the supply lifecycle model, and the
  delivery plan for building it.** How a supply arrives, where it is
  filed, when it is checked, what reaches the warehouse, and what the
  dashboard says about it: staging and promotion, the schedule and its
  slots, arrival classification, the decision log, and six delivery
  sprints. Split out of `plans/publishing-and-history.md` item 6 on
  2026-09-21 (Keith's own ask) once a day of design had grown far
  larger than its host item and turned out to be a different subject -
  item 6 is about CODE ARCHITECTURE (how many near-identical modules
  per dataset), this is the DOMAIN MODEL. Read this before touching
  anything about supply arrival, run/slot identity, promotion, cadence
  or the as-of picker - it records decisions already settled (don't
  re-litigate), several plausible-but-wrong approaches explicitly
  rejected (don't re-propose), and the open questions still with Keith.
  Nothing in it is built yet, and its eight requirements
  (`REQ-PIPE-034`..`REQ-DASH-041`) are all unsigned, so the sign-off
  gate applies.
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
  reading up front like the six above, but check it before starting a
  new significant piece of work in case it's already something Keith's
  flagged there, and scope each item with him before building it, same
  as anywhere else in this project.

**Finding what's currently PRIORITY, without reading all seven files.**
Some items carry an explicit priority line Keith has set (`Priority:
work through today/tomorrow`, `Priority: HIGH - to FIX`, ...). They're
scattered across files by design - priority is a property of an item,
not of a file - so the way to see the current queue is to grep for it
rather than trust any list written here, which would go stale the moment
one lands:

```
grep -rn -i "priority[:-]" plans/*.md
```

Do this at the start of a session, alongside reading the files
themselves. A priority line always states who set it and when, in Keith's
own words, so a stale one is recognisable as stale rather than silently
authoritative - check anything dated before the current session with him
rather than assuming it's still top of the list.

## Who this is for

Keith, Director of Data Technology at a Western Australian government
agency, working this as a proof-of-concept over **weeks**, not months -
don't assume a long timeline or plan around one. He gives feedback by
voice dictation fairly often; when a message reads oddly (garbled words,
self-contradicting mid-sentence), it's very likely a transcription
artifact, not a genuine ambiguity - read for intent rather than asking
him to repeat himself, unless the fork it implies is actually consequential.

**Standing working-style conventions, 2026-09-19 (Keith's own explicit
ask, a real end-of-session reflection on how this collaboration works -
this overrides this environment's own general "bias toward proceeding
without asking" default for this project specifically):**
- **Ask him questions as a general rule, not just when genuinely
  blocked.** His own words: it helps him think out loud, and he wants
  more of it, not less - a real, standing preference, not a one-off.
  Still use judgment on WHEN (mid-flow on something small doesn't need
  it), but default toward asking rather than silently deciding when
  there's a real, nameable choice to make, even a minor one.
- **When he dumps several ideas/tasks in one message with no explicit
  order, ask him which matters most rather than picking an order
  myself.** His own words: "that's a thing I suffer from in real life
  with my team" - prioritizing on his behalf risks working on whichever
  item I happened to find easiest or got to first, not the one he'd
  actually want first. Push back and ask, don't guess.
- **Log any small aside or idea mentioned in passing into `plans/
  running-thoughts.md` immediately, in the same turn - don't wait for a
  later sweep or for him to ask "did we drop something."** Real
  incident this session: the HCI/psychology grounding thread was
  flagged once, then nearly lost - recovered only because Keith
  directly asked and a slow, fragile grep of the raw session transcript
  found it. The fix isn't a better recovery method, it's not needing
  one - write it down the moment it's said, held to this standard from
  the start of a session, not arrived at partway through one.
- **Nudge Keith to stop working on this in the evening - his own
  explicit ask, 2026-09-20.** His words: "that's just something for you
  to remember so that you remind me and nudge me not to work late on
  this, to draw a clean line before bed." He gave the time twice and
  slightly differently - "a quarter to 10 p.m." and "9.25pm" - so treat
  it as **around 9:30-9:45pm Perth**, and nudge rather than enforce; the
  intent is a clean line before bed, not a curfew to police.

  Practically: this environment cannot watch a clock, so check the real
  local time (`TZ=Australia/Perth date '+%H:%M'`) at natural pauses once
  a session is running into the evening - after a push, between pieces
  of work - and say something once it is past the line. Pair it with the
  "suggest closing out and starting a fresh session" bullet below, since
  the honest version of the nudge is usually "this is a good place to
  stop, and here is what's queued for next time" rather than a bare
  reminder of the hour. Say it once and drop it if he keeps going - he
  asked for a nudge, not nagging.

  Real evidence he needs it, from this repo's own history: commits run
  as late as **23:26** Perth, with the hour-by-hour distribution
  tailing off after 21:00 (10 commits) into 22:00 (3) and 23:00 (3).

- **Proactively suggest closing out and starting a fresh session when a
  natural chunk of work completes** (not because a long session is
  inherently bad - Keith's own words, he doesn't mind running one) **or
  when this environment's own session-start-only-read gaps get hit**
  (a subagent added mid-session not appearing in the `Agent` tool's own
  roster, a `.mcp.json` change not picked up by an already-running MCP
  server - both real, repeated incidents this project has hit, `plans/
  wider.md` #10). These are two different problems with two different
  fixes, worth keeping distinct: conversational memory loss from
  compaction is mitigated by writing real decisions to `plans/*.md`
  as they happen (a file doesn't degrade with turn count, unlike
  conversational memory does through repeated lossy summarization) -
  restarting the session doesn't fix that on its own, a fresh session
  has zero memory of anything not already in a file. Session-start-only
  config staleness is the one class of problem ONLY a fresh session
  actually fixes.

**Keith is in Perth (AWST, UTC+8, no daylight saving) - this session's
own environment is not.** Real incident, 2026-09-18: a session wrote
several genuinely-correct "2026-09-18" dates (in `plans/running-
thoughts.md`, dictated on Keith's real Perth morning run), then
"corrected" them to 2026-09-17 based on this environment's own `date -u`
- which was still showing the 17th because AWST is 8 hours ahead and it
was between UTC 16:00 and 24:00, i.e. already past midnight in Perth.
Caught only when Keith asked directly. **When "today"'s real calendar
date matters** (a `plans/*.md`/`CHANGELOG.yaml` entry date, "is this
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

**The scale this is a PoC FOR, not the scale it currently runs at -
Keith's own standing instruction, 2026-09-21: "factor that into all
decisions and all advice."** Today there are 2 datasets. The real target
is **two data assets, each managed by a different team in a strictly
separated cloud environment, with its own deployment and its own
dashboard** (same codebase, entirely separate instances - so the asset
is a deployment's identity, not a row in the data), and **roughly 30
datasets on the quarterly asset alone**. A third and possibly fourth
asset shape is coming too: QA of one-off data extractions for individual
projects, which has supplies but no cadence at all.

Why it matters for advice rather than just for planning: a design that
is fine at 2 datasets routinely fails at 30 (per-dataset banners become
noise that must aggregate; a failure scoped to a whole run instead of
one dataset gets disabled by users; navigation built for a 2-item tree
is a different problem at 30), and a design that assumes a recurring
supply excludes the project-extraction shape entirely. Neither is
visible from the current repo, so it has to be carried in deliberately.
See `plans/publishing-and-history.md` item 6 and `plans/running-
thoughts.md` #23 for the design work this is feeding.

Rough layout:

| Path | What |
|---|---|
| `contract/` | Real ODCS contract + SodaCL check YAML - the actual source of truth for schema/quality rules. Also holds `data-asset.yaml` - genuinely data-asset-level (not per-dataset) config, currently just `data_asset_id`/`as_of_offset_days` (Thread C's "as of" viewing offset - one global value, corrected 2026-09-16 from an earlier, wrong per-dataset attachment - see `plans/publishing-and-history.md`) |
| `generator/` | Synthetic data generation (`daily_batch.py`, `generate_runs.py`, `resupply.py`, `dirty.py`, `names_au.py`, `presentation.py`) - Birth Registrations only; deliberately separate from `synthetic_data_generator/`'s population-scale generator, though the two share `dirty.py`/`names_au.py`/`presentation.py` (canonical here, imported from there - see `plans/publishing-and-history.md` #3). A real package (`generator/__init__.py`), invoked via `mothman bdm generate-synthetic-data`/`mothman cp generate-synthetic-data` (`cli/`'s own modules use `-m`-style absolute imports internally, never a bare `python3 generator/<module>.py` - that can't resolve the absolute imports this needs) - nothing outside `mothman`'s own implementation should invoke it directly. |
| `synthetic_data_generator/` | A separate, population-scale (millions), cross-agency-identity-linked synthetic data generator - not currently wired into the pipeline (see `plans/data-generation.md` #3). Also a real package, invoked via `mothman population` (Tier 4, explicitly exploratory - `plans/tooling.md` #1 Phase 5, never a bare `python3 -m synthetic_data_generator.<module>`). |
| `pipeline/` | `orchestrate.py` generates + loads the combined DuckDB warehouse - used locally (`mothman bdm generate-synthetic-data`, which `mothman pipeline run` also calls) and by `qa_tools.bdm.orchestrate_bdm`, never by CI (see `qa_results/`'s own entry). `build_dashboard_data.py`/`build_cp_dashboard_data.py` reshape `reports/results_bdm.json`/`results_cp.json` (check results + `dataset_stats`, both from committed `qa_results/` history) into dashboard JSON - pure functions of that one file since Phase 3, no DuckDB import or live query of their own any more. Also a real package - invoked via `mothman dashboard build-data`/`mothman pipeline run` (`cli/`'s own modules), never bare. |
| `qa_tools/` | The actual dbt-core/Soda Core/datacontract-cli/Evidently runs - the only pipeline path now (no more "_real" suffix on any of this - see `plans/qa-pipeline.md` #84's follow-up for why it dropped, once `engines/` was gone there was nothing left to distinguish it from). A proper Python package: `bdm/` and `cp/` (one per dataset, invoked via `mothman pipeline run`/`mothman bdm qa`/`mothman cp qa`/`mothman debug run-*` - `cli/`'s own modules, never a bare `python3 -m qa_tools.bdm.orchestrate_bdm` from outside them) plus `common/` (tool-generic subprocess/API invocation shared between them, including `qa_results_writer.py`, `qa_results_reader.py`, `check_lifecycle.py`, `git_identity.py`, and `changelog.py` - see the `qa_results/` entry below). `bdm/build_results_from_history.py`/`cp/build_results_from_history.py` rebuild `reports/results_bdm.json`/`results_cp.json` purely from committed `qa_results/` history, no real tool re-run needed - the Phase 2 counterpart to `orchestrate_bdm.py`/`orchestrate_cp.py`'s live-run path, same output shape either way (verified byte-identical, `generated_at` aside). (An earlier `engines/` directory of hand-written Python/DuckDB stand-ins, from before real tool access existed, was removed once it had drifted out of sync - see `plans/qa-pipeline.md` #83. Git history holds it if ever needed.) |
| `qa_results/` | Committed per-run raw tool output - one file per tool per dataset per run (`qa_results/<agency>/<dataset-or-collection>/<run_id>/<tool>.json`), written by every `qa_tools/*/run_*.py` module via `qa_tools/common/qa_results_writer.py`. Committed to git, not gitignored - unlike `reports/*.json` (still gitignored/ephemeral - a reshaped VIEW of this data, not the source of it), this is the real, permanent source of truth for QA history, potentially spanning years - see `plans/publishing-and-history.md` Thread B. Each file holds two things side by side: `raw_output` (that tool's native, genuinely unmodified output - a real dbt `run_results.json`, a real Soda `scan_results` dict, etc.) and `verified` (the same fully-resolved, dashboard-ready check-result records `evaluate_*()` builds in memory every run, captured here too so reading this history back later - `qa_tools/common/qa_results_reader.py`, Phase 2 - needs no live per-run DuckDB/CSV access; dbt's two known-bad-failure-count bugs (dbt-labs/dbt-core#11312, plus a second still-unexplained one - `plans/qa-pipeline.md` items 34/38) and Soda's missing row-count totals only resolve correctly via such a live connection, which won't exist once the run is over - see `qa_results_writer.py`'s own docstring for the full account). A 5th pseudo-tool file per run, `dataset_stats.json` (written the same way, `tool="dataset_stats"`, not a real QA tool), holds the presentation-layer data the dashboard needs (value-count distributions, arrival-lag stats, per-check failing-value aggregates, and that run's own manifest entry) - computed once by `orchestrate_bdm.py`/`orchestrate_cp.py` at the one point with a legitimate live warehouse connection (`qa_tools/bdm/dataset_stats.py`/`qa_tools/cp/dataset_stats.py`), so nothing downstream ever needs one - Phase 3, Keith's hard rule: CI must never touch data, real or (in this PoC) synthetic-standing-in-for-real. Every file also carries a top-level `run_by` field alongside `run_timestamp` (only the `dataset_stats` write passes it - one value per run is all the changelog feature below needs) - `qa_tools/common/git_identity.py`'s `get_run_by()` (the local `git config user.email`, read once per `orchestrate_bdm.py`/`orchestrate_cp.py` invocation, hard error if unset - never falls back to a placeholder). `qa_tools/common/changelog.py`'s `build_changelog(agency, dataset)` reshapes this into "who QA'd what, when" feed events - Phase 3's changelog/activity-feed DATA logic (its own UI is Phase 5): `run_by`/`run_timestamp` come straight from file content (grouped by `run_timestamp`, not by git commit, since one commit can legitimately bundle multiple datasets' events); `committed_at`/`commit_sha` are resolved by a single walk of that dataset's own git history (never self-recorded pre-push - see the module's own docstring for why a commit made locally can still be rebased before it reaches the shared branch, rewriting its SHA and committer date). Every check across all 4 tools also carries hand-authored lifecycle metadata (`check_id`/`introduced_date`/`description`/`changelog`) directly in its own definition (dbt's `meta:`, Soda's `attributes:`, the ODCS contract's `customProperties:`, a plain dict for Evidently) - parsed and validated by `qa_tools/common/check_lifecycle.py` (globally-unique `check_id`, no undocumented config changes) - see that file's own docstring and `plans/publishing-and-history.md` Thread D. |
| `dashboard/qa-reporting-dashboard.template.html` | The single-file static dashboard's real, committed source - hand-authored UI (HTML/CSS/JS), edited directly, with placeholder consts (`REAL_BIRTH_REG_DATA`/`REAL_CP_DATA`/`SNAPSHOT_MANIFEST`/`AS_OF_OFFSET_DAYS`/`CHANGELOG_FEED`/`RELEASE_NOTES` - `null`/`[]`/`null` here, never real data). **`dashboard/qa-reporting-dashboard.html` (no `.template`) is the BUILD OUTPUT - gitignored, never committed** (2026-09-16, Keith's call, `plans/publishing-and-history.md` Phase 3): `dashboard/embed_dashboard_data.py` reads the template, embeds real data from `reports/birth_registrations_dashboard.json`/`child_protection_dashboard.json` into the two `REAL_*` consts, `contract/data-asset.yaml` into `AS_OF_OFFSET_DAYS`, (Phase 5a, 2026-09-17) `qa_tools/common/changelog.py`'s `build_changelog()` output - merged across both real dataset scopes, newest-published-first, capped to 30 entries - into `CHANGELOG_FEED`, and the repo-root `CHANGELOG.yaml` - the hand-maintained "What's New" feed tracking the PoC/tool's own development history (a genuinely different feed from `CHANGELOG_FEED`'s QA-publish activity), parsed by `dashboard/changelog_yaml.py`'s `parse_changelog()` - into `RELEASE_NOTES`. Rewritten 2026-09-20 (REQ-DOCS-028) from hand-written Keep-a-Changelog Markdown into structured YAML written for READERS rather than maintainers: grouped by day with a one-sentence summary per day, each item a headline plus one or two second-person sentences, tagged with the same 7-part component taxonomy `plans/*.md` items use. The Release Notes panel renders those tags WITHOUT the per-component emoji (dropped the same day, Keith's call - the Plans tab's own filter chips keep theirs, which is why `COMPONENT_ICON` still exists). `mothman dashboard validate-changelog` gates the schema and the component tags in CI. Then writes the result to that gitignored path - what CI deploys to Pages and what `mothman pipeline run`/`mothman dashboard embed` builds for local viewing. Since `CHANGELOG_FEED` needs `qa_tools.common.changelog` importable, `embed_dashboard_data.py` is always invoked via `mothman dashboard embed`/`mothman pipeline run` (`cli/dashboard.py`'s own `_embed()`, itself calling `python3 -m dashboard.embed_dashboard_data`'s real module import path - never a bare script path like `python3 dashboard/embed_dashboard_data.py`, which only puts `dashboard/` on `sys.path`, not the repo root, so cross-package imports fail) - matches how `dashboard/check_dashboard_renders.py`/`dashboard/snapshot_dashboard.py` are invoked (`mothman dashboard check-renders`/`mothman dashboard snapshot`). `dashboard/snapshot_dashboard.py` separately re-embeds `SNAPSHOT_MANIFEST` into that same built file from the real, committed `dashboard/snapshots/manifest.json`. Since this split (previously one hybrid file holding both hand-authored UI AND embedded real data, with the real-data half either committed directly or, briefly, committed back by CI - see `plans/publishing-and-history.md` Phase 3 for that full history) git can never see a diff on the build output to accidentally stage or commit - the earlier problem ("don't commit a local rebuild") is now structurally impossible rather than something to remember or a pre-commit hook has to catch. `.github/workflows/deploy-pages.yml` rebuilds the whole dashboard from committed `qa_results/` history on every relevant push (no real tool re-run - CI is the only publish path, per Thread A), gates the result (structural + check-lifecycle + real-browser render checks - see `qa_tools/common/validate_check_lifecycle.py`/`dashboard/check_dashboard_renders.py`), and only then deploys - it doesn't commit anything back to git either. "What was published when" is a deterministic rebuild from `qa_results/` (same pipeline CI runs) or GitHub Pages' own deployment history (tied to the exact commit SHA each deployment was built from) - `qa_results/` itself (the real source of truth, Thread B) is untouched by any of this. `dashboard/snapshots/*.html.gz` below remains the separate, unaffected point-in-time archive mechanism. Also (`plans/running-thoughts.md` #10, 2026-09-18 evening, `plans/dashboard.md` #7): a `const PLANS` - this project's own `plans/*.md` planning memory, parsed by the new `dashboard/plans_md.py`'s `parse_plans()` straight from the committed `plans/` directory - powers a genuinely new top-level tab (`STATE.tier==="plans"`, a real `/plans` URL), not another header side-panel, with search and status/component/file filter chips. Also (`plans/tooling.md` #1 Phase 6, 2026-09-19, scoped via AskUserQuestion): a `const DEMO_CAST` - the real asciinema recording at `dashboard/demos/qa_wizard.cast`, embedded as a raw string by `embed_dashboard_data.py` - powers another genuinely new top-level tab (`STATE.tier==="demo"`, a real `/demo` URL, same not-a-side-panel treatment as Plans), rendering the vendored `dashboard/vendor/asciinema-player.min.js` widget lazily (only once the tab is actually opened) against that embedded recording via its `data:`-style source option (never the player's own `url:`/`fetch()` option - see the template's own const comment for why). |
| `dashboard/snapshots/` | "Time travel" archive - gzipped, timestamped, fully self-contained copies of the dashboard HTML (`dashboard/snapshot_dashboard.py`, opt-in via `SNAPSHOT_DASHBOARD=1`), each independently openable with nothing but a browser years from now. The `.html.gz` files are committed to git, not gitignored - unlike everything else generated by this pipeline, these are meant to accumulate, not get regenerated away. Decompressed `.html` siblings (same name, no `.gz`) also live alongside them for local/offline viewing - those ARE gitignored (`dashboard/snapshots/*.html`) and regenerated on every `mothman pipeline run`/`mothman dashboard snapshot` run via `sync_local_snapshots()`, same as any other generated artifact; only the `.gz` originals are the source of truth. Also touches `dashboard/`, so a commit adding one does trigger a (harmless, no-op-content) GitHub Pages redeploy alongside the real dashboard publish above - see `plans/dashboard.md` #5. |
| `dashboard/demos/` | The "Demo" tab's real source recording (`plans/tooling.md` #1 Phase 6, 2026-09-19) - `qa_wizard.cast`, a real asciinema v2 recording of the actual `mothman` CLI/TUI (Quality Assurance wizard, Birth Registrations, Synthetic mode), captured by `scripts/dev/record_cast.py`'s own real pty-capture-and-script tool (dev-only, same throwaway status as `scripts/dev/tui_screenshot.py`) and committed as plain, uncompressed text (a `.cast` file is JSON-lines, small enough - ~22KB here - that HTTP-level gzip transfer encoding already covers compression; unlike `dashboard/snapshots/*.html.gz`, no app-level decompression step is needed). `dashboard/embed_dashboard_data.py` embeds its raw text content into the template's `const DEMO_CAST` placeholder as a plain string (never fetched by the player at runtime - a `fetch()` of a sibling file is blocked by real browser CORS under a plain `file://` open, this dashboard's own supported local/offline viewing path, so embedding sidesteps that entirely - same "no live external dependency at render time" treatment every other embedded const already uses). |
| `dashboard/vendor/` | Vendored third-party static assets, same self-hosting rationale as `dashboard/fonts/*.woff2` (no CDN dependency, works from a plain `file://` open, works across government networks that may not have every third-party domain reachable) - `asciinema-player.{css,min.js}` (Apache-2.0, `asciinema-player.LICENSE`), the Demo tab's real playback widget. Referenced by the template via relative `<link>`/`<script src=` (same pattern as `fonts/`'s `@font-face url()`). A real, previously-latent gap fixed alongside this (2026-09-19, found live while wiring this up): `dashboard/snapshot_dashboard.py`'s `prepare_deploy_site()` never copied EITHER `dashboard/fonts/` or this new `dashboard/vendor/` into the `_site/` tree `.github/workflows/deploy-pages.yml` deploys - `fonts/` had silently had this gap since the self-hosted-fonts switch (a missing `.woff2` just falls back to a system font, no error), so the live published site had quietly been serving unstyled system fonts the whole time. Both are now copied into `_site/fonts/`/`_site/vendor/` by that same function. |
| `tests-js/` | Vitest coverage for the dashboard template's own inline JS (Phase 6 step 5, `plans/publishing-and-history.md`, 2026-09-18) - a genuinely separate toolchain from the Python `tests/` above (`package.json`/`package-lock.json`/`vitest.config.js` at repo root, `npm test` to run, `npm ci` in CI). `tests-js/support/loadDashboard.js` loads the REAL, committed `dashboard/qa-reporting-dashboard.template.html` into a real jsdom `Window` (`runScripts:"dangerously"`) exactly as a browser would - every top-level `function foo(){}` in the template's own inline `<script>` becomes a callable `window.foo`, so this needs **no changes to the template itself** to become testable (the concrete "how" question this step was explicitly scoped as needing to resolve first - see that file's own docstring for the couple of jsdom gaps it stubs, `matchMedia`/`scrollTo`, both real jsdom "not implemented" gaps, not page bugs). Covers cadence math, status rollups, drill-down navigation, and supply-history grouping (`tests-js/cadence.test.js`/`status-rollups.test.js`/`navigation.test.js`/`supply-history.test.js`) plus the raw-template-with-illustrative-mock-data scenario itself (`tests-js/dashboard-loads.test.js` - the same "zero console errors" bar `dashboard/check_dashboard_renders.py`'s real-browser check already holds the BUILT output to, applied here to the template's own inline logic). Run in CI by `.github/workflows/test.yml`'s separate `js-tests` job (parallel to the Python `test` job, independent toolchain). No coverage threshold enforced here yet (unlike the Python side's `pytest-cov`) - this step's own scope was "cover these 4 named areas," not full-suite coverage parity. |
| `docs/` | Research and design-note docs - `data-contract-engines-landscape.md` (tooling survey), `synthetic-data-generation-tools-research.md`, `synthetic-data-generator-notes.md`, `remediation-workflow-design.md` (the bad-data ticketing/case-management design - deliberately out of this PoC's build scope, seam only), `project-context-for-agents.md` (condensed orientation for the requirements-analysis subagents, `plans/wider.md` #10), `components.md` (2026-09-19, Keith's own ask - the full write-up of this project's own 7-part component taxonomy: names, codes, real scope, real file/directory ownership, in/out-of-scope boundary per component - `delivery-scoper` reads it to pick a new requirement's id code), `spa-best-practices.md` (2026-09-19 - SPA/client-side-routing best practice, read by `delivery-dashboard-ux`/`delivery-dashboard-ux-critic`), `hci-ux-psychology.md` (2026-09-19 - the real HCI/behavioral-psychology research grounding, context-indexed, read by all 4 `delivery-*-ux`/`*-critic` pairs across both the dashboard and CLI/TUI), `agent-orchestration.md` (2026-09-19 - how the main session actually sequences the `delivery-*` subagent pipeline: real dependencies between stages, what each needs as input, parallelism rules, how Keith can invoke it), `check-authoring-rules.md` (2026-09-20, REQ-QAC-024 - the standing standard for a check's three hand-authored prose fields, `description`/`failure_indicates`/`technical_note`: what each is for, and the real authoring rules settled with Keith over 25 checks reviewed three at a time, each carrying the draft it replaced. Read before adding a check or editing any of the three - none of it is CI-enforced, the lifecycle gate only checks `failure_indicates` is present) |
| `plans/` | Living project memory - see above. `plans/running-thoughts.md` specifically is the raw, not-yet-scoped capture buffer for Keith's own forward-looking ideas - see that file's own intro for how it differs from the other seven. Since 2026-09-18 evening (`plans/running-thoughts.md` #10), every numbered item and Thread/Phase section across all 7 tagged files (5 numbered-item files, 2 Thread/Phase essay files - `plans/tooling.md` joined the numbered-item group 2026-09-19, split out of `plans/wider.md`) carries a closed status (`todo`/`investigate`/`in-progress`/`parked`/`done`/`superseded`) and one or more of the same 7-part component tags `CHANGELOG.yaml` items also carry - and the whole set is browsable/searchable/filterable inside the live dashboard's own "Plans" tab (`dashboard/plans_md.py`), not just on GitHub. |

## Conventions worth knowing before touching anything

- **The `mothman` CLI/TUI (`plans/tooling.md` #1) is the only
  programmatic access point to this repo - a standing constraint, not a
  one-time migration.** Keith's own explicit ask, 2026-09-19: nothing -
  not CI workflows, not docs/README instructions, not a future session's
  own ad hoc script - should call a script directly, and that has to
  remain true going forward, not just be true the day Phase 4 shipped.
  Phase 4 (2026-09-19) reorganized the remaining ~24 real script entry
  points into 5 command groups (`bdm`/`cp` - Tier 1, `dashboard`/
  `github`/`pipeline` - Tier 2, `debug` - Tier 3), rewrote the 3 GitHub
  Actions workflows (`deploy-pages.yml`/`ticket-sync.yml`) to call
  `mothman` subcommands, and retired `run_pipeline.sh` in favour of
  `mothman pipeline run`. Along the way, found and fixed a real gap the
  phase's own original plan text got wrong: `orchestrate_bdm.py`'s/
  `orchestrate_cp.py`'s own `run_pipeline()`/`run_pipeline_cp()`
  functions (the full-manifest BATCH mode `run_pipeline.sh` step 2 used
  to call bare) were never actually wrapped by any earlier-phase mothman
  command - only `run_single()`, a different function in the same file,
  was - so `cli/pipeline.py`'s `mothman pipeline run` is a genuinely new
  command, not a rename. Also found and fixed a real, separate
  packaging bug while wiring this up: `uv sync` had been silently
  skipping installation of the `[project.scripts]` `mothman` entry point
  the whole time ("this project is not packaged"), so every `mothman`
  invocation anywhere in this project's history had actually been going
  through the `uv run python3 -m cli.app` fallback, never the real
  console script - fixed by adding a minimal `[build-system]`
  (hatchling) + `[tool.hatch.build.targets.wheel] packages = ["cli"]` to
  pyproject.toml; `uv run mothman ...`/`./mothman ...` both now real.
  Phase 5 (2026-09-19) added a 6th command, `mothman population` (Tier
  4, explicitly exploratory), wrapping `synthetic_data_generator/`'s own
  real argparse CLI - still genuinely unwired from the real BDM/CP
  pipeline (`plans/data-generation.md` #3/#8), just no longer a bare
  script either. Found and fixed a real, separate logic bug live while
  smoke-testing it: `synthetic_data_generator/generate.py`'s `build()`
  was calling `dirty_mod.apply_cp_notifications_presets()` with a stale
  3-arg signature - the real function had since grown `clients_df`/
  `workers_df` params (dangling-FK injection) that `generator/
  generate_cp_runs.py`'s own call site was updated for, but this
  sibling, unwired call site never was. Fixed and covered by a real
  regression test (`tests/test_cli_population.py`), confirmed failing
  against the pre-fix code first.
  Any new script added to this repo from here on gets a `mothman`
  subcommand in the same change that adds it, not left as a bare
  invocation to be swept up later - the same discipline this bullet
  itself has been asking for since before Phase 4 shipped.
- `data/raw/`, `data/warehouse.duckdb`, `reports/*.json` etc. are
  gitignored and fully regenerated - never hand-edit or try to commit
  them. `dashboard/snapshots/*.html.gz` and `qa_results/` are the
  deliberate exceptions - both ARE committed, on purpose (see each
  path's own table entry above) - don't gitignore them or delete old
  entries as "generated cruft". `qa_results/` specifically holds the
  real per-run tool output history (plans/publishing-and-history.md
  Thread B) - every real pipeline run adds to it, nothing in it should
  ever be deleted or regenerated away the way `reports/*.json` is.
  Regenerate via `mothman pipeline run` (the whole pipeline end to end
  for both datasets by default, ~45s+ - `--dataset bdm`/`--dataset cp`
  to scope to one; `--sequential` if debugging one specific run, since
  parallel workers interleave their print output and stack traces) or,
  for lower-level single-tool debugging against a run already on disk,
  `mothman debug run-dbt --dataset bdm --run-id <id>` (and the `run-soda`/
  `run-datacontract`/`run-evidently` equivalents - see `cli/debug.py`'s
  own docstring for why these ALSO write real qa_results/ history, same
  as any other real tool invocation, not a side-effect-free dry run).
  `qa_tools`, `generator`, `pipeline`, and `synthetic_data_generator` are
  all real Python packages (`cli/`'s own modules invoke them via `-m`-
  style absolute imports, never a bare script path like `python3
  generator/generate_cp_runs.py` - that can't resolve this project's
  absolute imports across packages), but nothing outside `mothman`'s own
  implementation should invoke them directly any more (see the mothman
  bullet above). Always through `uv run`, not a bare `python3` - this repo
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
  now installed and verified (2026-09-18 night, `plans/running-
  thoughts.md` #12): the real dbt-target-path collision this bullet
  used to flag as unchecked was confirmed real (reproduced it), fixed
  at the source (`evaluate_dbt_bdm()`/`evaluate_dbt_cp()` now build
  `target_path` from `DUCKDB_RUNS_DIR`/`CP_DUCKDB_RUNS_DIR` - already
  genuinely unique per run, already monkeypatched to a per-worker tmp
  dir in tests - instead of the fixed, repo-relative `dbt_project/
  target/`), and the other 3 tools' own fixtures were confirmed already
  safe (their scratch dirs were already monkeypatched to per-worker
  `tmp_path_factory` dirs). **Parallel is now the DEFAULT** (2026-09-19,
  Keith's own call, reversing the earlier serial-by-default preference):
  `pyproject.toml`'s `addopts = "-n auto --dist loadfile"` means a bare
  `uv run pytest` is already parallel, locally and in CI alike. The
  earlier reasoning for staying serial was debuggability, and the
  biggest part of it turned out not to hold - **pytest-xdist silently
  falls back to serial the moment `--pdb` is passed** (verified against
  a real failing test: a real `(Pdb)` prompt, no `gw0` worker banner),
  so interactive debugging is unaffected. Measured on this 4-core
  sandbox: full suite ~220s serial -> ~78s; a targeted single-file run
  pays a flat ~1s of worker startup (1.4s -> 2.2s). Use **`-n0`** to
  force serial - the one case genuinely worse in parallel is
  print-debugging several tests at once, where output interleaves.
  `--dist loadfile` is load-bearing, not tuning: it keeps every test in
  a file on one worker, without which `tests/test_dashboard_e2e.py`'s
  session-scoped build fixture runs once per worker and several workers
  race to rewrite the same real `reports/` files (`plans/tooling.md`
  #10). CI
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
  **Amended again, 2026-09-18 evening (Keith's own explicit call): run selective
  tests locally for smaller/medium changes, rely on CI for the full
  suite.** For a change scoped to one or two modules, run just the
  directly affected test file(s) locally (e.g. `uv run pytest
  tests/test_changelog.py -q`), not the whole suite - then push and let
  `test.yml` report the full-suite result, same as the "don't block on
  CI" amendment above already established for waiting on it. Still run
  the full local suite (plus `ruff`/`npm test`) for a genuinely large
  or cross-cutting change, or when actually uncertain whether something
  distant broke - this is about not defaulting to the heaviest check
  for every change, not skipping real verification.
- **The full local `uv run pytest` run took a real, measured ~193s
  (346 tests) as of 2026-09-18 evening - up from the ~2min/302-test
  figure recorded earlier the same day - not because the suite grew
  meaningfully, but because of a real, since-fixed performance bug.**
  `qa_tools/common/changelog.py`'s `_committed_at_by_run_timestamp()`
  (walked by `dashboard/embed_dashboard_data.py`'s `embed()`, which
  several tests exercise - `test_embed_dashboard_data.py`,
  `test_dashboard_e2e.py`'s `TestBuiltDashboardRenders`/`TestTicketBadge`)
  used to spawn one `git show <sha>` subprocess PER commit that ever
  touched a dataset's `qa_results/` subtree, diffing that commit's
  ENTIRE changed tree - real cost that scales with both commit COUNT
  and DIFF SIZE, and both grew a lot the same day this was found
  (several qa_results/ regeneration commits touching 80-900+ files
  each, mostly full-file rewrites). Measured before the fix: ~13s for
  Birth Registrations' own 12 commits alone, 225MB/5.3M lines of raw
  diff output. Fixed two ways: one `git log -p` call instead of N
  `git show` calls, AND narrowing the pathspec to `dataset_stats.json`
  files specifically - the only file this function (or its caller)
  ever actually reads, so excluding the real, verbose dbt.json/soda.json
  tool output (the bulk of the diff volume) is what did most of the
  work - measured after: 0.7s, 1.7MB/56K lines, a ~13x reduction on
  that one call; full local suite back down to ~122s/346 tests after
  the fix, in line with the earlier ~2min baseline. The STANDING
  lesson: this class of "walk real git history" logic scales with real
  repo growth, not just row/run counts - a real `pytest --durations=30`
  profile is the way to find where new growth actually went, the same
  diagnostic step that caught it here, not a guess.
  **Standing practice, 2026-09-18 evening (Keith's own explicit ask):
  keep an eye on this going forward, informally - report back if
  runtime has grown noticeably since the last time it was checked, the
  same way this entry itself does. Deliberately NOT a CI-enforced gate
  (unlike `pytest-cov`'s real, measured coverage threshold) - Keith's
  own words: "no need to put it into CI or anything." A rough running
  log of full-suite `uv run pytest` timings, newest last, so "has this
  grown" has a real number to compare against rather than a vague
  feeling: ~2m43s/163 tests (pre-2026-09-18) -> ~2min/302 tests
  (2026-09-18 morning, after `test_generate_runs.py`'s own fixture
  consolidation) -> ~193s/346 tests (2026-09-18 evening, the git-walk
  bug above) -> ~122s/346 tests (2026-09-18 evening, after that fix)
  -> ~59s/411 tests (2026-09-18 night, `pytest-xdist` `-n 4` - see
  `plans/running-thoughts.md` #12's own real fix/verification account;
  plain serial `uv run pytest` is still ~122s-equivalent at today's test
  count, `-n auto` is the fast path, not the new default - see that
  item for why) -> **~220s/649 tests serial (2026-09-19 evening,
  item 74's fix)**. The suite has grown ~58% in test count since the
  last entry, and that's most of the runtime growth - nothing pointed
  at a new hot spot this time. Two real, environment-only gotchas hit
  on a genuinely fresh sandbox during that run, both worth knowing
  before reading a red result as a code problem: the documented
  one-time `uv run dbt deps ...` step had never been run here (8 real
  dbt test failures until it was), and `PLAYWRIGHT_CHROMIUM_PATH=/opt/
  pw-browsers/chromium` was needed for the e2e module (16 errors until
  it was set). Neither is a code fault; both are one-line fixes.
  -> **~83s/653 tests (2026-09-19 evening, parallel now the default)**.
  The race that used to make `-n auto` unreliable for a full-suite pass
  is fixed (`plans/tooling.md` #10 - two of them, actually: the embed
  tests reading real `reports/` build artifacts mid-rewrite, and the
  e2e build fixture running once per worker), so this number is a
  like-for-like replacement of the 220s serial one above, not an
  optimistic best case. The real CI coverage command
  (`--cov=qa_tools --cov=pipeline --cov=generator --cov=dashboard`)
  passes at 94.76%, comfortably over the 92% floor.
  -> **~81s/673 tests (2026-09-19 late evening)**. Flat against the
  previous entry despite 20 more tests - no new hot spot.
  -> **~83s/680 tests (2026-09-20 morning)**. Flat again.
  -> **~84s/695 tests (2026-09-20 midday)**. Flat again, 15 more tests.
  -> **~85s/719 tests (2026-09-20 afternoon, REQ-QAC-023)**. Flat again.
  -> **~86s/754 tests (2026-09-20 afternoon, REQ-DOCS-029/REQ-TEST-030)**.
  Flat again, 35 more tests.
  -> **~85s/772 tests (2026-09-20 evening, REQ-QAC-024's authoring-rules
  doc and failure_indicates gate)**. Flat again. Worth knowing for the next fresh sandbox: the run
  before this one reported 20 failures across `test_run_dbt_*`,
  `test_cli_*` and `test_orchestrate_single_run.py`, all from the
  documented missing `dbt deps` step rather than any code fault - more
  than the "8 real tests fail" this file records elsewhere, and the
  symptom is a `FileNotFoundError` on a dbt `manifest.json`, which does
  not name `dbt_utils` anywhere. Check `dbt_project/dbt_packages/`
  exists before reading that shape of failure as a regression.
  -> **~87s/792 tests (2026-09-20 evening, the requirements sign-off
  gate)**. Flat again, 20 more tests.
  -> **~97s/809 tests (2026-09-20 evening, REQ-DASH-026)**. Up ~10s on
  17 more tests - the new ones are all real-browser e2e, which cost far
  more per test than the rest of the suite. No new hot spot.
  -> **~91s/812 tests (2026-09-20 evening, the detail-panel authored-text
  fix)**. Flat.
  -> **~96s/833 tests (2026-09-20 night, REQ-GHUB-027)**. Flat, 21 more
  tests.
  -> **~98s/839 tests (2026-09-20 night, REQ-DASH-033)**. Flat.
  -> **~154s/1048 tests (2026-09-23, REQ-GEN-043)**. Up ~56s on 209
  more tests, and that is where the growth went - no new hot spot.
  Worth knowing for the next fresh sandbox: the test count has grown
  ~25% in three days across the supply-model sprints.
  -> **~149s/1114 tests (2026-09-23, REQ-PIPE-050)**. Flat against the
  previous entry despite 66 more tests.
  -> **~149s/1154 tests (2026-09-23, REQ-PIPE-051/052)**. Flat again,
  40 more tests.
  -> **~153s/1185 tests (2026-09-23, REQ-PIPE-053)**. Flat again, 31
  more tests - eleven of them real-browser e2e, which usually shows.
  JS suite 183 tests in ~13s.
  -> **~148s/1217 tests (2026-09-23, REQ-QAC-047)**. Flat again, 32
  more tests. JS suite 218 tests in ~15s.
  Whenever a full local run happens anyway (not a reason to run one
  that selective testing above would otherwise skip), note the real
  number here.
- **Never report a test result you did not just run.** Real incident,
  2026-09-20: a commit message claimed "npm test 140 passed" when that
  run had actually been 2 failed | 138 passed. Nothing was fabricated
  deliberately - an earlier, genuinely-green result was reused after
  further changes had landed, which is the same thing as far as the
  record is concerned. Caught only by going back, checking out that
  commit's own files and re-running. A false green in a commit message
  is worse than a red one: it is durable, it is the thing a future
  session trusts instead of re-running, and nothing in CI ever checks
  it. So the rule is mechanical rather than a matter of care - if a
  number is going into a commit message, a requirement's `evidence:`,
  or a report to Keith, it comes from a run that happened AFTER the
  last change, not from earlier in the session. Same family as the CI
  bullet above: the failure mode is assuming a result still holds
  rather than confirming it does.

  **The clock is the same rule, and broke the same way the same day.**
  A session checked `TZ=Australia/Perth date` once at 15:12, then spent
  the next several hours estimating the time from how much work had
  happened instead of looking again - 5:40pm, 6:05pm, 7:10pm, "coming
  up on 8pm" - and was over three hours out when Keith asked. It had
  nudged him to stop working for the evening at what was actually
  quarter to five.

  This is worse than being wrong about the hour. The evening nudge a
  few sections above exists because Keith asked for it, and a nudge
  fired off an invented clock is one he learns to ignore - which costs
  the real nudge later. Same for any date-sensitive write: a
  `CHANGELOG.yaml` date or a `plans/*.md` entry stamped from a
  remembered reading is wrong in a file, not just in a sentence.

  So: **run the command, every time the answer matters.** Not once a
  session, not when it feels like it might have got late - at each
  natural pause, and always before saying a time out loud, nudging
  about the hour, or writing a date into a file. It costs one command.
  Estimating it from elapsed work feels reasonable and is exactly the
  reasoning that produced a three-hour error.

- **In a fresh session, do the environment setup UP FRONT - before
  running any test suite - rather than discovering what's missing from
  test failures.** Keith's own explicit ask, 2026-09-19, after watching
  a session run the full suite first, get 8 dbt failures and 16
  Playwright errors, and only then work backwards to the cause - all of
  which this file already documented. Every remote session starts from
  a freshly-cloned container with none of the gitignored build
  artifacts present, so assume they're missing rather than checking
  after the fact. The three, all one-liners:
  - `uv run dbt deps --project-dir dbt_project --profiles-dir
    qa_tools/dbt_profiles` (installs `dbt_utils`, whose macros several
    real dbt checks need - without it 8 real tests fail)
  - `npm ci` (without it `npm test` won't start at all)
  - `uv run playwright install chromium`, or in this sandbox
    `export PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium` (the
    pre-installed build lags what the pinned package expects)

  **The same fact cuts the other way for TESTS, and it produced a real
  red CI on 2026-09-23**: a freshly-cloned container has no `data/`
  either, so a test that ASSERTS a gitignored path exists passes
  locally and fails in CI, every time. Two generator-isolation tests
  did exactly that - `assert before["deliveries"], "test precondition -
  the real delivery tree must exist"` - and were green locally for the
  same reason they were red on the runner. Write the assertion so it
  holds whether or not the artifact happens to be there: an untouched
  ABSENT tree is still untouched, and a generator writing to its
  defaults would bring one into existence, which a before/after
  comparison catches either way. Verified by reproducing the CI
  condition locally - move the gitignored tree aside, run the test -
  which is the cheapest way to check this class before pushing.

  Two things worth knowing so this doesn't get mis-diagnosed next time:
  **CI is not affected** - `.github/workflows/test.yml` runs all three
  as real steps, so a red local suite with a green CI almost certainly
  means local setup, not a regression. And a failure in any of those
  areas is not evidence of a code fault until setup has actually been
  done. Automating this properly (a `.claude/settings.json` SessionStart
  hook) is scoped as `plans/tooling.md` #11 - until it exists, this
  bullet is the process fix.
- **`requirements.yaml` is the permanent artifact. `plans/*.md` is
  working material that gets deleted as its requirements land.** Keith's
  own framing, confirmed as a standing rule 2026-09-20 ("requirements
  are the permanent artifact... and then the plan file entries get
  deleted as we go"), and it applies whether or not the `delivery-*`
  subagents were used. This is a real inversion of how this project
  worked until now - the plans files used to BE the memory - so read
  it as replacing, not supplementing, any older guidance that treats a
  `plans/*.md` write-up as the durable record. Two obligations, both
  non-optional:
  1. **Emit requirements.** Build work that ships behaviour adds or
     updates real `requirements.yaml` entries - with `acceptance_criteria`,
     and, once `status` is `built`, `linked_tests`, `implemented_by`,
     `evidence` and `decisions` (all four CI-enforced). Not a plans note
     that says what was built.
  2. **Delete what it supersedes.** Any `plans/*.md` prose the new
     requirements now cover comes OUT of the plans file in that same
     change. Not archived to another file, not left tagged `done`.
     The point is to stop accumulating a growing corpus of requirements
     *plus* vague high-level plan thoughts describing the same thing, where
     the two can disagree and nothing says which wins.

  **Is deleting safe? Yes - but only because `decisions:` exists.**
  Keith raised this directly ("we can always reconstruct them from Git
  history, I guess. Does that seem safe?"). Git does hold every deleted
  word permanently on a public remote, so nothing is lost. But the
  failure this project has already hit is not "the text is gone", it is
  "nobody knew to go looking" - the third `plans/INDEX.md` proof
  (`plans/tooling.md` #17) watched an agent miss a decision sitting one
  level below what it read, recovering only by luck. Finding deleted
  prose needs `git log -S"<phrase>"` with a phrase you must already
  suspect, which is nothing like grepping a live file.

  His own answer to that, the same conversation, and it is the thing
  that makes this work: **`requirements.yaml`'s `decisions:` field** -
  short items recording what was decided and what was rejected, "our
  collective memory of the thinking that went into that requirement, so
  it doesn't have to be taken back out of git history or kept in a
  massive plan file." Required once a requirement is `built`, CI-gated,
  no exceptions.

  So the rule when deleting is concrete rather than a matter of care:
  **read the write-up and move anything it knows that the requirement
  does not into `decisions:` BEFORE the prose goes.** A requirement
  holds what the system shall do; a `done` write-up routinely holds why
  a different approach was rejected, which is exactly what gets
  re-derived otherwise - `CLAUDE.md`'s own reason for the
  read-everything rule is "don't re-derive a decision that's already
  recorded there". If a decision only exists in the prose, deleting the
  prose deletes it in practice even though git has the bytes. Deleting
  is cheap to do and expensive to notice you got wrong.

  **WHEN, mechanically: the deletion goes in the commit that flips a
  requirement to `built`.** Not the next commit, not a sweep at the end
  of the day. If that commit does not either remove prose or say in one
  line why there was none, the rule has been broken - which is a thing
  to check before committing, like `ruff`, not a thing to intend.

  **The reason this got skipped, and it will recur, so recognise the
  shape.** A plans entry is very often `done` AND still carrying live
  items - a follow-up fork, a tidy-up, an open question. That makes
  "delete the superseded prose" not a clean operation on a whole entry,
  and the friction is enough to turn it into "later". Real incident,
  2026-09-20: five requirements shipped in one day and not one plans
  entry came out with them; caught only because Keith asked directly.

  So a mixed entry is the NORMAL case, not an exception to postpone:

  1. Pull the live items out first - into the requirement's own
     `open_questions:`, or into a new plans entry of their own, or into
     a new requirement if they are real work. A fork sitting in the last
     paragraph of a `done` write-up is the single likeliest thing to be
     lost.
  2. Move what the prose knows that the requirement does not into
     `decisions:` - especially a rejected alternative.
  3. Then delete, and repoint every inbound reference at the requirement
     that now owns the decision. `grep` for the entry number; there are
     usually more than expected (11 for one pair of entries).

  **If a plans entry turns out to be the ONLY record of something real,
  that is a missing requirement, not a reason to keep the entry.** Write
  the requirement, then delete. Found this way on 2026-09-20: one `done`
  entry held both a live data-corruption bug affecting 166 of 352
  committed runs and an unbuilt design decision, neither of which any
  requirement mentioned. Deleting it as "done work, already shipped"
  would have destroyed the only account of both.

  Sequencing (Keith's own words, `plans/running-thoughts.md` #13):
  requirements first, deletion second, and the `CHANGELOG.yaml` rewrite as
  its own separate piece - that last one LANDED 2026-09-20 (REQ-DOCS-028). The back-catalogue of existing `done` items is
  a deliberate, separate job - this bullet governs NEW work from
  2026-09-20 on, so a change does not add to the pile while that is
  pending.

- **When a body of design work is scoped into requirements, carry the
  DECISIONS across at DRAFTING time, and delete the prose only when its
  last dependent batch is built.** Keith's own standing instruction,
  2026-09-22, and he was explicit that it governs how this works from
  here on, not just the piece of work that prompted it. It refines the
  bullet above rather than replacing it: that one says prose goes when
  a requirement is `built`, which assumes prose and requirement are
  roughly one-to-one. Once a large design file is scoped in BATCHES,
  they are not, and the assumption quietly destroys things.

  **What goes wrong without this.** A thread of design prose routinely
  feeds several batches - in the work that prompted this, one thread
  fed three. Delete it when the first batch is built and the second
  batch loses its source before anyone has scoped it. Meanwhile the
  requirements drafted from that thread carry only what the drafter
  happened to read, so a decision sitting two paragraphs below the
  sprint line is in neither place. Nothing fails; the decision just
  stops existing outside git.

  Four rules, and the third is the one that actually prevents the loss:
  1. **The scoper gets the SOURCE THREADS, not just the sprint lines.**
     A sprint entry is two sentences; the decision behind it is two
     paragraphs elsewhere. A scoper given only the sprint cannot write
     a requirement that carries what the thread knows.
  2. **`decisions:` is required at DRAFT time**, not from `built`. CI
     only enforces it at `built`, which is too late when the prose may
     be gone by then. Rejected alternatives count, and are the part
     most likely to be re-proposed if lost.
  3. **A mechanical carry-over check per batch.** When a batch comes
     back, walk its source threads and list every decision no drafted
     requirement carries. Each one either goes into a requirement or
     gets an explicit "not needed, because". The batch is not finished
     with the scoper until that list is empty. Mechanical like `ruff`,
     not a matter of care - the failure mode here is always "nobody
     knew to look", never "somebody was careless".
  4. **Delete a thread WHOLE, once its last dependent batch is built** -
     Keith's own choice, 2026-09-22, over deleting each decision as its
     requirement is signed off. A half-deleted thread is worse than
     either end state: it reads as complete while being full of holes,
     and nothing marks where the holes are. The delay is safe precisely
     because rule 3 has already established that nothing lives only in
     the prose.

- **No building begins on a requirement until Keith has signed it off.**
  His own standing instruction, 2026-09-20. A requirement existing in
  `requirements.yaml` is not the same as a requirement he has agreed to
  - drafting one, whether by hand or via `delivery-scoper`, produces a
  PROPOSAL.

  **What sign-off looks like**: present the requirement to him in prose
  he can react to - the story, the acceptance criteria, the non-
  functional constraints, and any open questions - not a YAML dump. He
  gives input, criteria change, and he says yes. Then building starts.
  Unresolved `open_questions:` are a particular signal: if one of them
  would change what gets built, it is not ready to build.

  **This applies whether or not the `delivery-*` agents were used.** The
  gate is on the requirement, not on which route produced it, and the
  route that skips the agents is the one most likely to skip the gate
  too.

  **Why it exists, from the day it was written.** Three requirements
  were built without anyone reading them. `REQ-QAC-024` and
  `REQ-QAC-025` were built from `plans/running-thoughts.md` notes, and
  only afterwards turned out to have had requirements specifying them
  all along - `REQ-QAC-025` had seven acceptance criteria, of which the
  build met five, and one of the two it missed was a criterion actively
  decided against without being read ("apply these rules to retired
  checks on the same terms as active ones"). `REQ-DASH-026` was worse:
  the work went the OPPOSITE way to a criterion, deleting information
  the requirement asked to have demoted rather than removed.

  That is the failure this closes, and note what it is NOT - none of it
  was a disagreement about what to build. It was building without
  looking, which a sign-off step makes structurally impossible because
  the requirement has to be read aloud to be signed.

- **Never change an authoring standard without Keith's explicit
  approval - propose the exact wording, get a yes, then edit.** His own
  standing instruction, 2026-09-20. It covers two files:
  `docs/check-authoring-rules.md` (how a check's three prose fields are
  written) and `CHANGELOG.yaml`'s own header (how a release note is
  written). Adding a rule, removing one, renumbering, or rewriting one
  to mean something slightly different are all the same act.

  **Approval of the substance is not approval of the wording.** The
  distinction is the point of the rule rather than pedantry: these are
  standards that hundreds of hand-authored texts get held against, and
  a clause that reads one way to the person who agreed it and another
  way to the session applying it across 257 checks is exactly how a
  corpus ends up consistent with the wrong thing. It happened the day
  this rule was written - a fork was settled in conversation, the rules
  were edited to match, and the edit turned out to carry a reading
  nobody had signed off on.

  Writing a check's prose, or a changelog entry, is ordinary work and
  needs none of this. Only the rules themselves are gated.

- **A push that ships anything release-note-worthy gets a `CHANGELOG.yaml`
  entry in the SAME push, not backfilled later.** Rewritten 2026-09-20
  (REQ-DOCS-028) when the hand-written Markdown `CHANGELOG.md` was
  replaced by structured YAML. The standing hold that sat here pending
  that conversation is gone; this is the rule that resumed.

  **How to write one is deliberately not here.** `CHANGELOG.yaml`'s own
  header carries that standard in full - voice, the measured length
  targets, structure - and it is the single copy on purpose (Keith,
  2026-09-20; the reasoning is on `REQ-DOCS-028`). This bullet covers
  only WHETHER and WHEN, which is genuinely this file's job.

  **The bar** is a real feature, fix, or architectural change to the PoC
  itself - the whole repo's real history, not dashboard-features-only.
  Curated prose, not a mechanical commit dump, so not every commit needs
  one: a `plans/*.md` update, a wording tweak, or this file's own
  conventions don't, and those belong in the relevant `plans/*.md` file
  instead.

  **The timing** is a real step, not something to remember when
  reminded: before every commit that isn't purely `plans/*.md`/
  process-only, ask "does this meet the bar", the same way `pytest`/
  `ruff` already are. Real incident, 2026-09-18: a full day of Phase 6/7
  work (test coverage, the resupply-chain redesign, two real CI fixes)
  shipped with zero changelog entries, caught only when Keith asked for
  them directly - the STANDING fix is this bullet, not that one-off
  backfill. If the scope seems genuinely unclear for a specific change,
  ask him rather than guessing either way (including something too
  granular, or skipping something real).
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
- **When you change the SHAPE of a value (making it nullable, adding a
  field, changing what's authoritative), enumerate every consumer
  mechanically, and verify at the LAST transform before the user - not
  the first one after the source.** Added 2026-09-19 after a real,
  instructive incident (`plans/qa-pipeline.md` item 74): making a
  check's warn/fail threshold nullable left two readers behind. One
  (`qa_tools/common/dataset_status.py`, the Python mirror of the
  dashboard's status logic) raised a real `TypeError` in CI. The other
  (`buildRealDataset()` in the template) silently dropped the new
  authoritative field and fell back to threshold math, rendering a check
  with 14 real violations GREEN - a false green, the dangerous
  direction, introduced by the very fix written to prevent it.
  Both hid for the same reason: the change was verified by reading
  `reports/*.json` and applying the new rule in a throwaway script.
  That proved the DATA layer and nothing else - two transforms sat
  downstream, untouched. **A green data layer says nothing about a
  render layer that has its own transform.** Concretely:
  - `grep` for every consumer before declaring a shape change done. Note
    that a value can have more implementations than expected - that
    incident turned up FOUR status implementations (JS, two Python, plus
    a dead one), not the two that were known about.
  - Assert at the layer a human actually sees. `tests/
    test_dashboard_e2e.py`'s own `TestStatusMatchesEachToolsOwnVerdict`
    is the worked example: it drives the real built dashboard in a real
    browser, uses the PAGE's own functions, and compares ~30k statuses
    against the verdicts the real tools recorded. It runs in seconds and
    catches exactly this class of bug - verified by reintroducing the
    real bug and confirming it fails with a diagnostic message.
  - Prefer a shape that fails loudly over one that fails silently. A
    hand-maintained allowlist of copied fields drops new fields in
    silence; spread-then-override carries them by default. Same
    reasoning as this file's own "no permissive fallback" stance
    elsewhere.
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
  Pages hosting depends on that; see `plans/dashboard.md` #2 for the
  parked note about what happens if/when it goes private again.
- When a design decision has real forks (not just implementation
  detail), scope it with Keith via a couple of rounds of clarifying
  questions before building - this has been the working pattern all
  along, not a one-off. Bias toward proceeding once the real forks are
  resolved; don't re-ask what's already been answered.
- Commit and push to whatever branch the session was told to develop
  on; don't create a PR unless explicitly asked.
- **When a real outbound network request gets blocked by this session's
  own egress policy (a 403/407 from the agent proxy - see `curl -sS
  "$HTTPS_PROXY/__agentproxy/status"`'s own `recentRelayFailures`), flag
  the exact blocked domain in this file** (a new bullet here, or append
  to this one) so Keith can decide whether to allow-list it for future
  sessions - his own explicit ask, 2026-09-19, after a session couldn't
  reach `keithamoss.github.io` (GitHub Pages, this project's own live
  dashboard) to verify a real production issue directly and had to
  reason from GitHub Actions logs instead. Report it, don't route around
  it or silently give up on the task - same "report the blocked host,
  never retry or route around it" rule `/root/.ccr/README.md` already
  states for this proxy generally, just with a durable place to land so
  it survives past the one session that hit it. Not every transient
  proxy failure needs an entry (a one-off Chromium captive-portal ping
  to `www.google.com` during a Playwright browser launch is noise, not
  a real blocked need) - only a domain this project's own real work
  genuinely needed and couldn't reach.
  **Audited in full 2026-09-19 evening (Keith's own ask, after he
  allow-listed several more).** Every domain below was re-tested with a
  raw `curl`, not `WebFetch` - per the standing lesson at the end of
  this bullet. A `403` here means a real `curl: (56) CONNECT tunnel
  failed, response 403` from the proxy, which is unambiguous; a `200`
  means the real page came back, confirmed by reading its actual
  `<title>` rather than just the status code.

  **Still genuinely blocked** (re-confirmed 2026-09-19, all `403`):
  - **`www.anthropic.com`** - Anthropic's own published multi-agent
    design guidance ("Building Effective Agents", the multi-agent
    research system writeup), wanted for the `delivery-*` subagent work
    (`plans/wider.md` #10). Note bare `anthropic.com` is NOT separately
    reachable: it returns a real 301 to `www.anthropic.com`, which is
    the blocked host, so the redirect is not a way around it.
    `code.claude.com` (Claude Code's own docs) remains reachable and
    needs no workaround.
  - **`skills.lc`** - a design-review skill writeup, wanted for the
    UX-reviewer-agent precedent research.
  - **`patch-diff.githubusercontent.com`** - `cfisch3r/estimate` PR
    #91's real `.diff`. Never actually blocked the work: the real file
    paths were found another way and fetched from
    `raw.githubusercontent.com` (reachable) instead.
  - **`snyk.io`** - the "Top 8 Claude Skills for UI/UX Engineers"
    article Keith found himself. A `translate.goog` proxy mirror exists
    and was deliberately NOT used - routing around a block is a
    different thing from picking a different legitimate primary URL.
  - **`clig.dev`** - the CLI guidelines, used for the CLI/TUI UX work.
    Worked around legitimately via its own real GitHub source
    (`raw.githubusercontent.com/cli-guidelines/cli-guidelines/main/
    content/_index.md`) - same repo, same content, a real primary
    source rather than a bypass.

  **Now reachable** (allow-listed by Keith; kept here rather than
  deleted so a future session reading an old `plans/*.md` reference to
  "the blocked X" can see it has since been resolved):
  - **`docs.github.com`** - GitHub's own documentation. Blocked when
    hit 2026-09-22 fact-checking GitHub Actions concurrency/queueing
    semantics for the decision-log design (`plans/supply-model.md`
    Thread H) - a real `curl: (56) CONNECT tunnel failed, response
    403`, worked around legitimately at the time via the docs' own
    public source repository (`github/docs`, a shallow sparse clone of
    `content/actions` - same content, a real primary source rather
    than a bypass, and it additionally exposes the
    `data/features/*.yml` version gates the rendered site hides).
    Allow-listed by Keith the same day and re-verified with a real
    `curl` (200), so the clone workaround is no longer needed - this
    project reaches for GitHub docs often enough (Actions, Issues, the
    ticketing path) that cloning a large docs repo each time was a
    poor trade.
  - **`keithamoss.github.io`** - this project's own live published
    dashboard. Resolved 2026-09-19 evening, and immediately paid for
    itself: the deploy that had just gone out was verified directly
    against the real site rather than inferred from a workflow's own
    `success` conclusion - 30,561 rendered statuses compared against
    each tool's own recorded verdict inside the real page, zero
    disagreements, zero results missing a verdict
    (`plans/qa-pipeline.md` item 74). **Two real gotchas when driving
    it with Playwright**, both environmental rather than page bugs:
    the agent proxy's MITM certificate needs
    `browser.new_context(ignore_https_errors=True)` (the same option
    `scripts/dev/serve_dashboard_https.py`'s own work already
    established), and the ~8MB page intermittently fails the navigation
    outright with `net::ERR_TOO_MANY_RETRIES` through the proxy - it
    succeeded on one attempt and failed on the next with no change, and
    a plain `curl` of the same URL downloads all 8.2MB reliably. Retry,
    or fetch with `curl` and drive the local copy, rather than reading
    that error as a broken deploy.
  - **`www.codecentric.de`**, **`iamjeremie.me`** - the
    isolated-specification-testing post and a spec-pipeline write-up,
    both previously snippet-only for the requirements-analysis work.
  - **`lawsofux.com`**, **`www.nngroup.com`** - previously
    snippet-only for the HCI/psychology grounding
    (`docs/hci-ux-psychology.md`). Both now readable as primary
    sources, so that guide's own citations can be checked directly if
    it's ever revisited.
  - **`smart-interface-design-patterns.com`**, **`rakhman.info`**,
    **`developer.mozilla.org`**, **`web.dev`**, **`en.wikipedia.org`** -
    allow-listed earlier the same day for the SPA best-practice
    research; re-confirmed still reachable in this audit (MDN 302,
    Wikipedia 301, the rest 200).

  **Standing lesson, and the reason this whole list gets re-tested with
  `curl` rather than `WebFetch`**: when a domain is allow-listed
  mid-session, `WebFetch` can keep returning `EGRESS_BLOCKED` for it
  long after the proxy itself has started allowing it - a stale
  tool-level check out of sync with the live policy, the same
  "read once, doesn't update mid-session" class of problem this project
  has hit with `.mcp.json` and the `Agent` roster. Hit for real on all
  five SPA-research domains (2026-09-19): raw `curl` returned genuine
  200s/301/302 while `WebFetch` still refused. **So never treat a
  repeated `WebFetch` failure as proof a domain is still blocked** -
  verify with `curl` first, and if `WebFetch` still won't cooperate,
  fetch the raw HTML with `curl` and read it directly. Only a real
  `curl: (56) CONNECT tunnel failed, response 403` is evidence of an
  actual block.

- **Periodically check the `.claude/agents/*.md` combined description-
  field token budget** (2026-09-19, Keith's own ask - make this a
  standing periodic check, same treatment as the pytest-runtime log
  below). Claude Code warns at startup once combined subagent
  descriptions (all non-built-in agents) exceed 15,000 tokens - the
  `description:` field specifically, not the whole file, since only
  that field loads for every session regardless of whether the agent
  runs. Checked 2026-09-19: 6 real agents, ~4,450 characters combined
  across just the `description:` fields (~1,100 tokens at a rough
  4-chars/token estimate) - nowhere near the limit. Re-check whenever a
  new agent is added or an existing one's description grows
  substantially, not on a fixed schedule. Re-checked 2026-09-19 evening
  after adding `delivery-cli-ux`/`delivery-cli-ux-critic`: 8
  real agents, ~6,420 characters (~1,600 tokens) - still nowhere near
  the limit.
- **Claude Code supports overriding a subagent's own default `model:`
  at spawn time**, via plain language in the request itself (e.g. "use
  the security-reviewer subagent with Opus to examine this module") -
  the named model takes precedence over the agent file's own `model:`
  frontmatter for that one invocation. Keith's own ask, 2026-09-19: a
  good thing to actually remember and use, not just know about -
  worth proactively suggesting when a specific run of one of this
  project's own `requirements-*` agents would benefit from a deeper
  (or, for something trivial, cheaper/faster) pass than its own default
  model, rather than only ever using each agent's file-defined default.
