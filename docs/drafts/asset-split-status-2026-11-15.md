# Asset split - build status audit, 2026-11-15 (read-only)

**Asset-split requirements audit (read only, nothing edited or run)**

The batch has 31 requirements whose source is the split (requirements.yaml:47727-48839). All are marked `not_started`. In practice about 6 are fully built, about 12 are partly built and about 13 are not started.

The requirements' own `decisions:` entries already record much of what was built ("WHAT LANDED", "C6/C7/C12/C13 BUILT", "NOT YET DONE"). I checked those claims against the code below. Where I could only see the prose and not the code or the test, I say so.

## Verdict table

| Req | Verdict | Met/total | Key evidence |
|---|---|---|---|
| PIPE-342 | partly | 7/10 (2 partly, 1 not met) | Move commit de009e91. Resolver in `qa_tools/common/assets.py:101-198`, state paths at call time `:451-472`. Assets found by listing the folder, `_Assets.names()` `:154`. Configuration-only reader of every asset: `qa_tools/common/every_asset.py`. CODEOWNERS lines 12-14 now `/assets/*/...`. Test fixture: `tests/asset_folders.py`. Tests: `tests/test_assets.py::TestTheRealLayout`, `::TestTheFixture`, `tests/test_every_asset.py`, `tests/test_state_paths_at_call_time.py` |
| PIPE-363 | built | 10/10 | `cli/app.py:54-55` builds no command groups with no asset set. "Commands for asset" line `:260`. "Set MOTHMAN_ASSET to one of" `:361-364`. Refusal text `assets.py:315-323`. Asset named beside the environment `cli/common.py:105`, `cli/env.py:73`. `tests/conftest.py:270,1433` refuses a test module with no asset mark. Tests: every test in `tests/test_cli_asset_selection.py` (`TestWithNoAssetSet`, `TestAnotherAssetsCollection`, `TestTheAssetIsNamed`). "Seen failing first" not confirmed |
| PIPE-364 | partly | 2/6 (2 partly, 2 not met) | `cli/check.py:191-203` runs each asset-reading gate once per asset folder. The check-id asset segment is checked per asset. No gate for files at the top of assets/. No tests against a two-asset fixture repository |
| PIPE-365 | partly | 2/5 (2 partly, 1 not met) | `Asset.data`/`reports` = data/<asset>, reports/<asset> (`assets.py:183-185`). `.gitignore:37` covers `reports/*/`. `REPLAY_INPUTS` leaves providers out (`replay_inputs.py:56-57`). `KEY_PREFIX` is `bootstrap-v3-` (`:61`) |
| QAC-368 | built (1 not confirmed) | 9/10 | Projects named `mothman_<asset>`. macro-paths/test-paths point at dbt_shared (`assets/*/dbt/dbt_project.yml:9,23-24`). `mothman env dbt-deps` runs in the session hook, `.devcontainer/post-create.sh:16` and test.yml:260,384,510. Pre-run refusal `assets.dbt_project_ready()` `:477`. Tests: `tests/test_dbt_packages_per_asset.py` (`TestInstalling`, `TestInstalledIsDecidedByDbtsOwnLock`, `TestARunWithoutThemIsRefused`, `TestEachAssetsProject`, `TestTheParseCacheSeesTheSharedFolder`). Criterion 9's changelog-gate half is not confirmed. The quarterly project has no `retired/` folder |
| PIPE-369 | partly (nearly built) | 7/8 | Adapters are loaded by path (`assets.py:505-570`). No `__init__.py` under assets/. Adapter-import gate `validate_collections.py:129`. Tests: `test_assets.py::TestLoadingByPath` (by path, id pattern, two assets with the same module name, spawned process), `::TestTheBootstrapHandsItsStreamsTheAsset`, `tests/test_adapter_imports.py::TestTheGate` |
| GEN-370 | partly | 2/9 (2 partly, 5 not met) | Providers in `assets/*/synthetic/collections/`, loaded by path (`test_assets.py::test_a_provider_is_loaded_from_its_assets_folder`). The providers gate runs per asset |
| GEN-371 | not started | 0/6 | No `eras.yaml` anywhere |
| PIPE-343 | partly | 5/8 (3 partly) | Identity guard (`db_identity.py:106` takes the selected asset's id). One asset per process (`assets.py:585-610`, `OneAssetPerProcess`). Databases named `supply_${asset}` (session hook :130-139, test.yml:237-260). Tests: `tests/test_db_identity.py::test_another_data_asset_is_refused`, `test_assets.py::TestOneAssetPerProcess`, `::TestTheConnectionGuard` |
| QAC-344 | partly | 6/8 | data_asset_id is `quarterly` / `daily` (`assets/*/data-asset.yaml:34`). Check ids carry it, e.g. `quarterly.child-protection-family-support...`. Rename transform `check_lifecycle.py:945 migrate_moved_check_id`, which reads the move map. Tests: `tests/test_moved_paths.py::TestTheRenameIsExcusedAndNothingElse` (4 tests). The unchanged-config_hash claim (378/378) is prose only |
| TEST-366 | partly | 6/8 | The move map, 4ff1be88. `qa_tools/common/moved_paths.py`. Tests in `tests/test_moved_paths.py`: `TestTheMapAppliesOnlyToThePushCarryingTheMove`, `TestTheLifecycleGateFollowsTheMove`, `TestTheSettingFreezeFollowsTheMove`, `TestThePeopleFileAtTheBaseFollowsTheMove`, `TestTheAddedOnWalkFollowsTheMove`, `TestCorrectionTrialReadsTheBaseThroughTheMove` |
| PIPE-345 | mostly not started | 1/8 | Only criterion 8 is met: `tests/test_calendar_move_pin.py`; the pin was last changed in fbfcecfc, before the split |
| PIPE-346 | not started | 0/7 | No weekday vocabulary in schedule.py or validate_schedule.py |
| DASH-347 | not started | 0/4 | (see Surprises) |
| QAC-348, GEN-349 (Cancer) | not started | 0/6, 0/5 | No cancer collection, adapter, provider or dbt folder under `assets/quarterly/` |
| QAC-350, GEN-351 (Mental Health) | not started | 0/6, 0/5 | No `assets/daily/department-of-health/`, adapter or provider |
| PIPE-352 | partly | 3/6 (2 partly, 1 not met) | Bootstrap runs per selected asset. Criterion 3: `scenario_map.map_path()` gives SCENARIOS-<asset>.md, and `mixed_asset_problems()` refuses a mixed scenario; test `tests/test_scenario_map.py::TestEachAssetHasItsOwnMap`. Criterion 2 is met in effect: `bootstrap.streams()` still groups by shared calendar (A12 not applied), but each asset has one calendar, so one stream |
| TEST-353 | partly | 2/9 | Build steps run once per asset (test.yml:574-579). dbt-deps once per asset in all three jobs |
| PIPE-372 | not started | 0/6 | No `publish_to_gh_pages` anywhere |
| DASH-373 | not started | 0/7 (criterion 2 trivially true) | `dashboard/snapshots/` still holds all 8 pre-split `.html.gz` files plus manifest.json. `SNAPSHOTS_DIR` is still not per asset (`dashboard/snapshot_dashboard.py:96`). No `snapshots_from`. The old "No snapshots yet" text is still at template:11333 |
| PIPE-354 (Cloudflare) | not started | 0/12 | No Pages, wrangler, `moved_to` or display-name keys in data-asset.yaml. Criterion 1 holds only because build-data already runs per asset |
| DASH-355, DASH-356 (period control) | not started | 0/11, 0/10 | No "For period" or "Period: all current" anywhere |
| DASH-367 | not started | 0/7 | The old period route is still live (template:5936) |
| TEST-357 | partly | 3/4 live (criteria 2 and 3 retired 2026-11-14) | c1: from-empty bootstrap per asset (fbe3359b, morning-reports.md:3269). c4: pins kept (see Surprises). c5: one move commit, de009e91. The retired c2 was built in bd9e004c (`tests/test_equivalence_assets.py`) |
| DOCS-358 | not started (partly on c3) | 0/4 | No "AMENDED ... by" marker from any of these requirements. A21 and the other amendments are still only in decisions |

## Unmet criteria in the partly-built requirements

- **PIPE-342 c2 (partly):** `assets/moved-paths.yaml` is still at the top of assets/ long after the next push.
- **PIPE-342 c4 (partly):** no agency is in both assets yet, and nothing tests that case.
- **PIPE-342 c10 (not met):** there is no shared-tree gate. `validate_collections.EXEMPT_DIRS` (:42-47) still exempts `contract`, `qa_tools/collections` and `generator/collections`.
- **PIPE-364 c1 (partly):** failures are not prefixed with the asset name (not confirmed).
- **PIPE-364 c3, c4 (partly):** these hold only because each gate reads one asset's hierarchy. No message names the asset.
- **PIPE-364 c5 (not met):** no gate refuses a stray file at the top of assets/. A folder with no data-asset.yaml is skipped, not failed (`test_every_asset.py::test_a_folder_with_no_data_asset_yaml_is_passed_over`).
- **PIPE-364 c6 (not met):** no two-asset fixture tests of each refusal, and no test of both assets reusing a collection id.
- **PIPE-365 c2 (partly):** checkpoints are per database (so per asset in effect) but have no per-asset test.
- **PIPE-365 c3 (partly):** `cache_key()` hashes `assets/**`, every asset, not the selected one (`replay_inputs.py:47-48`, `cli/pipeline.py:411-419`).
- **PIPE-365 c5 (not met):** no test runs one asset beside the other's populated folder and compares it byte for byte.
- **PIPE-369 c6 (not met):** coverage `source` in pyproject.toml:175 leaves out assets and has no `include_namespace_packages`. CI has no `--cov=assets` (test.yml:304, 589).
- **GEN-370 c1 (partly):** eras.yaml is missing.
- **GEN-370 c3 (not met):** no test that staging, checks or the dashboard read nothing under synthetic/.
- **GEN-370 c4 (not met):** `generator/daily_batch.py` and every `apply_*_presets` (`generator/dirty.py:379-692`) are still in shared code.
- **GEN-370 c5 (not met):** no provider-import gate in `generator/validate_providers.py`.
- **GEN-370 c6 (not met):** `synthetic_data_generator/generate.py:73-78` still applies Birth Registrations' and Child Protection's presets together.
- **GEN-370 c8, c9 (not met / partly):** no test with the synthetic/ folder removed. Of criterion 9's tests, only the load-by-path one exists.
- **PIPE-343 c1 (partly):** `mothman env mark --confirm` takes only the environment id, not the asset id (`cli/env.py:147-168`).
- **PIPE-343 c4 (partly):** `.devcontainer/post-create.sh` marks one database with no MOTHMAN_ASSET set, which the asset rule would refuse.
- **PIPE-343 c8 (partly):** the only wrong-asset test monkeypatches `data_asset_id`. It does not point each asset at the other's real database on every route.
- **QAC-344 c6 (not met):** the transform and the move map have not been deleted.
- **QAC-344 c8 (not met):** Keith's approval of the rename exception is not recorded.
- **TEST-366 c3, c4 (not met):** the map, its reader and the id transform are still present, and there is no one-off check. Later CI pushes include f6bc05bf, 741a1d87 and 9ea7e138.
- **PIPE-352 c4 (partly):** the hook's staged-table count queries database `supply`, not each `supply_<asset>` (session-start.sh:148).
- **PIPE-352 c5 (partly):** daily took 11m24s, quarterly 111m09s, against the 12-minute budget (morning-reports.md:3269; post-build-review #318).
- **PIPE-352 c6 (not confirmed):** no side-by-side figures found.
- **TEST-353 c1 (not met):** one cache key and one cache cover both assets.
- **TEST-353 c2 (partly):** bootstraps run one after the other in a for-loop, not side by side.
- **TEST-353 c4 (built differently):** one pytest session per asset (`--only-asset`), not one session for both.
- **TEST-353 c5 (partly):** one restored/rebuilt line for the whole job, not per asset.
- **TEST-353 c6 (not confirmed):** fast-half skip count.
- **TEST-353 c7, c9 (not met):** no ci-usage evidence; no `--cov=assets`.
- **PIPE-345 c1, c4 (partly):** each asset happens to hold one calendar; there is no "at most one" rule. Participation is the pre-split mechanism.
- **PIPE-345 c2, c3 (not met):** collections still declare `calendar:` (`assets/daily/calendar.yaml:157`; `assets/quarterly/calendar.yaml:266,310,351`), and there is no refusal.
- **PIPE-345 c5 (not confirmed).**
- **PIPE-345 c6 (not met):** the calendar-name tests remain at `generator/scenario_injection.py:1419` (`== "daily"`) and `assets/quarterly/synthetic/collections/child_protection.py:736,738` (`"quarterly"`).
- **PIPE-345 c7 (not met):** no gate test.
- **TEST-357 c6 (not met):** after C11, 12 tests that passed at the base fail (requirements.yaml:48755). Whether they pass today is not confirmed.
- **DOCS-358 c1, c2 (not met):** amendments A1-A43 and C1 are not applied, and the blanket sweep is not done. CLAUDE.md:310-316 still describe `contract/` and `dbt_project/`.
- **DOCS-358 c3 (partly):** only the dbt-deps lines in CLAUDE.md and README (113d9f35) and the README tour (3d34ffa0) were updated. `.env.example` has no `MOTHMAN_ASSET=` line.
- **DOCS-358 c4 (not met):** #131 and the others are still in plans.

## Surprises

1. **Status is stale.** PIPE-363 and QAC-368 are fully built and PIPE-369 is one criterion short, yet all are `not_started`. The decisions hold "WHAT LANDED / BUILT" notes rather than flipping the status.
2. **The move map has outlived its own rule.** Keith said "I don't want moved paths hanging around", and TEST-366 c3 requires deletion in the next push. The map and the id transform are still live after many pushes, which also keeps QAC-344 c6 open. They should not fire, because `moved_paths` only applies where the push's base has no assets/.
3. **Calendar names still in shared code.** The calendar-name checks PIPE-345 c6 says to remove are still there, so the "names no asset" rule only passes because the calendars happen to share the assets' names.
4. **CI is built differently from TEST-353.** One cache key covers both assets, so a daily-only edit invalidates both. Bootstraps run one after another, and deployment tests run one session per asset, not one session for both.
5. **Golden fixture extended.** `tests/fixtures/arrival_semantics_golden.json` grew by 404 lines in c5d01de5 (geocoding datasets added, no existing lines changed). That is not quite TEST-357 c4's "kept as captured".
6. **Stale exemptions.** `validate_collections.EXEMPT_DIRS` still lists the retired `contract`, `qa_tools/collections` and `generator/collections`, not A18's `assets/` and `aws/`.
7. **Two setup scripts still point at the old single database.** The session hook's staged-table count reads database `supply`, and the dev container marks one database with no asset set.
8. **"Weekly (<weekday>)" label already exists.** It is at template:1859, but it predates the split and comes from cadence, not weekday participation, so it does not meet DASH-347.
9. **Requirement with no matching code.** The checks for a dataset mixing linked and unlinked datasets (DASH-356 c6) and for a stray file at the top of assets/ (PIPE-364 c5) are not implemented anywhere.

**Not confirmed:**
- every "seen failing first" claim;
- the gates passing on the move push with the map, and the 378/378 config_hash comparison (prose only);
- TEST-353 c6;
- PIPE-365 c2's per-asset behaviour beyond checkpoints being per database;
- QAC-368 c9's changelog-gate half;
- whether the suite passes today.
