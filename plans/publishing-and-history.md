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

**Decision:** a configurable relative-day offset per data asset that
sets the dashboard's default "as of" date:
- Daily asset (BDM): no filter, always show the absolute latest.
- Quarterly asset (Child Protection, or whichever ends up quarterly):
  offset of N days (e.g. 30-60, exact number not yet decided) - the
  dashboard defaults to showing state as of N days ago, not today.
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

**Not yet designed:**
- Exact default offset values per asset (30 vs 60 days vs something
  else) - Keith was thinking out loud, not deciding, on the specific
  number.
- Whether the offset config lives in the repo (e.g. alongside the ODCS
  contract per dataset) or somewhere else.
- How "as of" interacts with the existing "time travel" snapshot picker
  (item 26) - they're different mechanisms (this queries live history
  for an arbitrary date; snapshots are frozen whole-page archives taken
  at explicit past moments), but a dashboard user might reasonably
  expect some relationship between the two UI entry points. Worth a
  short design pass when this gets built, not resolved here.

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

**Phase 3 (Thread A - CI-gated publishing) - [in progress, 2026-09-16]:**
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

**Not yet built - the remaining piece of Phase 3**: the changelog/
activity-feed DATA logic (reshaping git commit history over the
committed result paths into "who published what, when" feed entries -
the feed's own UI is Phase 5 regardless). The gate-and-publish
mechanism above is real and verified; this is a genuinely separate
piece of work, flagged rather than silently skipped or rushed.

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

## Doc updates needed once this starts landing

- `CLAUDE.md`: the `data/raw/`, `reports/*.json` gitignored-convention
  bullet needs an explicit carve-out once `qa_results/`-style committed
  per-run files exist - don't let the two contradict silently.
- `CLAUDE.md`'s own "read this first" list - add this file alongside
  `plans/wider.md`/`plans/qa-pipeline.md`.
- `plans/wider.md` items 25/26/27 - short pointers added to this file
  rather than duplicating the design there.
