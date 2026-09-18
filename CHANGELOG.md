# Changelog

What changed about this PoC itself over time - new features, fixes, and
architectural decisions as they shipped. This is a curated summary of
the project's real git history, not a mechanical commit dump; see
`git log` for the full, unabridged record.

This is deliberately a different feed from two others already in the
dashboard: the header's "Recent activity" panel (who ran/published QA
against which dataset, when - drawn from `qa_results/` history) and a
check's own changelog inside its detail panel (that one check's
definition-change history). This page is about the tool itself.

Dates are real calendar dates this project has run on, not a synthetic
generation window - real Perth (AWST, UTC+8) calendar dates specifically,
since that's the timezone this project is actually worked in, not this
tool's own server-side UTC clock. Each entry also carries the real time
(same AWST clock) it actually shipped at, taken straight from its own
git commit history - entries within a date/category are sorted newest
first.

Each entry leads with a short, bold headline and one or more component
tags (the same 7-part taxonomy `plans/*.md` items use) - shown in the
dashboard's own Release Notes panel with a matching icon per component.
The text stays real and technical (module names, real numbers), just
edited for a punchier, friendlier read than a bare commit log.

## 2026-09-19

### Added
- **12:30am** — **AWS Event-Driven MVP Design** **[Pipeline & publishing]** **[Docs & process]** A real design doc plus real, unit-tested code for
  triggering this pipeline automatically from S3 file arrivals instead
  of a manually-kicked-off local script (`docs/aws-event-driven-mvp-
  design.md`) - built overnight per Keith's own explicit instruction,
  for his morning review, not yet deployed (no real AWS access exists
  in this environment). Covers file-arrival pattern matching for
  individually-arriving, nested-folder, and zip-archive files; Child
  Protection's explicit-completion-signal design for waiting on all 6
  tables before running cross-table checks; new single-arrival
  orchestration entry points (`orchestrate_bdm.run_single()`/
  `orchestrate_cp.run_single()`) that reuse the existing 4-real-tool
  evaluation logic unchanged; and a clearly-flagged recommendation (not
  a silent decision) on how a Lambda-produced result reaches the
  committed `qa_results/` git history without Lambda ever holding
  git-write credentials. Two real architectural gaps surfaced and got
  fixed while writing the integration tests against the real local dbt/
  Soda/datacontract-cli/Evidently chain - see the design doc's own "Two
  more real gaps found while actually building this" section. AWS CDK
  (Python) infra and both Lambda handlers are real, reviewed code,
  written correctly per their respective documented APIs but genuinely
  unverified - never `cdk synth`'d, never invoked by a real S3 event.

## 2026-09-18

### Added
- **11:44pm** — **Parallel Test Runs** **[Testing & dev tooling]** `pytest-xdist` adopted for a real, measured ~2x faster full local test
  run (`uv run pytest -n auto` - ~59s vs ~122s serial on a 4-core
  machine), not just installed on faith. Found and fixed a real bug
  along the way: two dbt-based integration tests shared a literal run
  id that mapped to dbt's own shared `dbt_project/target/` output
  directory - safe only because tests ran one at a time before, and a
  genuine collision once run in parallel (reproduced directly, not
  assumed). Fixed by co-locating each run's dbt scratch output with its
  own DuckDB file instead of a fixed, repo-shared path - a small
  production improvement in its own right, not just a test workaround.
  Plain `uv run pytest` stays serial by default for easier single-test
  debugging.
- **11:25pm** — **Plans Tab** **[Dashboard UI]** **[Docs & process]** A real "Plans" page inside the dashboard - browse, search, and filter this
  project's own `plans/*.md` planning memory (status/component tags on
  every item and Thread) without leaving the live site. A genuinely new
  top-level page, not another header side-panel - the real content
  volume (124 entries) needed room a cramped drawer couldn't give it.
  Every plan-file item and Thread/Phase section now carries a closed
  status and the same component taxonomy `CHANGELOG.md` entries do,
  fixing 17 items that had quietly slipped through an earlier retrofit
  pass with no real date.
- **11:07pm** — **Friendlier Release Notes** **[Dashboard UI]** **[Docs & process]** Every entry on this page now leads with a bold headline, an icon, and
  the real component(s) it touches - not just a wall of technical
  prose. All 46 prior entries retrofitted to the new format (a full
  rewrite, not forward-only), same as the `plans/*.md` status/component
  tagging done earlier tonight - one consistent tagging scheme across
  both of this project's history feeds.
- **9:12pm** — **Leaderboard Launch** **[Dashboard UI]** **[GitHub workflow & people]** A real leaderboard: whoever's kept a dataset out of the red the
  longest, per dataset, gets a real streak count (amber doesn't break
  it, only a real red run does). Shows real people by name once added
  to `contract/people.yaml` - a bare email is never shown on this
  public page.
- **8:51pm** — **Dataset Ownership** **[GitHub workflow & people]** A real people/roles config: GitHub tickets now get assigned to
  whoever's actually responsible for that dataset (or its whole
  agency, as a fallback) once real people are added, and the dashboard
  shows an "Owned by" badge on the agency/dataset pages. Ships with no
  real people in it yet - a config for Keith to fill in, not guessed.
- **8:39pm** — **Amber Acceptance** **[GitHub workflow & people]** A real way to accept an amber supply: commenting `/accept` on that
  dataset's own GitHub QA ticket now records a real acknowledgment
  against the exact supply that was current at the time - no ID to
  type or copy. The supply itself stays amber (accepting never
  silently reads as green); a small badge shows who accepted it,
  linking to the real comment. An amber-only dataset now gets a real
  ticket too, not just a red one. Publishes within roughly a minute or
  two of the comment, not the next unrelated push.
- **8:11pm** — **GitHub Deep Links** **[GitHub workflow & people]** **[Dashboard UI]** Real deep links from the dashboard back into GitHub: clicking a check
  now opens its actual source (the real dbt test/Soda check/datacontract
  rule/Evidently preset that defines it, at the exact line), and clicking
  a dataset or agency opens its real QA code folder - both pinned to the
  exact commit the dashboard was built from, so a link always shows
  exactly what was true when that page was published.
- **8:00pm** — **Readable URLs** **[Dashboard UI]** Human-readable dashboard URLs: the address bar now shows a real path
  (`#/agency/.../dataset/.../column/.../check/...`) instead of an opaque
  block of URL-encoded JSON - every drill-down level, the 4 header side
  panels, and the check-comparison picker are all genuinely shareable
  links now, not just the top-level page.
- **6:52pm** — **CP Resupply Sim** **[Data generation]** Real resupply-chain simulation for Child Protection: a red quarterly
  delivery now gets a real, later resupply attempt (a genuinely slower
  turnaround than Birth Registrations' own daily-feed curve - a full
  collection re-extract realistically takes longer to correct), the
  same chain-orchestration engine Birth Registrations already uses,
  generalized to a whole delivery's worth of tables at once rather than
  a single file. Visible in the live dashboard's supply-history view
  with no changes to that view at all - it already derived chains
  purely from real, observable status, dataset-agnostic by design.
- **1:02pm** — **Timestamped Notes** **[Docs & process]** A real timestamp against every entry on this page (real AWST
  git-commit time, never fabricated), sorted newest-first within each
  date's own category - also shown in the dashboard's own Release
  Notes panel, not just this markdown file.
- **12:24pm** — **Ticketing MVP** **[GitHub workflow & people]** A GitHub Issues ticketing MVP: a new, separate write-permitted
  workflow that opens a real GitHub Issue per real dataset (birth
  registrations, and each of Child Protection's six real tables
  separately) the moment that dataset's worst-of-every-check status
  goes red, and keeps commenting with its live status on every
  subsequent run - still red, or resolved - without ever auto-closing
  the ticket, since closing stays a human decision. Runs automatically
  on every relevant push - confirmed live: all seven real tickets
  opened for real once turned on, each reflecting a genuine finding
  (a real sibling-record mismatch for Birth Registrations, a real
  dirty synthetic delivery for Child Protection's six tables), not a
  false alarm.
- **11:23am** — **Ticket Badge** **[GitHub workflow & people]** **[Dashboard UI]** A small badge on each dataset's own tile linking straight to its
  real, currently-open GitHub Issue (when one exists) - embedded at
  dashboard build time from a real, read-only GitHub API call, same
  treatment every other embedded feed on the page already gets.
- **8:15am** — **Requirements Register** **[Docs & process]** **[Testing & dev tooling]** A live requirements register: real user stories with MoSCoW priority
  and implementation status, each one's completion backed by a real,
  CI-enforced link to the test that actually verifies it - a claimed
  "built" requirement with no real test behind it now fails CI, not
  just a documentation exercise.
- **7:45am** — **Supply Status Rollup** **[Dashboard UI]** A real aggregate red/amber/green status shown against every entry in
  a dataset's supply history - the worst status among every check
  across every column for that specific delivery - and a genuine "N
  days since the previous supply" counter on resupply attempts.
- **12:58am** — **Test Coverage Push** **[Testing & dev tooling]** Full integration test coverage against all four real QA tools, a unit
  test suite for the dashboard's own inline JavaScript, and real-browser
  end-to-end tests (as-of date picking, supply-history drill-down, dark
  mode) - plus a measured code-coverage floor now enforced on every
  push, not just a speed-focused smoke-test suite.

### Fixed
- **7:37pm** — **Test Isolation Fix** **[Testing & dev tooling]** The BDM/CP generator test suites shared their output directory with real
  production data: running `tests/test_generate_runs.py`/`tests/
  test_generate_cp_runs.py` wrote straight into `data/raw/`/`data/
  cp_raw/`, the same directories `./run_pipeline.sh` and the real
  orchestrators read from and write to - harmless in outcome (generation
  is fully deterministic) but a real coupling between test execution and
  production state that shouldn't have existed. Both test files now
  point the generator at an isolated temp directory for the duration of
  the run.
- **7:22pm** — **Changelog Speedup** **[Pipeline & publishing]** A real git-history-walking performance bug: building the "who
  published QA results, when" changelog feed used to spawn one real
  `git show` subprocess per commit that ever touched a dataset's
  `qa_results/` history, diffing that commit's entire changed tree -
  cost that grew with real repo history, measured at several seconds
  and a real, noticeable chunk of the test suite's own runtime once
  enough of that history had built up. Down to a fraction of a second.
- **12:24pm** — **Ticket Labels Fix** **[GitHub workflow & people]** The GitHub Issues ticketing MVP's very first live run: opening a
  ticket needs its labels to already exist on the repo, which neither
  did yet - now created automatically the first time they're needed.
- **12:16pm** — **Threshold Bugs Fixed** **[QA checks & contract]** Two real threshold-encoding bugs behind the dashboard's red/amber/
  green status: a check with no fail threshold configured used to
  silently read as failing almost every run (a missing threshold
  defaulted to zero rather than "can't fail"), and a handful of real
  contract rules with a genuine non-zero tolerance had that real
  threshold discarded entirely.
- **12:16pm** — **Arrival Stats Fix** **[Pipeline & publishing]** A local build failure: re-running the real check tools without first
  refreshing the combined warehouse left one column's arrival stats
  looking up a run that wasn't there yet.
- **6:28am** — **CI Health Fixes** **[Testing & dev tooling]** Two real continuous-integration failures that had gone unnoticed for
  hours: GitHub's own runner resolving a newer Python version than this
  project had ever been tested against, and a missing one-time setup
  step for one of the real check tools.
- **6:12am** — **Resupply Grouping Fix** **[Dashboard UI]** A resupply-history grouping bug: a resupply landing weeks late used
  to get lumped in with an unrelated delivery that merely happened to
  arrive on the same calendar day.

### Changed
- **9:37pm** — **Leaderboard Redesign** **[Dashboard UI]** **[GitHub workflow & people]** Redesigned the leaderboard to celebrate resolving a dataset from red
  back to green, not just running QA on it - a real person's own streak
  of GitHub QA tickets closed in a row without being reopened, tracked
  via a real GitHub API call rather than committed QA-run history. The
  earlier "current not-red run streak" design (shipped 9:12pm the same
  day) had nothing left to credit once QA running itself becomes
  automated, since closing a ticket stays the one action in this system
  that's always a human decision.
- **7:08pm** — **CP Sim Calibration** **[Data generation]** Child Protection's resupply simulation, calibrated further: a dirty
  delivery now only fails 2-3 of its 6 real tables, not all of them,
  and the most recent delivery is no longer forced red - both random,
  same as every other delivery.
- **12:01pm** — **YAML Safety Net** **[Testing & dev tooling]** A real YAML syntax mistake in a hand-edited contract file went
  uncaught until the next tool run parsed it - a real `check-yaml`
  pre-commit check now catches this class of mistake at commit time.
- **7:45am** — **Resupply Chain Rework** **[QA checks & contract]** How a resupply chain gets identified: no longer inferred from
  internal bookkeeping about which delivery a resupply was "for," but
  derived purely from a delivery's real cadence-aware timing and each
  arrival's own real pass/fail outcome - closer to what could actually
  be observed from a real production feed, where a resupply never
  arrives labelled as such.

## 2026-09-17

### Added
- **8:23pm** — **Stale-Safe Drilldown** **[Dashboard UI]** Child Protection's dataset detail page now stays fully drillable even
  when its most recent supply falls outside the "as of" staleness
  window: real historical columns, checks, and trend charts stay
  browsable, just without misleading current-status colors.
- **7:33pm** — **Sparklines Everywhere** **[Dashboard UI]** Sparklines on the Tier 2 (agency dataset list) and Tier 3 (column
  grid) views, not just the Executive tier - then redesigned to show
  each tier's own aggregate failing-check RATE over time (not one
  arbitrarily-picked check's raw value, and not a raw count, which
  would stop being comparable the moment a check gets added or retired
  mid-history).
- **5:54pm** — **Trend Chart Markers** **[Dashboard UI]** Trend-chart gap and marker rework: a real visual split (with a small
  double-tick glyph) where a check's definition changed in a breaking
  way; a subtler marker where it changed non-breaking; a separate
  dashed connector for a run a check has no result for, distinct from
  either kind of definition change.
- **4:38pm** — **Dark Mode** **[Dashboard UI]** A dark mode toggle.
- **3:28pm** — **Check History Panel** **[Dashboard UI]** Changelog and plain-English description sections inside each check's
  own detail panel, alongside its existing trend chart and comparison
  view.
- **1:40pm** — **Retired Checks Toggle** **[Dashboard UI]** **[QA checks & contract]** A retired-checks toggle in the current-status view: a check that's
  been formally retired stays fully visible in its column's check list,
  behind a toggle, without ever being able to turn that column's status
  amber or red again.
- **9:14am** — **Activity Feed** **[Dashboard UI]** The Executive-tier "Recent activity" panel - a feed of who published
  QA results for which dataset, and when.
- **7:42am** — **As-Of Date Picker** **[Pipeline & publishing]** **[Dashboard UI]** The cadence-aware "as of" date picker: pick any date and see the
  data asset exactly as it stood then, with a staleness tolerance so
  an overdue dataset reads as "no data" rather than silently showing
  old data as current.

### Fixed
- **8:00pm** — **Freshness Check Fix** **[QA checks & contract]** The three `date_of_birth` freshness checks (dbt, Soda, datacontract-
  cli) that read permanently red - they were comparing against the real
  wall-clock date, which drifted further from this fixture's dates
  every day since it was last regenerated. Re-anchored to each run's
  own date instead, paired with a new occasional-staleness defect so
  the checks have something real to catch either way.
- **7:13pm** — **Snapshot Picker Fix** **[Dashboard UI]** The live dashboard's "past snapshots" picker, which had never
  actually shown a real snapshot on the published site - the archived
  snapshot files were there, the picker's own list of them just never
  made it into the deployed page.

### Changed
- **6:44pm** — **CP Cadence Re-Anchor** **[Data generation]** Child Protection's quarterly delivery cadence re-anchored to
  February/May/August/November.

## 2026-09-16

### Added
- **9:44pm** — **Publishing Architecture** **[Pipeline & publishing]** The whole publishing/history architecture this PoC now runs on: every
  real QA run's raw tool output committed to `qa_results/` as a
  permanent record; the dashboard rebuilt purely from that committed
  history, with no live database access required; a CI-gated publish
  pipeline (build, validate, deploy) with no manual local-publish path;
  and a permanent, globally-unique ID for every real check, so a
  check's history survives even once its definition changes or it's
  formally retired.
- **8:39am** — **Time-Travel Snapshots** **[Dashboard UI]** "Time travel" dashboard snapshots - a full, self-contained, gzip-
  archived copy of the dashboard taken at a point in time, openable
  years later with nothing but a browser - plus a picker panel, built
  into the live dashboard, for browsing past snapshots.
- **7:33am** — **Run Comparison View** **[Dashboard UI]** A status pill, a run-picker, and a real side-by-side run comparison
  added to the check-detail panel.

## 2026-09-15

### Added
- **9:10pm** — **Full Check Triplication** **[QA checks & contract]** Full triplication of the check battery: every check that a
  supporting tool can express, implemented in that tool - not just one
  or two illustrative examples per dimension.

### Fixed
- **10:22pm** — **dbt Failure-Count Bug** **[QA checks & contract]** A real dbt-core bug found running this project's own checks for
  real: a test whose true failure count was nonzero but under every
  configured threshold was silently reporting zero failures. Worked
  around by re-deriving the true count from dbt's own audit table
  instead of trusting its summary field.

## 2026-09-14

### Added
- **11:21pm** — **Failing Sample IDs** **[Dashboard UI]** **[QA checks & contract]** Real per-row failing sample identifiers (never full row content) in
  the check-detail panel, so a failing check shows which specific
  records tripped it.
- **9:04pm** — **Test Tooling Setup** **[Testing & dev tooling]** `uv`, `ruff`, and a real `pytest` smoke-test suite.
- **7:44am** — **Resupply Simulation** **[Data generation]** Resupply-chain simulation: a delivery with a real red failing check
  gets a simulated resupply request and a later, possibly-still-broken
  resupply attempt - matching how this actually plays out in practice.

### Changed
- **8:50pm** — **Real Tools Only** **[QA checks & contract]** Removed the four hand-written "equivalent" check engines entirely -
  built early on to demonstrate the pipeline before real tool access
  existed, now fully superseded by the real tools they stood in for.

## 2026-09-13

### Added
- **9:19pm** — **Child Protection Added** **[QA checks & contract]** **[Data generation]** Child Protection added as a second real dataset collection, alongside
  Birth Registrations, complete with its own cross-table business-rule
  checks.
- **8:06pm** — **Dashboard Goes Live** **[Pipeline & publishing]** The dashboard published live to GitHub Pages.
- **6:16pm** — **Project Kickoff** **[QA checks & contract]** Real dbt-core, Soda Core, datacontract-cli, and
  Evidently AI wired in, in place of this project's original
  hand-written stand-ins (built during an earlier session with no
  package-registry access).
