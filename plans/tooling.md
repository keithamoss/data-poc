# Testing & dev tooling

Real developer/testing tooling for this PoC that doesn't belong to any
one dataset or pipeline stage - the unified `mothman` CLI/TUI design (the
single item that outgrew `plans/wider.md` and justified this file, see
that file's own item #7 for the pointer) and the throwaway dev-only
scripts built to support building it. Split out of `plans/wider.md`
2026-09-19 (Keith's own explicit ask, once that one item had grown far
larger than anything else in that file) - see `plans/wider.md`'s own
intro for the account of its earlier, larger 2026-09-18 split into
`plans/dashboard.md`/`plans/data-generation.md`, which this mirrors at
smaller scale.

Status values: `todo` / `investigate` / `in-progress` / `parked` /
`done` / `superseded`. Every item also carries a Component tag - see
`plans/running-thoughts.md` item #10 for the shared taxonomy this and
`CHANGELOG.md` both use. IDs (`tooling-N`, referenced elsewhere as
`plans/tooling.md #N`) are permanent once assigned - never renumbered or
reused, even if an item is later retired, matching `qa_tools/common/
check_lifecycle.py`'s own `check_id` convention (same rule `plans/
wider.md`/`plans/dashboard.md`/etc. already state for their own items).

1. **[done, 2026-09-19]** **[Testing & dev tooling]** A real,
   unified CLI for running this whole PoC - Keith's own framing, this
   session: "my goal is a human only uses the click CLI and not
   scripts." All 6 phases below shipped (Phase 6, the recorded demo
   tab, was the last one in the build order - no further phase is
   scoped after it). **One real, still-open verification gap, flagged
   rather than silently left implicit**: `cli/pipeline.py`'s `mothman
   pipeline run` (Phase 4) - the full-manifest batch mode that
   regenerates synthetic data and runs all 4 real tools against EVERY
   run - was never actually executed end to end for real in this
   session's own sandbox; the one attempt was blocked by the sandbox's
   own auto-mode classifier as a "shared resources" write (it writes
   real, permanent `qa_results/` history across the whole manifest).
   Verified instead via code review plus every function it calls
   individually already being smoke-tested working correctly - a real,
   deliberate substitute, not a gap that went unnoticed, but genuinely
   not the same as having actually run the command. Worth a real run of
   `mothman pipeline run` (no flags, the default `--dataset all`) at
   some point to close this out properly. Superseded from the original
   `[parked, 2026-09-18]` scoping
   below (kept for the original motivation/friction account) by a long,
   multi-round design conversation the same day Thread A (the two
   on-demand `qa_tools/bdm/check_file.py` / `qa_tools/cp/check_delivery.py`
   Click CLIs, `plans/running-thoughts.md` #5) shipped - this item is the
   generalization of that same idea to every other entry point in the
   repo, reusing the already-decided `mothman` console-script name
   (`plans/wider.md` #5, the project-rename decision).

   **Build started 2026-09-19, Keith's own explicit go-ahead** ("feel
   free to just start working through the phases... only stop if you
   need my input") - the standing "don't begin building until I give
   permission" instruction above is now lifted. **Phase 1 progress, real
   and verified, not just written:**
   - `cli/` package: `cli/app.py` (root `mothman` Click group, bare-
     invocation TUI main menu), `cli/common.py` (the non-TTY guard,
     confirm-by-default+`--yes`, the back-navigation-aware `select()`,
     the tmp-dir-first Promote helper), `cli/banner.py` (the splash
     screen - iterated visually via `scripts/dev/tui_screenshot.py`'s
     own real screenshots, both themes and the actual production ASCII
     size, before landing), `cli/bdm.py` (Birth Registrations commands).
   - `mothman bdm generate-synthetic-data` and `mothman bdm qa
     [--run-id/--reference-run-id/--commit]` are real, working, flag-
     invocable AND TUI-navigable (one implementation, both entry paths) -
     verified against the real dbt-core/Soda Core/datacontract-cli/
     Evidently chain, not mocked. `[project.scripts] mothman` is declared
     in `pyproject.toml` but not actually wired (this repo has never been
     properly packaged - `uv sync` warns "not packaged" - and doing so
     properly is a bigger, separate lift than Phase 1 needs); a thin
     `./mothman` wrapper script (same pattern as `./run_pipeline.sh`)
     gives a real `./mothman` command today without that packaging risk.
   - `questionary`/`pyfiglet` added as real dependencies; `rich`/
     `rich-click` promoted from transitive to direct, per the original
     design.
   - **A real bug found and fixed while building this, not just
     designed-around**: `orchestrate_bdm.run_single()` unconditionally
     overwrites `RAW_DIR/manifest.json` with its own synthetic 1-or-2-
     entry manifest - correct for its real AWS Lambda use case (no
     pre-existing manifest there at all), but a real collision once
     called against a `RAW_DIR` that already holds the real, full
     `generate_runs.py` batch manifest this CLI's own run picker reads
     from. A manual smoke test actually corrupted the real, local
     `data/raw/manifest.json` from 176 entries down to 1 before this was
     caught. Fixed in `cli/bdm.py`'s own `run_check()` (backs the real
     manifest up and restores it around the call, rather than changing
     `run_single()`'s already-tested Lambda-path contract) - a real
     regression test added first, confirmed failing, then fixed,
     confirmed passing, same as every other real bug this project finds.
   - Verified end to end: the real check chain runs and reports
     correctly through both the flag-invocable command and the real,
     interactive TUI (arrow-key navigation confirmed via a real pty
     screenshot, not just code review); throwaway vs `--commit` both
     behave correctly against the real committed `qa_results/` tree;
     `uv run pytest`/`ruff` both clean, 490 tests passing (18 new).
   - **Phase 1 finished 2026-09-19**: `cli/cp.py` (Child Protection
     commands) built on the same pattern as `cli/bdm.py`, adapted for
     CP's real differences - a 6-table-per-run collection (not one CSV),
     `run_check()` loading both the target and reference run's 6 tables
     into their own per-run warehouses via `build_cp_warehouses.
     add_table_to_run()` before calling `orchestrate_cp.run_single()`
     (the same pattern `qa_tools/cp/check_delivery.py`'s own
     `_load_delivery()` already established for local-folder CP checks,
     reused here against an existing Synthetic manifest run's own
     `data/cp_raw/<run_id>/` directory instead of an arbitrary folder),
     and no row-count-growth/`previous_run_id` concept (CP has none).
     `mothman cp generate-synthetic-data` and `mothman cp qa
     [--run-id/--reference-run-id/--commit]` are real, working, both
     flag-invocable and TUI-navigable - verified against the real
     dbt-core/Soda Core/datacontract-cli/Evidently chain (177 real
     checks, 0 fail) against real, existing local CP data, not mocked;
     `cli/app.py`'s TUI main menu now offers a real Birth Registrations/
     Child Protection dataset picker for both the QA and generate-
     synthetic-data flows (previously a single-choice stand-in menu for
     BDM only), confirmed via a real pty screenshot showing the Child
     Protection branch of both menus. `uv run pytest`/`ruff` both clean
     (13 new CP CLI tests + 3 new app-menu tests). Phase 1 is now fully
     done - Phase 2 (Local-files QA source mode) is next.
   - **Phase 2 finished 2026-09-19**: Local files QA source mode, both
     flag-invocable (`mothman bdm qa --file <csv> --reference-file
     <csv>` / `mothman cp qa --folder <dir> --reference-folder <dir>`)
     and TUI-navigable (a real "Which source?" picker now precedes the
     existing Synthetic-only run picker in both `run_qa_interactive()`
     bodies, browsed via a new `common.path_prompt()` -
     `questionary.path()` with the same non-TTY guard/Back-navigation
     treatment every other prompt gets). `qa_tools/bdm/check_file.py`/
     `qa_tools/cp/check_delivery.py` are **retired and deleted** (not
     just superseded) - their real logic folded verbatim into
     `cli/bdm.py`'s `run_check_local_file()`/`cli/cp.py`'s
     `run_check_local_folder()`; `qa_tools/common/local_check.py`'s
     shared `run_id_from_path()`/`copy_into()` outlived them (called
     from the CLI modules now), its `format_report()` did not (replaced
     by the richer `rich.table.Table` report both source modes already
     shared). Two real bugs caught and fixed before they could bite,
     proactively rather than via a live incident (same manifest-
     clobbering bug class Phase 1 found for real, recognized early here
     instead): (1) `orchestrate_bdm.run_single()`'s manifest-clobbering
     side effect applies to Local files mode too (an arbitrary
     downloaded CSV has nothing to do with the batch manifest, but
     `run_single()` doesn't know that) - fixed by extracting Phase 1's
     backup/restore fix into a shared `_run_single_preserving_manifest()`
     helper, now used by both source modes, with a fallback for the
     case where no manifest exists yet at all (Local files mode's own
     first-ever call). (2) A real ordering bug in `local_run_id_from_path()`
     calls: since a Local-file run_id embeds a real UTC timestamp, calling
     it twice (once for the CLI's own report/promote call, once inside
     `run_check_local_file()`'s own default-run_id fallback) would silently
     produce two DIFFERENT run_ids - fixed by always computing it once at
     the call site and passing it through explicitly. Verified end to end
     against real local data outside any manifest (a real BDM CSV, 79
     checks; a real CP 6-table delivery folder, 177 checks) - not mocked,
     and the real batch manifests (176 BDM / 18 CP entries) confirmed
     untouched afterward. `uv run pytest`/`ruff` both clean (511 passing,
     only the 13 pre-existing, unrelated Playwright chromium-binary-
     mismatch errors this sandbox already had). `README.md`'s "On-demand
     checks" section rewritten for the new `./mothman bdm qa --file`/
     `./mothman cp qa --folder` commands. Phase 3 (S3 QA source mode) is
     next.
   - **Phase 3 finished 2026-09-19**: S3 QA source mode, both flag-
     invocable (`mothman bdm qa --s3-key <key> --s3-reference-key <key>`
     / `mothman cp qa --s3-delivery <prefix> --s3-reference-delivery
     <prefix>`) and TUI-navigable (a third "S3" choice on the existing
     "Which source?" picker in both `run_qa_interactive()` bodies) - real
     `boto3`, verified only via a mocked client (no real AWS access in
     this sandbox, same as Thread B). New `qa_tools/common/s3_source.py`
     (`list_keys()`/`list_delivery_prefixes()` via S3's own
     `Delimiter="/"` grouping/`download_key()`/`download_prefix()`) is
     the only new check-running surface - both `cli/bdm.py`'s
     `run_check_s3()` and `cli/cp.py`'s `run_check_s3_delivery()` are
     "download, then Local files mode" (download into a fresh staging
     dir, then call Phase 2's own `run_check_local_file()`/
     `run_check_local_folder()`), not a third parallel check-running
     code path - the real tool-chain correctness for whatever lands on
     disk is already covered by Phase 2's own real integration tests, so
     Phase 3's own tests stay fast unit tests (mocked download +
     monkeypatched delegate call) plus real `--help`/flag-validation
     coverage through `CliRunner`.

     A real, previously-flagged fork got resolved along the way, not
     silently: `docs/aws-event-driven-mvp-design.md` had proposed a real
     `arrivalPattern` ODCS contract `customProperties` extension for
     Thread B overnight, but explicitly kept it OUT of the real
     `contract/*.yaml` files - one of that doc's own "confirm in the
     morning" open items, since there was no safe way to verify
     overnight that it wouldn't break real dbt/Soda/datacontract-cli
     parsing (the exact class of mistake `CLAUDE.md`'s own YAML-quoting
     incident already caused once). Flagged to Keith directly before
     touching the real contract files; his call ("verify then wire it
     all in") was to add all 3 real `customProperties`
     (`s3Source`/`localSource`/`arrivalPattern`) to both `contract/
     bdm-birth-registrations-contract.yaml`/`contract/child-protection-
     contract.yaml` now that real tool access exists to actually verify
     it, rather than deferring or building a stripped-down version.
     Verified for real, not assumed: a real `DataContract(...).lint()`
     call against both changed files (`ResultEnum.passed`), the real
     `tests/test_run_datacontract_{bdm,cp}.py` integration suite (7
     passing, real data), `check_lifecycle.py`'s own contract quality-
     rule parser (27/62 checks, unchanged counts - confirming the new
     top-level `customProperties` entries don't interfere with the
     quality-rule-scoped ones it actually reads), and the real
     `validate_check_lifecycle` CI gate (`zero errors`). `s3Source`
     (the real `bdm/`/`cp/` prefixes, matching `aws/cdk/
     data_pipeline_stack.py`'s own S3 event-notification filter
     prefixes exactly) and `localSource` (`data/raw`/`data/cp_raw`, the
     same real `RAW_DIR`/`CP_RAW_DIR` constants `qa_tools/bdm/
     build_per_run_warehouses.py`/`qa_tools/cp/build_cp_warehouses.py`
     already use) are real, load-bearing config a new `qa_tools/common/
     s3_source.dataset_s3_config()` reads back out of the contract at
     CLI runtime - not decorative. The real raw-data bucket's own name
     is env-provided (`MOTHMAN_RAW_BUCKET_NAME`, read dynamically via a
     new `cli/common.raw_bucket_name()`), never hardcoded in the
     contract, since CDK auto-generates a globally-unique bucket name at
     deploy time (no fixed `bucket_name=` on either bucket in that
     stack). `README.md`'s "On-demand checks" section extended with the
     new S3 commands. `uv run pytest`/`ruff` both clean (531 passing -
     13 new BDM S3 tests, 6 new CP S3 tests - only the same 13
     pre-existing, unrelated Playwright chromium-binary-mismatch errors
     this sandbox already had); real `--help` output checked by hand for
     both commands. The exact real CI coverage command (`--cov=qa_tools
     --cov=pipeline --cov=generator --cov=dashboard`, no `--cov=cli` -
     `.github/workflows/test.yml`'s own invocation) passes clean at
     94.52%, comfortably above the 92% floor - `pyproject.toml`'s own
     `[tool.coverage.run] source` list already names `cli` too (added
     whenever Phase 1 landed), but since explicit `--cov=` flags take
     precedence over that config for what pytest-cov actually measures,
     `cli/`'s real coverage (a lot of thin, interactive TUI-prompt code
     genuinely not exercised by tests yet) isn't actually part of the
     enforced gate today - noted here as a real, live discrepancy
     between config and enforcement, not acted on unprompted since it's
     outside this item's own scope.
   - **Phase 3.5 finished 2026-09-19**: single-table Child Protection QA
     (`mothman cp qa --table <table> --file <csv>` / `mothman cp qa
     --table <table> --s3-key <key>`, both flag-invocable and
     TUI-navigable via a new "Full delivery or single table?" choice
     right after picking CP - single-table's own "Which source?" step
     only offers Local file/S3, since Synthetic mode's manifest runs are
     always full 6-table deliveries by construction, so "single table"
     has no real meaning there). This design was confirmed but not
     code-level-specified ("it automatically pulls the most recent
     Promoted state of the other 5 tables") - the concrete
     interpretation built here, not re-asked since it's a reasonable
     reading of an already-confirmed design, not a fresh fork:
     `raw_dir()` (`data/cp_raw/`) is the only place this PoC durably
     keeps CP table data once a check has finished running, so "the most
     recent Promoted state" resolves via the exact same
     `default_reference()` the Synthetic flow already uses (last
     Promoted run, falling back to the manifest's own first entry) -
     that same run doubles as the Evidently drift baseline too, so
     single-table mode needs no separate reference flag the way
     full-delivery Local files/S3 mode does. A real, explicit limitation
     documented rather than silently assumed: single-table mode needs at
     least one CP run already generated/Promoted locally to source the
     other 5 tables from - a real `ClickException` if none exists,
     never a silent wrong answer.

     `cli/cp.py`'s `run_check_single_table()`/`run_check_s3_single_table()`
     build the fresh table's warehouse from 2 sources in one run_id (the
     new table via `add_table_to_run()` pointed at the fresh file, the
     other 5 via the same call pointed at `raw_dir()/<other_tables_run_id>/
     <table>.csv`), then call `orchestrate_cp.run_single()` exactly like
     every other CP source mode - not a new check-running path, just a
     new way of assembling one run's warehouse. 8 new unit tests
     (monkeypatched `default_reference`/`_load_delivery`/
     `add_table_to_run`/`orchestrate_cp.run_single` - the real per-tool
     correctness is already covered elsewhere, this proves the RIGHT 6
     tables from the RIGHT 2 sources get loaded) plus a real end-to-end
     smoke test against real local data (`mothman cp qa --table
     cp_clients --file data/cp_raw/cp_run_14_.../cp_clients.csv`,
     deliberately mismatched against `cp_run_15`'s other 5 tables - a
     real 177-check run, 120 pass/7 warn/50 fail-or-error, confirming
     both that the combined warehouse genuinely builds and that a real
     cross-run table mismatch produces real cross-table referential-
     integrity failures rather than silently passing - exactly the
     scenario this feature exists to catch). Confirmed the real
     `data/cp_raw/manifest.json` (18 entries) and `qa_results/` were
     untouched afterward (no `--commit` passed). `uv run pytest`
     (539 passing) and `ruff` both clean; the real CI coverage command
     still passes at 94.52%.
   - **Phase 4 finished 2026-09-19** (Keith's own explicit go-ahead,
     "crack on w/ phase 4 - you can fix up any CI issues if they come
     up"): reorganized the remaining real script entry points into 4 new
     command groups - `mothman dashboard` (`rebuild-results`/`build-data`/
     `embed`/`validate-check-lifecycle`/`validate-requirements`/
     `check-renders`/`snapshot`/`rebuild`, wrapping the dashboard rebuild
     chain), `mothman github` (`sync-tickets`/`sync-acceptances`/
     `sync-leaderboard`), `mothman debug` (`run-dbt`/`run-soda`/
     `run-datacontract`/`run-evidently` - one dataset-parameterized
     command per tool, replacing the 8 retired `run_{dbt,soda,
     datacontract,evidently}_{bdm,cp}.py` scripts' own hardcoded-3-
     sample-run-ids `__main__` blocks with real `--dataset`/`--run-id`
     options - plus `build-warehouses`/`load-warehouse`/`changelog`),
     and `mothman pipeline` (`run`). Rewrote `.github/workflows/
     deploy-pages.yml` and `.github/workflows/ticket-sync.yml` to call
     `mothman` subcommands instead of bare `python3 -m` invocations
     (`.github/workflows/test.yml` needed no changes - it only ever runs
     `uv run pytest`/`npm test`, never one of the retiring scripts
     directly). Retired `run_pipeline.sh`.

     Two real gaps found and fixed along the way, neither in the
     original plan text above:
     1. **The "already named in Phases 1-3" claim for `orchestrate_bdm.py`/
        `orchestrate_cp.py` was wrong.** Only `run_single()` (one run at a
        time) was reused, by `mothman bdm/cp qa` - the same files' own
        `run_pipeline()`/`run_pipeline_cp()` (the full-manifest BATCH
        mode `run_pipeline.sh` step 2 used to call bare: regenerates
        synthetic data, runs all 4 real tools against EVERY run, writes
        both `reports/results_*.json` and fresh `qa_results/` history)
        had no mothman command at all until this phase. New `cli/
        pipeline.py`'s `mothman pipeline run --dataset {bdm,cp,all}
        [--sequential] [--snapshot]` wraps it - the real, direct
        replacement for `run_pipeline.sh`, not a rename of something
        that already existed.
     2. **`uv sync` was silently never installing the real `mothman`
        console script.** `pyproject.toml` already had a
        `[project.scripts] mothman = "cli.app:main"` entry since Phase
        1, but `uv sync` printed "Skipping installation of entry points
        ... because this project is not packaged" on every run - meaning
        every `uv run mothman ...`/`./mothman ...` invocation anywhere in
        this project's history had actually been silently falling
        through to nothing (`Failed to spawn: mothman`), never verified
        as the real console script working end to end. Fixed by adding a
        minimal `[build-system]` (hatchling) + `[tool.hatch.build.
        targets.wheel] packages = ["cli"]` to `pyproject.toml` - `uv
        sync` now really builds and installs `mothman` as a package, and
        `uv run mothman ...`/`./mothman ...` (the wrapper simplified to
        delegate to the real entry point rather than a separate `python3
        -m cli.app` fallback) were both verified working after the fix.

     Also found, flagged (not acted on, real caution during smoke-
     testing): `mothman debug run-{dbt,soda,datacontract,evidently}`
     write to real, committed `qa_results/` history as a side effect
     (the same `write_qa_result()` call every `evaluate_*()` function
     already makes for a real orchestrate run - pre-existing behaviour
     of those functions, not something this CLI wrapper introduced, but
     a real footgun worth documenting: running one against a run_id that
     already has committed history OVERWRITES that file with the debug
     invocation's own fresh timestamp). Discovered by direct experience -
     smoke-testing these commands against real run_ids left `qa_results/`
     genuinely modified (`git status` showed 4 changed files + 1 new
     directory); reverted with `git checkout --`/`rm -rf` before
     committing anything, and `cli/debug.py`'s own module docstring now
     carries an explicit CAUTION section about it.

     Verification: every new command manually smoke-tested against real
     local data (both BDM and CP sides of all 4 `debug run-*` commands,
     `debug build-warehouses --dataset {bdm,cp}`, `debug load-warehouse`,
     `debug changelog`, and the full `dashboard` group including a real
     `dashboard rebuild-results`/`build-data`/`embed` end-to-end run) -
     all succeeded except `dashboard check-renders`, confirmed via a
     side-by-side run of the bare script to be the same pre-existing
     sandbox-only Playwright chromium-binary-mismatch limitation this
     project's test suite already has (not a regression). `cli/pipeline.
     run`'s full real-manifest batch mode was NOT executed for real in
     this sandbox (the auto-mode classifier declined it as a "shared
     resources" write, reasonably - it writes real, permanent history
     across the whole manifest) - verified instead via code review plus
     the fact that every function it calls was already individually
     smoke-tested working correctly. 35 new tests
     (`tests/test_cli_{dashboard,github,debug,pipeline}.py`, CliRunner +
     monkeypatched real-tool seams, same convention as `tests/
     test_cli_bdm.py`) cover the real dispatch/manifest-lookup logic
     these commands add on top of each wrapped function (BDM's
     `csv_filename` lookup, the Evidently reference-run default, the
     `ctx.invoke()`+`sys.exit()` composition bug's regression coverage
     on `dashboard rebuild`). `uv run pytest -n auto` (574 passing, same
     13 pre-existing unrelated Playwright errors), `ruff check .`, and
     `npm test` (104 passing) all clean. README.md/CLAUDE.md updated
     throughout (setup instructions, layout table, the standing "only
     access point" convention bullet) and swept repo-wide for any
     remaining bare `python3 -m qa_tools.*`/`pipeline.*`/`generator.*`/
     `dashboard.*` invocation reachable from workflows/README/docs/ -
     none found outside historical narrative comments (which stay,
     describing real past events) and this bullet's own "never a bare
     ... invocation" phrasing.
   - **Phase 5 finished 2026-09-19**: the Tier 4 "Population Data"
     command, explicitly exploratory - `mothman population` wraps
     `synthetic_data_generator/generate.py`'s own real argparse CLI
     (`build()`/`build_linkage_answer_key()`/`write_outputs()`/
     `print_cross_agency_demo()`) with the exact same options/defaults
     (`--population`/`--seed`/`--case-workers`/`--dirty`/`--outdir`/
     `--demo-examples`) under the mothman umbrella - a reorg of the
     entry point, not a rewrite of what it does, and NOT wired into the
     real BDM/CP pipeline (still genuinely separate - `plans/data-
     generation.md` #3/#8). Flag-invocable only, not part of the
     interactive TUI's guided flows (those stay Tier 1/2/3) - matches
     its own "exploratory" framing. `cli/common.TIER_4` (`magenta`,
     defined since Phase 1 but unused until now) styles its own status
     output.

     A real, genuine logic bug surfaced live while smoke-testing
     `--dirty amber` for the first time (not something already known -
     found by actually running the real tool, this project's standing
     verification practice): `synthetic_data_generator/generate.py`'s
     `build()` called `dirty_mod.apply_cp_notifications_presets()` with
     its OLD 3-arg signature (`df, severity, seed`) - the real function
     had since grown `clients_df`/`workers_df` params for dangling-FK
     injection (`generator/dirty.py`), which `generator/
     generate_cp_runs.py`'s own call site was updated for at the time,
     but this sibling call site in the unwired `synthetic_data_
     generator/` package never was - exactly the kind of drift `plans/
     data-generation.md` #8 already flagged as a risk of leaving that
     package untested and unwired. Fixed (passes `cp_tables["cp_
     clients"]`/`cp_tables["cp_case_workers"]` through, matching
     `generate_cp_runs.py`'s real calling convention) and covered by a
     real regression test (`tests/test_cli_population.py`, confirmed
     failing against the pre-fix code with the exact real `TypeError`
     first, per CLAUDE.md's standing "whenever an actual bug is found"
     convention - a logic bug, not the environment/wiring exception, so
     no need to ask first). `plans/data-generation.md` #8 updated with a
     pointer - its own "not before [the package is wired into the real
     pipeline]" gate on comprehensive coverage still holds; this was the
     narrower, always-applicable bug-fix rule, not a response to that
     item.

     Verified: `--help`, a real small-population run (`--population 300`,
     confirms `public/`/`internal/` outputs land correctly, including
     the "ground truth - do not distribute" internal linkage answer
     key), a real cross-agency identity demo (`--population 2000
     --demo-examples 1` - confirmed the SAME name/DOB resolves correctly
     across all 3 agencies' own ID schemes for one real synthetic
     person), and both `--dirty amber`/`--dirty red` (the bug above,
     now fixed). 6 new tests, `uv run pytest`/`ruff check .` both clean.
   - **Phase 6 finished 2026-09-19** (Keith's own explicit "feel free to
     keep going to the next phase," plus a real AskUserQuestion round on
     content/count/tab-placement before building - his answers: record
     the Quality Assurance wizard only, one single combined recording
     rather than several shorter ones, Demo tab placed last, after
     Plans): a genuinely new top-level "Demo" tab (`STATE.tier==="demo"`,
     a real `/demo` URL, same not-a-side-panel treatment `plans/
     tooling.md #1 Phase 3.5's own PLANS precedent set) playing back a
     real recording of the actual `mothman` CLI/TUI - not a mockup, a
     real pty session, real keystrokes, real output.

     New `scripts/dev/record_cast.py` (dev-only, same throwaway status
     as the pre-existing `scripts/dev/tui_screenshot.py` it borrows its
     real pty-spawn/read loop from) records a scripted session as a
     timestamped asciinema v2 `.cast` file. A real, non-obvious problem
     solved along the way: `tui_screenshot.py`'s own fixed `key_delay`
     model (send the next key once output goes quiet for N seconds)
     isn't safe for a session that also runs a real, several-seconds-
     long subprocess mid-flow (the actual dbt-core/Soda Core/
     datacontract-cli/Evidently chain a real QA run triggers) - a brief
     real pause mid-subprocess could fire the next key too early. Fixed
     with a STEP-based script instead (`wait:<substring>[:timeout]` /
     `key:<name>`) that blocks on real text actually appearing in the
     decoded terminal output before sending the next key, with a real,
     loud `TimeoutError` (not a silent bad recording) if it never does.
     A second, separate real timing bug found and fixed live: a
     freshly-rendered `prompt_toolkit` prompt probes the real terminal
     for its cursor position (CPR) before it's actually ready for input;
     our synthetic pty never answers that probe, so prompt_toolkit falls
     back after its own real internal timeout - a key sent before that
     resolves can land during the probe window and get silently
     dropped (reproduced live: a scripted Escape right after "What would
     you like to do?" first matched never registered). Fixed by adding
     the same settle pause after every `wait` match, not just after
     every `key` send.

     The real recording itself (`dashboard/demos/qa_wizard.cast`, ~22KB,
     committed as plain text - small enough that HTTP-level gzip
     transfer encoding already covers compression, unlike `dashboard/
     snapshots/*.html.gz`'s app-level decompression dance) walks the
     real Quality Assurance wizard for Birth Registrations/Synthetic
     mode: splash screen, main menu, dataset picker, source picker, run
     picker, the real 4-tool chain actually executing (~24s wall time,
     genuinely captured, not sped up), the real report, declining to
     Promote, back at the main menu - ends there deliberately rather
     than also scripting a demonstrated exit, once the Escape-key CPR
     issue above made that its own separate rabbit hole not worth
     chasing further for a demo recording.

     Playback via `asciinema-player` (npm, Apache-2.0), vendored - not
     CDN-loaded - into new `dashboard/vendor/asciinema-player.{css,
     min.js}`, same self-hosting rationale as the pre-existing `dashboard/
     fonts/*.woff2` (no CDN dependency, works from a plain `file://`
     open, works across government networks). The recording itself is
     embedded into the built HTML as a plain JS string (`const
     DEMO_CAST`, `dashboard/embed_dashboard_data.py`) rather than fetched
     by the player at runtime via its own `url:` source option - a real,
     foreseeable failure avoided deliberately: a `fetch()` of a sibling
     file is blocked by the browser's own CORS policy under a plain
     `file://` open, this dashboard's own supported local/offline
     viewing path. `renderDemo()` creates the player lazily, only once
     the tab is actually opened, and shows a real "not built yet"
     fallback (not a crash) when `DEMO_CAST` is null or the player
     library never loaded.

     A real, separate, previously-latent bug found and fixed live while
     wiring `dashboard/vendor/` into the deployed site:
     `dashboard/snapshot_dashboard.py`'s `prepare_deploy_site()` never
     copied EITHER `dashboard/fonts/` or the new `dashboard/vendor/`
     into the `_site/` tree `.github/workflows/deploy-pages.yml`
     deploys - confirmed live (`uv run mothman dashboard snapshot
     --prepare-site <dir>` produced no `fonts/`/`vendor/` subdirectory
     at all before the fix). `fonts/` had silently had this exact same
     gap since the self-hosted-fonts switch, invisible because a missing
     `.woff2` just falls back to a system font rather than erroring
     loudly - the live published site had quietly been serving unstyled
     system fonts, not the real Public Sans/Source Serif 4/IBM Plex Mono
     choice this dashboard actually specifies, this whole time. Fixed by
     copying both directories straight through into `_site/fonts/`/
     `_site/vendor/`, with real regression tests confirming both the fix
     and the clean-noop case when neither directory exists.

     Verified: a real Playwright screenshot of the Demo tab mid-playback
     (the real splash-screen ASCII moth artwork, the real wizard prompts,
     a real progress bar/timestamp at the bottom - genuine asciinema-
     player chrome, not a static image), `mothman dashboard check-renders`
     passing clean against the real built output (embedded `DEMO_CAST`
     included), and the real CI coverage command still passing at
     94.65%. 9 new tests: `tests-js/demo-tab.test.js` (7 - routing/
     rendering/graceful-degradation under jsdom, where the vendored
     external player script never actually loads by design - see that
     file's own header comment for why, and why real playback is instead
     covered by...), 2 new real Playwright e2e tests
     (`tests/test_dashboard_e2e.py::TestDemoTab` - the one place real
     playback against the real vendored library is verified), plus
     `tests/test_embed_dashboard_data.py`'s DEMO_CAST embed/degrade
     coverage and `tests/test_snapshot_dashboard.py`'s fonts/vendor
     copy-into-`_site/` regression coverage (both bugs found live during
     this build, not pre-existing gaps this phase happened to also
     close). `uv run pytest -n auto` (599 passing, zero errors with
     `PLAYWRIGHT_CHROMIUM_PATH` set - the only pre-existing sandbox-only
     Playwright gap this project's suite has ever had, now confirmed to
     genuinely be sandbox-only, not code), `ruff check .`, and `npm test`
     (111 passing) all clean.

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
      subcommands; retire `run_pipeline.sh`. **Completeness bar, made
      explicit 2026-09-19 (Keith's own ask)**: this phase isn't done at
      "workflows call mothman now" - it's done when there is no bare
      `python3 -m qa_tools.*`/`pipeline.*`/`generator.*`/`dashboard.*`
      invocation left reachable from outside `mothman`'s own
      implementation anywhere in the repo (workflows, README, docs/),
      and a standing rule from then on (see CLAUDE.md's own new
      convention bullet): any script added after this phase ships gets
      a `mothman` subcommand in the same change, never left bare.
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

2. **[todo, 2026-09-19]** **[Testing & dev tooling]** More Python code-
   quality tooling, beyond today's `ruff` (a deliberately lean rule set
   - real bugs only, not style, per `CLAUDE.md`'s own framing). Flagged
   by Keith (voice-dictated batch) with no further specifics given - not
   yet scoped which real tool(s) (candidates worth a real look when this
   gets picked up: `mypy`/`pyright` for real static type checking,
   `radon`/`ruff`'s own complexity rules for cyclomatic-complexity/code-
   smell detection, `bandit` for security-specific static analysis,
   `vulture` for real dead-code detection), what it should actually
   catch that `ruff`/`pytest-cov` don't already, or whether it becomes a
   real CI gate (like `pytest-cov`'s enforced threshold) or stays
   advisory (like `ruff`'s current deliberately-lean scope). Needs a
   real conversation with Keith on what gap he's actually trying to
   close before anything gets scoped further.

3. **[todo, 2026-09-19]** **[Testing & dev tooling]** A real code-
   reviewer agent (or agents) - genuinely distinct from
   `delivery-critic` (`plans/wider.md` #10), which only ever
   checks finished work against one specific requirement's own
   acceptance criteria. This would be a general-purpose code-review
   capability, not tied to a requirement. Flagged by Keith alongside
   item #2 above, with one real detail already given: possibly split
   into more than one agent by language/stack - a Python-focused one and
   a front-end (dashboard JS/HTML/CSS) one, rather than one generalist
   reviewer, mirroring real-world precedent already found for the
   requirements-analysis work (`plans/wider.md` #10's own research
   turned up several real multi-subagent code-review setups doing
   exactly this kind of domain split - `dev.to`'s "How I Split Code
   Review Across Five Claude Code Subagents", `VoltAgent/awesome-claude-
   code-subagents`' own `code-reviewer.md`). Not yet scoped: whether
   this reuses/extends `delivery-architect`'s own code-quality/
   security checks (which already exist but only run pre-build, on a
   drafted requirement, never against already-merged code generally) or
   is a genuinely separate capability; what triggers it (a manual
   invocation, every PR, every push); how many agents and where the
   language boundary actually falls. Needs a real conversation with
   Keith before anything gets built.

4. **[todo, 2026-09-19]** **[Docs & process]** A documentation-quality
   agent - a real, adjacent idea found while digging into
   `cfisch3r/estimate`'s own real agent files for the UX/visual critic
   split (`plans/wider.md` #10). Read the real file
   (`.claude/agents/doc-quality.md`, fetched directly from source) while
   Keith had a subagent doing separate research in parallel - read-only
   (`tools: Read, Grep, Glob, Bash`, `model: inherit`), invoked via a
   `/doc-review` slash command with 3 real scopes (`diff` - default,
   reviews changed docs PLUS docs made stale by non-doc changes in the
   same diff, explicitly "the most important part"; `all` - full
   `docs/` audit; `path` - one file/subtree). 4 real check categories:
   **accuracy** (High - doc contradicts shipped code, e.g. a documented
   command that doesn't match the real `package.json` script) - the
   category with the most obvious real analogue here; **cross-reference
   integrity** (Medium - broken internal links, a docs-index table
   missing a real file or listing one that doesn't exist); **convention
   conformance** (Medium/Low - doc structure/format matching the repo's
   own established patterns, e.g. their ADRs following a fixed
   structure); **internal consistency** (Medium - two docs disagreeing,
   stale dates, a "TBD" left in a doc that reads as finished). Its own
   rubric is explicit that standards come from the repo's own real
   conventions, read fresh each time, not hardcoded into the agent
   itself - the same "check against this project's own real rules"
   principle our own agents already follow.

   **Real, concrete relevance to THIS project, not yet scoped into
   anything**: several of its check categories map onto real, already-
   -felt pain here - a `plans/*.md` item or a `CLAUDE.md` bullet going
   stale after the code it describes changes (the exact kind of drift
   `tests/test_component_taxonomy_consistency.py` just built a narrow,
   one-off CI guard against, 2026-09-19, `plans/wider.md` #10);
   cross-reference integrity between `requirements.yaml`'s own
   `dependencies` field and real ids (already CI-enforced by
   `validate_requirements.py`, so partial coverage already exists);
   whether a `plans/*.md` item's own real file/line references
   (`dashboard/qa-reporting-dashboard.template.html:3225`-style
   citations, used throughout this project's own planning entries) still
   resolve after a refactor - genuinely unchecked today. Not yet scoped
   as a real requirement - a real conversation with Keith on whether
   this is worth building here, and if so how narrow a first version
   should be, comes before anything gets drafted.

5. **[done, 2026-09-19]** **[Docs & process]** **[Testing & dev tooling]**
   2 real Claude Skills installed (`.claude/skills/`) - a genuinely
   different mechanism from the `requirements-*` subagents above:
   skills are progressive-disclosure capability packages that activate
   contextually (or as a slash command), not separate-context-window
   delegates. Found via a real Snyk article Keith found himself ("Top 8
   Claude Skills for UI/UX Engineers") and supplied as a PDF once the
   real site turned out to be blocked (`snyk.io`, flagged in
   `CLAUDE.md`). Keith picked 4 of the article's 8 real skills to bring
   in; 2 are installed, 2 are still pending (see below):
   - **`frontend-design`** (Anthropic's own, `anthropics/skills`,
     Apache-2.0) - pushes Claude away from generic "AI slop" aesthetics
     (banned fonts/palettes, a two-pass plan-then-build process,
     concrete anti-pattern examples). Vendored verbatim, byte-identical
     to the real upstream `SKILL.md`/`LICENSE.txt` (confirmed via a
     real `diff`, not just copied by hand) - no bundled scripts, purely
     markdown guidance, lowest real risk of the 4.
   - **`web-design-guidelines`** (adapted from Vercel's own
     `vercel-labs/agent-skills`, MIT) - reviews existing UI code against
     a real, comprehensive 17-section ruleset (accessibility, focus
     states, forms, performance, dark mode, i18n, anti-patterns, etc.),
     output in a terse `file:line` format. The real upstream skill does
     a live `WebFetch` of its ruleset before every review; Keith's own
     explicit call was to vendor a reproducible offline copy instead
     (same rationale as `dashboard/vendor/`'s own vendored assets - no
     live external dependency, works offline, works on a network that
     can't reach every third-party domain). The real ruleset (`vercel-
     labs/web-interface-guidelines`'s own `command.md`, MIT) is
     vendored verbatim at `.claude/skills/web-design-guidelines/
     reference/web-interface-guidelines.md` (confirmed byte-identical
     to upstream via a real `diff` after an earlier manual-retype
     attempt was caught corrupting curly quotes into straight ones -
     redone as an exact file copy instead); only the SKILL.md's own
     retrieval instructions were changed to read that local file
     instead of fetching live. No automated re-sync process exists yet
     - a real, deliberate gap, noted in the vendored file's own header
     comment.

   **Real security review done before installing, not just installed on
   the article's word** (both of these are pure markdown/text content,
   no bundled executable scripts - lowest-risk of the 4 skills Keith
   picked): read each real file directly from its real source
   (`raw.githubusercontent.com`, not a rendered/summarized page) and
   confirmed neither contains anything beyond design/review guidance
   text. Both source repos' real licenses were checked before vendoring
   (Apache-2.0 for `anthropics/skills`; MIT for both
   `vercel-labs/agent-skills` and `vercel-labs/web-interface-guidelines`
   - the second confirmed via that repo's own `README.md` "## License"
   section, since no separate `LICENSE` file exists there).

   **Declined, same day**: `UI/UX Pro Max`
   (`nextlevelbuilder/ui-ux-pro-max-skill`) and `AccessLint`
   (`accesslint/claude-marketplace` + `@accesslint/mcp`) - Keith's own
   explicit call, "don't worry about" either. Both bundle/run real
   executable code (a Python search CLI; an MCP server), unlike the 2
   installed above, and got a real security review in progress (all 5
   of UI/UX Pro Max's real Python scripts read directly from source and
   confirmed clean - stdlib-only, no network/subprocess/eval/exec, safe
   path handling; `@accesslint/mcp`'s real npm package downloaded and
   partly inspected) before Keith first asked to pause it, then decided
   not to pursue either at all. Not installed; everything downloaded
   during that partial review was deleted, confirmed via a clean
   `git status` (nothing had actually been written into the repo yet).
   Not parked for later either - a real decision, not just deferred.

6. **[todo, 2026-09-19]** **[Testing & dev tooling]** A real, dedicated
   MCP server wrapping `mothman` (via `uv run`), so the requirements-
   analysis agents that currently use `Bash` only to run `uv run
   mothman dashboard rebuild` (`delivery-critic`/
   `delivery-dashboard-ux-critic`/`delivery-dashboard-visual-critic`) could get a
   single narrow, purpose-built tool instead of open shell access -
   real, buildable (a small Python MCP server, `mcp.server.fastmcp` or
   the official `modelcontextprotocol` SDK, matching this project's own
   Python-first convention rather than introducing Node for something
   we'd write ourselves), and would let `Bash` be dropped entirely from
   those 3 agents' own tool grants - a further least-privilege step in
   the same spirit as the Playwright MCP split. Keith's own call: park
   it as an idea rather than build now, deliberately sequenced behind
   confirming the existing Playwright MCP setup actually works end to
   end first (`plans/wider.md` #10's own still-open verification gap) -
   a second custom MCP server built on the same currently-unconfirmed
   foundation would carry the identical risk. Not yet scoped beyond the
   one real, already-known need (`dashboard rebuild`) - whether other
   `mothman` subcommands would eventually get their own tools too is a
   real question for whenever this gets picked up.

7. **[todo, 2026-09-19]** **[Testing & dev tooling]** Bring real Google
   Lighthouse findings into one of the requirements-analysis agents'
   own review pass - Keith's own idea, prompted directly by the local-
   HTTPS-serving work above ("this gives me a good idea"). Confirmed
   real and working, not just plausible, before parking it: the real
   `lighthouse` npm package (v13.5.0) ran end to end against the real
   dashboard, served locally over HTTPS the same way
   `scripts/dev/serve_dashboard_https.py` already does, pointed at this
   sandbox's own installed Chromium via the real `CHROME_PATH` env var
   (no separate browser download needed - matches the same real-binary-
   reuse pattern this project already uses for Playwright). Produced a
   real, structured JSON report with real, specific findings, not
   placeholder output - e.g. a real `aria-hidden-focus` violation
   (`[aria-hidden="true"]` elements containing focusable descendants)
   and a real `color-contrast` failure, alongside category scores
   (accessibility 0.90, best-practices 0.96, performance 0.25 - the
   performance number is very likely an artefact of Lighthouse's
   default throttled-CPU simulation against this dashboard's own
   deliberately-different single-file-with-everything-embedded
   architecture (7.9MB of inline data) rather than a real reflection of
   how the actual published GitHub Pages site performs for a real
   visitor - not yet confirmed either way, a real thing to check before
   trusting that number for anything).

   **Real, concrete relevance**: Lighthouse's accessibility category is
   genuine, real prior art for a gap this project has already
   identified and left open - `delivery-dashboard-ux`/`delivery-dashboard-ux-
   critic`/`delivery-dashboard-visual-critic` all explicitly declare
   accessibility out of scope today, so nothing currently checks it at
   all. Not yet scoped: which agent this belongs to (a new dedicated
   accessibility-focused pass, or folded into
   `delivery-dashboard-visual-critic`'s existing remit), whether to run the
   full Lighthouse suite (performance/best-practices/SEO too, several
   of which may not even apply meaningfully to a single-file static
   dashboard with no build pipeline, no server-side rendering, no SPA
   routing) or scope it to just `accessibility`, and how findings get
   reported (raw Lighthouse JSON is real but verbose - needs real
   shaping into the same evidence-based finding format the other
   critics already use). A real conversation with Keith before
   building, same as every other agent-capability decision this
   session.

8. **[todo, 2026-09-19]** **[Testing & dev tooling]** Investigate
   whether Snyk has something real worth bringing into the
   requirements-analysis agents - flagged by Keith, real name garbled
   in voice dictation ("the SNCC Snyk security project" - not a real,
   recognizable Snyk product name as transcribed). Real candidates,
   given what's already come up naturally in this project's own recent
   research (the Snyk UI/UX-skills article, `plans/tooling.md` #5's own
   write-up): the real "Snyk MCP integration" the article itself
   mentioned in passing ("if you are already using Snyk Code or the
   Snyk MCP integration, you can scan skill scripts the same way you
   scan any code"); Snyk Code itself (static analysis); the real
   ToxicSkills research project the same article cited (prompt-
   injection/malicious-payload scanning for Claude Skills specifically -
   directly relevant given this project has now installed 2 real,
   external, third-party skills, `plans/tooling.md` #5). Not yet
   investigated at all - which of these (if any) Keith actually meant
   needs confirming with him before real research time goes into any
   one of them, not guessed from a garbled transcription.

9. **[done, 2026-09-19]** **[Testing & dev tooling]** Real, verified
   documentation/behaviour mismatch in `cli/common.py`: `select()`'s own
   docstring (and `path_prompt()`'s) claims "Returns None if the
   operator picked Back or hit Ctrl-C/Esc" - but a real, live test via
   the new `scripts/dev/tui_drive.py` (built the same day for
   `delivery-cli-ux-critic`, `plans/wider.md` #10) found `Escape`
   does NOT actually back out of a real `questionary.select()` prompt
   (confirmed twice, including with a full extra second to rule out a
   timing artifact) - only Ctrl-C genuinely triggers the "go back a
   step" behaviour today. A real, live proof the new CLI/TUI-driving
   mechanism catches genuine gaps, found incidentally while verifying it
   end to end, not chased down deliberately. Not fixed here - out of
   scope for that verification pass. Likely either a real `questionary`/
   `prompt_toolkit` default-binding gap (Escape may need an explicit
   keybinding this project's own `select()`/`path_prompt()` don't add)
   or a stale docstring claim from before some real dependency version
   changed default behaviour - root cause not yet investigated. Real fix
   needed either way: either make Escape actually work (matching the
   documented claim) or correct the docstring to match reality (never
   both left mismatched) - whichever ends up correct, add a real
   regression test first per this project's own standing "whenever an
   actual bug is found" convention (`CLAUDE.md`), confirmed failing
   against today's actual behaviour before any fix lands.

   **Root cause found and fixed, same evening, Keith's own explicit
   go-ahead**: grepped the actual installed `questionary` package's
   source (`.venv/lib/.../questionary/prompts/*.py`) - `select()` binds
   only `Keys.ControlC`/`Keys.ControlQ` to cancel (raising
   `KeyboardInterrupt`, which `.ask()` turns into `None`); a repo-wide
   grep for `Keys.Escape` across every real prompt type questionary
   ships (`select`, `path`, `text`, `checkbox`, ...) found zero matches
   - this questionary version never binds Escape to anything, in any
   prompt type, not just `select()`. Chose "correct the docstring" over
   "make Escape actually work": patching a third-party library's own
   internal key bindings post-construction would be fragile (version-
   coupled, no supported extension point for this in questionary's
   public API) for a purely cosmetic UX nicety nobody had actually
   asked for - the honest, low-risk fix was making `cli/common.py`'s
   own docstrings (`select()`/`path_prompt()`) say what's actually true
   (Ctrl-C only) rather than adding new library-patching surface area.
   Also found and fixed the same real inaccuracy baked into
   `tests/test_cli_common.py`'s own test names
   (`test_select_returns_none_on_ctrl_c_or_esc`/`test_path_prompt_
   returns_none_on_ctrl_c_or_esc`) - both tests only ever mocked
   `questionary.select`/`.path` to return `None` directly (real Ctrl-C
   behaviour), never actually exercising real questionary key-binding
   behaviour at all, so their own names asserted something neither test
   had ever verified - exactly the kind of gap that let the docstring
   claim go unnoticed. Renamed both to describe what they actually test
   (`common.select()`/`common.path_prompt()`'s own `None`-pass-through
   logic), with a real docstring explaining the live pty-driven
   verification (via `tui_drive.py`) happened manually, not as an
   automated test - deliberately not duplicated as a real-pty unit test,
   since that would either slow down an otherwise-fully-mocked test
   file or couple it to questionary's own internal implementation. All
   13 `tests/test_cli_common.py` tests still pass; `ruff` clean.

10. **[done, 2026-09-19]** **[Testing & dev tooling]** A real, pre-existing
    test-isolation gap between `tests/test_embed_dashboard_data.py` and
    `tests/test_dashboard_e2e.py` under `pytest-xdist`. Found
    incidentally while verifying `plans/qa-pipeline.md` item 74's fix -
    a full `uv run pytest -n auto` came back with 4 failures in
    `test_embed_dashboard_data.py` that passed cleanly the moment the
    same file was run on its own, and that an EARLIER `-n auto` run of
    the very same code had passed. So: a real race, not a deterministic
    break, and order-dependent on how xdist happens to distribute tests
    across workers that run.

    **Confirmed pre-existing, not caused by item 74's change** - checked
    properly rather than assumed, by `git stash`-ing every change and
    re-running the same two files together under `-n auto` on the clean
    tree: the untouched code produced the same class of collision (9
    errors) as the changed tree did (11). The difference in count is
    itself just the race landing differently, not a signal about either
    tree.

    Root cause not yet confirmed, but the obvious candidate: both
    modules drive `dashboard/embed_dashboard_data.py`'s own `embed()`,
    which reads and writes real, shared, repo-relative paths under
    `reports/` (`birth_registrations_dashboard.json`, etc.). Each test
    monkeypatches the specific module attributes it cares about
    (`QA_COMMENTS_JSON`/`DASHBOARD_HTML`/...), but monkeypatching is
    per-process, so two xdist WORKERS running `embed()` concurrently
    still contend for the same real files on disk - the same class of
    problem `plans/running-thoughts.md` #12 already found and fixed for
    dbt's shared `target/` directory, just in a different shared
    resource that the dbt fix didn't cover.

    **Fixed 2026-09-19** (Keith's own go-ahead, same message that made
    `-n auto` the default - the two are the same piece of work, since a
    flaky default is worse than a slow one). The diagnosis above was
    right about the shared `reports/` paths but incomplete: there were
    **two** independent races, and fixing either alone would have left
    the suite flaky.

    1. **A cross-module read/write race.**
       `test_dashboard_e2e.py`'s session-scoped `built_dashboard_html`
       shells out to the real build chain, rewriting the real
       `reports/birth_registrations_dashboard.json` (6.5MB) and its CP
       sibling. `test_embed_dashboard_data.py` monkeypatched every other
       real path `embed()` touches - `DASHBOARD_HTML`,
       `OPEN_TICKETS_JSON`, `TICKET_RESOLUTIONS_JSON`,
       `CHANGELOG_SOURCES` - but never `TARGETS`, so it read those two
       files live, and on a different worker could read one mid-rewrite
       and get truncated JSON. Fixed with an autouse
       `_isolate_embed_data_targets` fixture pointing `TARGETS` at tiny
       local stubs. This is the honest fix rather than a workaround:
       nothing in that module asserts anything about those files'
       CONTENTS (they're unit tests of `embed()`'s own wiring), and
       `embed()` only `json.load`s each target and substitutes it into a
       const. Real side benefit, not the goal: that module went from
       6.8s to 2.9s by not reading 7MB of JSON per test.
    2. **A worker-vs-worker clobber, not in the original diagnosis.**
       Under xdist's default `--dist load`, tests from one file are
       spread across workers, so `built_dashboard_html` - session-scoped,
       meaning once *per worker* - ran the whole build chain several
       times concurrently, each writing the same real files. Fixed with
       `--dist loadfile` (every test in a file stays on one worker),
       which is why that flag is load-bearing in `pyproject.toml`'s
       `addopts` rather than a tuning knob.

    Verified rather than assumed: the two modules run together 3/3 clean
    where they had failed reliably before, and the full suite is **649
    passed in 78s** under the new default, against 220s serial - a real
    2.8x. (Not the ~4x a naive `-n auto` would suggest: `--dist
    loadfile` keeps the big e2e module on one worker, which is the
    price of correctness here.)

    A regression test was deliberately NOT written for the race itself -
    this is the environment/wiring class `CLAUDE.md`'s bug-test
    convention carves out, and both fixes REMOVE the shared mechanism
    rather than guard it, so a test would document a hack that no longer
    exists. The autouse fixture is itself the standing guarantee.

11. **[todo, 2026-09-19]** **[Testing & dev tooling]** A real
    `.claude/settings.json` with a SessionStart hook, so a fresh session
    doesn't start from a half-configured sandbox. Keith's own ask,
    2026-09-19, after watching this session rediscover the same three
    gaps by hitting test failures rather than by reading setup docs.

    **The concrete problem.** This project needs three things that
    aren't (and shouldn't be) in git, because they're all correctly
    gitignored build artifacts:
    - `dbt_project/dbt_packages/` - `dbt_utils`, which several real dbt
      checks' macros come from. Missing it fails 8 real tests.
      (`uv run dbt deps --project-dir dbt_project --profiles-dir
      qa_tools/dbt_profiles`)
    - `node_modules/` - Vitest won't start at all without it.
      (`npm ci`)
    - Playwright's Chromium - 16 e2e errors without it.
      (`uv run playwright install chromium`, or this sandbox's own
      `PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium` escape hatch,
      since the pre-installed build here lags what the pinned package
      expects)

    **What's already right, and what isn't.** `.github/workflows/
    test.yml` runs all three as explicit steps, so CI is genuinely fine
    - this is not a broken-pipeline problem. What has no equivalent is
    the INTERACTIVE session: a fresh cloud container clones the repo and
    runs no setup at all, and there is no `.claude/settings.json` in
    this repo today (only `.claude/agents/` and `.claude/skills/`). So
    every new session re-derives the same three failures from scratch.

    Not scoped yet, and worth a real think rather than just writing the
    obvious hook: whether all three belong in one SessionStart hook or
    whether the Playwright one should stay opt-in (it's a real download,
    and plenty of sessions never touch the e2e suite); whether the hook
    should be idempotent-and-silent or actually report what it did;
    whether `PLAYWRIGHT_CHROMIUM_PATH` belongs in `env` rather than a
    hook, given `dashboard/check_dashboard_renders.py` already
    auto-detects the symlink (2026-09-19) so the gap may be narrower
    than it looks; and whether any of this wants to be shared with
    `README.md`'s own setup instructions rather than duplicated. There's
    a real `session-start-hook` skill available for building this.

    Related but genuinely separate, worth not conflating: `CLAUDE.md`
    already documents the `dbt deps` step in prose. The gap this closes
    is automation, not documentation - and the standing process fix for
    the documentation half (read and run setup BEFORE running the
    suite, rather than diagnosing failures backwards) landed as its own
    `CLAUDE.md` convention bullet the same day, at Keith's explicit ask.

12. **[todo, 2026-09-19]** **[Testing & dev tooling]**
    **Priority: HIGH - to FIX, not just to record (2026-09-19, Keith's own
    explicit ask, in as many words: "this is a priority issue to fix,
    so make that known").** Flagged at the top of this item rather than
    buried at the end because it changes what "done" means here: the
    closing paragraph below originally left "how much is worth acting
    on versus just recording" as an open question, and Keith has
    answered it - the output of this pass is real changes to the
    codebase, not a findings list. See the rubric below before touching
    anything though: "fix" still means fix the right category, and
    collapsing (b) or (c) would make things worse, not better.

    A real DRY /
    duplication pass across the whole codebase, to find the rest of what
    `plans/qa-pipeline.md` item 74 turned up by accident. Keith's own
    ask, immediately after that: the status logic existed in FOUR places
    (the dashboard's JS, two Python modules, and a dead rollup in
    `build_dashboard_data.py`), nobody knew, and the drift between two
    of them shipped a real `TypeError` to CI and a false GREEN to the
    rendered page. That was found by chasing one bug, not by looking -
    so the question is what else is sitting there unfound.

    **One real candidate already found and waiting, 2026-09-20:** the
    `label` field (`pipeline/dashboard_check_labels.py`'s shared
    cross-tool vocabulary - "Duplicate rate", "Null rate", "Invalid
    values") becomes **dead data** once `plans/qa-pipeline.md` item 25's
    REQ-DASH-026 lands. Its only consumer is
    `display_name(check_name, engine_short, label)` in the two dashboard
    builders - i.e. the card headline the plain-English sentence
    replaces. Nothing else reads it, confirmed by grep. It is still SET
    by all 8 `run_*.py` modules (dbt/Soda via lookup dicts, which are
    fine; the two datacontract ones derive it from description text and
    die as part of REQ-QAC-023). Removing the field itself is a real
    cleanup across 8 modules plus both builders - deliberately kept out
    of item 25's scope rather than smuggled in, and logged here instead.
    Worth checking when this pass runs whether the cross-tool
    equivalence signal it provided should be preserved some other way or
    genuinely dropped: 85 of 105 (column, label) groups are checked by
    2+ engines, so it was doing real work right up until the sentence
    took over.

**A second real candidate, found 2026-09-20 while scoping check
    explanations.** `pipeline/build_dashboard_data.py`'s `COLUMN_META`
    hand-maintains a prose description per column, duplicating the ODCS
    contract's own property descriptions. They have already drifted -
    the contract says *"BDM's unique registration identifier. Primary
    key of the feed."*, `COLUMN_META` says *"BDM's unique registration
    identifier - primary key of the feed."* Identical content, two
    hand-maintained copies, and only punctuation separating them so far.
    Sorts as (a) an accidental copy under this item's own rubric, since
    the contract is the obvious single source and the dashboard builder
    is already reading that file for other reasons - but check whether
    the contract's own descriptions are complete enough to replace
    `COLUMN_META` wholesale before assuming it collapses cleanly.

        **The rubric matters more than the findings, and is the part to
    settle first.** Today's incident is NOT an argument that duplication
    is bad: `pipeline/cadence.py` duplicates real logic into the
    dashboard's own JS deliberately and correctly (a static site has no
    backend, so the browser must re-roll cadence for any as-of date a
    viewer picks), and it has never drifted - because its own docstring
    commits both sides to being tested against the same real configs and
    dates. The status mirror had the same unavoidable split and no such
    cross-check, and that is the whole difference. So the pass should
    sort what it finds into: **(a) accidental copies** that should
    collapse to one implementation; **(b) genuinely unavoidable
    duplication** (a real client/server or language boundary) that needs
    a shared-fixture cross-check rather than removal; and **(c)
    deliberate, justified separation** that should be left alone -
    `plans/qa-pipeline.md` #84 already established, by real diffing,
    that the per-dataset BDM/CP split is genuinely different
    check-to-dashboard logic rather than copy-paste - a finding a
    mechanical duplication scan cannot reproduce and would contradict.
    Re-measure it rather than re-litigate it (see the note on #84 just
    below: it was measured at 2 datasets, and more has been built since).

    **Read `plans/qa-pipeline.md` #84 before starting - it is this exact
    pass, already done once, narrower** (Keith's own pointer,
    2026-09-19). In 2026-09-14 it asked the same question of the BDM/CP
    tool-runner file pairs, and it is the closest thing this project has
    to a proven method for the work:
    - **It diffed the pairs in full rather than reasoning about them.**
      That is what produced a defensible split (~30-40 shared lines per
      pair vs the rest genuinely dataset-specific) instead of a guess.
    - **The diff found MORE shared code than predicted** - two further
      bits (datacontract-cli's "local_test" server + `DataContract
      .test()` construction, and Evidently's PSI-via-DataDriftPreset
      computation) turned out byte-identical "once written side by
      side," in that item's own words, and were "found while doing the
      extraction, not predicted in advance." A strong argument that this
      pass has to actually put candidates next to each other rather
      than eyeball them from a filename similarity scan.
    - **It extracted ONLY the confirmed-shared part** and deliberately
      left the rest, landing on "not a false-DRY situation, but not
      nothing either." That is exactly the (a)/(b)/(c) judgement this
      item's rubric above is asking for, arrived at independently two
      months earlier - so the rubric is not a new invention to be
      trusted on faith, it is a restatement of what already worked here.
    - **Its own unresolved residue is still open and belongs to this
      pass**: "every new dataset currently means copy-pasting a whole
      file and manually picking apart which parts to keep." That cost
      was acceptable at 2 datasets and is the thing
      `plans/publishing-and-history.md` #6 later reopened at the
      project's stated ~30-dataset target. Worth treating #84's finding
      as correct FOR ITS TIME rather than as a permanent ruling - it
      measured 2 datasets, and the seeds below are what 2 more years of
      building on top of it produced.

    **Real seeds found in a 10-minute reconnaissance while parking this**
    - concrete starting points, not a guess that duplication exists:
    - **`_run_gh()` is byte-identical in THREE modules in the same
      directory** - `qa_tools/common/ticket_sync.py`,
      `acceptance_sync.py`, `leaderboard.py` each carry a private
      copy of the same 2-line `subprocess.run(["gh", *args], ...)`
      helper. Category (a), and about as clear-cut as it gets.
    - **`cli/bdm.py` and `cli/cp.py` share 19 identically-named
      functions across 1,067 lines** (`run_check`, `report_table`,
      `picker_choices`, `load_manifest`, `default_reference`,
      `_offer_promote`, ...). Needs real judgement rather than a
      mechanical merge - CP genuinely differs (6 tables vs 1 CSV, no
      row-count-growth concept) - so this is likely (b) or (c) in
      places and (a) in others.
    - **9 mirrored filenames across `qa_tools/bdm/` and `qa_tools/cp/`**
      (`build_results_from_history.py`, `dataset_stats.py`,
      `evidently_check_lifecycle.py`, ...). This overlaps
      `plans/publishing-and-history.md` #6, which owns the per-dataset
      file ARCHITECTURE question - deliberately not duplicated here: #6
      is "is one file per dataset per concern the right shape at ~30
      datasets", this item is the narrower "is the CONTENT of these
      pairs actually the same code". **#6 stopped being parked on
      2026-09-19** - Keith named the copy-paste-a-file cost as "not
      tolerable in the short term", so it is now `todo` and HIGH
      priority alongside this item. That makes the earlier "resolve #6
      first, or at least together" a real sequencing call rather than a
      politeness: #6 is the one with a concrete felt cost attached, and
      this sweep would otherwise keep rediscovering symptoms of it.
      Don't let this item quietly re-answer it.
    - **Known JS<->Python mirrors to audit as a class** (each needs a
      (b)-style cross-check, not removal): `cadence.py`/
      `cycleStartDate()` (has one, informally), `dataset_status.py`/
      `checkStatus()` (now has one, `tests/test_dashboard_e2e.py`'s own
      `TestStatusMatchesEachToolsOwnVerdict`), and
      `tests/test_dashboard_e2e.py`'s `_state_to_path()`/`stateToPath()`
      (test-only, documented as hand-synced - probably fine, worth
      confirming).
    - **Dead code specifically, since ruff demonstrably misses it**: the
      `worst` rollup sat unused in `build_dashboard_data.py` and `F841`
      never fired, because the variable is read inside its own
      accumulating loop. `plans/tooling.md` #2 already names `vulture`
      as a real candidate for exactly this - that item and this one
      should probably be picked up together, since a real dead-code
      detector is a mechanical way to find one whole category here.

    **Resolved by the priority flag above**: how much of this is worth
    acting on versus just recording. The answer is act - this is a fix,
    and a findings list alone doesn't close it.

    Still not scoped: whether the pass itself is a one-off manual sweep,
    a `delivery-*`-style agent doing it (cf. #3's code-reviewer agent
    idea), or a real tool in CI - and in what order the seeds above get
    worked, since they differ a lot in risk (`_run_gh` is a safe,
    obvious collapse; `cli/bdm.py`/`cli/cp.py` needs real judgement
    about what genuinely differs). Worth a short scoping round with
    Keith on approach and order before starting, not a full design
    conversation - the appetite question that would normally gate it is
    already answered.

13. **[done, 2026-09-19]** **[Testing & dev tooling]** The QA wizard
    goes completely silent for ~13.5 seconds while the real check chain
    runs. `cli/bdm.py`'s `_run_qa_interactive_synthetic()` prints one
    `"Running the real dbt-core/Soda Core/datacontract-cli/Evidently
    chain for <run_id>..."` line and then calls `run_check()`, which
    emits nothing until it's done. A real operator gets a static screen
    with no indication the tool is alive, working, or hung. `cli/cp.py`
    has the same shape.

    Found 2026-09-19 while re-recording the demo (`plans/dashboard.md`
    #13) - the recording made it impossible to miss, because that
    stretch shows up as a gap with **zero terminal events at all**, so
    the Demo tab freezes on one line for 13.5s of its ~48s runtime.
    Worth being precise that this is a real CLI gap, not a recording
    artifact: the recording is faithful, and what it faithfully shows is
    a CLI that says nothing for 14 seconds.

    This was actually designed and then not built. `plans/tooling.md` #1's
    own TUI research notes say "the planned spinner-under-10s /
    step-progress-bar-otherwise split for `rich.progress.Progress`
    already matches real progress-indicator UX guidance" - so the
    intended behaviour is on record; it just never made it into the
    synthetic-source path.

    Not fixed with the demo work, deliberately: that was scoped to
    recording-side pacing, and this is a change to the real shipped CLI
    that deserves its own decision. Real options when picked up, in
    rough order of effort: a `rich` `console.status()` spinner around the
    whole call (smallest, and honest - it genuinely is one opaque
    operation from the CLI's point of view); or a real per-tool
    step indicator (dbt -> Soda -> datacontract-cli -> Evidently), which
    is more informative and matches the "step progress bar over 10s" half
    of the design above, but needs `run_check()` to report progress back
    rather than returning once at the end. Either would also fix the
    demo's dead patch for free, without faking anything - the fix is
    that the tool starts saying something, not that the recording hides
    the silence.

    **Built the same evening, Keith's own ask on seeing the demo**: "it
    says 20 seconds of like nothing and waiting and there's no progress
    indicator. Is it possible to show a progress bar while that's
    happening?" It is, and genuinely rather than decoratively - the
    chain has real, discrete steps, so a bar over them measures actual
    position rather than animating to look busy.

    - **`RUN_STEPS`** on both orchestrators (identical, cross-checked by
      a test) is one source of truth for the step labels AND the count:
      the 4 real tools plus the `dataset_stats` computation. A bar sized
      from it can't drift from what actually runs.
    - **An optional `on_step` callback** threaded through
      `_run_one()` -> `run_single()` -> each `cli/` `run_check*`. Optional
      by design and defaulting to `None`, so the full-manifest batch
      loop, the AWS Lambda handlers and every existing test behave
      exactly as before - only the interactive CLI, where a human is
      actually watching, opts in.
    - **`cli/common.chain_progress()`** renders it: a spinner, the
      current tool's name, a real bar, the step count and elapsed time,
      `transient=True` so the report lands on a clean screen. It falls
      back to a plain one-line print when stdout isn't a TTY - a
      redirected log or CI runner gets no cursor-control spam.

    Honest caveat, documented in the code rather than smoothed over: the
    steps are very unevenly sized (dbt-core ~3.5s and datacontract-cli
    ~5.5s dominate; Soda Core and Evidently are a fraction of a second -
    matching `plans/performance.md`'s own measurements), so the bar
    advances in real but lumpy jumps. The spinner and elapsed-time
    columns are what carry continuity across the two long steps, which
    is precisely where a bare bar would look stalled.

    Verified by re-recording the demo against the real CLI, which is the
    same artifact that exposed the problem: the chain window went from
    **~0 terminal events and a 13.5s frozen gap** to **133 events with a
    largest gap of 1.5s**, with each tool visibly named as it runs
    (dbt-core -> Soda Core -> datacontract-cli -> Evidently). Real
    rendered frames confirmed rather than assumed, e.g. at t=35s:
    `⠹ Running datacontract-cli ━━━━━━━━━━━╺━━━━━━━━━━ 2/5 0:00:06`.
    5 new tests (`tests/test_chain_progress.py`) cover the plumbing -
    the two orchestrators agreeing on the steps, `_announce` being a
    genuine no-op without a callback, ordered reporting, and the non-TTY
    fallback. One pre-existing test double needed widening
    (`tests/test_cli_cp.py`'s `_fake_run_single` mirrored the real
    signature exactly and rejected the new optional kwarg) - fixed with
    `**kwargs` so it stops re-breaking on unrelated signature growth.

    **Completed properly after Keith caught that the first pass was
    partial.** He asked what "wired it into the BDM synthetic path"
    actually meant and whether CP needed it too - a question worth
    checking rather than answering from memory, and the audit found the
    first pass had covered only 5 of 13 real call sites. CP's Synthetic
    and Local-files paths did have it; **eight others did not**: both S3
    modes, CP's single-table mode (2 sites), and every flag-invocable
    `mothman <ds> qa` form (5 sites). That last group matters most - a
    human typing `mothman bdm qa --run-id X` waits the same ~13.5s, and
    it's the route someone uses repeatedly once they know the tool.
    Flag-mode parity is also `plans/tooling.md` #1's own stated design
    rule ("just put everything in the TUI" - no CLI-only/TUI-only
    split), so leaving it out would have been a real inconsistency, not
    just a gap. `on_step` now threads through the S3 wrappers too (they
    delegate down to the local-file/local-folder bodies), and all 13
    sites are covered.

    Two new tests specifically guard the thing that went wrong, since
    "I wired some of them" is not a mistake a functional test would
    catch: one asserts **no** `results, tmp_dir = run_check*(...)` call
    site anywhere in `cli/` sits outside a `chain_progress()` block, and
    one asserts flag mode and interactive mode both show it. Structural
    rather than driving 13 real chain runs, which would cost minutes -
    and deliberately blunt, so a future call site that genuinely
    shouldn't show a bar has to be an explicit decision rather than an
    omission. Verified by removing one wrapper and confirming the guard
    fails naming the exact `file:line`.

14. **[done, 2026-09-19]** **[Testing & dev tooling]** Confirming a
    Promote ended the flow the same way declining it did. Keith's own
    words, watching the demo: "after the user confirms promotion of
    results, they should get a success message rather than being bumped
    straight back to the menu."

    Worth separating two things that looked like one problem, because
    the first turned out not to be one. **A message did already exist**:
    `cli/bdm.py`/`cli/cp.py`'s `_offer_promote()` printed a green
    `Promoted -> <path>` plus a dim "commit and push it yourself to
    publish" follow-up. Part of why it read as absent in the recorded
    demo is `plans/dashboard.md` #13's CPR bug, fixed the same evening:
    every prompt re-rendered from row 0 and erased the lines above it,
    so in the demo that message was genuinely wiped the instant the
    main menu came back. But the underlying complaint stands on its own
    even with the recording fixed: two ordinary printed lines
    immediately followed by a full menu redraw makes the single most
    consequential action in the tool - writing into the permanent,
    committed `qa_results/` history - end exactly like a no-op.

    Built: `cli/common.report_promoted(dst)`, shared by both datasets'
    interactive flows.
    - **A bordered `rich` panel** rather than loose lines, so the
      completion has a visible boundary instead of dissolving into
      whatever prints next.
    - **A real, checkable outcome**: how many result files were written
      and where, counted from the destination directory rather than
      asserted. Someone who wants to verify the claim has the number
      and the path to check it against.
    - **An explicit acknowledgement**
      (`questionary.press_any_key_to_continue`) before the menu returns - the "rather
      than being bumped straight back" half of the ask. Guarded on both
      `stdin` and `stdout` being real terminals, so a piped or scripted
      run can never hang on a keypress that will never come.
    - **The flag-based `--commit` paths deliberately keep their
      one-liner.** `_finish_flag_mode()` in both modules is the
      scriptable form, where a panel is noise and a blocking keypress is
      a hang. The parity rule in #1 is about capability, not about
      making a script sit through a human's affordances.

    Three tests in `tests/test_cli_common.py` cover the file count and
    destination, the keypress firing in a real terminal, and - the one
    that actually guards a hang - that it never prompts when stdout
    isn't a terminal.

    Not shown in the committed demo recording, which answers **no** at
    the Promote prompt on purpose: saying yes there would write a real
    run into the permanent, committed `qa_results/` history as a
    side effect of making a video. Worth knowing when re-recording.

15. **[todo, 2026-09-19]** **[Testing & dev tooling]** **[Docs & process]**
    **Priority: pick up tomorrow morning (2026-09-19, Keith's own words,
    after watching a real `delivery-scoper` run take 5+ minutes: "in
    terms of making the agents run faster, flag all that stuff, and
    we'll come back to that tomorrow morning").**

    The `delivery-*` subagents are slow, and the cost is real, measured
    and mostly avoidable. Raised by Keith's own question - "why is it
    taking so long to run? It doesn't have to do a whole lot, does it?
    Or is there a large setup cost?" - during the first real end-to-end
    `delivery-scoper` run (item 25's scoping, `plans/qa-pipeline.md`).
    There is a large setup cost, and separately the slow part isn't the
    part that looks slow.

    **Real numbers from that run**, both passes of the same agent:

    | | tokens | tool calls | wall clock |
    |---|---|---|---|
    | First pass (cold) | 97,907 | 29 | 5m21s |
    | Second pass (resumed, answers relayed) | 119,130 | **2** | 3m28s |

    The second pass is the informative one: **2 tool calls, 3.5
    minutes**. It read essentially nothing and still took most as long
    as the cold pass, because what dominates is GENERATION over a large
    context, not file reading. Any fix aimed only at "make it read less"
    addresses the smaller half. Worth stating plainly before anyone
    optimises the wrong thing.

    **Where the ~98k of cold context goes** (approximate, `wc -w` x 4/3;
    the exact read set isn't inspectable without pulling the agent's own
    transcript into the main session's context, which would cost more
    than it tells us):

    - **`plans/qa-pipeline.md` - ~58,000 tokens.** 5,180 lines. The
      single largest item by a wide margin, and the agent had to go
      there because item 25 lives in it.
    - **`CLAUDE.md` - ~11,800 tokens**, loaded into every subagent
      automatically (see below).
    - Soda checks YAML + `check_lifecycle.py` + `requirements.yaml` -
      ~12,000.
    - `docs/components.md` + `docs/project-context-for-agents.md` -
      ~3,700.
    - The agent's own prompt - ~2,200.

    **Three real levers, none decided - this is the part to work through
    with Keith, not to guess at:**

    1. **`plans/qa-pipeline.md` has outgrown a single file** - every
       agent touching any QA-check question pays the full ~58k to read
       one item out of it. **Split out into its own item, #17**, at
       Keith's own ask: the same cost is paid by every SESSION at
       start, not just by agents, so it's broader than agent speed.
       See #17 for the real numbers and the options.
    2. **`omitClaudeMd: true` is a real, documented frontmatter option**
       (verified against Claude Code's own subagent docs while checking
       the `AskUserQuestion` question - see #16). A subagent loads
       "every level of the CLAUDE.md hierarchy the main conversation
       loads" unless it opts out, and none of the 8 `delivery-*` agents
       opts out - so each pays ~11,800 tokens for it.

       **A first version of this bullet claimed that cost was
       duplicated, because all 8 are also told to read the condensed
       `docs/project-context-for-agents.md`. That claim was asserted,
       not checked, and checking it showed it was wrong** - recorded
       here rather than quietly deleted, since the mistake is the
       instructive part. The two documents are largely
       COMPLEMENTARY: the agents doc is domain orientation (who the
       users are, what each wants, what's real vs illustrative,
       maturity) and explicitly defers to `CLAUDE.md` for architecture;
       `CLAUDE.md` carries the operational rules the agents doc barely
       touches. Real counts - `mothman` entry-point rule 22 mentions vs
       3, the no-live-data rule 5 vs 0, `uv run` 17 vs 0,
       enumerate-every-consumer 2 vs 0.

       So this lever is **much weaker than it first looked**, and worth
       keeping only as a documented option rather than a recommendation.
       `delivery-scoper` visibly USED `CLAUDE.md` on its first real run:
       its NFRs cite the "enumerate every consumer mechanically"
       convention, Thread D's settled "no CLI" call, and the real
       check-yaml pre-commit incident with shell-style quoting - none of
       which is in the agents doc. Dropping it would have cost real
       output quality to save ~12k tokens. If this is revisited, the
       question is narrower than "opt out": whether the handful of
       operational conventions an agent genuinely needs should be
       promoted into the agents doc, and only THEN the full file
       dropped - and whether that differs between pre-build agents
       (which reason about requirements) and post-build critics (which
       actually run commands and need the `uv run`/`mothman` rules).
    3. **Point an agent at an item, not a file.** The scoper was told
       to read "`plans/qa-pipeline.md` item 25 (around line 1131)" and
       appears to have read the file. A prompt that hands over the
       relevant extract directly, or names a line range, would sidestep
       most of the single largest cost without any restructuring at
       all - the cheapest of the three, and testable immediately.

    **Measure, don't guess** - the same standing lesson the `pytest
    --durations` profile established for test runtime. A real before/
    after on one identical scoping task is the way to tell which of the
    three actually moved the number, rather than doing all three and
    assuming.

    **RESOLVED 2026-09-20, and mostly in the direction of "this is not a
    problem".** Two things settled it.

    **New evidence, from the same day's `delivery-architect` and
    `delivery-dashboard-ux` runs.** Lever 3 was used on both without
    labelling it a test - each was handed a 181-line extract in a
    scratchpad file rather than told to go read `plans/qa-pipeline.md`
    item 25. Neither got cheaper:

    | agent | tokens | tool calls | wall clock |
    |---|---|---|---|
    | `delivery-scoper` (cold, no extract) | 97,907 | 29 | 5m21s |
    | `delivery-architect` (given the extract) | 109,458 | 31 | 5m06s |
    | `delivery-dashboard-ux` (given the extract) | 106,865 | 28 | 5m27s |

    They skipped the ~58k file and spent it elsewhere, on reading real
    code - which is what they are for. The architect's note cites line
    numbers across a dozen files and found three config-hash traps
    nobody had spotted; it earned those tokens. Honest limit on this
    evidence - only totals are visible, since inspecting what each
    agent actually read means pulling its transcript into the main
    session and costs more than it tells us.

    **So the reframe: ~100-130k and ~5 minutes is the price of a
    thorough agent pass, not waste.** The levers move WHERE the context
    goes, not how much of it there is.

    **Keith's call, same day, on being shown that: latency is "definitely
    not an impact".** That closes the speed motivation entirely, and
    with it levers 1 and 3 as speed measures - lever 1 (splitting
    `plans/qa-pipeline.md`) still stands on its own merits under #17,
    which is about every session's start cost rather than agents.

    **Lever 2 (`omitClaudeMd`) is formally CLOSED, not merely
    deprioritised.** This item's own correction already showed it was
    weak; the deciding evidence is that `delivery-scoper` visibly USED
    `CLAUDE.md` on its first real run, citing the enumerate-every-
    consumer convention, Thread D's settled "no CLI" call and the real
    check-yaml quoting incident in its NFRs - none of which appear in
    `docs/project-context-for-agents.md`. Dropping it would have cost
    real output quality to save ~12k tokens nobody is short of.

    **What remains live is a different lever this item never considered -
    model choice**, which acts on generation, the half that actually
    dominates. All 8 agents default to `model: opus`. Keith, same day -
    "I'm open to experimenting with different model choices". Being set
    up as a real controlled comparison rather than a guess, since the
    2026-09-19 runs left high-quality Opus baselines on a task whose
    answers are now known - see this item's own follow-up once the
    result is in.

16. **[done, 2026-09-19]** **[Testing & dev tooling]** **[Docs & process]**
    All 8 `delivery-*` agents declared a tool that can never work, and
    `docs/agent-orchestration.md` documents a workflow that cannot
    happen. Found live during the first real `delivery-scoper` run, and
    caught by Keith reading the agent's own log rather than by anything
    here noticing: the agent tried to ask him a question and got
    `Error: No such tool available: AskUserQuestion`.

    **Verified against Claude Code's own subagent documentation, not
    left at the error string** - Keith's own explicit ask ("verify
    through looking at Claude's subagent documentation whether you can
    give AskUserQuestion to a subagent rather than just assuming").
    The docs list the tools removed by the first filter, introduced as:
    *"The first filter removes these tools, even when listed in the
    `tools` field"* - and `AskUserQuestion` is on it, alongside
    `EndConversation`, `EnterPlanMode`, `ScheduleWakeup`, `TaskOutput`,
    `WaitForMcpServers`, `Workflow`, `ExitPlanMode` (unless
    `permissionMode: plan`) and `Agent` at the depth limit. So this is
    documented, universal to all subagents, and explicitly NOT
    fixable by listing it in `tools:`. The runtime error says "in this
    environment", which is what initially led this session to log it as
    an environment quirk - the docs are clearer than the error message,
    and the first write-up here was wrong until Keith pushed for the
    real source.

    Worth recording HOW that mattered, not just that it was wrong: the
    whole roster was designed around agents interrogating Keith
    directly. `delivery-scoper`'s own description is "stress-tests the
    idea with clarifying questions rather than assuming", it references
    the tool 3 times in its own body, and the other 7 reference it
    once or twice each. The premise held for none of them, and nobody
    noticed until an agent actually tried.

    **The fix, in two parts:**

    - **Strip the dead grant from all 8 agent files** and rewrite the
      instructions that tell each one to ask directly. They should
      instead hand questions back in relay-ready shape - which is what
      `delivery-scoper` improvised on its own when blocked, writing its
      forks as pre-formed `AskUserQuestion`-shaped sets with 2-4
      options each, and it worked well enough that the main session
      relayed them verbatim across 3 rounds.
    - **Rewrite `docs/agent-orchestration.md`'s flow** into the relay
      loop, with the doc citation so a future session doesn't
      re-litigate it. The loop: the agent hands questions back, the
      main session puts them to Keith with its own `AskUserQuestion`,
      then `SendMessage`s the answers to the SAME agent, which resumes
      with its context intact rather than starting over. The docs name
      resumption as the pattern here: *"When Claude sends a completed
      subagent a message with the `SendMessage` tool, the subagent
      resumes in the background without a new `Agent` invocation."*
      Verified working for real across 3 rounds on item 25's scoping.

    What's genuinely lost, and should be said in the doc rather than
    glossed: the agent can't adaptively follow up mid-flight without a
    round trip through the main session, so it has to front-load its
    questions into batches. That is a real constraint on the design,
    not just a transport detail - it pushes each agent toward asking
    everything it might need at once rather than following a thread.

    Also worth a look while in there: `#15`'s own finding that none of
    the 8 sets `omitClaudeMd`, which is a second frontmatter-level
    thing nobody has audited since these files were written.

    **Built the same night.** `AskUserQuestion` stripped from all 8
    `tools:` lines, and each agent given a real "Asking Keith a
    question" section instead: it states plainly that the tool is
    unavailable and why, cites the documentation so a future session
    doesn't re-litigate it, and specifies the relay shape - batch at
    most 4 questions with 2-4 real options each, give the trade-off
    both ways, never offer an "other" option (the tool adds one), and
    say which parts of the draft are provisional on an answer.
    `delivery-scoper`'s own step 2 rewritten, since it was the only one
    whose body actively instructed asking; it now also has to report
    which angles it judged and answered itself versus ruled out, so a
    thin pass is visible as one and Keith isn't asked things the
    codebase already answers.

    `docs/agent-orchestration.md` gained a real section for the loop,
    with the sequence diagram updated to point at it. Two things in it
    are worth more than the mechanism: the front-loading constraint
    (an agent can't follow a thread adaptively, so every follow-up
    costs a round trip through Keith's attention - which pushes toward
    broader, less responsive question sets, and that's the design
    rather than sloppiness), and three practices that made the real
    item 25 run work - relay the agent's own framing rather than a
    paraphrase, verify its factual claims at source before putting
    them to Keith as fact, and answer whatever the codebase or
    `plans/*.md` already answers rather than spending his attention on
    it.

    Not done, deliberately: the `omitClaudeMd` audit above stays with
    #15, since #15's own correction established the lever is much
    weaker than it first looked.

17. **[todo, 2026-09-19]** **[Docs & process]**
    **Priority: pick up tomorrow morning alongside #15 (2026-09-19,
    Keith's own ask - "yes, please log the QA pipeline token problem").**

    This project's own orientation instruction now costs **~159,000
    tokens before any work begins**. `CLAUDE.md` opens by telling every
    new session to read seven `plans/*.md` files "in full before doing
    anything else", and that instruction has quietly become one of the
    most expensive things in the repo:

    | file | ~tokens |
    |---|---|
    | `plans/qa-pipeline.md` | **57,962** |
    | `plans/publishing-and-history.md` | 34,656 |
    | `plans/tooling.md` | 18,764 |
    | `plans/wider.md` | 16,752 |
    | `plans/dashboard.md` | 12,744 |
    | `CLAUDE.md` itself | 11,830 |
    | `plans/data-generation.md` | 4,264 |
    | `plans/conceptual-design.md` | 2,050 |
    | **total** | **~159,022** |

    Split out from #15 (agent speed) at Keith's own ask, because it
    isn't only an agent problem - #15 found it, but **every session pays
    this, including the main one, at every start.** A subagent reading
    one file is the cheap case.

    **The real finding is not file size, it's the `done`/`todo` ratio.**
    Parsed through `dashboard/plans_md.py`'s own parser: 137 items, of
    which **78 `done` plus 3 `superseded`** - and those account for
    **~85,000 of the ~107,000 tokens of item text, 79% of it.** The
    numbered-item files have become mostly a record of completed work,
    because this project's convention is to append a full build write-up
    to an item when it lands rather than collapse it to a line. Current
    live work - 37 `todo`, 12 `parked`, 7 `investigate` - is under a
    quarter of the volume.

    **And that is exactly what makes this hard rather than obvious.**
    Those completed write-ups are not dead weight: they exist precisely
    so a session doesn't re-derive a settled decision, which is
    `CLAUDE.md`'s own stated reason for the read-everything rule
    ("don't re-derive a decision that's already recorded there, and
    don't re-propose something already logged"). Cutting them to save
    tokens would cause the exact failure the instruction was written to
    prevent. This item is NOT "the plans files are too big, trim them".

    Real options to weigh tomorrow, none decided:

    - **Split `qa-pipeline.md`.** 5,180 lines, nominally scoped to one
      dataset's pipeline while plainly carrying everything. Direct
      precedent twice: `wider.md` split 2026-09-18, `tooling.md` split
      out of it 2026-09-19. Reduces the per-question cost without
      losing anything - but doesn't reduce the session-start total at
      all if the instruction still says read all of them.
    - **Change the instruction, not the files.** Read the live items in
      full; read `done`/`superseded` as an index (id, title, one line)
      and drill in on demand. This is the only option that actually
      moves the ~159k number, and it's the one with real risk attached -
      it trades a guaranteed cost for a probabilistic one, where the
      failure mode is a session confidently re-proposing something
      settled months ago.
    - **Generate the digest rather than hand-maintain it.**
      `dashboard/plans_md.py` already parses every item into structured
      fields (status, components, file, number, text) for the Plans tab.
      A generated per-file index is close to free and can't drift from
      the source the way a hand-written summary would.
    - **Do nothing deliberately.** ~159k is affordable in a large
      context window, and the instruction demonstrably works - this
      session alone caught two stale items (`plans/qa-pipeline.md` #74's
      partly-fixed threshold bug, item 25's half-built premise) because
      the context was actually there. Worth stating as a real option
      rather than assuming the cost must be paid down.

    Measure before and after, same standing lesson as #15 and the
    `pytest --durations` work: a real token count on one identical task
    is the way to tell whether a change helped.

    **BUILT 2026-09-20 - the generated-digest option, and three real
    proof runs against it.** `plans/INDEX.md`, built by `dashboard/
    plans_index.py` from the same parser the Plans tab already uses, one
    entry per numbered item and per Thread/Phase, CI-gated by `mothman
    dashboard plans-index --check` so the committed copy cannot drift
    from its source. Nothing is deleted - Keith's own condition when
    this was scoped - every entry still exists in full in its own file.
    Grew over the day as each proof found a real limit: sub-entries for
    the two essay files (a Thread was one line for 400 lines of prose),
    sub-entry headers that carry the text they introduce rather than
    truncating at the colon, and - Keith's own suggestion - a `touches:`
    line per entry naming the source files that entry's own text refers
    to. Final shape: 358 lines, ~6,945 tokens, 92 `touches:` lines,
    against the ~159,000 the read-everything instruction costs.

    **The third proof was the decisive one**, and it is worth recording
    honestly because it did not simply confirm the thing was working.
    Method: a pristine git worktree at the pre-scoping commit, a
    `delivery-scoper` run on item 25 with only the index as its entry
    point, scored on three questions set before it ran. Its own account,
    in full, plus the tool trace it left:

    - **The index did what it was built for.** The agent never opened a
      `plans/*.md` file in full. Its entire plans reading was two slices
      of `qa-pipeline.md` (items 25 and 43) and ~40 lines of
      `publishing-and-history.md`. It ruled out four whole files -
      `data-generation.md`, `conceptual-design.md`, `wider.md`,
      `tooling.md` - from their index lines alone, correctly. That is
      most of a 159k read avoided for two wrong turns.
    - **But neither of the two findings that actually mattered came from
      the index.** The decisive one - that item 25's feature was already
      ~70% built - came from opening item 43 on a judgement call, off a
      summary line that never mentions descriptions. The index pointed
      at a door without saying what was behind it. The second - Phase
      5c's real build of the "What this check does" panel - did not come
      from the index at all: the agent found it by grepping the
      template, then grepped `publishing-and-history.md` for the string
      it had found. At step 172 of 183.
    - **`touches:` was useful, useless and misleading, all three.**
      Genuinely useful on `dashboard.md` #8 and Thread D, where it gave
      an accurate multi-file map the agent reasoned from without opening
      anything. Useless but harmless on `done` items already ruled out.
      And **misleading by omission in the one place it mattered most**:
      item 25's `touches:` names `dbt_project/models/staging/schema.yml`
      and `pipeline/dashboard_check_labels.py`, both honest readings of
      that item's own text, neither anywhere near where the mechanism
      actually lives. The agent read `dashboard_check_labels.py` in full
      and found it was about card titles and status ranking. The
      field's contract is "files this entry's text refers to", which is
      exactly why a stale entry yields stale pointers - `touches:`
      inherits the staleness of the prose it is derived from, while
      looking like ground truth.

    **The conclusion, stated plainly: an index over stale text is a
    faithful index of stale text.** Every current-state fact in that
    run's report - the real description counts, `cli/bdm.py:241`'s raw
    `check_id`, `COLUMN_META`'s third hardcoded copy, `description`
    being unvalidated while `check_id`/`category` are hard errors - came
    from reading the code, not the plans. The index makes the plans
    cheap to navigate. It does not make them true, and this run's most
    valuable output was catching that they weren't.

    Two concrete follow-ups the run named, both still open: the
    `Build order` entry in `publishing-and-history.md` is one `done`
    line with ~44 sub-entries and a `touches:` list ending "+34 more" -
    in practice a "read the whole file" pointer, and Phase 5c is not
    named anywhere in it. And several sub-entries truncate one clause
    short of the decision they record - Thread D's field list stops
    immediately before `description`, `dashboard.md` #8's stops at
    "category axis: a real per-check". The truncation is not random; the
    interesting part of a line of this project's prose tends to be near
    its end.

    **Truncation FIXED 2026-09-20 (Keith's own call - do this one, park
    the other two).** Measured first rather than guessed, and the
    measurement changed the fix: **72% of entry summaries and 98% of
    sub-entries are longer than the 120-character cap**, so where the
    cut lands is the normal case, not an edge case. Raising the cap was
    the obvious move and the wrong one - 120 -> 250 would have doubled
    the index (~7,000 -> ~12,600 tokens) and spent almost all of it on
    ordinary prose that was never the problem. The two real failures
    were both structural, and both cheap to fix directly:

    - **A cut that lands inside an open bracket.** This project's prose
      habitually puts the decision inside a parenthetical - `dashboard.md`
      #8's entire outcome (the category axis AND the UI surface) is
      inside one. An unclosed bracket is the one truncation that is
      actively misleading rather than merely short: it promises a
      qualification and then withholds it. Now the parenthetical is
      either carried whole or dropped entirely.
    - **A colon-ended header followed by a list.** Carrying the
      following prose verbatim spends the whole budget naming the FIRST
      member and none of the others - which is exactly how Thread D's
      field list stopped before `description`. Now the item TERMS are
      listed instead: "check_id, introduced_date, retired_as_of +
      retired_reason, description, changelog". It answers the question
      and is *shorter* than the truncation it replaces.

    Only 21 sub-entries are term lists and only 27 summaries would stop
    inside a bracket, so letting each run to its natural end cost ~8%
    (45,297 -> 49,068 bytes), not the ~80% a bigger cap would have.

    Two real bugs found in that fix, both caught by a test written to
    fail first: a per-term cap that sliced mid-word ("a real visual
    gap/sp"), and a clause splitter that broke at any `.`, renaming
    `CLAUDE.md` to `CLAUDE` and `qa_results_writer.py` to
    `qa_results_writer` - a term list of filenames whose filenames had
    silently lost their extensions.

18. **[done, 2026-09-20]** **[Docs & process]**
    **BUILT 2026-09-20** - parked earlier the same day, then unparked
    once the verification-methods question below settled what it was
    actually for.

    Point a requirement at the code that implements it, not just at the
    tests that verify it. `requirements.yaml` has `linked_tests`, which
    CI resolves against a real AST parse - `tests/test_x.py::TestY::test_z`
    fails the build if that method does not exist. There is no
    equivalent for implementation. The full field set today is `id`,
    `title`, `story`, `moscow`, `status`, `acceptance_criteria`,
    `linked_tests`, `source`, `date_written`,
    `non_functional_requirements`, `open_questions`, `dependencies`,
    `evidence` - and `evidence`, the only free-text candidate, is used
    by **zero of the 27** requirements.

    **Why this came up, and why it probably matters more than the
    alternative it displaced.** The third index proof (#17 above) found
    that `touches:` pointed at the wrong files for item 25 - honestly
    derived from that item's own prose, but the prose was stale, so the
    pointers inherited the staleness while looking like ground truth.
    The obvious response was a manual backfill of `touches:` across
    ~150 plans entries. Keith's own reaction, and it reframes the
    problem: *"now that I say it, going forward we're going to have
    requirements for everything and the requirements point to the files
    involved, right? Because that's a better source than the plan
    files, which are going to be high level, kind of almost like
    ephemeral artifacts."*

    That is the right split. A plans entry is a narrative written at a
    moment in time and never revisited; a requirement is checked against
    reality by CI. `linked_tests` already proves the mechanism works. A
    hand-backfilled `touches:` would be a second, unverified copy of
    something a requirement could hold authoritatively - so the backfill
    is parked with this, not scheduled alongside it.

    **Decided in advance (Keith, 2026-09-20), so the build does not have
    to re-ask:** the field is **required once `status` is `built`** -
    the same rule `linked_tests` already carries. That is the stronger
    of the two options considered and it has a real, known cost: all
    22 already-built requirements need backfilling before CI can go
    green, so this cannot land incrementally.

    **Symbols, decided 2026-09-20** (Keith: "let's definitely go
    symbols... CI validates the files and the symbols with an AST pass").
    The rule, and the asymmetry in it, is the whole point:

    - A `.py` entry **must** name a symbol (`file.py::function` or
      `file.py::Class::method`) and is AST-verified. A bare Python path
      is rejected outright. `Path.exists()` stays green while a module
      is gutted, stubbed, or renamed-and-recreated - which is precisely
      how `touches:` rotted while continuing to look authoritative.
    - A front-end path (`.html`/`.js`/`.ts`) may be bare, since there is
      no JS parser on the Python side and this project's own validator
      docstring rules out a regex for exactly this job ("never a regex/
      string match, which could be fooled by a comment or a docstring
      mentioning the same name"). Keith's framing: "for the HTML we'll
      probably end up with a separate TypeScript or JavaScript file, and
      maybe we can take it up later."
    - A `::` on a front-end file IS allowed and IS verified - just in
      the Node toolchain, by the new `tests-js/implements.test.js`. It
      reuses `tests-js/support/loadDashboard.js`, which already loads
      the real committed template into a real jsdom window with
      `runScripts: "dangerously"`, so every top-level `function foo(){}`
      genuinely becomes `window.foo`. That is **stronger** than the AST
      check it stands in for, not weaker: it is real execution, so a
      name appearing only in a comment cannot pass.
    - A `::` on anything else (`.yaml`, `.sql`) is rejected. Nothing
      verifies it, and an unchecked claim inside a checked field is
      worse than a plain path.

    Both halves were proven by breaking them on purpose rather than
    assumed: renaming a real Python symbol produced
    `REQ-QAC-006: implements entry '...::parse_contract_check_metadataX'
    names no real function/class/method in that file`, and typo-ing a
    template symbol failed `npm test` naming `REQ-DASH-012` and the
    exact entry.

    All **14** `built` requirements backfilled in the same change, since
    "required once built" cannot land incrementally. The panel renders
    "Implemented in:" directly above "Verified by:" - verified in a real
    browser, 14 rendered blocks, zero console errors - because they are
    two halves of one question and reading them apart is what let the
    register answer only the second for a year.

    **The four verification methods, and what this means for
    `evidence`.** Recognised practice has four: analysis, inspection,
    testing, demonstration. Keith's own read, 2026-09-20, and it holds
    up better than the framing it corrected:

    - **Testing** - `linked_tests`, already.
    - **Demonstration** - also `linked_tests`. `tests/
      test_dashboard_e2e.py` drives a real browser through the real
      flow. Once a demonstration is automated and committed it stops
      being a separate method and becomes a test; the distinction is
      about who watches, not about what is verified.
    - **Inspection** - this field, with one honest caveat: it gives the
      *object* of inspection, not a record that one happened. That is
      the better half to hold, though. A prose note saying "read lines
      42-88 on 2026-09-20" is an unverifiable claim about the past that
      decays silently; a CI-verified pointer stays true or breaks the
      build.
    - **Analysis** - the genuine remainder. Deriving that a requirement
      holds by measurement rather than execution (the 72%/98%
      truncation figures, the token-cost tables, REQ-QAC-023's
      byte-identical `config_hash` proof) has no field. In practice it
      already lands in `plans/*.md` and `CHANGELOG.md`, which is a
      reasonable home.

    So `evidence` is now largely redundant - three of the four methods
    are covered by fields that CI enforces, and the fourth has a home
    elsewhere. **Not retired here**, deliberately: removing a field is a
    separate decision from adding one, and it is Keith's to make. Logged
    as #20 below.

    **Provenance of `evidence`, traced 2026-09-20 at Keith's ask**,
    because the lesson shaped this field's design. It arrived in
    `6cc10f1` (2026-09-19) as one of five optional fields, spec'd
    clearly in `requirements.yaml`'s own header: "populated by the
    requirements-reviewer agent, not the scoper... a real paper trail
    distinct from just which tests pass." It has **zero uses**, and not
    through neglect.

    **First diagnosis, and it was wrong.** This entry originally said
    the field had been assigned to `delivery-critic`, which is
    read-only, so nothing could write it. Keith corrected that the same
    day: the main session does all the writing regardless, so write
    permission was never the constraint. He is right, and the real
    numbers make it plain. Of the five fields added in that one commit,
    counted across the five requirements written since:

    | field | used |
    |---|---|
    | `source` | 5/5 |
    | `non_functional_requirements` | 5/5 |
    | `dependencies` | 4/5 |
    | `open_questions` | 2/5 |
    | `evidence` | **0/5** |

    Same author, same file, same commit, same session. Permission
    explains none of that spread.

    **What does explain it is the handoff FORMAT.** The four populated
    fields are all ones `delivery-scoper` produces, and its output
    contract is a YAML block that gets pasted straight in. `evidence` is
    the only one assigned to a stage - the critic - whose output
    contract is a **prose report**. It never arrives in a shape that
    lands in the file, so it does not land. `open_questions` at 2/5
    rather than 5/5 is honest absence (not every requirement has one);
    `evidence` at 0/5 is not, because all five of those requirements
    genuinely WERE verified against real code. The evidence existed and
    had nowhere to go.

    A grep of every `.claude/agents/*.md` and `docs/*.md` still finds
    not one mention of the field, which is the same point from the other
    side: no stage is told to emit it in a form anything can use.

    The actionable version, then, is narrow and cheap: give the critic's
    output contract a YAML fragment alongside its report, the way the
    scoper's already has one. Whether that is worth doing at all is #20.

    Neither cited source prescribes it. EARS is purely a phrasing
    template set and has no opinion on attributes at all. The
    `zhsama/claude-sub-agent` precedent (README fetched and read, not
    assumed) has no `evidence` concept: its `spec-validator` outputs
    "Validation report, quality score" - a *separate artifact*, never an
    amendment to `requirements.md`. The field is this project's own
    invention.

    **That is why `implements` is required rather than optional.** A
    field with no forcing function stays empty however well its schema
    is written - `evidence` proves it, with a better spec than most.
    Keith's "required once built" call supplies the forcing function,
    because CI refusing to go green is one.

20. **[todo, 2026-09-20]** **[Docs & process]**
    Decide whether `requirements.yaml`'s `evidence` field survives.

    Raised by #18's own build, not a fresh idea: with `implements`
    landed, three of the four recognised verification methods are
    covered by CI-enforced fields (`linked_tests` for testing and
    demonstration, `implements` for inspection) and the fourth
    (analysis) already lands in `plans/*.md`/`CHANGELOG.md`. `evidence`
    has zero uses across 27 requirements - and, per #18's own corrected
    diagnosis, that is a handoff-format problem rather than a
    permissions one: it is the only optional field assigned to a stage
    whose output is prose rather than a pasteable YAML block.

    Three real options, none picked:

    - **Retire it.** A field nothing fills is noise in a schema whose
      whole value is that its fields are real, and it quietly teaches
      whoever reads the schema next that optional fields here are
      decorative.
    - **Give it a write path.** Concretely: add a YAML fragment to
      `delivery-critic`'s output contract, the way `delivery-scoper`
      already has one. Cheap, and it would work - the four fields the
      scoper emits are at 4/5 or 5/5. The question is whether the
      content is worth having once `implements` and `linked_tests`
      cover inspection, testing and demonstration between them.
    - **Narrow it to analysis specifically** - the one method genuinely
      uncovered (a measurement or derivation that proves a requirement
      holds without executing it). That would give it a reason to exist
      that it currently lacks, and a much clearer authoring rule than
      "what was checked and how", which today overlaps three fields.

    Worth deciding rather than leaving as-is.

19. **[todo, 2026-09-20]** **[Docs & process]**
    **PARKED by Keith, 2026-09-20**, same conversation as #18.

    `plans/publishing-and-history.md`'s `## Build order` section is one
    heading over **1,711 lines** - 53% of that whole file - containing
    Phases 1 through 7, each with its own full build write-up. The index
    parser keys threads on `##`, so all of it collapses to a single
    entry: one `done` line, ~44 sub-entries, and a `touches:` list
    ending "+34 more". In practice that is a "read the whole file"
    pointer.

    It is not really an index bug. That section is structurally seven
    sections wearing one heading, and Phase 5c - the sub-heading a real
    proof run needed and never found - sits three levels inside it. The
    phases are consistently marked (`**Phase N (...)** - [DONE, date]:`),
    so promoting them to real entries is tractable; whether to do that
    in the parser or by splitting the source file is the open question.
