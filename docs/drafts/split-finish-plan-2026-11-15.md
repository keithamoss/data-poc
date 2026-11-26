# Finishing the asset split - draft plan, 2026-11-15

Keith, 2026-11-15: "Finish the split before #134." Source: the audit at
`docs/drafts/asset-split-status-2026-11-15.md` (31 requirements, every one
still `not_started` in the register). This is a plan only; nothing is built
or edited from it until Keith answers the questions at the end.

## The 31 sort into two kinds

**The STRUCTURAL split** - one repository, two asset folders, each with its
own database, state, gates and CI. About 18 requirements, most of them
partly built. What is left is mostly tidying up and small gaps.

**FEATURES that arrived with the split** - two new collections, weekday
participation, hosting per asset and a period control. About 13
requirements, none started, each a real build. Cloudflare needs accounts
outside this repository. The period control depends on Cloudflare
(DASH-355 depends on PIPE-354) and on both new collections (DASH-356).

## Proposed tranches

**T0 - Make the register tell the truth (register edits only, after the
suite).** Flip PIPE-363 to built. QAC-368 is built once c9's
changelog-gate half is confirmed. Every partly-built requirement becomes
`in_progress`, its unmet criteria entered with `blocked_by`. No code
changes.

**T1 - The leftovers of the move (small; one builder).**
- Delete the move map, its reader and the check-id transform
  (TEST-366 c3/c4, QAC-344 c6, PIPE-342 c2). It is overdue: Keith said "I
  don't want moved paths hanging around". QAC-344 c8 needs his approval of
  the rename exception recorded.
- Add a shared-tree gate and retire the stale `EXEMPT_DIRS`
  (PIPE-342 c10).
- Per-asset gates (PIPE-364):
  - prefix each failure with the asset;
  - refuse a stray file at the top of assets/;
  - add a two-asset fixture covering each refusal, and the case where both
    assets reuse a collection id.
- Fix the two setup scripts:
  - the session hook counts `supply_<asset>` (PIPE-352 c4);
  - the devcontainer marks each asset's database (PIPE-343 c4).
- `env mark` takes the asset id (PIPE-343 c1).
- A wrong-asset test points each asset at the other's real database
  (PIPE-343 c8).
- Coverage reads assets/ (PIPE-369 c6, TEST-353 c9).

**T2 - Calendar names out of shared code (small-medium).** Do PIPE-345 c1-c7:
- each asset has one baseline calendar;
- collections stop declaring `calendar:`;
- the `== "daily"` and `"quarterly"` tests in shared code go;
- add a gate.

**T3 - State and CI per asset (medium).**
- PIPE-365 c3: the cache key covers the selected asset only.
- PIPE-365 c5: run one asset beside the other's populated folder and
  compare the results byte for byte.
- TEST-353: one cache per asset, bootstraps side by side, a per-asset
  restored/rebuilt line, and ci-usage evidence. c4 was BUILT DIFFERENTLY
  (one pytest session per asset), see Q3.

**T4 - What the synthetic side still owes (GEN-370 c3-c9, GEN-371
eras.yaml).** OVERLAPS #134 v6, see Q2.

**T5 - Close-out: TEST-357 c6 and DOCS-358** (amendments A1-A43 applied,
CLAUDE.md and README restated for two assets). This is last because it
restates whatever T1-T4 settle.

**Features, if they stay in "the split":**
- F1: weekday participation (PIPE-346, DASH-347).
- F2: Cancer collection (QAC-348, GEN-349).
- F3: Mental Health collection (QAC-350, GEN-351).
- F4: hosting (PIPE-372 refuse-publish, DASH-373 delete pre-split
  snapshots, PIPE-354 Cloudflare).
- F5: the period control (DASH-355, DASH-356, DASH-367).

F2 and F3 add bootstrap time to an asset already about 9x over its budget
(quarterly 6666s against 720s). The signed speed batch is the fix for
that, so they fit better after it.

## Questions for Keith, one at a time

1. **Scope.** Does "finish the split" mean the structural tranches T0-T5
   only, with the features after #134's core and the speed batch? Or all 31
   requirements? Recommended: structural only. The features are new
   behaviour, not the split being unfinished.
2. **T4 against #134 v6.** GEN-370 c4 moves `daily_batch.py` and every
   `apply_*_presets` into the asset folders. GEN-370 c6 stops population
   applying both presets together. v6 then reorganises the same code into
   `scenarios/`, and its QC answer has population keep its literal rates
   and dirty both assets in one process, which contradicts c6. Options:
   build T4 now and let v6 move it again; or retire or fold GEN-370
   c4/c6/c8 into v6 and keep only c3/c5/c9 (the read-nothing-under-synthetic
   tests and the provider-import gate). Recommended: fold.
3. **TEST-353 c4**, built as one pytest session per asset rather than one
   session for both. Options: amend the criterion to what was built, or
   rebuild it. Recommended: amend. It is simpler and already green.
4. **The golden fixture grew** (TEST-357 c4: 404 added lines for the
   geocoding datasets, nothing existing changed). Options: accept it as kept
   (amend c4 to "no existing line changed"), or treat it as a breach.
   Recommended: accept, given "the synthetic history may move".
