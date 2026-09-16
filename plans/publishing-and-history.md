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
error. Explicit is the only signal that's actually trustworthy. Concrete
mechanism (not yet fully designed, but the shape): each check definition
(Soda YAML / dbt schema.yml / the ODCS contract's quality: blocks) gets
an optional lifecycle marker - something like `retired_as_of: <date>`
for retirement, and a `version`/`changed_as_of: <date>` concept for
definition changes - captured into the committed per-run file's own
metadata (not just the check's live definition, since a run committed
in the past needs to keep recording what was true when IT ran, not get
silently reinterpreted by a later definition change).

**Not yet designed:**
- Exact schema for the lifecycle marker(s) in the check-definition YAML/
  contract files.
- How the dashboard's existing check-history trend/panel (item 45's
  comparison UI, the trend chart) visually distinguishes "retired since
  X" from "definition changed at X, treat before/after as separate
  series" from a normal continuous history. Needs real UI design, not
  just a data-model answer.
- Whether a "breaking" vs "non-breaking" definition change (Keith's
  original item 27 framing) is itself something someone declares
  explicitly per change, or something inferred by comparing the stored
  definitions across versions. Given the retirement decision above
  (explicit, not inferred), the default lean is explicit here too, but
  worth confirming when this gets designed in detail.

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
3. Only publishes (deploys to GitHub Pages) if the gate passes - a
   broken run genuinely can't reach the published site.

**Proposed default, not yet explicitly confirmed with Keith (easy to
revise later - flagging rather than blocking on it):** CI triggers on
push to the committed raw-result paths, not a fixed schedule. Keeps
faith with the "every run should arguably be shared" principle from the
original local-publish brainstorm - the moment someone's results land in
the repo, the team's view updates (once smoke tests pass), no separate
deliberate "now publish" step and no waiting for a scheduled window
either. A schedule can be layered in later (e.g. a periodic rebuild even
absent new commits, to catch drift) if gaps turn out to matter in
practice.

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
