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
- Action 25's "how checks output/results get stored in a multi-user
  environment" parked bullet - this file is the real answer.
- Item 26's "time travel" snapshot mechanism stays as built (freezing
  the whole rendered dashboard page) - genuinely different from this
  file's "as of" viewing (Thread C below), which queries real
  accumulated history rather than replaying a frozen page. Both are
  staying in the design; see Thread C for how they relate.
- Item 27 (check versioning, parked) - folded into this file's Thread D,
  built together with Thread B rather than as a separate later round,
  per Keith's own call once the storage format was in scope anyway.

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
  plans/wider.md's history-depth entry), not picked to paper over the
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

**Not yet built**: the offset value is now configured (correctly
scoped) and verified parseable, but nothing reads it into the
dashboard build yet, and none of Thread C's actual UI (as-of date
picker, URL param persistence, "no data available" below-threshold
state) or querying logic (how the dashboard computes/displays state
"as of" an arbitrary past date against committed history) exists yet -
a genuinely separate, larger piece of work from configuring the one
number.

## Build order

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
  facts (see the `astral-sh/setup-uv@v10` pin incident, `plans/wider.md`
  #29). Researched for real (WebSearch + WebFetch on
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

**Phase 4 (Thread C - cadence-aware "as of" viewing):**
- Depends on Phase 1 and Phase 2 (real committed history, merged/
  reshaped) - NOT on Phase 3. Worth being explicit about this: the
  numbering reads sequential, but Phase 4 isn't actually blocked by
  Phase 3 - kept in sequence anyway per Keith's own call, for
  simplicity, not because of a real dependency.
- Includes Thread C's own UI (the as-of date picker/calendar widget,
  URL param persistence) - that's part of this phase, not Phase 5 below.

**Phase 5 (UI presentation - spans Thread D's check-lifecycle UI and
Thread A's changelog/activity-feed UI) - its own standalone phase,
pinned per Keith's own call:**
- Thread D: the breaking-change trend-line gap, the non-breaking marker
  (same color, no gap), **retired-checks dropping from the default
  current-status view with a toggle to show them**, and the changelog +
  description sections in the existing check-detail panel.
- Thread A: the "📋 Recent activity" header button + panel for the
  publish changelog (same interaction pattern as "🕐 Past snapshots").
- Depends on Phase 1 (check-lifecycle data to render) and Phase 3
  (publish-activity data to render) - not on Phase 2 directly (though
  Phase 2 is what makes the check-lifecycle data actually renderable)
  or Phase 4.

**Phase 6 (test coverage) - added 2026-09-16, Keith's own call, once
Phases 1-5 are otherwise done:** not scoped yet beyond the name - a
deliberate placeholder so the ask isn't lost, not scoped in depth here
since Keith hasn't asked for that yet. Depends on everything above
existing to have something real to cover. Scope for real (what's
covered vs. gap, unit vs. integration, real-tool-run coverage vs.
fixture-only) when this phase is actually reached.

## Doc updates needed once this starts landing

- `CLAUDE.md`: the `data/raw/`, `reports/*.json` gitignored-convention
  bullet needs an explicit carve-out once `qa_results/`-style committed
  per-run files exist - don't let the two contradict silently.
- `CLAUDE.md`'s own "read this first" list - add this file alongside
  `plans/wider.md`/`plans/qa-pipeline.md`.
- `plans/wider.md` items 25/26/27 - short pointers added to this file
  rather than duplicating the design there.
