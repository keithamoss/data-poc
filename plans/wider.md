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
| Birth-registrations QA pipeline | this repo, root (`contract/`, `dbt_project/`, `engines/`, `generator/`, `pipeline/`, `real_tools/`) | Real tools wired up and running (`real_tools/*.py`); see `plans/qa-pipeline.md` for open items |
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

10. **[todo, medium]** Repo review and tidy-up before continuing much
    further — Keith flagged this given the pace of recent changes (Phase
    3/4, the QA-check battery, several real bugs found and fixed along the
    way). Not yet scoped: likely candidates are a dead-code/stale-comment
    pass, a consistency check across `real_tools/*.py` and `engines/*.py`
    (naming, structure, how closely each pair actually mirrors the
    other), a README accuracy pass against everything that's shipped
    since it was last substantially updated, confirming `.gitignore`
    coverage is still complete, and revisiting action 6 above (does
    `synthetic-data-generator/` split into its own repo now).

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
