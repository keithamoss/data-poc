# Publishing & results history

Scoped 2026-09-16, one long session with Keith working through several
linked threads: how QA results actually become durable/shared, how
multiple people running QA concurrently across ~30 datasets shouldn't
step on each other, how a quarterly-cadence data asset should be
presented differently from a daily one, and how a check being retired
(or changed) should show up in the reporting UI. None of this is built
yet - this file is the scoping record plus an implementation order,
written because Keith wants to start building against it soon.

This supersedes/extends parts of `plans/wider.md`:
- `plans/wider.md` #8's "how checks output/results get stored in a
  multi-user environment" parked bullet - this file is the real answer.
- `plans/dashboard.md` #5's "time travel" snapshot mechanism stays as
  built (freezing the whole rendered dashboard page) - genuinely
  different from this file's "as of" viewing (Thread C below), which
  queries real accumulated history rather than replaying a frozen page.
  Both are staying in the design; see Thread C for how they relate.
- This file's own item #4 (check versioning, superseded) - folded into
  this file's Thread D, built together with Thread B rather than as a
  separate later round, per Keith's own call once the storage format was
  in scope anyway.

## Why this changes things

Today: `data/raw/`, `data/warehouse.duckdb`, `reports/*.json` are all
gitignored and fully regenerated locally (CLAUDE.md's own stated
convention). `dashboard/qa-reporting-dashboard.html` is the only
git-tracked artifact, one file with every dataset's data embedded as JS
consts, updated by whoever last committed a regeneration of it.

That model breaks down at the scale this is actually heading toward:
multiple people running QA concurrently across ~30 datasets, some daily-
cadence, some quarterly. Two real problems surfaced:

1. **Concurrency** - if publishing means committing the whole embedded
   dashboard file, two people publishing around the same time can
   silently clobber each other's freshest data for datasets they didn't
   touch, or produce real git conflicts on a file that isn't naturally
   mergeable.
2. **No real persistence** - nothing durable exists for the actual check
   RESULTS beyond whatever's currently embedded in the live dashboard.
   There's no way to ask "what did dataset X's checks look like 6 months
   ago" beyond the opt-in, coarse "time travel" snapshots (whole-page
   freezes, not queryable data).

## Thread B - committed per-run tool-output files (build first)

**Status:** done (2026-09-16) · **Category:** Pipeline & publishing

**Decision:** each QA run's raw tool output - one file per tool per
dataset per run (a real dbt run-results file, a real Soda scan result, a
real Evidently report, etc.) - gets committed to the repo, as-is in each
tool's own native format, not reshaped into a common schema first. This
becomes the actual source of truth for QA history, potentially spanning
years, independent of whatever the dashboard currently renders.

A separate "dashboard pipeline" step reads the full committed history
and merges/reshapes it into the reporting layer - deliberate separation
of concerns between the checks layer and the reporting layer, since
either might get swapped independently (tools narrowed down post-PoC;
the dashboard itself rebuilt or replaced).

**Confirmed explicitly with Keith:**
- Scope is tool RESULTS only (what `reports/*.json` already holds today)
  - NOT the underlying raw synthetic data records (`data/raw/`), which
    stays exactly as it is: gitignored, regenerated, ephemeral.
- This reverses CLAUDE.md's current documented rule that `reports/*.json`
  etc. are gitignored/regenerated - needs an explicit doc update as part
  of this work, not a silent contradiction (see "Doc updates needed"
  below).
- Retention: keep everything forever, same policy as the dashboard
  snapshots (item 26) - no thinning, revisit only if storage genuinely
  becomes a problem.
- Format: native/raw tool output, unmodified - the dashboard pipeline
  does all reshaping when reading history back, not at commit time.

**Not yet pinned down** (implementation detail, propose a default when
building, not a real fork worth a round of questions): exact path/
naming layout for these files. Something like `qa_results/<agency>/
<dataset>/<run_timestamp>/<tool>.<ext>` is the obvious shape, consistent
with how `data/raw/`/`data/cp_raw/` already lay out by dataset - confirm
against the real per-tool output formats when this gets built (dbt's
`run_results.json`, Soda's scan result, Evidently's report format may
each want slightly different handling).

**Scoped and decided, 2026-09-16 (Keith): per-table nesting stays
dataset-level everywhere, not table-level** - both for check DEFINITION
files and for `qa_results/` output. Keith's own initial instinct was
table-level (Child Protection has 6 tables, and he was explicitly fine
with the real-tool run time cost of invoking each tool once per table
instead of once per dataset), but once the ODCS/datacontract-cli
constraint was laid out concretely - one contract document IS one data
product, carrying document-level identity/version/team/support/as-of
config plus 10 real cross-table FK/business-rule checks that don't have
a single owning table to live under - Keith's final call was to keep
every tool (dbt/Soda/ODCS/Evidently) uniformly at dataset level, not
carve out ODCS as the one exception while the other three fragment.
Nothing about `qa_results/`'s existing `<agency>/<dataset>/<run_id>/
<tool>.json` layout needed to change to honor this - it was already
dataset-level for 3 of 4 CP tools.

**A real bug found while confirming that, not a design gap**: tracing
CP's actual on-disk `qa_results/` layout to answer this turned up that
`run_evidently_cp.py` was the one genuine outlier - it wrote under its
own table-scoped dataset id (`cp_common.TABLE_DATASET_ID
["cp_notifications"]`) instead of the collection id every other CP tool
uses, landing each run's `evidently.json` in a stray sibling directory
instead of alongside that run's other 4 files. Fixed (write path only -
each result's own per-table `dataset_id` field is untouched, still
needed for dashboard grouping), verified via a real full `orchestrate_
cp.py` run diffed against the previously-committed history (only
`run_timestamp` changed, same 2832-result pass/warn/fail distribution),
stale directory removed. Full account, including the regression tests,
in `plans/qa-pipeline.md` item 50 - not re-derived here.

## Thread D - check lifecycle: retirement + definition changes (build together with B)

**Status:** done (2026-09-16) · **Category:** QA checks & contract

Originally item 27 (parked), pulled forward once Keith realised the
committed-per-run format in Thread B needs to already accommodate this -
retrofitting it after the fact would be harder than designing it in from
the start.

**Two things need capturing, both confirmed in scope for this round:**
1. **Retirement** - a check stops running. Its history must stay fully
   visible (not deleted, not hidden), but clearly flagged as inactive/
   retired rather than silently looking like a check that's just
   stopped reporting (which would look like a broken run, not a
   deliberate change).
2. **Definition changes while still active** - a check's threshold or
   logic changes but it keeps running. Some changes are a genuine break
   in the series (shouldn't be read as a real trend change), some
   aren't - both need to show up differently in the reporting UI per
   Keith's original framing of item 27.

**Confirmed: explicit declaration, not inferred from absence.** A check
missing from a recent run's output is ambiguous - could mean retired,
could mean the run crashed before reaching it, could mean a tool config
error. Explicit is the only signal that's actually trustworthy.

**Round 2 (2026-09-16, same session) - metadata location, identity,
version detection, enforcement, and authoring all settled:**

- **Metadata location: per-tool, duplicated**, not one canonical
  registry. Keith's own call - tool count is narrowing to ~2 eventually,
  so the duplication cost is lower than a canonical-registry design
  would be worth. Richer metadata than originally sketched: not just a
  retired flag, but a version, a retirement **reason**, a **changelog**
  of changes over time, and the date a check was **first introduced**.

- **Check identity: needs an explicit, human-entered, globally unique
  `check_id`** - NOT derived from any tool's own naming. Checked all
  four tools' actual current naming (not assumed):
  - dbt: `test_metadata["name"]` (`qa_tools/bdm/run_dbt_bdm.py`) - dbt's
    stable BASE test name (e.g. `"accepted_values"`), deliberately
    reused across every column/dataset that uses that generic test.
  - Soda (`run_soda_bdm.py`): auto-named checks use a metric-type name
    (`missing_percent[scope]`); custom-named "failed rows" checks use a
    human-written `name:` field from the YAML (`contract/*-soda-
    checks.yml`) - real, but genuinely collision-prone: BDM's date-range
    check is named `"date_of_birth is within a plausible range"`, CP's
    is `"date_of_birth out of range"` - different text today by luck,
    not by any enforced uniqueness, for what's conceptually the same
    kind of check on two different datasets.
  - Evidently (`run_evidently_bdm.py`): hardcoded Python string
    constants (`"drift:PSI"`, `"evidently:row_count_growth"`),
    deliberately shared across whichever dataset's orchestration script
    uses them.
  - datacontract-cli: same pattern, `f"datacontract:{metric}"`.

  None of these give a single flat string that's unique on its own
  across 30 datasets - every one of them relies on being combined with
  `dataset_id`/`column_name` to disambiguate, and even the most
  deliberately-named case (Soda's custom `name:` field) has zero
  uniqueness enforcement. Keith's call: introduce an explicit,
  human-entered `check_id` rather than relying on tuple composition or
  any tool's own naming quirks.

- **Uniqueness enforcement: a GitHub Actions job**, not a local
  pre-commit/pre-push hook (that distinction was worth drawing out
  explicitly: a local git hook only fires if a contributor has it
  installed and can be bypassed with `--no-verify`; a GitHub Actions
  workflow can't stop a push from landing, but CAN block it from being
  merged/published - which is exactly what Thread A's existing CI gate
  already does). Confirmed: fold this into that SAME gate rather than
  building a second, separate enforcement mechanism. The job scans every
  committed check definition across all 30 datasets and fails if any
  `check_id` is duplicated, or if a check's config changed without a
  matching changelog entry present.

- **Version detection: auto-detect via config hash, human marks
  breaking/reason** - confirmed shape unchanged from the first round:
  hash each check's config under its `check_id`; a hash that differs
  from what's on file is an automatically-detected new version. A human
  then writes the changelog entry for it (see fields below) - the CI gate
  above is what actually enforces that this happens before a change can
  be published, not an optional courtesy step.

- **Authoring: no CLI - structured metadata lives directly in each
  check's own definition**, hand-typed by a human. Keith's explicit
  call, reversing my own earlier CLI proposal: the CI gate validates
  correctness (uniqueness, required fields present), so a separate
  authoring tool isn't needed - the check definition file itself is
  where this metadata belongs. Verified per-tool mechanics rather than
  assumed a single approach works everywhere:
  - **dbt**: has a real, already-existing `meta:` dict on tests, built
    for exactly this kind of custom metadata - doesn't touch
    `config.warn_if`/`error_if`, no new dbt-core mechanism needed.
  - **Soda**: checked the installed `soda-core` package's own SodaCL
    parser (`soda/sodacl/sodacl_parser.py`) - `ATTRIBUTES` is a real
    parser keyword, a genuine per-check `attributes:` block, not
    something to invent from scratch. Exact per-check nesting mechanics
    to confirm when this gets built.
  - **Evidently**: a real asymmetry worth being upfront about - its
    checks aren't YAML at all today, they're hardcoded Python constants
    in `run_evidently_bdm.py`. "Alongside the check" means alongside
    that Python code (e.g. a module-level dict), not a YAML field like
    the other three.
  - **ODCS contract**: not yet checked against the real spec for a
    custom-properties equivalent - do this when building, same rigor as
    the other three (verify, don't assume).

**Confirmed field set for the metadata, each check gets:**
- `check_id` - human-entered, must be globally unique (CI-enforced).
  Format confirmed 2026-09-16: `<data-asset-name>.<agency>.<dataset>.
  <table>.<column>.<check_name>` - `column` omitted for a table-level
  check (e.g. `dbt_utils.expression_is_true`/`recency`, declared under
  the model itself, not a column). `data-asset-name` is a fixed literal
  prefix used across every check_id in the whole system, not something
  that varies per check - placeholder value for now: `data-asset-1`
  (Keith's own call - a real name can replace it later, everywhere it
  appears, without changing the scheme itself). `dataset` and `table`
  are deliberately separate segments even though they're near-identical
  strings for BDM today (single-table dataset) - they genuinely differ
  for Child Protection (one collection/dataset, six distinct tables),
  and Keith's explicit go-ahead: duplication for BDM is fine.
- `introduced_date` - when the check was first added.
- `retired_as_of` + `retired_reason` - both optional, both required
  together if the check is retired (history stays fully visible, just
  flagged inactive from this date).
- `description` - human-written, plain-English explanation of what the
  check actually does and why - pulled in from `plans/qa-pipeline.md`
  #43 2026-09-16 (Keith's own instruction: "pull that out"), which had
  parked a related but distinct idea: surfacing a check's REAL
  SQL/YAML/technical definition in the dashboard, not just today's
  terse `label`. That original ask stays open on its own (see below) -
  this `description` field is the complementary, human-authored
  explanation, not a replacement for showing the real technical rule.
  Natural fit alongside the rest of this metadata, authored the same
  way (dbt's `meta:`, Soda's `attributes:`, etc.) since it's the same
  kind of hand-written, check-level information.
- `changelog` - a list of entries, each with: `date` (automatic, not
  hand-entered), `description` (human-written), `author` (human-entered
  - deliberately not auto-derived from git's own commit author, per
  Keith's own call), `breaking` (human-set boolean).

**Concrete per-tool schema, `data-asset-1` placeholder applied:**

```yaml
# dbt schema.yml
tests:
  - not_null:
      meta:
        check_id: data-asset-1.bdm.birth_registrations.stg_birth_registrations.registration_number.not_null
        introduced_date: "2026-01-15"
        description: "Every birth registration must carry a registration number - BDM's primary key for the feed."
        changelog:
          - date: "2026-06-01T10:00:00Z"
            description: "Tightened null tolerance"
            author: "Keith Moss"
            breaking: false

# Soda checks YAML
checks for birth_registrations:
  - missing_percent(place_of_birth_facility) > 5%:
      name: place_of_birth_facility missing rate
      attributes:
        check_id: data-asset-1.bdm.birth_registrations.stg_birth_registrations.place_of_birth_facility.missing_percent
        introduced_date: "2026-01-15"
        description: "Facility should usually be captured - home births are the expected exception."
        changelog: []

# ODCS contract
quality:
  - metric: nullValues
    mustBe: 0
    customProperties:
      - property: check_id
        value: data-asset-1.bdm.birth_registrations.stg_birth_registrations.registration_number.nullValues
      - property: description
        value: "Every record must carry a registration number."
      - property: introduced_date
        value: "2026-01-15"

# Evidently (Python, no YAML today)
CHECK_LIFECYCLE = {
    "data-asset-1.bdm.birth_registrations.stg_birth_registrations.row_count_growth": {  # table-level, column segment omitted
        "introduced_date": "2026-02-01",
        "description": "Row count should mostly grow run over run - a real drop signals a broken/partial extract.",
        "changelog": [],
    },
}
```

**UI presentation - resolved, 2026-09-16, same session:**
- **Breaking definition change: a real visual gap/split in the trend
  line**, not just a marker on a continuous line - the strongest signal
  that before/after genuinely aren't comparable. Deliberately styled
  DISTINCTLY from Thread C's "no data available" state (quarterly-
  cadence datasets, below the as-of threshold) - both are "a gap in the
  line," but they mean different things (one is missing data, one is a
  deliberate declaration that the check itself changed) and must not
  look identical. Exact styling (color/pattern) to work out when built,
  but the constraint is now explicit, not something to discover as a
  bug later.
- **Non-breaking definition change: a subtle marker on the still-
  continuous line, deliberately the SAME COLOR as the breaking-change
  styling** - Keith's own call: color is the consistent visual language
  for "the check itself changed here" across both cases; the *shape*
  (a gap vs. a marker on an unbroken line) is what actually carries the
  breaking/non-breaking distinction, not a different color per case.
- **Retired checks: drop out of the main current-status view by
  default** (column drawer, overall summary) - a retired check isn't
  part of "what's currently being checked," so the default view stays
  focused on active checks. A toggle brings retired checks back into
  view for history/audit purposes - full history stays intact and
  reachable, just not front-and-centre by default.
- **Changelog and description metadata both surface in the existing
  check-detail panel** (item 42's status pill, item 45's comparison UI)
  rather than a new tooltip pattern - each becomes another section of
  the panel that already shows a check's status/history/comparison,
  consistent with how everything else about a check is already
  presented there.

**Still not designed:**
- Exact visual styling for the breaking-change gap vs. Thread C's
  no-data gap, and the shared marker/gap color itself (the constraints
  - must differ from no-data, breaking and non-breaking share one color
  - are settled; the actual color/pattern values aren't).
- `plans/qa-pipeline.md` #43's ORIGINAL ask - surfacing a check's real
  SQL/YAML/technical definition (not the new plain-English
  `description` field, which is now resolved) - stays open, not
  resolved by this round. Candidate approaches unchanged from that
  item's own text: embed the source snippet at generation time, or a
  simpler static mapping keyed by check_id now that one reliably
  exists.
- **Un-retiring a check leaves a misleading gap in its trend chart,
  not a visible break** (Keith's question, 2026-09-16: "would it just
  work, or would it blow things up?"). Mechanically nothing blows up -
  moving a check_id back from its tool's `-retired` sibling file into
  the active one is clean against `validate()` (config_hash excludes
  `retired_as_of`/`retired_reason`, so un-retiring alone needs no new
  changelog entry unless the underlying threshold also changed), and
  the real tool just resumes evaluating it from the next run. The gap
  is in what's rendered: while retired, the check has literally no
  result in any run's `qa_results/` output (not a placeholder - the
  entry doesn't exist), so its `history` array jumps straight from the
  last pre-retirement point to the first post-un-retirement one. Traced
  the actual chart code (`dashboard/qa-reporting-dashboard.html`'s
  `trendChart()`, the `xs()` position function) to check, not assumed:
  points are positioned by ARRAY INDEX, not real elapsed time, so
  today's chart would draw that gap as an ordinary unbroken line
  between two "adjacent" points - visually implying continuous
  reporting straight through the retired period, the opposite of a
  visible break. Same root cause as the breaking-change gap styling
  above (an index-based x-axis with no concept of real time between
  points) - Keith's call: fold "retirement gap" into that same
  not-yet-designed piece of work rather than treating it separately,
  since a fix for one likely fixes both (a date-based x-axis, or at
  minimum a real-time-aware gap/break marker between two history
  points whose dates are further apart than the dataset's own normal
  run cadence).

## Thread A - publishing (build after B/D's data format exists)

**Status:** done (2026-09-16) · **Category:** Pipeline & publishing

**Decision: no manual "publish from local" path, in any form** - not a
routine mechanism, and not even as a break-glass fallback for CI being
down (Keith's explicit call: "gone entirely - CI is the only path").
Local QA runs still build a local dashboard HTML so someone can look at
their own results, but that's purely for personal viewing - it never
becomes the mechanism by which the shared/published site updates.

**What replaces it:** local runs commit just the raw per-run tool-output
files (Thread B) - lightweight, low-conflict commits, since concurrent
runs from different people/datasets are different files, not edits to a
shared blob. A CI job then:
1. Rebuilds the full dashboard from ALL committed history (not just the
   latest run) via the Thread B/D-aware dashboard pipeline.
2. Runs a smoke-test gate before allowing publish - confirmed scope:
   structural checks (the dashboard actually builds, embeds valid JSON,
   no parse/build errors) PLUS a real render check (load the built
   dashboard in a headless browser, check for JS console errors and
   that key UI elements actually render - the same kind of check this
   session's own Playwright verification has been doing by hand
   throughout; this becomes an automated, permanent version of that).
   **Also covers Thread D's check-lifecycle validation** (settled
   2026-09-16): fails if any `check_id` is duplicated across the 30
   datasets, or if a check's config changed without a matching
   changelog entry - one gate, not two separate enforcement mechanisms.
3. Only publishes (deploys to GitHub Pages) if the gate passes - a
   broken run genuinely can't reach the published site.

**Confirmed with Keith (2026-09-16):** CI triggers on push to the
committed raw-result paths - explicitly NOT on a schedule. Keeps faith
with the "every run should arguably be shared" principle from the
original local-publish brainstorm - the moment someone's results land in
the repo, the team's view updates (once smoke tests pass), no separate
deliberate "now publish" step and no waiting for a scheduled window
either.

Broadened per Keith's own addition: the trigger path set isn't just the
raw per-run result files - it's anything in this space whose change
could affect the published output. In practice that means the workflow's
`paths:` filter needs to cover, at minimum: the committed `qa_results/`-
style raw tool outputs (Thread B), the check-lifecycle/versioning
metadata (Thread D - a retirement or definition-change declaration
changes what gets rendered even without a new run), and the dashboard
pipeline's own code (the merge/reshape/render logic itself - a bug fix
or feature to that code changes the published output just as much as
new data does, same principle `deploy-pages.yml`'s existing `dashboard/**`
path filter already applies to today). Exact path list to be finalized
when Thread A actually gets built, once Thread B/D's real directory
layout exists to filter on.

**Changelog/activity feed** (Keith's own addition mid-thread - "who's
committed/pushed what dataset's QA recently"): falls out of this design
almost for free. Since publishing now means committing individual
per-run result files, git's own commit history (author, timestamp,
files touched) IS the changelog's source of truth - no bespoke
`PUBLISH_LOG`-style embedded const needed (an earlier idea, from before
Thread B was in scope, now superseded). The dashboard pipeline just
needs to reshape recent commit history touching `qa_results/` into a
friendly "Birth Registrations - published by Keith - 10 mins ago" feed
in the UI. Per-dataset, per-publish granularity confirmed as the right
level of detail.

**Refined, 2026-09-16, same session:** each entry needs TWO distinct
timestamps, not one - when the QA actually ran (the run's own execution
time, already captured in the committed result file's own metadata -
this project already has a `run_timestamp`/`run_id` concept), and when
it was committed/published (git's own commit timestamp). These can
genuinely differ - someone might run QA at 2pm and not commit until 5pm
- and conflating them would misrepresent how fresh the underlying check
actually is versus how fresh its publication is.

**Explicitly out of scope for this changelog, Keith's own clarification:**
check-lifecycle events (a check retired, a check's definition changed -
Thread D) do NOT appear here. This feed is purely "which dataset got
QA'd and published, by whom, when" - check versioning has its own
record (the lifecycle metadata itself, plus git's own commit history on
the check-definition files, which already provides an equivalent
changelog for THAT concern without needing to be merged into this one).

**UI, resolved - a real gap until Keith flagged it, the data model above
had been specified but not where/how it's actually shown:**
- **Placement: same pattern as the existing "🕐 Past snapshots" header
  button + side panel** - a new header button (e.g. "📋 Recent
  activity") opening a panel that lists entries, deliberately consistent
  with an interaction pattern that's already built rather than a new one.
- **Scope: one global feed across all 30 datasets**, not per-dataset -
  matches the original framing ("who's committed/pushed what dataset's
  QA recently") as a single cross-cutting view, useful for someone
  wanting an overview of what's happening across the whole register
  without checking dataset by dataset.
- **Depth: bounded to recent activity** (something like the last 20-50
  entries, or a time window - exact number not yet pinned down), not a
  full scrollable history - matches the "recent" framing of the original
  ask. Git's own history is already the permanent record for anyone who
  needs to go further back than this feed shows.

## Thread C - cadence-aware "as of" viewing (build last - depends on B/D)

**Status:** done (2026-09-17) · **Category:** Pipeline & publishing

Daily and quarterly datasets need different framing. Showing "today's"
dashboard state right after a quarterly refresh would look identical to
a daily dataset's genuinely live current state, even though the
quarterly one won't move again for ~3 months - a false signal, Keith's
own words.

**Decision:** a configurable relative-day offset that sets the
dashboard's default "as of" date. **Corrected 2026-09-16 (Keith's
call, superseding the two bullets originally here):** this offset is
genuinely DATA-ASSET-level, not per-dataset - one number, configured
once for the whole system, applied uniformly to every dataset's as-of
view regardless of that dataset's own refresh cadence. The original
design (documented below in the "Resolved while scoping Phase 4"
entry, kept for the record rather than deleted) reasoned a *different*
offset per dataset from its own cadence - 0/none for daily Birth
Registrations, 60 for quarterly Child Protection - which Keith flagged
as the wrong attachment point: it's config that belongs to the data
asset as a whole (`data-asset-1`, the same placeholder already used
throughout every check_id), not scattered per dataset. Concretely, once
this is wired into real as-of viewing logic, Birth Registrations will
ALSO default to a date some days behind latest rather than the
absolute latest - a real, deliberate behavior change from the original
design, not an oversight.
- Below the as-of threshold, a check/dataset that hasn't been run yet
  shows "no data available" rather than a misleading blank/red state.

**Confirmed: whole-dataset granularity, not per-check/per-column.**
Every check for a dataset runs together in one dbt build / Soda scan /
Evidently run - there's no mechanism today (or planned) where individual
checks inside one dataset go stale independently of each other. (The
one real exception - a check added to the suite after some point, so
its own history starts later than others - is Thread D's concern, not a
freshness question.)

**Also confirmed:** the as-of date is adjustable via a calendar UI
widget (not just the two states of "default offset" and "true latest"),
and the selected date persists in the URL so a specific view is
shareable/bookmarkable.

**Explicit build-order dependency, confirmed with Keith:** this needs
Thread B's real accumulated per-run history to query an arbitrary past
date against - it can't be meaningfully retrofitted onto today's
rolling-window/embedded-blob model. Build B (and D, since they're
intertwined) first.

**Resolved while scoping Phase 4 for real, 2026-09-16 (previously
"not yet designed") - SUPERSEDED the same day, see the correction
below:**
- **Offset value: 60 days for Child Protection**, Keith's call - set
  now that CP's own real generated cadence is genuinely quarterly (see
  plans/dashboard.md #5's history-depth entry), not picked to paper over the
  old weekly-labeled-as-quarterly mismatch. No offset for Birth
  Registrations (daily asset, always shows the absolute latest, by
  design - unchanged).
- **Offset config location: alongside the ODCS contract**, Keith's
  call - a root-level (dataset-level, not per-check) `customProperties`
  block on `contract/child-protection-contract.yaml`
  (`asOfOffsetDays: "60"`), same place check-lifecycle metadata already
  lives, no new top-level config file. No equivalent property on
  `contract/bdm-birth-registrations-contract.yaml`. Verified for real:
  `datacontract lint` still passes, `check_lifecycle.
  parse_contract_check_metadata()` still parses the same 62 checks
  (the new root-level block doesn't interfere with the existing
  per-check `quality:`-scoped customProperties parsing), full pytest +
  ruff clean.
- **Relationship to the "time travel" snapshot picker: two separate,
  clearly-labeled entry points**, Keith's call - not merged/unified,
  unaffected by the correction below.

**Corrected, same day (Keith): wrong attachment point - this is
data-asset-level config, not dataset-level, and genuinely one global
value, not a different one per dataset.** Keith's own words: "that
shouldn't be attached to datasets or anything... that should be
configuration attached to the data asset... that's like global, not
per dataset." Confirmed explicitly (not assumed) that he meant this
literally - one shared offset applied to every dataset's as-of view,
including Birth Registrations, not a shared config location that still
holds a different value per dataset underneath.

Moved out of `contract/child-protection-contract.yaml`'s
`customProperties` entirely into a new file, `contract/data-asset.yaml`
- the one place the `data-asset-1` placeholder (already used throughout
every check_id) is itself declared, alongside `as_of_offset_days: 60`.
The number carries over unchanged from the superseded per-dataset
value - only its attachment point and scope changed, not the number
itself (revisit if a genuinely global default warrants something
else). Re-verified for real after the move: `datacontract lint` still
passes on the now-smaller CP contract, `check_lifecycle.validate()`
still reports the same 258 checks/zero errors (the removed block was
root-level, never inside `check_lifecycle.py`'s per-check `quality:`
parsing), full pytest + ruff clean.

**Built, 2026-09-16 (same day, Phase 4): the actual as-of date picker
UI, querying logic, and "no data available" state.** Two forks scoped
with Keith via AskUserQuestion before building, both answered against
the recommended default:
- **One global as-of date control for the whole dashboard, not
  per-dataset** - a single header button (📅, next to "🕐 Past
  snapshots" - a deliberately separate entry point, per the
  already-confirmed design above) opens a small picker panel; picking a
  date rebuilds every real dataset's view against it at once.
- **Default date basis: "one shared 'now' across the whole data
  asset"** (Keith's own words), not each dataset's own latest run. I
  reasoned - not yet separately re-confirmed by Keith beyond the
  AskUserQuestion answer itself - that this "shared now" should be a
  deterministic quantity computed from committed history (the max
  `run_date` across every real dataset's `runs`, BDM and every CP table
  alike) rather than live wall-clock time, matching this project's
  existing reproducibility ethos (`TODAY` at the top of the dashboard
  script is already the same kind of fixed, seeded quantity for the
  illustrative datasets) - `maxRunDate()`/`defaultAsOf()` in the
  template. `AS_OF_OFFSET_DAYS` (Thread D's `contract/data-asset.yaml`
  value, re-embedded by `embed_dashboard_data.py` alongside the two
  real data consts) is then subtracted from that date to get the actual
  default.

Mechanics, all in `dashboard/qa-reporting-dashboard.template.html`:
- `clipDatasetToAsOf(d, asOfDateStr)` (written earlier alongside the
  scoping work above) filters a raw real dataset to only its runs at or
  before the picked date, recomputing history/current/previous/row
  counts/arrival from that clipped set; returns `null` when no run
  qualifies yet.
- `noDataDataset(...)` is the placeholder shown when `clipDatasetToAsOf`
  returns `null` - status `"nodata"`, deliberately NOT shaped like a
  real dataset (empty `columns`, `null` `lastArrival`) so a render path
  that forgets to check `ds.noDataAsOf` fails loudly instead of
  rendering wrong numbers.
- `"nodata"` sits below `green` in `STATUS_ORDER` (order `-1`) so it can
  never silently win a `worstOf()` reduce (would either mask a real
  problem or look like the worst possible outcome) - `worstOf()` alone
  also can't let it win an ALL-nodata rollup (an empty-after-filtering
  reduce just falls back to its `"green"` seed), so `rollup()`
  (datasets → collection) and the new `rollupStatuses()` (collections →
  agency) both special-case that "every child is nodata" case
  explicitly rather than relying on the reduce.
- `buildData(asOfDateStr)` - the whole `agencies:[...]` literal plus its
  bottom-up rollup wiring, which used to be a one-shot `const DATA =
  {...}`, is now a function; `DATA` itself is `let`, rebuilt from
  scratch (`DATA = buildData(CURRENT_AS_OF)`) on every date change -
  same "no leftover state from the old view" principle `navigate()`
  already uses for drill-down transitions, not a mutate-in-place update.
- URL persistence via a plain `?asof=YYYY-MM-DD` query-string param -
  deliberately NOT folded into the existing hash-based `STATE`
  mechanism (`stateToHash`/`hashToState`/`popstate`), since as-of is a
  global filter over the whole page, not a per-navigation state someone
  would want the browser's own back/forward to step through one change
  at a time. Omitted from the URL entirely when it equals the computed
  default, so a plain shared link never implies "someone deliberately
  picked a date" when nobody did.
- `renderAgency()`'s dataset table and `renderDataset()`'s dataset view
  both gained an explicit `ds.noDataAsOf` branch (a collapsed table row;
  a "no QA run as of this date" empty state) rather than reaching into
  `ds.lastArrival`/`ds.columns` unconditionally, which would otherwise
  crash on `noDataDataset()`'s intentionally-sparse shape.
- New `.pill.nodata` CSS treatment (dashed border, muted, matching the
  existing `.pill.illustrative` tone - "no data" is a different kind of
  signal from green/amber/red, not a fourth severity level).

Verified for real: `uv run python3 -m dashboard.check_dashboard_renders`
(built output AND template both render clean, zero console errors) plus
a separate real headless-Chromium functional script (not just the
render-cleanliness check) driving the actual picker - confirmed the
default date computes sanely, picking a date before Birth
Registrations'/Child Protection's earliest run shows the "no data"
empty state at both the dataset-detail and agency-table-row levels (and
doesn't crash the executive tier either), the URL gains/loses `?asof=`
correctly, and resetting to the default restores the real dataset view
and removes the URL param. Full `uv run pytest` (170 passed) and `uv
run ruff check .` clean.

**Corrected, same day (Keith): wrong default-date basis.** My own
un-confirmed reasoning above (`defaultAsOf()` computing "one shared
'now'" from the latest `run_date` anywhere in committed history) was
wrong - Keith's own words: it should be the genuine current date minus
`AS_OF_OFFSET_DAYS`, not the latest run date minus the offset. Fixed:
`defaultAsOf()` now reads real wall-clock `new Date()` directly
(`liveNowDateStr()`), same as `generator/anchor_date.py`'s own default
already anchors every real run's OWN dates to - the two normally agree
(BDM regenerates near real "now" every time), but only a genuine
wall-clock basis stays correct once real time has moved on since the
fixture was last regenerated, which a run-date-derived default would
silently fail to track. `maxRunDate()` removed (no longer used).

**Also same day: a real, related UI bug Keith caught by using the
picker, not a design gap** - the agency-tier dataset table's "Arrival
(today)" column header was written before Thread C's as-of clipping
existed, back when the default view WAS unconditionally "today's"
data. Once every dataset's default view can legitimately be clipped to
an earlier as-of date, that header is actively misleading - it reads
"(today)" over a date that may be days, weeks, or (for a quarterly
dataset) months in the past, which is very plausibly what looked like
"both BDM and CP arrived today" from the dashboard. Fixed: relabelled
to "Latest arrival" (matching the dataset-detail view's own SLA-tile
wording), dropping the now-inaccurate "(today)" implication rather than
trying to make it as-of-aware in-line.

**Investigated, not changed: whether Child Protection's own real
cadence still looks genuinely quarterly.** Keith's fallback instruction
("if [CP genuinely looks like it arrived today], pin its most recent
supply to around the first of August") was conditional, so checked the
premise directly against `reports/child_protection_dashboard.json`
before acting: CP's real latest committed run is `2026-07-01`, not
today (`2026-09-16` real wall-clock, per `generator/anchor_date.py`'s
default) - genuinely a real quarterly-cadence extract, ~2.5 months
behind BDM's own latest daily run, which is what the two-column-header
bug above most likely actually was (an accurate, quarterly-lagged date
sitting under a header that said "(today)" regardless). Since the
premise didn't hold, CP's own generated data was left alone - no
regeneration triggered speculatively. Genuinely shifting CP's rolling
quarter-boundary anchor (`generator/generate_cp_runs.py`'s
`_quarter_start()`/`_add_quarters()`, both phase-locked to calendar
Jan/Apr/Jul/Oct 1 via the shared `generator/anchor_date.py` anchor) so
its most recent supply lands nearer 2026-08-01 is a real, separate
design fork (a one-time hardcoded date vs. a permanent phase shift of
the quarter boundaries themselves, which would keep rolling forward
with real time the same way the existing Jan/Apr/Jul/Oct boundaries
already do) - not built, pending Keith confirming he still wants it now
that the header-label explanation accounts for what he saw.

**Resolved, same day: Keith confirmed CP's real latest supply
(`2026-07-01`) is already what he wanted** ("make that the 1st of
July, not August") - the design-fork question above is moot, no
generator change needed.

**Corrected, same day: a real, second gap in "no data available" - not
covered by anything above.** Keith actually tested the live picker
(not just read the header) and set as-of to `2026-09-16` on Child
Protection, expecting "no data" - got CP's real (accurate,
2.5-months-old) July data instead, i.e. "it's like it's still showing
me the last run somehow." Root cause, confirmed via `AskUserQuestion`
before touching code (a prior guess on this exact feature - the
run-date-derived default basis, corrected above - had already gone
wrong once, so this one wasn't assumed): `clipDatasetToAsOf()`'s "no
data" state only ever fired when literally NO run existed at or before
the picked date - correct as far as it went, but that only naturally
happens before a dataset's very first-ever run, which for a quarterly
dataset queried anywhere near "now" is nearly unreachable. That's
backwards from Thread C's actual point: a quarterly dataset overdue
for its next refresh should read as overdue, not silently show old
data as if current.

**Confirmed design (Keith, via AskUserQuestion): `AS_OF_OFFSET_DAYS`
is a staleness TOLERANCE, not just an input to the default-date
computation.** Once a dataset's most recent supply at-or-before the
picked as-of date is itself more than `AS_OF_OFFSET_DAYS` days older
than that picked date, the view now treats it the same as "never
supplied" - `"no data"`, not stale-but-real numbers. `clipDatasetToAsOf()`
gained one extra check (`daysBetween(effectiveRun.run_date,
asOfDateStr) > AS_OF_OFFSET_DAYS`) right after finding the effective
run, using the same `AS_OF_OFFSET_DAYS` const the default-date
computation already reads - one number now does double duty by
design, not two config values that happen to coincide. Both "no data"
render paths (the dataset-detail empty state, the collapsed agency-
table row) had their copy corrected too - the old wording ("no QA run
exists ... at or before this date") stopped being accurate once "no
data" could also mean "a run exists, but it's stale beyond tolerance",
not just "never ran yet".

Verified for real against Keith's own reported scenario: a headless-
Chromium script setting as-of to `2026-09-16` confirms Child
Protection now shows the corrected "no data" empty state (both at
dataset-detail and agency-table-row level) while Birth Registrations
(daily, always well within a 60-day tolerance) still shows its real
data; the DEFAULT as-of date (today minus 60) still shows Child
Protection's real July data too (17 days of gap, well inside
tolerance) - confirming the fix is genuinely date-gap-driven, not a
blanket "CP always shows no data" regression; and the pre-existing
true-absence case (an as-of date before CP's very first-ever run)
still correctly shows "no data" the original way. Full `uv run pytest`
(170 passed) and `uv run ruff check .` clean.

**Revisited, 2026-09-17 - the "DEFAULT as-of still shows real data"
verification above no longer holds, now that CP's real cadence has
been re-anchored** (Feb/May/Aug/Nov, `plans/qa-pipeline.md` item 59's
follow-on - CP's latest real delivery moved from 2026-07-01 to
2026-08-01). The 17-day gap that made the default view safe above is
now a case where the default as-of (`today - 60` = 2026-07-19) falls
BEFORE CP's real Aug-1 delivery, hiding it from the default view
entirely and falling back to the May-1 delivery instead - 79 days
stale relative to Jul 19, past the 60-day tolerance. Net effect: the
whole Department for Child Protection agency now reads `nodata` on the
plain Executive overview by default, not just on a deliberately-picked
near-today date the way the original design/verification anticipated.
Confirmed for real (`ag.status === "nodata"` at the live default
as-of, headless-Chromium). This is the SAME open tension flagged
immediately below ("`AS_OF_OFFSET_DAYS` is deliberately global, not
per-dataset") made concretely visible for the first time, not a new
bug - put to Keith with the exact numbers; not yet resolved as of this
entry. Three options on the table: grow the shared offset to
accommodate CP's ~91-day cadence (loosens BDM's own daily staleness
sensitivity, since it's one shared value); reopen global-vs-per-dataset
properly; or accept this default-view consequence for now. Keith's
initial answer ("flag it and move on") was given before seeing this
concrete default-view manifestation - re-raised once the severity
became visible rather than silently proceeding on the earlier, more
abstract answer.

**Follow-up, same day: a real Tier 3 structural gap found (and fixed)
while walking Keith through this mechanism.** Asked him to describe
exactly what he expected to see in two concrete as-of scenarios;
comparing that against actual behavior found status COLORS already
worked correctly at Tier 1/2, but Tier 3 discarded ALL historical
column/check data the moment a dataset went stale (`clipDatasetToAsOf()`
returning `null` unconditionally, `noDataDataset()`'s `columns: []`) -
no drill-down, nothing clickable, contrary to Keith's explicit "no red
amber and greens, but I should still be able to see the historical
graphs and comparison stuff." Built and verified for real against CP's
own live stale state - full account, including the one real design
question asked along the way (whether the no-data column tile's own
sparkline should suppress its real colors or keep them - Keith: keep
them), in `plans/qa-pipeline.md` item 64 (Phase 5g), not repeated here.
This is a genuinely separate fix from the `AS_OF_OFFSET_DAYS`-vs-CP-
cadence question just above - it makes the CURRENT no-data behavior
usable/drillable, it doesn't change when a dataset qualifies as
no-data at all, so the three options above remain exactly as open as
before this landed.

**Also found live-testing the picker, same day: BDM's own real window
was too shallow for its own default view.** `AS_OF_OFFSET_DAYS` (60)
and BDM's real generation window (`generator/generate_runs.py`'s
`N_DELIVERIES`, also 60) happened to collide - the default as-of date
landed one day before BDM's own earliest real run, so the flagship
real dataset showed "no data" on the very first thing anyone sees.
Keith's fix: widen BDM's rolling window (`N_DELIVERIES` 60 -> 120,
"from today backward", periodic regeneration accepted as normal
going forward) - full detail, plus the separate real `delivery_id`/
`run_id` zero-padding bug this widening exposed (and Keith's own
"fix properly, not just wider" correction) in `plans/qa-pipeline.md`
item 55, not repeated here since it's a generator/qa_results_reader.py
fix, not an as-of-viewing one.

**Superseded, 2026-09-17 (Phase 5j, `plans/qa-pipeline.md` item 65) -
`AS_OF_OFFSET_DAYS` itself is gone, not just re-tuned.** Everything
above this note (the "staleness TOLERANCE" design, the three options
on the table for the CP-cadence collision, BDM's own window-collision
fix) is history, not current design - kept for the record of how this
was reasoned through, not as a description of what's built now.
Walking through the actual open tension with Keith (why a flat global
day-count kept trading BDM's sensitivity against CP's cadence,
concretely: CP's real ~92-day gap between deliveries made the default
view read `nodata` for roughly two-thirds of every quarter) surfaced
that the real problem was the day-count SHAPE itself, not which one
number to pick. Keith's own reframe, prompted by "tell me more about
this" rather than the `AskUserQuestion` 3-option menu originally
planned to resolve it: the actual intent was never "N days of
tolerance," it was "a team on a quarterly cadence should be able to
set the as-of date to their own cycle's start and watch deliveries
flip from no-data to real status (and see whether they arrived late,
or early) as the day goes on" - a concept that needs to work
identically for a team on a daily cadence too. That reframing is what
replaced the day-count with real, per-dataset cadence config (daily/
weekly/quarterly, each with an AWST expected time + latency grace,
authored in each dataset's own ODCS contract's `slaProperties:`) -
"no data" now means "nothing has landed in the CURRENT expected
cycle," computed fresh from cadence, never a day-count comparison.
Confirmed fixed for real: CP's default as-of view (2026-09-17, inside
its current Aug-1-anchored quarterly cycle) now shows real status
instead of `nodata`. Full design history, what was built, and how it
was verified against real regenerated data: `plans/qa-pipeline.md`
item 65 - not repeated here.

## Build order

**Status:** done (2026-09-18) · **Category:** Pipeline & publishing

Renumbered/reorganized 2026-09-16 (Keith's own call, for ease of
reasoning/talking about this work) - each phase still names which
Thread(s) it corresponds to above, for reference back into the detailed
design, but Thread A/B/C/D are no longer the primary labels here.

**Split into 5 phases, same day, same session** - Keith's own follow-up
ask: the original Phase 1 (below) bundled two genuinely separable
things - producing/validating the committed data, and consuming it into
the dashboard - into one phase. Split along that write-side/read-side
line rather than separating Thread B from Thread D (that split was
deliberately rejected: Thread D's metadata needs to be designed into
Thread B's format from the start, not bolted on after, so those two
stay together).

**Phase 1 (Thread B + D - results storage + check-lifecycle format and
validation) - [DONE, 2026-09-16]:**
- Committed per-run raw tool-output files, with check-lifecycle
  (retirement/definition-change) metadata designed into the format from
  the start.
- **The check-lifecycle validation logic itself, as its own explicit
  deliverable** - the duplicate-`check_id` scan across all committed
  check definitions, and the changelog-completeness check (a config
  hash changed without a matching changelog entry). Built as reusable
  logic here, in this phase, so Phase 3's CI gate can directly invoke
  it rather than needing to build equivalent logic itself under a
  different phase's name.
- Doc updates: `CLAUDE.md`'s gitignore convention explicitly updated to
  reflect that `qa_results/` (or whatever this ends up named) is now
  committed, not ephemeral.

**Built and verified for real, not just designed:**
- `qa_tools/common/qa_results_writer.py` - writes each tool's native raw
  output to `qa_results/<agency>/<dataset-or-collection>/<run_id>/
  <tool>.json`. Wired into all 8 `run_*.py` tool-runner modules (BDM +
  CP, all 4 tools each). Collection-level tools (dbt/Soda/datacontract-
  cli for CP, which run once across all 6 tables in one invocation) use
  the collection ID as the "dataset" path segment, not split artificially
  per table - the path reflects what the tool actually ran, not a
  finer grain than the real execution.
- `qa_tools/common/check_lifecycle.py` - parses check-lifecycle metadata
  from all 4 tools' own definition formats (dbt's `meta:`, Soda's
  `attributes:`, the ODCS contract's `customProperties:`, a plain dict
  for Evidently), computes a per-check config-hash fingerprint (scoped
  to exclude cosmetic fields), and validates global `check_id`
  uniqueness + changelog-completeness on config changes. 19 tests, all
  against fixtures, not the real ~250 production checks.
- All 4 tools' real check definitions, both datasets, fully retrofitted
  with `check_id`/`introduced_date`/`description`/`changelog`: BDM (25
  dbt + 26 Soda + 27 contract + 2 Evidently = 80) and Child Protection
  (52 dbt + 59 Soda + 62 contract + 1 Evidently = 173) - **254 checks
  total across the whole system**, `check_lifecycle.validate()` clean
  (zero duplicate `check_id`s, zero undocumented config changes).
  Verified against real tool runs throughout, not just YAML parsing -
  a real `dbt build`, a real `soda scan`, a real `datacontract test`
  were each run against both datasets after retrofitting, confirming
  the added `meta:`/`attributes:`/`customProperties:` blocks don't
  break any of the four tools.
- Ran the full real pipeline end to end (`./run_pipeline.sh` for BDM,
  `qa_tools.cp.orchestrate_cp` for Child Protection) to generate and
  commit real `qa_results/` history for all 25 runs (15 BDM + 10 CP)
  across every tool - 100 files, ~8.9MB. Confirmed the dashboard still
  renders with zero console errors afterward (real Playwright check).

**A real design gap found during verification, not anticipated in the
original scoping:** the agreed `check_id` format (`<data-asset-name>.
<agency>.<dataset>.<table>.<column>.<check_name>`) has no segment
distinguishing which TOOL implements a check. This didn't matter for
most checks (each tool's own metric vocabulary - `not_null` vs
`missing_count` vs `nullValues` - already differs naturally), but
several cross-table business rules and FK checks are implemented
identically in more than one tool (Soda and the ODCS contract both
implement the same 7 foreign keys and 3 business rules, in their own
vocabularies, by this project's own long-standing design - see Thread
B's own docstring). Where the check_name chosen for each was the same
generic label (e.g. "date_of_birth range check"), this produced a real
`check_id` collision - found on the BDM side first (5 collisions),
fixed with a `_soda`/`_datacontract` suffix on the affected checks;
applied proactively on the CP side afterward (7 FK + 3 business-rule
checks each got a tool-suffixed check_name from the start, avoiding a
second collision-and-fix round).

**Decided and applied, 2026-09-16 (Keith): tool-qualify every
`check_id` by default.** Not just the ones that happened to collide -
robustness against future collisions that haven't happened yet.
Keith's explicit call on the continuity tradeoff this raised (renaming
all 249 non-collision check_ids sixty seconds after Phase 1 landed
would sever trend continuity with the 25 already-committed historical
runs - see below): "we're only making fake data in development, so we
can just blow it all away and start again." So the mass rename was
done immediately rather than deferred - every real check_id across
both datasets and all 4 tools now ends in `_dbt`/`_soda`/
`_datacontract`/`_evidently` (227 renamed, the 27 that already carried
a collision-driven suffix left as-is since they already qualified).
Applied via a scripted, verified rename (exact-match on the check_id's
full line, longest-string-first, to avoid the one real prefix collision
found along the way - `sex.invalid_percent` vs.
`sex.invalid_percent_recent` - matching as a substring instead of a
whole line would have corrupted the shorter one). Re-verified against
real tool runs, not just YAML parsing, same as the original retrofit:
real `dbt build`/`soda scan`/`datacontract test` succeeded for both
datasets, `check_lifecycle.validate()` clean across all 254 checks
(zero duplicates, zero undocumented changes), a real Playwright check
of the rebuilt dashboard showed zero console errors. Both real
orchestrators (`qa_tools.bdm.orchestrate_bdm`, `qa_tools.cp.
orchestrate_cp`) were re-run end to end, overwriting all 100
already-committed `qa_results/` files in place with the new
check_id-bearing raw output (same run_ids, so this is a normal
overwrite via the pipeline's own generation path, not a manual
delete-and-regenerate) - confirmed via diff that only check_id strings
and inherently-nondeterministic wall-clock/invocation-id fields
changed, not any actual pass/warn/fail result (1214 BDM results: 824
pass/64 warn/326 fail; 1770 CP results: 1464 pass/61 warn/245 fail -
same distribution as Phase 1's original verification). The
"renamed-check reads as retired+reintroduced" consequence flagged
below is accepted as-is for this rename, given only 25 runs of history
existed at the time - not solved with a "renamed from" concept, per
Keith's call above.

`check_lifecycle.py` still doesn't model "this check_id replaced that
one" as a distinct kind of change from retirement - only retirement
and config-change are modeled. Worth remembering if a check_id rename
is ever needed again once real history has accumulated (Phase 2+),
since a rename at that point wouldn't get to lean on "it's all fake
data anyway."

**Decided and built, 2026-09-16 (Keith): a check with no `check_id` is
now a hard error, not a silent skip.** Before this, `check_lifecycle.py`
treated a check with no `check_id` in its metadata as "not yet
migrated" and silently excluded it from parsing - appropriate mid-
retrofit, but a real gap once the retrofit gave every one of the 254
real checks a `check_id`: from that point on, a check with none is a
mistake, not a valid state. `parse_dbt_check_metadata`/
`parse_soda_check_metadata`/`parse_contract_check_metadata` now raise
`MissingCheckIdError` (collecting every offending check in a file into
one error, not failing on the first) naming the file, the
model/table/column, and the check/test/rule - Evidently's
`CHECK_LIFECYCLE` dict is exempt by construction (it's keyed by
`check_id`, so there's no way to add an entry without one). Verified
against all 254 real checks (`parse_*` + `validate()` still clean) and
covered by new tests (`test_parse_dbt_check_metadata_raises_for_tests_
without_check_id`, `test_parse_soda_check_metadata_raises_for_checks_
without_check_id`, `test_parse_contract_check_metadata_raises_for_
quality_rule_without_check_id`).

**Decided and built, 2026-09-16 (Keith, same day, prompted by the
check_id-propagation work for Phase 4's dashboard-wiring): a `check_id`,
once introduced, is PERMANENTLY unique - it must never be changed or
deleted, even once retired.**

Surfaced by Keith's own question while scoping the check_id-propagation
prerequisite for Phase 4: "if that was real data, we wouldn't want to
have to backfill it in... is there any protection against a user
changing the check_id?" Checked `validate()` precisely - there wasn't
any. It only ever checked two things (duplicates in the current set;
config changed without a changelog entry under the SAME check_id) -
nothing looked at whether a check_id present in the previous commit was
still present now. A renamed or deleted check_id passed completely
clean: the old id simply vanished unflagged, and the new one looked
"brand new" - `find_undocumented_changes()`'s own "nothing to have
changed FROM" exemption. Worse than needing a backfill - silent history
orphaning, with nothing telling anyone it happened. (This session's
earlier 227-check_id tool-qualify rename would itself have been blocked
by this rule had it existed then - already explicitly accepted as a
one-time, pre-production exception when only 25 runs of history
existed; this rule only applies going forward.)

**Mechanism, verified for real before building, not assumed:**
retirement was already designed (this section, above) to mean "history
stays fully visible, just flagged inactive" - so the natural fix is one
new rule: *any check_id present in the previous commit must still be
present now, full stop.* Retiring a check must never make it disappear
from what the parser sees, only relocate it. Checked whether each
tool's LIVE, actually-executed config file could keep a retired check's
metadata declared while disabling its execution in place:
- **dbt**: yes - `config: {enabled: false}`. Verified with a real `dbt
  build`: the disabled test is cleanly absent from `run_results.json`
  entirely (no error), while its `meta`/`check_id` block stays fully
  parseable in `schema.yml`.
- **Soda**: no native mechanism. Checked the installed `soda-core`
  package directly, not just docs - its SodaCL parser
  (`soda/sodacl/sodacl_parser.py`) has no `enabled`/`disable`/`active`
  keyword, and its `Scan` class's public API (`soda/scan.py`) has no
  exclude/skip-check method either.
- **datacontract-cli/ODCS**: no native mechanism either. Fetched the
  real ODCS v3 JSON schema from `bitol-io/open-data-contract-standard`
  directly - a quality rule's full property list has no `enabled`/
  `active`/`disabled` field. Confirmed the same against the installed
  `datacontract_specification` package's own `Quality` Pydantic model.

Given that split, Keith's own call: **use one uniform mechanism for all
four tools anyway, not a dbt-specific exception** - a small sibling
`-retired` file per tool (dbt's `enabled: false` route was available but
deliberately not used, for consistency). Retiring a check means
removing its whole metadata block from the tool's actually-executed
file and moving it, unchanged except for adding `retired_as_of`/
`retired_reason`, into that tool's own sibling file - never loaded by
the real tool, only ever read by `check_lifecycle.py`:
- `dbt_project/schema-retired.yml` - deliberately OUTSIDE
  `dbt_project/models/` (dbt's own `model-paths`), verified for real
  that dbt's parser completely ignores a yml file sitting outside its
  configured paths (a real `dbt build` with a garbage-content file
  there succeeded cleanly). Same nested shape as the real `schema.yml`,
  so `parse_dbt_check_metadata()` reads it completely unchanged.
- `contract/bdm-birth-registrations-soda-checks-retired.yml` /
  `contract/child-protection-soda-checks-retired.yml` - real SodaCL
  shape, reusing `parse_soda_check_metadata()` unchanged.
- `contract/bdm-birth-registrations-contract-retired.yaml` /
  `contract/child-protection-contract-retired.yaml` - real ODCS shape,
  reusing `parse_contract_check_metadata()` unchanged.
- `qa_tools/bdm/evidently_check_lifecycle_retired.py` /
  `qa_tools/cp/evidently_check_lifecycle_retired.py` - same
  `CHECK_LIFECYCLE` dict shape, reusing `parse_evidently_check_
  metadata()` unchanged. (Evidently didn't strictly need this split -
  it's plain Python, so retiring a check there was always just "stop
  calling it" - but got the same sibling-file treatment anyway, for one
  rule with no per-tool exceptions to remember.)

**Built:** `check_lifecycle.find_disappeared_check_ids(old_checks,
new_checks)` - any check_id in `old_checks` missing entirely from
`new_checks` is an error; wired into `validate()` as a third error
type, alongside the existing duplicate/undocumented-change checks. All
7 new sibling files created now (empty but validly-shaped, header
comments explaining the mechanism) rather than waiting for a first real
retirement, so `collect_checks()` never hits a missing-file surprise.
`validate_check_lifecycle.py`'s `_YAML_SOURCES`/`_EVIDENTLY_SOURCES`
extended to read each tool's active AND retired file - both feed into
one combined list, so a properly-retired check_id is still found
(just now sourced from the retired file) while a genuine deletion or
rename shows up as missing entirely. **A real robustness gap found
while writing the integration test, not just a test-fixture
inconvenience**: `collect_checks(ref=None)` (the current working tree)
crashed with `FileNotFoundError` on any listed source that didn't exist
on disk yet - it already tolerated a missing path at an old git ref,
just not at the working tree. Fixed the same way, symmetrically.
9 new tests (unit-level `find_disappeared_check_ids()` cases, plus two
full `main()` integration tests against a real temp git repo - one
genuine deletion correctly caught, one proper retirement correctly
passing clean - and a `collect_checks()` missing-source test). Verified
against the real repo: `validate_check_lifecycle.py` reports 258 checks,
zero errors, with all 7 (currently-empty) retired files wired in. Full
pytest (162 tests) + ruff clean.

**Built, 2026-09-16 (same day): `check_id` propagated into every real
check RESULT record, all 8 `run_*.py` modules, all 4 tools - the actual
Phase 4 prerequisite the check_id-permanence and singular-test-gap work
above both grew out of.** Before this, `check_id` existed only in check
DEFINITIONS (schema.yml's `meta:`, the Soda/contract YAML's
`attributes:`/`customProperties:`, Evidently's `CHECK_LIFECYCLE` dict) -
never on the RESULT dicts `evaluate_*()` builds and `write_qa_result()`
commits, so nothing downstream could join a specific result back to its
own check's lifecycle metadata. Verified each tool's join mechanism for
real before wiring it in, not assumed:
- **dbt**: no reliable manifest-based join exists - confirmed
  empirically (again, see the singular-test-gap entry above) that a
  test's `meta`/`config.meta` doesn't survive into the compiled
  manifest. `check_lifecycle.dbt_check_id_lookup(schema_yml_path)`
  reads `schema.yml` directly instead, building a lookup keyed on
  `(model, column_or_None, test_type_or_singular_name)` - `run_dbt_bdm.
  py`/`run_dbt_cp.py` look their own result up in it at write time.
  **A real bug found wiring this in, not a design gap**: the lookup's
  original key (from the singular-test-gap build, `(column, test_type)`
  with no model) collided across datasets - both `stg_birth_
  registrations` and `stg_cp_clients` have a `date_of_birth` column with
  an `accepted_range` test, and schema.yml holds every model in one
  file, so the second one parsed silently overwrote the first's
  check_id. A real BDM result came back tagged with CP's check_id
  before this was caught (checked directly, not assumed - see
  `plans/qa-pipeline.md` item 50's neighbour entry for the full
  account). Fixed by adding `model` to the key. A second, smaller bug in
  the same function: schema.yml's own key for a cross-package macro is
  qualified (`dbt_utils.accepted_range`), but dbt's compiled manifest
  reports that test's name UNqualified (`test_metadata["name"] ==
  "accepted_range"`) - the lookup now strips the package prefix to
  match.
- **Soda**: real scan results carry `resourceAttributes` (a list of
  `{name, value}` pairs, confirmed against a real scan output) directly
  on each check - no cross-check lookup needed, no collision risk (each
  result already knows its own attributes).
  `soda_common.check_id_from_resource_attributes()`.
- **datacontract-cli**: real `Run.checks[]` entries carry
  `qualityDefinition` - a YAML string dump of the original rule,
  `customProperties` included (confirmed against a real
  `DataContract.test()` run) - parsed the same way check_lifecycle.py's
  own `_custom_properties_to_dict()` reads the contract file directly,
  just from a string instead of an already-loaded dict.
  `datacontract_common.check_id_from_quality_definition()`.
- **Evidently**: trivial, as expected - each dataset's own
  `evidently_check_lifecycle.py` now exports its check_id(s) as named
  constants (`PSI_CHECK_ID`, BDM also gets `ROW_COUNT_GROWTH_CHECK_ID`),
  imported directly into `run_evidently_*.py` rather than duplicating
  the literal string in two places.

Every one of the 4 result-construction functions now fails loudly
(`ValueError`, not a silent `None`) if a real check somehow produces no
check_id - matches this codebase's established fail-loud convention
(`MissingCheckIdError`, `MissingGitIdentityError`) rather than letting
a lookup miss surface later as a confusing downstream gap.

**Verified via a real, full 3rd regeneration of `qa_results/` (both
datasets), not just unit tests**: `orchestrate_bdm.py` (6884 results,
4655 pass/373 warn/1856 fail) and `orchestrate_cp.py` (2832 results,
2332 pass/123 warn/377 fail) - identical distributions to the
pre-check_id regeneration. Diffed every regenerated file against the
previously-committed version across all 505 files: every one of the
9,716 real check results now carries a non-null `check_id`, and the
only fields that changed anywhere were `run_timestamp` (expected,
every real run) and, in 13 of BDM's `datacontract.json` files, the
*order* (not content) of `failing_sample_keys` - a genuine, pre-
existing nondeterminism in datacontract-cli's own sample ordering
(same 5 values, different position - same class of already-documented,
accepted nondeterminism as dbt's own `plans/qa-pipeline.md` items
34/38, just not previously visible since no earlier regeneration had
diffed this finely against itself). Full pytest (166 tests, +4 new:
2 for the model-collision bug, 1 for the package-prefix-stripping bug,
1 for the CP Evidently write-path bug already logged separately) +
ruff clean, `check_lifecycle.validate()` unaffected (result records
were never part of what it validates - only check definitions).

**Still not built**: this only gets `check_id` onto every result
record - nothing downstream (the dashboard-data builders, the
dashboard's own JS) reads or uses it yet.

**Built, 2026-09-16 (same day): full per-run stats fidelity in both
dashboard-data builders - the other Phase 4 prerequisite.** Scoped with
Keith first ("shape change scoped first"), not built straight off the
back of the check_id work: `pipeline/build_dashboard_data.py`/
`build_cp_dashboard_data.py`'s `stats.current`/`stats.previous`
(valueCounts, invalid/valid counts), `lastArrival`, and `rowCount`/
`prevRowCount` were all hardcoded to just the latest two runs, even
though the source data (`qa_results/.../dataset_stats.json`) already
carries `value_counts`/`arrival` for every committed run - purely a
reshape gap, not a missing-data one, and no new `qa_results/`
regeneration was needed.

Two real forks resolved before building, both Keith's call:
- **Shape: a dict keyed by `run_id`**, not an array aligned with the
  existing `runs` list (unlike `checks[].history`, which is walked in
  chart order) - the as-of picker needs direct "look up state as of
  this specific run" access, not a scan.
- **Also fix `arrivalHistory`'s `onTime`**, which was hardcoded `True`
  for every run but the latest even though every run's own real
  `max_lag_hours` already existed to compute it honestly - Keith's
  call: leaving it hardcoded while claiming full per-run fidelity
  elsewhere would be inconsistent with the project's own honesty
  standard.

**Additive, not a breaking change**: `stats.current`/`stats.previous`/
`lastArrival`/`rowCount`/`prevRowCount` are computed exactly as before
and stay in the output unchanged - today's dashboard rendering keeps
working without any JS changes. `stats["byRun"]` and a new dataset-level
`arrivalByRun` are new fields alongside them, built from `checks_out[0]`
(the same "primary check" `current`/`previous` already use, post
`rank_for_headline()`) so both stay governed by the same "which check is
primary" choice. `history` entries (and the honest-placeholder path's
own history) also gained a `run_id` field they didn't have before - a
genuine correctness fix along the way, not cosmetic: `run_date` alone
can't key a run uniquely once resupply runs exist (a resupply run
shares its base run's `run_date`, e.g. `run_54_2026-09-10` and
`run_54_2026-09-10_resupply1`), so `byRun` needed an unambiguous key to
match against.

Per-run row counts aren't duplicated into their own dict - `runs`
(already in the output) carries `n_rows_generated`/`row_counts[table]`
per manifest entry already, so nothing new was needed there.

Verified: real rebuild of both `reports/*_dashboard.json` outputs
against the current `qa_results/` history, real `dashboard.
embed_dashboard_data` + a real headless-Chromium Playwright render
check (`dashboard.check_dashboard_renders`) - zero console errors, same
as before this change (confirms the additive fields don't break today's
rendering) - then the local dashboard HTML rebuild was discarded
(`git checkout --`), never committed, per this repo's standing Phase 3
rule. 4 new fixture-based tests, 2 per dataset (the CP dataset-builder
layer had no dedicated test file at all before this - added
`tests/test_build_cp_dashboard_data.py`), including one proving
`onTime` is genuinely computed (a >24h fixture lag correctly reads
`False`), not just checking the happy path. Full pytest (170 tests) +
ruff clean.

**Not yet built**: Thread C's actual as-of picker UI (date picker/
calendar widget, URL param persistence, "no data available"
below-threshold state) and the querying logic that reads `stats.byRun`/
`arrivalByRun` to render an arbitrary past date - both prerequisites
(`check_id` propagation, full per-run stats fidelity) are done now, so
this is the only piece of Phase 4 left.

**Phase 2 (Thread B - dashboard pipeline's read side) - [DONE,
2026-09-16]:**
- The dashboard pipeline's "read all committed history, merge, reshape"
  step - turning Phase 1's committed per-run files into what the
  dashboard actually renders.
- Depends on Phase 1's format existing (doesn't need Phase 1's
  validation logic specifically, just the data shape it produces).

**A real gap found before building, not anticipated in the original
scoping - resolved with Keith upfront rather than discovered mid-build:**
tracing through the existing `evaluate_dbt_bdm()`/`evaluate_soda_bdm()`
(and CP counterparts) showed Phase 1's committed `raw_output` alone
isn't trustworthy or sufficient for this phase. Three real issues, all
in code that predates this whole publishing-and-history effort - not
re-derived here, cited from where they were already fully investigated:
- **dbt bug 1 - the `failures=0` accounting bug**, root-caused
  (`plans/qa-pipeline.md` item 34, `qa_tools/bdm/run_dbt_bdm.py`'s own
  docstring): `dbt/task/test.py`'s `build_test_run_result()` never
  reassigns `failures` off its `0` default when a test's final status
  lands on "Pass" - a test whose real failure count is nonzero but
  under every configured threshold (a genuine pass) silently reports
  `failures=0` in `run_results.json`. Filed and triaged upstream,
  fix unmerged as of our installed version: [dbt-labs/dbt-core#11312](
  https://github.com/dbt-labs/dbt-core/issues/11312).
- **dbt bug 2 - a second, separate, still-NOT-root-caused
  nondeterminism** (`plans/qa-pipeline.md` items 34 and 38): a test's
  reported status/failures flipping between correct and wrong across
  separate `dbt build` invocations of the identical warehouse file, no
  code change in between. Item 38's own deep, controlled repro (40+
  invocations, isolated and under real parallel load) found and fixed a
  related-but-distinct, fully-explained bug along the way (a missing
  `fail_calc:` override in this project's own `schema.yml`) but never
  reproduced the original flip - still open, unexplained, no upstream
  issue filed (points at dbt-duckdb's own query execution path, not
  dbt-core's result-reporting logic, so there's nothing external to
  link beyond this repo's own account).
- **Soda gap - not a bug**: `row_count_total` isn't in `scan_results`
  at all, just a genuine gap in what that structure exposes (no issue
  to cite, upstream or otherwise).

Both dbt bugs only get corrected by the same live query
(`_AUDIT_AGGREGATE_SQL`) against that run's own per-run DuckDB
warehouse, computed *after* Phase 1 already wrote the raw file -
deliberately "at once" per that query's own docstring, since it
re-derives the truth from dbt's own audit table regardless of which of
the two produced a wrong number. Soda's `row_count_total` needs the
same kind of live per-run-warehouse query, same timing problem.

Both live queries need a DuckDB connection to `data/duckdb_runs/`/
`data/cp_duckdb_runs/` - ephemeral, gitignored, regenerated - which
won't exist by the time history gets read back later. Put to Keith
directly (see this file's own AskUserQuestion round, 2026-09-16): bake
the correction into what's committed, keep it strictly local + depend
on regenerated warehouses at read time, or accept the raw
(occasionally wrong) numbers. **Keith's call: bake it in** - as an
additive field, never by mutating what the tool itself reported.

**Built and verified for real:**
- `qa_results_writer.write_qa_result()` gained a second top-level
  field, `verified`, sitting alongside `raw_output` (never inside it -
  `raw_output` stays genuinely, permanently what the tool reported,
  bug included, a real audit trail). `verified` is the same
  fully-resolved, dashboard-ready check-result list `evaluate_*()`
  already built in memory every run - now also captured at the moment
  it's built (which for dbt/Soda is *after* their own live-query
  corrections, not before). All 8 `run_*.py` modules (BDM + CP x 4
  tools each) moved their `write_qa_result()` call to the end of their
  `evaluate_*()` function accordingly - including the 2 tools
  (datacontract-cli, Evidently) that never needed correcting, for
  uniformity: every committed file has the same shape, so the reader
  never special-cases which tools happen to need it.
- `qa_tools/common/qa_results_reader.py` (new) - `read_one()`/
  `read_qa_results()`, walks the committed tree and concatenates every
  run's every tool's `verified` list back into one flat list, in the
  same run-then-tool order a live orchestrator run always produced -
  purely mechanical, no reshaping of its own.
- `qa_tools/bdm/build_results_from_history.py` + `qa_tools/cp/
  build_results_from_history.py` (new) - rebuild `reports/results_bdm.
  json`/`results_cp.json` purely from committed `qa_results/` +
  local `manifest.json` (for `"runs"` only - generator-run metadata
  like delivery dates/resupply chains/dirty_severity stays out of
  `qa_results/`'s scope, per Thread B's own "tool RESULTS only"
  boundary already agreed before this phase started). No real tool
  re-run, no `data/duckdb_runs/`/`data/cp_duckdb_runs/` needed.
  CP's builder reads two `qa_results/` dataset segments per run (the
  collection-level one for dbt/Soda/datacontract-cli, Evidently's own
  table-scoped one) and interleaves them per run_id to match
  `orchestrate_cp.py`'s own construction order exactly, not two
  concatenated blocks.
- Verified by real regeneration, not just unit tests: re-ran both real
  orchestrators end to end (populating every committed file's new
  `verified` field, same 1214 BDM / 1770 CP check-result counts as
  before - no regression from moving the write call), saved their
  live-run `reports/*.json` output aside, then ran the new history-only
  builders and diffed - **byte-identical to the live-run output, aside
  from `generated_at`'s own wall-clock timestamp**, for both datasets.
  Rebuilt the dashboard from the history-only `reports/*.json` and
  confirmed a clean render (real Playwright check, zero console
  errors). 123 tests passing (5 new: `tests/test_qa_results_reader.py`,
  plus 2 more in `test_qa_results_writer.py` for `verified`), ruff
  clean.

**Phase 3 (Thread A - CI-gated publishing) - [complete, 2026-09-16]:**
- Wires Phase 1's validation logic into the CI gate, alongside the
  structural checks and the headless-browser render check.
- Removes any local-publish path - CI is the only path, per Thread A's
  own decision.
- Changelog/activity-feed data logic (reshaping git commit history over
  the committed result paths into feed entries) - the feed's own UI is
  Phase 5, not here.
- Depends on Phase 1 and Phase 2 (needs a working dashboard to publish).

**Two real forks resolved with Keith before building, not assumed:**

1. **Should CI actually rebuild the dashboard, or just gate a human's
   local build?** The old `deploy-pages.yml` only ever republished
   whatever `dashboard/qa-reporting-dashboard.html` a human had already
   built and committed locally - which doesn't actually deliver "CI is
   the only path" (the real build still happens locally) and doesn't
   solve the concurrency problem this whole file's "Why this changes
   things" section names (two people's local builds only ever reflect
   their own machine's `qa_results/` state, not the full merged
   history). **Keith's call: yes, CI-only build** - confirmed via
   AskUserQuestion, matches Thread A's own text.
2. **`dashboard/qa-reporting-dashboard.html` holds BOTH hand-authored
   UI source (committed, edited directly all project) AND two embedded
   data consts - found only once actually tracing through what "stop
   committing it" would really mean, not anticipated when framing
   question 1.** Two ways to actually stop committing the DATA while
   still tracking the UI SOURCE: split into a template + gitignored
   build output (cleaner, actually fixes the mergeability problem, but
   a real rename/restructure), or keep the one file and have CI itself
   commit the data-only diff back (no restructuring, but the exact
   same file that used to be human-committed is now bot-committed -
   doesn't fix mergeability, just moves who commits). **Keith's call:
   keep one file, CI commits the data-only diff back** - explicitly
   choosing not to restructure, even knowing it doesn't resolve the
   mergeability concern the same way the alternative would have.
   **Superseded, 2026-09-16 (same day, Keith reconsidered): the
   template + gitignored build output split, after all** - see the
   dated entry below ("Reconsidered and built") for the full account
   of why this changed and what got built.

**Built and verified for real:**
- `qa_tools/common/validate_check_lifecycle.py` (new) - the Thread D
  gate: parses every real check definition (all 4 tools x both
  datasets) at both the current working tree and `HEAD~1` (Keith's
  call on "old" - the immediately-previous commit on the pushed
  branch, not whatever's currently live on Pages - simplest, no state
  to track, and catches "changed without a changelog entry in the same
  commit" which is the more useful thing anyway), and runs
  `check_lifecycle.validate()` between them. A file that didn't exist
  at `HEAD~1` reads as "no old checks from it," not an error.
  Evidently's plain-dict metadata has no YAML parser to reuse, so old
  content gets `exec`'d as trusted source (our own repo content at a
  real git ref) rather than needing a bespoke parser. 6 tests
  (`tests/test_validate_check_lifecycle.py`), including a real temp
  git repo exercising the actual `git show HEAD~1:<path>` mechanism,
  not a mocked subprocess.
- `dashboard/check_dashboard_renders.py` (new) - the structural +
  render gate: both embedded data consts (`REAL_BIRTH_REG_DATA`/
  `REAL_CP_DATA`) parse as JSON (reusing `embed_dashboard_data.py`'s
  own regex, not a re-derived one, so the two can't drift on what "the
  embedded data line" means), then a real headless-browser load with
  zero console errors AND `#view` (where the whole drill-down app
  mounts) actually populated - not just "the page didn't crash." 4
  tests for the structural half; the render half needs a real
  Chromium, exercised by hand and will be exercised for real by CI
  itself, not worth mocking a browser for in a unit test.
- `.github/workflows/deploy-pages.yml` rewritten (same filename - the
  file's ultimate purpose, publish to Pages, is unchanged, just hugely
  expanded in scope; not worth the churn of a rename nobody asked for)
  into the real build-validate-publish pipeline: regenerates BDM+CP's
  synthetic data and warehouses fresh (fully deterministic - see
  below), rebuilds check results from committed `qa_results/` alone
  (Phase 2, no real dbt/Soda/datacontract-cli/Evidently re-run), reshapes
  into dashboard JSON, embeds it, runs both gate scripts above, and
  only if both pass, commits the data-only change back to the branch
  (`[skip ci]`-tagged, with a bounded retry-on-push-conflict loop) and
  deploys. `permissions: contents: write` - a real, deliberate
  escalation from the old `read`-only workflow, the direct and
  necessary consequence of Keith's decision 2 above.
- **A real finding while proving this out, not assumed to be fine**:
  `pipeline/build_dashboard_data.py`'s/`build_cp_dashboard_data.py`'s
  own DIRECT DuckDB queries (the sex/concern_type value-count charts)
  run against the regenerated synthetic-data warehouses, not just
  `qa_results/` - so the CI rebuild needs the FULL synthetic-data-
  generation step too (`generator.generate_runs`/`generate_cp_runs` +
  warehouse loading), not just Phase 2's committed-history read. Still
  entirely consistent with Thread B's own scope boundary ("tool
  RESULTS only, not the underlying raw synthetic data records, which
  stays gitignored/regenerated") - this data was never meant to be
  committed, CI just needs to regenerate it fresh like any local run
  does, which is fine precisely because it's genuinely deterministic.
- **That determinism was verified for real, not assumed**: rehearsed
  the entire rebuild sequence in an isolated clean git clone (no local
  state, matching a real CI checkout) end to end - both gate scripts
  passed. Ran the synthetic-data-generation step twice from a
  completely empty `data/`, diffed the two runs' `manifest.json` and
  `results_bdm.json` (`generated_at` aside) - byte-identical. (A
  three-way diff against THIS session's own accumulated local
  `data/raw/` - built up over many manual re-runs across a long
  session, never cleared between them - genuinely did differ, which is
  expected and not a bug: `generator/anchor_date.py`'s own docstring
  already documents that regenerating without a pinned
  `GENERATOR_ANCHOR_DATE` lands near real "today," and this project's
  own generator doesn't clear stale leftover files between local
  re-runs either - see `plans/qa-pipeline.md`'s "old dated files aren't
  cleaned up between regenerations" finding. Not a property CI actually
  depends on: every CI run starts from a genuinely clean checkout, the
  same starting point every time, which is the only determinism that
  actually matters here.)
- Documented the new convention (CLAUDE.md, README.md): a local
  `./run_pipeline.sh` run still regenerates `dashboard/qa-reporting-
  dashboard.html` in place for personal viewing, same as always - but
  committing that regeneration yourself is now explicitly against
  convention, since only CI's own gated rebuild should ever land in
  git.

**A real, hard-rule gap Keith raised right after the first live CI run,
not caught while building the above**: Phase 3's CI job was still
regenerating BDM+CP's synthetic data and warehouses (`pipeline.
orchestrate`, `generator.generate_cp_runs`, `qa_tools.cp.
build_cp_warehouses`) so `build_dashboard_data.py`'s/
`build_cp_dashboard_data.py`'s own direct DuckDB queries (value-count
charts, per-check aggregate failing-value data, arrival-lag stats) had
something to query. Harmless *today*, since this PoC's "data" is
synthetic - but Keith's call, put explicitly: **"that's not great, I
don't like that... it's a hard rule that CI never touches production
data"** - not just real data, the PATTERN of CI regenerating anything
data-shaped, because a pipeline that's only safe by accident of today's
data being fake isn't a pipeline that generalizes to a real deployment.

**Scoped via 3 rounds of AskUserQuestion before building, per Keith's
own ask:**
1. **Fix scope**: confirmed via re-tracing the actual live-query call
   sites (found a 3rd one missed on the first pass - CP's own per-table
   arrival-lag stat, `build_cp_dashboard_data.py`'s `build_one_table()`)
   that this covers all 3 chart/stat use cases AND the "runs" manifest
   metadata `build_results_from_history.py` was still reading from
   local `data/raw/manifest.json`/`data/cp_raw/manifest.json` - Keith's
   call: fix all of it, not just the originally-flagged charts, since a
   pipeline that still needs *any* local regeneration for *any* reason
   doesn't satisfy the hard rule either.
2. **Where it's committed**: inside `qa_results/` - a new per-run
   pseudo-tool file (`dataset_stats.json`, `tool="dataset_stats"` via
   the existing `write_qa_result()`), not a separate top-level tree -
   Keith's call, simplest, no new top-level concept.
3. **Who writes it**: `orchestrate_bdm.py`/`orchestrate_cp.py` stay the
   sole `qa_results/` writers (reading `data/raw/manifest.json` back
   and splitting it per run_id themselves) rather than the generator
   committing its own manifest entries directly - Keith's call, keeps
   "what writes to `qa_results/`" a single, consistent answer, and
   leaves the generator exactly the PoC-only, explicitly-out-of-Thread-
   B's-scope thing it's always been.

**Built and verified for real:**
- `qa_tools/bdm/dataset_stats.py` + `qa_tools/cp/dataset_stats.py`
  (new) - `compute_dataset_stats()`, computing value-count
  distributions, arrival-lag, and per-check aggregate failing-value
  data (the `AGGREGATE_SPEC` dicts, moved here from `pipeline/
  build_*_dashboard_data.py` - now the canonical definition, the
  dashboard-building layer imports them back for its own `check_names`
  attach-decision, not a second copy) - against a real DuckDB
  connection, at the one point in the whole pipeline with a legitimate
  one already open. 3 tests (`tests/test_dataset_stats.py`), real small
  DuckDB fixtures, not mocked.
- `orchestrate_bdm.py`/`orchestrate_cp.py`'s `_run_one()` now also
  computes and commits `dataset_stats.json`; `run_pipeline()`/
  `run_pipeline_cp()` read it back (via a new `qa_results_reader.
  read_dataset_stats()`) to assemble `output["dataset_stats"]` - not
  threaded through `_run_one()`'s own return value, since
  `parallel_orchestrate.run_manifest()`'s contract is shared with both
  datasets and not worth complicating for this; also means the live-run
  path and the history-rebuild path (below) share the exact same
  "how do I get dataset_stats for a run" code, so they can't drift.
- `build_results_from_history.py` (both datasets) rewritten to discover
  run_ids via a new `qa_results_reader.list_run_ids()` (a directory
  listing of committed `qa_results/`) instead of reading local manifest
  files - reconstructs "runs" from each run's own committed
  `dataset_stats.json["manifest_entry"]`, sorted by `run_index` (not
  `run_date` - a resupply attempt's own `run_date` is when it actually
  arrived, which would sort it away from its parent delivery;
  `run_index` matches the original generation order and doesn't).
  Neither builder touches `data/raw/`/`data/cp_raw/` at all any more.
- `pipeline/build_dashboard_data.py`/`build_cp_dashboard_data.py`:
  every live DuckDB query removed - `import duckdb` is gone from both
  files entirely. Both are now pure functions of `reports/results_bdm.
  json`/`results_cp.json` alone (specifically its new `dataset_stats`
  key).
- `.github/workflows/deploy-pages.yml`: the "Regenerate synthetic data
  + warehouse(s)" steps removed entirely - this job now touches nothing
  but committed files. `generator/**` dropped from the trigger `paths:`
  list accordingly (a generator-only change has no effect on this job
  any more).
- Verified for real, not assumed: re-ran both real orchestrators
  end-to-end (`--sequential`, same 1214 BDM / 1770 CP check-result
  counts as before - no regression), backfilling `dataset_stats.json`
  for all 25 already-committed historical runs. Diffed every specific
  value this change moved (BDM's sex value-counts + arrival lag, CP's
  concern_type value-counts + per-table arrival lag) against what the
  currently-live, pre-refactor dashboard actually showed - exact
  matches, not just "didn't crash". Full pytest (141 tests, 4 new/
  reworked) + ruff clean. **A real bug this work's own regression
  testing caught, not a hypothetical**: the existing `test_orchestrate_
  reference_run.py` called `_run_one()` directly with a synthetic fake
  entry - once `_run_one()` started calling `write_qa_result()` for
  `dataset_stats` too, this test started silently writing a stray
  directory into the actual project's committed `qa_results/` tree on
  every run, caught by `pytest` genuinely failing (CP's variant hit a
  missing-warehouse-file error outright; BDM's variant "passed" while
  quietly corrupting real repo state, since the combined warehouse
  happened to already exist) - fixed by monkeypatching `duckdb.connect`/
  `write_qa_result`/`compute_dataset_stats` in both test cases, per this
  repo's own "verify a regression test actually fails first, then fix"
  convention.

**Changelog/activity-feed DATA logic - built and verified, 2026-09-16**
(the feed's own UI is still Phase 5 - this is only the data side):

Scoped with Keith across several rounds before building, each one a
real fork, not a rubber-stamp:
- **What a feed line looks like**: one line per dataset, "\<dataset\>
  QA'd by \<person\> on \<the real time it was QA'd\>", with the actual
  commit time available too so the two can be compared - Keith's own
  framing, motivated by wanting a real signal for "QA'd today but not
  published for days."
- **Grouping key**: Keith's own objection to naive git-commit-history
  reconstruction - "someone could easily QA multiple datasets and do a
  single commit," so a commit can't be the feed's unit of grouping.
  Resolved once traced through: `orchestrate_bdm.py`'s/
  `orchestrate_cp.py`'s own `run_timestamp` is already stamped
  identically across every file from one invocation, so grouping by
  `(agency, dataset, run_timestamp)` reconstructs one real QA event per
  dataset for free, regardless of how many datasets later land in the
  same commit.
- **Attribution field**: `run_by` = `git config user.email`, not name -
  email is required to make any commit at all, so it's exactly as
  reliably available as name, and disambiguates two people sharing a
  display name. **Fail loudly and early** if unset (Keith's call,
  matching `check_lifecycle.py`'s `MissingCheckIdError` posture) -
  raised before any real tool runs, not partway through.
- **Where "committed at" comes from - the real design turn**: the
  first design (self-record `commit_sha`/`committed_at` locally, right
  after `git commit`, into a small companion file/ledger) looked
  simpler and was seriously considered, including a pre-commit-hook
  variant that would bake it into the same commit. Both broken by the
  same real problem, surfaced by Keith asking directly how this would
  hold up with multiple people's working copies: a commit made
  locally, pre-push, can still be rebased before it reaches the shared
  branch - rebasing rewrites the commit's SHA and (git's own default
  behaviour) bumps its committer date to rebase time. Self-recording
  "committed at 9:05am" locally, then pushing at 2pm after a rebase,
  leaves a ledger entry that's not just imprecise but silently wrong -
  in exactly the "QA'd today, published days later" scenario this
  feature exists to catch. No local hook (pre-commit, post-commit,
  pre-push) can fix this: none of them fire after the push is actually
  accepted by the remote, so none of them can know if or when a
  rebase will happen. The only thing that knows "did this actually
  land, and when" is the real, already-pushed branch - so `committed_
  at`/`commit_sha` are resolved by reading that, not by recording a
  local guess. Content-based lookup (walking history and reading what
  each commit's diff actually introduced) is also naturally rebase-safe
  in a way SHA-based self-recording can never be: it finds the commit
  wherever the content ends up living, no matter how many times that
  content got replayed onto a new base getting there.
- **Performance at scale, also raised directly by Keith** ("what about
  a thousand commits after a year?"): the first version of the
  content-based lookup did one `git log -S"<value>"` pickaxe search per
  distinct `run_timestamp`, each independently re-walking the same
  commit history - O(events) searches x O(commits) each = effectively
  O(events^2). Fixed before building: walk each dataset's own commit
  history ONCE, read every commit's own diff for whatever
  `run_timestamp` value(s) it introduced, in a single pass - O(commits)
  total. Not a problem this PoC has yet at 25 runs, but the fix was
  real, not deferred, since the whole design exercise was about not
  papering over exactly this kind of thing.
- **Historical data**: the 25 already-committed runs predated `run_by`
  and can't be backfilled honestly (no way to know who ran a run
  that's already over) - Keith's call: nuke and regenerate rather than
  leave them unattributed or fake an answer. (This does collapse
  several genuinely distinct historical `run_timestamp` values - one
  per real regeneration this session - into a single fresh one; a
  known, accepted, explicitly-flagged trade, not an oversight.)

**Built**:
- `qa_tools/common/git_identity.py` (new) - `get_run_by()` +
  `MissingGitIdentityError`.
- `qa_tools/common/qa_results_writer.py` - `write_qa_result()` gained
  an optional `run_by` param, stamped alongside `run_timestamp` (always
  present as a key, `None` when a caller doesn't pass it - same shape
  `verified` already uses). Only `orchestrate_bdm.py`'s/
  `orchestrate_cp.py`'s own `dataset_stats` write passes it - one value
  per run is all the changelog needs, and `dataset_stats.json` is the
  one file guaranteed to exist for every run; the other 8 `run_*.py`
  writes are unchanged.
- `orchestrate_bdm.py`/`orchestrate_cp.py` - `run_pipeline()`/
  `run_pipeline_cp()` call `get_run_by()` once, before any real tool
  runs (fails loudly and early), and thread it through `_run_one()`.
- `qa_tools/common/qa_results_reader.py` - new `read_run_provenance()`,
  reading the `run_timestamp`/`run_by` envelope fields (not
  `raw_output`, which `read_dataset_stats()` already owns and every
  existing caller already assumes is the whole return value - a
  separate function rather than reshaping that one, to avoid breaking
  every existing caller).
- `qa_tools/common/changelog.py` (new) - `build_changelog(agency,
  dataset)`: groups by `(agency, dataset, run_timestamp)` from
  committed file content, resolves `commit_sha`/`committed_at` via the
  single-pass git-history walk described above. Not yet wired into the
  published dashboard JSON or CI (no UI exists to consume it yet - see
  Phase 5) - a standalone, tested, `python3 -m qa_tools.common.
  changelog <agency> <dataset>`-invokable module for now.
- 3 tests (`tests/test_changelog.py`, real temp git repo, same pattern
  as `test_validate_check_lifecycle.py`) - including one that
  specifically exercises Keith's original objection: two datasets QA'd
  and committed together in ONE commit still produce two separate feed
  events, each with its own `run_timestamp`/`run_by`, sharing only the
  commit metadata. 3 more for `git_identity.py` (real subprocess
  against a real temp repo, including the "email configured but empty"
  and "not configured at all" failure modes). 2 more in
  `test_qa_results_writer.py` for the new `run_by` param.
- All 25 historical runs (15 BDM + 10 CP) regenerated fresh (nuked
  first, per Keith's call above) - verified same 1214 BDM / 1770 CP
  check-result counts as before (no regression), `run_by` confirmed
  present and identical across every file from the same invocation
  (one `git config user.email` read per orchestrator run, as designed).
  Rebuilt `reports/*.json` from the fresh history and re-embedded the
  dashboard - both CI gates (`validate_check_lifecycle`,
  `check_dashboard_renders`, the latter via `PLAYWRIGHT_CHROMIUM_PATH`
  for this environment's pre-installed Chromium) pass clean; the local
  dashboard re-embed itself was reverted before committing, per this
  project's own "only CI commits that file's data" convention. Full
  pytest (149 tests, 8 new) + ruff clean.

**Follow-on, same day (2026-09-16) - the CI-vs-human push race, and
removing the commit-back step entirely:**
- After the first live CI runs above, hit two real non-fast-forward
  push rejections doing normal local work on this same branch - CI's
  own `[skip ci]` bot commit (the "commit the rebuilt dashboard data
  back to the branch" step) landed while local work was in progress.
  Both resolved cleanly via `git fetch` + `git rebase` + `git push`, but
  Keith asked about it directly: was this caused by CI writing to the
  same branch as human work? Confirmed yes.
- Keith asked whether collapsing to "one CI/CD process, one branch"
  (classic GitHub Pages branch-based hosting, Pages serving a branch's
  tree directly) would work instead of a dedicated output branch -
  talked through the real mechanism and tradeoffs (would mean giving up
  the modern Actions-artifact deployment model).
- Keith then asked to verify via real research whether the modern
  `actions/deploy-pages` path truly has no way to avoid a shared-branch
  commit-back step at all, rather than taking that as given - per this
  project's own standing lesson against asserting unverified external
  facts (see the `astral-sh/setup-uv@v10` pin incident, this file's own
  item #5). Researched for real (WebSearch + WebFetch on
  `github.com/actions/deploy-pages`, since `docs.github.com` is blocked
  by this environment's network proxy): **the earlier framing was
  wrong** - `deploy-pages` is already artifact-based and branch-
  independent; the race was entirely the fault of this workflow's own
  separate "commit the rebuilt dashboard data back to git" step, not of
  `deploy-pages` itself, which never touches git at all. Corrected this
  directly rather than letting the wrong framing stand.
- That research surfaced two branch-independent fixes, both compatible
  with the modern deployment path: (a) commit the rebuilt data to a
  dedicated output branch instead of the shared dev branch, keeping
  `deploy-pages` as-is; (b) stop committing the rebuilt dashboard data
  to git at all, relying on each Pages deployment's own history (tied to
  the exact commit SHA it was built from) for "what was published when"
  traceability instead.
- Before deciding, Keith asked exactly what's inside the committed
  rebuild record that option (b) would stop capturing. Walked through
  it precisely: the two embedded consts (`REAL_BIRTH_REG_DATA`/
  `REAL_CP_DATA`) are `reports/birth_registrations_dashboard.json`/
  `child_protection_dashboard.json` pasted in verbatim by
  `dashboard/embed_dashboard_data.py` - the reshaped, presentation-ready
  output (check results by dataset, `history` pass/warn/fail/error
  trends, `columns_out`/per-check metadata, `stats` value-count/
  aggregate-failing-value data, `lastArrival`/`arrivalHistory`,
  `rowCount`/`prevRowCount`). Under option (b), what's lost is the
  git-diffable, point-in-time record of exactly that reshaped data at
  each commit (`git log -p`/`git diff` on the HTML file, and checking
  out an old commit to see precisely what was live then with zero
  rebuild). What's NOT at risk either way: `qa_results/` itself (raw
  tool output + `dataset_stats.json` + manifest entries per run) stays
  the permanent, committed source of truth regardless (Thread B,
  untouched by this decision), and the reshaped dashboard JSON/HTML
  stays 100% deterministically reproducible from it at any time via the
  exact same `build_results_from_history.py` -> `build_*_dashboard_
  data.py` -> `embed_dashboard_data.py` chain CI already runs.
  `dashboard/snapshots/*.html.gz` (plans/wider.md #26) is unaffected
  either way, a wholly separate point-in-time archive mechanism.
- **Keith's call, after that walkthrough: option (b)** - stop
  committing the rebuilt dashboard data to git at all. Comfortable
  trading the git-native diffable history for removing the push race
  entirely, given the underlying source of truth is untouched.
- **Built and verified**: removed the "Commit the rebuilt dashboard data
  back to the branch" step from `.github/workflows/deploy-pages.yml`
  entirely (the job's `Prepare site` step already reads the just-
  rebuilt `dashboard/qa-reporting-dashboard.html` straight off the
  job's own working tree via `snapshot_dashboard.prepare_deploy_site()`,
  not from git, so the deploy path needed no other change). Reverted
  `permissions: contents: write` back to `read` (no longer writes to
  git) and removed the now-pointless `if: ... [skip ci]` job guard (no
  bot commit exists any more to guard against re-triggering on). Updated
  the workflow's own header comment with the full incident/research/
  decision writeup, and `CLAUDE.md`'s `dashboard/qa-reporting-
  dashboard.html` entry to match - including the explicit consequence
  that the git-committed copy of this file's two consts is now
  permanently stale, and local rebuilds of it must still never be
  committed (that would just reintroduce the same problem this decision
  was meant to avoid).

**Enforced structurally, 2026-09-16 (same day, Keith's call): a local
pre-commit hook, not just the convention above.** Surfaced doing the
Phase 4 dashboard-data verification work (running `dashboard.embed_
dashboard_data` + a real Playwright render check locally, then
discarding the rebuild via `git checkout --` before committing) -
Keith's instinct, matching this project's standing preference for a
real mechanism over remembered discipline: "let's not have the
dashboard template overwritten by a local build." `dashboard/
check_no_local_embed_committed.py`, wired into `.pre-commit-config.yaml`
as a local hook (`files: ^dashboard/qa-reporting-dashboard\.html$`),
reads the file's staged diff (`git diff --cached -U0`) and refuses the
commit only when EVERY changed line is one of the two `const REAL_*_DATA
= ...;` lines - a genuine hand-edit to the dashboard's own HTML/CSS/JS
(which IS meant to be committed directly) will always touch other
lines too, so this can never block real work, only an accidentally-
staged local rebuild. Verified for real, not just unit-tested: ran
`embed_dashboard_data.py` against the real repo, staged the real
rebuilt file, attempted a real `git commit` through the real installed
hook (`pre-commit install`) - confirmed blocked with the expected
message - then restored the file (`git restore --staged --worktree`)
before committing this change itself. 4 new tests (`tests/test_check_
no_local_embed_committed.py`, real temp git repos + real subprocess
invocations, same rigor as `tests/test_validate_check_lifecycle.py`'s
own git-history tests) - covering the block case, two "genuine edit"
cases (touches other lines only; touches other lines AND the const
lines), and the not-staged case. Full pytest (174 tests) + ruff clean.

**Reconsidered and built, 2026-09-16 (same day): the template + gitignored
build output split, after all - the pre-commit hook above removed as
redundant.** Keith's own follow-up after the hook landed: "what if we
instead had the file as a `.template.html` file? And then let the
builder write to the current file name?" - the exact option framed and
set aside in decision 2 above, back when CI was still going to commit
the data-only diff back (making "not worth the restructuring churn" a
real tradeoff at the time). That justification no longer held once CI
stopped committing anything at all (the decision right above this one)
- at that point the pre-commit hook was already compensating for a
structural gap a clean split would remove entirely, so reconsidering it
was the right call, not scope creep.

Three real forks resolved before building:
- **Template placeholder content: `null`/`[]`, not today's frozen real
  data** - keeps the file people actually hand-edit small and diffable,
  with no risk of stale megabyte-scale JSON sitting in reviewable
  source (a real, additional benefit beyond just closing the commit
  risk - every real pipeline regeneration used to touch a multi-hundred-
  KB diff in the SAME file as hand-authored UI code before this).
- **Remove the now-redundant pre-commit hook** - once the build output
  is gitignored, git can never see a diff on it to stage in the first
  place, so a hook checking for that diff shape can only ever fire on a
  deliberate `git add -f` bypass. Kept as dead-weight complexity would
  have cost more (a hook whose docstring no longer matches reality) than
  it protects against.
- **A fresh clone no longer has an immediately-openable, pre-built
  dashboard - confirmed acceptable.** Only the empty-placeholder
  template exists until `./run_pipeline.sh`/`embed_dashboard_data.py`
  runs. GitHub Pages (the actual public-facing, always-fresh copy) is
  completely unaffected; only a local clone's immediate-open convenience
  changes, and that copy was already frozen/stale under the previous
  design anyway.

**Built:**
- `git mv dashboard/qa-reporting-dashboard.html dashboard/qa-reporting-
  dashboard.template.html` (preserves file history) - the three consts
  (`REAL_BIRTH_REG_DATA`/`REAL_CP_DATA`/`SNAPSHOT_MANIFEST`) nulled/
  emptied out. A real, pre-existing staleness caught fixing this file's
  own header comment while touching it anyway (not otherwise related to
  this change): "10 scheduled deliveries, up to 15 manifest entries"
  corrected to the real current numbers (60/85, since the history-
  deepening work).
- `dashboard/embed_dashboard_data.py` - reads `TEMPLATE_HTML` (new
  constant), writes `DASHBOARD_HTML` (same path/name as before) - the
  only functional code change needed. `dashboard/snapshot_dashboard.py`/
  `dashboard/check_dashboard_renders.py` needed NO changes at all -
  both already referenced the build-output path, never the source,
  confirmed by grepping every reference to the filename across the repo
  before assuming so.
- `.gitignore` - added `dashboard/qa-reporting-dashboard.html`.
- Removed: `dashboard/check_no_local_embed_committed.py`, its
  `.pre-commit-config.yaml` entry, and `tests/test_check_
  no_local_embed_committed.py` (4 tests).
- `README.md`/`CLAUDE.md` updated to describe the new split (edit the
  template, never the build output) in place of the old "don't commit a
  local rebuild" convention-based wording.

**Verified for real, not just that the build succeeds:** a real
`embed_dashboard_data.py` run confirmed the build output lands
correctly ignored (`git check-ignore -v`, `git status` shows the staged
rename cleanly with no interference from the freshly-built ignored
file sitting at that path); a real Playwright render check
(`check_dashboard_renders.py`) against that freshly-built file - zero
console errors, same as before; a real `snapshot_dashboard.py` run
confirmed `SNAPSHOT_MANIFEST` still re-embeds correctly from the real
`dashboard/snapshots/manifest.json` (the verification run's own stray
snapshot file and `manifest.json` diff were discarded afterward, not
committed - not a genuine data-refresh run). Full pytest (170 tests,
down from 174 - the 4 removed hook tests, no replacements needed) +
ruff clean.

**Follow-up, same day: the template must render cleanly on its own,
not just the built output.** Keith's explicit requirement once the
split above landed - opening the raw `.template.html` directly
(before `embed_dashboard_data.py` has ever run) is a real path a
contributor can hit, not just a hypothetical the "build first"
convention alone should have to prevent from crashing. Checked, not
assumed: `buildBirthRegistrations()`/`buildChildProtectionDatasets()`
called `buildRealDataset(null)`/`null.datasets.map(...)` on the
template's own placeholder consts - a real, confirmed crash (verified
with a real headless-Chromium load against the template before fixing
anything). Fixed by falling back to `genDataset()` - the exact same
illustrative-mock generator the other 14 non-real datasets already
use - whenever `REAL_BIRTH_REG_DATA`/`REAL_CP_DATA` are still `null`;
`genDataset()` never sets `isReal`, so the fallback tiles correctly
show as "Illustrative mock data" (the same honest signal every other
non-real tile already gives), not a new UI state to build or maintain.
`dashboard/check_dashboard_renders.py` extended to check BOTH the
built output and the template now (a real headless-browser load of
each, zero console errors, `#view` populated) - the template's render
check doesn't validate embedded-JSON structure the way the built
output's does (its placeholders aren't real pipeline output to
validate), just that it loads and renders without error. Verified for
real: a genuine `file://` load of the template in real Chromium, zero
console errors, confirmed both before (crash reproduced) and after
(clean) the fix - not assumed from reading the code alone.

**Also flagged, same conversation, logged rather than fixed**: a real
UI bug in the check-detail panel's (X) close button (needs several
clicks to actually close after picking multiple "Compared run" dates)
- root-caused and logged as `plans/qa-pipeline.md` item 52, Keith's
own explicit instruction to resolve it at the end of the next phase
rather than now.

**Phase 4 (Thread C - cadence-aware "as of" viewing) - [DONE, 2026-09-16]:**
- Depends on Phase 1 and Phase 2 (real committed history, merged/
  reshaped) - NOT on Phase 3. Worth being explicit about this: the
  numbering reads sequential, but Phase 4 isn't actually blocked by
  Phase 3 - kept in sequence anyway per Keith's own call, for
  simplicity, not because of a real dependency.
- Includes Thread C's own UI (the as-of date picker/calendar widget,
  URL param persistence) - that's part of this phase, not Phase 5 below.
- The picker widget itself and its URL persistence are still exactly
  as built here; only the staleness rule UNDERNEATH it (what makes a
  dataset read "no data" for a given as-of date) later changed - see
  the "Superseded, 2026-09-17" note earlier in this thread and
  `plans/qa-pipeline.md` item 65 (Phase 5j).

**Phase 5 (UI presentation - spans Thread D's check-lifecycle UI and
Thread A's changelog/activity-feed UI) - its own standalone phase,
pinned per Keith's own call. Split into 4 sub-phases, 2026-09-17
(Keith's own follow-up call, same reasoning as the earlier "split into
5 phases" reorg above): the original single-phase bundle mixed one
genuinely substantial piece of work (a real trend-chart architecture
change) in with three much smaller, independent, purely-additive UI
pieces - splitting lets each land and get verified on its own rather
than as one large, harder-to-review change. Depends on Phase 1
(check-lifecycle data to render) and Phase 3 (publish-activity data to
render) - not on Phase 2 directly (though Phase 2 is what makes the
check-lifecycle data actually renderable) or Phase 4. Recommended
build order below; the 4 sub-phases have no dependencies on each other
(each is a self-contained UI addition), so the order is a suggestion,
not a requirement.**

- **Phase 5a (Thread A) - the "📋 Recent activity" panel - [DONE,
  2026-09-17].** Header button ("📋 Recent activity") + side panel,
  same interaction pattern as the already-built "🕐 Past snapshots".
  `dashboard/embed_dashboard_data.py` now also builds `CHANGELOG_FEED`
  by calling `qa_tools/common/changelog.py`'s `build_changelog()` for
  each real dataset scope (Birth Registrations; Child Protection's
  whole collection, NOT once per table, since a real CP run QAs and
  commits all 6 tables together as one event), merging the results,
  sorting newest-published-first (`committed_at`, not `run_timestamp` -
  "published/committed" is this feed's actual subject per the original
  ask), and capping to 30 entries (the exact number was left open in
  this file's own Thread A write-up - "something like the last 20-50" -
  30 picked as the middle of that range rather than left further open).
  Each row shows both timestamps the design called for - when the QA
  itself ran and when it was actually published - noting the gap
  between them only when it's ≥5 minutes (a near-zero gap on every
  normal run/push would just be noise, not the "QA'd today but not
  published for days" signal this exists to catch).

  Real, not hypothetical data to build/verify against: two genuine
  events exist right now (one Birth Registrations publish, one Child
  Protection publish, both from earlier the same day this was built),
  confirming the whole pipeline - real git history walk, real
  `run_by`/`run_timestamp`/`commit_sha`/`committed_at` resolution -
  end to end, not just against a synthetic fixture.

  Found and fixed a real, separate wiring bug while building this:
  `embed_dashboard_data.py` needs `import qa_tools.common.changelog`,
  but `run_pipeline.sh`/`deploy-pages.yml` both invoked it as a bare
  `python3 dashboard/embed_dashboard_data.py` - which puts only
  `dashboard/` on `sys.path`, not the repo root, so the import would
  fail. Fixed by switching both to `python3 -m dashboard.embed_
  dashboard_data` (matching how `dashboard/check_dashboard_renders.py`/
  `dashboard/snapshot_dashboard.py` were already correctly invoked) -
  `run_pipeline.sh`'s own `snapshot_dashboard.py` call switched the same
  way for consistency, though it didn't strictly need to yet.

  Verified for real: a headless-Chromium check confirming the panel
  opens, shows the 2 real entries with correct relative/absolute
  timestamps and the BDM entry's real ~19-minute QA-to-publish gap,
  Escape closes it, and the template's own placeholder (`CHANGELOG_FEED
  = []`) renders a real "no activity yet" empty state rather than
  crashing. New `tests/test_embed_dashboard_data.py` covers the
  merge/label/sort/cap logic in isolation (monkeypatched
  `build_changelog`, not real git/qa_results access). Full `uv run
  pytest` (175 passed) and `uv run ruff check .` clean.
- **Phase 5b (Thread D) - retired checks default out of the
  current-status view, with a toggle to bring them back - [DONE,
  2026-09-17].** Column drawer + overall summary.

  Found before building anything: every one of the 4 tools' `-retired`
  sibling files (`schema-retired.yml`, both `*-checks-retired.yml`, both
  `*-contract-retired.yaml`, both `evidently_check_lifecycle_retired.py`)
  was still empty - no check had ever actually been retired via this
  mechanism, so there was nothing real to build/verify the toggle
  against. Put to Keith rather than assumed: build against zero real
  retired checks (verify later, whenever the first real retirement
  happens) or retire one real check now so this phase has something
  genuine to demo. Keith's call: retire one now, same "verify against
  real data, not just a fixture" standard as everything else this
  session. Picked `source_system_record_id`'s `matches_regex` dbt test
  (BDM) - a real, low-stakes, genuinely-defensible choice: this column
  is BDM's own internal re-extraction-trace ID (COLUMN_META's own
  description), no downstream consumer reads it, so retiring format
  validation on it (`not_null` stays active) is a plausible real
  decision, not a check invented just to have something to retire.
  Moved its whole `meta:` block from `dbt_project/models/staging/
  schema.yml` into `dbt_project/schema-retired.yml` unchanged except
  adding `retired_as_of: "2026-09-17"`/`retired_reason`/a changelog
  entry - confirmed `check_lifecycle.validate()` stays clean (config_hash
  unaffected since meta is excluded from it; check_id doesn't "disappear"
  since it's still found via the retired file) and confirmed (re-reading
  `dbt_project/dbt_project.yml`'s `model-paths: ["models"]`) that
  `schema-retired.yml` sits genuinely outside what a real `dbt build`
  ever scans - no pipeline re-run needed, existing committed `qa_results/`
  history for this check_id (176 runs, always-0/green - this format never
  actually breaks in this fixture) stays exactly as committed, per
  Thread D's "history stays fully visible" rule.

  Second real fork, also put to Keith rather than assumed: should a
  retired check's last-known status still count toward column/dataset/
  agency "current status" (the worst-of rollup that drives every status
  pill), or always excluded - visible via the toggle for history/audit,
  never able to turn a pill red/amber on its own? Keith's call: always
  excluded - retiring a check removes it from what CURRENT health means
  entirely.

  Built: `pipeline/build_dashboard_data.py`/`build_cp_dashboard_data.py`
  both now build a `{check_id: CheckMetadata}` lookup once per run via
  `qa_tools.common.validate_check_lifecycle.collect_checks(None)` (reuse,
  not a second copy of the same active+retired source-file list CI's
  own gate already walks) and attach `check_id`/`retired_as_of`/
  `retired_reason` to every check record - static config-file parsing
  only, no live data/DuckDB access, same CI-safety class as everything
  else in this build path. `buildRealDataset()` (the template) derives
  `retired: ck.retired_as_of != null` client-side (explicit declaration,
  never inferred from absence, matching Thread D's original rule) and
  now computes `column.status` from `c.checks.filter(ck=>!ck.retired)` -
  the one place this needed enforcing, since every status above it
  (dataset/collection/agency) already rolls up from `c.status`.
  `pickRepresentativeCheck()` (the Executive-tier sparkline picker, items
  55/56) got the same exclusion, since a retired check could otherwise
  still coincidentally match a target status and get picked to illustrate
  current health. The column drawer's "Checks run on this column" list
  now renders every check including retired ones (history never hidden),
  behind a `.hide-retired` CSS class toggled by a "Show N retired
  check(s)" checkbox that only renders when `retiredCount>0` - pure
  CSS show/hide off one container class, so the drawer's existing
  index-based check-card click wiring never needed to change. A retired
  check's card gets a "Retired" pill (title tooltip: date + reason) in
  place of its status pill, plus an inline note; the "All checks on this
  column — current run" Passing/Warning/Failing counts always exclude
  retired checks, independent of the toggle. The check-detail panel's own
  header status badge mirrors the same "Retired" pill when opened from a
  retired card - full changelog/description display in the panel body
  stays Phase 5c's job, this is just the header staying consistent with
  where the panel was opened from. Explicitly NOT touched (out of scope
  for this sub-phase, per its own "no chart-rendering changes" framing):
  the "Worst status across all checks — every QA run" historical
  status-dot row still includes retired checks' past contributions
  (correct - they really did contribute to status before their own
  retirement) - the trend-chart gap/marker treatment for retired periods
  is Phase 5d's job.

  Verified for real: `check_lifecycle.validate()` clean against the
  retirement change; rebuilt `reports/results_bdm.json`/
  `birth_registrations_dashboard.json` from committed history (no live
  pipeline re-run); a real headless-Chromium check confirmed the toggle
  starts unchecked with the retired card hidden, checking it reveals
  exactly the 1 retired check with the right pill/tooltip/note text, the
  column's own status pill is unaffected (green, all 7 checks - 6 active
  + 1 retired - present in `column.checks`), and the check-detail panel
  opened from the retired card shows the same "Retired" badge, with zero
  console errors throughout. 2 new fixture tests added
  (`test_build_dashboard_data.py`'s existing 4 tests updated for the new
  required `check_id` field, plus a new
  `test_a_retired_checks_metadata_is_carried_through`); `build_one_table`
  in `build_cp_dashboard_data.py` gained a new required `retirement_by_id`
  parameter, its own 2 existing tests updated to pass `{}`. Full `uv run
  pytest` (176 passed) and `uv run ruff check .` clean.
- **Phase 5c (Thread D) - changelog + description sections in the
  existing check-detail panel - [DONE, 2026-09-17].** Surfaces each
  check's own hand-authored `changelog`/`description` metadata (already
  collected by `check_lifecycle.py` since Phase 1) as new sections of the
  panel that already shows a check's status/history/comparison - mostly
  plumbing already-available data into new panel sections, confirmed no
  new data source needed (Phase 5b's `lifecycle_by_id` lookup already
  parses every check's full `CheckMetadata`, `description`/`changelog`
  included, just wasn't read yet).

  Built: `pipeline/build_dashboard_data.py`/`build_cp_dashboard_data.py`
  (the same `lifecycle_by_id` lookup Phase 5b added, renamed from
  `retirement_by_id` since it's no longer retirement-only) now also
  attach `description`/`changelog` to every check record.
  `buildRealDataset()` (the template) passes `description` straight
  through and maps `changelog` entries into real `Date` objects for
  display - a real, found-before-shipping bug here: the existing
  `toDate()` helper assumes either a bare `"YYYY-MM-DD"` or a
  space-separated `"YYYY-MM-DD HH:MM:SS"` string (both used elsewhere in
  this app for `run_date`/`run_timestamp`) and unconditionally appends a
  `"Z"` - but `check_lifecycle.py`'s own authored changelog dates are
  ALREADY full ISO-8601 (`"2026-09-17T00:00:00Z"`, this file's own
  earlier schema example), so running them through `toDate()` would have
  produced `"...T00:00:00ZZ"` and silently rendered "Invalid Date"
  everywhere a changelog date was shown. Caught before ever hitting a
  browser, by re-reading `toDate()`'s own two branches against the
  actual string shape rather than assuming reuse was safe; fixed with a
  bare `new Date(e.date)` for changelog entries specifically, left a
  comment explaining why the two helpers can't be interchanged.
  `openCheckPanel()` gained two new sections: "What this check does"
  (only rendered when `check.description` is set - not every check has
  one yet) right under the existing dimension/note blurb, and "Definition
  changelog (N changes)" (only rendered when at least one entry exists)
  as the panel's last section - each entry shows its date, a
  Breaking/Non-breaking pill (red border-left + red pill for breaking,
  matching Thread D's "color means the check changed" convention Phase
  5d's own trend-gap work will extend), the human-written description,
  and the author, newest first. A retired check's own retirement is
  just another changelog entry here (see `dbt_project/schema-
  retired.yml`'s real one from Phase 5b) rather than special-cased -
  the "Retired" badge in the panel header (Phase 5b) already covers the
  current-state signal, this covers the audit trail.

  Verified for real: rebuilt `reports/*.json` + the embedded dashboard;
  a real headless-Chromium check confirmed a normal check (`sex`'s
  `accepted_values` test) shows its real hand-authored description with
  no changelog section (zero entries, correctly omitted), and the
  Phase 5b-retired check shows both its description AND its one real
  changelog entry - correct date (Sep 17, 2026), "Non-breaking" pill,
  the actual retirement-reason text, and "Keith Moss" as author - with
  zero console errors. New test `test_a_checks_description_and_
  changelog_are_carried_through` (`tests/test_build_dashboard_data.py`).
  Full `uv run pytest` (177 passed) and `uv run ruff check .` clean.
- **Phase 5d (Thread D) - the trend-chart gap/marker work - [DONE,
  2026-09-17].** Bundled all three related fixes, all traced back to the
  same root cause (`trendChart()`'s `xs()` position function places
  history points by array INDEX, not real elapsed time, so it had no way
  to represent "a gap in time"):

  **Scope decision made before building, not left implicit**: the plan
  text's own "a date-based x-axis, or at minimum a real-time-aware gap/
  break check between adjacent history points" left a real engineering
  choice open. Went with the lighter "at minimum" option deliberately -
  `xs()` stays exactly as it was (evenly spaced by array index), and
  gaps/markers are ANNOTATIONS on top of that existing coordinate
  system, not a rewrite of it. Rejected the full date-proportional
  x-axis: it would also force reworking `wireChart()`'s hover/click
  index math and the tick-label placement, and would make a dataset
  with perfectly regular daily cadence (the overwhelming majority of
  real checks) look uneven for no benefit, all for a distinction only
  the rare gap actually needs to carry.

  **Built, as two independent, composable mechanisms** (both new
  top-level functions, `computeReportGaps()`/`computeChangeMarkers()`,
  kept out of `trendChart()` itself so their logic is inspectable on its
  own):
  - **Reporting gaps** (the un-retirement bug's actual fix, generalized):
    for each adjacent pair of a check's own `history` points, checks
    whether the DATASET's own full run manifest (`ds.runs` - now also
    returned from `buildRealDataset()`, previously only its `.length`
    was kept) has a real run strictly between their two dates that this
    check has no result for. Deliberately NOT keyed off `retired_as_of`
    metadata at all - that only ever describes the check's CURRENT
    state, not a past retire-then-reactivate cycle, and a check reactivated
    today would show no trace of it in its own current definition. The
    gap in `qa_results/` itself (a real run this check has zero result
    for) is the actual, general, metadata-free signal - it would catch
    retirement or any other reason a check went quiet for a run, with
    no need to know or guess why.
  - **Changelog markers**: each of a check's own `changelog` entries
    (already surfaced in Phase 5c's panel) maps onto the first history
    point at or after its date. A BREAKING entry forces a genuine blank
    cut in the rendered path (multiple `<path>` segments, not one) plus
    a small violet double-tick glyph at the cut - a real, deliberate
    visual split, distinct in shape from anything else on the chart. A
    NON-BREAKING entry gets only a small violet diamond marker sitting
    ON the still-fully-connected line - no path split at all.

  **Visual styling decided while building, as the plan file flagged it
  would be**: a new `--change`/`--change-soft` color token (violet -
  `#6B3FA0` light / `#C9A0E8` dark), deliberately a new hue rather than
  reusing green/amber/red/accent, so "the check itself changed here"
  reads as its own consistent visual language. Breaking and non-breaking
  share this exact color per Keith's 2026-09-16 call - shape (a real
  gap+glyph vs. a marker on an unbroken line) is what actually
  distinguishes them, not color. A pure reporting gap (no changelog
  entry, just detected missing data) gets its own THIRD, distinctly
  muted treatment - a dashed `var(--ink-faint)` connector across that
  stretch of line, not a blank cut and not the violet color - since
  "this check went quiet for a while" is a genuinely different claim
  from "this check's definition changed here," and neither should read
  as Thread C's no-data-available EMPTY STATE (a different page
  entirely, not a chart element, so no real collision risk there
  either way). A small legend row (`.change-legend`) explaining
  whichever of these three actually appear is rendered under the chart -
  omitted entirely for the vast majority of checks that have none of
  them, so no new UI clutter for the common case.

  **Verification data, decided deliberately per-mechanism, not
  uniformly**: the non-breaking marker had real data to verify against
  already - Phase 5b's real retirement changelog entry on
  `source_system_record_id.matches_regex_dbt` (`breaking: false`).
  Confirmed for real: opening that check's panel shows exactly one
  violet diamond marker and the matching legend line, with real data,
  no fabrication needed. The breaking-gap and reporting-gap mechanisms
  had no real example anywhere in committed history to verify against -
  the repo's first-ever retirement (this same one) has never been
  reactivated, and no check has ever had a real documented
  `breaking: true` change. Deliberately did NOT manufacture one to get
  real coverage, unlike Phase 5b's retirement: a fabricated real
  THRESHOLD change would risk shifting actual historical green/amber/
  red status values across up to 176 runs of carefully-calibrated real
  data (README.md's documented clean/amber/red counts, several tests'
  own hardcoded expectations) - a real, asymmetric risk the retirement
  never carried (that check was always 0/green, so retiring it changed
  no historical status anywhere). Verified both mechanisms instead
  against clearly-labeled, non-committed fixtures injected directly into
  the live `DATA` object via Playwright (a real check's own history,
  copied and deliberately mutated in the browser only - never written
  to any file) - confirmed the breaking case renders exactly 2 path
  segments and 1 break glyph at the fabricated changelog date, and the
  reporting-gap case renders exactly 1 dashed connector across a
  fabricated 5-run missing window, both with the correct legend line and
  zero console errors. A real end-to-end example of either awaits an
  actual future breaking change or retire/reactivate cycle - flagged
  here rather than silently left unverified.

  Additionally verified: a full sweep opening all 424 real + illustrative
  check panels across every agency (`openCheckPanel()` called directly
  for each) - zero crashes, zero console errors, confirming the new
  logic degrades safely for illustrative mock datasets too (`ds.runs` is
  `undefined` there, `computeReportGaps()` returns no gaps rather than
  erroring). Full `uv run pytest` (177 passed, unchanged - this was a
  pure frontend change) and `uv run ruff check .` clean.

**Phase 6 (test coverage) - added 2026-09-16, Keith's own call, once
Phases 1-5 are otherwise done. Scoped for real 2026-09-17**, after a
subagent survey of actual coverage (211 tests, no zero-coverage modules
in the real BDM/CP data path itself - see the survey's own findings,
not repeated in full here) turned up two things worth fixing more than
any specific missing test: CI never runs `pytest` at all today
(`deploy-pages.yml` only runs the build pipeline + `validate_check_
lifecycle`/`check_dashboard_renders` as Pages gates - the 211-test
suite is enforced nowhere), and the real dbt/Soda/datacontract-cli/
Evidently output-PARSING logic (`qa_tools/*/run_{dbt,soda,datacontract,
evidently}_*.py`) is monkeypatched out in the one test that touches
`orchestrate_bdm.py`/`orchestrate_cp.py` - a deliberate, correct choice
for that one test's own narrow purpose (checking reference-run
forwarding, not re-running real tools), but with the side effect that
nothing ever exercises the real "turn this tool's actual output into
our check-result shape" logic under `pytest` at all - only a real,
slow, full `./run_pipeline.sh` run does.

Real forks resolved (a genuine scoping conversation with Keith, not a
single answer):
- **CI execution: yes** - wire `uv run pytest` into CI. Currently zero
  enforcement path for the whole suite.
- **Coverage tooling: `pytest-cov` + a real threshold**, not just a
  one-time fix-the-gaps pass - Keith's own words, "so we can't silently
  regress" again. The actual threshold number should be set once the
  real achieved coverage from the work below is known, not picked
  first and built toward - an arbitrary a-priori number would either be
  trivially easy (if too low) or force padding coverage with low-value
  tests just to hit it (if picked before knowing what's realistic).
- **`synthetic_data_generator/` stays OUT of scope** - real gap (zero
  coverage), but also currently entirely unused/not wired into the real
  pipeline (see `plans/qa-pipeline.md` #84's own history) - covering
  dormant code isn't a good use of this phase. Revisit noted separately
  (see below) rather than silently dropped.
- **New backend coverage, Keith's own explicit order:**
  1. The real-tool output-parsing logic named above (`run_dbt_bdm.py`/
     `run_soda_bdm.py`/`run_datacontract_bdm.py`/`run_evidently_bdm.py`
     and their CP counterparts) - the highest-value gap, since it's the
     actual "does this project correctly understand what the real tool
     told it" logic, currently unverified by anything except a full
     manual pipeline run.
  2. The other real gaps found by the survey - `qa_tools/{bdm,cp}/
     build_*_warehouses.py`, `build_results_from_history.py` (both
     datasets), `evidently_check_lifecycle.py`/`_retired.py` (both
     datasets), `qa_tools/common/{datacontract,dbt,evidently,
     soda}_common.py`, `pipeline/{aggregate_values,dashboard_check_
     labels,load,orchestrate}.py`, `generator/{anchor_date,names_au,
     presentation}.py` - thinner, more mechanical glue code, real but
     lower-risk than (1).
- **Dashboard JS: yes, but as its own separate follow-up step after the
  backend work above, not bundled into it.** Zero automated JS
  assertions exist today (~2,500 lines of inline logic - cadence math,
  status rollups, drill-down navigation, the new supply-history code -
  verified only by hand-written, throwaway Playwright scripts each
  session). Vitest is Keith's own preference from past experience, open
  to alternatives if it turns out to be a bad fit for a single-file
  inline-`<script>` dashboard with no existing build step - this repo
  has never had a JS test runner or bundler before, so first setup is
  real, non-trivial work in its own right (how the template's inline
  functions get imported into a test file without a real module system
  is the concrete thing to figure out first).
- **Real Playwright end-to-end integration tests: yes, real user-flow
  scenarios**, not just an extension of `check_dashboard_renders.py`'s
  existing render-and-zero-console-errors check - e.g. picking an as-of
  date and confirming the right dataset goes to no-data, clicking a
  supply-history entry and confirming it drills into the right run,
  toggling dark mode and confirming it persists. Confirmed with Keith:
  a well-built suite (a shared pytest-playwright fixture asserting zero
  console errors as part of every single test's teardown, not just one
  dedicated test) naturally subsumes `check_dashboard_renders.py`'s
  built-output check as a side effect of testing real behavior - **but
  the raw TEMPLATE-with-no-real-data-embedded case (illustrative mock
  fallback) needs to stay its own explicit scenario**, since a suite
  built against the real built output wouldn't otherwise cover it.
  Once `pytest` runs in CI (per the CI-execution decision above),
  `check_dashboard_renders.py`'s separate standalone-script CI step
  likely folds into this same suite rather than staying a second,
  parallel gate - the original reasoning for keeping it outside pytest
  ("not worth mocking a browser for here") stops applying once this
  phase is investing in real browser tests under pytest anyway.

Build order for the work above, once started (not yet begun as of this
scoping pass): (1) wire `pytest` into CI early - immediately valuable,
blocks nothing else, and everything built after this point should
already be enforced as it lands, not bolted on at the end; (2) the
real-tool parsing logic; (3) the other backend gaps; (4) set the real
`pytest-cov` threshold once (2)+(3)'s actual achieved number is known;
(5) dashboard JS tests (Vitest, own setup work); (6) real Playwright
user-flow scenarios, absorbing `check_dashboard_renders.py`. (5) and
(6) weren't given a strict relative order by Keith - both are "after
the backend work," not ordered against each other - so either can lead
once reached, revisit which makes more sense at that point rather than
assuming this order is fixed.

**Separately parked, not part of Phase 6 itself**: `synthetic_data_
generator/` test coverage - Keith's own words, "when we come back to
it, have a note that we should consider adding tests for it." See
`plans/data-generation.md` #8 for the actual parked entry
(added alongside this scoping pass) rather than duplicating it here.

**Build progress, 2026-09-18** - Keith's own authorization to "keep
plowing through... do all of phase six" without further check-ins:
- **Step 1 (CI wiring) - DONE.** `.github/workflows/test.yml`, a new
  workflow separate from `deploy-pages.yml` (that workflow's own
  `on.push.paths` filter excludes `generator/**`, and it never ran
  `pytest` anywhere in its existing steps) - `uv sync --dev` then
  `uv run pytest` on every push to this branch.
- **Step 2 (real-tool output-parsing logic) - DONE**, both datasets.
  `tests/conftest.py` gained session-scoped fixtures building small,
  REAL BDM/CP data (real `generator`/`synthetic_data_generator` output,
  real per-run DuckDB warehouses via the actual `build_per_run_
  warehouses.build_all()`/`build_cp_warehouses.build_all()`) - a clean
  reference run plus a red-severity dirty run per dataset, real defect
  injection via `apply_*_presets(severity="red")` rather than
  hand-crafted rows. 8 new test files (`tests/test_run_{dbt,soda,
  datacontract,evidently}_{bdm,cp}.py`, `evidently`'s CP file named
  `test_run_evidently_cp_real.py` since `test_run_evidently_cp.py`
  already existed for a different, narrower concern) call each real
  `evaluate_*()` function directly against these fixtures. Real
  surprises found writing these, not assumed: the CP fixture's row
  counts had to clear the real Soda `row_count` warn floors
  (`contract/child-protection-soda-checks.yml` - `cp_clients` 300,
  `cp_notifications` 600, `cp_carers` 150), which needed a 45,000-person
  base population (not the 70k production scale, but well past an
  initial, too-small 8,000 guess) for the "clean" reference run to
  genuinely have zero real Soda failures; datacontract-cli's custom_sql
  rules only label 3 of 5 real rules (`_CUSTOM_SQL_LABEL`) - a first
  test version wrongly asserted all 5 got a label; Evidently's
  row-count-growth `metric_value` is a positive drop percentage, not
  negative - a first test version had the sign backwards.
- **Step 3 (other backend gaps) - DONE**, every module the scoping list
  named. Coverage across `qa_tools`+`pipeline`+`generator`+`dashboard`
  went from 85% to 91% (`--cov-report=term-missing`, real number, not
  guessed) - `qa_tools/{bdm,cp}/build_results_from_history.py` (0% ->
  ~94%, tested against this repo's own REAL committed `qa_results/`
  history, not a fixture - exactly what CI itself reads), `pipeline/
  load.py` (0% -> 95%, reusing the step-2 `bdm_raw_dir` fixture),
  `pipeline/orchestrate.py` (0% -> 92%, a wiring-only test via
  monkeypatched stubs - genuinely regenerating/loading real project
  data here would itself violate the "CI must never touch data" rule),
  `pipeline/aggregate_values.py` (48% -> 100%, real DuckDB queries
  against an in-memory table), `pipeline/dashboard_check_labels.py`
  (92% -> 100%), `generator/anchor_date.py` (88% -> 100%),
  `evidently_check_lifecycle_retired.py` both datasets (0% -> 100% -
  these are read as plain text by `validate_check_lifecycle.py`, never
  `import`-ed by real code, so a real `import` in a test was the only
  way to close this at all), the "rebuild an existing .duckdb/warehouse
  file" branch in `build_per_run_warehouses.py`/`build_cp_warehouses.py`/
  `pipeline/load.py` (only hit by calling `build_all()`/`load_all()`
  twice against the same path), and the failure/no-match/empty edge
  branches in `qa_tools/common/{dbt,soda,datacontract,evidently}_
  common.py` (87-96% -> 100% each) that the real-tool integration tests
  above don't happen to trigger on their own "happy path" fixtures.
  Remaining gaps in these modules are essentially all `if __name__ ==
  "__main__":` entrypoint lines (never executed under `pytest`, not a
  real gap) plus one genuinely-defensive "shouldn't happen for any real
  committed run" branch in both `build_results_from_history.py` files -
  left alone rather than fabricated a broken committed file just to hit
  it. 9 new test files: `tests/test_build_results_from_history.py`,
  `test_pipeline_load.py`, `test_pipeline_orchestrate.py`,
  `test_aggregate_values.py`, `test_common_helpers.py`,
  `test_dashboard_check_labels.py`, `test_anchor_date.py`,
  `test_evidently_check_lifecycle_retired.py`,
  `test_build_warehouses_rebuild.py`.
- **Step 4 (set the real pytest-cov threshold) - DONE.**
  `pyproject.toml` gained `[tool.coverage.run]` (scoped to `qa_tools`/
  `pipeline`/`generator`/`dashboard` - not `tests/` itself, not
  `synthetic_data_generator/`, deliberately out of Phase 6's scope) and
  `[tool.coverage.report]`, with an `exclude_also` for every
  `if __name__ == "__main__":` entrypoint line (never executed under
  `pytest` - not a real gap, just how every one of these scripts is
  actually invoked) - excluding those bumped the real measured number
  from 91% to 93.73%. `fail_under = 92` - a small buffer below that
  measured number, not the number itself, so one new untested edge
  branch doesn't immediately fail CI, while still catching an actual
  regression. `.github/workflows/test.yml`'s test step now runs with
  `--cov=qa_tools --cov=pipeline --cov=generator --cov=dashboard
  --cov-report=term-missing`, enforcing that same `fail_under` on every
  push. `CLAUDE.md`'s testing-convention bullet updated too - it had
  gone stale ("fast smoke tests... ~3s for 13 tests") the moment step
  2's real-tool integration tests landed (now ~2-3 minutes, 270 tests).
- **Step 5 (dashboard JS tests, Vitest) - DONE.** The concrete question
  this step was scoped around - how does the template's own inline
  `<script>` logic (no module system, ~2,500 lines, hand-authored,
  edited directly per `CLAUDE.md`'s own description) get imported into a
  test file at all - resolved to: it doesn't need to be imported, it
  needs to be RUN, the same way a browser runs it. `tests-js/support/
  loadDashboard.js` loads the real, committed template into a real
  jsdom `Window` via `runScripts:"dangerously"`, which executes both
  inline `<script>` blocks in document order against the template's own
  real markup (the theme button, panels, etc. all already exist in that
  markup - no synthetic DOM stubbing needed beyond `matchMedia`/
  `scrollTo`, two real jsdom "not implemented" gaps, not page bugs).
  Every top-level `function foo(){}` declaration becomes a plain
  `window.foo` property this way (true in any non-module browser
  script, not a jsdom quirk) - confirmed against the real template
  before committing to this approach (a throwaway probe script), not
  assumed. Zero changes to the template itself - the single-file
  hand-authored source stays exactly that, structurally impossible to
  accidentally couple to a test-only module system. Only `const`/`let`
  top-level bindings (`REAL_BIRTH_REG_DATA`, `STATE`, etc.) stay
  unreachable this way, same as in a real browser - tests that need to
  observe those go through the DOM/URL hash instead, not a direct
  reference (see `tests-js/navigation.test.js`'s own comments on this).
  New toolchain, `package.json`/`package-lock.json`/`vitest.config.js`
  at repo root, `npm test` to run, genuinely separate from the Python
  side (no coverage threshold set here - this step's scope was the 4
  named areas below, not full-suite parity with `pytest-cov`). 45 tests
  across 5 files: `tests-js/dashboard-loads.test.js` (the raw-template-
  with-mock-data scenario itself, including a real "zero console
  errors" assertion - the same bar `check_dashboard_renders.py` already
  holds the BUILT output to), `cadence.test.js` (`cadenceLabel`/
  `cycleStartDate`/`cycleLabel`/`addDaysToDateStr` - the JS-side mirror
  of `pipeline/cadence.py`'s `cycle_start()`), `status-rollups.test.js`
  (`checkStatus`/`worstOf`/`rollupStatuses`/`rollup` - including the
  "nodata" special case, STATUS_ORDER's own "must never win a worstOf()
  reduce... must never silently vanish one level up"), `navigation.
  test.js` (`stateToHash`/`hashToState` round-tripping, plus a real
  `navigate()` call driving the actual DOM through jsdom - hash update,
  rail breadcrumb text, exec-grid removal, `resolveContext()` resolving
  the exact real dataset), and `supply-history.test.js`
  (`buildSupplyHistory()`/`rowCountAtRun()` - cycle grouping, newest-
  first ordering within a cycle, resupply attempts as sibling entries
  not nested children, per Keith's own confirmed Stage 2 answer). All
  45 passed on first real run (unlike step 2's BDM/CP batches, no
  test-authoring bugs surfaced here - these are pure functions with
  behaviour read directly from source before each assertion was
  written, not assumed). `.github/workflows/test.yml` gained a second,
  independent `js-tests` job (parallel to the Python `test` job -
  different toolchain, `actions/setup-node@v4` + `npm ci` + `npm test`).
  `CLAUDE.md` gained a `tests-js/` layout-table entry and a pointer from
  the testing-conventions bullet; `.gitignore` gained `node_modules/`.
- **Step 6 (Playwright e2e user-flow tests) - DONE.** `pytest-playwright`
  added as a dev dependency (its own `page` fixture - sync API, no
  `pytest-asyncio` needed, unlike `check_dashboard_renders.py`'s own
  `async_playwright` usage). `tests/test_dashboard_e2e.py`'s
  `built_dashboard_html` fixture runs the exact same real, CI-safe build
  chain `deploy-pages.yml` itself runs (`qa_tools.{bdm,cp}.
  build_results_from_history` -> `pipeline.build_{,cp_}dashboard_data`
  -> `dashboard.embed_dashboard_data`, via real subprocess calls to each
  module, matching that workflow's own steps rather than reimplementing
  their `__main__` write-to-file logic) - session-scoped, built once,
  reused by every test. A shared `clean_page` fixture wraps
  pytest-playwright's own `page` and asserts zero real console errors/
  uncaught exceptions in ITS OWN teardown, so every test gets that bar
  for free, not just one dedicated test - Keith's own confirmed design.
  5 tests, all passing: `TestBuiltDashboardRenders` (`#view` populated,
  zero console errors - absorbs `check_dashboard_renders.py`'s
  built-output half) and the sibling `test_raw_template_renders_with_
  zero_console_errors` (the raw-template-with-mock-data scenario,
  deliberately its own explicit test - a suite built only against the
  real built output wouldn't otherwise cover this path);
  `TestAsOfDatePicking` (a date computed as 1000 days before the
  EARLIEST real committed run - read from `qa_results/` at test time
  via `qa_results_reader`, never hardcoded, so it can't go stale as
  history grows - shows a real "No data" pill); `TestSupplyHistoryDrillDown`
  (clicking a real supply-history row sets the URL's `asof=<that run's
  date>` - a first version picked whichever row rendered first and hit
  a real edge case, a run genuinely dated "today" in this environment,
  where `setAsOfInUrl()` deliberately OMITS the `asof` param when it
  equals `DEFAULT_AS_OF` - fixed by picking a row whose date isn't
  today, not by weakening the assertion); `TestDarkModeToggle` (toggle,
  reload, same theme persists via `localStorage`).

  Environment note, not a design decision: this sandboxed dev
  environment pre-installs a version-pinned Chromium at a fixed path
  Playwright's own default resolution doesn't find (a real, reproduced
  failure - `BrowserType.launch: Executable doesn't exist at .../
  chromium_headless_shell-1234/...`, version mismatch between the
  installed browser and what this Playwright version expects) -
  `tests/conftest.py` gained a `browser_type_launch_args` override that
  adds `executable_path` ONLY when `PLAYWRIGHT_CHROMIUM_PATH` is set,
  the same escape hatch `check_dashboard_renders.py` already had for
  this exact situation - a no-op on a real contributor machine or CI
  (both run `uv run playwright install chromium` normally).
  `.github/workflows/test.yml`'s `test` job gained that install step.

  **Deliberately NOT done**: folding `check_dashboard_renders.py`'s own
  CI step out of `deploy-pages.yml`, even though the new suite now
  covers the same real-browser ground. That script is the actual
  pre-publish gate for a public site - judged too risky to remove or
  restructure unsupervised, on a design point ("likely folds into this
  same suite") that was tentative, not a firm instruction. Left as
  deliberate, explained redundancy: both now check the built output
  renders cleanly, which is safe overlap, not a gap. Revisit with Keith
  if it's ever worth actually merging the two.

**All of Phase 6 is now DONE** (steps 1-6, plus the scoping pass
itself) - see each step's own write-up above for what was built. What's
left, if ever revisited: `synthetic_data_generator/` test coverage
(deliberately parked, not part of Phase 6 - `plans/data-generation.md`
#8), and the "deliberately NOT done" `check_dashboard_renders.py`
folding question just above.

**Real gap found after the fact, 2026-09-18 (Phase 7) - Keith's own
report: "the last GitHub Actions run failed."** Every single `test.yml`
("Run test suite") run had actually been failing since Phase 6 step 2
landed - TWO genuinely separate real bugs, not one, both invisible
locally the entire time.

**Bug 1 - Python version drift.** CI's own resolved Python version
silently diverged from what every local verification this whole
session used. `pyproject.toml`'s `requires-python = ">=3.11"` has no
upper bound and no `.python-version` file existed, so `uv sync` picked
whatever newest-compatible Python the `ubuntu-latest` runner happened
to offer - Python 3.12 - while every local run in this session (and
the sandbox's own system Python) was 3.11.15. Soda Core's own
`soda/common/env_helper.py` does `from distutils.util import
strtobool` - `distutils` was removed from the stdlib in 3.12, so every
Soda-based test failed with `ModuleNotFoundError`. Fixed with the
standard `uv` mechanism: a committed `.python-version` file pinning
`3.11` (`uv python pin 3.11`).

**Bug 2 - missing `dbt deps` in `test.yml` (initially misattributed to
bug 1, confirmed separate by checking the ACTUAL CI run after bug 1's
fix landed).** Every dbt-based test still failed with the exact same
`FileNotFoundError` reading `target/<run_id>/manifest.json`, even once
Python correctly resolved 3.11.16 in CI - proving it wasn't the Python
version after all. Real root cause: `test.yml` never ran
`uv run dbt deps --project-dir dbt_project --profiles-dir qa_tools/
dbt_profiles` (README.md/CLAUDE.md's own documented one-time step,
installs `dbt_utils` - several real checks use macros that package
ships, not dbt-core itself, so `dbt build` won't even compile without
it). `dbt_project/dbt_packages/` is gitignored, never committed, so
every fresh CI checkout genuinely needs this - invisible locally
because this sandbox already had it installed from earlier session
work. Reproduced for real before fixing (moved `dbt_packages/` aside
locally, got the identical error, ran `dbt deps`, confirmed it
resolved) rather than guessed. Fixed by adding the step to `test.yml`.

Neither bug ever touched `deploy-pages.yml` (the actual site-publish
gate) - it only reads pre-committed `qa_results/` JSON, no real Soda
import or dbt subprocess call at all, so the live site was fine
throughout; only the newer pytest-based CI gate (Phase 6 step 1) was
silently red, for the entire span this session's own local
verification kept reporting green. Both fixes pushed as separate
commits, each verified against the REAL GitHub Actions run (via the
GitHub MCP tools, not just local pytest) before moving on - the first
push (Python pin alone) was still red, which is exactly what surfaced
bug 2 as genuinely separate rather than assuming one fix covered both.
The final run (after both fixes) came back `conclusion: success`,
confirmed by checking the API directly.

**Process fix, not just the two point fixes**: Keith's own explicit
ask - "think about how you fix the root cause of this, which is that
you aren't actually monitoring the health of the CI action. You are
just assuming - that's not good enough." `CLAUDE.md`'s conventions
section now carries a standing rule: after every push that touches
CI-relevant files, actually check the real GitHub Actions run (the
GitHub MCP tools' `actions_list`/`get_job_logs`) before considering
the work done - a passing local `uv run pytest` is a necessary check,
never a sufficient one, since CI's environment can silently diverge on
things neither `pytest` nor `ruff` would ever catch.

## Doc updates needed once this starts landing

- `CLAUDE.md`: the `data/raw/`, `reports/*.json` gitignored-convention
  bullet needs an explicit carve-out once `qa_results/`-style committed
  per-run files exist - don't let the two contradict silently.
- `CLAUDE.md`'s own "read this first" list - add this file alongside
  `plans/wider.md`/`plans/qa-pipeline.md`.
- `plans/wider.md` #8 (was #25) and `plans/dashboard.md` #5 (was #26) -
  short pointers added to this file rather than duplicating the design
  there. (Old #27 itself moved fully into this file - see #4 below.)

## Related open items

Redistributed from `plans/wider.md` as part of that file's 2026-09-18
split (see that file's own intro for the full account, and `plans/
running-thoughts.md` item #10 for the status/category schema these
items' tags follow) - pipeline/publishing concerns that had accumulated
there rather than being scoped here from the start. Status values:
`todo` / `investigate` / `in-progress` / `parked` / `done` /
`superseded`. Every item also carries a Component tag - see `plans/
running-thoughts.md` item #10 for the shared taxonomy this and
`CHANGELOG.md` both use. IDs (`publishing-and-history-N`, referenced
elsewhere as `plans/publishing-and-history.md #N`) are permanent once
assigned - never renumbered or reused, even if an item is later
retired, matching `qa_tools/common/check_lifecycle.py`'s own `check_id`
convention. Numbered independently from this file's own Thread/Phase
structure above - these are discrete open questions, not part of any
one Thread's narrative.

1. **[todo, 2026-09-14]** **[Pipeline & publishing]** Medium priority (the
   original tag's own word, preserved through the 2026-09-20 retrofit).
   No CI. Nothing re-runs
   `qa_tools/bdm/orchestrate_bdm.py` against upstream tool releases, so a
   `dbt-core`/`soda-core-duckdb`/`datacontract-cli`/`evidently` update
   could silently break this and we wouldn't know. A scheduled job (even
   a simple cron/GitHub Action) that runs the real pipeline and diffs
   against `reports/results_real.json` would catch regressions early —
   including possibly resolving or changing the dbt-duckdb bug
   (`plans/qa-pipeline.md` #1) on its own. If this happens, revisit
   `plans/performance.md` #4/#5 (parallelizing the ~2.5min runs) — worth
   the complexity for something that runs on a schedule in a way it
   isn't for an occasional manual run.

2. **[done, 2026-09-14]** **[Data generation]** Separate "resupply
   orchestration" from "synthetic data creation per dataset" as a
   distinct architectural concern. Raised by Keith right after `plans/
   data-generation.md` #5 landed, prompted by two things landing at
   once: `generate_runs.py`'s new attempt-chain loop (`plans/data-
   generation.md` #5) is currently entangled directly with
   `daily_batch.py`'s specific generation API (`main()` calls
   `generate_daily_batch()` and `apply_birth_registrations_presets()`
   directly; `_churn_rows()` itself calls `generate_daily_batch()` again
   to manufacture "missing rows that should have been in the original
   file"), and `plans/data-generation.md` #4's research doc (`docs/
   synthetic-data-generation-tools-research.md`) makes a real case that
   the underlying generator (`daily_batch.py`, and/or `population.py`'s
   wider household model) may itself get replaced later (Faker/Mimesis
   name pools, ABS-calibrated IPF structure, possibly a real dynamic
   microsimulation engine like `neworder`/LIAM2). If the resupply-chain
   logic (delay distribution, retry/still-red probability, MAX_ATTEMPTS,
   manifest bookkeeping, delivery/attempt ID scheme) stays welded to
   `daily_batch.py`'s specific function signatures, swapping the
   generator later means rewriting the resupply logic too, not just the
   generation calls.

   **Draft architecture sketch** (not agreed, not built — the actual
   design should follow from the questions below): the orchestration
   loop in `generate_runs.py` doesn't actually need to know anything
   about *how* a dataset's rows are made — it only needs three
   operations to exist for whatever dataset it's driving: (1) generate
   an initial attempt's rows for a given date/seed/row-count/id-offset,
   optionally dirtied to a severity; (2) churn an existing attempt's
   rows forward (small add/modify/remove deltas) to produce the next
   attempt's starting point; (3) (re-)apply a dirty preset at a given
   severity to an existing attempt's rows. That's close to a `Protocol`/
   duck-typed "dataset provider" shape — e.g. `generate(date, seed,
   n_rows, id_offset) -> DataFrame`, `churn(df, seed, run_date,
   id_offset) -> DataFrame`, `dirty(df, severity, seed,
   previous_row_count) -> DataFrame` — with `daily_batch.py` +
   `dirty.py`'s existing Birth-Registrations-specific functions becoming
   the first (and for now, only) implementation plugged into it.
   Everything that's genuinely about *resupply behaviour* rather than
   *row content* (the business-day delay curve, STILL_RED_PROB,
   MAX_ATTEMPTS, the delivery_id/attempt_number/supersedes_run_id
   manifest shape) would move to a module that takes a provider as a
   parameter, rather than living inside a birth-registrations-specific
   script. Genuinely open, not yet decided: whether "churn" is really a
   resupply-orchestration-level concept at all (same shape for every
   dataset) or a dataset-specific concern that belongs behind the
   provider interface too — churn was designed once, for Birth
   Registrations' specific columns (`extract_timestamp` nudging), and
   may not generalise as-is.

   **Scoped via 4 questions, then built** (all recommended answers): do
   the split now as prep rather than waiting for a second generator to
   exist; churn stays behind the provider (it's dataset-specific column
   knowledge, not resupply scheduling); Birth Registrations only for
   now, not designed around Child Protection too; lands in a new shared
   module rather than staying inline in `generate_runs.py`.

   `generator/resupply.py` (new) now owns everything that's genuinely
   about resupply *behaviour*: `MAX_ATTEMPTS`, `STILL_RED_PROB`, the
   business-day delay distribution, `_add_business_days`, and
   `run_delivery_chain()` - a generator that walks one delivery through
   its full attempt chain and yields each `Attempt` (number, arrival
   date, severity, rows), knowing nothing about how those rows were
   made. It's driven by a `DatasetProvider` protocol - `generate()`,
   `dirty()`, `churn()` - three operations any dataset's generator needs
   to support to get resupply simulation "for free." `generator/
   generate_runs.py` is now a thin script: a `BirthRegistrationsProvider`
   class wrapping `daily_batch.py`'s `generate_daily_batch()` and
   `dirty.py`'s `apply_birth_registrations_presets()` (churn's
   implementation moved here unchanged, since it's
   Birth-Registrations-specific - `extract_timestamp` nudging, calling
   `generate_daily_batch()` for "missing" rows), plus a `main()` that
   just writes CSVs/builds manifest entries from what
   `run_delivery_chain()` yields. A future replacement generator (per
   `plans/data-generation.md` #4's research doc) only has to write a new
   provider class: `resupply.py` and its chain logic don't change.

   **Verified, not assumed**: regenerated the full 10-delivery/
   15-attempt batch after the refactor and diffed `manifest.json`
   against the pre-refactor version byte-for-byte - identical (same
   delivery_06 3-attempt and delivery_09 4-attempt chains, same arrival
   dates, same row counts), confirming the split is behaviour-preserving,
   not just a plausible-looking rewrite.

3. **[done, 2026-09-14]** **[Pipeline & publishing]** `generator/`, `pipeline/`, and
   `synthetic_data_generator/` got the same treatment `plans/qa-
   pipeline.md` #84 gave `real_tools/` -> `qa_tools/`: real Python
   packages (an `__init__.py` each, `-m` invocation, real absolute
   imports), not `sys.path.insert()` hacks. Keith asked directly why
   these three still had the hacks qa_tools/ had already been cleaned
   out of, and picked the full fix over a smaller "one shared bootstrap
   helper" alternative he was also offered.

   Triggered by tracing the actual root cause of the dual-`dirty.py`
   import bug (`plans/qa-pipeline.md` #17): `synthetic-data-generator/`
   has a hyphen in its name, which makes it impossible to `import` as a
   real Python package at all - the sys.path hacks in `population.py`,
   `pipeline/orchestrate.py`, `pipeline/build_cp_dashboard_data.py`, and
   `generator/generate_cp_runs.py` existed because of that constraint,
   not just because nobody had cleaned them up yet.

   Surfaced a second, related problem while surveying the damage:
   `names_au.py` and `presentation.py` were ALSO duplicated between
   `generator/` and `synthetic-data-generator/` (kept in sync by hand,
   like `dirty.py` was) - just hadn't drifted apart yet, purely by luck.
   Fixed at the root rather than just renamed: `generator/` now holds
   the one canonical copy of `dirty.py`/`names_au.py`/`presentation.py`;
   `synthetic_data_generator/` imports them from there
   (`from generator.dirty import ...`) instead of keeping duplicates.
   Nothing left in the repo to silently drift apart a second time.

   What changed:
   - `synthetic-data-generator/` -> `synthetic_data_generator/` (`git
     mv`) - the only reason for the whole exercise: hyphens aren't valid
     in a Python package/module name.
   - `generator/__init__.py`, `pipeline/__init__.py`,
     `synthetic_data_generator/__init__.py` added
     (`reference/__init__.py` already existed but the directory it
     marked is gone now - see below); every cross-directory `sys.path.
     insert()` call site (4 files) removed, replaced with real absolute
     imports.
   - Deleted `synthetic_data_generator/dirty.py`,
     `synthetic_data_generator/presentation.py`,
     `synthetic_data_generator/reference/names_au.py` (and the now-empty
     `reference/` directory) - all three were exact or near-duplicates
     of files already canonical in `generator/`. The 6 places that
     imported the local copies (`generate.py`, `population.py`,
     `child_protection.py` x3, `agency_datasets.py`) now import from
     `generator` instead.
   - Every entry-point script that crosses a package boundary now runs
     as `python3 -m <package>.<module>` (`generator.generate_cp_runs`,
     `pipeline.orchestrate`, `pipeline.build_dashboard_data`,
     `pipeline.build_cp_dashboard_data`,
     `synthetic_data_generator.generate`) instead of a bare script path -
     `-m` invocation is what makes the repo root importable at all,
     which absolute imports across packages need and a bare `python3
     generator/foo.py` can't provide (Python only auto-adds the
     script's OWN directory to `sys.path`, not the repo root). `run_
     pipeline.sh`, README, and CLAUDE.md all updated; `run_pipeline.sh`
     also switched every step from a bare `python3` to `uv run python3`
     while this was already being touched (part of the same session's
     `uv`-only cleanup - the two changes landed together since they
     touched the same lines). `dashboard/embed_dashboard_data.py` is the
     one script left alone - it has no cross-package imports at all, so
     a bare script path still works fine and changing it would've been
     pure churn.
   - `pyproject.toml`'s pytest `pythonpath` swapped `["generator",
     "pipeline", "."]` for just `["."]`; every test file that used to
     `import generate_runs`/`import dirty`/etc. now does `from generator
     import generate_runs` etc.

   Verified behaviour-preserving: full pipeline re-run end to end for
   both datasets post-restructure (839 BDM / 1000 CP check results),
   identical pass/warn/fail counts to pre-restructure;
   `synthetic_data_generator.generate` re-run directly and produces the
   same cross-agency-identity output shape. `uv run pytest` (28 tests)
   and `uv run ruff check .` both clean.

   Also part of the same session: Playwright browser verification (used
   throughout `plans/qa-pipeline.md`'s dashboard work) had only ever
   been run through the sandbox's system Python, which happened to have
   `playwright` installed - never through `uv`'s own venv. Added as a
   real `uv` dev dependency instead (`uv run playwright install
   chromium` once, then `uv run python3 ...` drives a real browser) -
   the same "don't depend on something that merely happens to be
   present outside `.venv`" principle as the package-import fixes
   above, for the same reason: this repo is meant to be checked out and
   run by other people evaluating the PoC, on their own machines, not
   just the one it was built on.

4. **[superseded, 2026-09-16]** **[Pipeline & publishing]** Versioning the checks
   themselves, with that version flowing through to the results/data
   each check run captures - Keith's own framing, raised right after
   `plans/dashboard.md` #5's time-travel build: "a useful thing to have
   as a baseline concept we could hook into later," because checks will
   inevitably change ("there will be breaks in checks and changes to
   checks"), and not every change means the same thing for someone
   reading the history.

   The core idea, as he framed it: some check changes are a genuine
   **break in the series** (a threshold moved, the underlying logic
   changed what's actually being measured - the run before and the run
   after aren't really comparable anymore) and some aren't (a label
   reworded, a cosmetic tweak, a bug fix that doesn't change what
   passes/fails). At the time, nothing in this project distinguished the
   two - a check was identified purely by its name/column, with no
   version number or change history of its own, and every real check
   result this project produced was tagged with which RUN it came from
   but never with which VERSION of the check produced it. The trend
   chart (`trendChart()`, `dashboard/qa-reporting-dashboard.html`) drew
   one continuous line across a check's whole `history` regardless - a
   silent threshold change would show up as an unexplained kink in the
   line, not a flagged discontinuity a reader would understand as "the
   check itself changed here, don't read this as organic drift."

   Real connections to what already existed at the time, worth keeping
   in view: `plans/dashboard.md` #5's time-travel snapshots already
   capture a check's `warn`/`fail` thresholds as they stood at that
   moment (each snapshot is self-consistent), so versioning would mostly
   be about making that fact EXPLICIT and queryable rather than an
   accidental side effect of how snapshots happen to work; `plans/
   qa-pipeline.md` #43 (surfacing a check's real SQL/YAML definition in
   the dashboard) is the natural place a version identifier would also
   want to show up.

   **Superseded, same day (2026-09-16)**: picked back up and scoped for
   real - see this file's own Thread D above. Every "not yet scoped"
   question this item originally raised now has a real, built answer
   there (explicit declaration rather than inferred-from-absence, folded
   into Thread B's committed per-run file design). Kept here as the
   original framing/history, not duplicated into Thread D.

5. **[parked, 2026-09-16]** **[Pipeline & publishing]** Root cause of the
   `astral-sh/setup-uv@v10` CI failure (`plans/dashboard.md` #5's
   addendum) - not the specific broken pin itself (already fixed), but
   the pattern that produced it: an external fact needed for a config
   file (a GitHub Action's valid tag format) got asserted from a single
   WebFetch-summarized page rather than checked against the primitive
   source, and the wrong answer went straight into a committed workflow
   file. It then took an actual CI failure - Keith checking the run
   rather than assuming green - to catch it. Worth a real "how do we
   stop this happening again" discussion, because the specific fix (look
   at the tags list, not a summarized release page) doesn't generalize
   on its own to whatever the next instance of this pattern looks like.

   Not scoped yet - open questions to work through together: is this
   narrowly about external version pins in CI/infra config (a smaller,
   more tractable problem - e.g. always resolve a third-party GitHub
   Action ref against its real tags/releases before writing it, never
   from a single fetched page), or does it point at a wider category of
   "asserted external fact, not independently verified, landed in
   something committed" that could show up in other places too (a
   library API's actual signature, a tool's actual CLI flag, a claimed
   default behaviour)? And practically: does addressing it mean a
   written convention (a CLAUDE.md rule, similar in spirit to the
   existing bug-fix-gets-a-test convention), something checked
   mechanically (e.g. a CI step that validates action refs actually
   resolve, catching this class of mistake before merge rather than
   after), both, or something else entirely. Deliberately not conflating
   "log the specific mistake" (done, `plans/dashboard.md` #5's addendum)
   with "fix the pattern" (this item).

6. **[todo, 2026-09-19]** **[Pipeline & publishing]**
   **Priority: HIGH - to FIX, and no longer a "discuss it later"
   (2026-09-19, Keith's own explicit words, quoting `plans/qa-pipeline.md`
   #84's own closing cost back at it): "every new data set currently
   means copy pasting a whole file and manually picking apart which
   parts to keep - that is not tolerable in the short term as we add
   more data sets, so that will need to be addressed as a priority."**

   That is a real change of position on this item, and worth recording
   as one rather than quietly rewriting the entry: this was parked from
   Phase 2 until now on Keith's own earlier, softer framing - "near-
   future not now", "I don't really want a separate file for each
   individual dataset/agency, but I am open to it if needs be" - and
   logged explicitly as "a discussion/brainstorm to have later, not a
   decision made here." Both the urgency and the appetite have moved:
   the copy-paste cost is now named as NOT tolerable, on a short-term
   horizon, tied to datasets actually being added rather than to the
   ~30 target as an abstraction. What has NOT changed is the caveat
   three paragraphs down - #84's finding that the per-dataset LOGIC is
   genuinely different still stands, and "fix" here does not mean
   forcing it into one shared abstraction to reduce file count.

   Revisit the per-dataset file
   architecture across `qa_tools/`/`pipeline/` - originally flagged by
   Keith right after Phase 2 landed. This entry originally recorded only
   the concern and its context, with no proposed solution; the sections
   below are still that, now with a real mandate attached.

   Related to, but a reopening of, `plans/qa-pipeline.md` #84 rather
   than the same question: `plans/qa-pipeline.md` #84 confirmed the same
   "one file pair per tool per dataset" pattern back when there were
   only 2 datasets (BDM, Child Protection), found it wasn't false-DRY
   (the per-dataset half is genuinely different check-to-dashboard-field
   logic, not copy-paste boilerplate), extracted the confirmed-shared
   ~30-40 lines/pair into `qa_tools/common/`, and left the per-dataset
   split itself in place - explicitly flagging even then that "every new
   dataset currently means copy-pasting a whole file." That trade-off
   made sense at 2 datasets. The project's own stated target is ~30, and
   Phase 1/2 above have since added MORE per-dataset file pairs on top
   of the original 4 tool-runners (`build_results_from_history.py`,
   `evidently_check_lifecycle.py`, the per-dataset warehouse builders,
   the two `build_*dashboard_data.py` scripts) - the pattern `plans/
   qa-pipeline.md` #84 already named as a real (if partial) cost is now
   multiplying, not just persisting.

   Nothing about `plans/qa-pipeline.md` #84's actual finding is being
   second-guessed - the per-dataset LOGIC (which tests exist, what they
   mean, dataset-specific reliability workarounds) is still genuinely
   different per dataset and shouldn't be forced into one shared
   abstraction just to reduce file count. What's worth a real
   conversation is the file-per-dataset-per-concern SHAPE itself at ~30x
   today's scale - e.g. whether tool-runner logic could be data-driven
   off each dataset's own config/check definitions inside fewer files,
   whether a plugin/registry pattern per tool (not per dataset) reads
   better, or whether the current shape is still fine and it's
   specifically the Phase 1/2 additions (which are more mechanical/
   generic than the original 4 tool-runners) that should collapse first.

   **Relationship to `plans/tooling.md` #12, since both are now HIGH
   priority and they overlap** - worth being precise so a session
   doesn't do half of each twice. #12 is the broad duplication sweep
   across the whole codebase (`_run_gh` copied three times, the JS<->
   Python mirrors, dead code); THIS item is the narrower, sharper one
   Keith's words above are actually about: making "add a dataset" stop
   meaning "copy-paste a file." #12's own rubric already says to resolve
   this one first or alongside it, and that ordering now looks right
   rather than incidental - this is the item with a concrete, felt cost
   attached to it, and #12 is the sweep that would otherwise keep
   rediscovering symptoms of it. `plans/qa-pipeline.md` #84 supplies the
   method for both (diff the real pairs in full, sort into
   genuinely-shared vs genuinely-dataset-specific, extract only what's
   confirmed) - and note #84 measured 2 datasets, whereas Phase 1/2 have
   since added more per-dataset pairs on top, so its numbers need
   re-measuring rather than reusing.

   Still genuinely unscoped: WHICH of the shapes above is right
   (data-driven off each dataset's own config, a per-tool plugin/
   registry, or collapsing only the mechanical Phase 1/2 additions).
   That's the conversation this entry was always waiting for - it just
   now has a decided outcome to aim at rather than an open question
   about whether to bother.

   **FIRST piece of work under this item (Keith's own call, 2026-09-20):
   settle the agency/collection/dataset/table hierarchy before touching
   anything else here.** It surfaced from a plain factual question of his
   - "what is it that actually groups Child Protection data together as a
   collection?" - and the answer turned out to be four different things.

   The hierarchy IS modelled, three levels, and the dashboard's own data
   tree uses it consistently (`registry-services` -> `civil-registration`
   -> `birth-registrations`; `child-protection-family-support` ->
   `child-protection` -> 6 datasets; the illustrative agencies the same).
   What is inconsistent is everything underneath it:

   1. **The CP collection has four names.** `cp_common.py` says
      `COLLECTION_ID = "child-protection"`; the contract's `id` is
      `child-protection-casework`, its `name` is "Child Protection
      Casework Collection", and its `domain` is `child-and-family-safety`.
      The telling detail - Birth Registrations' contract `domain` is
      `civil-registration`, which EXACTLY matches the dashboard's
      collection id for it. So `domain` looks like it is meant to BE the
      collection, and for CP it simply does not match.
   2. **Birth Registrations has no collection in code at all.**
      `cp_common.py` carries `AGENCY_ID` + `COLLECTION_ID` + a
      `TABLE_DATASET_ID` map; the BDM side carries only `AGENCY_ID` +
      `DATASET_ID`. One models the middle level, the other skips it.
   3. **`check_id` has no collection segment.** The grammar is
      `data-asset.agency.dataset.table.column.check`, but a dashboard URL
      is `/agency/X/collection/Y/dataset/Z`. The URL carries a level the
      identifier does not, so a check's collection cannot be derived from
      its own id. Found while scoping `plans/qa-pipeline.md` item 25's
      REQ-QAC-023, which writes that grammar down - it was taken from the
      module docstring without noticing it skips a level.
   4. **The storage layer picks the OTHER model.** `qa_results/` keys CP
      by `<agency>/<collection>/<run_id>/` with ONE set of 5 tool files
      per run covering all 6 tables, and BDM by
      `<agency>/<dataset>/<run_id>/` with the same 5 files. So on disk,
      CP's collection is stored exactly the way BDM's dataset is - one
      unit, one run, one set of files - and the 6 tables are split out
      afterwards by `TABLE_DATASET_ID`.

   **Keith's own framing of the choice**, recorded in his words rather
   than paraphrased: it could be "a collection containing multiple data
   sets where each data set has one table", or "drop collection and just
   have one data set, for example child protection, having multiple
   tables". **He leans toward keeping collection** because it groups
   things well, "even if it means inventing some collection names for
   smaller agencies".

   **His stress test - "if we didn't have a collection and we had one
   dataset with multiple tables, is that something we'd also support?" -
   already has an answer in the code, and it is the most useful finding
   here.** Yes, and not hypothetically: that IS how CP is stored today
   (finding 4). The system currently implements BOTH models at once - one
   dataset holding multiple tables at the storage layer, a collection of
   single-table datasets at the presentation layer - and bridges them
   with a hand-maintained table-to-dataset map. That is not a choice
   between two designs so much as a decision about which of the two the
   system should stop pretending not to have.

   **DECIDED 2026-09-20, and the framing changed on the way there.**
   The question started as "which layer gives way" - split `qa_results/`
   per dataset, or accept that a dataset holds several tables. Keith's
   first answer was storage follows presentation ("I'm not keen on
   splitting things out via the hand maintained table dataset ID map").
   Then he asked a better question that reframed the whole item, and it
   is the one to carry forward: **what does a partial resupply
   require?**

   His scenario - some CP tables come back clean, two of the six get
   resupplied. Can the tools run against just those two, keep the
   original good four, and still evaluate the referential-integrity
   checks between them?

   **Checked against the real code: no, on every path, and by design.**
   - A local run's warehouse is a self-contained snapshot of one
     delivery - `data/cp_duckdb_runs/<run_id>.duckdb`, "each containing
     that run's 6 tables". Nothing composes a warehouse from two new
     tables plus four from an earlier run.
   - CP's resupply simulation treats a delivery as whole - "CP's own
     payload is a whole delivery's worth of tables at once" - so a
     resupply re-sends all six.
   - The AWS event-driven path enforces the same rule explicitly, via
     `qa_tools/cp/completion_tracker.py`. Worth being precise, since an
     earlier draft of this entry overstated it - that module is imported
     ONLY by `aws/lambda_handlers/cp_ingest_handler.py` and the CDK
     stack. It constrains nothing you can run locally. It is a third
     expression of the same intent, not a third live constraint.

   And the referential-integrity half specifically: running against only
   the two resupplied tables would evaluate `placements.carer_id ->
   carers` against a warehouse where `carers` is absent. Not a check
   that quietly passes - an error or a false red on every row. Which is
   exactly the "incomplete/wrong cross-table-check result" the
   completion signal was built to prevent.

   **Keith's decision, in his own words: "we're going to have to move to
   a model where the shape is per dataset runs against a shared
   warehouse composed of the current good version of every table,
   because that's just the reality of how it works."**

   That is a stronger basis for this work than tidiness. Partial
   resupply is ordinary in the real world - one agency resends one file
   - and it is *impossible* while results are stored per collection,
   because a single `run_id` would have to mean different things for
   different tables.

   **What the model requires:**
   - Per-table lineage - each table has its own arrival history and its
     own current version, rather than sharing one delivery's `run_id`.
   - A composed warehouse - assembled from the current version of every
     table, not a snapshot of one delivery.
   - Per-dataset QA runs, each triggered by its own table's arrival.
   - Cross-table checks running against that composed warehouse, so they
     see real current data on both sides.
   - `qa_results/` keyed per dataset, which is where this item started.
   - `TABLE_DATASET_ID` retires.

   **What falls out for free:** the `raw_output` problem disappears. It
   is 75% of each run's bytes and cannot be split per dataset without
   either duplicating it six times or filtering a document whose
   `metadata`/`elapsed_time`/`args` describe one whole invocation -
   which would break the "genuinely unmodified tool output" guarantee
   that makes it worth keeping. If the tools run per dataset, its output
   is per dataset already. Nothing to duplicate, nothing to filter.
   Birth Registrations is unaffected throughout (one table), which is a
   good sign - the model generalises rather than special-casing CP.

   **ALL THREE ANSWERED 2026-09-20 evening (Keith), and the four
   hierarchy findings above re-verified against the real code first
   rather than trusted from this prose.** Verification: CP's collection
   really does carry four names (`COLLECTION_ID = "child-protection"`,
   contract `id: child-protection-casework`, `name: Child Protection
   Casework Collection`, `domain: child-and-family-safety`), while Birth
   Registrations' contract `domain: civil-registration` exactly matches
   its dashboard collection id; the BDM side really carries only
   `AGENCY_ID` + `DATASET_ID`; `_SEGMENTS` really is
   data_asset/agency/dataset/table/column with no collection; and
   `qa_results/` really does key CP at collection level (18 run dirs)
   against BDM at dataset level (352). All six CP datasets share the
   same 18 run_ids today - one collection-level timeline.

   1. **"Good" is the wrong word - it is the CURRENT version, always.**
      The composed warehouse holds what the agency actually sent, and
      status is reported rather than acted on. A red table is still the
      table. Rejected holding the last green version: the warehouse and
      the real delivery would silently disagree, and every downstream
      number would inherit that - a green dashboard built on last week's
      data is the worst failure this system could have. This no longer
      waits on `plans/conceptual-design.md` Thread A; Thread A decides
      what a human may DO about an amber supply, which is a different
      question from what the warehouse contains.
   2. **A cross-table check result belongs to its own cross-table
      scope, not to any one dataset.** Rejected recording it against the
      triggering dataset (a viewer of `carers` would never see a check
      concerning `carers` change) and rejected duplicating it against
      every table it touches (two records to keep in step, and a check
      appearing in a dataset's history without that dataset changing).
      This matches what these checks already are on the page:
      REQ-DASH-033 gave them their own section for exactly this reason,
      so the lineage follows the presentation rather than fighting it.
   3. **Supply history survives per-table lineage - VERIFIED, not
      assumed.** `buildSupplyHistory(d)` reads only the dataset object
      it is handed (`d.runs`, plus `statusByRun`/`arrivalByRun` keyed by
      run_id), so six timelines are six calls. Driven in a real browser
      against the built page: `cp-placements` doctored down to 9 of its
      18 runs, as a table resupplied on its own schedule would be,
      produced 7 well-formed chains carrying all 9 entries, zero console
      errors. Thread A's "dataset-agnostic by construction" claim is
      real. Scope of that check, stated so it is not over-read: it
      covers the chain-building logic. Whether the as-of picker and the
      rendered supply-history UI also hold up is untested and worth
      checking when this is built.

   **Two scope answers, 2026-09-20 evening (Keith), settled because
   `delivery-scoper` cannot resolve either from the files and cannot
   follow a thread adaptively mid-run:**

   - **The committed `qa_results/` history may be REBUILT for both
     datasets. An explicit, approved exception to a hard rule**, in his
     words: "given we're making big structural changes, I'm happy to
     make an exception and approve rebuilding what's there for child
     protection and obviously for BDM as well." `CLAUDE.md` otherwise
     states that `qa_results/` is the permanent source of truth and that
     nothing in it should ever be deleted or regenerated away, so this
     is a one-off for this restructure, granted for it, and does not
     generalise to any other work.

     What it actually costs, measured rather than assumed before
     acting: all 370 `dataset_stats.json` files carry a single
     `run_by`, and their `run_timestamp` values span 2026-09-18T04:01
     to 2026-09-19T06:16 - about 26 hours, two days before the
     decision. So this is machine-generated history from one identity,
     not a long-accumulated multi-person QA record, and what a rebuild
     rewrites is the dashboard's own activity feed
     (`qa_tools/common/changelog.py` derives "who QA'd what, when" from
     exactly those two fields plus git history). Nothing irreplaceable.
     Note also that a rebuild is necessarily LOCAL - it re-runs the real
     tools against regenerated data, which CI must never do.

   - **The synthetic generator is IN SCOPE.**
     `generator/generate_cp_runs.py` currently emits "a whole delivery's
     worth of tables at once", so per-table arrival cannot even be
     exercised without changing it. Keith: "yes, that should be part of
     this work." It is not a separate follow-up.

   **NOT needed before scoping, deliberately**: which of the three
   shapes is right (data-driven off each dataset's own config, a
   per-tool plugin/registry, or collapsing only the mechanical Phase 1/2
   additions). That is an architecture question and belongs to
   `delivery-architect` AFTER scoping - `delivery-scoper` needs to know
   what is in scope, not how it is built.

   **CORRECTION to finding 2 above, verified 2026-09-20 night.** It says
   "Birth Registrations has no collection in code at all". Not quite:
   there is no `bdm_common.py`, and all four `qa_tools/bdm/run_*_bdm.py`
   modules DO each declare `COLLECTION_ID = "civil-registration"` -
   copy-pasted four times - while `orchestrate_bdm.py` and
   `build_results_from_history.py` declare only `AGENCY_ID` +
   `DATASET_ID`. So BDM names its collection and then never passes it to
   `write_qa_result()`, which is why it vanishes at the storage layer.
   Raised by `delivery-scoper` and confirmed by reading the four files.
   The inconsistency is real; it is a duplication problem as much as an
   omission, which makes it a better fit for the "stated once" treatment
   than the original wording suggested.

   **SCOPED 2026-09-20 night by `delivery-scoper`, awaiting Keith's
   sign-off. Nothing applied to `requirements.yaml` yet, deliberately -
   several criteria are provisional on the questions below.** Eight
   small requirements proposed, ids to be re-checked at apply time
   (highest live id was `REQ-DASH-033`):

   - per-dataset arrival lineage
   - the composed warehouse
   - per-dataset QA runs
   - cross-table checks get their own scope and lineage
   - `qa_results/` keyed per dataset, plus the approved one-off rebuild
   - one hierarchy stated once, including in a check's own identity
   - the generator delivering one table at a time
   - supply history and the as-of picker under per-dataset arrivals
     (the stated limit of this item's own verification)

   **Eight questions for Keith, recorded here so they survive the
   session that produced them:**

   Set 1 - the model's own forks.
   1. **Check_ids and a collection segment.** Rename all 258 ids to carry
      `collection` (and absorb `plans/running-thoughts.md` #22's
      `table`/data-asset changes at the same time, one rename instead of
      two), rename for `collection` only, or do not touch check_ids and
      resolve a check's collection through the single hierarchy
      definition instead. The first two need an explicit exception to the
      permanence rule below.
   2. **Does "these six arrived together" stay a recorded fact?**
      Per-dataset arrival ids only, or per-dataset ids plus a delivery id.
   3. **How is a historical arrival re-evaluated** once the warehouse is
      composed rather than snapshotted? Point-in-time composition,
      current composition only, or split by check type.
   4. **When does a cross-table check re-run?** On any arrival it depends
      on, on any arrival in the collection, or on its own cadence.

   Set 2 - the non-functional ones it could not settle from the files.
   5. **Timestamps on rebuilt history.** Preserve the originals, stamp
      the rebuild, or carry both.
   6. **A check whose other side has never arrived.** Report not
      evaluable, fail loudly and stop, or defer silently until both
      sides exist.
   7. **Are superseded table versions kept?** Every version, current
      only, or a bounded window. This one decides whether question 3's
      point-in-time option is even available.
   8. **How far may the composed warehouse span?** Per collection, per
      agency, or the whole data asset. Real privacy question in a real
      deployment, since composition puts several agencies' tables in one
      place.

   **The collision question 1 turns on is real, confirmed by reading
   it**: this file's own line 991 states a check_id "once introduced, is
   PERMANENTLY unique - it must never be changed or deleted". 1,850
   committed history files, 129MB, carry today's ids. Any rename needs
   its own recorded exception on the same terms as the `qa_results`
   rebuild, not one inherited from it by implication.

   **One scoper claim NOT confirmed**, flagged so it is not carried
   forward: it suggested `validate_tail_uniqueness()`'s own docstring
   calls its collision "structurally impossible". No such wording exists
   in `qa_tools/common/check_id.py`. Whether that gate still guards
   something real under the new model is still worth settling while the
   grammar is open - but not on that basis.

   **Still to do**: get Keith's answers to the eight above, then apply
   the requirements for sign-off. Nothing here is built.

   **Three real questions this opens, flagged not resolved:**
   1. **What does "good" mean in "current good version"?** If
      `cp-placements` arrives red, does the warehouse use it - it is
      what the agency actually sent - or hold the last green one? A QA
      tool that quietly substitutes older data for bad data is not
      reporting reality. The likely answer is "current version" full
      stop, with status reported rather than acted on, which makes
      "good" the wrong word. This is adjacent to
      `plans/conceptual-design.md` Thread A's amber accept/reject
      governance and should be settled with it, not separately.
   2. **A check result stops being a pure function of one run.** If
      `placements` is resupplied and `carers` is not, the FK check
      re-runs and may change answer later when `carers` is resupplied -
      without `placements` changing at all. So a cross-table check's
      result depends on two tables' versions. Which dataset's history
      records it, and what a viewer is told when it changes without its
      own dataset changing, both need deciding.
   3. **What a "run" means, and what that does to supply history.**
      Today `run_id` is one delivery across six tables; Phase 7's
      resupply-chain redesign derives chain membership from per-run
      aggregate status. Per-table arrivals change what a chain is - six
      independent timelines rather than one. Worth checking whether the
      existing supply-history UI genuinely survives that, given Thread A
      claims it is "dataset-agnostic by construction".

7. **[done, 2026-09-19]** **[Pipeline & publishing]** Both GitHub Actions
   workflows are pinned to a single, hardcoded session branch name -
   `on: push: branches: [claude/new-session-en9qen]` in
   `.github/workflows/test.yml`, and the equivalent in
   `deploy-pages.yml`. That branch was the working branch of the session
   that last edited them; every session since gets a different one, so
   **neither workflow fires at all for the current branch** and CI
   silently does nothing.

   Found 2026-09-19 while following `CLAUDE.md`'s own standing "a
   passing local pytest is NOT evidence CI is green - actually check the
   real run" rule after pushing item 74's fix: there was no run to
   check. `list_workflow_runs` filtered to this session's own branch
   returned `total_count: 0`, while the unfiltered list showed 335 runs,
   every recent one on `claude/new-session-en9qen`.

   Worth noting precisely what this does and doesn't break, because it's
   easy to over- or under-read: nothing is broken on the branch the pin
   names, and the last run there (`b0585da`) was genuinely green. The
   failure mode is subtler and matches the exact incident that rule was
   written for - CI appearing fine because it isn't running, rather than
   failing loudly. `workflow_dispatch` is a real workaround (used for
   item 74's own push, against this branch's ref, and it works), but it
   depends on someone remembering, which is the same class of thing the
   rule already says not to rely on.

   **Fixed 2026-09-19** (Keith's call: "open to moving to PR triggers if
   that's cleaner, but also a Claude glob if simpler"). Chose the
   `claude/**` glob, and the deciding fact was one nobody had checked:
   **this repo has no trunk at all.** `list_branches` returns three
   branches, every one a `claude/*` session branch, each continuing from
   the last - there is no `main`. So a `pull_request` trigger has
   nothing to target, and the PR option isn't "cleaner" here, it's
   inapplicable without first inventing a trunk. Worth recording since
   the option sounded reasonable in the abstract.

   **A third workflow had the identical pin, found only by grepping
   after fixing the first two**: `.github/workflows/ticket-sync.yml`.
   That one matters more than the other two, because it holds
   `issues: write` and opens real GitHub issues on a public repo - and
   its own trigger `paths` include itself, so the very commit fixing its
   pin would fire it. Its own comment records that Keith had explicitly
   enabled its push trigger at the time; the dead pin meant it had
   nonetheless never once fired. Flagged to him with the real number
   before touching it - 3 datasets currently read red
   (birth-registrations, cp-carers, cp-placements), down from all 7
   before `plans/qa-pipeline.md` item 74's fix, so the first real run
   opens 3 tickets rather than the noise storm that item's own write-up
   had been holding this back to avoid - and his call was to fix the pin
   and let it fire.

   `test.yml` also gained a real `concurrency` group
   (`test-${{ github.ref }}`, `cancel-in-progress: true`): this branch
   pushes several times a session and only the newest commit's result
   means anything. Keyed on the ref, so two concurrent sessions can't
   cancel each other. `deploy-pages.yml` already had its own
   `concurrency: pages` group, so deploys serialise rather than
   interleave.

   **A real second half to this, found immediately after pushing the
   fix and NOT solvable from code**: `deploy-pages.yml` now fires, and
   then fails in ~2 seconds with no steps run and no logs (a 404 on the
   log download). That is the signature of GitHub's own **environment
   protection rules** rejecting the branch: the job declares
   `environment: github-pages`, and that environment is configured in
   repo Settings to allow deployments only from specific branches -
   almost certainly still just `claude/new-session-en9qen`, the same
   dead branch this whole item is about. So the pin exists in TWO
   places, and fixing the workflow file only fixed one of them.
   Diagnosis is high-confidence but not directly confirmed: this
   session's proxy blocks the `/repos/{owner}/{repo}/environments/...`
   API path, so the rule couldn't be read back. Supporting evidence:
   the same workflow succeeded on the old branch (run 163), a
   job-level `if:` evaluating false would report "skipped" not
   "failure", and the `concurrency: pages` group would report
   "cancelled".

   **Keith's to fix, not a session's** - repo Settings -> Environments
   -> `github-pages` -> "Deployment branches and tags" -> allow
   `claude/**` (or whatever pattern matches the glob above). Deliberately
   NOT reverted to a pinned branch to hide it in the meantime: a visible
   failure is strictly better than the silent non-run this item started
   as.

   **Done by Keith, 2026-09-19 evening - and the diagnosis is now
   CONFIRMED, not just high-confidence.** He added the `claude/**`
   wildcard to the environment's allowed branches, and the very next
   push flipped the workflow's behaviour completely: instead of failing
   in ~2 seconds with zero steps and a 404 on logs, it ran properly and
   finished `success`. That's the first time all three workflows have
   run and passed on a session branch since the pin broke - `Run test
   suite`, `Sync QA status to GitHub Issues`, and `Build, validate, and
   publish the dashboard`, all green on the same commit. The earlier
   inference (environment protection rejecting the branch, unreadable
   from here because the proxy blocks the environments API) held up
   exactly.

   Real, user-visible consequence worth naming: the live published
   dashboard had not been rebuilt since before the pin broke, so this
   is also the deploy that finally carries `plans/qa-pipeline.md` item
   74's corrected statuses to the public site - the end of the "all 7
   datasets read red on every run" era for anyone actually looking at
   it.

   **Now verified against the real live site, not just inferred from the
   workflow's own conclusion** - Keith allow-listed
   `keithamoss.github.io` minutes later (see `CLAUDE.md`'s own audited
   blocked-domain list), which made the check that this item originally
   had to skip actually possible. Driving the real published URL in a
   real browser and using the page's OWN
   `buildRealDataset()`/`checkStatus()`/`historyStatus()`: **30,561
   rendered statuses compared against each tool's own recorded verdict,
   zero disagreements, and zero results missing a verdict** (locally it
   had been 198 before the placeholder fix, so that shipped too). The
   live page's embedded `GITHUB_LINKS` commit confirms it was built from
   `24b2560`, the commit carrying all of item 74's work. This is the
   first time this project has verified its own published output at the
   render layer against the real source of truth, rather than trusting a
   green workflow.

   **One residual risk, named rather than silently accepted**: with a
   glob, any `claude/*` branch can publish to the live public site. That
   matches how this project actually works (sessions are sequential, so
   "newest push publishes" is correct) and the pages concurrency group
   stops two interleaving - but if two sessions genuinely overlap, an
   older branch pushing last would publish older content. The honest fix
   for that is a real trunk branch to publish from, which is a bigger
   change to how this project works and is deliberately NOT bundled in
   here.

8. **[done, 2026-09-19]** **[Pipeline & publishing]** The Plans tab was
   silently never republishing. `dashboard/embed_dashboard_data.py`
   embeds every `plans/*.md` file's own content into `const PLANS` at
   build time (via `dashboard/plans_md.py`'s `parse_plans()`,
   `PLANS_DIR`), exactly like `CHANGELOG.md` feeds Release Notes and
   `requirements.yaml` feeds the Requirements panel - but **`plans/**`
   was never added to `.github/workflows/deploy-pages.yml`'s own trigger
   `paths`**, so a plans-only commit didn't rebuild the site and the
   live Plans tab quietly drifted behind the repo.

   Missed when that tab was built (2026-09-18, `plans/running-
   thoughts.md` #10). The other two embedded files each carry an inline
   comment in that path list saying why they're there ("embeds this
   file's own content at build time") - `plans/**` just never got added
   alongside them.

   Found 2026-09-19 evening, and only because `keithamoss.github.io`
   had just been allow-listed (`CLAUDE.md`'s own audited domain list):
   fetching the REAL published page and grepping it showed none of that
   day's plans work present, with the live build's own embedded
   `GITHUB_LINKS` commit still reading `24b2560` after five subsequent
   plans-only commits. Not findable any other way from here - the
   workflow wasn't failing, it simply wasn't running, the same
   silent-non-run failure mode as item #7 above and caught by the same
   habit of checking the real artifact rather than the green tick.

   Fixed by adding `plans/**` to that `paths` list, with a comment
   matching the convention the neighbouring two already use. The fix
   verifies itself: the commit carrying it is a `plans/**` change, so
   it triggers the very rebuild it enables.
