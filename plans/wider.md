# Wider PoC plan

Tracks the whole multi-agency data pipelines proof-of-concept, not just
the birth-registrations QA pipeline (that has its own plan:
`plans/qa-pipeline.md`). This is a working document, not a spec — update
it as things move, don't let it go stale.

**Context:** Keith is Director of Data Technology at a Western Australian
government agency, working this PoC over a period of **weeks**, then
cleaning it up and handing it to the team for their input. Nothing here
should assume a multi-month timeline.

## What exists, and where

| Component | Where | Status |
|---|---|---|
| Birth-registrations QA pipeline | this repo, root (`contract/`, `dbt_project/`, `engines/`, `generator/`, `pipeline/`, `real_tools/`) | Real tools wired up and running (`real_tools/*.py`); see `plans/qa-pipeline.md` for open items |
| Synthetic data generator | this repo, `synthetic-data-generator/` | Code present, runs, verified (population-scale, cross-agency identity linkage); **not yet wired into the QA pipeline or dashboard** — see action 2 below |
| QA reporting dashboard | this repo, `dashboard/qa-reporting-dashboard.html` | Only Birth Registrations wired to real data; ~14 other datasets are still fabricated mock, clearly labeled as such. Also separately published as a claude.ai Artifact ("Data Asset QA Register") that is **not** auto-synced with this file — see action 5 |
| Supporting docs | this repo, `docs/` | `data-contract-engines-landscape.md` (source of the real contract/checks YAML), generator design notes, a standalone quarantine-pattern demo |

## Action items

Status values: `todo` / `in progress` / `done`. Priority is relative,
not a schedule.

1. **[done]** Pull `synthetic-data-generator/` and `docs/` into this repo.
   The sibling repo never existed on GitHub — only inside claude.ai chat
   sessions — so this was a zip merge, not a git remote add. Deliberately
   left out a stale, pre-real-tools snapshot of the pipeline files bundled
   in the same upload. Commit `8a1028f`.

2. **[todo, high]** Wire a second dataset into the QA dashboard end to
   end, as a template for the rest. `synthetic-data-generator/`'s Child
   Protection collection (real FKs across 6 tables) or School Enrollment
   are the natural next candidates — unlike birth registrations, Child
   Protection would exercise a `relationships` dbt test for the first
   time (deliberately skipped so far for lack of a second table to join).
   This is the highest-value item: it proves the birth-registrations
   pipeline's approach generalizes rather than being a one-off.

3. **[todo, medium]** No CI. Nothing re-runs `real_tools/orchestrate_real.py`
   against upstream tool releases, so a `dbt-core`/`soda-core-duckdb`/
   `datacontract-cli`/`evidently` update could silently break this and we
   wouldn't know. A scheduled job (even a simple cron/GitHub Action) that
   runs the real pipeline and diffs against `reports/results_real.json`
   would catch regressions early — including possibly resolving or
   changing the dbt-duckdb bug (`plans/qa-pipeline.md` #1) on its own.

4. **[todo, low]** Try Postgres as the warehouse instead of DuckDB (the
   original HANDOFF suggested it as an alternative). Would tell us
   whether the dbt-duckdb reliability bug is DuckDB-specific or a more
   general dbt-core issue — useful signal for `plans/qa-pipeline.md` #1
   even if Postgres itself isn't adopted.

5. **[todo, medium]** Decide how to handle the dashboard/Artifact split.
   Options: keep publishing a fresh Artifact copy manually after each
   repo change; write a small script/workflow to do it; or treat the
   repo's HTML as the sole source of truth and stop maintaining the
   Artifact. Needs a decision, not just an observation.

6. **[todo, low]** Decide the long-term home for `synthetic-data-generator/`.
   It's a subdirectory here for now (simplest, since it never had its own
   GitHub repo); worth revisiting once cleanup starts — does it stay
   merged into this repo, or get split out now that we can actually push
   to GitHub?
