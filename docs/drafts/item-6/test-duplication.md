<!-- Copied from the session scratchpad 2026-10-18 ~21:35 Perth so it survives the container, for Keith's morning walk-through (morning report #6). A read-only review; nothing in it has been acted on except F2's leak, fixed the same day as post-build-review #225. -->

# Duplication among the registry-era tests

Read-only review. I ran no tests and touched no database. Each finding was checked against the product code it exercises, to see whether the two halves really go through one code path. That meant checking the legacy flags in `qa_tools/tools/legacy.py`, whether each runner branches on its adapter, and whether `cli/one_table.py` and `cli/many_tables.py` each have their own copy of the code.

**Totals: 9 findings that would remove tests, about 10 test functions removable out of 27 involved.** The 12 groups that only look like duplicates are listed under "Kept" with the reason each one stays. Gaps where a shared behaviour is tested for only one collection are at the end.

Ordered by how many tests each finding removes. Ties are ordered by confidence.

---

## F1. Evidently "no reference is not a pass": the CP unit class repeats BDM's real test (removes 2)

- `tests/test_run_evidently_cp.py::TestNoReferenceIsNotAPass::test_it_reports_no_reference_rather_than_passing` asserts that PSI status is `nodata` (and, redundantly, not `pass`).
- `...::TestNoReferenceIsNotAPass::test_it_computes_nothing_at_all` asserts that PSI `metric_value` and `reference_run_id` are None, with a stubbed `_reference_frame` that raises if it is reached.
- `...::TestNoReferenceIsNotAPass::test_the_row_count_it_did_measure_is_still_there` asserts PSI `row_count_total == 2`.
- `tests/test_run_evidently_bdm.py::TestASupplyWithNothingToMeasureAgainst::test_the_drift_check_says_no_reference_rather_than_pass` asserts PSI status `nodata`, metric None, reference None and the engine tag, using the real tool on real fixtures.

**Why they duplicate (types 2 and 4).** The PSI half of `evaluate()` (`_psi_result`) is shared and no legacy flag touches it. `evidently.reads_unreadable_tables` only gates whether the check runs at all. The CP class stubs both frames, so the only thing "Child Protection" adds is the check config. Its first test is a strict subset of the BDM real test. Its second test repeats two of BDM's assertions; only the raising stub is new.

The three CP tests make the same stubbed call and read three slices of the result.

**Recommendation.** Merge the three CP tests into one: `nodata`, metric None, reference None, `row_count_total == 2`, with the raising `_reference_frame` stub kept. That keeps the one thing nothing else proves (the reference frame is never built). **4 involved, removes 2.**

## F2. Generator: "never touches the real delivery tree", CP half (removes 1, and it may be leaking)

- `tests/test_generate_runs.py::test_generating_never_touches_the_real_delivery_tree` fingerprints the real deliveries, receipts, bookkeeping and `scenario_placements.json`. It then calls `driver.generate("civil-registration")` with all four redirected and asserts the real ones are unchanged.
- `tests/test_generate_cp_runs.py::test_generating_never_touches_the_real_delivery_tree` does the same for `driver.generate("child-protection")`, but redirects and checks only three of the four (no placements).

**Why they duplicate (type 2).** Since REQ-GEN-246 every write goes through `generator/driver.py`'s module globals plus `scenario_injection.PLACEMENTS_PATH`. Providers only return file contents: I grepped `generator/collections/*.py` and found no direct writes. Isolation is therefore the driver's property, not the provider's, and the CP test is a strict subset of the BDM one. It also pays for a whole extra Child Protection generation, which has been the expensive one since the 55-quarter growth (REQ-GEN-207).

**Possible defect, not verified by running.** The CP test does not redirect `PLACEMENTS_PATH`, and the CP provider has injected scenarios (cp-clients ones in `scenario_injection.py`). So `plan.resolved` is non-empty and `write_placements(merge=True)` probably writes the REAL `data/scenario_placements.json` every time this test runs. That is the leak the BDM test's own docstring (the 2026-09-29 note) says it fixed in its own copy. I found nothing in `tests/conftest.py` that guards placements writes.

**Recommendation.** Delete the CP copy. BDM's covers the driver, including placements. **2 involved, removes 1.** If the CP copy is kept for any reason, it needs the `PLACEMENTS_PATH` redirect. Treat that as a defect fix, test first, per CLAUDE.md.

## F3. Generator: "writes a delivery and nothing beside it" (removes 1)

- `tests/test_generate_runs.py::test_the_generator_writes_a_delivery_and_nothing_beside_it`
- `tests/test_generate_cp_runs.py::test_the_generator_writes_a_delivery_and_nothing_beside_it`

Both have identical bodies. Each asserts that the output root holds `deliveries`, `receipts` and the bookkeeping file and nothing else, and that no supply file appeared under the real `data/`.

**Why (type 2).** Everything asserted is written by the driver (`delivery.write_delivery`, `write_bookkeeping`, `write_placements`). Providers have no write path of their own. `tests/test_generator_providers.py::TestOneDriverForEveryCollection::test_a_third_collections_history_is_written_by_the_shared_driver` also proves the driver's output layout through a third provider.

**Recommendation.** Delete the CP copy. It costs nothing at runtime, because the module's `manifest` fixture is shared, so this is about the record rather than speed. **2 involved, removes 1.** Moderate confidence: the only thing the CP copy guards is a future CP provider writing a file itself.

## F4. `has_failures` tested once per collection on a static base method (removes 1)

- `tests/test_cli_bdm.py::test_has_failures_true_on_fail_or_error_false_otherwise`
- `tests/test_cli_cp.py::test_has_failures_true_on_fail_or_error_false_otherwise`

Same three assertions on `bdm.has_failures` and `cp.has_failures`.

**Why (type 1).** `has_failures` is a `@staticmethod` on `CollectionCLI` (`cli/collection_cli.py:163`). Both halves call one function with identical inputs.

**Recommendation.** Delete the CP copy. **2 involved, removes 1.**

(The neighbouring picker round-trip pair is NOT a duplicate: `picker_choices` has separate implementations in `one_table.py` and `many_tables.py`.)

## F5. TUI QA menu: dispatch proven three times (removes 1)

- `tests/test_cli_app.py::test_qa_menu_picks_bdm_and_calls_its_run_qa_interactive` asserts that picking BDM's label runs only BDM.
- `tests/test_cli_app.py::test_qa_menu_picks_cp_and_calls_its_run_qa_interactive` is the same for CP.
- `tests/test_collection_cli.py::TestTheTUIMenus::test_a_third_collection_is_offered_and_runs_its_own_flow` asserts that the choices are all three labels in hierarchy order and that picking the fake runs only the fake.

**Why (types 2 and 4).** `cli/app.py::_qa_menu` is three lines with no per-collection branch. The third-collection test proves both "listed from the registry" and "the choice runs that one and no other".

**Recommendation.** Delete the CP pick test. Keep BDM's as the real-label instance next to the registry one. **3 involved, removes 1.**

## F6. TUI generate menu, first run: BDM and CP mirror each other (removes 1)

- `tests/test_cli_app.py::test_generate_menu_first_run_skips_confirmation_and_generates` (BDM) asserts: no deliveries, no confirm prompt, generates.
- `tests/test_cli_app.py::test_generate_menu_picks_cp_and_generates_via_the_cp_module` asserts the same for CP. It also stubs `generated_output_dir`, which is not asserted.
- Also in scope: `tests/test_collection_cli.py::TestTheTUIMenus::test_the_generate_menu_dispatches_the_same_way` (the fake collection).

**Why (type 2).** `_generate_menu` has no per-collection branch.

**Recommendation.** Delete the CP copy. **3 involved, removes 1.** Keep the "declined confirmation" test, which is a different branch.

## F7. `debug run-dbt` dispatch: BDM, CP and the third collection (removes 1)

- `tests/test_cli_debug.py::test_run_dbt_bdm_looks_up_nothing_and_calls_evaluate_dbt_bdm`
- `tests/test_cli_debug.py::test_run_dbt_cp_calls_evaluate_dbt_cp`
- `tests/test_collection_cli.py::TestTheSharedCollectionOption::test_debug_runs_a_tool_for_a_third_collection`

All three assert that `run-dbt --collection <short>` calls `run_dbt.evaluate` with the matching collection id and run id.

**Why (type 2).** `run_dbt_command` does not branch at all (`cli/debug.py:71`).

**Recommendation.** Delete the CP copy. **3 involved, removes 1.** The `run-datacontract` and `run-evidently` pairs are NOT duplicates: both branch on `_one_table()`, and the BDM tests cover the manifest guard while the CP tests cover the default reference.

## F8. `pipeline run --collection X` touches only X: mirror tests (removes 1)

- `tests/test_cli_pipeline.py::test_run_dataset_bdm_only_never_touches_cp`
- `tests/test_cli_pipeline.py::test_run_dataset_cp_only_never_touches_bdm`
- Also in scope: `tests/test_collection_cli.py::TestTheSharedCollectionOption::test_pipeline_run_runs_a_third_collection` (with three registered, only the fake runs).

**Why (type 2).** Same path, collections swapped. The two step-order assertions are identical.

**Recommendation.** Delete the CP-only copy. **3 involved, removes 1.**

## F9. Evidently CP write-path tests: two slices of one stubbed call (removes 1)

- `tests/test_run_evidently_cp.py::test_evaluate_evidently_cp_writes_under_the_collection_id_not_the_table_id` asserts that `write_qa_result` gets the collection id.
- `tests/test_run_evidently_cp.py::test_evaluate_evidently_cp_still_tags_its_own_result_with_the_table_dataset_id` asserts that the result's `dataset_id` is the table's dataset.

**Why (types 1 and 4).** Same stubs and the same call, different assertions. The second also repeats `tests/test_collections_registry.py::TestTheSharedToolModules::test_evidently_reads_everything_it_needs_from_the_adapter`, which asserts `psi["dataset_id"] == FAKE_DATASET` through the same shared code.

**Recommendation.** Merge into one test asserting both. **2 involved, removes 1.** Lower confidence than F1 to F8: the two are separate guarantees and only the setup is shared.

---

## Kept: looks like duplication, but is not

Each of these was checked against the product code.

1. **The `test_run_{dbt,soda,datacontract}_{bdm,cp}.py` clean/dirty pairs** (12 functions). One shared runner each, but every half runs its collection's OWN real check file (schema.yml, Soda YAML, ODCS contract) under its own legacy flags. Examples: `soda.scope_suffix` and `soda.named_check_value_is_invalid_count` for BDM, `dbt.no_built_model_guard` and `dbt.audits_skipped_tests` for BDM. A broken check in one collection's file is caught only by its own half. The assertions also differ: BDM checks the field shape (run_id, engine, status range), CP checks that results span several tables.
2. **The CP "unreadable table" classes in all four tool tests.** They run the non-legacy branch BDM's flags switch off. The flag branches themselves are covered by stubs in `test_collections_registry.py::TestTheSharedToolModules`.
3. **The Evidently volume no-reference checks**: `test_run_evidently_bdm.py::TestASupplyWithNothingToMeasureAgainst::test_the_volume_check_says_the_same_thing` against `test_run_evidently_cp_real.py::TestARelativeVolumeCheckOnEveryDataset::test_no_reference_means_no_reference_rather_than_a_pass`. Different code: `_volume_from_drift_frame` (the BDM legacy flag) against `_volume_per_table`.
4. **BDM's "forwards the given reference"** (`test_evaluate_evidently_bdm_forwards_the_given_reference_not_the_module_default`). It overlaps `test_run_evidently_cp_real.py::test_dirty_run_has_a_real_check_id_and_reference` in the shared `_psi_result`, but it is BDM's only real drift run against a reference (the `sex` column and its check config). Keep it.
5. **The generator invariant pairs** (`test_generate_runs.py` against `test_generate_cp_runs.py`): one entry per slot, severity counts, resupply only after a red, resupply on a weekday, slot deliveries advancing in time, no date in a run_id. Run ids are composed in each provider (`civil_registration.py:507`, `child_protection.py:528`), so is `received_at`, and BDM has its own weekday-moving logic (`civil_registration.py:698`). These are real per-provider properties of the real histories.
6. **The CLI generate-command trios** in `test_cli_bdm.py` and `test_cli_cp.py` (declined, `--yes`, first run). `generate()` is COPIED in `cli/one_table.py:367` and `cli/many_tables.py:594` (only the prompt text differs), so each trio guards its own copy. That is duplicated PRODUCT code, worth folding into `CollectionCLI`. Once it is folded, one trio becomes removable (3 more tests).
7. **The CLI qa flag-mode pairs** (trial, commit, failures, unknown run id), **the picker pairs** and **the S3 tests.** Separate implementations per shape.
8. **The dashboard builder pairs** (`test_build_dashboard_data.py` against `test_build_dashboard_child_protection.py`): byRun stats, punctuality, "could not evaluate says why", "two checks sharing a name". Different branches: `stats.single_table_shape`, `dashboard.reference_reason_fallback`, same-dataset keys against pooled cross-table keys.
9. **The two third-collection `compute_dataset_stats` tests**: `test_collections_registry.py::TestTheSharedOrchestratorStatsAndRebuild::test_dataset_stats_count_a_third_collections_tables_from_the_registry` (empty StatsSpec) and `test_orchestrate_shared.py::TestAThirdCollectionsStatsAndClaimWindowForReal::test_a_non_empty_stats_spec_is_what_the_fake_collection_measures` (non-empty). They complement each other; consider putting them in one class. There is a one-line overlap in the claim-window pair: the registry test's `_claim_window("child-protection", ...) is not None` is implied by the orchestrate test's exact-window assertion. That is not worth a removal.
10. **Help imports no tool**: `test_collection_cli.py::TestHelpImportsNoTool` against `test_cli_at_thirty_collections.py::TestHelpAtThirty::test_help_imports_no_tool`. They run either side of `N_LIST` (different rendering code) in different trees.
11. **The unknown-collection message**: `test_cli_at_thirty_collections.py::TestTheThresholdAtTwo::test_the_refusal_still_lists_every_collection` (unit, "Closest: bdm") against `test_collection_cli.py::...::test_the_option_refuses_naming_every_collection_at_three` (through the CLI). They overlap on "Known:" and "mothman collections", but only the unit test checks "Closest". You could fold "Closest" into the CLI test and drop the unit test (1 more), but it is a weak case.
12. **Folder links**: `test_dashboard_for_every_collection.py::TestAThirdCollectionIsLinked::test_its_dataset_and_agency_get_links_from_the_registry` against `test_github_links.py::test_a_dataset_opens_its_contract_at_its_own_entry_and_an_agency_its_folder`. The second is stronger on the real two, but only the first would catch a loop hardcoded to them.

## Fixtures (type 3)

- **`third_collection.py`, `fake_collection.py` and `thirty_collections.py` are three fake-collection builders.** Each serves a different mechanism:
  - `third_collection.py` monkeypatches the hierarchy in-process.
  - `fake_collection.py` puts real files in a tree copy and runs subprocess `mothman` plus a bootstrap.
  - `thirty_collections.py` generates 28 config-only adapters in a tree copy.

  None could serve the others without losing what it is for. They already share `tree_copy.py`. **No merge recommended.**
- **Three fake `Provider` subclasses**: `third_collection._provider`, `test_generator_providers._Writing` and the template in `thirty_collections.build`. These are acceptable. `_Writing` exists because the fixture's provider deliberately writes nothing.
- **Small helper copies worth folding** (no tests removed):
  - `test_orchestrate_shared.py::TestEveryAdapterNamesItsResultsFile` re-implements `test_collections_registry._package` and the REAL module list inline.
  - `_patch_delivery_dirs` is defined in both `test_cli_bdm.py` and `test_cli_cp.py`, with different signatures, next to the conftest `*_delivery_dirs` fixtures.
  - The `raw_dir`/`real_data_before`/`manifest` module fixtures in the two generator modules are structurally identical and could be one helper in `generator_isolation.py` taking a collection id.

## Shared behaviour tested for only ONE collection

- **"Running a check is a read of the arrival record, never a write"** (`test_cli_bdm.py::test_run_check_leaves_the_arrival_record_on_disk_exactly_as_it_found_it`) covers only `one_table.run_check`. `many_tables.run_check` has no equivalent.
- **Soda "a check Soda cannot evaluate is recorded as error"** is real-tested only on BDM (`test_run_soda_bdm.py::test_a_check_soda_cannot_evaluate_is_recorded_as_an_error`). CP's real path goes through the readable-table filter, the branch BDM's `soda.reads_unreadable_tables` switches off. CP has only a unit test of `unreported_checks`' table parsing.
- **The dbt audit-table recount** (`metric_value` re-derived around dbt-core#11312) is asserted only on BDM (`test_run_dbt_bdm.py::test_audit_table_correction_overrides_run_results_failures_field`). The shared `_AUDIT_AGGREGATE_SQL` applies to CP's tests too.
- **Dashboard builder robustness tests run only in BDM's single-table shape:**
  - `test_a_run_that_measured_nothing_is_not_current`
  - `test_a_headline_check_with_no_value_for_a_run_does_not_crash_the_build`
  - `test_a_table_level_check_lands_in_a_pseudo_column`

  CP's `row_counts`-by-table shape, and the `dashboard.drops_empty_sections` branch, which BDM switches off, have no counterpart.
- **The registry's third-collection Evidently test does not assert the write location.** Its datacontract and Soda siblings check `written[0][:2] == ("fake-agency", FAKE_ID)`. For Evidently, only `test_run_evidently_cp.py` (F9) covers where results are written.

## What I was unsure about

- **F2's placements leak** is inferred from the code, not observed. The CP test lacks the `PLACEMENTS_PATH` redirect, CP has resolved scenarios, and `write_placements(merge=True)` defaults to the real file. Confirm it by running the CP test once with a real `data/scenario_placements.json` and comparing its mtime.
- **F3** keeps a slight value: it would catch a CP provider writing outside the driver. I judged that remote.
- **F9** is the weakest finding: merging it is housekeeping rather than real duplication.
