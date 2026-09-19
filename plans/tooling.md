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
   `requirements-reviewer` (`plans/wider.md` #10), which only ever
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
   this reuses/extends `requirements-architect`'s own code-quality/
   security checks (which already exist but only run pre-build, on a
   drafted requirement, never against already-merged code generally) or
   is a genuinely separate capability; what triggers it (a manual
   invocation, every PR, every push); how many agents and where the
   language boundary actually falls. Needs a real conversation with
   Keith before anything gets built.

4. **[todo, 2026-09-19]** **[Docs & process]** A documentation-quality
   agent - a real, adjacent idea found while digging into
   `cfisch3r/estimate`'s own real agent files for the UX/visual critic
   split (`plans/wider.md` #10): that repo has a third agent,
   `.claude/agents/doc-quality.md`, not yet looked at in any depth
   (found via a real directory listing, content not yet fetched/read).
   Flagged by Keith to look at later, distinct from item #2 above (that
   one's about Python CODE quality tooling; this one's about
   DOCUMENTATION quality specifically - comments, docstrings, README/
   `plans/*.md` accuracy, or something else entirely, not yet known
   without actually reading that file). Not yet scoped at all - read the
   real file first before proposing anything.
