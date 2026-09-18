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

## 2026-09-18

### Added
- **12:24pm** — A GitHub Issues ticketing MVP: a new, separate write-permitted
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
- **11:23am** — A small badge on each dataset's own tile linking straight to its
  real, currently-open GitHub Issue (when one exists) - embedded at
  dashboard build time from a real, read-only GitHub API call, same
  treatment every other embedded feed on the page already gets.
- **8:15am** — A live requirements register: real user stories with MoSCoW priority
  and implementation status, each one's completion backed by a real,
  CI-enforced link to the test that actually verifies it - a claimed
  "built" requirement with no real test behind it now fails CI, not
  just a documentation exercise.
- **7:45am** — A real aggregate red/amber/green status shown against every entry in
  a dataset's supply history - the worst status among every check
  across every column for that specific delivery - and a genuine "N
  days since the previous supply" counter on resupply attempts.
- **12:58am** — Full integration test coverage against all four real QA tools, a unit
  test suite for the dashboard's own inline JavaScript, and real-browser
  end-to-end tests (as-of date picking, supply-history drill-down, dark
  mode) - plus a measured code-coverage floor now enforced on every
  push, not just a speed-focused smoke-test suite.

### Fixed
- **12:24pm** — The GitHub Issues ticketing MVP's very first live run: opening a
  ticket needs its labels to already exist on the repo, which neither
  did yet - now created automatically the first time they're needed.
- **12:16pm** — Two real threshold-encoding bugs behind the dashboard's red/amber/
  green status: a check with no fail threshold configured used to
  silently read as failing almost every run (a missing threshold
  defaulted to zero rather than "can't fail"), and a handful of real
  contract rules with a genuine non-zero tolerance had that real
  threshold discarded entirely.
- **12:16pm** — A local build failure: re-running the real check tools without first
  refreshing the combined warehouse left one column's arrival stats
  looking up a run that wasn't there yet.
- **6:28am** — Two real continuous-integration failures that had gone unnoticed for
  hours: GitHub's own runner resolving a newer Python version than this
  project had ever been tested against, and a missing one-time setup
  step for one of the real check tools.
- **6:12am** — A resupply-history grouping bug: a resupply landing weeks late used
  to get lumped in with an unrelated delivery that merely happened to
  arrive on the same calendar day.

### Changed
- **12:01pm** — A real YAML syntax mistake in a hand-edited contract file went
  uncaught until the next tool run parsed it - a real `check-yaml`
  pre-commit check now catches this class of mistake at commit time.
- **7:45am** — How a resupply chain gets identified: no longer inferred from
  internal bookkeeping about which delivery a resupply was "for," but
  derived purely from a delivery's real cadence-aware timing and each
  arrival's own real pass/fail outcome - closer to what could actually
  be observed from a real production feed, where a resupply never
  arrives labelled as such.

## 2026-09-17

### Added
- **8:23pm** — Child Protection's dataset detail page now stays fully drillable even
  when its most recent supply falls outside the "as of" staleness
  window: real historical columns, checks, and trend charts stay
  browsable, just without misleading current-status colors.
- **7:33pm** — Sparklines on the Tier 2 (agency dataset list) and Tier 3 (column
  grid) views, not just the Executive tier - then redesigned to show
  each tier's own aggregate failing-check RATE over time (not one
  arbitrarily-picked check's raw value, and not a raw count, which
  would stop being comparable the moment a check gets added or retired
  mid-history).
- **5:54pm** — Trend-chart gap and marker rework: a real visual split (with a small
  double-tick glyph) where a check's definition changed in a breaking
  way; a subtler marker where it changed non-breaking; a separate
  dashed connector for a run a check has no result for, distinct from
  either kind of definition change.
- **4:38pm** — A dark mode toggle.
- **3:28pm** — Changelog and plain-English description sections inside each check's
  own detail panel, alongside its existing trend chart and comparison
  view.
- **1:40pm** — A retired-checks toggle in the current-status view: a check that's
  been formally retired stays fully visible in its column's check list,
  behind a toggle, without ever being able to turn that column's status
  amber or red again.
- **9:14am** — The Executive-tier "Recent activity" panel - a feed of who published
  QA results for which dataset, and when.
- **7:42am** — The cadence-aware "as of" date picker: pick any date and see the
  data asset exactly as it stood then, with a staleness tolerance so
  an overdue dataset reads as "no data" rather than silently showing
  old data as current.

### Fixed
- **8:00pm** — The three `date_of_birth` freshness checks (dbt, Soda, datacontract-
  cli) that read permanently red - they were comparing against the real
  wall-clock date, which drifted further from this fixture's dates
  every day since it was last regenerated. Re-anchored to each run's
  own date instead, paired with a new occasional-staleness defect so
  the checks have something real to catch either way.
- **7:13pm** — The live dashboard's "past snapshots" picker, which had never
  actually shown a real snapshot on the published site - the archived
  snapshot files were there, the picker's own list of them just never
  made it into the deployed page.

### Changed
- **6:44pm** — Child Protection's quarterly delivery cadence re-anchored to
  February/May/August/November.

## 2026-09-16

### Added
- **9:44pm** — The whole publishing/history architecture this PoC now runs on: every
  real QA run's raw tool output committed to `qa_results/` as a
  permanent record; the dashboard rebuilt purely from that committed
  history, with no live database access required; a CI-gated publish
  pipeline (build, validate, deploy) with no manual local-publish path;
  and a permanent, globally-unique ID for every real check, so a
  check's history survives even once its definition changes or it's
  formally retired.
- **8:39am** — "Time travel" dashboard snapshots - a full, self-contained, gzip-
  archived copy of the dashboard taken at a point in time, openable
  years later with nothing but a browser - plus a picker panel, built
  into the live dashboard, for browsing past snapshots.
- **7:33am** — A status pill, a run-picker, and a real side-by-side run comparison
  added to the check-detail panel.

## 2026-09-15

### Added
- **9:10pm** — Full triplication of the check battery: every check that a
  supporting tool can express, implemented in that tool - not just one
  or two illustrative examples per dimension.

### Fixed
- **10:22pm** — A real dbt-core bug found running this project's own checks for
  real: a test whose true failure count was nonzero but under every
  configured threshold was silently reporting zero failures. Worked
  around by re-deriving the true count from dbt's own audit table
  instead of trusting its summary field.

## 2026-09-14

### Added
- **11:21pm** — Real per-row failing sample identifiers (never full row content) in
  the check-detail panel, so a failing check shows which specific
  records tripped it.
- **9:04pm** — `uv`, `ruff`, and a real `pytest` smoke-test suite.
- **7:44am** — Resupply-chain simulation: a delivery with a real red failing check
  gets a simulated resupply request and a later, possibly-still-broken
  resupply attempt - matching how this actually plays out in practice.

### Changed
- **8:50pm** — Removed the four hand-written "equivalent" check engines entirely -
  built early on to demonstrate the pipeline before real tool access
  existed, now fully superseded by the real tools they stood in for.

## 2026-09-13

### Added
- **9:19pm** — Child Protection added as a second real dataset collection, alongside
  Birth Registrations, complete with its own cross-table business-rule
  checks.
- **8:06pm** — The dashboard published live to GitHub Pages.
- **6:16pm** — Project kickoff: real dbt-core, Soda Core, datacontract-cli, and
  Evidently AI wired in, in place of this project's original
  hand-written stand-ins (built during an earlier session with no
  package-registry access).
