# Wider PoC plan

Tracks the whole multi-agency data pipelines proof-of-concept, not just
the birth-registrations QA pipeline (that has its own plan:
`plans/qa-pipeline.md`) or the real-tool orchestration scripts' runtime
(`plans/performance.md`). This is a working document, not a spec — update
it as things move, don't let it go stale.

**Context:** Keith is Director of Data Technology at a Western Australian
government agency, working this PoC over a period of **weeks**, then
cleaning it up and handing it to the team for their input. Nothing here
should assume a multi-month timeline.

**Purpose, stated explicitly (2026-09-15, correcting a framing slip in
`plans/qa-pipeline.md` #28)**: this repo is a tool evaluation/shootout -
comparing dbt-core, Soda Core, datacontract-cli, and Evidently against
each other on their own individual merits - not a PoC whose job is to
get all of them combined into a working production pipeline. This
matters for how every finding gets read: a gap in one tool that another
tool happens to cover in this project's specific setup (all three run
together, redundantly, on every check) is NOT "harmless" just because
this pipeline still works end to end - it's a real minus against that
tool standalone, since the evaluation's job is to tell the agency what
each tool can and can't do on its own, not to justify keeping all of
them forever. Concrete instance this was caught on: datacontract-cli's
inability to yield PKs/failing values for any `type: sql` rule was
initially logged as "usually harmless" because Soda/dbt cover the same
rules in this fixture - wrong lens; fixed in `plans/qa-pipeline.md`
#20/#28 to read as a standalone capability gap instead. Apply this
lens going forward whenever a tool's shortcoming is tempting to wave
away because something else in this specific pipeline happens to cover
it.

## What exists, and where

| Component | Where | Status |
|---|---|---|
| Birth-registrations QA pipeline | this repo, root (`contract/`, `dbt_project/`, `generator/`, `pipeline/`, `real_tools/`) | Real tools wired up and running (`real_tools/*.py`); see `plans/qa-pipeline.md` for open items. `engines/` (the original no-internet-access equivalent engines) removed - see action 18 |
| Synthetic data generator | this repo, `synthetic_data_generator/` | Code present, runs, verified (population-scale, cross-agency identity linkage); **not yet wired into the QA pipeline or dashboard** — see action 2 below |
| QA reporting dashboard | this repo, `dashboard/qa-reporting-dashboard.html` | Only Birth Registrations wired to real data; ~14 other datasets are still fabricated mock, clearly labeled as such. Also separately published as a claude.ai Artifact ("Data Asset QA Register") that is **not** auto-synced with this file — see action 5 |
| Supporting docs | this repo, `docs/` | `data-contract-engines-landscape.md` (source of the real contract/checks YAML), generator design notes, a standalone quarantine-pattern demo |

## Action items

Status values: `todo` / `in progress` / `done`. Priority is relative,
not a schedule.

1. **[done]** Pull `synthetic-data-generator/` and `docs/` into this repo.
   The sibling repo never existed on GitHub — only inside claude.ai chat
   sessions — so this was a zip merge, not a git remote add. Deliberately
   left out a stale, pre-real-tools snapshot of the pipeline files bundled
   in the same upload. Commit `8a1028f`.

2. **[done]** Wired the Child Protection collection (6 tables, real FKs)
   into the QA dashboard end to end, across 4 phased pushes: (1) periodic
   snapshot generation + per-table ODCS contract, (2) the 7 `relationships`
   checks + 3 cross-table business rules across all three tools, a fix for
   2 business rules that used to always fail (a real generator gap, see
   `plans/qa-pipeline.md` #9), and (3) the dashboard Collection tier itself
   — merged with real-tool wiring (originally its own separate phase)
   since a genuinely real dashboard tile needed it anyway, and
   `engines/*.py`'s equivalents don't support cross-table checks at all.
   **Department for Child Protection and Family Support → Child
   Protection**, 6 datasets, all tagged "Real pipeline data" — see
   README.md's "The Child Protection collection" section for the full
   account, including a real dashboard display bug (a `severity: warning`
   check's missing fail_threshold defaulting to 0) caught only by actually
   rendering it in a browser before calling this done. This proves the
   birth-registrations pipeline's approach generalizes rather than being a
   one-off, and was the highest-value item on this list.

3. **[todo, medium]** No CI. Nothing re-runs `qa_tools/bdm/orchestrate_bdm.py`
   against upstream tool releases, so a `dbt-core`/`soda-core-duckdb`/
   `datacontract-cli`/`evidently` update could silently break this and we
   wouldn't know. A scheduled job (even a simple cron/GitHub Action) that
   runs the real pipeline and diffs against `reports/results_real.json`
   would catch regressions early — including possibly resolving or
   changing the dbt-duckdb bug (`plans/qa-pipeline.md` #1) on its own. If
   this happens, revisit `plans/performance.md` #4/#5 (parallelizing the
   ~2.5min runs) — worth the complexity for something that runs on a
   schedule in a way it isn't for an occasional manual run.

4. **[todo, low]** Try Postgres as the warehouse instead of DuckDB (the
   original HANDOFF suggested it as an alternative). Would tell us
   whether the dbt-duckdb reliability bug is DuckDB-specific or a more
   general dbt-core issue — useful signal for `plans/qa-pipeline.md` #1
   even if Postgres itself isn't adopted.

5. **[done]** The old claude.ai Artifact copy is no longer a concern —
   decided to stop maintaining it; this repo's HTML is the sole source of
   truth going forward. **Public hosting live**: the repo itself is now
   public (Keith's call, given the data involved is synthetic), so GitHub
   Pages works on the free plan with no workaround needed.
   `.github/workflows/deploy-pages.yml` publishes
   `dashboard/qa-reporting-dashboard.html` (as `index.html`) on every push
   that touches `dashboard/` — no separate build step, since the file
   already has its data baked in at commit time. Pages source flipped to
   "GitHub Actions" in Settings, workflow run confirmed successful
   (`conclusion: success`, run `34756094074`) — **live at
   https://keithamoss.github.io/data-poc/**. This also means: as more
   datasets get wired in (action 2) and a scheduled re-run job exists
   (action 3), the public dashboard updates itself automatically on every
   push — no extra work per dataset added.
   **Parked, not actioned**: Keith wants to move this repo back to
   private. That directly breaks free-plan GitHub Pages hosting (only
   works for public repos) — a known, deliberate trade-off to flag now
   rather than rediscover later, not something to pre-solve. Don't reach
   for a different (paid Pages tier, a separate cloud host, etc.) hosting
   solution until the private-repo move actually happens and a public
   dashboard is still wanted at that point — may turn out not to be
   needed at all.

6. **[todo, low]** Decide the long-term home for `synthetic_data_generator/`.
   It's a subdirectory here for now (simplest, since it never had its own
   GitHub repo); worth revisiting once cleanup starts — does it stay
   merged into this repo, or get split out now that we can actually push
   to GitHub? Note this is now a real dependency-in-the-other-direction,
   not just physical proximity: `synthetic_data_generator/` imports
   `generator.dirty`/`generator.names_au`/`generator.presentation`
   directly (see action 21 below) - splitting it into a separate repo
   would need to either vendor those three modules back in or make
   `generator` an actual installable dependency, not just delete the
   sys.path hack that used to paper over this.

7. **[investigate]** Data pipeline observability — flagged as a tangent,
   not yet scoped. Distinct from what's already built: the QA
   dashboard/real-tools pipeline checks *data quality* at a point in time;
   this would be about the health of the *pipeline itself* — did a run
   happen, how long did it take, did it fail silently, is the data stale.
   Also distinct from action 3 above (which is specifically "catch
   upstream tool breakage via a scheduled re-run"). Needs scoping before
   it becomes an actionable item — open questions:
   - Instrumentation (run metrics/tracing — e.g. OpenTelemetry, run
     duration/success history) vs. cataloging (the governance/catalog
     tools surveyed in `docs/data-contract-engines-landscape.md`'s
     Category C — DataHub, OpenMetadata) vs. alerting (notify someone
     when a check fails, rather than only surfacing it on the dashboard
     next time someone looks)? Could be more than one of these.
   - Scoped to this PoC's own pipeline runs, or meant to model what a
     *real* production multi-agency pipeline would need operationally
     (i.e. part of the PoC's demonstration value, not just this repo's
     own housekeeping)?
   - Does it belong as a feature of the existing QA dashboard (a new
     tier/tab), or as a genuinely separate concern?

8. **[todo, low]** Birth Registrations and Child Protection currently come
   from two separate, unlinked synthetic populations — no cross-agency
   identity linkage is actually exercised in this pipeline, despite the
   machinery existing. `synthetic-data-generator/population.py` builds a
   shared master registry (`person_uid`, households) and
   `synthetic-data-generator/generate.py` + `agency_datasets.py` draw
   Birth Registrations, Child Protection, and School Enrollment all from
   that *same* population (each agency gets its own presented name/ID via
   `presentation.py`, linked underneath by `person_uid`, with an
   `internal/` linkage answer-key file) — real and present, just not what
   this pipeline calls. `generator/daily_batch.py` (what
   `generator/generate_runs.py` actually uses for Birth Registrations) is
   a deliberately separate event-flow generator with no population.py
   involvement at all — a fresh cohort of newborns each day, not a
   resample of an existing population, per its own docstring.
   `generator/generate_cp_runs.py` (Phase 1, Child Protection) does call
   `population.py`, but generates its own standalone population instance,
   not shared with Birth Registrations'. **Follow-up:** re-point Birth
   Registrations at the shared population (`agency_datasets.py`'s own
   `generate_birth_registrations()` already does this — a second, genuine
   implementation that exists but isn't wired into the pipeline) so a
   synthetic person can genuinely show up in both datasets under
   different agency IDs — worth doing once there are enough datasets
   wired into the dashboard (action 2) that cross-agency identity
   resolution becomes a meaningful thing to demonstrate, not before.

   **Scoped, not built (2026-09-14)** - Keith asked for this, then
   stopped short of building once the real shape became clear, to keep
   focus on the pipeline's actual core (QA) rather than get pulled into
   generator work. Filed here so the scoping isn't lost if this comes
   back later:
   - `agency_datasets.py`'s `generate_birth_registrations()` is NOT a
     drop-in replacement for `daily_batch.py` - it emits one row per
     person in a whole-population snapshot in a single call, with no
     concept of daily deliveries, dirty-severity injection, or resupply
     chains (the machinery the actual QA pipeline's "multiple runs over
     time" story depends on). Real linkage means threading a shared
     identity source underneath both generators' *existing* mechanics,
     not swapping generators.
   - Asked how much overlap: **"a meaningful minority (most/all CP
     clients also get a BDM record)"**, not just a handful. This rules
     out relying on coincidental overlap between CP's population (ages
     0-17) and BDM's ~10-day rolling newborn window (statistically
     near-zero chance of a birthdate landing inside it) - it requires a
     **historical backfill** dataset (birth registrations for people
     already in the population, via `generate_birth_registrations()`
     largely as-is) as an *additional* piece alongside BDM's existing
     daily event-flow feed, not a replacement for it.
   - Asked whether the backfill goes through the real dbt/Soda/
     datacontract-cli checks like any other run: **yes, in scope** - not
     treated as exempt archival data.
   - Asked whether the dashboard should visibly surface the linkage:
     **no, separate follow-up** - this item is scoped as the data-model
     linkage only (shared population underneath both generators + the
     historical backfill + a linkage answer-key file, mirroring
     `synthetic-data-generator/generate.py`'s existing `internal/`
     convention), not a dashboard feature.
   - Also surfaced, not yet acted on: `population.py`/`child_protection
     .py`/`agency_datasets.py` each hardcode their own `TODAY = pd
     .Timestamp("2026-09-13")` for age/mortality calculation - separate
     from the rolling-window dates fixed in action 20's freshness-filter
     follow-up (`generator/anchor_date.py`), but would need the same
     treatment for population-linked birthdates to land correctly inside
     BDM's actual rolling window if this is picked back up.
   - Not scoped at all yet: how the historical backfill is exposed
     structurally (a new manifest entry type distinct from daily runs?
     how it interacts with row-count-growth/on-time-arrival checks built
     around the daily-delivery shape), and exactly how many/which
     `has_child_protection_history` children get birthdates placed inside
     the rolling window vs. left at their existing 0-17-year spread.

9. **[todo, low]** Explore alternative dashboard output types/tools —
   Streamlit and Power BI named specifically — as alternatives or
   complements to the current hand-rolled static HTML dashboard. Not yet
   scoped: worth comparing what each would actually buy (native
   interactivity and widgets, real data-source connectors instead of a
   baked-in JS const, embedding into BI tooling the agency likely already
   runs) against the cost of a rebuild and what it'd mean for the
   "publish as a static file, zero external dependency" property the
   current dashboard was deliberately built to have (self-hosted fonts,
   no CDN calls — see `plans/qa-pipeline.md`'s dashboard-readability
   entries). Decide replace vs. supplement before committing to either.

10. **[done, medium]** Repo review and tidy-up before continuing much
    further — Keith flagged this given the pace of recent changes (Phase
    3/4, the QA-check battery, several real bugs found and fixed along the
    way). Scoped live by actually investigating each candidate first
    (dead-code pass, `real_tools/*.py`/`engines/*.py` consistency, README
    accuracy, `.gitignore` coverage, action 6's repo-split question),
    then checking findings against Keith before touching anything.

    - **Dead-code/stale-comment pass**: genuinely clean. Grepped for
      TODO/FIXME/deprecated/placeholder markers across all source - every
      hit was a legitimate documentary one (contact-email placeholders
      meant to be filled in later, an external API's own deprecation
      history), nothing stale in this repo's own code. No backup/scratch
      files either. Nothing to fix here.
    - **`engines/*.py` vs `real_tools/*.py` naming**: found one real
      inconsistency - `engines/contract_engine.py`/`soda_engine.py`/
      `dbt_test_engine.py` all follow `<tool>_engine.py`, but
      `drift_engine.py` was named by function (drift) instead of tool
      (Evidently) - the odd one out among its own siblings. **Fixed**:
      renamed to `evidently_engine.py`, and updated every reference,
      including the module's own "engine" self-tag string that's baked
      into `results.json`/the dashboard JSON, not just a docstring
      (`pipeline/orchestrate.py`'s import, `build_dashboard_data.py`'s
      `ENGINE_SHORT` lookup key, comments in `run_evidently_real.py`,
      README/`qa-pipeline.md` mentions). Verified end to end by
      re-running `./run_pipeline.sh`. The rest of `real_tools/*.py`'s own
      naming (`run_<tool>_real.py`/`_cp.py`) was already consistent -
      left alone.
    - **`.gitignore` coverage**: found one real gap.
      `reports/comparison.txt` (output of
      `real_tools/compare_real_vs_equivalent.py`) was the one committed,
      non-regenerating file among otherwise-gitignored reports - checked
      its actual content and found it already stale (only covered the
      original 10 runs, zero resupply-chain entries from the work done
      earlier this session). Exactly the drift risk a committed generated
      file creates that a gitignored one can't. **Fixed**: deleted and
      added to `.gitignore` - regenerate on demand when actually wanted.
    - **README accuracy pass**: found real drift. "The 10 runs" section
      still said "one deliberately red," predating the resupply-chain
      work entirely (now 2 red: run_06, run_09) and never mentioned
      resupply attempts at all. **Fixed**: rewrote with fresh, verified
      per-run numbers for all 4 dirty runs and an explanation of why
      `data/raw/` actually has 15 entries, not 10. Also fixed the
      quick-start blurb and the `generator/` layout listing (which didn't
      mention `resupply.py` at all). Confirmed `generate_cp_runs.py`'s
      "10 weekly snapshots" claim is still accurate - the resupply work
      was Birth-Registrations-only, so CP wasn't affected.
    - **Bigger finding, surfaced as a side effect of verifying the
      rename**: re-embedding the dashboard to confirm `evidently_engine`
      worked revealed the last commit to actually touch the dashboard's
      embedded data predated the resupply-chain feature entirely (recent
      dashboard commits were front-end-only - the tooltip fix, the
      Mothman footer mention). The live published dashboard had been
      silently serving data from before run_06 was ever made red. Fixed
      as a side effect of this pass's regeneration - worth knowing this
      class of staleness can happen silently (nothing errors, the
      dashboard just quietly stops reflecting the generator's actual
      logic) until someone re-runs the pipeline.
    - **Action 6's repo-split question** (does `synthetic-data-generator/`
      become its own repo): revisited given a real finding from this same
      pass - `generator/generate_cp_runs.py` and `generator/daily_batch.py`
      both actually reference `synthetic-data-generator/` now (not fully
      decoupled, contrary to the general "deliberately separate" framing
      elsewhere). Keith's call: leave it merged - the coupling makes a
      clean split more work than it's worth right now, revisit only if it
      becomes a real pain point.

11. **[todo, low]** Document/explain how the synthetic data population is
    generated and how `dirty.py`'s failure injection reflects real
    government data quality issues — Keith wants to understand the
    current approach's realism, not just confirm that it runs. Distinct
    from action 8 above (which is about wiring cross-agency linkage into
    the pipeline) — this is about explaining and reviewing the *model*
    itself: what `population.py`/`presentation.py`/`daily_batch.py`
    actually simulate (household structure vs. this repo's deliberately
    separate event-flow generator, ordinary cross-agency name/ID
    variation, nickname/typo drift) and whether `dirty.py`'s presets
    (null-rate creep, invalid codes, near-duplicates, drift, the newer
    format/cross-record presets) are a fair proxy for the kinds of
    defects real agency data actually has, or read as generic "data
    quality gremlins" a reviewer familiar with real WA government data
    would find unconvincing. Could land as a design-note doc, a README
    section, or a live walkthrough — not yet decided.
    **Progress:** did the live walkthrough for `population.py` (format/
    audience/rigor scoped via questions first) — found real, evidence-
    backed gaps: the hand-authored name pools collide heavily at
    population scale (`Charlotte Smith` × 5,499 at 200k people; ~5,000
    genuine full-name+DOB collisions), couple ages are drawn fully
    independently (32% of couples have a >15-year gap), mortality is
    computed but never enforced anywhere downstream, and
    `has_child_protection_history` can structurally never reach an adult
    despite the code's own comment claiming it's lifelong. Not yet walked
    through `agency_datasets.py`/`presentation.py`/`daily_batch.py`/
    `generate_cp_runs.py`/`dirty.py` - pick back up there.
    Also researched (not yet actioned) whether an existing library would
    do this better than hand-rolling it further - see
    `docs/synthetic-data-generation-tools-research.md`. Bottom line: no
    clean drop-in for "Python, Australian, multi-agency," but a real
    path exists (swap name pools for Faker/Mimesis now that pip access
    isn't the blocker it was when they were hand-authored; recalibrate
    household/age structure against real ABS Census DataPack marginals;
    if the multi-decade dimension is ever actually wanted, adopt a real
    dynamic microsimulation engine like `neworder` or LIAM2 rather than
    faking time-evolution in a point-in-time snapshot generator).
    **Also parked for future synth-data work**: day-of-week seasonality.
    Raised while analysing whether the row-count-growth check
    (`plans/qa-pipeline.md` #12) should compare against a run from N
    calendar days ago rather than the immediately preceding run - the
    real motivation for date-matching over ordinal-matching would be
    filtering out day-of-week effects (e.g. registrations naturally
    dipping on weekends), but `daily_batch.py`/`generate_runs.py` don't
    model any seasonality at all today, so the distinction is currently
    moot. Worth reconsidering if/when the generator models realistic
    weekly (or holiday) patterns - which would also mean revisiting the
    row-count-growth check's own thresholds, since a same-day-of-week
    comparison would then behave differently from a previous-run
    comparison in a way it doesn't yet.

12. **[done, medium - generator layer only]** Resupply-chain simulation
    for Birth Registrations, Keith's own real-world practice: a delivery
    with a RED failing check (never amber) gets a resupply request, and
    the corrected (or still-broken) resupply arrives some working days
    later - "no single fixed resupply rate," deliberately. Scoped up
    front via 2 rounds of questions before building: generator/manifest
    layer only, real rows-largely-the-same-plus-organic-churn on
    resupply (not a fresh random draw), a real per-attempt retry chance
    rather than "one resupply always fixes it," Birth Registrations only
    for now.
    `generator/generate_runs.py` now walks each of its 10 scheduled
    deliveries through a full attempt chain when the first attempt is
    red: a business-day-aware delay (skewed fast - days 1-3 carry ~79%
    of the probability mass, tailing out to day 10), a 60%-per-attempt
    chance the resupply is ALSO red (calibrated so ~13% of red chains
    need 5+ attempts - "sometimes, in a really bad scenario," most
    resolve in 1-2 - matches Keith's own framing), and small-rate organic
    churn between attempts (~2% rows added, ~2% modified, ~1% removed -
    the source system keeps moving between attempts, a resupply isn't a
    time-frozen resend of byte-identical data). Bumped RUN_PLAN from 1
    red delivery to 2 so there'd be two independent chains to compare,
    not one data point.
    `data/raw/manifest.json` gained `delivery_id` (stable across every
    attempt of one logical delivery), `delivery_date` (the originally
    scheduled date), `attempt_number`, `arrived_date` (when this specific
    attempt's file was actually received), `is_resupply`, and
    `supersedes_run_id` - one delivery can now produce several manifest
    entries. Verified end to end: a real 2-attempt chain and a real
    4-attempt chain both generated and resolved correctly, with correct
    business-day arithmetic (every resupply `arrived_date` lands Mon-Fri)
    and correctly-scoped churn (isolated-tested at the designed ~1%/~2%
    rates; the larger add/remove deltas visible between a red delivery's
    own consecutive attempts are the combined effect of churn *and* that
    attempt's own freshly reapplied red-severity defects, not a churn
    bug).
    **Deliberately left untouched**: `real_tools/*.py`, both dashboard
    builders, and the dashboard UI all still assume one manifest entry =
    one calendar day. Checked what that mismatch actually looks like
    rather than guessing: pointed the existing (unmodified) equivalent-
    engine pipeline at the new 15-entry manifest and it does NOT crash -
    it silently treats every attempt as its own independent "day," so
    `run_date`-sorted logic (e.g. `build_dashboard_data.py`'s
    `latest_run`) ends up picking whichever attempt arrived most recently
    *across every delivery's chain*, conflating separate deliveries'
    timelines into one sequence instead of representing "5+ attempts,
    same delivery" as what it is. That's the concrete, real input for
    designing what the reporting UI needs - not yet designed. Keith's own
    framing for that follow-up, already agreed: the dashboard should
    track delivery attempts (each with its own outcome and a
    supersedes-link) and derive "what's current" purely from attempt
    recency within its own data - no need for it to know anything about
    whether a downstream publishing/consumption system has acted on a
    corrected resupply yet.
    **Follow-up finding, verified**: revisited the row-count-growth
    check's own "compare against the immediately preceding run" logic
    (`real_tools/run_evidently_real.py`'s `_previous_run_file`, which
    walks `manifest.json` in list/generation order) in light of this
    item's own resupply chains - it has a real ordering problem now that
    generation order and arrival order can diverge. Confirmed directly
    against the actual `data/raw/manifest.json`: `run_10_2026-09-10`
    (arrived 2026-09-10) sits at manifest position 15, immediately after
    `run_09_2026-09-09_resupply3` (position 14) - but that resupply
    didn't actually arrive until 2026-09-16, six days AFTER run_10.
    `_previous_run_file` would compare run_10's row count against a
    delivery that, chronologically, hadn't arrived yet at the time run_10
    was received. Before this item, generation order and arrival order
    were always identical (one entry per calendar day, in sequence), so
    this was structurally impossible - a genuinely new problem this
    feature introduced, not a pre-existing one just now noticed. Not yet
    fixed - the same class of issue as the "silently conflates attempt
    chains" finding above, and probably wants the same fix (group/sort by
    arrived_date and delivery, not raw manifest order) rather than a
    point patch to just this one check.

13. **[done]** Separate "resupply orchestration" from
    "synthetic data creation per dataset" as a distinct architectural
    concern. Raised by Keith right after action 12 landed, prompted by two
    things landing at once: `generate_runs.py`'s new attempt-chain loop
    (action 12) is currently entangled directly with `daily_batch.py`'s
    specific generation API (`main()` calls `generate_daily_batch()` and
    `apply_birth_registrations_presets()` directly; `_churn_rows()` itself
    calls `generate_daily_batch()` again to manufacture "missing rows that
    should have been in the original file"), and action 11's research doc
    (`docs/synthetic-data-generation-tools-research.md`) makes a real case
    that the underlying generator (`daily_batch.py`, and/or
    `population.py`'s wider household model) may itself get replaced later
    (Faker/Mimesis name pools, ABS-calibrated IPF structure, possibly a
    real dynamic microsimulation engine like `neworder`/LIAM2). If the
    resupply-chain logic (delay distribution, retry/still-red probability,
    MAX_ATTEMPTS, manifest bookkeeping, delivery/attempt ID scheme) stays
    welded to `daily_batch.py`'s specific function signatures, swapping
    the generator later means rewriting the resupply logic too, not just
    the generation calls.

    **Draft architecture sketch** (not agreed, not built — the actual
    design should follow from the questions below): the orchestration loop
    in `generate_runs.py` doesn't actually need to know anything about
    *how* a dataset's rows are made — it only needs three operations to
    exist for whatever dataset it's driving: (1) generate an initial
    attempt's rows for a given date/seed/row-count/id-offset, optionally
    dirtied to a severity; (2) churn an existing attempt's rows forward
    (small add/modify/remove deltas) to produce the next attempt's
    starting point; (3) (re-)apply a dirty preset at a given severity to
    an existing attempt's rows. That's close to a `Protocol`/duck-typed
    "dataset provider" shape — e.g.
    `generate(date, seed, n_rows, id_offset) -> DataFrame`,
    `churn(df, seed, run_date, id_offset) -> DataFrame`,
    `dirty(df, severity, seed, previous_row_count) -> DataFrame` — with
    `daily_batch.py` + `dirty.py`'s existing Birth-Registrations-specific
    functions becoming the first (and for now, only) implementation
    plugged into it. Everything that's genuinely about *resupply
    behaviour* rather than *row content* (the business-day delay curve,
    STILL_RED_PROB, MAX_ATTEMPTS, the delivery_id/attempt_number/
    supersedes_run_id manifest shape) would move to a module that takes a
    provider as a parameter, rather than living inside a
    birth-registrations-specific script. Genuinely open, not yet decided:
    whether "churn" is really a resupply-orchestration-level concept at
    all (same shape for every dataset) or a dataset-specific concern that
    belongs behind the provider interface too — churn was designed once,
    for Birth Registrations' specific columns (`extract_timestamp`
    nudging), and may not generalise as-is.

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
    to support to get resupply simulation "for free."
    `generator/generate_runs.py` is now a thin script: a
    `BirthRegistrationsProvider` class wrapping `daily_batch.py`'s
    `generate_daily_batch()` and `dirty.py`'s
    `apply_birth_registrations_presets()` (churn's implementation moved
    here unchanged, since it's Birth-Registrations-specific -
    `extract_timestamp` nudging, calling `generate_daily_batch()` for
    "missing" rows), plus a `main()` that just writes CSVs/builds
    manifest entries from what `run_delivery_chain()` yields. A future
    replacement generator (per action 11's research doc) only has to
    write a new provider class: `resupply.py` and its chain logic don't
    change.
    **Verified, not assumed**: regenerated the full 10-delivery/
    15-attempt batch after the refactor and diffed `manifest.json`
    against the pre-refactor version byte-for-byte - identical (same
    delivery_06 3-attempt and delivery_09 4-attempt chains, same arrival
    dates, same row counts), confirming the split is behaviour-preserving,
    not just a plausible-looking rewrite.

14. **[investigate]** Great Expectations (GX Core) as a genuine comparison
    tool alongside dbt/Soda/datacontract-cli/Evidently in `real_tools/`.
    `docs/data-contract-engines-landscape.md`'s own worked example noted
    GX "isn't pip-installable in this environment" at the time it was
    written - that's no longer true (confirmed via `pip index versions
    great-expectations`: 1.23.0 available), the same kind of
    stale-constraint discovery as Faker/Mimesis in
    `docs/synthetic-data-generation-tools-research.md`. Worth revisiting
    IF research holds up that it adds something the current four tools
    don't. **Rationale downgraded**: the original candidate reason was
    GX's `unexpected_index_list` as the way to get real per-row
    failing-record samples - but `plans/qa-pipeline.md` #15's follow-up
    research (reading the actual installed source of all four current
    tools, not docs) found THREE of the four already do this natively:
    `datacontract-cli` via `include_failed_samples=True` (a one-line
    change to what `run_datacontract_real.py` already calls), Soda Core
    via SodaCL's `samples limit:` + a custom `Sampler` class, and dbt via
    `store_failures: true` - none currently turned on, but none need a
    new tool either. Evidently genuinely doesn't (confirmed - no such
    concept in its source), consistent with its role here being
    drift/row-growth, not validity. So GX is no longer motivated by that
    specific gap. Not yet scoped whether it's worth evaluating for any
    other reason (pure feature/API comparison, maturity, ecosystem) -
    Compare, don't assume, before wiring anything in.

15. **[investigate]** Data generation currently duplicates the contract's
    column definitions rather than reading from them - a real pain point
    Keith flagged. Confirmed by reading the code, not assumed:
    `contract/bdm-birth-registrations-contract.yaml`'s `schema.properties`
    is the actual source of truth for Birth Registrations' column
    names/types/quality rules, but `generator/daily_batch.py` builds its
    output via a hand-written `pd.DataFrame({"registration_number": ...,
    "child_given_names": ..., ...})` literal with its own independently
    hand-typed column names - nothing connects the two today. Add, rename,
    or remove a column in the contract and the generator silently drifts
    out of sync; nothing would catch it until a QA check started failing
    unexpectedly, or worse, silently stopped covering a real column at
    all. Not yet scoped how to fix: options range from a thin
    generator-side loader that reads column names/types straight out of
    the ODCS YAML's `schema.properties` at generation time (cheap, doesn't
    touch what actually gets simulated per column, just what the frame is
    shaped like) to something deeper tied into the
    `docs/synthetic-data-generation-tools-research.md` replacement work (a
    real generator library could plausibly take the contract's schema as
    its literal column spec, rather than either side hand-authoring
    independently). Worth scoping properly rather than picking blind -
    revisit alongside actions 11/13's generator work, not in isolation.
    See also action 22 - the same "contract should generate its
    downstream files, not just describe them" question, applied to dbt's
    and Soda's own check files instead of the generator.

16. **[parked]** Keith wants to give a dedicated walkthrough of *why* this
    project exists and its actual goals, once the current loop of smaller
    follow-ups winds down - explicitly so future analysis/recommendations
    here are better informed by that context rather than inferred
    piecemeal from individual requests. Nothing to do yet - revisit when
    he raises it.

17. **[decided]** Project codename: **Mothman**. Chosen over "data-poc" -
    scoped via a few rounds: single or two words max, playful/punny or a
    backronym, tied to the wider government-data-asset angle rather than
    narrowly to birth registrations. Landed on Mothman for the strongest
    thematic fit found across the whole exercise (see below) - a legend
    remembered as a warning that came before a disaster, matching what a
    QA/checks system is actually for: catching problems before they
    cause real downstream damage. **Applied**: a subtle mention added to
    both `README.md` (a small subtitle line under the H1) and the
    dashboard footer (`dashboard/qa-reporting-dashboard.html`, a faint
    italic line in the existing small/muted footer) - the dashboard's
    actual product title ("Data Asset QA Register") and main header were
    deliberately left untouched.
    **Parked, Keith's own action item**: renaming the actual GitHub repo
    (`data-poc`) to something Mothman-branded. Not done here - no
    available GitHub tool can rename a repo (nothing in the MCP
    toolset touches repo settings, and there's no `gh` CLI/API access in
    this environment either), and it's also a genuinely consequential
    change worth doing deliberately rather than automatically: it would
    change the live GitHub Pages URL
    (`https://keithamoss.github.io/data-poc/`, already public) and
    require updating any local git remotes. Keith will do this himself
    via GitHub Settings -> General -> Repository name when ready; revisit
    updating internal references (this README, the Pages workflow, any
    hardcoded links in the plan docs) afterward if the rename actually
    breaks anything.
    Full options considered, for context:

    - **Greek philosophy/mythology round**: **Plato**/**The Cave**
      (strongest *conceptual* fit found - the Allegory of the Cave maps
      almost exactly onto this repo's actual two-generation architecture:
      `engines/` the hand-written stand-ins built with no real internet
      access = the shadows on the wall; `real_tools/` the actual
      dbt/Soda/datacontract-cli/Evidently = the real forms outside - this
      is literally README's own "what's real vs equivalent" framing);
      **Diogenes**/**Lantern** (searching for the one honest record among
      the noise); **Themis** (scales of justice/law - the best fit
      *for a government context specifically*, and confirmed via web
      research to have zero presence as a name in the data-quality/
      observability tooling market, unlike the alternatives below);
      **Argus**/**Panoptes** (the all-seeing giant - "always watching");
      **Sisyphus** (half-joke - eternally pushing the boulder back up,
      given resupply chains sometimes take 5+ attempts to resolve).
    - **Researched the real market first** (not just guessed): current
      data-quality/observability tools (Monte Carlo, Bigeye, Metaplane,
      Anomalo, Sifflet, Elementary, Validio, Qualytics, Lightup, Atlan,
      Soda, dbt) lean on vigilance metaphors (Bigeye = literally "big
      eye" watching data; Sifflet = French for "whistle"/alarm),
      deduction (Elementary), or invented quality-word portmanteaus
      (Anomalo, Validio, Qualytics) - mythological names are a genuinely
      open lane in this specific market, not a crowded one. Sources:
      Atlan's 2026 data-observability-tools roundup, daily.dev's 2026
      roundup, Atlan's open-source-data-quality-tools roundup.
    - **Broader myths-and-legends round** (West Virginia AND Western
      Australia both explored, since the request named both and they
      point at genuinely different folklore): **Mothman** (WV, Point
      Pleasant 1966-67 - strongest thematic fit found across the whole
      exercise: sightings stopped exactly when the Silver Bridge
      collapsed, so it's remembered as a warning that came before a
      disaster - an unusually apt metaphor for a QA/checks system whose
      whole point is catching problems before they cause real downstream
      damage); **Flatwoods Monster** (WV - genuinely weaker fit, included
      as "another famous WV cryptid" rather than for a real thematic
      reason, worth dropping); **Drop Bear** (WA/Australian - the
      fictional carnivorous-koala tourist joke, zero cultural baggage,
      purely playful larrikin humour); **Falling Stones of Mayanup**
      (genuinely obscure real WA local legend, quirky hidden-gem
      option). **Wagyl** (the rainbow-serpent figure from Noongar/WA
      Aboriginal mythology) came up as a thematically strong candidate
      (a serpent shaping the land ~ data flowing through the system) but
      was deliberately NOT pitched as a casual codename option - it's a
      significant living sacred figure, not folklore-as-entertainment
      the way Mothman or Drop Bear are, and would need real consultation
      first rather than a naming-brainstorm pick.
    - **Backronym round** (earlier, WA-data-asset-literal): **SWAN**
      (Shared WA Asset Network - WA's own emblem bird, and "asset" is
      the exact word this project's own docs already use for the
      multi-agency data asset concept); also considered and set aside:
      GUARDIAN, TRUST, Black Swan Watch, QuokkaCheck, DataMuster.

    **Decision (2026-09-14): Mothman.**

18. **[done]** Removed `engines/*.py` entirely, superseding action 10's
    earlier "rename for consistency" pass. Follow-up to Keith's own
    question ("do we still need the old equivalent engine code given
    that's legacy from when we couldn't install packages?") - scoped via
    questions first (framework/scope for the smoke-tests work landing
    alongside this, uv adoption), with the engines/ decision itself
    answered directly: remove it, real internet access isn't going away
    and it had already drifted out of sync (Child Protection, the
    row-count-growth/freshness/text-format checks were all built
    real-tools-only, never backfilled).
    Confirmed safe first: `reports/results_real.json` (real_tools/
    orchestrate_real.py's output) is a strict superset of the old
    equivalent path (824 checks vs. 630) - no coverage gap from dropping
    the merge.
    What changed, beyond deleting `engines/*.py` and the now-dead
    `real_tools/compare_real_vs_equivalent.py`:
    - `pipeline/orchestrate.py` trimmed to just its real remaining job -
      generate + load the combined warehouse (`data/warehouse.duckdb`) -
      dropping the "run 4 equivalent engines -> reports/results.json"
      half entirely. The combined warehouse itself is still needed:
      `build_dashboard_data.py`'s own direct DuckDB queries (e.g. the sex
      value-count chart) run against it; `real_tools/orchestrate_real.py`
      builds its own separate per-run warehouses for dbt/Soda.
    - `pipeline/build_dashboard_data.py` rewritten to source solely from
      `results_real.json` - removed the `_REAL_ONLY_CHECK_KEYS` allowlist
      and `_merge_real_only_checks()` merge logic entirely (there's no
      more "base" equivalent result to merge real-only checks into), and
      simplified `ENGINE_SHORT` to the 4 real tags only.
    - `run_pipeline.sh` rewritten to run the actual real-tools pipeline
      end to end (generate+load -> real_tools/orchestrate_real.py ->
      build_dashboard_data.py -> embed) rather than the old
      equivalent-only path - there's only one path now.
    - README.md's whole "two generations" framing rewritten - the intro,
      quick-start, tool table, Layout section, and "The Child Protection
      collection"/"Known simplifications" sections all updated. The
      debugging narrative in "Known simplifications" (the real ODCS
      validation fixes, the dbt-core %-syntax bug, the dbt-duckdb
      reliability bug, the Soda wall-clock finding, the PSI binning
      difference) was kept, not deleted - it's genuine technical history
      - just reframed as "found by comparing against the equivalent that
      existed at the time" (past tense) rather than describing an
      ongoing dual-source dashboard, since there's only one source now.
    - Swept every other file for stray references to the deleted module
      names/paths and fixed them in place rather than leaving dangling
      pointers: `real_tools/*.py` docstrings/comments, `contract/
      bdm-birth-registrations-contract.yaml`, `dbt_project/dbt_project.yml`
      and `schema.yml`, and the dashboard HTML (a visible footer line, a
      JS block comment, and a drawer subtitle template string) - plus one
      unrelated stale `HANDOFF.md` reference found along the way (that
      file was deleted earlier this session; missed at the time).
    **Verified end to end, not assumed**: full `./run_pipeline.sh` run
    after the rewrite succeeded with no `engines/` dependency anywhere;
    confirmed the rebuilt dashboard JSON has zero stale "equiv" wording
    and every check's `engine` field is one of the four real tags.
    `plans/qa-pipeline.md`'s own historical entries (bug-hunt narrative
    naming `contract_engine.py`/`soda_engine.py`/etc.) were deliberately
    left untouched - that file is a development log of what happened and
    when, not a description of current state, so it stays historically
    accurate as originally written.

19. **[done]** Development tooling: `uv`, `ruff`, and `pytest` smoke
    tests - Keith asked "is there anything you want to do now to set us
    up well for [adding more code]," scoped via questions before
    building each piece.
    - **ruff** (chosen over black+flake8): a deliberately lean rule set
      (`F` pyflakes + `E9` syntax errors only - real bugs, not style),
      enforced via a `pre-commit` hook (`.pre-commit-config.yaml`) rather
      than CI-only or on-demand-only. First run found 6 real, safe
      findings across the whole repo, not just recently-touched files -
      5 unused imports, 1 confirmed-dead variable assignment in
      `build_dashboard_data.py` - all fixed.
    - **pytest smoke tests** (`tests/`, 13 tests, ~3s) - scope agreed as
      generator layer + pipeline/dashboard-builder layer, explicitly NOT
      a real (slow) `real_tools/` integration run:
      `test_resupply.py` exercises `generator/resupply.py`'s chain
      orchestration against a trivial stub `DatasetProvider` (business-day
      arithmetic, clean/amber/red outcomes, chain termination,
      strictly-advancing dates) - the exact use case that module's own
      `DatasetProvider` Protocol boundary (action 13) was built to enable;
      `test_generate_runs.py` runs the real seeded generator and checks
      manifest shape/invariants (severity counts against `RUN_PLAN`,
      resupply-only-follows-red, weekday-only arrivals, well-formed
      supersedes chains); `test_build_dashboard_data.py` exercises
      `pipeline/build_dashboard_data.py`'s reshaping logic against small
      fixtures (a tiny `results_real.json` + DuckDB table) via
      `monkeypatch`, deliberately avoiding a real `real_tools/` run to
      stay fast.
    - **uv**, adopted as the full `pyproject.toml` + `uv.lock` setup (not
      just a faster pip drop-in). Genuinely solved a real, previously-
      documented problem: `soda-core-duckdb` declares `duckdb<1.1.0`
      while `datacontract-cli[duckdb]` needs a newer duckdb via
      `ibis-framework` - a hard `pip` `ResolutionImpossible` error that
      used to need a manual two-step `pip install` workaround (see
      `plans/qa-pipeline.md`'s original account). `pyproject.toml`'s
      `[tool.uv] override-dependencies = ["duckdb>=1.5"]` tells uv's
      resolver to trust that the declared ceiling is stale - verified
      repeatedly at runtime, all four tools genuinely work fine together
      on duckdb 1.5.5 - so `uv sync --dev` now resolves everything in one
      step. Verified end to end: full pipeline run under the new
      uv-managed venv produces identical output (same 824 checks, same
      byte counts embedded into the dashboard) to before the migration.
      `requirements-real.txt` removed - `pyproject.toml`/`uv.lock` fully
      supersede it, and keeping both would be the same dual-source-of-
      truth drift risk action 18 just fixed elsewhere. The old two-step
      `pip install` dance is only still needed for plain-pip installs
      (no equivalent override mechanism) - documented as such in README.

20. **[investigate]** Code duplication across `real_tools/*_real.py` (BDM)
    vs `real_tools/*_real_cp.py` (Child Protection) file pairs - asked
    because more datasets are coming. Confirmed: yes, one file pair per
    tool, 8 files / 1392 lines total for 2 datasets (dbt 258+181, Soda
    200+140, datacontract-cli 154+177, Evidently 185+97).

    Diffed the dbt pair (and spot-checked the Soda pair) in full. Same
    split both times:
    - **Genuinely shared/generic** (~30-40 lines/pair): subprocess/API
      invocation boilerplate (`_run_dbt`'s `subprocess.run` call shape,
      `--target-path` handling), `_parse_threshold`/`_NUM_RE`, path
      constants, `ENGINE_TAG` pattern, the per-run-warehouse-file
      convention.
    - **Genuinely dataset-specific** (the rest): test-name -> dimension/
      label mapping dicts (different tests exist per dataset), BDM's
      `_VERIFY_COUNT_SQL` dbt-duckdb reliability workaround (Child
      Protection has never hit that bug), CP's `_table_for_test()`
      multi-table attribution (BDM is single-table, doesn't need it).
      This half isn't boilerplate - it's the actual check-to-dashboard-
      field mapping logic per dataset, and forcing it into one shared
      abstraction would fight the grain of "each dataset's tests are
      genuinely different."

    Not a false-DRY situation, but not nothing either: ~150-260 lines/
    file with a real (if partial) shared layer inside it, and every new
    dataset currently means copy-pasting a whole file and manually
    picking apart which parts to keep.

    **[done]** Built (2026-09-14), scoped via questions first (naming
    suffix, folder structure, import style, and what to do with an
    unrelated stray file the restructure surfaced):
    - **Renamed the BDM/birth-registrations files to match the CP
      convention** - `run_dbt_real.py` -> `run_dbt_real_bdm.py` etc.
      (`_bdm`, not `_births` - matches the existing `contract/
      bdm-birth-registrations-*` naming and "BDM" used as the dataset's
      short name everywhere else in the repo). Previously birth
      registrations had no suffix at all (it was the only dataset when
      these files were written) while CP got `_cp` when it was added
      later - fine with one dataset implied by "no suffix," not fine
      with more coming.
    - **Extracted the confirmed-shared ~30-40 lines/tool-pair** into
      `real_tools/common/{dbt,soda,datacontract,evidently}_common.py` -
      exactly the boilerplate identified above (subprocess/API
      invocation, `--target-path` handling, threshold parsing,
      `ENGINE_TAG`), plus two extra bits datacontract-cli's and
      evidently's pairs turned out to also share byte-for-byte once
      written side by side (the "local_test" server + `DataContract
      .test()` construction; the PSI-via-DataDriftPreset computation) -
      found while doing the extraction, not predicted in advance. Left
      genuinely dataset-specific: test-name/metric mapping dicts, BDM's
      `_VERIFY_COUNT_SQL` workaround, CP's `_table_for_test()`, BDM's
      row-count-growth check (CP has no equivalent).
    - **Split into per-dataset subfolders** - `real_tools/bdm/`,
      `real_tools/cp/`, `real_tools/common/` - rather than a flat
      directory of 16 files that only reads as organized by tool-name
      prefix. `dbt_profiles/` stays directly under `real_tools/` (one
      shared dbt project, can't be split by dataset).
    - **`real_tools` became a proper Python package** (`__init__.py`
      throughout, dotted imports - `from real_tools.common import
      dbt_common`, `from . import cp_common`) rather than extending the
      old per-script `sys.path.insert(0, dirname(__file__))` hack across
      subfolders - Keith's own call between the two options asked about.
      Scripts now run as `python3 -m real_tools.bdm.orchestrate_real_bdm`
      (not a bare file path) - `run_pipeline.sh`, README, and CLAUDE.md
      all updated. `pyproject.toml`'s pytest `pythonpath` swapped
      `"real_tools"` for `"."` accordingly.
    - **Deleted `real_tools/soda_configuration.yml`** (Keith's call, once
      established it wasn't used by any code - a static reference doc
      for running the `soda` CLI directly, hardcoded to one BDM run file,
      superseded by the Python Scan API `run_soda_real_bdm.py` actually
      uses). Git history holds it if ever needed.

    Verified behaviour-preserving, not just refactored: both orchestration
    scripts re-run end to end post-restructure and diffed byte-for-byte
    identical (modulo `run_timestamp`) against pre-restructure
    `results_real.json`/`results_real_cp.json` - 824 and 950 check
    results respectively, zero differences. `uv run pytest` (19 tests,
    `tests/test_parallel_orchestrate.py`'s import updated to the new
    module path) and `uv run ruff check .` both clean.

    **Follow-up, same day: dropped `_real` everywhere.** Keith noticed the
    `_real` qualifier throughout (`real_tools/` itself,
    `run_dbt_real_bdm.py`, `results_real.json`, the `ENGINE_TAG` values'
    `"(real)"` suffix) only ever meant "genuinely ran the tool, not the
    `engines/*.py` hand-written equivalent" - and that distinction has had
    nothing to contrast against since `engines/*.py` was removed (action
    18). Confirmed before touching anything: the dashboard's *separate*
    `REAL_BIRTH_REG_DATA`/`REAL_CP_DATA`/"Real pipeline data" naming is a
    different "real" (genuinely-computed rows vs. the illustrative mock
    data still covering most of the dashboard) and was deliberately left
    alone - not part of this cleanup.

    Scoped via questions (dropping `ENGINE_TAG`'s `"(real)"` is
    dashboard-visible - each check's note text - so worth confirming
    before regenerating reports/re-embedding the dashboard; renaming
    `real_tools/` itself is bigger again, since it touches the import
    paths just built): both yes. Keith left the new package name to be
    picked - went with `qa_tools/` (matches "QA reporting dashboard"/
    "QA pipeline" language used throughout the docs already; avoids
    `checks/`, which would collide in spirit with the existing
    `contract/*-soda-checks.yml` naming).

    What changed: `real_tools/` -> `qa_tools/`; every `_real_bdm.py`/
    `_real_cp.py` file -> `_bdm.py`/`_cp.py` (`run_dbt_bdm.py`,
    `orchestrate_cp.py`, etc.); every `evaluate_*_real_bdm`/
    `run_real_pipeline` function -> `evaluate_*_bdm`/`run_pipeline`
    (same pattern for `_cp`); `reports/results_real.json`/
    `results_real_cp.json` -> `results_bdm.json`/`results_cp.json`; all
    four `ENGINE_TAG` values lost their `"(real)"` suffix (`"dbt-core
    1.12 + dbt-duckdb"` etc.) - which meant updating `ENGINE_SHORT`'s
    dict keys in both `build_dashboard_data.py`/`build_cp_dashboard_data
    .py` to match, and regenerating `reports/*.json` + re-embedding the
    dashboard HTML so the new tag text actually reaches it. Also fixed:
    `build_cp_dashboard_data.py`'s `sys.path.insert(..., "real_tools")`
    + flat `import cp_common` (would have broken outright once
    `real_tools/` stopped existing) now does `from qa_tools.cp import
    cp_common` instead; a couple of stale `real_tools/soda_configuration
    .yml` mentions left behind in `contract/child-protection-soda-checks
    .yml`'s usage comment from that file's earlier deletion (action 20's
    first round) were also caught and fixed here, not before.

    Verified the same way as the first round: both orchestration scripts
    re-run end to end, this time diffed against the pre-rename output
    with an explicit exception for the field that was *supposed* to
    change - every `engine` string (and the `note` text
    `build_dashboard_data.py`/`build_cp_dashboard_data.py` derive from
    it) lost its `"(real)"` suffix, confirmed as the *only* difference;
    every other field, byte-for-byte identical. `uv run pytest`/
    `uv run ruff check .` both clean.

21. **[done]** `generator/`, `pipeline/`, and `synthetic_data_generator/`
    got the same treatment action 20 gave `real_tools/` -> `qa_tools/`:
    real Python packages (an `__init__.py` each, `-m` invocation, real
    absolute imports), not `sys.path.insert()` hacks. Keith asked
    directly why these three still had the hacks qa_tools/ had already
    been cleaned out of, and picked the full fix over a smaller
    "one shared bootstrap helper" alternative he was also offered.

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
      `synthetic_data_generator/__init__.py` added (`reference/__init__.py`
      already existed but the directory it marked is gone now - see
      below); every cross-directory `sys.path.insert()` call site (4
      files) removed, replaced with real absolute imports.
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
      `-m` invocation is what makes the repo root importable at all, which
      absolute imports across packages need and a bare `python3
      generator/foo.py` can't provide (Python only auto-adds the script's
      OWN directory to `sys.path`, not the repo root). `run_pipeline.sh`,
      README, and CLAUDE.md all updated; `run_pipeline.sh` also switched
      every step from a bare `python3` to `uv run python3` while this was
      already being touched (see the `uv`-only item below - the two
      changes landed together since they touched the same lines).
      `dashboard/embed_dashboard_data.py` is the one script left alone -
      it has no cross-package imports at all, so a bare script path still
      works fine and changing it would've been pure churn.
    - `pyproject.toml`'s pytest `pythonpath` swapped
      `["generator", "pipeline", "."]` for just `["."]`; every test file
      that used to `import generate_runs`/`import dirty`/etc. now does
      `from generator import generate_runs` etc.

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
    the same "don't depend on something that merely happens to be present
    outside `.venv`" principle as the package-import fixes above, for the
    same reason: this repo is meant to be checked out and run by other
    people evaluating the PoC, on their own machines, not just the one it
    was built on.

22. **[investigate]** A real, currently-unused way to make the ODCS
    contract the actual single source of truth for dbt's and Soda's own
    check files too - not just something the dashboard/datacontract-cli
    read. Keith asked for this to be flagged as an architectural
    consideration, not built. Same underlying pain as action 15 (the
    generator hand-duplicating the contract's column definitions), just
    hitting `dbt_project/models/staging/schema.yml` and
    `contract/*-soda-checks.yml` instead of `generator/daily_batch.py`:
    all three of these files independently hand-encode the same quality
    rules the ODCS contract already states, with nothing connecting them
    today - add or change a rule in the contract and the dbt/Soda check
    files silently don't follow, the same drift risk action 15 already
    named for the generator.

    Both tools have real bridge tooling for this (verified with actual
    research, not assumed - full detail and sources in
    `plans/qa-pipeline.md` #19): `datacontract-cli`'s own `dbt sync`
    command (already installed in this project) and the third-party
    `dbt-contracts` package both read an ODCS file and **write real
    `schema.yml`/model files to disk** - `dbt sync` specifically tags the
    sections it manages so a re-run won't clobber hand-added tests.
    Soda's `soda ai` (shipped inside `soda-core` itself, no extra
    install) translates an ODCS contract into Soda's own Contract
    Language, with a review-and-approve step before it saves a real file.
    **Neither is a live runtime bridge** - dbt and Soda always execute
    against whatever file is sitting on disk, with zero awareness of
    where it came from or whether it's stale relative to the contract.

    The pipeline shape this would actually enable, if adopted:
    ```
    contract/*.yaml (hand-edited, the only thing a human touches)
            |
            |  CI step, triggered on contract changes (or run manually)
            v
    `datacontract dbt sync ...`  /  `soda ai` (translate, review, approve)
            |
            v
    dbt_project/.../schema.yml (generated + meta-tagged)
    a generated Soda Contract Language file (replaces *-soda-checks.yml)
            |
            v
    `dbt build` / `soda scan` - run completely normally, no ODCS involved
    ```
    Real, currently-unresolved tradeoffs, not yet scoped: `soda ai` is
    explicitly experimental with no published GA date (see #19) - a real
    dependency to take on for a PoC, not a stable foundation yet.
    `dbt-contracts` is an unofficial third-party package, not from dbt
    Labs. And this project's own check design leans on things that might
    not survive a generated round-trip - the dbt-duckdb `fail_calc`
    reliability workaround (`schema.yml`'s own header comment), the
    count-based (not percentage) `warn_if`/`error_if` bands calibrated
    per check, the custom `failed rows`/`fail query:` pattern used where
    Soda's ordinary metric checks don't fit - would need verifying
    whether `dbt sync`/`soda ai`'s generated output can even express
    these, not just whether the happy path works. Not scoped further;
    revisit alongside action 15, not in isolation - same root question
    (should the contract generate its downstream check files, or stay
    read-only reference material) applied to a different pair of files.

23. **[todo]** Secure/authenticated hosting for the dashboard - Cloudflare
    Access or equivalent - near-term work Keith flagged, not scoped yet.
    Directly relevant to action 5 above: the dashboard is currently
    public with zero access control at all (`https://keithamoss.github.io
    /data-poc/`, GitHub Pages free-tier, no login of any kind), because
    the repo itself is public. This is a different, narrower question
    than action 5's "move the repo back to private" - auth-gating the
    *deployed site* is a real option regardless of whether the
    underlying repo is public or private, and action 5's own "don't
    pre-solve this" stance was specifically about not reaching for paid
    Pages tiers/alternate hosts before the repo-privacy question was
    live; this is Keith asking for exactly that now, on its own merits,
    not contingent on the repo going private. Not scoped: which
    mechanism (Cloudflare Access sitting in front of the existing GitHub
    Pages URL vs. moving hosting to Cloudflare Pages directly vs. a
    different provider entirely), who needs access (just Keith, a small
    reviewer group, anyone with a shared password), and whether the
    `.github/workflows/deploy-pages.yml` auto-publish-on-push flow needs
    to change at all or just gets a login wall in front of it.

24. **[parked]** A real CLI for running this PoC, built on Python's
    `click` library - Keith's own framing: "the goal is to give humans a
    user-friendly tool to use to run this PoC on real and fake data."
    Today's actual entry points, confirmed against `README.md`: BDM has
    one (`./run_pipeline.sh`, a plain shell script wrapping 4 `uv run
    python3 -m ...` calls), but Child Protection has no wrapper at all -
    generating + running + building dashboard data for CP is 3 separate,
    manually-typed `uv run python3 -m generator.generate_cp_runs` /
    `qa_tools.cp.orchestrate_cp` / `pipeline.build_cp_dashboard_data`
    commands, each needing the right module path remembered and run in
    the right order. Real friction for anyone other than whoever's been
    living in this repo daily. Not yet scoped: a single `click`-based
    entry point covering both datasets (e.g. `run bdm`, `run cp`, `run
    all`, maybe `generate --dataset cp --severity red` for the dirty-
    data presets already in `generator/dirty.py`) vs. one subcommand
    group per dataset; where it lives (a new top-level script, or
    exposed via `pyproject.toml`'s `[project.scripts]` so `uv run
    mothman ...` works without a path); and whether "real and fake data"
    implies a mode this CLI would need to switch between, or just means
    "the same synthetic-but-realistic data this PoC already only ever
    uses" (no genuinely real BDM/CP data source exists anywhere in this
    project today - see action 25 below for what that would actually
    take).

25. **[parked, medium-term]** What this repo would need to change to run
    against real data in production, not just this PoC's synthetic
    fixtures - Keith's own list of concerns, not yet scoped or
    investigated against the actual codebase the way every `[todo]`/
    `[investigate]` item above has been:
    - **A checks library** - today's checks are hand-authored per column
      across 4 separate places (ODCS contract, Soda YAML, dbt
      `schema.yml`, the handful of contract-level `type: sql` rules) for
      exactly 2 datasets; a real multi-agency deployment would need
      this to scale past hand-authoring each one, per dataset, per
      tool, from scratch.
    - **Developer documentation** - `README.md`/`CLAUDE.md` explain this
      PoC's own layout and conventions today; production would need
      onboarding docs for engineers who didn't build it.
    - **Running on Windows EC2s** - this PoC has only ever been run in
      this project's own Linux sandbox/dev environment; `uv`, the real
      tool packages (dbt-core, Soda Core, datacontract-cli, Evidently),
      and every shell script (`run_pipeline.sh`) would all need a real
      Windows-compatible path checked, not assumed.
    - **How checks output/results get stored in a multi-user
      environment** - today `reports/*.json`/`data/*.duckdb` are
      gitignored, regenerated locally, single-user, no concurrency or
      persistence story at all; a real deployment needs an actual answer
      for where run results live, who can see them, and what happens
      when two people or two scheduled runs overlap.
    - "et cetera" (Keith's own words) - likely an incomplete list, not a
      closed one; revisit and expand before this gets scoped for real.

    Deliberately logged as a single parked item covering all of the
    above rather than split into 4 - Keith raised them together as one
    "what would production need" question, and splitting now would
    guess at boundaries between them that scoping might not agree with.

26. **[done, medium]** "Time travel" - the ability to go back and see the
    entire reporting solution exactly as it was for any previous run,
    not just a single check's own history (which item 45 already covers
    within the live dashboard's own rolling window). Keith's own framing
    up front: "think big, think architecturally, and consider this
    solution will run for years" - built through several explicit rounds
    of AskUserQuestion (intent, then scope, then solution architecture)
    before any code was written, per his own request.

    **Round 1 - intent.** Confirmed against the actual codebase first,
    not assumed: this project has NO persistent, accumulating run
    history today - `data/`, `reports/*.json`, and `dbt_project/target/`
    are all gitignored and fully regenerated, and both generators
    (`generate_runs.py`/`generate_cp_runs.py`) recompute a ROLLING
    window of runs anchored to `date.today()` on every regeneration, not
    an ever-growing log - so "time travel" had no historical spine to
    stand on yet, a genuinely architectural gap, not a UI feature to
    bolt on. Keith's answers: covers data AND the check definitions in
    effect at the time AND the dashboard UI itself, not just today's UI
    rendering old data; driven by audit/compliance and incident-
    debugging (a third option, general trend exploration/convenience,
    was explicitly parked for a later discussion); per-dataset vs.
    whole-system-at-a-point-in-time granularity left open pending scope.

    **Round 2 - scope.** The PoC's own rolling-window architecture was
    deliberately left as-is (not changed to accumulate real infinite
    history) - time travel just needs to work correctly for whatever
    window exists at snapshot time. Snapshot trigger: gated behind a
    manual on/off flag rather than an automatic "is this a real refresh"
    heuristic, since this PoC has no clean signal to distinguish a
    genuine scheduled run from a developer iterating on code (both use
    the same script) - Keith's own call, plus wanting the mechanism
    covered by real tests and a handful of demo snapshots committed to
    the repo so there's something to actually show. Retention: keep
    everything for now, no thinning - explicitly deferred to whichever
    future storage backend (S3/SharePoint/Cloudflare/etc, per action 25
    above) eventually replaces "just commit it to the repo".

    **Round 3 - solution architecture.** Three real approaches were
    compared before picking one, not just the first idea Keith floated:
    - **A - full self-contained snapshot**: archive the exact same fully-
      built static HTML the pipeline already produces (shell + CSS + JS
      + embedded data, zero external dependencies), one complete file
      per snapshot.
    - **B - data-only + shared shell ("hybrid")**: archive just the data
      payload, tagged to a commit SHA pinning which version of the
      rendering code understands that shape; viewing means loading an
      old commit's shell against archived data.
    - **C - archive inputs, rebuild on demand**: archive the raw tool
      outputs (`results_bdm.json`/`results_cp.json`) plus a commit SHA,
      and regenerate the dashboard from them at view time.

    B and C both trade real integrity for storage savings: replaying old
    data through a DIFFERENT commit's rendering code (B) is exactly the
    kind of thing that can silently misrender history if the JS
    interpretation logic ever changes - the opposite of what an audit
    feature needs; C additionally depends on the entire toolchain
    (dbt-core, Soda Core, `uv`, Python itself) still installing and
    behaving identically years from now just to produce a view at all.
    Given the audit/incident-debugging driver from round 1, Keith
    confirmed the hard requirement this settled it: a snapshot must be
    openable with nothing but a browser, forever - which only A
    satisfies. Storage growth (A's real cost) settled as gzip-compression-
    only, no harder cap, matching round 2's "keep everything for now".
    One more scope question resolved here too: whether snapshots need to
    support cross-snapshot querying/comparison ("show me every snapshot
    where this check was red") - Keith's own correction sharpened this:
    that's the LIVE dashboard's trend-chart job (operating on its
    current rolling window), a genuinely different concern from an
    archived, opened-one-at-a-time forensic record - so no separate JSON
    payload alongside each snapshot, just the plain self-contained HTML.
    Build order: the snapshot mechanism + tests + demo snapshots this
    round; a browse/picker UI for opening past snapshots explicitly
    deferred to a later, separate round once snapshots exist to browse.

    **Built**, per the above:
    - `dashboard/snapshot_dashboard.py` - `take_snapshot()` (a pure,
      testable function - injectable `html_path`/`snapshots_dir`/`now`)
      gzips the current fully-embedded `dashboard/qa-reporting-
      dashboard.html` into `dashboard/snapshots/<UTC timestamp>_<git
      short sha>.html.gz` and appends an entry to a plain `manifest.json`
      alongside it (bookkeeping for this script and its own tests - NOT
      the cross-snapshot query feature ruled out above). The timestamp
      format (`%Y%m%dT%H%M%SZ`, no colons) is deliberately Windows-
      filesystem-safe, given action 25 above's own flag that this needs
      to run on Windows EC2s eventually. `main()` is gated on
      `SNAPSHOT_DASHBOARD=1` (unset by default) so a normal `./run_
      pipeline.sh` run stays a no-op for this step unless explicitly
      asked for.
    - The check-defining thresholds that determine each check's pass/
      fail status (`check.warn`/`check.fail`) are already embedded in
      the data payload itself, so a single frozen HTML snapshot
      genuinely captures "data AND the check definitions in effect
      then" for status-determination purposes without needing to
      separately embed raw contract/Soda/dbt YAML - nothing in the
      dashboard renders that content today anyway (see plans/qa-
      pipeline.md #43). The snapshot's git commit SHA is enough
      provenance to look up the exact check-definition files in git
      history if that's ever needed later.
    - `run_pipeline.sh` gained a 5th step calling the snapshot script
      unconditionally (the script itself no-ops without the env flag) -
      `SNAPSHOT_DASHBOARD=1 ./run_pipeline.sh` to actually archive one.
      Documented in `README.md` and `CLAUDE.md` (including flagging that
      `dashboard/snapshots/*.html.gz`, unlike every other generated
      artifact this project produces, is deliberately committed to git,
      not gitignored - the whole point is that it accumulates).
    - `tests/test_snapshot_dashboard.py` (9 tests): gzip round-trip
      byte-for-byte integrity, filename has no Windows-unsafe characters
      (regex-checked), manifest entries are correct and accumulate
      correctly across multiple snapshots, a missing dashboard HTML
      raises rather than silently producing an empty snapshot, and
      `main()` is a genuine no-op without `SNAPSHOT_DASHBOARD=1` set to
      exactly `"1"` (not `"true"`/`"yes"`/empty).
    - 3 real demo snapshots generated and committed (`dashboard/
      snapshots/`), confirmed genuinely distinct (different `md5sum`s
      after gunzip) by regenerating the whole pipeline twice more under
      `GENERATOR_ANCHOR_DATE` overrides a week and three weeks back
      before restoring the live dashboard to today's real, un-overridden
      state as the final step - so the committed `dashboard/qa-
      reporting-dashboard.html` isn't left backdated. One of the three
      verified with Playwright: gunzipped to a plain file, opened cold
      in a real browser (no dev server, no repo context) - renders with
      zero console/page errors, `card count: 6`, confirming genuine
      standalone integrity, not just "the gzip round-trips".

    Known, accepted side effect: `dashboard/snapshots/` sits inside
    `dashboard/`, so a commit adding new snapshots also matches `.github/
    workflows/deploy-pages.yml`'s `dashboard/**` trigger path - a
    harmless, no-op-content GitHub Pages redeploy alongside the real
    publish whenever a snapshot-only commit happens. Not worth narrowing
    the workflow's trigger path for - the redeploy costs nothing and
    always republishes the correct, current dashboard either way.

    `uv run pytest` (80) and `uv run ruff check .` both clean.

    **Originally deferred** (per round 3's build-order answer): any UI
    for browsing/listing/opening past snapshots from the live dashboard.

    **Picker built, same day (2026-09-16), its own short round of
    AskUserQuestion first:** confirmed it needed to work on the live
    public GitHub Pages site now (not just from a local clone), which
    forced a real design question - GitHub Pages can't be told to serve
    a `.html.gz` with `Content-Encoding: gzip`, so a plain link to one
    would just download it, not render it. Keith's own steer settled it:
    keep gzip as the git storage format (already built, tested, no
    reason to undo it for a marginal complexity saving), but decompress
    at DEPLOY time so the published site serves plain `.html` files -
    normal links, no client-side decompression JS needed at all.

    Built: `.github/workflows/deploy-pages.yml`'s "Prepare site" step now
    also gunzips every `dashboard/snapshots/*.html.gz` into `_site/
    snapshots/*.html` (plus publishing `manifest.json` alongside, for
    direct inspection) - nothing decompressed is ever committed to git,
    only produced at deploy time. The picker itself lives INSIDE the
    live dashboard (Keith's call, not a separate page) - a "🕐 Past
    snapshots" button in the header opens a panel listing every
    snapshot (date/time, commit SHA, compressed size), each linking to
    its decompressed page. Deliberately reads an embedded
    `SNAPSHOT_MANIFEST` const (re-embedded by `dashboard/snapshot_
    dashboard.py` every time a snapshot is taken, same mechanism as
    `embed_dashboard_data.py`'s `REAL_BIRTH_REG_DATA`/`REAL_CP_DATA`
    replacement) rather than `fetch()`-ing `manifest.json` at runtime -
    a fetch would silently fail under `file://` (CORS), breaking the
    picker for exactly the offline/local-open workflow this dashboard's
    own dev loop (and every Playwright check this session has run) has
    depended on all along. A snapshot's own archived copy still only
    ever reflects the manifest as it stood before that snapshot was
    taken - it re-embeds AFTER archiving, not before, so a snapshot
    never "knows about" itself or later snapshots.

    Verified end to end with Playwright, not just unit-tested: served a
    real simulation of the Pages deploy output (`gunzip` step run
    locally, exactly as the workflow does it) over a local HTTP server,
    opened the live dashboard, clicked "Past snapshots" (4 rows shown,
    correctly formatted), clicked "Open" on one, and confirmed the
    resulting new tab actually rendered the archived page - real title,
    real card count, zero console errors, correct decompressed URL.
    Checked both color schemes render legibly. 6 new/updated tests in
    `tests/test_snapshot_dashboard.py` (12 total) cover the manifest
    re-embedding: it matches `manifest.json` exactly, a snapshot's own
    archive excludes itself, and a missing `SNAPSHOT_MANIFEST`
    placeholder raises a clear error rather than silently doing nothing.
    83 tests pass repo-wide; `uv run ruff check .` clean.

    **Explicitly checked, Keith's own ask**: the "first time" case - a
    brand new dashboard build with zero snapshots ever taken (`const
    SNAPSHOT_MANIFEST = [];` still its untouched placeholder value) and
    `dashboard/snapshots/` not existing on disk at all. Verified rather
    than just assumed correct: simulated both with Playwright (a real
    dashboard file with its manifest reset to `[]`) and by running the
    deploy workflow's own shell logic against a directory tree with no
    `dashboard/snapshots/` at all. Both already worked without changes -
    the picker shows a clear "No snapshots yet - run SNAPSHOT_DASHBOARD=1
    ./run_pipeline.sh..." message instead of an empty/broken panel, and
    the workflow's `if [ -d dashboard/snapshots ]` guard means a missing
    directory is a clean no-op, not an error.

    **Important clarification, same day (2026-09-16) - Keith's own
    correction, checked and confirmed before writing anything further:**
    the "rolling window" referenced throughout rounds 1-2 above is
    PURELY an artifact of how this PoC fabricates plausible-looking
    recent demo data cheaply (`generate_runs.py`/`generate_cp_runs.py`
    anchoring their date range to `date.today()` and regenerating a
    fresh ~10-15-run window each time) - it is NOT a property of a real
    production BDM/CP feed, and must never be treated as a real
    architectural input to how time travel, or anything else, *should*
    work. A real feed genuinely accumulates forever: a new file arrives,
    joins the record, the record never resets - there is no "window" in
    reality at all, just growing history.

    Checked against what was actually built: `take_snapshot()` doesn't
    know or depend on how the dashboard's underlying data was produced -
    it archives whatever `dashboard/qa-reporting-dashboard.html`
    currently contains, whether that's this PoC's narrow rolling window
    or (in a real deployment) years of genuinely accumulated history. So
    the snapshot MECHANISM needed no changes. What did need tightening
    was this very writeup: "time travel just needs to work correctly for
    whatever window exists at snapshot time" (Round 2 above) is accurate
    but risks being misread later as endorsing the rolling window as a
    legitimate design constraint, rather than naming it as the specific
    reason THIS PoC's OWN demo snapshots only ever show a shallow ~15-run
    slice - a limitation of the fake data generator, not of the feature.
    Read every "rolling window" reference above with that in mind.

    Separately parked, not acted on now (Keith's call): deepening the
    PoC's own fake-data generation to accumulate more simulated history
    over time, so a demo could show genuinely deep time travel rather
    than a handful of nearby points - worth doing eventually, not a
    priority while the feature's job is proving the mechanism works.

    **Added 2026-09-16, same "when we come back to generating more
    history" follow-up:** also tackle a genuinely different resupply
    cadence between the two datasets at that point - one dataset daily,
    the other quarterly. Today's actual cadences, for context:
    `generate_runs.py` (BDM) already generates daily scheduled
    deliveries; `generate_cp_runs.py` (Child Protection) generates
    WEEKLY snapshots, not quarterly (its own docstring: "Child
    Protection isn't a daily event feed, it's a periodic full extract of
    the same underlying casework collection... re-extracted 10 times as
    weekly snapshots"). Read this as widening that existing gap, not
    introducing a third cadence - CP's own framing as "a periodic full
    extract" already fits a quarterly re-extract at least as naturally
    as a weekly one, arguably more so for a real casework/investigation
    collection. A quarterly cadence would also make deepening simulated
    history (the paragraph above) matter more directly: getting even 10
    quarterly runs needs ~2.5 years of simulated calendar time, a much
    more meaningful stress test of "does time travel actually work over
    a long, sparse history" than 10 weekly runs (~10 weeks) does today.
    Not yet scoped - revisit together with the history-depth work above,
    not in isolation.

    **Local/offline viewing gap found and fixed, same day (2026-09-16),
    right after the picker build:** Keith's own catch - "a developer...
    does a QA run... opens the latest file that was generated... they
    can't actually go back and select any of the previous runs, can't
    they? Because they're all just gzipped up in the repository." Correct:
    the picker's links (`snapshots/<name>.html`) only ever resolved on
    the published GitHub Pages site, where `deploy-pages.yml` decompresses
    every `.html.gz` at deploy time - nothing decompressed anything
    locally, so `dashboard/snapshots/` on a real clone only ever held the
    gzipped originals, and opening the dashboard via `file://` would 404
    on every "Open" link. (Briefly thought this was already handled -
    it wasn't; confirmed by reading `take_snapshot()`, which only ever
    called `gzip.open()`, never wrote a plain `.html` copy anywhere.)

    Fixed with `sync_local_snapshots()` in `dashboard/snapshot_
    dashboard.py`: decompresses any `*.html.gz` in `dashboard/snapshots/`
    lacking a local `.html` sibling, writing to the exact same relative
    path the picker's existing links already use - so neither the
    dashboard's JS nor its link markup needed any change, locally or on
    Pages. Called from two places: unconditionally at the top of `main()`
    (so a plain `./run_pipeline.sh`, no `SNAPSHOT_DASHBOARD` flag needed,
    backfills local copies of whatever snapshots already exist - the
    literal fresh-clone scenario Keith described), and again at the end
    of `take_snapshot()` itself (so a snapshot just taken is immediately
    locally openable too). Idempotent - a `.gz` with an existing `.html`
    sibling is left untouched.

    Scoped via two quick questions rather than assumed: whether
    decompression should be automatic vs. a separate explicit step
    (Keith's read - correctly - was that automatic is how it already
    should work, confirming the fix's direction), and whether the local
    `.html` copies should be committed or gitignored-and-regenerated -
    "Gitignored, regenerated from .gz," so `dashboard/snapshots/*.html`
    was added to `.gitignore`; the `.gz` files stay the only thing
    actually committed, same single-source-of-truth pattern as `data/`/
    `reports/` elsewhere in this repo.

    Verified two ways: `uv run python3 -c "from dashboard import
    snapshot_dashboard; snapshot_dashboard.sync_local_snapshots()"`
    against the real repo's 4 existing committed `.gz` snapshots -
    correctly backfilled 4 local `.html` copies, confirmed gitignored
    (`git status` shows nothing new). Then real Playwright against the
    live dashboard opened via `file://`: clicked "🕐 Past snapshots",
    clicked "Open" on a row, confirmed the resulting popup actually
    rendered the archived page from its local `file://.../snapshots/
    <name>.html` path - real title, real content, zero console errors.
    6 new tests in `tests/test_snapshot_dashboard.py` (18 total, up from
    12): `sync_local_snapshots()`'s decompress/skip-existing/missing-dir/
    idempotent behaviour, `take_snapshot()` leaving a local copy behind
    too, and `main()` syncing even with no `SNAPSHOT_DASHBOARD` flag set
    (the existing `main()` tests were also updated to mock out
    `sync_local_snapshots()`, since it otherwise touches the real repo's
    `dashboard/snapshots/` directory as a side effect of running the test
    suite). 89 tests pass repo-wide; `uv run ruff check .` clean.

    **Unified with the deploy pipeline's decompression, same day
    (2026-09-16), right after the fix above:** Keith flagged the local
    sync and the GitHub Pages deploy step (`.github/workflows/deploy-
    pages.yml`'s "Prepare site") were two separate implementations of
    the same "unzip a snapshot" logic - the deploy step was a bash
    `gunzip` loop, `sync_local_snapshots()` was Python's `gzip` module -
    that could quietly drift apart. His ask: make local sync literally
    exercise the same code path deploy uses, so running it locally is a
    real dry run of what CI will do, not just something that resembles
    it. First separately confirmed the local-sync feature itself was
    fine to keep as-is (his worry it might undercut "push to the shared
    site" incentives didn't hold up: `sync_local_snapshots()` only ever
    decompresses `.gz` files already on disk - either pulled from git,
    already shared, or just taken by that same local run - so it can't
    let anyone see history they didn't already have access to).

    Extracted `_decompress_snapshot(gz_path, dest_path)` as the one
    place a `.gz` becomes a plain `.html`, called by both
    `sync_local_snapshots()` (unchanged behaviour) and a new
    `prepare_deploy_site(site_dir, ...)`, which now builds the entire
    `_site/` tree deploy uploads (index.html + decompressed snapshots +
    manifest.json copy) - replacing the old bash loop entirely. Wired up
    via a `--prepare-site <dir>` flag on `snapshot_dashboard.py`'s own
    `main()` rather than a separate script, so there's no risk of the
    workflow importing a stale copy. `deploy-pages.yml`'s "Prepare site"
    step is now: `uv run --no-project python3 -m dashboard.
    snapshot_dashboard --prepare-site _site`.

    Verified for real, not just unit-tested: ran `python3 -m dashboard.
    snapshot_dashboard --prepare-site <dir>` from the repo root -
    correctly produced `index.html` plus all 4 real committed snapshots
    decompressed under `snapshots/`, confirming namespace-package `-m`
    resolution works without `dashboard/` needing an `__init__.py`. 6
    new tests (24 total in `tests/test_snapshot_dashboard.py`, 95
    repo-wide): `prepare_deploy_site()`'s copy/decompress/manifest/no-
    snapshots-dir behaviour, an explicit byte-for-byte-identical check
    between the local and deploy decompression paths, and the
    `--prepare-site` CLI flag itself (including its usage-error case).
    `uv run ruff check .` clean.

    **Correction, same day (2026-09-16) - Keith's own catch:** this
    entry originally said the deploy step should invoke a bare `python3`
    since the script only needs stdlib, "so no uv/dependency install
    needed" - wrong. Keith asked directly: are we sure GitHub Pages
    deployment can't use uv? It can - nothing stops it, and this repo's
    own convention (CLAUDE.md: "Always through `uv run`, not a bare
    `python3`... nothing should depend on... a system Python that
    happens to have the right packages") applies in CI too, not just to
    local dev machines. "Needs no third-party packages" and "so skip uv"
    had been quietly conflated. The actual constraint was narrower: a
    plain `uv run` in this repo's directory would sync the FULL project
    dependency set from `pyproject.toml` (dbt-core, Soda Core,
    datacontract-cli, Evidently, pandas...) before running anything -
    genuinely unwanted for a step that only needs stdlib and would slow
    every deploy. `uv run --no-project` resolves that: it skips the
    project-context dependency sync entirely while still running through
    uv's own pinned Python rather than trusting whatever `python3`
    happens to be preinstalled on the runner. Verified locally
    (`uv run --no-project python3 -m dashboard.snapshot_dashboard
    --prepare-site <dir>`, ~0.15s, no dependency sync triggered) before
    changing the workflow. `.github/workflows/deploy-pages.yml` now adds
    an `astral-sh/setup-uv` step before "Prepare site" and runs the
    script through `uv run --no-project`.

    **That deploy actually failed in CI, same day - real bug, caught
    because Keith checked the run rather than assuming green:**
    `astral-sh/setup-uv@v10` errored with "Unable to resolve action...
    unable to find version `v10`" - a second wrong guess about that
    action, not just the first one. Confirmed via its actual tags list
    (`astral-sh/setup-uv` doesn't publish floating major-version tags at
    all - only exact ones like `v10.1.0` - unlike `actions/checkout`/
    `actions/deploy-pages` etc., which do) and its own README, which
    recommends pinning to the full commit SHA rather than any tag, a
    real supply-chain-security convention for third-party actions.
    Re-pinned to `astral-sh/setup-uv@bec219d24cd3e171d82865faccec3312
    0bb574f4 # v10.1.0`. Lesson worth naming plainly: the earlier "v10"
    guess was asserted without checking the actual tags list first time
    round either - looked up a release page, not the specific ref format
    this workflow needed. Verified this time by listing the repo's real
    tags before writing the pin, not by re-guessing a plausible-looking
    one.

27. **[parked]** Versioning the checks themselves, with that version
    flowing through to the results/data each check run captures - Keith's
    own framing, raised right after item 26's time-travel build: "a
    useful thing to have as a baseline concept we could hook into
    later," because checks will inevitably change ("there will be
    breaks in checks and changes to checks"), and not every change means
    the same thing for someone reading the history.

    The core idea, as he framed it: some check changes are a genuine
    **break in the series** (a threshold moved, the underlying logic
    changed what's actually being measured - the run before and the run
    after aren't really comparable anymore) and some aren't (a label
    reworded, a cosmetic tweak, a bug fix that doesn't change what
    passes/fails). Today, nothing in this project distinguishes the two
    - a check is identified purely by its name/column, with no version
    number or change history of its own, and every real check result
    this project produces is tagged with which RUN it came from but
    never with which VERSION of the check produced it. The trend chart
    (`trendChart()`, `dashboard/qa-reporting-dashboard.html`) draws one
    continuous line across a check's whole `history` regardless - a
    silent threshold change today would show up as an unexplained kink
    in the line, not a flagged discontinuity a reader would understand
    as "the check itself changed here, don't read this as organic
    drift."

    Real connections to what already exists, worth keeping in view once
    this gets scoped: item 26's time-travel snapshots already capture a
    check's `warn`/`fail` thresholds as they stood at that moment (each
    snapshot is self-consistent), so versioning would mostly be about
    making that fact EXPLICIT and queryable rather than an accidental
    side effect of how snapshots happen to work; `plans/qa-pipeline.md`
    #43 (surfacing a check's real SQL/YAML definition in the dashboard,
    not yet built) is the natural place a version identifier would also
    want to show up. Not yet scoped: what actually constitutes a
    "version" (a hash of the check's YAML config, a hand-maintained
    semver-style number, a git commit reference), who/what decides
    breaking vs. non-breaking (an author-asserted flag when the check
    changes, vs. some automated diff heuristic), how a check result
    would carry its version forward (a new field alongside `run_id` in
    `reports/results_*.json`), and exactly how a "break in the series"
    should read in the UI (a visual gap in the trend line, an
    annotation/marker at the break point, splitting the line into two
    separately-labeled segments, something else). Parked for a dedicated
    scoping discussion, not this session.

28. **[parked, big think-piece]** Generalizing this whole architecture
    (ODCS contract schema, Soda checks, dbt generic tests, and the
    dashboard's own rendering model) to work on different SHAPES of data
    asset, not just the one it's built around today. Keith's own
    framing, raised right after the snapshot-picker build: "derived
    products from data matching processes or data extractions" - his
    explicit examples of shapes this project doesn't handle at all yet.
    Near-to-medium term, not now - "a bigger think piece."

    Everything this project has built so far - the ODCS contract's
    `schema:`/`quality:` blocks, every Soda/dbt check, the dashboard's
    entire Agency → Collection → Dataset → **Column** drill-down model -
    assumes one specific shape: a table of typed columns, checked for
    completeness/validity/uniqueness/freshness/relationships. That's a
    real, deliberate scope (see this file's own framing throughout), but
    it's not the only shape a real multi-agency data asset register
    would need to cover. Keith's two named examples are both already
    hinted at elsewhere in this project without being built:
    - **Data-matching/record-linkage outputs** - `synthetic_data_
      generator/population.py`'s cross-agency `person_uid` identity-
      linkage machinery already exists (action 8 above: built, real,
      but not wired into the QA pipeline at all). A real linkage
      process's own natural QA concerns are a different SHAPE of
      question entirely - match rate, false-positive/false-negative
      link rate, cluster purity, confidence-score distribution - not
      "is this column null", and don't obviously fit a column-drill-down
      dashboard view at all.
    - **Data extractions** - a derived/aggregated/transformed output (a
      report, a summary table, a published extract drawn FROM other
      data rather than captured directly) has yet another different QA
      shape: reconciliation against source totals, extraction
      completeness (did the job actually capture everything it should
      have), aggregation correctness, lineage consistency back to the
      source asset(s) it was derived from.

    Not yet scoped, not even a first-pass design: whether the contract/
    dashboard model needs a genuine "asset type" concept above "table"
    (with each type bringing its own check vocabulary), whether dbt-
    core/Soda Core/datacontract-cli have any native support for non-
    tabular assets worth researching before assuming a from-scratch
    build, and whether the dashboard's column-drilldown visual model can
    stretch to cover a match-quality or reconciliation report or
    genuinely needs a separate view type per asset shape. Connects to
    action 25 above's "a checks library" concern (a real checks library
    for a multi-agency register would need to cover more than one
    asset shape from the start) - worth revisiting together once either
    gets scoped for real.
