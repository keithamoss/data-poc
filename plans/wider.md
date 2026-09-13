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

5. **[done]** The old claude.ai Artifact copy is no longer a concern —
   decided to stop maintaining it; this repo's HTML is the sole source of
   truth going forward. **Public hosting decided and set up**: the repo
   itself is now public (Keith's call, given the data involved is
   synthetic), so GitHub Pages works on the free plan with no workaround
   needed. `.github/workflows/deploy-pages.yml` publishes
   `dashboard/qa-reporting-dashboard.html` (as `index.html`) on every push
   that touches `dashboard/` — no separate build step, since the file
   already has its data baked in at commit time. One manual step still
   needed (can't be done via the GitHub API access available here):
   **Settings → Pages → Build and deployment → Source: "GitHub Actions"**,
   one time, in the repo's web UI. Once that's flipped, the live URL will
   be `https://keithamoss.github.io/data-poc/`. This also means: as more
   datasets get wired in (action 2) and a scheduled re-run job exists
   (action 3), the public dashboard updates itself automatically on every
   push — no extra work per dataset added.

6. **[todo, low]** Decide the long-term home for `synthetic-data-generator/`.
   It's a subdirectory here for now (simplest, since it never had its own
   GitHub repo); worth revisiting once cleanup starts — does it stay
   merged into this repo, or get split out now that we can actually push
   to GitHub?

7. **[investigate]** Data pipeline observability — flagged as a tangent,
   not yet scoped. Distinct from what's already built: the QA
   dashboard/real-tools pipeline checks *data quality* at a point in time;
   this would be about the health of the *pipeline itself* — did a run
   happen, how long did it take, did it fail silently, is the data stale.
   Also distinct from action 3 above (which is specifically "catch
   upstream tool breakage via a scheduled re-run"). Needs scoping before
   it becomes an actionable item — open questions:
   - Instrumentation (run metrics/tracing — e.g. OpenTelemetry, run
     duration/success history) vs. cataloging (the governance/catalog
     tools surveyed in `docs/data-contract-engines-landscape.md`'s
     Category C — DataHub, OpenMetadata) vs. alerting (notify someone
     when a check fails, rather than only surfacing it on the dashboard
     next time someone looks)? Could be more than one of these.
   - Scoped to this PoC's own pipeline runs, or meant to model what a
     *real* production multi-agency pipeline would need operationally
     (i.e. part of the PoC's demonstration value, not just this repo's
     own housekeeping)?
   - Does it belong as a feature of the existing QA dashboard (a new
     tier/tab), or as a genuinely separate concern?
