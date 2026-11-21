# Item 6 groundwork: generalising the per-collection code

Research for `plans/publishing-and-history.md` #6, 2026-10-15 night, done by a
read-only research agent at Keith's request and saved here by the main session.
Keith's definition of done: **a small adapter per collection** - shared per-tool
code, plus one short module per collection for whatever genuinely differs.

## Headline findings

- **Very little of the copied code is genuinely collection-specific.** Across 14
  Birth Registrations (bdm) / Child Protection (cp) module pairs: ~2,200 bdm and
  ~2,640 cp code lines (comments and docstrings excluded). About 77% is the same
  shape with collection constants. Only ~16% of bdm and ~7% of cp is truly
  specific, and almost all of that is in the generator.
- **Outside the generator, cp's copy is a strict superset of bdm's**: the same
  code generalised from 1 table to N, plus multi-table and cross-table logic.
  `plans/qa-pipeline.md` #84's 2026-09 finding ("the per-dataset logic is
  genuinely different") no longer holds for the tool runners. The shared modules
  should start from cp's code.
- **The copies have drifted**, so a naive merge would change bdm's recorded
  output - the main risk to a byte-identical migration (list below).
- **All eight of item 6's 2026-09-20 questions, and its three "real questions",
  are settled** by built requirements (table below). None blocks the design.
- **~45 collection-dispatch sites in 27 files**, against the architect's ~20 in
  ~14. Most are silent omission or silent fallback to Child Protection; one
  fails at import, two at runtime, five refuse explicitly.
- **The generator already has the adapter pattern**: `generator/resupply.py`'s
  `DatasetProvider` Protocol plus `run_slot_chain`.

## 1. Duplication inventory (`plans/qa-pipeline.md` #84's method)

AST-parsed, code lines only, collection tokens normalised, every pair diffed in
full and read by hand. Classes: (a) identical; (b) same shape with constants
[constants in brackets = adapter content]; (b-gen) generic multi/cross-table
logic only cp has; (c) genuinely specific.

| Pair | bdm / cp | (a) | (b) [constants] | (b-gen) | (c) |
|---|---|---|---|---|---|
| orchestrate_bdm / orchestrate_cp | 260 / 310 | 42 / 42 | 218 / 227 [~6/~6] | 41 | 0 / 0 |
| run_dbt_* | 194 / 212 | 16 / 16 | 178 / 196 [~30/~25] | 0 | 0 / 0 |
| run_soda_* | 138 / 134 | 0 | 132 / 128 [~30/~10] | 0 | ~6 / ~6 |
| run_datacontract_* | 103 / 112 | 0 | 103 / 106 [~6/~3] | 6 | 0 |
| run_evidently_* | 135 / 170 | 0 | 90 / 105 [~10/~10] | 65 | 45 / 0 |
| per-run warehouse builders | 90 / 112 | 0 | 90 / 91 [~4/~4] | 21 | ~2 |
| build_results_from_history | 58 / 63 | 0 | 58 / 63 | 0 | 0 |
| dataset_stats | 88 / 92 | 5 / 2 | 83 / 90 [~28/~30] | 0 | 0 |
| evidently_check_lifecycle (+retired) | 36 / 48 | 2 / 2 | 34 / 46 (all data) | 0 | 0 |
| bdm_common / cp_common | 10 / 31 | 10 / 7 | 0 / 24 (data) | 0 | 0 |
| pipeline dashboard-data builders | 273 / 391 | 11 / 11 | 262 / 344 [~20/~90] | 36 | 0 |
| generator generate_runs / generate_cp_runs | 451 / 400 | 17 / 17 | 178 / 195 [~20/~20] | 0 | 256 / 188 |
| cli/bdm / cli/cp | 361 / 562 | 50 / 51 | 273 / 325 [~10/~10] | 186 | 38 / 0 |
| **Total** | **~2,200 / ~2,640** | **153 / 148** | **1,699 / 1,940 [~180/~260]** | **0 / 355** | **345 / 194** |

**Drift** (each a place where merging changes recorded output): bdm lacks
`left_out.note`, dbt's built-model guard, the `skipped` status case and
`unrunnable` results; bdm's dashboard drops empty pseudo-columns and has a
reference-reason fallback for `not_evaluated`; recorded shapes differ -
dataset_stats (`row_count` vs `row_counts`; aggregates keyed `"sex"` vs
`"table.col"`; zeros kept vs dropped), results JSON (`"dataset"` vs
`"collection"`+`"datasets"`), dashboard JSON (one object vs `{"datasets": [...]}`),
and bdm's Evidently raw output carries a `row_count` snapshot.

**Hidden coupling**: `pipeline/build_cp_dashboard_data.py` imports and mutates
the bdm module's `COLUMN_SCOPE_KEY`; `qa_tools/cp/dataset_stats.py` imports
`qa_tools.bdm.dataset_stats`; `cli/common.py` imports `RUN_STEPS` from
`orchestrate_bdm`. Tests: 92 files touch per-collection modules, 36 monkeypatch
per-collection attributes - migration cost, not design input.

## 2. Collection-dispatch sites (effect when a third collection is added)

| # | Site | Effect |
|---|---|---|
| 1 | `qa_tools/common/github_links.py` `AGENCY_QA_FOLDER` | Import-time KeyError |
| 2 | `processing_pass.py` `COLLECTIONS` | Silent omission: arrivals never processed |
| 3 | `recheck.py` map | Runtime KeyError |
| 4 | `checkpoints.py` | Runtime StopIteration |
| 5 | `bootstrap.py` names/generate, `_TARGET_DATASETS`, `_LABEL`, confirm-rebuild | Silent omission |
| 6 | `bootstrap.py` `_run_collection`, `_rebuild_results` (if bdm / else) | Silent fallback to cp |
| 7 | `validate_check_lifecycle.py` `_YAML_SOURCES`/`_EVIDENTLY_SOURCES` | Silent omission: zero active checks, gates blind |
| 8-11 | `tables_read.py`, `soda_common.py`, `check_bands.py`, `check_lifecycle.py` CONTRACTS | Silent omission |
| 12 | `ticket_sync.py` | Silent omission: no tickets |
| 13 | `cli/app.py` two-item menus, `else cp` | Omission plus fallback |
| 14 | `cli/pipeline.py` `_run_bdm`/`_run_cp`, `click.Choice` x3 | Refusal; `all` omits |
| 15 | `cli/debug.py` five `click.Choice` plus if/else, report list | Refusal; omission |
| 16 | `cli/supply.py` `_SHORT_COLLECTION`, `known` | Explicit refusal |
| 17-18 | `cli/dashboard.py`, `embed_dashboard_data.py` `TARGETS` | Silent omission |
| 19 | dashboard template consts, `buildBirthRegistrations`/`buildChildProtectionDatasets`, `datasetTile` | Renders as "no data": omission dressed as no-data |
| 20 | `snapshot_dashboard.py`, `check_dashboard_renders.py` | Omission |
| 21 | `generator/output.py` `generated_into` | Omission |
| 22 | `scenario_injection.generated_periods` | Explicit refusal (correct) |
| 23-24 | `generator/targeting.py`, `generator/targets.py` | Silent fallback (non-bdm treated as cp) |
| 25 | `orchestrate_cp._claim_window` default `"cp-clients"` | Internal fallback |
| 26 | run-id prefixes `run_`/`cp_run_` in ~20 calls | Each collection needs its own |
| 27 | cross-module imports above | Coupling |
| 28 | `aws/cdk/data_pipeline_stack.py`, `aws/lambda_handlers/{bdm,cp}_ingest_handler.py` | Omission |
| 29 | hierarchy literals in per-collection modules (REQ-QAC-039 c1, ~70 occurrences) | Restatement |
| 30 | `bootstrap.py` `collection == "all"` (REQ-PIPE-170 c31) | Works if "all" = every collection |

Already derived from the hierarchy (correct): `hierarchy.py`,
`ticket_sync.DATASET_SCOPE`, embed `CHANGELOG_SOURCES`, the template's
`HIERARCHY` tree, `scenario_injection`'s refusal.

## 3. Item 6's old questions: all settled

| Question | Settled by |
|---|---|
| Q1 check_ids and a collection segment | REQ-QAC-039 c5, c6, c8 (c1 unmet: 17 literals - this work closes it) |
| Q2 "these six arrived together" | REQ-PIPE-034 c7-8; REQ-PIPE-036; REQ-PIPE-105 |
| Q3 historical re-evaluation | REQ-PIPE-035 c11 |
| Q4 when cross-table checks re-run | REQ-QAC-037 c4; REQ-PIPE-036 c8-9; REQ-PIPE-121 |
| Q5 timestamps on rebuilt history | REQ-PIPE-038 c4; REQ-PIPE-144; REQ-PIPE-081 c27-31 (regenerated, replay clock) |
| Q6 a check whose other side never arrived | REQ-PIPE-035 c6; REQ-QAC-037 c7 |
| Q7 superseded table versions | REQ-PIPE-035 c4; REQ-PIPE-118 |
| Q8 how far the warehouse spans | REQ-PIPE-035 c5 |
| "current good version" | REQ-PIPE-034 c2-3; REQ-DASH-041 c3; REQ-DASH-056 |
| cross-table result depending on two versions | REQ-PIPE-036 c10-11; REQ-QAC-037; REQ-PIPE-038 c2 |
| what a "run" means | REQ-PIPE-105; REQ-PIPE-036 c1; REQ-DASH-041 c1 (residual: trial/hand runs still carry N tables) |

## 4. Recommended shape

- **Shared per-tool modules** built from cp's code (a new package, e.g.
  `qa_tools/tools/`): `run_dbt`, `run_soda`, `run_datacontract`,
  `run_evidently`, `stage`, `dataset_stats`, `build_results_from_history`,
  `orchestrate`; `pipeline/build_dashboard_data.py`; `cli/collection.py`'s
  `make_group(c)`; `generator/driver.py` for the shared slot loop.
- **A collection registry** (`qa_tools/common/collections.py`) derived from
  `contract/data-asset.yaml`'s hierarchy, never hand-listed, with explicit new
  keys `short` and `run_prefix`, refusing an unknown collection by name.
- **One adapter module per collection** (`qa_tools/collections/<id>.py`)
  implementing a `CollectionAdapter` Protocol: sample keys, business rules,
  check presentation, Evidently checks and PSI columns, aggregate spec, value
  count column, provider and delivery-format strings, column/table meta, the
  generator provider and period plan, optional target-trial support, and
  temporary `legacy` flags for drift.
- **Estimated adapter sizes**: bdm ~230 QA/dashboard lines (~100 if check
  presentation moves into the check files) plus ~280 generator; cp ~260 (~120)
  plus ~210; an Emergency Department adapter ~60 plus ~100 - against ~2,200
  code lines for a copy.
- **Dashboard**: `REAL_BIRTH_REG_DATA`/`REAL_CP_DATA` become one
  `COLLECTION_DATA` keyed by collection id.
- **Gate** in `validate_hierarchy.validate()`: every collection has an adapter
  and vice versa; `short`/`run_prefix` unique; contract files exist; calendar
  membership; adapter table keys belong to the collection; a literal gate (no
  hierarchy id or run prefix as a literal outside contract/, the adapters and
  the scenario register).
- **Migration in 12 byte-identical steps**, each checked by bootstrapping into a
  fresh database and comparing against a HEAD baseline (extending
  `tests/equiv_support.py` to deliveries, receipts, `raw_output` and the
  results/dashboard JSON): 0 harness; 1 registry and gate, rewiring every
  dispatch site to existing modules; 2 check-source lists; 3 the four tool
  runners; 4 staging; 5 stats and results; 6 orchestrator; 7 Python dashboard
  builder; 8 dashboard consts; 9 CLI group factory; 10 generator driver;
  11 retire each legacy flag as its own small output-changing change.

## 5. The researcher's open questions

1. Preserve drift behind legacy flags first, then retire each - recommended.
2. Unify recorded shapes on cp's N-table forms once flags retire - recommended.
3. Move per-check presentation metadata into the check files - recommended.
4. Move Evidently check definitions to `contract/<stem>-evidently-checks.yml` - recommended.
5. Declare `short`/`run_prefix` explicitly in data-asset.yaml - recommended.
6. Shared generator driver, providers and plans per collection, last - recommended.
7. Target trial as an optional adapter capability; refuse instead of fallback - recommended.
8. AWS handlers/CDK: parametrise later or scope out explicitly.
9. Soft ~150-line budget for an adapter's QA/dashboard part, reported not enforced.
10. REQ-PIPE-170 c31 "both" -> "every collection" (needs Keith's wording).
11. Byte-identity includes `raw_output`, volatile keys normalised - recommended.
