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
