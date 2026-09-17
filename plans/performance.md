# Real-tool pipeline performance

How long `qa_tools/bdm/orchestrate_bdm.py` (Birth Registrations) and
`qa_tools/cp/orchestrate_cp.py` (Child Protection) actually take, what
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

3. **[investigated, low — no action taken]** datacontract-cli's ~6-7.6s/run
   cost, profiled properly (2026-09-14) rather than left as a guess.
   Phase-by-phase timing of `evaluate_datacontract_real()` confirmed the
   cost is genuinely inside `.test()`, not import/setup: import 0.349s,
   `DataContract()` construction 0.011s, `.test()` call 6.743s.

   `cProfile`'d the `.test()` call itself to find out *why*. No single
   dominant fixable bottleneck — the time is spread across genuine work
   inside datacontract-cli's own implementation:
   - ibis/DuckDB schema introspection (`ibis.backends.duckdb.table()` /
     `get_schema()`) — 14 calls, ~4.82s cumulative, the largest chunk.
   - Raw SQL execution (`_duckdb.sql`) — 29 calls, 2.944s tottime (the
     single biggest *tottime*, i.e. time not spent in sub-calls).
   - ibis backend connection setup (`connect_ibis`) — 1.308s, paid once.

   14 `table()`/`get_schema()` calls for what's presumably 6 CSVs (one
   per table in the contract) stood out as possibly-redundant schema
   introspection — a plausible investigation lead if this were pursued
   further, since re-doing schema lookups on tables already introspected
   would be pure waste. Not chased further: this cost lives inside
   datacontract-cli's own library code, not this repo's — fixing it means
   either patching/monkeypatching a dependency (fragile, real ongoing
   maintenance cost) or upstreaming a fix (a genuinely new commitment vs.
   the "PoC in weeks" scope). Given item #4 already delivered a bigger,
   safer win (3.1-3.4x, this repo's own code, zero dependency risk),
   parking this — same status this item always had ("lower confidence
   this pays off"), now with real evidence behind that call rather than a
   guess.

4. **[done, medium]** Parallelize across the independent runs
   (multiprocessing — each run is its own isolated DuckDB file, no shared
   mutable state between runs by design). Scoped via questions first
   (2026-09-14): both `orchestrate_real.py` and `orchestrate_real_cp.py`
   together (shared implementation, `real_tools/parallel_orchestrate.py`)
   rather than Birth Registrations alone; a worker failure aborts the
   whole batch (matches the original sequential behaviour - no partial
   `results_real*.json` ever gets written); a `--sequential` flag kept
   for easier debugging (parallel workers interleave print output/stack
   traces); worker count dynamic (`os.cpu_count()`), not hardcoded to
   this session's specific 4-core VM.

   The real blocker this item always named - dbt writes to a shared
   `dbt_project/target/` directory by default, so concurrent `dbt build`
   calls for different runs would clobber each other's `manifest.json`/
   `run_results.json` mid-write - is fixed: `run_dbt_real.py`/
   `run_dbt_real_cp.py` now pass `--target-path <run_id>` per run,
   applied unconditionally (safe and free even sequentially, not just
   under parallel execution).

   **Measured end to end, not the earlier extrapolated 60-80s guess**:
   - Birth Registrations (15 runs): 2m35s sequential -> **45s parallel -
     a real 3.4x**.
   - Child Protection (10 runs): 1m52s sequential -> **36s parallel - a
     real 3.1x**.
   - Both beat the corrected 2-2.5x extrapolation above - dbt (a
     subprocess, not Python-GIL-bound) parallelizes at least as well as
     the three in-process tools did in the smaller 4-run test that
     extrapolation was based on.
   - Output verified byte-for-byte identical to sequential for both
     (every field except the run-timestamp), not just same check counts -
     confirms the `--target-path` fix and manifest-order reassembly are
     both correct, not just fast.
   - `tests/test_parallel_orchestrate.py` covers the dispatch logic
     itself (manifest-order preservation regardless of completion order,
     abort-on-failure) with fast stub workers - real-tool integration
     stays out of pytest's scope per its own established boundary.

   Given the real numbers landed better than estimated, and CI wasn't
   even required to make this worthwhile, the original "probably not
   worth it for occasional local/manual runs" framing turned out wrong -
   worth having by default regardless of how often this actually runs.

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
   summing them - per-run time ~11s -> ~6s, roughly 5s/run saved, ~75s
   across the 15-run manifest (an estimated ~1m20-30s) - a ~45-50% cut,
   larger than "smaller win than #4" suggested at the time.
   **Superseded**: #4 was then actually built and measured at 45s for
   the same 15-run manifest - a bigger win than this item's own estimate,
   for less engineering (no thread-safety concerns, since separate
   processes rather than threads sharing one interpreter). Not worth
   doing on top of #4 now - staying `[open, low]` only as a record of
   the analysis, no longer an active candidate.

## Manifest size changed, 2026-09-16 - not yet re-benchmarked

BDM's manifest grew from 15 to 85 entries (60 scheduled deliveries, up
from 10) and CP's from 10 to 16 (quarterly instead of weekly - see
plans/wider.md's history-depth entry). Both real orchestrators were run
successfully end to end against the new scale (verified in
plans/wider.md), but no fresh sequential-vs-parallel timing comparison
was taken - the #4 parallelism numbers above (45s/36s) are from the
original, smaller manifests and shouldn't be read as current. Worth a
real re-measurement if runtime becomes a live concern again at this
depth, not assumed to still hold linearly.

## Flagged, 2026-09-17 - not investigated yet, follow up next

BDM's manifest grew again, 60 -> 120 scheduled deliveries (176 real
runs including resupply attempts - see `plans/qa-pipeline.md` item 55
for why: `AS_OF_OFFSET_DAYS` needed real margin BDM's old 60-delivery
window didn't have). Keith's own framing, same session: **this
dataset's real run count is headed into the thousands, not hundreds,
over the project's life** - the `delivery_id`/`run_id` zero-padding fix
in that same item was corrected once already for reasoning the same
way ("wider padding" -> "no width assumption at all") once that became
clear. Runtime deserves the same treatment before it becomes a live
problem, not after.

A real data point from this exact regeneration (not extrapolated): the
qa_results/ write timestamps for BDM's real-tool phase (`qa_tools/bdm/
orchestrate_bdm.py`, parallel across CPU cores per item #4 above) span
~11 minutes for 176 runs. That's in line with item #4's/#5's
steady-state per-run breakdown (dbt-core ~5s, datacontract-cli ~6s,
Soda/Evidently ~0.1s each, ~11s/run, parallelized ~3.1-3.4x) - nothing
newly wrong, just a real number to scale from. Naively linear, "a
couple thousand runs" (roughly 10-15x today's volume) puts this phase
alone at something like 2 hours wall-clock, which would make
`./run_pipeline.sh` a genuinely bad local/CI experience, not just a
slow one - worth getting ahead of before that data volume is actually
reached, not after someone's stuck waiting on it.

Not investigated or built - candidates for next session's actual
profiling/decision, roughly in order of expected leverage at this
scale, least invasive first:

- **Re-score item #3's parked datacontract-cli cost (~6-7s/run).** It
  was parked at "lower confidence this pays off" when only ~15-85 runs
  existed - the same fixed per-run cost now applies to 176 runs and
  will keep compounding as the manifest grows, so the parking math
  (engineering cost vs. total time saved) may no longer land the same
  way even though the per-run cost itself hasn't changed.
- **Increase/verify worker parallelism**: `parallel_orchestrate.py`'s
  worker count is `os.cpu_count()`-based - confirm this environment
  isn't leaving real parallelism on the table (or that item #4's
  already-measured 3.1-3.4x ceiling is genuinely CPU-bound, not an
  artifact of a smaller test manifest).
- **Incremental regeneration - the actual structural fix at "thousands"
  scale, and the biggest engineering lift.** `./run_pipeline.sh` today
  always regenerates and re-runs everything from scratch - data/raw/
  wiped, every delivery in the rolling window regenerated, every real
  tool re-run for every run - even though a rolling-window regeneration
  mostly just shifts the window forward by however many days passed
  since the last run, leaving most of the window's runs genuinely
  unchanged. At hundreds of runs that's wasteful but tolerable; at
  thousands it's the dominant cost. Turning this into "only regenerate/
  re-run what's actually new or changed since qa_results/'s own
  committed history" would cut the common case from O(window size) to
  O(runs added since last regen) - but needs real design (how to detect
  "unchanged" reliably including resupply chains, whether it's even
  compatible with this project's "everything is seeded, full
  regeneration is a real correctness diff" convention, or whether that
  convention itself needs to bend at this scale).
- **dbt-core's ~5s/run fixed startup cost** (Jinja environment,
  manifest parsing, adapter loading, paid once per subprocess
  invocation) - amortizing this across runs would need a genuinely
  different execution strategy (a persistent dbt process/server, or
  batching multiple runs' checks into fewer invocations), a bigger and
  riskier architectural change than anything else in this list - only
  worth it if the simpler items above don't get this phase back under
  control on their own.
