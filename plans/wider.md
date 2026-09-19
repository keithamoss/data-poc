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

7. **[in-progress, 2026-09-19]** **[Testing & dev tooling]** A real,
   unified CLI for running this whole PoC - Keith's own framing, this
   session: "my goal is a human only uses the click CLI and not
   scripts." Superseded from the original `[parked, 2026-09-18]` scoping
   below (kept for the original motivation/friction account) by a long,
   multi-round design conversation the same day Thread A (the two
   on-demand `qa_tools/bdm/check_file.py` / `qa_tools/cp/check_delivery.py`
   Click CLIs, `plans/running-thoughts.md` #5) shipped - this item is the
   generalization of that same idea to every other entry point in the
   repo, reusing the already-decided `mothman` console-script name
   (`plans/wider.md`'s own earlier project-rename decision, item history
   above). **Not yet built** - Keith's own explicit standing instruction,
   still in force: "don't begin building until I give permission." What
   follows is the real, scoped design, ready to build once he gives the
   word; the two things actually built so far (dev screenshot tooling,
   this writeup itself) are called out separately at the end since
   neither counts as "beginning" the CLI.

   **Core shape, confirmed:**
   - Organized by dataset (bdm/cp) under a real interactive TUI - not
     just rich-formatted output, real arrow-key menus, confirmed
     feasible via `click`+`rich`/`rich-click` (already transitively
     present via dbt-core) plus a new `questionary` dependency for the
     menus themselves (built on `prompt_toolkit`).
   - Bare `mothman` (no args) always launches the interactive menu -
     the only entry point a human needs to remember.
   - Every command is BOTH flag-invocable AND TUI-navigable - no
     CLI-only/TUI-only split. (Earlier drafts this session proposed
     splitting "human TUI flows" from "flag-only Tier 2/3 commands";
     Keith's own correction: "just put everything in the TUI.")
   - Three-tier colour coding across every command/menu entry (Keith's
     own explicit ask - "make sure you use colors as well"): **Tier 1**
     (human, day-to-day) = green, **Tier 2** (machine/CI-only
     automation) = blue, **Tier 3** (developer debugging) =
     yellow/amber. **Tier 4** (see Population Data below) is its own,
     separately-flagged exploratory bucket. Every command/menu entry
     also gets a real 1-2 sentence description, not just a name.
   - A splash screen on TUI launch (Keith's own fun ask): a big
     `pyfiglet` block-letter "MOTHMAN" wordmark plus a hand-drawn ASCII
     moth (glowing red eyes, rendered in colour via `rich`), living in a
     new `cli/banner.py`, shown once before the main menu.
   - **"Promote"** replaces the earlier working term "commit" (rejected
     - collides with git). Promoting writes a run into the real,
     permanent `qa_results/` git history. It does **not** itself run any
     git command - the human still stages/commits/pushes separately,
     which is what already triggers CI's existing `deploy-pages.yml`
     rebuild-and-publish. No separate "publish" step - Keith: "let's
     just rely on the current thing where the git commit triggers CI
     rebuild."
   - After a run, the TUI offers to rebuild the dashboard and then
     either open the rebuilt HTML directly in the browser
     (`click.launch()`) or just prints the confirmation/path, operator's
     choice.

   **The Quality Assurance flow** (the flagship guided wizard): agency ->
   dataset -> (Child Protection only: full delivery vs. a single table,
   for partial resupplies - see the single-table design below) -> source
   mode [**Synthetic** / **Local files** / **S3**] -> browse/pick ->
   confirm the suggested dataset mapping -> run the real check chain ->
   rich-rendered report -> Promote? -> rebuild dashboard -> open in
   browser?. Three source modes are real, distinct entry points onto the
   same flow (Keith: "there's, there's three ways to run QA for a given
   data set"), not one mode with options:
   - **Synthetic** - pick an existing generated run, or generate a new
     one on the spot if none exists yet, then check it. Reference/
     baseline file for Evidently drift defaults to the last **Promoted**
     run in `qa_results/` history for that dataset (asks instead if
     nothing's been promoted yet).
   - **Local files** - a configured default root per dataset, browsed
     via `questionary.path()` (ready-made tab-completion browsing, no
     hand-built file picker needed). This is also where Thread A's two
     existing CLIs retire to: "humans will be using the browsable local
     files point, so they're never going to touch [check_file.py]
     directly" - their real logic (the dbt/Soda/datacontract-cli/
     Evidently chain against an already-downloaded file/folder) folds
     into this mode rather than staying as separate standalone commands.
   - **S3** - real `boto3` against real config, verified only via
     mocks (no real AWS access in this sandbox -
     `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` are literal
     `"proxy-injected"` here, same as Thread B). S3 location config
     lives as new `s3Source`/`localSource`/`arrivalPattern`
     `customProperties` entries on each dataset's own real ODCS contract
     YAML (a top-level `customProperties:` block already exists there,
     e.g. `currentDeliveryFormat`/`piiClassification` in
     `contract/bdm-birth-registrations-contract.yaml`).

   **Single-table Child Protection QA (design confirmed, not yet
   built)**: CP's real dbt models need all 6 tables present (`ref()`/
   `source()`), so a single-table check can't just run a reduced set -
   it automatically pulls the most recent **Promoted** state of the
   other 5 tables, builds a combined warehouse, and runs the full check
   suite including the cross-table checks. Grounded in real precedent
   already in this codebase: `generator/resupply.py` already models "a
   resupply might only touch a subset of tables, the rest carry forward
   unchanged" - this reuses that same idea for a human-driven partial
   delivery instead of a synthetic one.

   **Generate/Regenerate synthetic data** - its own Tier 1 top-level
   command group, wrapping the real, unmodified
   `generator.generate_runs`/`generator.generate_cp_runs` - including
   their existing resupply-chain and dirty-severity-preset simulation,
   confirmed NOT to be stripped down for this ("that should also include
   the... resupply stuff where it kind of has broken resupplies and so
   forth"). Confirmed (by reading `pipeline/orchestrate.py`) that
   `prepare_warehouse(regenerate=True)` already fuses "generate" and
   "build the combined warehouse" into one function - so this is one
   command, not two, correcting an earlier draft of this design that had
   wrongly split them. **Naming resolved, 2026-09-19**: an earlier
   session had settled on a shorter alternative to bare "generate" (to
   avoid reading as dev-only, since operators mostly run this against
   real-shaped data day to day) but the exact string was lost to context
   compaction; re-asked directly, and Keith's answer was to keep the
   full, self-explanatory phrase rather than a single-word rename - the
   command/menu label is **"Generate synthetic data"** (e.g.
   `mothman bdm generate-synthetic-data` / `mothman cp
   generate-synthetic-data` as the flag-invocable form), not a cute
   one-word verb. Explicitly saying "synthetic data" in the name is
   itself what avoids the dev-only-sounding ambiguity a bare "generate"
   had.

   **Tier 4 - Population Data**: `synthetic_data_generator/` (the
   separate, population-scale, cross-agency-identity-linked generator,
   not currently wired into the pipeline) gets its own top-level CLI
   entry point too, explicitly flagged exploratory in its own
   description - Keith wants to revisit and collapse it down to a single
   generator eventually, but happy to expose today's version in the
   meantime rather than hide it.

   **Debug group (Tier 3)**: `qa_tools/common/changelog.py` and similar
   internal/diagnostic modules that a human would otherwise have no way
   to run by hand - Keith: "if it wasn't in the CLI, how would a human
   debug it?" - live under a `mothman debug ...` subcommand group rather
   than being left out of the CLI entirely.

   **Full-pipeline run** stays a real command but Tier 2, not
   human-facing - "that's more there for like integration tests and for
   yourself and not there for the humans." Exact shape (a
   `mothman pipeline run` replacing `run_pipeline.sh` outright, vs.
   something narrower) still open - "I'm open to how we do that."

   **Trogon** (`Textualize/trogon`, auto-generates a Textual TUI from a
   Click app's own introspection) - researched, not adopted for the core
   guided flows: a good fit only for flag-heavy, non-branching commands,
   a poor fit for the Quality Assurance wizard's real conditional
   branching. Flagged as an optional future bonus (a `mothman tui`
   fallback) rather than anything in the phase plan below.

   **`questionary` chosen over alternatives on real, sourced project-
   health grounds** (Keith's own explicit due-diligence ask before
   committing to a new dependency): `PyInquirer` is effectively dead,
   built on the unmaintained `blessed`; `InquirerPy`'s last real commit
   was ~May 2022, last release (0.3.3) February 2023 - 3.5+ years stale
   as of this project's own "today," with a community fork existing
   because of that upstream inactivity; `questionary` is actively
   maintained (v2.1.0, updated ~1 month before this check, two named
   maintainers, live CI/dependabot activity). `questionary.path()` is
   also directly reusable for the Local-files source mode's browsing UI,
   rather than needing a hand-built file picker.

   **TUI design considerations, from real online research (2026-09-19,
   Keith's own explicit "one last check before we proceed" ask) - 5
   concrete additions to the Phase 1 design, sourced rather than
   guessed:**
   - **Non-TTY guard.** `questionary`/`prompt_toolkit` can crash outright
     in a non-terminal context (a script, some CI runners, an IDE
     console) rather than degrading gracefully. Every TUI entry point
     must check `sys.stdin.isatty()` before calling into `questionary`
     and fail with a clear message pointing at the equivalent
     flag-based invocation, not a stack trace - the wizard/flags duality
     already designed (every command both flag-invocable and
     TUI-navigable) only actually holds together with this guard in
     place.
   - **Never encode meaning in colour alone.** Every Tier
     (green/blue/amber) and status indicator needs a real text label
     alongside its colour, not colour as the only signal - real practice
     from GitHub CLI's own accessibility work. Respecting
     `NO_COLOR`/`FORCE_COLOR`/`CLICOLOR` env vars is `rich-click`'s
     already-default behaviour - explicitly don't override that default.
   - **Confirm-by-default on writes, with a bypass.** **Promote** (writes
     real, permanent `qa_results/` history) and **Generate/Regenerate
     synthetic data** (can overwrite local generated data) should both
     default to an explicit `[y/N]` confirmation (no as the safe
     default), with a `--yes` flag to bypass it for repeatable/scripted
     use - not removing the prompt, bypassing it. Worth a `--dry-run` on
     Promote specifically, showing what would be written without writing
     it, given how permanent that write is meant to be.
   - **Back-navigation gap in the QA wizard - a real, previously
     undesigned hole.** `questionary` prompts have no native "go back a
     step" support, and the agency -> dataset -> source-mode -> ...
     chain as designed has no way to back up if the operator picks
     wrong partway through. Fix: inject a "<- Back" choice into every
     `select()` menu in the chain, decided now rather than retrofitted
     after Phase 1 ships.
   - **Default output stays human-readable; raw/developer detail is
     opt-in.** Standard CLI guidance (clig.dev): don't show
     developer-only output by default. Applies to the Tier 3 debug
     commands and to the QA flow's own report - the default report stays
     the rich-rendered summary already designed, with raw dbt/Soda/
     datacontract-cli/Evidently tool output behind an explicit
     `--verbose`/`-v`.

   (Two other things researched came back as confirmation of what was
   already designed, not new work: the wizard/flags duality itself is a
   real, named pattern - "wizards and flags aren't opposites... the
   wizard is the flags with training wheels" - and the planned
   spinner-under-10s / step-progress-bar-otherwise split for `rich.
   progress.Progress` already matches real progress-indicator UX
   guidance.)

   **Build order (revised 2026-09-19 to fold in what Generate/Synthetic
   and single-table CP QA need to already exist):**
   1. **Phase 1** - `cli/` package scaffold; `mothman` console-script
      entry (`[project.scripts]`); add `questionary`/`pyfiglet` as real
      dependencies, promote `rich`/`rich-click` from transitive to
      direct; the splash screen; three-tier colour coding; the
      Quality Assurance flow against **Synthetic** source mode only;
      the Generate/Regenerate synthetic data command (needed by that
      same flow's "offer to generate if missing" step, so it can't ship
      later than Phase 1); Promote + dashboard rebuild + open-in-browser.
   2. **Phase 2** - Local-files QA source mode (`questionary.path()`);
      retire `qa_tools/bdm/check_file.py`/`qa_tools/cp/check_delivery.py`
      as standalone CLI entry points, folding their logic in here.
   3. **Phase 3** - S3 QA source mode (real `boto3`, mocked-only
      verification) + the new `s3Source`/`localSource`/`arrivalPattern`
      contract `customProperties`.
   4. **Phase 3.5** - single-table Child Protection QA (auto-pull last-
      Promoted state of the other 5 tables, full check suite) - depends
      on Phases 1-3's QA flow already existing to extend.
   5. **Phase 4** - reorg the remaining scripts into the CLI tree.
      **Real enumeration (2026-09-19), replacing an earlier vague "~20"
      estimate lost to context compaction** - every real script entry
      point in the repo (`grep -rl '__name__ == "__main__"'` across
      `qa_tools/`, `pipeline/`, `generator/`, `dashboard/`, `aws/`,
      `synthetic_data_generator/`), re-derived from the actual codebase
      rather than from memory, minus the 6 already named in Phases 1-3
      (`check_file.py`/`check_delivery.py`, `generate_runs.py`/
      `generate_cp_runs.py`, `orchestrate_bdm.py`/`orchestrate_cp.py`):
      25 remain. Grouped by real role, not just left as a flat list:
      - **Dashboard rebuild chain (Tier 2)**: `pipeline/
        build_dashboard_data.py`, `pipeline/build_cp_dashboard_data.py`,
        `qa_tools/bdm/build_results_from_history.py`, `qa_tools/cp/
        build_results_from_history.py`, `dashboard/
        embed_dashboard_data.py`, `dashboard/check_dashboard_renders.py`,
        `dashboard/snapshot_dashboard.py` (opt-in) - likely one
        `mothman dashboard rebuild` command wrapping the whole chain,
        not 7 separate ones.
      - **GitHub workflow/people automation (Tier 2)**: `qa_tools/
        common/ticket_sync.py`, `qa_tools/common/acceptance_sync.py`,
        `qa_tools/common/leaderboard.py`.
      - **CI validation gates (Tier 2)**: `qa_tools/common/
        validate_check_lifecycle.py`, `qa_tools/common/
        validate_requirements.py`.
      - **Per-tool debug runners (Tier 3, the real answer to "if it
        wasn't in the CLI, how would a human debug it")**: the 8
        individual `run_{dbt,soda,datacontract,evidently}_{bdm,cp}.py`
        modules (run one real tool in isolation against a run already on
        disk) plus `qa_tools/common/changelog.py` (already named),
        `qa_tools/bdm/build_per_run_warehouses.py`, `qa_tools/cp/
        build_cp_warehouses.py`, and `pipeline/load.py` - all under the
        `mothman debug` group.
      Rewrite the 3 GitHub Actions workflows to call `mothman`
      subcommands; retire `run_pipeline.sh`.
   6. **Phase 5** - Tier 4 Population Data command
      (`synthetic_data_generator/`), flagged exploratory.
   7. **Phase 6 (new, 2026-09-19)** - a recorded CLI/TUI demo embedded in
      the dashboard as a genuinely new top-level "Demo" tab (Keith's own
      call today - a new tab, not a small panel folded into an existing
      one; built after the core CLI exists and there's something real
      worth recording, not before). Real GitHub Pages hosting is static
      only - no backend to run a real interactive terminal behind a
      websocket - so this is a **recording**, not live interactivity:
      script real, deterministic keystrokes into the actual `mothman`
      CLI (same pty-capture technique as the dev screenshot tooling
      below), capture to an asciinema-format `.cast` file (plain
      timestamped JSON, no video encoding), and replay it with the
      static/offline-capable `asciinema-player` JS widget (no server, no
      asciinema.org account). A real recording of real CLI behaviour,
      not a mockup. New committed asset directory, analogous to the
      existing `dashboard/snapshots/*.html.gz` pattern (e.g.
      `dashboard/demos/*.cast`).

   **Already built, ahead of Phase 1 (approved by Keith as prep, not
   counted as "beginning" the CLI itself - it's throwaway dev tooling,
   never imported by the shipped pipeline/CLI)**: `scripts/dev/
   tui_screenshot.py` - spawns a real command in a real pseudo-terminal
   (stdlib `pty`), scripts fake keystrokes into it, and resolves the
   captured raw ANSI byte stream through a real terminal-emulator buffer
   (`pyte`, new dev-only dependency) into the actual on-screen character
   grid - necessary because `questionary`/`rich` redraw in place via
   cursor-movement/erase codes, so the raw byte stream alone isn't what a
   human would actually see. Renders that grid to HTML and screenshots it
   via this sandbox's pre-installed headless Chromium (pinned to its
   actual installed build, `chromium-1194`, via an explicit
   `executable_path`, since it lags the `playwright` package's own
   expected version here). Verified end to end against a small real
   `rich` demo (`scripts/dev/demo_rich_sample.py`) - a real screenshot
   was sent to Keith directly in chat. Will be reused through Phase 1+
   to show real TUI/CLI visuals as they're built, not just described.

   **Original scoping, 2026-09-18 (superseded by the above, kept for
   history):** A real CLI for running this PoC, built on Python's
   `click` library - Keith's own framing: "the goal is to give humans a
   user-friendly tool to use to run this PoC on real and fake data."
   Today's actual entry points, confirmed against `README.md`: BDM has
   one (`./run_pipeline.sh`, a plain shell script wrapping 4
   `uv run python3 -m ...` calls), but Child Protection has no wrapper at
   all - generating + running + building dashboard data for CP is 3
   separate, manually-typed commands, each needing the right module path
   remembered and run in the right order. Real friction for anyone other
   than whoever's been living in this repo daily.

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
