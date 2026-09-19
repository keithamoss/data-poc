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
      instructions now built directly into `requirements-reviewer.md`
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
      convention, `requirements-scoper` explicitly asks multiple rounds
      of clarifying questions and escalates genuine forks rather than
      resolving them itself). `zhsama`'s reviewer stage directly edits
      code; this one's `requirements-reviewer` is strictly read-only,
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

    1. `requirements-scoper` - turns a raw idea into EARS-format
       requirements, splitting a big idea into several small
       self-contained ones (Keith's own explicit call: "I'm keen for
       requirements to remain pretty small and self-contained") rather
       than one sprawling entry, plus a draft `plans/*.md` entry. Asks as
       many rounds of clarifying questions as it takes - never settles
       for an assumption.
    2. `requirements-architect` - a genuinely "simple" architect (Keith's
       own framing), NOT full software design: duplication/overlap
       detection against the real codebase (the exact class of problem
       the `generator/`/`synthetic_data_generator/` drift bug already
       demonstrated for real), fit within `mothman`'s existing command
       structure, cross-component blast radius, security, and code-
       quality/clean-code expectations for the builder - plus an
       optional lightweight architecture/data-model sketch, only when it
       would genuinely help.
    3. `requirements-ux` - dashboard-only (not the CLI/TUI, not
       accessibility - Keith's own explicit scope choices), checking
       consistency with the dashboard's real existing UI patterns and
       workflow/information-architecture fit, advisory only, alongside
       the architect, before anything is built.
    4. `requirements-reviewer` - merged reviewer + fresh-context QA-
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
      `requirements-ux.md` and `requirements-reviewer.md`'s own
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
      `requirements-reviewer` now**, not deferred - Keith explicitly liked
      the idea flagged during the UX-agent scoping research (a real-
      world precedent, VoltAgent's `ui-ux-tester`: a "frustrated
      end-user" persona doing actual Playwright-driven visual QA) and
      asked for it built into the current reviewer rather than parked.
      `requirements-reviewer` now does a real, separate visual-QA pass
      for dashboard-facing requirements only, adopting a busy/moderately-
      attentive data-steward persona, taking real screenshots as
      evidence (spacing, interaction states, dark mode, whether a
      confused click-path is possible), checked against the same
      Apple-level bar - and, since `requirements-ux`'s own pre-build note
      is a real standard to check against (same "not implementation
      reasoning" treatment `requirements-architect`'s note already gets),
      the reviewer is explicitly told it may be given that note too.

    **Deliberately not yet done, Keith's own explicit call**: deeper
    grounding of `requirements-ux`'s own intent in real human-psychology/
    HCI research (not just "consistency + workflow fit"). Revisit once
    this refinement round is in hand, not before.

    **Correction, same day**: Keith's earlier "let me do some research
    online" on whether real precedent exists for a UX-reviewer-agent
    role was reversed - he wants this session to do that research, not
    him.

    **UX-reviewer-agent precedent research, done same day.** Real
    precedent exists, and this project's own design (a genuinely
    separate `requirements-ux` pre-build agent, plus a post-build
    visual-QA pass folded into `requirements-reviewer` rather than kept
    as its own third agent) lines up with how others have actually built
    this:
    - `cfisch3r/estimate` PR #91 - a real repo running two SEPARATE
      Claude Code subagents, `design-critic-ux` (UX heuristics) and
      `design-critic-visual` (visual design), both wired to a Playwright
      MCP server for "live screenshot-based UX and visual design review"
      against a running dev server - the same "drive a real browser,
      don't just read code" mechanism `requirements-reviewer`'s own
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
      directly validates `requirements-reviewer`'s own "never mark a
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
    of `requirements-ux`'s own intent in real human-psychology/HCI
    research - this precedent research answered "does a UX-reviewer role
    exist elsewhere," not "what does the psychology literature say about
    good UX," which is a separate, deliberately deferred question.

    **Requirements-register schema refined further, same day** - three
    more real follow-up asks, before the agent system's first real run:
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
    - **`requirements-scoper` now genuinely asks Keith about non-
      functional requirements**, not just derives them from the
      codebase itself - a real `AskUserQuestion` step added alongside
      the existing "check against this project's own standing rules"
      one, Keith's own explicit call that relying on self-derived NFRs
      alone wasn't enough.
