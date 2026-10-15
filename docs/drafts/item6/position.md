# Item 6: the main session's position (round 0, before the scoper)

Keith, 2026-10-15 ~23:40 Perth: research, form my own view, take it through
delivery-scoper (a couple of rounds), delivery-architect and the UX reviewers,
and bring back a fully scoped, architected and reviewed proposal - "happy for
you to make those decisions", with the significant calls listed for him to
sense-check. Evidence: `docs/drafts/item6/groundwork.md`.

## Settled by Keith already
- Generalise BEFORE the Emergency Department (ED) dataset; ED is the first
  collection added the new way; the Child Protection shrink waits on it.
- Done means a **small adapter per collection** - shared per-tool code plus one
  short module per collection for what genuinely differs. Not config-only; not
  only fixing dispatch points.

## My calls (each marked SIGNIFICANT where Keith should sense-check it)

1. **Shape**: the groundwork's recommended shape - shared per-tool modules
   built from Child Protection's (N-table) code, a collection registry derived
   from `contract/data-asset.yaml`, one adapter module per collection behind a
   `CollectionAdapter` Protocol, one `COLLECTION_DATA` const in the dashboard.
2. **Byte-identical refactor first, behaviour changes after.** Every refactor
   step leaves a from-empty bootstrap identical to a baseline taken before it
   (qa tables, supply digests, deliveries, receipts, raw tool output with
   volatile keys normalised, results and dashboard JSON). Drift between the
   copies is preserved behind named legacy flags on the Birth Registrations
   adapter, and each flag is retired later as its own small change that is
   allowed to change output. Never mix a refactor and a behaviour change.
3. **SIGNIFICANT - the recorded shapes unify on Child Protection's N-table
   forms** when the flags retire (results JSON, dataset stats, dashboard JSON,
   Evidently raw output). Birth Registrations' history is regenerated, as
   synthetic history already may be (REQ-PIPE-038/144). This is the point at
   which Birth Registrations stops being a special case.
4. **Run prefixes and CLI short names are declared** in data-asset.yaml
   (`short: bdm|cp|ed`, `run_prefix: run_|cp_run_|ed_run_`), not derived -
   deriving them would rename every recorded Birth Registrations run.
5. **SIGNIFICANT - Evidently check definitions move out of Python** into
   `contract/<stem>-evidently-checks.yml`, so every tool's checks are found the
   same way and a collection's checks are all configuration. Check ids and
   prose do not change; the authoring standard is untouched.
6. **Per-check presentation metadata (labels, dimensions, columns) stays in
   the adapters for now.** Moving it into the check files would roughly halve
   the adapters but changes the check files' structure; logged as a follow-up,
   not part of this work. Adapters land at ~230/~260 lines rather than ~100/~120.
7. **The generator gets a shared driver** (slot loop, bookkeeping, delivery
   writing, injection placement) with providers and period plans per
   collection - and it comes BEFORE ED rather than after, so ED's generator is
   an adapter from day one rather than a third copy to unpick later. It is the
   riskiest step for byte-identity (random draw order), so it is last among
   the refactor steps.
8. **Target trial (Birth Registrations only) becomes an optional adapter
   capability**; anything without it is refused by name, replacing the two
   silent fallbacks in `generator/targeting.py`/`targets.py`.
9. **SIGNIFICANT - AWS (the CDK stack and the two ingest Lambdas) is scoped
   OUT** of this work and logged as its own follow-up: it is not on the
   bootstrap or dashboard path, and parametrising it is cheap once the
   registry exists.
10. **A gate, not a convention**: `mothman check` fails when a hierarchy
    collection has no adapter or an adapter names no collection, when
    `short`/`run_prefix` collide, when an adapter keys a table outside its
    collection, and when a hierarchy id or run prefix appears as a literal
    outside `contract/`, the adapters and the scenario register (closes
    REQ-QAC-039 criterion 1). An adapter's QA/dashboard part is reported
    against a soft budget of ~150 lines, never enforced.
11. **Tests follow the code**: the 36 test modules that monkeypatch
    per-collection attributes move to the shared modules in the step that
    moves the code; no test is kept that only proves a deleted module is gone.
12. **Requirement split**: about eight requirements rather than one per step -
    harness; registry, gate and every dispatch site; check sources (incl.
    Evidently YAML); the four tool runners and staging; stats, results and
    orchestrator; dashboard (Python builder and consts) and CLI factory;
    generator driver; legacy-flag retirement and shape unification. Each
    refactor requirement carries the same two criteria: the bootstrap equals
    the baseline, and the per-collection files it replaces are deleted.
13. **Outside the delegation, to Keith**: REQ-PIPE-170 criterion 31's
    "both collections" -> "every collection" (built); approve in the registry
    step.

## Round 3 calls, after the dashboard UX review (main session)

14. **Zero-run collection vs missing entry** (dashboard UX finding 1):
    ADOPTED - a registered collection with no runs emits an entry with every
    declared dataset and an empty history, rendering the existing
    never-supplied / not-owed-yet notice; only a declared collection with NO
    entry fails the embed, naming the collection, the expected file and the
    command that makes it, writing no page; and `mothman check` catches an
    unwired collection before any build.
15. **SIGNIFICANT - one missing collection fails the whole build** (UX Q1):
    kept as (a). With call 14's gate an unwired collection never reaches a
    build, so a missing entry means a builder crashed - and publishing a
    page that silently lacks a collection is the false quiet item 6 exists to
    remove. Rejected (b), a "results not built" tile, for now; revisit when a
    real deployment has more than a handful of collections.
16. **SIGNIFICANT - a dataset's "View on GitHub" opens its ODCS contract,
    anchored at the dataset** (UX Q2 (b)), not the adapter: the contract is
    what the dataset is held to; the tooltip names the target. This replaces
    round 2's call 5.
17. **SIGNIFICANT - the agency-level pill is removed** (UX Q3 (a)): no single
    file stands for an agency once an agency owns several collections, and a
    link to a config entry answers no reader's question. A second visible
    change, with a CHANGELOG line.
18. ADOPTED: collections iterate in hierarchy order; dataset ids unique
    across collections (a `mothman check` gate) with one dataset-id index; each
    collection's entry self-contained (an NFR, so lazy loading stays possible
    later); S6 captures each dataset page by cold-loading its URL.

## Round 3 calls, after the CLI UX review (main session)

19. ADOPTED, all four REQ-TEST-245 gaps: the TUI/group label rule (see 21),
    with a tui_drive check of the "Which dataset?" menus; `--help` imports no
    tool library (pandas, duckdb, soda, dbt, datacontract, evidently) for
    every `mothman <short> [qa] --help`, measured against today's baseline
    first, and adapter declarations stay importable without tool code
    (a line in REQ-PIPE-243); a 30-collection fixture proves `--help` still
    imports nothing and lists every group, with absolute times recorded; a
    collection whose adapter cannot load never takes down the CLI - its own
    commands refuse by name, everything else works, no traceback. One shared
    `--collection` helper in cli/common.py with a registry-generated legend.
20. ADOPTED for REQ-TEST-239: S7 captured with fixed COLUMNS and NO_COLOR=1;
    named surfaces (`--surfaces` takes names or codes, `--help` lists all
    seven); capture refuses an existing label unless `--yes`, prints the
    baseline path, and on failure drops its scratch database, leaves no
    readable baseline and names the failed stage; compare refuses a reduced
    baseline against a full one, naming both.
21. A one-table collection is labelled by its DATASET's name in TUI menus and
    group help, an N-table one by its collection's name - reproducing today
    exactly ("Birth Registrations", "Child Protection"). Rejected: collection
    name always (changes what users see, mid-refactor); a declared display
    label (one more field, nothing needs it yet).
22. The CLI at 30 collections (help panels, grouped/searchable picker, short
    hint forms) is NOT in this series - it is behaviour change, so it waits
    for its own requirement once the collection count grows; logged as
    plans/running-thoughts.md #101.
23. FOR KEITH (a genuine fork): is "~30" thirty COLLECTIONS each with its own
    command group, or a handful of collections holding ~30 datasets? It sets
    the 30-collection fixture's realism and #101's priority; nothing in the
    series is blocked on it.

## Round 4 calls, after the architect review (main session)

24. **SIGNIFICANT - proof strategy: captures by commit, in a git worktree,
    chained** (architect E1a). `capture --ref <sha>` runs that commit's own
    code in a worktree against a scratch database, so there is no module
    patching and the harness is never edited per step; requirement N's
    "after" is N+1's "before"; the dashboard and CLI steps use cheaper
    surfaces (S5/S6 rebuilt from one kept database; S4 regeneration, S7, the
    reduced corpus); one full end-to-end compare from before REQ-PIPE-240 to
    after REQ-GEN-246. About 4-5 hours of captures rather than ~10. Scripted
    decisions stay ON in a full capture; only `--reduced` turns them off. The
    harness refuses an asset not declared synthetic and records a harness and
    normaliser version, refusing to compare across versions; named exclusions
    apply on every surface. Rejected: a full before/after per requirement
    with module-patching redirection (the series deletes what it patches).
25. **Legacy flags on BOTH adapters** (E2a), replacing the "Child Protection
    has none" criterion: the copies are a NEAR superset, not a strict one -
    the Soda `[scope]` check-name suffix (Birth Registrations), Child
    Protection's empty Soda dimensions on 88 checks, divergent
    row_count_invalid branches, dbt model-level-test routing and test-shape
    sampling. Every refactor step stays byte-identical; the reader-visible
    flags (the suffix, the empty dimensions) are added to REQ-QAC-247's
    retirement list. Rejected: changing Child Protection's output inside a
    refactor step.
26. **The fake-collection proof runs in a repo copy** (E3a): git archive of
    HEAD to a temp dir, the fake's files added there, `mothman` run from the
    copy against a scratch database, and the copy's diff against HEAD
    asserted additions-only in the allowed paths. Rejected: in-process
    redirection, which needs a single config root across 41 modules first.
27. **Each dispatch site is rewired once** (E4a): REQ-PIPE-240 rewires only
    the sites whose code survives the series (processing_pass, recheck,
    checkpoints, bootstrap incl. resume(), the lifecycle and source lists,
    github_links, ticket_sync); every other site sits on the shrinking
    allowlist and is rewired, with its third-collection test, by the
    requirement that rewrites its file.
28. ADOPTED, the rest of the architect's findings: seed schedules are a
    provider method and a genuine never-retired difference, with every seed
    a provider can derive inside its declared range; `AGENCY_BLURB` moves to
    presentation config in REQ-DASH-244, and the scenario register's
    exemption names `INJECTIONS` and `INHERITING_DATASET` only; the gate adds
    unique table names and dbt singular-test names across collections and a
    run_prefix of `[a-z0-9_]` that fits PostgreSQL's 63 bytes with every
    suffix and `adhoc_`/`ref_` form; **each collection's dbt models, sources,
    schema and singular tests live under `dbt_project/models/<collection_id>/`
    and `dbt_project/tests/<collection_id>/`**, the runner scoping nodes by
    the adapter's table set; Evidently YAML dates quoted (or coerced to str)
    so config_hash cannot move, and the base side's sources derived from the
    base ref's own hierarchy, with the legacy Python reader time-boxed; the
    adapter is per-tool sub-objects (`.dbt`, `.soda`, `.datacontract`,
    `.evidently`, `.staging`, `.stats`, `.present`); S6 adds the page's own
    `buildDatasetsOn()` output for sampled as-of dates; S7 adds the TUI menu
    text; the CI 5% NFR is replaced by back-to-back sandbox timings with a
    threshold set from the self-check's measured noise.
