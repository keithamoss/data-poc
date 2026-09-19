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

**This file's own scope, narrowed 2026-09-18.** Originally an
undifferentiated catch-all for every "wider than the QA pipeline"
thought - grew to 32 items spanning data generation, dashboard features,
codebase architecture, dev tooling, and outright miscellany (a project
codename decision) with zero internal grouping. Split that day into
topic-specific files that already existed or made sense as new ones -
see the table below. What's LEFT here has a real, narrower identity:
genuinely cross-component strategic questions (ones that don't belong to
any single part of the system - Postgres vs. DuckDB, pipeline
observability, production-readiness, generalizing the whole
architecture) plus small process/housekeeping notes that don't warrant
their own file. If a new item shows up that's clearly about ONE
component, it belongs in that component's own file below, not here.

| File | Covers |
|---|---|
| `plans/qa-pipeline.md` | The check battery itself - real bugs found running the real tools, check design, dashboard follow-ups from that work |
| `plans/publishing-and-history.md` | How QA results become durable, published history - committed per-run files, CI-gated publishing, check-lifecycle versioning, "as of" viewing |
| `plans/conceptual-design.md` | Real conceptual/design tensions in how this PoC models real-world concepts |
| `plans/performance.md` | The real-tool orchestration scripts' runtime |
| `plans/dashboard.md` | The QA reporting dashboard itself - features, UI, hosting/deployment |
| `plans/data-generation.md` | Synthetic data generation - `generator/` and `synthetic_data_generator/` |
| `plans/tooling.md` | Real developer/testing tooling that doesn't belong to one dataset or pipeline stage - the unified `mothman` CLI/TUI design and its supporting dev scripts. Split out of this file 2026-09-19 once that one item outgrew everything else here |
| `plans/running-thoughts.md` | Keith's own raw, not-yet-scoped capture buffer |

Status values: `todo` / `investigate` / `in-progress` / `parked` /
`done` / `superseded`. Every item also carries a Component tag - see
`plans/running-thoughts.md` item #10 for the shared taxonomy this and
`CHANGELOG.md` both use. IDs (`wider-N`, referenced elsewhere as
`plans/wider.md #N`) are permanent once assigned - never renumbered or
reused, even if an item is later retired, matching `qa_tools/common/
check_lifecycle.py`'s own `check_id` convention.

## What exists, and where

| Component | Where | Status |
|---|---|---|
| Birth Registrations QA pipeline | `contract/`, `dbt_project/`, `generator/`, `pipeline/`, `qa_tools/bdm/` | Real dbt-core/Soda Core/datacontract-cli/Evidently checks running end to end, published to a live GitHub Pages dashboard, real ticketing/gamification layer on top - see `plans/qa-pipeline.md` for the check battery, `plans/dashboard.md` for the UI |
| Child Protection QA pipeline | `contract/`, `dbt_project/`, `generator/`, `pipeline/`, `qa_tools/cp/` | A second real dataset collection (6 tables, real FKs), fully wired end to end, not a mock - proves the Birth Registrations approach generalizes |
| Synthetic data generator | `synthetic_data_generator/` | Code present, runs, verified (population-scale, cross-agency identity linkage); still **not wired into the QA pipeline or dashboard** - see `plans/data-generation.md` #3 |
| QA reporting dashboard | `dashboard/qa-reporting-dashboard.template.html` | Both real datasets wired to real data; a real ticketing/people/leaderboard layer, published live at https://keithamoss.github.io/data-poc/ - see `plans/dashboard.md` |
| Supporting docs | `docs/` | `data-contract-engines-landscape.md` (source of the real contract/checks YAML), generator design notes, a standalone quarantine-pattern demo |

## Action items

1. **[todo, 2026-09-18]** **[Pipeline & publishing]** Try Postgres as the
   warehouse instead of DuckDB (the original HANDOFF suggested it as an
   alternative). Would tell us whether the dbt-duckdb reliability bug is
   DuckDB-specific or a more general dbt-core issue — useful signal for
   `plans/qa-pipeline.md` #1 even if Postgres itself isn't adopted.

2. **[investigate, 2026-09-18]** **[Pipeline & publishing]** Data pipeline
   observability — flagged as a tangent, not yet scoped. Distinct from
   what's already built: the QA dashboard/real-tools pipeline checks
   *data quality* at a point in time; this would be about the health of
   the *pipeline itself* — did a run happen, how long did it take, did
   it fail silently, is the data stale. Also distinct from `plans/
   publishing-and-history.md` #1 (which is specifically "catch upstream
   tool breakage via a scheduled re-run"). Needs scoping before it
   becomes an actionable item — open questions:
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

3. **[done, 2026-09-15]** **[Docs & process]** Repo review and tidy-up
   before continuing much further — Keith flagged this given the pace of
   recent changes (Phase 3/4, the QA-check battery, several real bugs
   found and fixed along the way). Scoped live by actually investigating
   each candidate first (dead-code pass, `real_tools/*.py`/`engines/
   *.py` consistency, README accuracy, `.gitignore` coverage, `plans/
   data-generation.md` #2's repo-split question), then checking findings
   against Keith before touching anything.

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
   - **`plans/data-generation.md` #2's repo-split question** (does
     `synthetic-data-generator/` become its own repo): revisited given a
     real finding from this same pass - `generator/generate_cp_runs.py`
     and `generator/daily_batch.py` both actually reference
     `synthetic-data-generator/` now (not fully decoupled, contrary to
     the general "deliberately separate" framing elsewhere). Keith's
     call: leave it merged - the coupling makes a clean split more work
     than it's worth right now, revisit only if it becomes a real pain
     point.

4. **[parked, 2026-09-18]** **[Docs & process]** Keith wants to give a dedicated
   walkthrough of *why* this project exists and its actual goals, once
   the current loop of smaller follow-ups winds down - explicitly so
   future analysis/recommendations here are better informed by that
   context rather than inferred piecemeal from individual requests.
   Nothing to do yet - revisit when he raises it.

5. **[done, 2026-09-14]** **[Docs & process]** Project codename:
   **Mothman**. Chosen over "data-poc" - scoped via a few rounds: single
   or two words max, playful/punny or a backronym, tied to the wider
   government-data-asset angle rather than narrowly to birth
   registrations. Landed on Mothman for the strongest thematic fit found
   across the whole exercise (see below) - a legend remembered as a
   warning that came before a disaster, matching what a QA/checks system
   is actually for: catching problems before they cause real downstream
   damage. **Applied**: a subtle mention added to both `README.md` (a
   small subtitle line under the H1) and the dashboard footer
   (`dashboard/qa-reporting-dashboard.html`, a faint italic line in the
   existing small/muted footer) - the dashboard's actual product title
   ("Data Asset QA Register") and main header were deliberately left
   untouched.

   **Parked, Keith's own action item**: renaming the actual GitHub repo
   (`data-poc`) to something Mothman-branded. Not done here - no
   available GitHub tool can rename a repo (nothing in the MCP toolset
   touches repo settings, and there's no `gh` CLI/API access in this
   environment either), and it's also a genuinely consequential change
   worth doing deliberately rather than automatically: it would change
   the live GitHub Pages URL (`https://keithamoss.github.io/data-poc/`,
   already public) and require updating any local git remotes. Keith
   will do this himself via GitHub Settings -> General -> Repository
   name when ready; revisit updating internal references (this README,
   the Pages workflow, any hardcoded links in the plan docs) afterward
   if the rename actually breaks anything.

   Full options considered, for context:
   - **Greek philosophy/mythology round**: **Plato**/**The Cave**
     (strongest *conceptual* fit found - the Allegory of the Cave maps
     almost exactly onto this repo's actual two-generation architecture:
     `engines/` the hand-written stand-ins built with no real internet
     access = the shadows on the wall; `real_tools/` the actual
     dbt/Soda/datacontract-cli/Evidently = the real forms outside - this
     is literally README's own "what's real vs equivalent" framing);
     **Diogenes**/**Lantern** (searching for the one honest record among
     the noise); **Themis** (scales of justice/law - the best fit *for a
     government context specifically*, and confirmed via web research to
     have zero presence as a name in the data-quality/observability
     tooling market, unlike the alternatives below); **Argus**/
     **Panoptes** (the all-seeing giant - "always watching"); **Sisyphus**
     (half-joke - eternally pushing the boulder back up, given resupply
     chains sometimes take 5+ attempts to resolve).
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
     (genuinely obscure real WA local legend, quirky hidden-gem option).
     **Wagyl** (the rainbow-serpent figure from Noongar/WA Aboriginal
     mythology) came up as a thematically strong candidate (a serpent
     shaping the land ~ data flowing through the system) but was
     deliberately NOT pitched as a casual codename option - it's a
     significant living sacred figure, not folklore-as-entertainment the
     way Mothman or Drop Bear are, and would need real consultation
     first rather than a naming-brainstorm pick.
   - **Backronym round** (earlier, WA-data-asset-literal): **SWAN**
     (Shared WA Asset Network - WA's own emblem bird, and "asset" is the
     exact word this project's own docs already use for the multi-agency
     data asset concept); also considered and set aside: GUARDIAN,
     TRUST, Black Swan Watch, QuokkaCheck, DataMuster.

   **Decision (2026-09-14): Mothman.**

6. **[done, 2026-09-18]** **[Testing & dev tooling]** Development tooling: `uv`,
   `ruff`, and `pytest` smoke tests - Keith asked "is there anything you
   want to do now to set us up well for [adding more code]," scoped via
   questions before building each piece.
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
     `DatasetProvider` Protocol boundary (`plans/publishing-and-
     history.md` #2) was built to enable; `test_generate_runs.py` runs
     the real seeded generator and checks manifest shape/invariants
     (severity counts against `RUN_PLAN`, resupply-only-follows-red,
     weekday-only arrivals, well-formed supersedes chains);
     `test_build_dashboard_data.py` exercises `pipeline/
     build_dashboard_data.py`'s reshaping logic against small fixtures (a
     tiny `results_real.json` + DuckDB table) via `monkeypatch`,
     deliberately avoiding a real `real_tools/` run to stay fast.
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
     truth drift risk `plans/qa-pipeline.md` #83 just fixed elsewhere.
     The old two-step `pip install` dance is only still needed for plain-
     pip installs (no equivalent override mechanism) - documented as
     such in README.

7. **[superseded, 2026-09-19]** **[Testing & dev tooling]** A real,
   unified CLI for running this whole PoC (`mothman`) - the full design
   (core shape, the Quality Assurance wizard, single-table CP QA,
   Generate/Regenerate synthetic data, Tier 4 Population Data, the debug
   group, TUI design research, and the build order) moved to its own
   file once it had grown far larger than anything else here: see
   **`plans/tooling.md` #1**. This entry's own number stays reserved,
   never reused, per this file's own "IDs are permanent" rule above -
   it's a pointer, not a retirement of the work itself (still
   `in-progress` there, same as it was here).

8. **[parked, 2026-09-16]** **[Pipeline & publishing]** What this repo
   would need to change to run against real data in production, not
   just this PoC's synthetic fixtures - Keith's own list of concerns,
   not yet scoped or investigated against the actual codebase the way
   every `[todo]`/`[investigate]` item above has been:
   - **A checks library** - today's checks are hand-authored per column
     across 4 separate places (ODCS contract, Soda YAML, dbt
     `schema.yml`, the handful of contract-level `type: sql` rules) for
     exactly 2 datasets; a real multi-agency deployment would need this
     to scale past hand-authoring each one, per dataset, per tool, from
     scratch.
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
     for where run results live, who can see them, and what happens when
     two people or two scheduled runs overlap.
   - "et cetera" (Keith's own words) - likely an incomplete list, not a
     closed one; revisit and expand before this gets scoped for real.

   Deliberately logged as a single parked item covering all of the above
   rather than split into 4 - Keith raised them together as one "what
   would production need" question, and splitting now would guess at
   boundaries between them that scoping might not agree with.

   **The "how checks output/results get stored" bullet is now properly
   scoped, same day (2026-09-16)** - see `plans/publishing-and-
   history.md` in full. Not built yet, but no longer an open question:
   committed per-run tool-output files as the real source of truth,
   CI-gated publishing with no manual local-publish path, and a build
   order.

9. **[parked, 2026-09-18]** **[QA checks & contract]** Generalizing
   this whole architecture (ODCS contract schema, Soda checks, dbt
   generic tests, and the dashboard's own rendering model) to work on
   different SHAPES of data asset, not just the one it's built around
   today. Keith's own framing, raised right after the snapshot-picker
   build: "derived products from data matching processes or data
   extractions" - his explicit examples of shapes this project doesn't
   handle at all yet. Near-to-medium term, not now - "a bigger think
   piece."

   Everything this project has built so far - the ODCS contract's
   `schema:`/`quality:` blocks, every Soda/dbt check, the dashboard's
   entire Agency → Collection → Dataset → **Column** drill-down model -
   assumes one specific shape: a table of typed columns, checked for
   completeness/validity/uniqueness/freshness/relationships. That's a
   real, deliberate scope (see this file's own framing throughout), but
   it's not the only shape a real multi-agency data asset register would
   need to cover. Keith's two named examples are both already hinted at
   elsewhere in this project without being built:
   - **Data-matching/record-linkage outputs** - `synthetic_data_
     generator/population.py`'s cross-agency `person_uid`
     identity-linkage machinery already exists (`plans/data-
     generation.md` #3: built, real, but not wired into the QA pipeline
     at all). A real linkage process's own natural QA concerns are a
     different SHAPE of question entirely - match rate, false-positive/
     false-negative link rate, cluster purity, confidence-score
     distribution - not "is this column null", and don't obviously fit a
     column-drill-down dashboard view at all.
   - **Data extractions** - a derived/aggregated/transformed output (a
     report, a summary table, a published extract drawn FROM other data
     rather than captured directly) has yet another different QA shape:
     reconciliation against source totals, extraction completeness (did
     the job actually capture everything it should have), aggregation
     correctness, lineage consistency back to the source asset(s) it was
     derived from.

   Not yet scoped, not even a first-pass design: whether the contract/
   dashboard model needs a genuine "asset type" concept above "table"
   (with each type bringing its own check vocabulary), whether dbt-core/
   Soda Core/datacontract-cli have any native support for non-tabular
   assets worth researching before assuming a from-scratch build, and
   whether the dashboard's column-drilldown visual model can stretch to
   cover a match-quality or reconciliation report or genuinely needs a
   separate view type per asset shape. Connects to item #8 above's "a
   checks library" concern (a real checks library for a multi-agency
   register would need to cover more than one asset shape from the
   start) - worth revisiting together once either gets scoped for real.

10. **[done, 2026-09-19]** **[Docs & process]** A dedicated requirements-
    analysis subagent system - Keith's own idea (voice-dictated batch):
    "I think I'd like to work on creating an agent with you to do
    requirements analysis, and then we can have them go off and do some
    work while we continue." Genuinely cross-cutting (not tied to one
    component) - a process/tooling idea about HOW work on this project
    gets scoped, not a feature of any one part of the system.

    **Scoped and built the same day, across many real rounds of
    back-and-forth (not speced unilaterally, per Keith's own explicit
    ask above)** - real research into Claude Code's own published
    sub-agent guidance, Anthropic's broader multi-agent architecture
    patterns, and real-world "BA agent"/spec-driven-development examples
    in the wild, each round folded into the design before the next:

    - **Real published guidance found first** (`code.claude.com/docs/en/
      sub-agents.md`, Anthropic's "Building Effective Agents" and
      multi-agent research system posts): subagent tool access is a real,
      harness-enforced boundary, not a polite prompt instruction; start
      with single-purpose agents; 5 real orchestration patterns exist
      beyond the evaluator-optimizer reviewer loop Keith already had in
      mind (prompt chaining, parallelization, routing, orchestrator-
      worker) - of those, prompt chaining and parallelization are real,
      useful extensions for later (a scoped-then-built-then-reviewed
      lifecycle chain; batch-reviewing many already-built features at
      once), not needed for this initial build.
    - **Real-world precedent researched** (deliberately checked before
      finalizing the design, not just Anthropic's own docs):
      `zhsama/claude-sub-agent`'s real 5-stage spec pipeline
      (spec-analyst/architect/planner/reviewer/validator) validated the
      overall shape and, independently, that EARS-format acceptance
      criteria is a real convention others use; `www.codecentric.de`'s
      "Don't Let Your AI Cheat: Isolated Specification Testing" post (by
      Thomas Jaspers) supplied the real, concrete isolation mechanism
      (`.claudeignore` + `settings.json` permission restrictions +
      separate `CLAUDE.md` files per agent) and three specific prompt
      instructions now built directly into `delivery-critic.md`
      ("report exactly what you observe," "never mark a criterion met
      unless explicitly verified," "don't let one finding bias the
      next"). A UX-focused agent has almost no real precedent in the
      wild (confirmed via real research, not assumed) - that part of the
      design is closer to novel than to following an established
      pattern, flagged as such rather than presented as proven.
    - **Where this project's own design deliberately diverges from that
      precedent**, each a real Keith decision, not a default: `zhsama`'s
      pipeline has no forced human approval step (agent-scored gates
      only); this one does (per this project's own "ask, don't guess"
      convention, `delivery-scoper` explicitly asks multiple rounds
      of clarifying questions and escalates genuine forks rather than
      resolving them itself). `zhsama`'s reviewer stage directly edits
      code; this one's `delivery-critic` is strictly read-only,
      reporting findings back to the main session (and Keith) to act on.
      Task granularity is deliberately small (Keith: "none of our tasks
      really should be like four to eight hours long... one or two at a
      time"), so no separate task-planner stage was built at all.

    **Final shape, 4 real subagents** (`.claude/agents/*.md`), plus a new
    `docs/project-context-for-agents.md` (drafted from what was already
    in `CLAUDE.md`/`README.md`, per Keith's own explicit call - not
    dictated from scratch) and 5 new optional `requirements.yaml` fields
    (`source`/`non_functional_requirements`/`dependencies`/
    `open_questions`/`evidence` - see that file's own header comment for
    the full schema, and `qa_tools/common/validate_requirements.py` for
    the real enforcement, including a genuine dangling-reference check on
    `dependencies`):

    1. `delivery-scoper` - turns a raw idea into EARS-format
       requirements, splitting a big idea into several small
       self-contained ones (Keith's own explicit call: "I'm keen for
       requirements to remain pretty small and self-contained") rather
       than one sprawling entry, plus a draft `plans/*.md` entry. Asks as
       many rounds of clarifying questions as it takes - never settles
       for an assumption.
    2. `delivery-architect` - a genuinely "simple" architect (Keith's
       own framing), NOT full software design: duplication/overlap
       detection against the real codebase (the exact class of problem
       the `generator/`/`synthetic_data_generator/` drift bug already
       demonstrated for real), fit within `mothman`'s existing command
       structure, cross-component blast radius, security, and code-
       quality/clean-code expectations for the builder - plus an
       optional lightweight architecture/data-model sketch, only when it
       would genuinely help.
    3. `delivery-dashboard-ux` - dashboard-only (not the CLI/TUI, not
       accessibility - Keith's own explicit scope choices), checking
       consistency with the dashboard's real existing UI patterns and
       workflow/information-architecture fit, advisory only, alongside
       the architect, before anything is built.
    4. `delivery-critic` - merged reviewer + fresh-context QA-
       checker into one role (Keith's own explicit simplification,
       accepting the real tradeoff of losing genuine fresh-context
       independence, partly offset by an explicit self-check step built
       into its own prompt). Checks finished work against the
       requirement's acceptance criteria AND the architect's quality/
       security/code-quality expectations, reads real code, drives a
       real headless Playwright browser via `Bash` (this environment has
       no dedicated Playwright tool - the same ad hoc
       `playwright.async_api` script pattern this project's own sessions
       already use), and checks real test coverage - line coverage for
       real today, branch coverage flagged as not-yet-measured rather
       than fabricated (`pyproject.toml`'s `[tool.coverage.run]` doesn't
       set `branch = true` yet, `plans/running-thoughts.md` #11,
       deliberately parked). Deliberately isolated from the scoper's/
       builder's own implementation reasoning - only ever given the
       requirement, the architect's quality bar, and the finished result
       - the real "don't teach to the test" principle the codecentric.de
       research surfaced, agreed explicitly by Keith before building.
       Strictly read-only; reports back to the main session, never edits
       anything itself.

    Not yet exercised end-to-end on a real feature - built and reviewed
    in design, not yet run for real. First real use will be the natural
    test of whether the design holds up in practice.

    **Refined further, same day, before that first real run** - Keith
    held off running the loop to give more real input first, three real
    additions:
    - **A real, named polish standard.** Keith's own words: he wants
      dashboard UX polished "to the level that Apple goes for their
      products... a UX where you don't even realize it's polished
      because of everything else." Now a real, explicit bar in both
      `delivery-dashboard-ux.md` and `delivery-critic.md`'s own
      instructions, not just implied.
    - **Real role depth in `docs/project-context-for-agents.md`.**
      Keith's own observation: the agents (UX especially) need more than
      role labels - real motivations and perspectives per role. Added:
      what Keith himself is actually doing when he looks at this (judging
      the approach generally, and using it as something to show other
      people); the data steward's real frustration point (noise, too many
      clicks before reaching what matters, checking this quickly
      alongside other work); the accountable data owner's real concern
      (trend over time, defensibility); the pipeline maintainer's
      opposite need (wants the raw tool-level detail the steward
      doesn't) - a real, concrete tension the same dashboard has to serve
      both sides of.
    - **The "banked for later" post-build UX pass pulled forward into
      `delivery-critic` now**, not deferred - Keith explicitly liked
      the idea flagged during the UX-agent scoping research (a real-
      world precedent, VoltAgent's `ui-ux-tester`: a "frustrated
      end-user" persona doing actual Playwright-driven visual QA) and
      asked for it built into the current reviewer rather than parked.
      `delivery-critic` now does a real, separate visual-QA pass
      for dashboard-facing requirements only, adopting a busy/moderately-
      attentive data-steward persona, taking real screenshots as
      evidence (spacing, interaction states, dark mode, whether a
      confused click-path is possible), checked against the same
      Apple-level bar - and, since `delivery-dashboard-ux`'s own pre-build note
      is a real standard to check against (same "not implementation
      reasoning" treatment `delivery-architect`'s note already gets),
      the reviewer is explicitly told it may be given that note too.

    **Deliberately not yet done, Keith's own explicit call**: deeper
    grounding of `delivery-dashboard-ux`'s own intent in real human-psychology/
    HCI research (not just "consistency + workflow fit"). Revisit once
    this refinement round is in hand, not before.

    **Correction, same day**: Keith's earlier "let me do some research
    online" on whether real precedent exists for a UX-reviewer-agent
    role was reversed - he wants this session to do that research, not
    him.

    **UX-reviewer-agent precedent research, done same day.** Real
    precedent exists, and this project's own design (a genuinely
    separate `delivery-dashboard-ux` pre-build agent, plus a post-build
    visual-QA pass folded into `delivery-critic` rather than kept
    as its own third agent) lines up with how others have actually built
    this:
    - `cfisch3r/estimate` PR #91 - a real repo running two SEPARATE
      Claude Code subagents, `design-critic-ux` (UX heuristics) and
      `design-critic-visual` (visual design), both wired to a Playwright
      MCP server for "live screenshot-based UX and visual design review"
      against a running dev server - the same "drive a real browser,
      don't just read code" mechanism `delivery-critic`'s own
      post-build pass uses (via ad hoc `Bash`+Playwright here instead of
      an MCP server, since that's what this environment actually has).
      Real precedent for keeping UX review genuinely separate from code
      review, not folded into one generic reviewer.
    - `xenstalker02/punchlist` - a structured, evidence-based design-
      audit methodology: every review declares a concrete user scenario
      up front ("a `[user]`, in `[state]` on `[device]`, starts at
      `[entry point]` and tries to `[complete task]`"), findings must
      cite what was actually inspected (a real screenshot, a real
      element), and anything not actually checked goes in a "Not
      assessed" section rather than inflating the finding count -
      directly validates `delivery-critic`'s own "never mark a
      criterion as met unless you've explicitly verified it" rule and
      its explicit busy/moderately-attentive-steward persona (though
      punchlist itself deliberately avoids a "frustrated user" archetype
      in favour of a neutral state+device description - a real
      alternative framing worth knowing about, not adopted here).
    - `agapi-koutsi/UX-Design-Critique` - a different real pattern: MULTIPLE
      named personas (Product Manager, Engineer, Skeptical User) critique
      independently, then a Moderator agent summarizes the debate -
      genuinely different from this project's single-UX-reviewer
      design, not adopted, but confirms multi-persona critique is a real,
      explored pattern elsewhere if ever revisited.
    - General search confirms the wider "split review into independent
      specialist lenses, fresh context per lens" pattern extends past
      code review into UX/visual/accessibility-specific reviewer roles
      in real, existing Claude Code subagent setups - not just a code-
      review-only convention.
    (`skills.lc` was blocked mid-research trying to read one further
    design-review skill's primary source - flagged in `CLAUDE.md`,
    only reachable via a search-engine snippet.)

    Still not done, still Keith's to revisit when ready: deeper grounding
    of `delivery-dashboard-ux`'s own intent in real human-psychology/HCI
    research - this precedent research answered "does a UX-reviewer role
    exist elsewhere," not "what does the psychology literature say about
    good UX," which is a separate, deliberately deferred question.

    **Follow-up, same day: does `agapi-koutsi/UX-Design-Critique`
    actually show why its multi-persona approach works well?** Keith
    asked directly, genuinely curious given how "pretty complex" it
    sounded. Dug further (a direct fetch of its raw `README.md`, plus a
    web search for any write-up, example output, or case study) and
    found nothing beyond the one-line pitch already quoted above - no
    screenshots of a real critique session, no sample agent dialogue,
    no before/after example, no stated rationale for why 3 personas +
    a moderator beats one reviewer. Honest finding: this looks like a
    small, undocumented personal project (its author, Agapi Koutsi, is
    a real UI/UX designer - Lead Product Designer, Questrade Financial
    Group, per her own public profile - so the concept itself has real
    design-practitioner authorship behind it), not a validated case
    study. Keith's own reaction: interested in the UX-critic/visual-
    critic split specifically (real precedent for that comes from
    `cfisch3r/estimate` PR #91 above, which DOES show concrete
    implementation, unlike this one) but wants it parked for now - "put
    that to the side for now and come back to me on this."

    **Follow-up, Keith asked the same "is there a real basis to it"
    question of `cfisch3r/estimate` too.** Dug further - the PR itself
    (#91) and its follow-up issue (#88, "Design critique: remaining
    screens") are both task descriptions only, no raw critique output
    published either. But PR #87 ("Mode Select"), which #88 says already
    used this critique process, DOES show something real: a concrete
    list of fixes the author applied as a result of it - a heading using
    a bespoke inline `font-size` instead of the real `h2` scale, a
    component using the wrong text style (`CardMeta` instead of
    `CardBody`), vertical centering fixed via a real design token instead
    of a magic number, an icon colour brought into line with its sibling
    icon, a footer layout change, and real accessibility additions (a
    skip link, a `<main>` landmark) - exactly the kind of "you don't
    notice it's polished" detail-level issue this project's own Apple-
    polish bar cares about, not vague generic feedback. The author also
    noted "two investigated-but-not-fixed findings turned out to be
    false positives" - an honest, real signal this isn't a magic bullet,
    just a real process with a real (imperfect) hit rate, not unlike
    what `delivery-critic`'s own post-build UX pass should expect
    to produce. Still no raw agent transcript/output published anywhere
    public for either repo, so "why it works" is inferred from real
    fix-list evidence, not directly observed.

    **Keith's own follow-up: keeping `docs/components.md` in sync with
    the UI, and the first real standalone test of the reviewer's
    post-build UX pass.** Two real asks, same day:
    - **Sync question**: how do we stop `docs/components.md`, the
      dashboard template's own `COMPONENT_ICON`/`PLANS_ALL_COMPONENTS`
      consts, and `_COMPONENT_CODES` drifting apart, now that the same
      taxonomy shows up in 3 real places (the Plans tab, the Release
      Notes panel, and now every requirement's own id)? Answer: a real
      CI test, not a rule to remember -
      `tests/test_component_taxonomy_consistency.py`, which fails if
      any of the 3 disagree (verified with a real, deliberately-
      introduced typo in `docs/components.md` first, confirmed failing,
      then reverted). Note: the Requirements panel itself doesn't
      currently DECODE a requirement's id into a component name/icon -
      it only shows the raw id string (the code is visible but not
      translated) - whether to add a decoded badge there too is a
      separate, not-yet-asked follow-up.
    - **First standalone capability test of `delivery-critic`'s
      post-build UX pass**: Keith wants the mobile overflow bug
      (`plans/dashboard.md` #12) used as the real first test case -
      point the agent at the real built
      dashboard's Requirements panel, on a mobile viewport, with
      genuinely zero hints about what's wrong, and see if it finds the
      bug on its own. Run via the main session (not `delivery-dashboard-ux`,
      which never drives a live browser - this is explicitly
      `delivery-critic`'s own post-build visual-QA pass,
      exercised standalone rather than as part of a full requirement
      review). **Result: it worked, and found real, substantial
      evidence** - see the full new section below, "The standalone test
      ran, found the bug and much more, and led to a real architecture
      change."
    - **Component-coded ids.** Every `requirements.yaml` id is now
      `REQ-<CODE>-NNN` (`GEN`/`QAC`/`PIPE`/`DASH`/`GHUB`/`TEST`/`DOCS` -
      `qa_tools/common/validate_requirements.py`'s own
      `_COMPONENT_CODES` is the single source of truth), the same
      7-part taxonomy this file's items and `CHANGELOG.md` entries
      already tag with. Keith's own explicit follow-up: drop the old
      bare `REQ-NNN` shape entirely rather than grandfather it - so all
      22 real, pre-existing entries were migrated the same day (each
      kept its own original number, picked up whichever real component
      best fits, checked against how the equivalent feature is actually
      tagged elsewhere in this repo) rather than left as a legacy
      exception. `_ID_RE` now rejects the bare shape outright.
    - **A real `date_written` field** (optional `YYYY-MM-DD`) - Keith's
      own ask for a real chronological trail on the register, not just a
      sequential id. Rendered next to each requirement's title in the
      dashboard's own Requirements panel.
    - **`delivery-scoper` now genuinely asks Keith about non-
      functional requirements**, not just derives them from the
      codebase itself - a real `AskUserQuestion` step added alongside
      the existing "check against this project's own standing rules"
      one, Keith's own explicit call that relying on self-derived NFRs
      alone wasn't enough.

    **Follow-up, same day: `delivery-scoper` now actively coaches
    Keith through NFRs, not just asks once.** Keith's own words: "I feel
    like I'm not good at doing non-functional requirements... I'd like
    it to prompt me from different angles." The single generic
    `AskUserQuestion` step above was replaced with a real, named set of
    10 angles (performance, scalability, reliability, security, privacy/
    data sensitivity, compatibility/portability, maintainability,
    observability/auditability, compliance/retention, cost) - adapted
    from the real ISO/IEC 25010 software-quality-characteristics
    taxonomy, each one translated into a concrete question grounded in
    this project's own real domain (e.g. "would this requirement's own
    assumptions still hold if this were ever pointed at real production
    Birth Registrations/Child Protection data" for privacy, "will this
    still hold up once `qa_results/` has years of real history" for
    scalability) rather than left as abstract textbook categories. The
    agent works through the list itself, judges which angles are
    plausibly relevant to the specific requirement at hand, and asks
    Keith about those via batched `AskUserQuestion` calls (up to 4
    questions per call) - genuine active coaching, not a mechanical
    10-question interrogation on every requirement.

    **The standalone test ran, found the bug and much more, and led to
    a real architecture change.** A general-purpose agent, adopting
    `delivery-critic`'s own real instructions (its actual "Post-
    build UX / visual QA pass" section, at the time still folded into
    that agent), was pointed at the real built dashboard's Requirements
    panel at a real 390x844 mobile viewport with genuinely zero hints -
    no mention of the mobile overflow bug, no mention of what to look
    for. It built the real dashboard itself (`mothman dashboard rebuild-
    results`/`build-data`/`embed`), drove a real headless Chromium via
    throwaway Playwright scripts (same mechanism the agent's own
    instructions described), and came back with 9 real, evidenced
    findings (F1-F9), not a vague pass/fail. Full detail is in
    `plans/dashboard.md` #12 (the bug it confirmed and substantially
    deepened) - the short version: it found the overflow bug unprompted,
    discovered it's actually a real horizontal-PAN bug (confirmed via
    real CDP touch-event dispatch, not just a script), traced the real
    root cause to two specific real lines (`renderRequirementsPanel()`
    at template line 3225, `.drawer-body`'s `overflow-y`-only rule at
    line 285), found the same bug on the Changelog panel too, and
    surfaced several more real findings in the same pass (stale
    `not_started` rows for features that are actually built, a MoSCoW
    "Must" pill reusing the page's own red-means-failing colour
    language, no search/filter unlike the structurally similar Plans
    tab, sub-platform tap targets) - while also honestly reporting what
    worked well (zero console errors, clean dark-mode parity, Escape-to-
    close). This is real, working evidence the isolated "read your own
    instructions, go in cold" design actually produces genuine,
    specific findings, not generic feedback - the single most direct
    validation this agent system has had since being built.

    Keith's own reaction: adopt the `cfisch3r/estimate`-style UX/visual
    split for real, and two real technical decisions came with it
    (scoped via `AskUserQuestion` before building, per this project's
    own standing convention):
    - **A real Playwright MCP server**, not the ad hoc Bash+throwaway-
      script mechanism `delivery-critic` used for the test above.
      Explained to Keith in plain terms first (Playwright = real browser
      automation; MCP = a fixed, named "menu" of tools an agent calls
      directly instead of writing its own script each time; "Playwright
      MCP" = Microsoft's own real MCP server wrapping Playwright that
      exact way - what `cfisch3r/estimate`'s own `.mcp.json` wires up).
      Set up for real: `.mcp.json` at the repo root, running
      `@playwright/mcp@0.0.82` (pinned, matching this project's own
      version-pinning convention - `.python-version`, `dbt_utils`) via
      `npx`, configured with `--executable-path /opt/pw-browsers/
      chromium` (this sandbox's own real, pre-installed Chromium -
      confirmed via a real smoke test: launched the server in HTTP mode
      on a local port, got a real listening banner and a real HTTP
      response back, proving the browser launches correctly against
      this environment's own Chromium rather than trying to download a
      mismatched revision, the same class of problem this project has
      hit before on the Python/pytest side), `--headless`, `--no-
      sandbox` (needed in this kind of sandboxed environment),
      `--isolated` (in-memory profile, no leftover state between runs).
    - **The post-build UX pass pulled OUT of `delivery-critic`
      entirely**, into 2 new, dedicated, Playwright-MCP-driven agents:
      `delivery-dashboard-ux-critic` (workflow/navigation/discoverability -
      does the flow make sense) and `delivery-dashboard-visual-critic`
      (spacing/alignment/overflow/dark-mode/interaction-states - does it
      LOOK deliberate), a real domain split mirroring `cfisch3r/
      estimate`'s own `design-critic-ux`/`design-critic-visual` pair.
      `delivery-critic` itself goes back to purely functional/
      code-quality/security/test-coverage checks - its own "Post-build
      UX / visual QA pass" section is gone, its description/`tools:`
      frontmatter updated to match. `delivery-dashboard-ux` (the PRE-build
      agent) had its own "out of scope" pointer updated to name the 2
      new post-build agents instead of `delivery-critic`. Each new
      agent's own real tool list is a genuine, considered subset of
      `@playwright/mcp`'s real ~60-tool surface (verified against the
      real npm package's own README, not guessed) - `browser_navigate`/
      `browser_click`/`browser_resize`/`browser_take_screenshot`/
      `browser_console_messages`/etc. for `delivery-dashboard-ux-critic`;
      those plus `browser_evaluate` (real measured CSS/DOM values, not
      guesswork) and `browser_emulate_media` (real forced dark-mode
      testing) for `delivery-dashboard-visual-critic` - deliberately excluding
      the advanced surface neither needs (tracing, video, storage-state,
      cookies).

    Also, same follow-up: Keith asked whether `cfisch3r/estimate` itself
    has a real basis for the split (not just concrete implementation,
    which was already confirmed) - see PR #87's real fix list (a
    heading-scale bug, a design-token misuse, an icon-colour mismatch,
    real accessibility additions, and an honest "two findings were false
    positives" note) two entries up in this same file's history for the
    full account; not repeated here.

    Not yet done: neither new agent has been run for real yet (the
    standalone test above ran under `delivery-critic`'s OLD,
    not-yet-split instructions) - their own first real run is still
    ahead, and the Playwright MCP server, while smoke-tested at the CLI
    level, hasn't yet been exercised through an actual Claude Code
    subagent session pulling tools from it.

    **Keith asked directly whether the 2 new agents were actually
    copies of `cfisch3r/estimate`'s own real prompts - they weren't
    (never had access to them until he asked to go and look), and once
    real access was found, real, worthwhile differences turned up.**
    First attempt (fetching the PR's rendered page) gave an internally
    CONTRADICTORY "verbatim" excerpt for `design-critic-ux.md` on 2
    separate tries - a real, concrete demonstration that `WebFetch`'s
    own HTML-rendered-page summarization is not reliable for "what does
    this file actually say," flagged here so a future session doesn't
    trust it either. Found the real file paths
    (`.claude/agents/design-critic-ux.md`/`design-critic-visual.md`,
    plus a third, not-yet-looked-at `doc-quality.md`) via a real
    directory listing, then fetched the real raw source directly from
    `raw.githubusercontent.com` (not the rendered PR page) - internally
    consistent across 2 separate fetches (each file correctly
    cross-references the other by name), structured exactly like this
    project's own real Claude Code agent files (YAML frontmatter +
    prose), genuinely more trustworthy than the first attempt.

    Real content, real differences from what was already built here:
    - `model: sonnet` for both of theirs, vs `opus` for both of ours -
      ours followed this project's own existing convention (every other
      `requirements-*` agent is `opus`), not copied from them.
    - `tools: Read, Grep, Glob, mcp__playwright` - a single namespace-
      level grant for the WHOLE Playwright MCP toolset, not individual
      tool names. Real, useful discovery: Claude Code does support
      granting an entire MCP server this way. Our own 2 agents instead
      list each real `mcp__playwright__browser_*` tool individually (15
      for UX-critic, 12 for visual-critic) - a deliberate, narrower
      grant matching this project's own existing minimal-tool-per-agent
      convention (every other agent here gets only what it needs, not a
      whole category), not an oversight - but worth Keith knowing the
      simpler, broader syntax exists as a real alternative.
    - Their visual critic reads the app's own real, NAMED design-token
      CSS files (`src/design/nocturne.css`) before critiquing, and
      judges "against Nocturne's own tokens... not generic best
      practice." Real, concrete idea neither of our 2 new agents
      currently has explicitly - our dashboard does have its own real
      CSS custom properties (`var(--ink-muted)`, `var(--surface-alt)`,
      etc. throughout the template) that `delivery-dashboard-visual-critic`
      could be told to read first the same way, not yet added.
    - Their UX critic's own contract explicitly expects to be handed
      "User goal on this screen" / "Target audience" as real structured
      inputs per review, not just general project context. Ours relies
      on `docs/project-context-for-agents.md`'s general personas
      instead - a real, different choice (more general-purpose per
      review, less tailored per screen), not yet reconsidered.
    - Their visual critic's own "squint test" (mentally blur the
      screenshot, can you still tell what's most important) is a
      concrete, real visual-hierarchy technique ours doesn't currently
      name.
    - A third real agent, `doc-quality.md`, exists in that repo -
      unrelated to UX/visual, not yet looked at, but a real, adjacent
      data point for Keith's own separately-parked interest in a
      code-quality tool/reviewer agent (`plans/tooling.md` #2/#3) -
      "documentation quality" specifically, a slightly different angle
      neither of those 2 parked items named yet.

    **Keith's own real decision on each of the 5, same day:**
    - Model (`sonnet` vs `opus`) - **kept `opus`**, no change.
    - Whole-server `mcp__playwright` grant vs per-tool list -
      **adopted** - both agents' own `tools:` frontmatter simplified
      from an explicit 12-15-tool list down to a single
      `mcp__playwright` grant.
    - Reading the app's own real design tokens before critiquing -
      **adopted** - `delivery-dashboard-visual-critic` now has a real,
      explicit step reading the dashboard template's own `:root{}`
      colour/radius custom properties before judging anything, with an
      honest caveat that there's no formal spacing-scale token to check
      against (compare against a real, similar existing element
      instead, same as before).
    - Structured "user goal/target audience" per-review input -
      **declined** - Keith's own call: keep relying on
      `docs/project-context-for-agents.md`'s general personas instead.
    - The "squint test" visual-hierarchy technique - **adopted** -
      added as a real, named check in `delivery-dashboard-visual-critic`'s
      own evaluation list.
    - The third, unexplored `doc-quality.md` agent - **not adopted, not
      yet even read** - parked as its own new item,
      `plans/tooling.md` #4, distinct from that file's existing #2
      (Python code-quality tooling generally).

    **Real, verified finding, same day: none of the 6 `requirements-*`
    agents can use the 2 real Claude Skills just installed
    (`plans/tooling.md` #5).** Keith asked directly whether the UX/
    reviewer subagents use these skills, or only the main session does.
    Didn't guess - tested it for real: a fresh general-purpose subagent
    was asked to introspect and report its own real, visible tool list
    and system-reminders. It confirmed a real `Skill` tool and a real
    system-reminder listing both `frontend-design` and
    `web-design-guidelines` among ~24 available skills - but that
    agent's own tool access is unrestricted (`tools: *`, its own type
    definition). Checked our own 6 agents' real `tools:` frontmatter
    directly (`grep -n "^tools:" .claude/agents/*.md`): none of them
    list `Skill` - `delivery-architect`/`delivery-scoper`/
    `delivery-dashboard-ux` are `Read, Grep, Glob, AskUserQuestion`;
    `delivery-critic` adds `Bash`; `delivery-dashboard-ux-critic`/
    `delivery-dashboard-visual-critic` add `Bash, mcp__playwright`. Since
    Claude Code subagent tool restriction is harness-enforced, not just
    prompt-level (confirmed earlier this session, `plans/wider.md`
    itself, the "what is a subagent" 101 thread), the real, current
    answer is: **only the main session can use these 2 skills right
    now - none of the 6 requirements-* agents can, because `Skill`
    isn't in any of their allowlists.**

    **Fixed the same day, plus a much bigger real finding underneath
    it.** Keith asked 3 more things in one message: does
    `delivery-dashboard-ux-critic`/`delivery-dashboard-visual-critic` still need
    `Bash` now they have Playwright MCP; fix `delivery-critic`'s
    stale pre-split ad hoc Bash+Playwright-script instructions; and
    (his own preferred mechanism, confirmed via the real official docs
    rather than the generic `Skill` tool) scope skill access per agent
    via the real `skills:` frontmatter field instead.

    - **Bash**: still needed, but narrowly - confirmed by grepping the
      real files, not memory. `delivery-dashboard-ux-critic`/`requirements-
      visual-critic` use `Bash` for exactly one thing, running `uv run
      mothman dashboard rebuild` to build the dashboard before
      Playwright can view it - all real browser automation is 100% via
      Playwright MCP now. `delivery-critic` also needs `Bash` for
      `pytest --cov` coverage checks, unrelated to Playwright.
    - **`delivery-critic` fixed**: its "Observable UI behaviour"
      section still described the pre-split ad hoc Bash+throwaway-
      script mechanism and had never been granted `mcp__playwright` at
      all. Now uses the same real MCP mechanism as the other two
      agents, with `mcp__playwright` added to `tools:`.
    - **`skills:` wired in, selectively, not blanket-applied**: real,
      reasoned per-agent calls, not "add both skills everywhere since
      Keith approved it." `delivery-dashboard-ux` (pre-build, never sees
      built code, and whose job - matching EXISTING patterns - is in
      real tension with `frontend-design`'s whole ethos of breaking
      from templated defaults) gets neither. `delivery-dashboard-ux-critic`
      (post-build, reviews real code) gets `web-design-guidelines`
      only - its navigation/forms/content sections are real UX-critic
      territory; `frontend-design`'s aesthetic-distinctiveness guidance
      isn't its lane. `delivery-dashboard-visual-critic` gets both - the
      single best match for `frontend-design`, plus
      `web-design-guidelines`'s visual-adjacent sections (animation,
      typography, dark mode, hover states).

    **The much bigger finding, caught by testing the fix rather than
    trusting it**: re-ran the same real diagnostic-subagent test after
    adding `mcp__playwright` to `delivery-dashboard-ux-critic` - still ZERO
    `mcp__playwright__*` tools visible, and the newly-added `skills:`
    field wasn't reflected either. Dug into why rather than assuming
    the docs were wrong: `ps aux` on this session's own real running
    `claude` process showed a FIXED `--mcp-config
    /tmp/mcp-config-cse_....json` naming only `github`/`Claude_Docs`/
    `Claude_Code_Remote` - no `playwright`, and that file's real content
    (read directly) confirmed it. This is a real, documented, correct
    mechanism (Claude Code's own cloud-environments doc, verified
    directly: "Your repo's `.mcp.json` MCP servers | Yes, in a session
    with one repository | Part of the clone, found from the session's
    working directory") - but "part of the clone" means read ONCE, at
    session start, from whatever the repo looked like at that moment.
    This session's own VM was provisioned before `.mcp.json` existed in
    the repo (added mid-session, several turns after this session
    began), so its own fixed MCP config never picked it up - not a bug
    in anything built, not an environment limitation, just a real
    timing gap between when this session started and when `.mcp.json`
    landed. The fix (`mcpServers: [playwright]` on the 3 agent files,
    the real official field for referencing an already-configured
    project server) is correct and committed regardless - genuinely
    untestable from inside this specific session, but should work for
    real the moment a fresh session clones this repo with `.mcp.json`
    already present. Flagging clearly rather than claiming victory:
    **nobody has yet confirmed Playwright MCP actually works end to end
    in a live Claude Code session on this repo** - the mobile-overflow-
    bug test earlier used the old, genuinely-working ad hoc Bash+script
    mechanism, before any of this MCP work existed. Re-run the same
    diagnostic test (spawn `delivery-dashboard-ux-critic`, ask it to report
    its own visible `mcp__playwright__*` tools) in the next fresh
    session on this repo to actually confirm it, rather than assuming.
    **Keith's own follow-up, same day: a real prompt handed to him to
    start that fresh session and confirm it himself** - see this
    file's own closing note/the session transcript for the exact text
    given.

    **`permissionMode: plan` added, selectively - Keith's own explicit
    "defense in depth" call.** Real ambiguity hit researching this
    first: a first pass at the official docs summarized `plan` mode as
    "read-only (reads files, runs read-only bash)"; a second, more
    careful direct quote-check of the same real page instead found
    `plan` described plainly as "read-only exploration," with the
    built-in `Plan` subagent's own tools stated as "read-only tools;
    Write and Edit are denied" - no documented mechanism for
    distinguishing a read-only Bash command from a real write one.
    Given that real contradiction between 2 research passes of the same
    document, and the real risk of silently breaking
    `delivery-critic`/`delivery-dashboard-ux-critic`/`requirements-
    visual-critic`'s own genuine need to run `uv run mothman dashboard
    rebuild` via `Bash` (a real filesystem write, even though only to a
    gitignored build path), applied `permissionMode: plan` only to the
    3 agents that never use `Bash` at all -
    `delivery-scoper`/`delivery-architect`/`delivery-dashboard-ux` -
    where it's unambiguously safe (pure defense-in-depth, no
    functional change, since none of the 3 could ever write a file
    anyway). Deliberately NOT applied to the other 3 yet - a real,
    open question flagged rather than guessed at, worth resolving (via
    the fresh session Keith is about to start to verify Playwright MCP
    anyway) before deciding whether `plan` mode would actually break
    their real `mothman dashboard rebuild` step or not.

    **2 more real things recorded, Keith's own ask**: a periodic check
    of the `.claude/agents/*.md` combined description-field token
    budget (now a standing `CLAUDE.md` convention, checked 2026-09-19:
    ~1,100 tokens combined, nowhere near the real 15,000-token warning
    threshold) - and Claude Code's real spawn-time model-override
    capability (plain language, e.g. "use the security-reviewer
    subagent with Opus"), also now a standing `CLAUDE.md` note, since
    Keith wants this proactively suggested when relevant rather than
    only used if he happens to remember it exists.

    **Playwright MCP connection CONFIRMED WORKING, 2026-09-19** - the
    fresh session the paragraph above anticipated. Background: the
    session that committed `.mcp.json` (8c04c54) had it added mid-session,
    after that VM had already cloned the repo, so it never picked the
    server up and the wiring was unverified. A fresh session clones with
    `.mcp.json` already present, and it does connect. Real evidence,
    three independent ways:
    - **The server process is genuinely running**: `ps aux` shows a real
      `npm exec @playwright/mcp@0.0.82 --headless --executable-path
      /opt/pw-browsers/chromium --no-sandbox --isolated` plus its own
      `node .../playwright-mcp` child, matching `.mcp.json` exactly.
    - **Loaded from the repo's own `.mcp.json`, not the harness.** This
      session's `--mcp-config` file (`/tmp/mcp-config-cse_*.json`) lists
      only `github`/`Claude_Docs`/`Claude_Code_Remote` - `playwright`
      appears nowhere in it. So the project-scoped `.mcp.json` really is
      what's supplying it, which is exactly the thing that couldn't be
      confirmed before.
    - **The tools reach the subagents, and actually function.** A
      diagnostic-only `delivery-dashboard-ux-critic` run (told explicitly not
      to review anything) reported all 25 `mcp__playwright__browser_*`
      tools visible in its own tool list, and a real
      `mcp__playwright__browser_snapshot` call returned a real, well-
      formed response from a live browser context. Tool access really is
      the harness-enforced boundary the earlier research said it was -
      the `mcp__playwright` entry in these agents' own `tools:`
      frontmatter is what carries it through.

    **One real, newly-found gap, though: the `file:` protocol is
    BLOCKED by this MCP server.** `browser_navigate` to
    `file:///home/user/data-poc/dashboard/qa-reporting-dashboard.html`
    fails with a literal `Error: Access to "file:" protocol is blocked`
    - reproduced independently in both the subagent and the main
    session, so it's the server's own default policy, not a one-off.
    That matters because `delivery-dashboard-ux-critic.md` (line 58) and
    `delivery-dashboard-visual-critic.md` (line 60) both instruct exactly that
    `file:///<repo-root>/...` navigation - as written, neither agent can
    currently open the dashboard it's meant to critique. **Verified
    workaround**: serving the repo over a plain local HTTP server and
    navigating to `http://127.0.0.1:<port>/dashboard/...` works
    completely - real page load, real title (`Data Asset QA Register`),
    real accessibility snapshot, zero page-level console errors (the one
    error seen was a `favicon.ico` 404 from the ad hoc server itself,
    not a page bug).

    **Resolved, same day - Keith chose (b), serving locally, but asked
    specifically for HTTPS rather than plain HTTP** (closer to how the
    real published site, GitHub Pages, is always served, than a bare
    local HTTP server would be). Verified the whole mechanism end to end
    before writing it into any agent's own instructions, not just
    assumed it'd work: a real ephemeral self-signed cert via `openssl
    req -x509` (1-day validity, no passphrase), Python's stdlib
    `http.server` wrapped in a real `ssl.SSLContext`, confirmed
    reachable via `curl -k` and, separately, via a real `playwright`
    Python script with `ignore_https_errors=True` (real page load, real
    title `Data Asset QA Register`, zero console errors) - the same
    context option `@playwright/mcp`'s own `--ignore-https-errors` flag
    maps onto internally. Built as a real, shared, committed dev tool
    rather than 3 separate agent-authored throwaway scripts each
    re-implementing cert generation:
    `scripts/dev/serve_dashboard_https.py` (same `scripts/dev/` throwaway-
    tooling status as `record_cast.py`/`tui_screenshot.py`, excluded
    from the coverage gate the same way - not in `[tool.coverage.run]`'s
    own `source` list). `.mcp.json` gained the real `--ignore-https-
    errors` flag. All 3 agents that drive Playwright (`requirements-
    reviewer`/`delivery-dashboard-ux-critic`/`delivery-dashboard-visual-critic`) had
    their own `file://` instructions replaced with "run the new script
    via `Bash`, navigate to `https://localhost:8743/...`, stop the
    server when done" - explicitly told **never** to navigate to a
    `file://` URL, not just told about the new alternative, so the old,
    now-broken instruction can't linger as a fallback. Rejected option
    (a) (`--allow-unrestricted-file-access`) once its real scope was
    understood - it grants `file://` access to the WHOLE filesystem, not
    just this repo, broader than the real need.

    Also fixed in passing: `.playwright-mcp/` (page snapshots and
    console logs the MCP server writes straight into the workspace root)
    was showing up untracked in `git status` - now gitignored, so a real
    browser-driven review can't leave commit-able scratch behind.

    Still open, unchanged by this session: whether `permissionMode: plan`
    would break `delivery-critic`/`delivery-dashboard-ux-critic`/
    `delivery-dashboard-visual-critic`'s own `Bash`-driven `mothman dashboard
    rebuild` step - this session verified the MCP wiring only, and
    didn't test that.

    **Resolved, 2026-09-19 evening, by the `claude/playwright-mcp-
    verify-b2t4nb` session** (asked to pick up `claude/new-session-
    en9qen` and verify several things, including this) - and it also
    found a real, important correction to the paragraph above. Couldn't
    test `permissionMode: plan` live, two ways, and correctly didn't
    work around either: a new throwaway agent file added mid-session
    isn't registered (`Agent type ... not found` - the same session-
    start-only agent-list read this project has now hit twice, see
    `delivery-cli-ux-critic`'s own entry above), and editing an
    EXISTING agent's frontmatter (`delivery-architect`, temporarily
    adding `Bash`) was denied outright by the harness's own auto-mode
    self-modification guard. So it verified the real, documented
    behaviour from Claude Code's own primary docs instead:

    - `plan` mode does NOT block `Bash` outright. Verbatim: "Claude
      reads files, runs shell commands to explore, and writes a plan,
      but does not edit your source" - "the classifier reviews shell
      commands during planning instead of prompting you. Approved
      commands run, and rejected ones are blocked. Otherwise, commands
      outside the built-in read-only set prompt for approval." So the
      real mechanism IS a read-only/side-effecting distinction (a
      built-in read-only set plus a classifier for everything else) -
      the second, more careful research pass earlier this project
      (quoted just above, "no documented mechanism for distinguishing a
      read-only Bash command from a real write one") undersold what
      actually exists. `mothman dashboard rebuild` is genuinely side-
      effecting (writes a gitignored build file), so under `plan` mode
      in a normal (non-auto) session it would prompt for approval, not
      execute silently and not get blocked outright either.
    - **The real, more consequential correction**: "When the main
      conversation is in `bypassPermissions`, `acceptEdits`, or auto
      mode, the subagent runs in that same mode and Claude Code ignores
      the `permissionMode` you set." This project's own sessions run in
      auto mode a meaningful fraction of the time (this one included) -
      in an auto-mode session, the `permissionMode: plan` added to
      `delivery-scoper`/`delivery-architect`/`delivery-dashboard-ux`
      in `ed6435f` is a real, literal no-op: the subagent just inherits
      auto mode instead. It's still correct, real protection in a
      non-auto session (the original "pure defense-in-depth, no
      functional change" framing above only holds THERE) - but the
      blanket claim needed this caveat, which the original entry didn't
      have. Confirms the decision not to apply `plan` mode to the 3
      `Bash`-using critics was still the right call either way: in a
      non-auto session, `mothman dashboard rebuild` being side-effecting
      would mean `plan` mode prompts for approval inside a subagent with
      no human there to answer it.

    **The same verification session's other real findings** (asked to
    pick up this branch and check several things at once - the full
    HTTPS/port-collision mechanism, both critics running for real, and
    the `permissionMode` question above):

    - **Mechanism confirmed working, with one honestly-labelled gap.**
      `serve_dashboard_https.py` works exactly as designed (ephemeral
      port, `PORT=<n>` parsed cleanly, `curl` 200, `kill $(cat
      $PIDFILE)` genuinely stops it) and the `cd405b9` port-collision fix
      holds for real (two servers ran concurrently on distinct ports,
      no bind error, each critic got its own). The one leg that
      genuinely couldn't be tested end-to-end: that session's own live
      MCP server process had started from the OLD `.mcp.json` (before
      `--ignore-https-errors` existed) - checking out this branch
      mid-session doesn't restart it, the same staleness class as the
      original `file://` bug. Proved the underlying mechanism correct
      anyway via a standalone script using the same server/Chromium
      (`ignore_https_errors=False` → `net::ERR_CERT_AUTHORITY_INVALID`;
      `=True` → real page, real title) - the fix is right, it just needs
      a genuinely fresh session (new MCP server process) to confirm
      through `.mcp.json` itself, same resolution as every other
      session-start-only-read gap this project keeps hitting.
    - **Both critics ran for real and produced real findings.**
      `delivery-dashboard-ux-critic` independently rediscovered `plans/
      dashboard.md` #12 (the mobile overflow bug) with NO hints, and its
      own measured number matched the already-recorded one exactly
      (`maxScrollLeft: 457`, `plans/dashboard.md` #12's own "457px wider
      than the phone"). `delivery-dashboard-visual-critic` found 3 further
      real things, each independently verified in source (not taken on
      trust) - logged in `plans/dashboard.md` alongside #15, see that
      file for detail.
    - **4 real, mechanical issues found, flagged not fixed by that
      session** (out of scope for someone else's branch): (1)
      `mothman dashboard rebuild` exits 1 in a genuinely fresh sandbox -
      not a branch bug, this sandbox's installed Chromium build
      (`chromium_headless_shell-1194`) doesn't match what the pinned
      Playwright package expects (`-1234`); the project's own
      `PLAYWRIGHT_CHROMIUM_PATH` escape hatch fixes it (exit 0 once
      set), but all 3 dashboard-driving agents' own instructions START
      with this command, so a fresh sandbox without that env var set
      could make one give up thinking something's actually broken. (2)
      `browser_take_screenshot` resolves a bare `filename` against the
      workspace root, not `.playwright-mcp/` - the visual critic's own
      `vis-*.png` files landed as untracked repo-root files (caught and
      self-corrected by relocating them before finishing, tree left
      clean). (3) After a failed HTTPS navigate, the browser context
      parks on `chrome-error://chromewebdata` and keeps reporting that
      page until explicitly navigated away. (4) The agents' own
      `sleep 1` before parsing `PORT=` held 3/3 in timed testing but is
      a real race under load, not a guaranteed wait.

    **Follow-up, same day, 2026-09-19 evening**: flagged to Keith that
    `serve_dashboard_https.py`'s fixed default port (8743) would collide
    if two of the 3 Playwright-driving agents ever ran in parallel - he
    asked for it fixed. Now defaults to `--port 0` (an OS-assigned free
    ephemeral port) and prints the real bound port as `PORT=<n>` on its
    first stdout line. All 3 agents' instructions rewritten to capture
    that output to a file (`mktemp`), read the real port back, and kill
    only their own server by PID (`kill $(cat $PIDFILE)`) rather than a
    blanket `pkill -f serve_dashboard_https` - the earlier instruction
    would have killed any other copy running in parallel too, not just
    its own. Verified for real: ran two instances concurrently, both
    bound distinct OS-assigned ports and served real content
    simultaneously (`curl -k` 200 from both).

    **Follow-up, same session, 2026-09-19 evening**: Keith's own ask -
    "we should tell one of the sub agents to care about... clean human
    readable URLs... and also to embody single page application best
    practice" - wider than just URLs. Real research done (WebSearch
    only - `smart-interface-design-patterns.com`/`rakhman.info`/
    `developer.mozilla.org`/`web.dev`/`en.wikipedia.org` all blocked,
    `CLAUDE.md`'s own blocked-domains list has the account), synthesized
    into a new `docs/spa-best-practices.md`, grounded in this
    dashboard's own real routing mechanism (read straight from the
    template's own `stateToPath()`/`pathToState()`/`navigate()`/
    `popstate` handler, not written generically) - covers URL design
    (path vs. query string), History API mechanics, deep-linking,
    scroll position, and route-change accessibility. `delivery-dashboard-ux`
    (pre-build) and `delivery-dashboard-ux-critic` (post-build) both updated
    to read it and act on it - the pairing recommended to Keith earlier
    this session, confirmed. One deliberate scope carve-out made without
    a separate round of questions (flagged in both agent files and
    below for Keith to correct if he disagrees): `delivery-dashboard-ux`'s
    existing "accessibility - not this agent's job" boundary now
    excludes general a11y but explicitly INCLUDES route-change
    accessibility (title/focus/ARIA-live), since that's structurally
    part of "does this navigation mechanism work," not general page
    accessibility.

    Real, concrete findings surfaced by grounding the guide in the
    actual template rather than writing it generically (both logged as
    `plans/dashboard.md` #15, not fixed in this pass): (1) zero
    route-change accessibility handling exists anywhere in the template
    today - no `document.title` update, no focus management, no ARIA
    live region, confirmed via a real grep returning zero matches; (2)
    `requirements.yaml`'s `REQ-DASH-020` ("Human-friendlier dashboard
    URLs") still reads `status: not_started` even though its own
    acceptance criterion was actually satisfied by
    `plans/running-thoughts.md` #9's 2026-09-18 hash-path rework - that
    work shipped outside the formal requirements pipeline, so nothing
    ever flipped the status field. Both flagged to Keith rather than
    corrected unilaterally.

    **Follow-up, same evening**: Keith allow-listed the 5 blocked
    domains and asked for the research to be redone against them, then
    to report back what changed. Real, network-level access confirmed
    via a raw `curl` (genuine 200s/301/302 - `web.dev/articles/urls` a
    genuine 404, not a block) - but `WebFetch` itself kept returning
    `EGRESS_BLOCKED` for all five even after that, a stale tool-level
    check out of sync with the live proxy policy (`CLAUDE.md`'s own
    blocked-domains entry now has the standing lesson: verify with a raw
    `curl` before trusting a repeated `WebFetch` failure post-allow-
    list). Worked around by `curl`-ing the raw HTML and reading it
    directly. Re-verified and extended `docs/spa-best-practices.md`
    against the real primary-source text (MDN, `smart-interface-design-
    patterns.com`, `rakhman.info`, Wikipedia) - refined the URL-design
    section with real length/character/slug guidance, confirmed this
    dashboard's own initial-load `replaceState` already matches MDN's
    documented pattern, and added a genuinely new section (D) grounded
    in `rakhman.info`'s own writeup: real `<a href>` elements vs. bare
    `onclick` handlers for internal navigation, so middle-click/Ctrl-
    click/copy-link-address keep working. Grounding that new section
    against the real template surfaced a real, previously-unflagged gap
    - only 5 real `<a href>` elements exist anywhere in the file, all
    external; all 39 internal drill-down navigation call sites use a
    bare `onclick` handler on a non-anchor element instead - logged in
    `plans/dashboard.md` #15 alongside the earlier accessibility gap,
    not fixed. Both `delivery-dashboard-ux`/`delivery-dashboard-ux-critic` updated
    to check for this class of gap going forward.

    **The deferred HCI/psychology grounding item, finally revisited,
    same evening.** Real process, scoped with Keith directly before any
    research started (his own ask, "let's talk through my own thinking
    first" - 2 rounds of clarifying questions, then research, then
    refine, matching a pattern this session had already used
    successfully for the SPA work): (1) both classic HCI/usability
    psychology AND behavioral/motivational psychology, roughly equal
    weight; (2) reaches BOTH the dashboard and the CLI/TUI (`mothman`) -
    a genuine scope widening from the original, dashboard-only ask; (3)
    proactive/foundational, not a response to one bad moment; (4)
    context-indexed - different principles for different interaction
    moments, Keith's own explicit ask, not a flat checklist. Real
    research done (2 rounds - a first WebSearch-only pass, then a
    second pass against real primary sources once Keith allow-listed
    `clig.dev`/`lawsofux.com`/`www.nngroup.com` and asked for it to be
    redone properly): Sweller, Nielsen, Hick's/Fitts's/Doherty/Gestalt/
    Von Restorff/Jakob's/Tesler's laws, `clig.dev`'s own real CLI
    guidelines (worked around its own block via its real GitHub source),
    real TUI design principles, Self-Determination Theory, the Fogg
    Behavior Model, Lally et al.'s real 2010 habit-formation study,
    Seligman & Maier's learned helplessness, Baumeister et al.'s real
    2001 negativity-bias paper (read via Wikipedia once allow-listed -
    the real "negativity dominance"/"dishonest person" findings),
    attribution theory via the real service-recovery-paradox literature
    (McCollough & Bharadwaj 1992, Michel & Coughlan 2009, real meta-
    analyses - read via Wikipedia), Kahneman & Fredrickson's real 1993
    peak-end study (NN/g's own real elaboration, including a genuinely
    useful worked example - a real Spotify bad-error-message case), and
    Lindgaard et al.'s real, heavily-cited 2006 50ms first-impressions
    study. Proposed a real 6-context taxonomy (at-a-glance/scanning,
    investigating/drill-down, first-time use, routine daily use, error/
    failure states, configuration/setup) mapped onto real dashboard AND
    CLI/TUI examples, plus an honest research-based weighting (error
    states > first-time use > routine daily use > the rest, stated
    plainly where the evidence is strong vs. merely theory-grounded, not
    a false uniform precision) - Keith confirmed both before anything
    got written into the repo or any agent file.

    Same real "verify a domain change before trusting WebFetch" gap hit
    again mid-research: `lawsofux.com`/`www.nngroup.com` genuinely
    reachable via `curl` once allow-listed, but `WebFetch` itself kept
    returning `EGRESS_BLOCKED` for both - same stale-tool-level-check
    class of issue as the SPA research round, same `curl`-and-read-
    directly workaround, already logged in `CLAUDE.md`'s own blocked-
    domains entry (which also now covers `clig.dev`, worked around via
    its real GitHub source instead).

    Built: `docs/hci-ux-psychology.md` (the real guide); `requirements-
    ux`/`delivery-dashboard-ux-critic` updated to read and apply it
    (context-indexed, not a flat checklist - each agent works out which
    of the 6 contexts a requirement/built result falls into, then checks
    against THAT context's own dominant principles specifically). Two
    real architectural forks resolved with Keith before building
    further (his own explicit choices, both via `AskUserQuestion`): (1)
    a genuinely NEW sibling pair, `delivery-cli-ux`/`requirements-
    cli-ux-critic`, rather than widening the dashboard pair - his own
    reasoning matched mine: the post-build mechanism genuinely differs
    (a real pty session vs. Playwright MCP), so keeping each pair's
    scope/mechanism clean beats one agent straddling two unrelated
    review mechanisms; (2) build the real CLI/TUI-driving mechanism now,
    not defer it.

    New `scripts/dev/tui_drive.py` - a persistent, addressable real pty
    session (reuses `tui_screenshot.py`'s real `pyte` terminal-buffer
    rendering and `record_cast.py`'s real CPR-answering fix, rather than
    reinventing either) exposed over a local Unix domain socket so a
    subagent can drive it step by step across separate `Bash` calls
    (`serve` in the background, then `send`/`screen`/`wait`/`alive`/
    `close` as separate client calls reading the socket path back from a
    file - same "env vars don't survive between Bash calls" reasoning as
    `serve_dashboard_https.py`'s own port-file design). A genuinely new
    protocol, not a scripted-replay tool like `record_cast.py`'s own
    fixed `--step` list - a real post-build critic needs to SEE the
    actual current screen before deciding its next action, the same
    "observe, then act" loop Playwright MCP gives the dashboard critics,
    which a pre-written script can't do; a persistent session (not a
    fresh pty per command) matters because `mothman`'s own wizard flows
    can trigger real, several-seconds-long subprocess runs, and
    replaying from scratch every step would re-trigger that real work
    repeatedly. Verified end to end against the real, live `mothman`
    wizard before being written into `delivery-cli-ux-critic`'s own
    instructions (this project's own standing discipline, same as
    `serve_dashboard_https.py`'s own pre-verification) - real
    interactive navigation, real screen capture, real wait-for-substring,
    clean process/socket shutdown confirmed, and one real, useful side-
    finding along the way: Ctrl-C at a `questionary` prompt genuinely
    goes back one step (not a full exit), matching `cli/common.py`'s own
    documented design.

    **A second, more interesting real finding surfaced by the same
    verification pass**: `cli/common.py`'s own docstring claims
    `select()`/`path_prompt()` return `None` (the "go back" signal) on
    either Ctrl-C OR Escape - real, live testing (twice, including a
    full extra second to rule out a settle-delay artifact) found Escape
    genuinely does NOT back out of a real prompt today, only Ctrl-C
    does. A real, live proof the new mechanism catches genuine gaps,
    found incidentally while verifying it, not chased down deliberately.
    Not fixed here - logged as `plans/tooling.md` #9 (root cause not yet
    investigated - a real `questionary`/`prompt_toolkit` default-
    binding gap, or a docstring that went stale after some real
    dependency version changed default behaviour), matching this
    project's own standing "whenever an actual bug is found, add a
    regression test first" convention once someone does pick it up.

    **A real, known limitation hit trying to empirically verify the new
    agent pair actually works when spawned** (the same methodology this
    session used successfully to verify the `mcpServers:` field earlier)
    - the `Agent` tool's own available-agent-type list is read once at
    session start, so `delivery-cli-ux-critic` (added mid-session)
    wasn't in this session's own list, `Agent type ... not found`. Same
    category of gap as the earlier `.mcp.json`-read-once-at-start issue
    (`plans/wider.md` #10's own earlier entry, resolved that time by a
    fresh session). Worked around by verifying the underlying mechanism
    directly (this main session driving `tui_drive.py` itself, not
    through the new subagent) rather than the full agent-level
    invocation - real, live end-to-end verification of `tui_drive.py`
    itself happened either way, just not routed through the new agent's
    own instructions text. ~~**Still open**: a real, live spawn of
    `delivery-cli-ux`/`delivery-cli-ux-critic` needs a fresh
    session (or the other already-open one) to confirm the agent files
    themselves - not just the underlying mechanism - actually work as
    written.~~

    **Resolved, 2026-09-19 evening, by the fresh `claude/delivery-
    subagents-plans-717lrx` session this anticipated** - and it closes
    the post-rename question too (commit `0e9b634` renamed all 8
    `requirements-*` agents to `delivery-*`; nothing had confirmed the
    renamed files were actually spawnable, only that they existed on
    disk). Verified three independent ways, in a session that cloned
    the repo with the renamed files already present:
    - **All 8 appear in this session's own `Agent` tool roster** under
      their new `delivery-*` names, with their real descriptions - the
      session-start-only read that caused the original gap above now
      picks them up correctly.
    - **3 were genuinely spawned**, not just listed - deliberately
      chosen to span all 3 tool profiles rather than 3 of a kind:
      `delivery-architect` (`Read/Grep/Glob/AskUserQuestion`,
      `permissionMode: plan`), `delivery-cli-ux` (same profile), and
      `delivery-cli-ux-critic` (adds `Bash`). Each was asked to recite
      its own role from the instructions it was LOADED with (not from
      re-reading its own file), and each came back with a real,
      correct, agent-specific answer - so the renamed files are being
      parsed and injected as system prompts, not merely resolving as
      names. `delivery-architect` also confirmed its own frontmatter
      reads `name: delivery-architect` / `model: opus`.
    - **Their own internal cross-references survive the rename.**
      `delivery-cli-ux-critic` grepped `.claude/agents/` for lingering
      `requirements-` strings: only 2 hits, both in
      `delivery-critic.md`, both the ordinary English phrase
      "requirements-check" rather than a stale agent name - no agent
      file still points at a `requirements-*` sibling that no longer
      exists. `delivery-cli-ux` separately confirmed both reference
      docs its instructions name (`docs/project-context-for-agents.md`,
      `docs/hci-ux-psychology.md`) resolve on disk, and
      `delivery-cli-ux-critic` confirmed `scripts/dev/tui_drive.py`
      does too.

    One real, deliberate non-finding worth recording rather than
    leaving implicit: the 5 agents not spawned here
    (`delivery-scoper`/`delivery-dashboard-ux`/`delivery-critic`/
    `delivery-dashboard-ux-critic`/`delivery-dashboard-visual-critic`)
    are covered by the roster check only, not by a live spawn - the 3
    chosen cover every distinct `tools:` profile in the set, so a 4th
    of an already-proven profile would add little, but that's a
    reasoned sample, not full coverage. The 3 Playwright-MCP-driving
    agents specifically were verified live in the earlier
    `claude/playwright-mcp-verify-b2t4nb` session (see this item's own
    account above), so the only genuinely unexercised files are
    `delivery-scoper`/`delivery-dashboard-ux`.

    Also still open, unchanged and NOT tested here: whether
    `permissionMode: plan` would break the 3 `Bash`-using critics'
    own `mothman dashboard rebuild` step - and note the caveat already
    recorded above, that in an auto-mode session (this one included)
    `permissionMode:` is ignored entirely, so this session couldn't
    have observed it either way.

    **A separate, small finding from the same sweep, flagged not
    fixed**: a repo-wide grep for stale `requirements-<agentname>`
    references outside `.claude/agents/` found 25 hits, all in
    `CHANGELOG.md`. Every one is a historical entry describing what
    those agents were genuinely called at the time they were built, so
    leaving them is arguably correct (a changelog records history, it
    doesn't get retro-edited) - but it does mean a future reader
    grepping `CHANGELOG.md` for an agent by its current name finds
    nothing. Keith's call whether that's worth a one-line note at the
    rename's own CHANGELOG entry; no code or agent file is affected
    either way.

    **Keith's own offer, same evening, not yet acted on**: he offered to
    explain more about who the real users actually are, to sharpen both
    this taxonomy/weighting (currently grounded in the generic personas
    `docs/project-context-for-agents.md` already had - data steward,
    agency data owner, pipeline maintainer) and `plans/running-
    thoughts.md` #2's own real roles (QA, peer review, manager - today
    just labels driving ticket assignment, no real description of what
    each actually does day to day). Captured here too (and in that
    file's own item #2) so it survives compaction either way - ask him
    for this directly next time revisiting either the HCI guide or the
    roles/ticketing work, don't let it quietly drop.
