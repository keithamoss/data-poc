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
generation window.

## 2026-09-17

### Added
- The Executive-tier "Recent activity" panel - a feed of who published
  QA results for which dataset, and when.
- A retired-checks toggle in the current-status view: a check that's
  been formally retired stays fully visible in its column's check list,
  behind a toggle, without ever being able to turn that column's status
  amber or red again.
- Changelog and plain-English description sections inside each check's
  own detail panel, alongside its existing trend chart and comparison
  view.
- A dark mode toggle.
- Trend-chart gap and marker rework: a real visual split (with a small
  double-tick glyph) where a check's definition changed in a breaking
  way; a subtler marker where it changed non-breaking; a separate
  dashed connector for a run a check has no result for, distinct from
  either kind of definition change.
- Sparklines on the Tier 2 (agency dataset list) and Tier 3 (column
  grid) views, not just the Executive tier - then redesigned to show
  each tier's own aggregate failing-check RATE over time (not one
  arbitrarily-picked check's raw value, and not a raw count, which
  would stop being comparable the moment a check gets added or retired
  mid-history).
- Child Protection's dataset detail page now stays fully drillable even
  when its most recent supply falls outside the "as of" staleness
  window: real historical columns, checks, and trend charts stay
  browsable, just without misleading current-status colors.

### Fixed
- The three `date_of_birth` freshness checks (dbt, Soda, datacontract-
  cli) that read permanently red - they were comparing against the real
  wall-clock date, which drifted further from this fixture's dates
  every day since it was last regenerated. Re-anchored to each run's
  own date instead, paired with a new occasional-staleness defect so
  the checks have something real to catch either way.
- The live dashboard's "past snapshots" picker, which had never
  actually shown a real snapshot on the published site - the archived
  snapshot files were there, the picker's own list of them just never
  made it into the deployed page.

### Changed
- Child Protection's quarterly delivery cadence re-anchored to
  February/May/August/November.

## 2026-09-16

### Added
- "Time travel" dashboard snapshots - a full, self-contained, gzip-
  archived copy of the dashboard taken at a point in time, openable
  years later with nothing but a browser - plus a picker panel, built
  into the live dashboard, for browsing past snapshots.
- The cadence-aware "as of" date picker: pick any date and see the
  data asset exactly as it stood then, with a staleness tolerance so
  an overdue dataset reads as "no data" rather than silently showing
  old data as current.
- The whole publishing/history architecture this PoC now runs on: every
  real QA run's raw tool output committed to `qa_results/` as a
  permanent record; the dashboard rebuilt purely from that committed
  history, with no live database access required; a CI-gated publish
  pipeline (build, validate, deploy) with no manual local-publish path;
  and a permanent, globally-unique ID for every real check, so a
  check's history survives even once its definition changes or it's
  formally retired.

## 2026-09-15

### Added
- Full triplication of the check battery: every check that a
  supporting tool can express, implemented in that tool - not just one
  or two illustrative examples per dimension.
- A status pill, a run-picker, and a real side-by-side run comparison
  added to the check-detail panel.

### Fixed
- A real dbt-core bug found running this project's own checks for
  real: a test whose true failure count was nonzero but under every
  configured threshold was silently reporting zero failures. Worked
  around by re-deriving the true count from dbt's own audit table
  instead of trusting its summary field.

## 2026-09-14

### Changed
- Removed the four hand-written "equivalent" check engines entirely -
  built early on to demonstrate the pipeline before real tool access
  existed, now fully superseded by the real tools they stood in for.

### Added
- Real per-row failing sample identifiers (never full row content) in
  the check-detail panel, so a failing check shows which specific
  records tripped it.
- `uv`, `ruff`, and a real `pytest` smoke-test suite.

## 2026-09-13

### Added
- Project kickoff: real dbt-core, Soda Core, datacontract-cli, and
  Evidently AI wired in, in place of this project's original
  hand-written stand-ins (built during an earlier session with no
  package-registry access).
- Child Protection added as a second real dataset collection, alongside
  Birth Registrations, complete with its own cross-table business-rule
  checks.
- The dashboard published live to GitHub Pages.
- Resupply-chain simulation: a delivery with a real red failing check
  gets a simulated resupply request and a later, possibly-still-broken
  resupply attempt - matching how this actually plays out in practice.
