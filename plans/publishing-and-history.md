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
- `introduced_date` - when the check was first added.
- `retired_as_of` + `retired_reason` - both optional, both required
  together if the check is retired (history stays fully visible, just
  flagged inactive from this date).
- `changelog` - a list of entries, each with: `date` (automatic, not
  hand-entered), `description` (human-written), `author` (human-entered
  - deliberately not auto-derived from git's own commit author, per
  Keith's own call), `breaking` (human-set boolean).

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
- **Retired checks: drop out of the main current-status view by
  default** (column drawer, overall summary) - a retired check isn't
  part of "what's currently being checked," so the default view stays
  focused on active checks. A toggle brings retired checks back into
  view for history/audit purposes - full history stays intact and
  reachable, just not front-and-centre by default.
- **Changelog metadata surfaces in the existing check-detail panel**
  (item 42's status pill, item 45's comparison UI) rather than a new
  tooltip pattern - a changelog entry becomes another section of the
  panel that already shows a check's status/history/comparison,
  consistent with how everything else about a check is already
  presented there.

**Still not designed:**
- Exact per-tool schema/field names (the concepts above are settled,
  the literal YAML/Python shape isn't).
- Exact visual styling for the breaking-change gap vs. Thread C's
  no-data gap (the constraint that they must differ is settled; the
  actual color/pattern isn't).
- How a non-breaking definition change reads in the UI at all (the
  breaking case now has a real design; the non-breaking case - still
  one continuous line, but a change genuinely happened and has a
  changelog entry - hasn't been designed yet. Presumably some lighter
  marker on the continuous line, not yet confirmed with Keith).

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

1. **Thread B + D together**: committed per-run raw tool-output files,
   with check-lifecycle (retirement/definition-change) metadata designed
   into the format from the start. The dashboard pipeline's "read all
   committed history, merge, reshape" step. Doc updates: CLAUDE.md's
   gitignore convention explicitly updated to reflect that `qa_results/`
   (or whatever this ends up named) is now committed, not ephemeral.
2. **Thread A**: CI-gated publishing (smoke tests + headless-browser
   render check), removing any local-publish path, changelog derived
   from git history.
3. **Thread C**: cadence-aware "as of" viewing, once B/D's real history
   exists to query.

Check-lifecycle UI presentation (retired/definition-changed badges in
the check-history/trend views) can land alongside either 1 or 2,
whichever turns out more natural once the data model is real - not a
hard blocker either way.

## Doc updates needed once this starts landing

- `CLAUDE.md`: the `data/raw/`, `reports/*.json` gitignored-convention
  bullet needs an explicit carve-out once `qa_results/`-style committed
  per-run files exist - don't let the two contradict silently.
- `CLAUDE.md`'s own "read this first" list - add this file alongside
  `plans/wider.md`/`plans/qa-pipeline.md`.
- `plans/wider.md` items 25/26/27 - short pointers added to this file
  rather than duplicating the design there.
