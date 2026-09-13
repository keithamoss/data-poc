# Birth-registrations QA pipeline plan

Open items from wiring up the real dbt-core/Soda Core/datacontract-cli/
Evidently tools (`real_tools/*.py`) against this pipeline. Everything here
is either a genuine bug found by actually running the real tools, or a
documented equivalent-vs-real-tool disagreement worth a second look.
Scoped to this repo's `contract/`/`dbt_project/`/`engines/`/`real_tools/`
work specifically — wider-project items live in `plans/wider.md`.

Status values: `open` / `workaround shipped` / `done`. Priority is
relative, not a schedule — this is weeks of work, not months.

## Found running the real tools

1. **[workaround shipped, high]** dbt-duckdb reliability bug. dbt-core's
   own reported `failures` count was reproducibly wrong (0 instead of the
   true row count) on some runs for a percentage-based `fail_calc`, while
   the identical compiled SQL run directly via DuckDB's Python API always
   gave the right answer. Root cause not found despite extensive isolation
   (removed all arithmetic, disabled partial parsing, forced
   `--store-failures`, substituted SUM for COUNT — see
   `dbt_project/models/staging/schema.yml`'s comments for the full trail).
   Current fix: absolute row-count thresholds instead of a computed
   percentage, plus independent re-verification in
   `real_tools/run_dbt_real.py`. **Follow-up:** build a minimal standalone
   repro (no dbt project, just the SQL pattern) and file it upstream
   against `duckdb-labs/dbt-duckdb`; `plans/wider.md` #3/#4 (CI, Postgres)
   might also shed light on this without extra effort.

2. **[open, medium]** `soda-core-duckdb`'s `duckdb<1.1.0` pin isn't a
   compatibility ceiling — it pins to a DuckDB version with a published
   CVE (GHSA-w2gf-jxc9-pf2q), patched in 1.1.0. Confirmed via upstream
   issue `sodadata/soda-core#2295`. Currently ignored (we run on 1.5.5,
   verified working end to end — see `requirements-real.txt`'s comments).
   **Follow-up:** there's a newer `soda-duckdb` V4 package
   (`sodadata/soda-core/soda-duckdb`) that's actively maintained — worth
   checking whether it's the intended replacement and whether
   `run_soda_real.py`'s `Scan` API still exists there before migrating.

3. **[open, low]** Soda's `[recent]` scoped check (`filter ... where:
   extract_timestamp >= CURRENT_DATE - 1`) never gets meaningfully
   exercised against real Soda Core — it uses the actual wall-clock date,
   and this fixture's synthetic runs are all in the past by the time
   anyone actually runs it, so the scope always resolves to 0 rows.
   Documented as a real, honest finding (README's known-disagreements
   section), not fixed. **Follow-up:** regenerate the synthetic runs on a
   rolling window near "today" instead of a fixed Sept 2026 range, so the
   scoped check has real data to filter — would also un-stale the fixture
   generally.

4. **[open, low]** Evidently's PSI and the equivalent engine's PSI
   genuinely differ (0.144 vs 0.179 on the red run) because Evidently bins
   by every distinct observed value while `drift_engine.py` collapses
   everything outside {M,F,X} into one `_other` bucket. Both valid;
   documented, not reconciled. **Follow-up:** decide whether to make the
   equivalent's PSI bin per-distinct-value too (closer fidelity to
   Evidently, more equivalent-engine complexity) or leave it as a
   deliberate simplification — either is defensible, just needs a call.

5. **[open, low]** `engines/contract_engine.py`'s `type: sql` rule handling
   (added when the contract was rewritten to real ODCS vocabulary) uses a
   temp-view + string-replace to scope each SQL rule to one run's rows.
   Works, but is fragile — equivalent-only tech debt, not a real-tool
   issue.

6. **[open, low]** The two-step `pip install` requirement
   (`requirements-real.txt` then separately `pip install
   'datacontract-cli[duckdb]'`) is brittle — a single combined install is
   a hard resolver failure today. Worth a periodic recheck as
   `dbt-duckdb`/`soda-core-duckdb`/`datacontract-cli` release new
   versions; this could resolve cleanly on its own, or break differently.

9. **[open, medium]** Two of the three Child Protection cross-table
   business rules (Phase 2 — see `plans/wider.md` #2) fail on *every* run,
   dirty or clean, at a stable rate: placement/carer approval compliance
   (37/242 placements, ~15%) and closed-case investigation hygiene
   (16/181 investigations, ~9%). Confirmed for real and triangulated
   across all three tools — `datacontract test`, `dbt test`, and
   `soda scan` all independently report the same 37 and 16 on the same
   data. Not a bug in the rules: `synthetic-data-generator/child_protection.py`
   genuinely doesn't enforce either invariant (`carer_for_placement` is
   drawn from the full carer pool regardless of `approval_status`;
   `case_status` and investigation `end_date` are generated
   independently) — real findings the rules are right to keep surfacing,
   documented in `contract/child-protection-contract.yaml`,
   `contract/child-protection-soda-checks.yml`, and
   `dbt_project/tests/*.sql` rather than loosened to hide them. The third
   rule (escalation completeness) has no such issue — 0 on every clean
   run, correctly firing (2-6) only on dirty runs, since
   `cp_investigations` is built directly from notifications with the
   matching outcome. **Follow-up, a call for Keith:** leave these two
   rules as permanently-red findings on the dashboard (accurate to a real,
   ongoing compliance risk), soften them to a warning tier so they read as
   "known issue" rather than "broken check", or adjust the generator so
   clean runs satisfy both invariants and only a future dirty preset
   violates them (bigger change — would need new dirty.py presets for
   cp_placements/cp_investigations, which don't exist today). No action
   taken yet — worth deciding before Phase 3 wires this collection into
   the dashboard, since that's what will make the choice visible.

## Held over from the original (equivalent-only) build

Lower priority — these were already documented as deliberate, honest
simplifications before any real tool ran, and nothing since has changed
that assessment. Listed here so they don't get lost, not because they're
urgent.

7. **[open, low]** ODCS severity is single-tier (pass/fail or pass/warn,
   never a three-way band). `contract_engine.py` encodes that into the
   dashboard's two-threshold shape as warn==fail (error severity) or an
   unreachable fail ceiling (warning/info severity). Real, not a bug —
   revisit only if the dashboard's shape itself changes.

8. **[open, low]** Soda's `row_count` check is a genuine two-sided range
   (too few *or* too many rows); `soda_engine.py`'s `_numeric_threshold()`
   reduces it to the upper bound only for display — the one place a piece
   of real information (the lower bound) is dropped for a single scalar.
   Would need a dashboard/schema change (a second threshold field) to fix
   properly, not just an engine change.
