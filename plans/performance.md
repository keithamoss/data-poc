# Real-tool pipeline performance

How long `real_tools/orchestrate_real.py` (Birth Registrations) and
`real_tools/orchestrate_real_cp.py` (Child Protection) actually take, what
was done about it, and what's left on the table. Scoped narrowly to these
two orchestration scripts — not the whole repo's performance.

Status values: `done` / `open`. Priority is relative, not a schedule.

## Measured baseline (Child Protection, per run)

A one-off timing breakdown of `real_tools/orchestrate_real_cp.py`'s four
per-run tool calls, before any fix:

| Tool | Time/run | Share |
|---|---|---|
| dbt-core | 9.5s | 45% |
| datacontract-cli | 7.6s | 36% |
| Evidently | 3.5s | 17% |
| Soda Core | 0.5s | 2% |
| **Total** | **~21s** | → **×10 runs ≈ 3.5 min** |

dbt's 9.5s breaks down further: `dbt --version` alone (no project work at
all) takes ~2.4s — dbt-core has heavy *fixed* per-invocation startup cost
(Jinja environment, manifest parsing, adapter loading), and both
orchestration scripts were paying that cost **twice** per run, via two
separate subprocess calls (`dbt run` then `dbt test`).

## Done

1. **[done, high]** Combine `dbt run` + `dbt test` into a single
   `dbt build` call, in both `run_dbt_real.py` and `run_dbt_real_cp.py`.
   Same work (build the model(s), then run their tests) in about half the
   time — verified directly with isolated CLI timing on one CP run:
   `dbt run` (5.6s) + `dbt test` (3.9s) = 9.5s separately, vs. 4.2s for
   one combined `dbt build` call.

   Measured end to end:
   - **Child Protection**: full 10-run orchestration went from an
     estimated ~3.5 min (210s, from the per-run breakdown above — the
     unfixed version was never successfully timed end-to-end as a
     baseline run since the fix was made alongside a data reorder) to a
     **measured 2m23s (143s)**.
   - **Birth Registrations**: no valid "before" timing exists — see the
     bug below, it was crashing, not slow. **Measured 2m24s (144s)**
     after the fix, its first successful full run in this project's
     current form.

   No behavioral change: `run_results.json` from `dbt build` also
   contains the model-build step's own result alongside the test results,
   which both files' existing parsing already silently skips (test-node
   lookups return `None` for anything that isn't a test).

2. **[done, high]** Fixed a real, live bug found *while* implementing #1,
   not a hypothetical: `run_dbt_real.py`'s dbt invocation had no
   `--select` at all. This was fine when the dbt project only contained
   `stg_birth_registrations` (the whole project *was* the selection), but
   Phase 2 added 6 Child Protection models + 3 singular tests to the same
   `dbt_project/` without updating this file — so every call since then
   was also trying to build/test the CP models against a
   birth-registrations-only warehouse that has none of those tables, and
   crashing on the CP singular tests (`node["test_metadata"]` — they have
   none) with a bare `KeyError`. Nobody had re-run
   `real_tools/orchestrate_real.py` since Phase 2 added those models, so
   this sat undiscovered. Fixed by adding
   `--select stg_birth_registrations`, verified against both a clean run
   (matches prior documented numbers exactly) and the red run (58/769,
   matching README's known-disagreements numbers).

## Open — filed away, not implemented

3. **[open, low]** Investigate datacontract-cli's 7.6s/run. Unlike dbt,
   this isn't process-startup overhead — the Python import is ~0.45s and
   `DataContract()` construction is ~0.03s; the cost is genuinely inside
   `.test()` itself (parsing 6 CSVs into DuckDB views, running every
   quality rule). Harder to justify a fix without understanding *why*
   it's slow first (repeated DuckDB extension loading? ibis backend
   setup? something reducible without changing what's tested?) — lower
   confidence this pays off, needs investigation before it needs code.

4. **[open, medium]** Parallelize across the 10 independent runs
   (multiprocessing — each run is its own isolated DuckDB file, no shared
   mutable state between runs by design). Highest ceiling of any option
   here — theoretically up to ~10x, realistically 3-5x depending on core
   count — but not a small change: dbt writes to a shared
   `dbt_project/target/` directory by default, so concurrent `dbt build`
   invocations for *different* runs would clobber each other's
   `manifest.json`/`run_results.json` mid-write unless each parallel
   worker is given its own `--target-path`. Worth doing if this becomes a
   frequently-run CI job (see `plans/wider.md` action 3); probably not
   worth the added complexity for occasional local/manual runs.

5. **[open, low]** Smaller-scope parallelism: within a single run, run
   the dbt subprocess concurrently with the three in-process Python calls
   (Soda / datacontract-cli / Evidently) via a thread pool, since none of
   them touch each other's state. Avoids #4's `target/` collision problem
   entirely (only one dbt process ever running at a time).
   **Re-measured for Birth Registrations specifically (2026-09-14),
   correcting the estimate above** - the ~9.5s/~4.2s figures were Child
   Protection's own baseline, and even that carried a real distortion:
   isolated per-tool timing across 3 consecutive BDM runs in one process
   showed Evidently and Soda both pay a one-time cost on their first call
   (evidently: 2.88s -> 0.12s -> 0.10s; soda: 0.35s -> 0.08s -> 0.08s) -
   almost certainly the `evidently`/`soda` package imports, not per-run
   work - so a single-run timing snapshot overstates them heavily.
   Steady-state BDM breakdown across real runs: dbt-core ~5s,
   datacontract-cli ~6s, Soda/Evidently ~0.1s each (negligible). The real
   bottleneck is dbt-core and datacontract-cli specifically, not "the
   four tools' sum." Threading dbt concurrently with the other three
   would overlap dbt's ~5s against datacontract-cli's ~6s instead of
   summing them - **per-run time ~11s -> ~6s, roughly 5s/run saved, ~75s
   across the current 15-run manifest (measured 2m36s full run -> an
   estimated ~1m20-30s)** - a ~45-50% cut, larger than "smaller win than
   #4" suggested. Still real engineering (thread-safety of the Python API
   calls, correctly collecting/ordering results), but worth revisiting
   the low-priority tag given the corrected number.
