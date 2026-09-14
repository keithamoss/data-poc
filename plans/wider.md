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

## What exists, and where

| Component | Where | Status |
|---|---|---|
| Birth-registrations QA pipeline | this repo, root (`contract/`, `dbt_project/`, `generator/`, `pipeline/`, `real_tools/`) | Real tools wired up and running (`real_tools/*.py`); see `plans/qa-pipeline.md` for open items. `engines/` (the original no-internet-access equivalent engines) removed - see action 18 |
| Synthetic data generator | this repo, `synthetic-data-generator/` | Code present, runs, verified (population-scale, cross-agency identity linkage); **not yet wired into the QA pipeline or dashboard** — see action 2 below |
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

3. **[todo, medium]** No CI. Nothing re-runs `real_tools/orchestrate_real.py`
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

6. **[todo, low]** Decide the long-term home for `synthetic-data-generator/`.
   It's a subdirectory here for now (simplest, since it never had its own
   GitHub repo); worth revisiting once cleanup starts — does it stay
   merged into this repo, or get split out now that we can actually push
   to GitHub?

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
    picking apart which parts to keep. Candidate approach, mirroring the
    `parallel_orchestrate.py` precedent (action item above, `plans/
    performance.md` #4) of extracting a *generic* module that dataset-
    specific files call into rather than a base class datasets subclass:
    a small `_dbt_common.py`/`_soda_common.py`/etc. per tool holding just
    the confirmed-shared ~30-40 lines, imported by both existing files
    and any new dataset's file. Not started - this is a "worth scoping
    before the 3rd dataset lands" flag, not yet built or asked about in
    enough detail to commit to a shape (e.g. whether it's worth doing per-
    tool now vs. waiting to see what a 3rd dataset's files actually need,
    which would be better evidence than extrapolating from 2 data
    points).
