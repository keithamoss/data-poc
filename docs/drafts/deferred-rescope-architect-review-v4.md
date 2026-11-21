# delivery-architect on deferred-rescope-v4.yaml, 2026-11-21

Read-only. Summary; every code claim was cited by the agent to file:line.

## Must fix before sign-off
1. **The repository is public** (REQ-DOCS-259 not_started); `extractions/<id>/` would
   publish project name, cohort bounds and filter text. CI also parses every folder
   (`yamllint --strict .`, critical.yml:102, test.yml:282), so 446 c11's "no workflow
   names extractions/" test gives false comfort. Block 440 on 259, or keep one-off
   configuration in a separate private repository via use_root (Keith).
2. **Dropping the database leaves the extract on disk**: hand-filing's delivery
   copies under `data/<id>/`, failing-row keys in `reports/<id>/`, dbt scratch. The
   drop must remove them and the confirmation must list them.
3. **440 c3 "no calendar.yaml" breaks the loader**: `no_calendar:` is read from
   calendar.yaml's `datasets:` (agreement.py:510-516); a missing file raises. Generate
   a minimal calendar.yaml.
4. **439 c7 "not CSV" is new work**: staging is CSV-only (stage.py:203-215).
5. **A derived product has no "in development" declaration** once 438 splits routing
   from state; `not-yet-agreed` is refused in an extraction, so a new key (e.g.
   `derived: true`). Open: a cross-table check spanning derived and counted tables
   (state_for_participants marks the whole result in development).
6. **446's gate list names gates that do not exist** and omits `hierarchy`,
   `patterns`, `soda`, `columns`, `caches`, `guard`; `guard` opens a database and
   must be not-applicable.
7. **446 c12 (<1s per folder) is not reachable**: each per-asset gate is a
   subprocess - ~2,000 interpreter starts at 200 folders. Gate only changed folders
   against MOTHMAN_DIFF_BASE plus a cheap in-process pass over the rest.
8. **433 against ticket_github.py**: comments() is per-ticket and bodies only; a
   comment's slot needs its issue's label (two paged listings); GitHub's `since`
   filters on updated time, so record handled ids; filter out the service's own
   comments; effective_at = created_at.
9. **442 against the CLI**: the TUI refuses without a selected asset and the first
   connection claims the process, so `open` needs an exemption from REQ-PIPE-363 c6,
   and an extraction's collection shorts become top-level command names.
10. **443's NFR "fonts and vendor self-contained, as today" is not true**: fonts load
    from fonts/ beside the page.

## Reuse
hand_filing.file_supply and s3_source (loading); bootstrap/checkpoints' admin
pattern (create/drop), plus marking the new database's identity (db_identity) and a
gate that data_asset_id equals the folder name; cli/env.py's database ages; 446 c6's
refusals largely exist; check.py's per-gate rows (a new partial not-applicable
state); the adapter registry loads by path (shared adapter resolved there); 436 half
done in embed (the gap is build_dashboard_data.py:896's cadence()); 434's defect
confirmed (filing.py:446-469); 435 as a new append-only qa table granted to the
publisher role, not decision_log; 444's commit via _git_short_sha; 437 via
tests/real_asset.py; 443 reuses publish()'s build sequence, not hosting.

## Command group
`mothman one-off` (open, load, decide, publish, drop, list). 433 is a stage in
`mothman pipeline process` before tickets.

## Order
434 → 438 → 436 → (433 any time) → 446 → 439 → 440 → 441 → 442 → 435 → 444 → 443
→ 437. Finding 1 blocks 440 for real until resolved.

## one-offs/<kind>/<id>/
Ids one namespace across assets and every kind; gate declarations per (gate, kind),
undeclared refused; shared vs per-kind: shared 434, 435, 442, 443, 446, 438's rollup,
444's decision panel - per kind 439, 440, 441, 444's recipe panel; the two-level
listing defeats assets.py's single-directory stat cache; ~200 dbt projects each
needing dbt deps (point at dbt_shared); validate-config.yml never checks one-offs.

## Its questions
1. Where committed one-off folders live while the repository is public.
2. `mothman check` over every one-off folder, or changed-only plus a digest pass.
3. A cross-table check between a derived and a counted table.
4. Local files and reports deleted with the database at drop.
