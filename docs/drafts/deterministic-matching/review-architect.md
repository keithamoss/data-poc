# delivery-architect on REQ-PIPE-279 draft (2026-10-22)

(Returned as a report - the agent has no write tool - and saved here by the main session; condensed, every finding kept.)

Verdict: the core is right - record at run time which supply each check read, take the delivery from `qa.filing` (no new column; held supplies have a filing row with `slot` NULL, `delivery` NOT NULL), placement a lookup. Four blockers, each leaving a guess or an undefined key.

## Blocking

**B1. The run sequence is drawn in the wrong place, and freezing it is wrong once a run is re-resolved (c4).** Runs are registered in three places: `qa_store.register_run_if_absent` (file checks at staging, `file_checks.py:411`), `record_run` (every tool write, `qa_results_writer.py:604`), `open_run` (`orchestrate.py:127`). A DEFAULT on INSERT records the first - staging time, not evaluation. The same run key is evaluated again in real paths (`open_run` -> `reopen_run` + `record_resolution` replaces the resolution; `recheck.mint_run_id(taken=...)` reuses an owed run's key so a retry completes the same run), so a retry reading newer state keeps its first number - a wrong "newer" with no visible tie. Fix: one column drawn only in `open_run`, redrawn on every reopen ("the order evaluations began against their recorded resolution"); `record_run`/`register_run_if_absent` never set it; `complete_run` refuses a run without one. Concurrency: `nextval` is unique and increasing; allocation vs commit order doesn't matter (build reads completed runs). Real window: pass and terminal concurrently - a decision can land between a run's resolution and its number. Draw it in the same transaction that records the resolution, or under v4 S1's per-(collection, period) advisory lock. Parallel bootstraps across collections are independent; each collection's order needs re-checks/knock-ons sequential within it (they are today).

**B2. c12's list of guesses to remove is incomplete.**
- `build_dashboard_data.py` 735: own runs sorted by DAY (`_run_date`), ties to `results_history.py:91` `run_index` (a re-check shares its arrival's, `recheck.py:232`; a pair's two supplies share one), ties to natural run-key sort.
- 499-506: "current value" compares `recorded_at`, takes max.
- 317-320, 477: `own_runs` and `recorded_by` read `run_owner(run_id)` off the id (c11 covers sentences, not `own_runs`).
- 350-363, 230-239: `share_cross_table_results` / `_cross_table_info` place by TODAY's declarations (`collect_checks(None)`), not recorded reads - same history, different checkout, different placement.
- Template 3649-3652 `about = read || ownRun` (a guess); 3667 chain sort `(date, at)`; 3697 point sort `(date, at, runId)`; 5146-5157 `deliveryCount`/`defaultCompareIndex` via `sameDelivery`.
- Gate: `supply_status.py:59` `ORDER BY caused_at, r.run_key`; `qa_store.py:1300-1301` `supply_current_run` `run_instant, run_key`.
- Run path: `qa_results_writer._with_tables_read` (154) swallows exceptions -> a cross-table result with no read; must refuse. `carried.decide` (165) takes siblings in `sorted(others)` text order (minor; use sequence).
Fix: exhaustive c12, plus a test failing if placement/ordering code reads `recorded_at`, run_id text or a day.

**B3. c7's grouping key and in-point precedence are undefined.** c6 gives a cause only to re-check/readers/knock-on runs; c7 needs one for an arrival run of ANOTHER delivery reading an older supply (test (b), Investigations reading 1 Feb Case Workers). Define cause as decision id | load id | delivery name. Precedence: within a point each check takes its highest-sequence result - not today's "another table's result replaces the own verdict" (template 3615-3621), which is wrong because `current_runs_only` makes a supply's own point its CURRENT run, possibly a `full` re-check opened after the sibling's arrival that re-ran the same check. The page also needs each own point's supply id: the manifest's `arrival_record` (`dataset_stats.py:35`) has run_id, run_index, received_at, delivery, no supply; emit `qa.run.supply_id`.

**B4. Q3(a) as worded contradicts the story and the one-fact-two-readers NFR.** Sequence for the page, `effective_at` for the gate => page and gate name different "newest" for any decision recorded after the fact. Re-put Q3: (a) sequence for both; (b) sequence for page, effective time for gate, disagreement named in a criterion. Architect's view: (a) - post-build-review #116 D1's case (a re-evaluation never outranking its arrival) also holds under sequence, since a re-run is always opened after what it re-runs; replay doesn't distort opening order.

## Should-fix

- **S1. c1's states vs the resolution.** Contested: ambiguous AND resolved - falls through to the period's promoted supply (`supply_db.Resolution.unreadable`); record the supply read plus a contested flag with the contested files. Open pair: one filed supply (`#1`) with two files - "naming each contested supply" names the wrong thing. Held: today a physical name (own table withheld, `period_overlay.py:134`), a supply id (`name_held_siblings`, :209) or `""` (open pair held) - record the held SUPPLY id always, or c9 can't match `""`. Add a no-supply state for sample/trial tables.
- **S2. c2 breaks unnamed readers.** `qa_results_writer.py:148-150` uses `logical in resolution.supply_of` as "is a period table"; once staged tables enter `supply_of` their names go through `period_tables.stamped_name`. Record the source explicitly (`PeriodResolution.source`), keep the result's `tables_read` names unchanged, with a test. Write the supply on `qa.tables_read.supply` too (its comment says NULL for staged); `runs_about`'s physical-name matching then becomes dead - remove under c13. The staged mapping exists at run time in `period_overlay.staged_for_period`'s loop over `filing.CURRENT` and `supply_files.resolve`. REQ-PIPE-265: `carried._supply_names`/`_same_supplies` reduce to comparing supply ids; `carried_from` unaffected.
- **S3. Storage shape: a table, not jsonb `extra`** (the gate's SQL joins it): `qa.check_read(result_id -> check_result.id ON DELETE CASCADE, logical_table, state, supply_id)` so `record_results`' delete+insert (`qa_store.py:1881`) replaces result and reads atomically; or rows keyed `(run_key, check_id, logical_table)` deleted by the same write key.
- **S4. Enforce c3**: the writer refuses a single-table result under a run whose `dataset_id` isn't the check's dataset. "0 of 20,014" is today's data, not a guarantee at 30 collections.
- **S5. c16 vs c13.** Replacing the `run_key` tie-break with sequence can change which run is current (62 groups on ed_probe share a run instant; B4(a) changes more). Require the before/after comparison to list every difference with the tie/order it changed, not zero differences.
- **S6. Duplicate orderings.** Already `run_index` (arrival enumeration), arrivals' `sequence` / `qa.delivery_file.receipt_sequence` (receipt order), `check_result.id`. Name the new column distinctly (`run_seq`), state what each surviving order is for, retire `run_index` as the build's own-run order.
- **S7. "Emit order" concretely**: a dense rank per point and per history entry, computed per collection, never the raw number; the template sorts on the rank alone.
- **S8. c15 is existing mechanism**: `_refuse_another_version` already refuses older versions; this is `SCHEMA_VERSION` 45 -> 46. Say so.

## Notes

- Gives #95 v4 B2 exactly its fact: cross-table results via c1 (each table read, own included, with a state); single-table via c3 (`qa.run.supply_id`). In #95, 267 c1 and 269 c1-c2 cite 279 c1 not `qa.tables_read`; 269 c7's single selection function should be c13's gate function (e.g. `supply_status.results_about`), shared by page, gate and #95 counting. For the gate's own supply per-check vs per-run selection coincide, so gate changes under c13 come from the tie-break.
- #95 B3 joinable: no conflict; "newest" defined by the Q3 answer.
- `name_held_siblings` decides held vs absent by parsing `arrival_key_of(supply_id)` at run time - deterministic, decides c1's state; leave it.
- Fit: no new command or CLI change; touches QAC, PIPE, DASH, TEST - right as its own requirement. Security: no concern (facts in `qa`, never `staging._resolutions`).

## Q1-Q6 (technical consequences)

Q1 (a): what #95 B2 needs; brings the REQ-DASH-264 c1 amendment. Q2 (a) once B3 defines the cause key; under (b) point count depends on fan-out. Q3: see B4, sequence for both; expect c16 differences if scripted decisions carry back-dated `effective_at`. Q4 (a): (b) re-introduces a timezone-dependent test (`asset_time.local_date`); the as-of clip by `recorded_at` keeps a Monday view right. Q5 yes: otherwise `carried.siblings()` keeps parsing run ids and `runs_about` keeps name-matching; c2's supply on `qa.tables_read` is needed by the gate anyway. Q6: none; the build should carry the read supply in the data either way.

## Tests that would fail on a guess (add to c17)

1. Two Clients supplies in one day (09:00, 15:00 resupply); a Notifications run reads the 15:00 one -> placed on 15:00 (day rule and `read || ownRun` both fail).
2. A delivery across midnight.
3. Same run instant, badly sorting keys (`__r10` vs `__r9`, `cp_notifications__X` vs `cp_clients__X__r1`): page order and `supply_current_run` follow sequence.
4. An owed re-check retried under its own key after another run opened: its number is greater (B1).
5. Another collection's runs interleaved: built output byte-identical (S7).
6. A check's declared reads edited: placement unchanged (B2).
7. A contested own table: placed on the promoted supply it fell through to (S1).
8. A settled pair: two supplies of one table in one delivery.
9. The writer refuses a cross-table result with no read recorded.
10. JS `unitCounts`: two points with the same date and `at` ordered by emitted rank.

## Bootstrap cost

Schema bump forces `mothman env reset-synthetic` + `mothman pipeline bootstrap` (last from-empty ~1,245s, 2026-10-18); REQ-TEST-239's before/after needs one per schema, ~double. New writes ~1.9k rows + one `nextval` per run, negligible. CI cache miss on the first push: a full deployment bootstrap (~39 billable minutes, REQ-TEST-260) - keep to one push.

## Builder expectations

One function answers "which supply did this result read", used by build, `supply_status` and `carried`; its docstring states read/held/contested/absent/no-supply and why. Every placement query `ORDER BY` a recorded key. No `recorded_at`, run_id text or day comparison in placement/ordering code of `build_dashboard_data.py` or the template's `unitCounts`, `sameDelivery`, `defaultCompareIndex`, point sorts. The sequence column's comment says why it's drawn in `open_run`, redrawn on reopen, never in `record_run`/`register_run_if_absent`. `_with_tables_read`'s `except Exception: return verified` goes for cross-table results. Removed code goes with its tests. Each removed heuristic gets a `decisions:` line.

## Sketch

`open_run` draws `qa.run.run_seq`. The writer takes each read table's supply from the run's resolution (now carrying staged supplies, from `filing.CURRENT` / `supply_files` in `staged_for_period`) and writes `qa.check_read` in `record_results`' transaction. The build joins `check_result` + `check_read` + `run` (`run_seq`, `scope`, `dataset_id`, `supply_id`, `caused_by_*`) + `filing` (`delivery`); point = (dataset, supply, cause), cause = the delivery if the recording run is an arrival of the delivery that brought the supply, else the causing decision/load/delivery; emits a per-collection rank. Template sorts on rank, clips by `recorded_at`. The gate's `results_about(supply)` runs the same join.

## Questions for Keith

1. Q3 re-put: sequence order for page AND gate, or sequence for page with the gate on effective time and the disagreement written into a criterion? (B4)
2. A run key evaluated again (owed retry, reopen): new sequence number (recommended), or keep the first and refuse the re-run if its resolution changed? (B1)
3. c16: accept a before/after comparison that lists and explains decision differences rather than requiring none? (S5)
