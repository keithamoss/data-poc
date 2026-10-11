# Test review, pass 2: retired behaviour, source greps, process tooling, redundancy

Read-only review, 2026-10-11. The baseline is 4,641 tests collected (`uv run pytest --collect-only`). Every entry below is a test I read in full.
"fn" means a test function; "items" means collected pytest items, so a parametrised function counts once per parameter.
Nothing was edited, and nothing was run beyond `--collect-only`.

How I found them: an AST scan over every `test_*` function for `inspect.getsource`, `ast.parse`, `read_text()`, `not hasattr(`, `find_spec`, plus a name grep for no_longer/retired/gone/absent/stale. That gave 233 source-reading hits and about 180 name hits. I triaged them by hand.
Many hits are false positives: reading YAML, JSON or workflow configuration is not grepping product source. Those are kept and only summarised.

---

## Headline: tests that are green for the wrong reason

Fix these first. Each one passes today while proving nothing, which is the false-green shape CLAUDE.md warns about.

| Test | Why it is vacuous |
|---|---|
| `test_staging_loads.py::TestStagingIsSequential::test_staging_happens_before_the_tools_fan_out` | It asserts `"build_per_run_warehouses.build_all()" in inspect.getsource(orchestrate_bdm)` (and the CP equivalent). Neither orchestrator calls `build_all()` any more. The string survives only in the stale module docstrings: orchestrate_bdm.py:25 and orchestrate_cp.py:17, which still talk about `data/raw/` and `data/duckdb_runs/`. No `ProcessPoolExecutor` remains either, so the order check `continue`s. It passes on prose alone. |
| `test_arrivals.py::TestNoCommittedResultCarriesBookkeeping::test_every_committed_dataset_stats_file_is_clean` | It walks `ROOT/"qa_results"`, which was deleted by REQ-PIPE-089. `rglob` over a missing directory yields nothing, so the assertion is `[] == []`. |
| `test_dashboard_e2e.py::TestStatusMatchesEachToolsOwnVerdict::test_every_rendered_status_matches_the_tool_that_produced_it` (only the floor guard) | The guard against "compared nothing" counts runs under `qa_results/*/*`, which is now 0. So it degrades to `compared > 0`. The disagreement check itself is still real. |
| `test_trial_runs.py::TestATrialLeavesNothingBehind::test_the_tidy_up_is_one_transaction` | It asserts `"transaction" in inspect.getsource(trial.discard).lower()`. The docstring alone ("ONE TRANSACTION ...") satisfies it. |

Recommendations:
- **TestStagingIsSequential:** delete all 3 tests. They are counted under A below.
- **The bookkeeping test:** replace it with a query over `qa` dataset_stats payloads in the deployment database. The rule is still alive. If that is not wanted, delete it, since the static AST half in the same file covers new code.
- **The e2e floor:** derive it from `qa.run` row count, or from the embedded run list.
- **The trial transaction test:** replace it with a behaviour test. Make the `DELETE ... load_outcome` statement raise inside `discard()` and assert the trial's schemas still exist.

---

## A. Absence / retired-behaviour tests

### A-DELETE: one-off migration memorials (38 fn, 42 items)

In each case the thing is gone. A reintroduction would be a deliberate act, not a plausible regression. For removed functions, any caller would also fail loudly with AttributeError or ImportError on first use.

| Test | Asserts |
|---|---|
| `test_arrival_patterns.py::TestTheTransportMatcherIsADifferentThing::test_the_filename_matcher_no_longer_lives_in_delivery` | `delivery._filename_pattern_to_regex` is absent, and `qa_tools.common.file_arrival` does not exist |
| `test_asset_time.py::TestTheTimezoneIsVersioned::test_there_is_no_bare_lookup` | `asset_time.asset_timezone` is absent |
| `test_assignment.py::TestTheRecordSaysWhy::test_there_is_no_ambiguity_left_to_mark` | the record has no "ambiguous" or "ambiguity" key (retired REQ-PIPE-065) |
| `test_assignment.py::TestTheRetiredRulesAreGone::test_the_retired_helpers_no_longer_exist` | 5 retired helper names are absent from assignment and slots |
| `test_backlog.py::TestHowFarProcessingGotIsDerived::test_backlog_no_longer_answers_it` | `backlog.unprocessed` is absent. **This is one of Keith's two named examples.** |
| `test_backlog.py::TestTheStoredMarkerIsGone::test_nothing_reads_or_writes_a_marker` | 5 retired marker names do not appear in backlog.py's source |
| `test_changelog.py::test_the_commit_walk_is_gone` | "git log", "subprocess" and similar do not appear in changelog.py's code |
| `test_cli_common.py::test_report_recorded_no_longer_tells_anyone_to_commit_and_push` | the success message does not contain "commit" or "push" (qa_results/ era) |
| `test_cli_pipeline.py::TestARunOverRecordedHistoryIsRefused::test_regenerate_history_is_retired` | the `regenerate-history` command is absent. This is also asserted in test_history_rekey.py:332. |
| `test_history_rekey.py::TestTheRegenerationCommand::test_no_per_collection_delete_is_left` | `qa_store.delete_history` is absent |
| `test_db_identity.py::TestAnUnmarkedDatabase::test_the_old_database_settings_are_not_an_identity` | `ALTER DATABASE ... SET mothman.*` is not read as an identity. **This is Keith's other named example.** `test_is_refused_and_not_adopted` already covers "unmarked is refused". |
| `test_delivery_hold_retired.py::test_no_delivery_level_kind_remains` | `KINDS == (ASSIGNMENT_RULE,)` and DELIVERY_LEVEL is absent. The same file's three behaviour tests prove that two files raise no hold. |
| `test_delivery_log.py::TestARecordOutlivesItsFiles::test_there_is_no_prune` | `delivery_log.prune` is absent. The living rule is proven by its sibling `test_a_delivery_a_filing_names_cannot_be_deleted`. |
| `test_filing.py::TestAFilingIsRecordedInTheDatabase::test_the_path_cannot_quietly_come_back_into_use` | there is no `filings/` directory and no `filings/` line in .gitignore |
| `test_filing_from_github.py::TestWhoIsAsking::test_there_is_nowhere_to_claim_one` | `Comment` has no `actor` attribute. The security rule is proven by its sibling `test_a_name_typed_in_the_body_is_not_read_as_one`. |
| `test_generate_runs.py::test_no_manifest_entry_carries_a_retired_field` | 9 REQ-GEN-042 field names are absent from the manifest |
| `test_generate_cp_runs.py::test_no_manifest_entry_carries_a_retired_field` | same, for CP |
| `test_resupply.py::test_no_manifest_entry_carries_a_retired_field` | same, at unit level |
| `test_one_arrival_area.py::test_no_module_still_names_a_cp_raw_directory_IN_CODE` | AST sweep of 5 packages: no string literal contains "cp_raw" |
| `test_one_arrival_area.py::test_staging_takes_no_raw_dir_argument` | there is no `raw_dir` parameter on two functions |
| `test_one_arrival_area.py::test_no_module_still_exports_a_retired_constant` (4 items) | CP_RAW_DIR and MANIFEST_PATH are absent from 4 modules |
| `test_one_arrival_area.py::test_the_bdm_loader_has_no_raw_directory_at_all` | RAW_DIR is absent |
| `test_one_arrival_area.py::test_no_module_still_names_a_raw_directory_in_code` | AST sweep: no "data/raw" literal or join |
| `test_one_arrival_area.py::test_nothing_resolves_a_csv_against_a_raw_directory` | `_resolve_csv` and RAW_DIR are absent from 2 modules |
| `test_outstanding.py::TestTheRetiredProducersAreGone::test_none_of_them_remains` | 5 retired producer names are absent |
| `test_outstanding.py::TestTheRetiredProducersAreGone::test_an_item_carries_no_ambiguity_field` | `Item.as_record()` has no "ambiguity" key |
| `test_period_overlay.py::TestARunReadsExactlyOnePeriod::test_nothing_fans_out_any_more` | `period_schema.fan_out` is absent. Its sibling, which raises on a two-dataset arrival, is the behaviour test. |
| `test_recorded_arrival_classification.py::TestTheRetiredDerivations::test_the_arrival_date_derivation_is_gone` | `pipeline.cadence` does not exist, and `agreement.classify_arrival` is absent |
| `test_recorded_arrival_classification.py::TestTheRetiredDerivations::test_the_builders_no_longer_derive_it` | the 2 builders do not import `classify_arrival`. Its own comment admits the import would fail at load anyway. |
| `test_arrival_classification.py::TestItNeverLooksAtTheArrivalDateToPickASlot::test_the_module_does_not_reach_for_the_old_derivation` | "cycle_start" and "classify_arrival(" do not appear in the module source |
| `test_supply_holds.py::TestItIsNoLongerADeadEnd::test_a_hold_can_be_resolved` | `hasattr(supply_holds, "resolve")`. resolve is behaviour-tested in test_supply_hold_store and test_outstanding. |
| `test_supply_holds.py::TestItIsNoLongerADeadEnd::test_the_module_no_longer_claims_to_be_a_dead_end` | the module **docstring** does not contain "sprint 12" |
| `test_supply_holds.py::TestItIsNoLongerADeadEnd::test_it_says_where_a_hold_now_lives` | the module **docstring** contains "qa.hold" |
| `test_ticket_sync.py::test_no_code_or_comment_still_asserts_the_retired_rule` | the source does not contain a retired sentence, and **does** contain the word "RETIRED". This is a test that a comment exists. |
| `test_terminal_routes.py::TestTheHelpSaysWhatTheRoutesNowDo::test_no_stale_default` (2 items) | `--help` output does not mention "auto-pull" |
| `test_staging_loads.py::TestStagingIsSequential::test_build_all_stages_without_fanning_out` | no Pool or Executor in the 2 loaders. The rationale (one DuckDB file, one writer) was retired by REQ-PIPE-087. |
| `test_staging_loads.py::TestStagingIsSequential::test_staging_happens_before_the_tools_fan_out` | **vacuous, see the headline above** |
| `test_staging_loads.py::TestStagingIsSequential::test_one_collection_is_staged_at_a_time` | `_run_bdm` comes before `_run_cp` in run_command's source, with no Executor. The DuckDB rationale is gone. Per-arrival ordering is proven behaviourally in test_arrival_lifecycle. |

### A-REPLACE: the absence is about a still-living rule, so prove it by behaviour (8 fn)

- **`test_arrivals.py::TestNoCommittedResultCarriesBookkeeping::test_every_committed_dataset_stats_file_is_clean`**
  - Asserts no bookkeeping keys in committed qa_results/ (now vacuous).
  - Replace with the same key scan over the recorded dataset_stats rows in the database.
- **`test_one_arrival_area.py::test_the_generator_writes_a_delivery_and_nothing_beside_it`** and **`::test_the_bdm_generator_writes_a_delivery_and_nothing_beside_it`**
  - Asserts by AST that there is no `cp_raw` literal or `to_csv(path)` in the generator, and that `"write_delivery"` is in the source.
  - Replace with one behaviour assertion inside the existing module-scoped `manifest` fixtures in test_generate_runs and test_generate_cp_runs, which already redirect output to tmp. After generation, the redirected root holds only `deliveries/`, `receipts/` and the bookkeeping file.
- **`test_one_arrival_area.py::test_the_drift_check_does_not_fall_back_to_a_file`** and **`::test_the_bdm_drift_check_does_not_fall_back_to_a_file`**
  - Asserts by AST that no except-handler mentions "csv".
  - Replace: make the warehouse read in run_evidently_{cp,bdm} raise, and assert the run raises rather than returning a number.
- **`test_one_arrival_area.py::test_staging_a_single_arrival_does_not_copy_it_first`**
  - Asserts by `getsource(run_single)` that it contains no "RAW_DIR" or "dest_path".
  - Replace by extending the existing behaviour test `test_staging_writes_no_second_copy_of_the_file_it_was_given` (CP) to the BDM single-arrival staging path.
- **`test_recorded_arrival_classification.py::TestTheRetiredDerivations::test_the_template_no_longer_blanks_a_resupplys_verdict`**
  - Asserts two JS strings are absent from the template.
  - Replace with a Vitest test: `buildRealDataset` on a resupply row keeps its own `arrivalStatus` and `arrivedAt`.
- **`test_check_id.py::test_the_grammar_carries_no_table_segment`**
  - Asserts "table" is not in SEGMENT_NAMES and the parsed object has no `table` attribute.
  - Replace with a positive specification: `SEGMENT_NAMES == (<exact tuple>)`. That catches any segment change, not just this one.

### A-TRIM: keep the test, delete only the absence lines (4 fn)

- `test_assignment.py::TestTheRecordSaysWhy::test_the_vocabulary_is_exactly_three_branches`: keep the set equality, drop the `for gone ... not hasattr` loop. The exact-set assertion already proves it.
- `test_cli_bdm.py::test_the_cli_reports_where_the_generator_actually_wrote`: drop the `not hasattr(bdm, "raw_dir")` line.
- `test_history_rekey.py::TestTheRegenerationCommand::test_both_halves_are_mothman_subcommands`: drop the `"regenerate-history" not in` line.
- `test_resupply.py::test_clean_delivery_yields_exactly_one_attempt`: drop the 2 `not hasattr` lines.

### A-KEEP: absence that protects a living rule

These were read and judged living rules:
- **Generator bookkeeping and the data boundary:**
  - `test_arrivals.py::TestTheGeneratorsBookkeepingIsWalledOff`: all 4 tests. This is the "no QA module reads generator bookkeeping" rule.
  - `test_publisher_role.py::TestItCannotReachSupplyRows`: behaviour, against a real role.
  - `test_qa_results_writer.py::test_it_writes_no_files_at_all`: behaviour.
- **CI and credentials:**
  - `test_publish.py::TestGitHubHoldsNoCredentialAndRunsNoBuild`: the 3 no-database, no-secret and no-publish workflow tests. They read workflow configuration, and the rule is live.
- **Identity:**
  - `test_db_identity.py::TestAnUnmarkedDatabase::test_a_connection_string_cannot_claim_an_identity`: a security rule.
- **Tests whose names say "no longer" but which are real behaviour invariances:**
  - `test_build_dashboard_data.py::test_the_suppliers_own_timestamp_no_longer_decides_punctuality`, plus the CP copy in test_build_cp_dashboard_data.py
  - `test_check_bands.py::...::test_notification_id_nulls_no_longer_carry_the_escalation_checks`
  - `test_cli_schedule.py::...::test_a_daily_dataset_no_longer_needs_an_until`
  - `test_arrivals.py::...::test_the_prefix_no_longer_decides_anything`
  - `test_dashboard_e2e.py::...::test_the_pseudo_columns_no_longer_appear_among_the_real_columns`
- **Tests already counted elsewhere:**
  - `test_validate_requirements.py::test_validate_rejects_the_old_legacy_bare_id_format` is a real validator rule. Fold it into the C table.

---

## B. Source-grep tests (product .py or template read as text, AST or getsource)

### B-REPLACE with a behaviour test (31 fn)

Most of these become cheap spy or fake tests. The functions already take injectable collaborators, or are click commands runnable with CliRunner.

| Test | Asserts (text) | Replace with |
|---|---|---|
| `test_publish.py::TestThereIsExactlyOnePublishPath::test_the_command_delegates_rather_than_pushing_for_itself` | `"publish("` in source, `'"push"'` not in source | Monkeypatch `dashboard_cli.publish` to a spy. Invoke `dashboard publish`, `pipeline run --publish` and `common.offer_to_publish()` (tty, answer yes). Assert the spy was called once each. One parametrised test replaces all three. |
| `...::test_pipeline_run_publish_calls_the_same_function` | `"dashboard_cli.publish()"` in source | same as above |
| `...::test_the_wizards_prompt_calls_the_same_function` | `"dashboard_cli.publish()"` in source | same as above |
| `test_publish.py::TestTheGateCannotBeSkipped::test_publish_runs_the_render_check` | `"_check_renders()"` in source | Spy `_check_renders` and `_publish` (and the build step). Call `publish()`. Assert the call order, and that a raising `_check_renders` means `_publish` is never called. Replaces both tests. |
| `...::test_it_runs_the_check_before_it_publishes` | string-index order | same as above |
| `test_publish.py::TestPublishingIsAlwaysAsked::test_the_prompt_defaults_to_not_publishing` | `"default=False"` in source | With tty True, monkeypatch `questionary.confirm` to capture kwargs. Assert `default is False`. |
| `test_publish.py::TestTheArtifactSaysWhereItCameFrom::test_the_embed_fills_it_with_the_environment_and_the_commit` | 3 substrings in `embed()` | Run `embed()` into tmp. Parse `BUILD_PROVENANCE` from the output and assert the environment and commit values. |
| `...::test_absence_of_either_is_tolerated_rather_than_invented` | `"except Exception:"` and `'commit = None'` in source | Same run, with `environments.current_or_none` raising and `current_commit_sha` returning None. Assert nulls, not invented values. |
| `...::test_the_page_renders_both_into_the_build_stamp` | substrings inside `renderBuildStamp` in the template | Vitest: set `BUILD_PROVENANCE`, call `renderBuildStamp()`, assert the rendered text holds the environment and a 7-character sha. |
| `test_publish.py::TestThePublishedContentCannotMixWithTheSource::test_it_uses_a_detached_worktree_rather_than_checking_the_branch_out` | "worktree", "--detach" and "--orphan" in source | `_publish(site, dry_run=True)` in a tmp git repo. Assert the source branch's HEAD and working tree are unchanged, and that `.nojekyll` is in the published tree. Replaces both tests. Moderate cost. |
| `...::test_it_writes_nojekyll` | `".nojekyll"` in source | same as above |
| `test_ticket_reconciler.py::TestTheTicketsOwnBodySaysWhereItIsNow::test_the_body_goes_first` | AST call order `set_body`, `comment` | FakeTickets already exists. Record a call log and assert `set_body` comes before `comment`. |
| `test_ticket_reconciler.py::TestAPersonsOperationGoesThroughTheSamePass::test_every_route_that_records_a_decision_reconciles_the_same_way` | a call string is in `reconcile_after`'s source | Spy `ticket_reconciler.after_runs`/`report`. Call `filing_decisions.reconcile_after(Outcome(changed=True), ...)` and assert the spy was called. |
| `...::test_a_refused_decision_reconciles_nothing` | `"if not outcome.changed:"` in source | Same spy with `changed=False`. Assert it was not called. |
| `...::test_the_pass_covers_every_slot_so_a_new_periods_tickets_appear` | "open_period" in substitute, "states_for" in after_runs | DB behaviour: substitute into a new period, then `after_runs` includes that slot. |
| `test_trial_runs.py::TestATrialLeavesNothingBehind::test_the_tidy_up_is_one_transaction` | the word "transaction" (satisfied by the docstring) | Force a failure mid-`discard()` and assert nothing was dropped (see the headline). |
| `test_cross_table_scope.py::TestTheRebuildPathReadsTheScope::test_both_rebuild_paths_read_the_scope` (2 items) | "read_cross_table_results" is in the rebuild source | With `clean_qa_history`, record one cross-table result, run `build_results_from_history`, assert it is present. **It also requests `deployment_history` without using it,** so a text grep sits in CI's slow half. |
| `test_history_rekey.py::TestOneAgreedOrdering::test_both_orchestrators_and_both_rebuilds_apply_it` | "canonical_order" is in 4 function sources | For the 2 rebuilds: record results out of order, rebuild, assert canonical order. The orchestrator half could stay as an AST call check or go. |
| `test_history_rekey.py::TestCompletenessIsWhatThisDatasetActuallyOwes::test_it_is_derived_from_the_checks_rather_than_configured` | "collect_checks" is in source | Monkeypatch `collect_checks` to add one Evidently check for a dataset. Assert `expected_tools_for` includes evidently. |
| `test_tables_read.py::TestTheGateRefusesAReservedDatasetId::test_the_gate_runs_as_part_of_the_real_hierarchy_validation` | "reserved_name_errors" is in `validate()`'s source | Run `validate_hierarchy.validate()` on a tmp asset file declaring a `_cross-table` dataset. Assert it reports. |
| `test_claim_window_lookahead.py::TestTheSlotStaysVisibleOnceFilled::test_BOTH_call_sites_use_the_lookahead` | "claimable_until" is in 2 sources | One test: file an early supply via `filing.file_arrivals`, then assert `slot_state.states_for` lists the slot. Delete outright if the class's siblings already go through both entry points. |
| `test_atomic_file.py::test_both_results_writers_write_atomically` (2 items) | an `atomic_file.write_json(RESULTS_PATH` substring | Spy `atomic_file.write_json` while running each `build_results_from_history`. Or delete it, since the atomic writer itself is behaviour-tested in the same file. |
| `test_sample_data.py::TestATableNameIsNotADatasetId::test_both_staging_paths_decide_from_the_table` | `ensure_schema_for_table(` in, `ensure_schema_for(` out | Stage through each builder a table whose name differs from its dataset id. Assert the landing schema. |
| `test_stated_environment.py::TestDroppingThingsNeedsTheTypedId::test_discard_sample_asks_through_the_same_confirmation` | `confirm_drop(` in callback source | CliRunner: `supply discard-sample --yes` with no tty is refused, or asks for the typed id. This also covers the duplicate second half of `test_sample_data.py::TestDiscardingIsSomethingAPersonDoes::test_only_the_terminal_calls_discard`. |
| `test_refiling.py::TestItIsLocalToTheSupplyThatMoved::test_it_reads_one_record_rather_than_the_whole_history` | no `filings_of(` and no loop in the body | Count queries, as `test_assignment::TestItDoesNotScanEverySlot` already does ("counted, not grepped"). |
| `test_run_scope.py::test_the_scope_uses_reevaluations_own_plan_and_mark` | `plan`/`mark` attribute calls in the AST | Spy `reevaluation.plan`/`mark`. Call `writer._scope_to_run`. Assert both were used. |
| `test_correction_trial.py::TestTheCalendarEntry::test_the_view_edits_no_configuration` | no `calendar.yaml").write` or `CALENDAR_YAML` in source | Drive `calendar_menu`/`_draft` via CliRunner. Assert the calendar.yaml bytes are unchanged. |
| `test_arrival_classification.py::TestARejectedSupplyIsClassifiedToo::test_classification_cannot_see_whether_a_supply_was_promoted` | "promoted", "rejected" and "status" are not in `classify`'s source | Signature assertion (as `test_assignment::test_assignment_takes_no_supply_contents_at_all` does), or classify the same input before and after a promotion and get the same result. |
| `test_recorded_arrival_classification.py::TestItFollowsAReFile::test_it_is_never_recomputed_from_the_promotion_instant` | AST: no `promoted_at` attributes | Promote at a much later instant, then assert the recorded verdict is unchanged. The sibling `test_the_receipt_instant_does_NOT_move_with_it` does the refile half. |
| `test_recorded_arrival_classification.py::TestTheRealFilingPathRecordsIt::test_every_branch_of_the_rule_carries_the_arrival_instant` | every `Assignment(...)` in `assign()` passes `received_at=` | Drive `assign()` through each of its 3 branches (OPEN_UNFILLED, RESUPPLY, HELD) and assert `received_at`. Its sibling covers only one branch. |
| `test_filing.py::TestAFilingIsRecordedInTheDatabase::test_no_code_path_writes_a_filing_to_disk` | no FILINGS_DIR, `write_text(` or `mkdir(` in filing.py | chdir to tmp, file an arrival, assert no files appear. This is the pattern `test_qa_results_writer::test_it_writes_no_files_at_all` already uses. |

### B-CONSOLIDATE: the living data-boundary rule, implemented 13 ad-hoc ways (13 fn, 14 items)

Rule: "a build or reader may read recorded QA results, never supply rows". Each test below greps one module for a slightly different forbidden word list:
- `test_agreement_drift.py::test_it_reads_recorded_metadata_and_configuration_only`
- `test_assignment.py::TestItReadsNoData::test_the_module_never_touches_the_warehouse`
- `test_correction_trial.py::test_it_reads_configuration_and_recorded_facts_only`
- `test_dashboard_corrections.py::test_it_reads_recorded_facts_and_configuration_only`
- `test_promotion_state.py::TestItReadsRecordsAndNeverSupplyRows::test_it_names_no_schema_that_holds_supply_rows`
- `test_slot_timeline.py::TestItReadsTheLogAndNothingElse::test_it_names_no_schema_that_holds_supply_rows`
- `test_verdict_record.py::TestReJudgement::test_it_reads_recorded_metadata_and_configuration_only`
- `test_outstanding.py::TestItReadsRecordsAndNeverSupplyRows::test_it_reads_no_schema_that_holds_supply_rows`
- `test_outstanding.py::TestItReadsRecordsAndNeverSupplyRows::test_it_reaches_the_database_only_through_the_record_modules`
- `test_period_schema.py::TestACheckIsEvaluatedOnce::test_the_replay_path_re_runs_no_tool_and_opens_no_warehouse` (2 items)
- `test_scenario_map.py::TestTheCommittedMap::test_building_the_map_reads_nothing_under_data_except_the_record`
- `test_sample_data.py::TestWhereTheDataItself_Lands::test_nothing_that_computes_a_period_reads_it`
- `test_recheck.py::TestOnlyFromTheOrchestratorPath::test_no_build_path_imports_the_executor`

Recommendation: KEEP the rule and REPLACE the 13 greps, preferably with one behaviour test. Run the dashboard data build, plus the reader modules on its path, over a connection made as the publisher role, which `test_publisher_role.py` already sets up and proves cannot read staging. Any supply-row read then fails with InsufficientPrivilege, whatever the spelling. That is strictly stronger than any word list, and it catches dynamic SQL.

If that is too heavy, collapse the 13 into one parametrised AST test over (module, forbidden-identifiers) that ignores docstrings. Today's versions disagree on whether prose counts, which the slot_timeline test's own comment complains about.

### B-DELETE (2 fn)

- `test_schedule.py::TestNothingIsComputedFromAHolidayCalendar::test_no_holiday_library_is_imported_by_this_module` asserts there is no `import holidays` or similar in schedule.py. `holidays` and `workalendar` are not dependencies in pyproject.toml, and the sibling `test_the_authored_dates_are_returned_verbatim` is the behaviour proof.
- `test_ticket_reconciler.py::TestItNeverCloses::test_the_service_is_never_asked_to_close` asserts "def close" is not in the reconciler source. The real boundary guard is `test_ticket_github.py::...::test_nothing_here_can_close_or_delete` (kept). The reconciler can only reach GitHub through that adapter, and FakeTickets has no close method, so the behaviour tests would already fail on a call.

### B-TRIM (1 fn)

- `test_postgres_version.py::TestTheServerIsAsserted::test_it_reads_server_version_num_and_never_aurora_version`: keep the behaviour half (`conn.sql == [...]`) and the PROBE assertions. Drop the 2 `inspect.getsource` lines.

### B-KEEP: AST guards that enforce architecture rules, with no cheaper behaviour equivalent

These are allowed, as call-graph, single-writer or lint rules:
- **Single writer or single path:**
  - `test_publish.py::...::test_only_one_function_in_the_cli_pushes_anything`
  - `test_scripted_decisions.py::TestNoBackDoor::test_only_decision_log_inserts_into_the_decision_table`
  - `test_reset_synthetic.py::TestNothingElseDeletes::test_no_other_module_calls_it`
  - `test_db_identity.py::TestMarking::test_nothing_else_writes_an_identity`. Minor issue: its regex still matches `mark_by_admin`, which pass 1 moved to conftest. The alternative is dead and can be dropped.
  - `test_plain_base_names.py::TestOnlyOneCodePathMovesAPeriodTable::test_rename_and_set_schema_are_said_only_there`
  - `test_ticket_reconciler.py::...::test_only_the_pass_and_the_refusal_route_write_to_a_ticket`
  - `test_sample_data.py::...::test_only_the_terminal_calls_discard` (the grep half)
- **Never-calls rules:**
  - `test_cli_filing_tui.py::TestItCallsNoGitHub::test_nothing_in_this_module_imports_a_github_client`
  - `test_promotion_after_run.py::TestTheRunItselfDoesNotPromote::test_the_run_function_calls_no_promotion`
  - `test_ticket_github.py::...::test_nothing_here_can_close_or_delete`
  - `test_filing_from_github.py::TestTheTerminalRouteNeverCallsGitHub::test_the_shared_implementation_does_not_import_this_one`
  - `test_filing_from_github.py::...::test_the_module_never_mentions_reading_one`
- **Wiring and ordering:**
  - `test_connections_close_on_failure.py::TestEveryLongLivedConnectSiteIsGuarded::test_its_close_is_inside_a_finally` (4 items). Its behaviour siblings prove the mechanism, and this checks every site.
  - `test_tools_beside.py::test_each_orchestrator_runs_dbt_beside_the_rest`
  - `test_ticket_reconciler.py::...::test_it_is_called` and `test_it_is_called_AFTER_the_runs`
  - `test_filing_before_checks.py`: the remaining 4 wiring tests (both batches go through the lifecycle, no second composition, file before overlay, BDM files one arrival)
- **Lint on tests or the template:**
  - `test_decision_log.py::TestNoTestAssumesTheNewestEntryIsItsOwn::test_no_test_module_takes_the_last_entry_for_a_dataset` (a lint on test code)
  - `test_display_time.py::TestThereIsOnlyOneOfIt` (2 tests, a one-formatter lint on the template)
  - `test_chain_progress.py::test_no_check_chain_call_site_is_left_without_a_progress_indicator`
- **No alternative available:**
  - `test_cdk_handler_environment.py`: both tests. aws_cdk is not installed, so source is the only thing available.

Configuration-file reads (workflows, hooks, .gitignore, CODEOWNERS, .env.example, pre-commit, people.yaml) were also hit by the scan. They are not product-source greps. Configuration is the thing under test, so KEEP. Examples: `test_publish.py::TestTheWorkflowCarriesEveryVariableThePipelineNeeds` (4) and `TestNeitherHalfOfCIQuietlyStopsCovering` (4), `test_db_identity.py::TestEveryPlaceMarksItsOwn` (3), `test_ci_on_demand`, `test_ci_bootstrap_cache`, `test_no_calendar::test_ci_installs_what_the_rollup_comparison_runs`, `test_tables_read` pre-commit (2), `test_devcontainer`, `test_local_env`.

---

## C. Process-tooling over-testing

Honest framing first: these run in milliseconds (97 validate_requirements tests collect and run in well under a second). Collapsing them into tables buys **fewer functions and less code to maintain, not gate time**. Exact duplicates, tautologies and brittle corpus tests are the real deletions.

### test_validate_requirements.py: 97 items

- **DELETE 8 exact duplicates** (identical input and assertion to a kept test):
  - `test_date_written_is_optional_and_absent_is_fine`, `test_non_functional_requirements_absent_is_fine`, `test_dependencies_absent_is_fine` and `test_omitting_it_entirely_is_still_valid` are all `validate([_valid_entry()]) == []`, the same as `test_validate_returns_empty_list_for_a_fully_valid_requirement`.
  - `test_implemented_by_is_optional_until_a_requirement_is_built` and `test_evidence_is_optional_until_a_requirement_is_built` are byte-identical inputs to `test_validate_allows_not_started_with_no_linked_tests`.
  - `test_a_not_started_requirement_may_still_carry_a_sign_off` is identical to `test_decisions_is_optional_until_a_requirement_is_built`.
  - `TestARetiredRequirement::test_it_keeps_its_history_without_being_refused_for_it` is identical to `TestARetiredRequirement::test_a_retired_requirement_with_its_three_facts_is_valid`.
- **COLLAPSE into 4 tables:**
  1. "One bad field is reported, naming the field": about 38 single-field rejection tests become 1 parametrised test of (overrides, expected substring). These cover id, legacy id, unknown component, title, story, moscow, status, empty acceptance_criteria, built with no linked tests, missing or fake linked test, source missing, empty or blank, date_written blank or non-ISO, non-functional requirements as a string or with empty entries, open_questions, evidence types, dependencies as a string or nonexistent, implemented_by empty, bare .py, missing symbol, non-Python symbol or missing path, evidence or decisions empty or blank, the 4 sign-off rules, not_started or in_progress carrying tests, evidence or code, and built or in_progress unsigned.
  2. "These shapes are valid": about 12 acceptance tests become 1 table.
  3. `_linked_test_exists` / `_python_symbol_exists` resolution: 9 tests become 1 table.
  4. unmet_criteria / blocked_by: about 11 tests become 1 table.
- **Before:** 97 items in about 83 functions. **After:** 89 items in about 20 functions.
- **KEEP as is:** `TestNoHyphenWrapArtifacts` (a real-file lint), the duplicate-ids test (multi-entry) and the retired-block tests not listed above.

### test_sprint_state.py: 49 items

- **DELETE** `TestADeferralIsNotMet::test_counting_requirements_instead_would_have_said_done`. Its "rejected design" check is the tautology `built = all(True for _ in [1])`, and its only real assertion repeats the test above it.
- **DELETE** `TestTheRealFiles::test_the_real_plan_exercises_each_state` (3 items). It depends on the corpus: it goes red the day no sprint is BLOCKED or todo, which is work succeeding. Every branch is already reached by the rule-level fixture tests. **Flag this one to Keith.**
- **DELETE (low value)** `TestBlocked::test_blocked_is_the_only_value_added_to_the_vocabulary`. It restates constants against literals.
- **COLLAPSE** the derivation rules into 1 parametrised (plan spec, register spec) → (met, total, derived) table, covering about 15 tests:
  - `TestTheStatusIsCountedNotTyped` (4)
  - `TestADeferralIsNotMet::test_a_built_requirement_with_deferrals_is_not_complete`
  - `TestBlocked::test_a_sprint_owing_only_deferrals_is_blocked` and `TestBlocked::test_work_of_its_own_outranks_a_deferral`
  - `TestAnUnscopedSprint::test_it_is_todo_rather_than_done` and `TestAnUnscopedSprint::test_an_empty_sprint_is_never_reported_done`
  - `TestWhatCountsAsBlocked` (3)
  - `TestRetiredCountsForNothing` (2)
  - `TestSharedOwnership::test_a_shared_criterion_is_counted_once`
- **Before:** 49 items in 47 functions. **After:** 44 items in about 30 functions.

### Smaller collapses

- **test_plans_md.py (19 items).** 7 text-joining tests become 1 table of (input markdown, expected body), with no cases dropped: wrapped paragraph, paragraph breaks, bullet list, numbered list, wrapped numbered item, hyphen rejoin and real dash. That gives 19 items in 13 functions.
- **test_validate_premise.py (16 items).** The 5 `TestItDoesNotFireOnHistory` "this scan returns []" variants (AMENDED, "used to", a line that FORBIDS it, a negation on the line before, the plans dir) become 1 table. That gives 16 items in 12 functions.
- **DELETE `test_replacement_setting.py::TestTheRequirementsItAmends::test_both_name_the_exception`.** It asserts that requirements.yaml's prose for REQ-PIPE-075 criterion index 3 and REQ-PIPE-065 criterion index 8 mentions "REQ-PIPE-123". It tests the register's wording by position, so it breaks on any renumbering and proves no behaviour.

Totals for C: 12 functions (14 items) deleted. About 75 functions become about 12 parametrised functions, with all cases kept.

---

## D. Redundant pairs: the same thing proven twice

| Delete | Because it is already proven by |
|---|---|
| `test_filing_before_checks.py::TestTheFilingCallComesBeforeTheToolRuns::test_the_lifecycle_files_before_it_checks` (AST call order) | `test_arrival_lifecycle.py::TestOneArrivalAtATime::test_each_arrival_is_filed_checked_and_gated_before_the_next`, which drives `process_all` with recording steps |
| `test_filing_before_checks.py::TestFilingIsInterleavedRatherThanDoneUpFront::test_the_lifecycle_processes_one_arrival_at_a_time` (getsource, no "Pool") | the same behaviour test |
| `test_qa_results_writer.py::test_the_writer_imports_no_filesystem_machinery` (import list) | `test_qa_results_writer.py::test_it_writes_no_files_at_all` (behaviour, in the same file) |
| `test_supply_hold_store.py::TestAHoldIsRecorded::test_the_retired_delivery_level_kind_is_refused` | the same file, line 69: an unknown kind ("whatever") is refused by the same code path |
| `test_processing_pass.py::TestTheCommandGeneratesNothing::test_no_generator_is_imported` | `test_arrivals.py::TestTheGeneratorsBookkeepingIsWalledOff::test_no_pipeline_module_imports_the_generator_package`. processing_pass.py is under qa_tools/, which that test walls off. |
| `test_chain_progress.py::test_flag_mode_and_interactive_mode_both_show_progress` | `test_chain_progress.py::test_no_check_chain_call_site_is_left_without_a_progress_indicator`, which already checks every `run_check*` call site in both files, `qa_command` included |
| `test_plain_base_names.py::TestOnlyOneCodePathMovesAPeriodTable::test_no_other_move_takes_a_period_schema` (AST) | `...::test_and_a_bare_move_into_a_period_is_refused_at_run_time` (behaviour, in the same class) |
| `test_lambda_handlers.py::TestTheHandlerOnlyRecordsThenRunsThePass::test_neither_handler_calls_the_single_run_entry_point` (text grep) | `test_run_single_is_for_trials.py` (run_single refuses any non-trial id) together with the handler behaviour tests in the same file |
| `test_decision_log.py::TestNoDatabaseMeansNoDecision::test_the_module_has_no_spool_path_at_all` ("open(" and "Path(" not in source) | its sibling in the same class, which redirects HOME and cwd and asserts a refused decision leaves no file |
| `test_evidently_check_lifecycle_retired.py::test_bdm_retired_evidently_checks_is_currently_empty` and `::test_cp_...` | They assert the retired registries are `{}`, so they fail the first time a check is legitimately retired. The files' shape is exercised by `validate_check_lifecycle`, which reads them. |
| (already in A) `test_cli_pipeline.py::...::test_regenerate_history_is_retired` | `test_history_rekey.py:332` |

There is also one D-REPLACE: the e2e floor guard in `TestStatusMatchesEachToolsOwnVerdict` (see the headline).

Totals for D: 11 functions deleted and 1 replaced.

---

## Totals

| Category | DELETE | REPLACE | TRIM | CONSOLIDATE | KEEP (read, reasoned) |
|---|---|---|---|---|---|
| A absence/retired | 38 fn (42 items) | 8 | 4 | - | about 11 |
| B source-grep | 2 | 31 | 1 | 13 (14 items) → 1 test | about 25 architecture guards, plus config reads |
| C process tooling | 12 fn (14 items) | - | - | about 75 fn → about 12 tables | the rest |
| D redundant | 11 | 1 | - | - | - |
| **Total** | **63 fn (about 69 items)** | **40** | **5** | **13 greps → 1 behaviour test** | |

Net effect if all of it is accepted:
- About 69 items are deleted outright.
- About 40 weak tests become behaviour tests, roughly one for one. A few merge: the 3 publish-path tests become 1, and the 2 gate tests become 1.
- The 13 data-boundary greps become 1 publisher-role behaviour test.
- About 75 process-tooling functions become about 12 tables.

Gate-time saving is small; this pass is about strength, not speed. The exception is the cross-table grep, which drags `deployment_history` into the slow CI half.

## Side findings, not tests

- **Stale module docstrings.** orchestrate_bdm.py:20-28 and orchestrate_cp.py:12-18 still describe `data/raw/`, `data/cp_raw/`, `data/duckdb_runs/` and `build_all()`, all retired. That stale prose is exactly what made TestStagingIsSequential pass.
- **`test_plain_base_names.py` has an empty `class TestTheStampedNameComesFromTheLog`** with only a docstring. It is dead scaffolding.
- **`test_db_identity.py::TestMarking::test_nothing_else_writes_an_identity`** keeps a regex alternative for `mark_by_admin`, which pass 1 moved into tests/conftest.py.
