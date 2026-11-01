# Keith's decisions, 2026-10-31 evening to 2026-11-01 - the recovery record

Written 2026-11-01 after a replaced container lost every unpushed commit
(plans/running-thoughts.md #135). Every answer below was given by Keith in
conversation and is restated here from the main session's transcript so that
the rebuild needs no question asked twice. Drafts and builders read this file.

## Pass / Warn / Fail (pass-warn-fail-v1.yaml + reviews + answers in 3291b4c)
- v2 Q1: the promoted-then-re-checked heading is 'Promoted, then failing on
  re-check' (and 'warning on re-check'). Replaces the 2026-10-29 wordings
  'Promoted green, re-checked amber', '1 re-checked red after promotion' and the
  heading 'Promoted, then re-checked <verdict>' in seven built criteria
  (v2's A19, A28-A34). REJECTED 'Promoted, then re-checked: became Fail'.
- Sign-off: "approve all but significant changes I've not already discussed".
  All four requirements (REQ-DASH-359, REQ-TEST-360, REQ-TEST-361,
  REQ-DOCS-362) and every amendment SIGNED 2026-11-01, including the five
  word-for-word wordings (REQ-DASH-225 c2/c5, REQ-DASH-226 c8, REQ-DASH-227 c5,
  REQ-DASH-337 c9), which apply the count form and 'Promoted, warning'.
- BUILD ORDER: Pass / Warn / Fail, then geocoding, then the asset split.
- TICKET DUPLICATE: accepted and noted (ticket_sync._already_said compares
  worded bodies; one duplicate 'Still failing' comment per open ticket if the
  disabled workflow is re-enabled). Not fixed.
- #289 D8d (trend axis labels overprint) and D8e (a not-evaluated point drawn
  as a 0% dip) are fixed IN this batch, D8e test-first.
- At build: (1) the re-checked-worse reason CARRIES the promotion date, from
  the decision log ('was promoted passing on <date>'); (2) the template keeps
  its own copy of the words, held equal to status-cases.json by a parity test -
  accepted; (3) checklist rows that only show for data the synthetic history
  may lack are checked by zero count only - enough.
- The register must not claim proofs not yet run: each criterion whose proof
  waits on the end-of-run bootstrap goes in unmet_criteria with blocked_by
  {unowned: true}, owner 'the end-of-run bootstrap (2026-11-01 build run)',
  cleared once it passes, before the push. Applies to every batch.

## REQ-TEST-374 (the provisional-choice gate) - signed 2026-11-01
- post-build-review #292: every PROVISIONAL choice goes on the morning report's
  question list, AND `mothman check` WARNS (never fails) on PROVISIONAL markers
  in BUILT requirements.
- The ~188 markers already present are written once to a committed,
  shrink-only baseline; only new ones warn; the check fails if the baseline
  gains an entry. REJECTED sweeping them first, and warning on all of them.
- Tightened after its critic: an item is ANSWERED only if it says
  'SETTLED by Keith' or 'answered by Keith' followed by a date. Bare 'answered'
  and 'SIGNED by Keith' do not count. A quoted word (backticks or single
  quotes) is a mention, not a marker; REQ-TEST-374's own items quote the word.
- Six older answered markers are reworded to that form (meaning unchanged):
  REQ-PIPE-086 d29, REQ-PIPE-107 d19, REQ-TEST-114 d15, REQ-PIPE-151 d39
  (SETTLED by Keith 2026-10-06), REQ-PIPE-173 d12 (SETTLED by Keith
  2026-10-11), REQ-DASH-204 d32 (answered by Keith 2026-10-23).
- Its baseline file sits at the repo root beside requirements.yaml.

## REQ-PIPE-341 (multi-column sample keys) - signed earlier, rebuilt
- A check whose failure judges the whole table and names no row (Birth
  Registrations' freshness check; datacontract-cli's duplicate check on a
  non-key column) DECLARES `names_no_row: true` (a Soda attribute or a contract
  customProperty). The criterion-5 gate and every sampler honour that one
  declaration; verdicts unchanged. REJECTED a metric check, and sampling the
  newest record.
- A failing row whose key is NULL is recorded with an EMPTY key part (shown on
  the page as '(no value)'), never as the text 'None' and never dropped - for
  every tool (Soda and dbt dropped them too). Criteria 7 and 8 amended:
  'AMENDED 2026-11-01 (Keith, post-build-review #294): a failing row whose key
  is null is recorded with an empty key part, never as the text None and never
  dropped.'
- validate_soda warns (rather than silently skipping) on a failed-rows check
  whose table declares no key.

## Geocoding (REQ-QAC-294..REQ-PIPE-341 batch, signed 2026-10-31)
- v7 delta (docs/drafts/geocoding-v7-delta.yaml) SIGNED, every change, with
  the FINAL TEXT of amendments A1, A5, A6, A7, A8; A2, A3 and A4 wordings SIGNED
  too. 'WORDING NOT YET SIGNED' becomes 'WORDING SIGNED by Keith 2026-10-31'.
- 'notchecked' is DISPLAY ONLY: no tool can record it; the store refuses it; a
  check that ran and errored stays Fail.
- Signing A4 settles linkage's 18:00 due time; REQ-GEN-334's 'DUE 18:00, NOT
  14:00' decision is no longer provisional.
- REQ-GEN-295 criterion 5 AMENDED: a record's CODES are fixed every quarter;
  its match level follows that quarter's address columns (criterion 6, GA2 a).
  REJECTED fixing the match level.

## Asset split (asset-split-v2.yaml in 3291b4c, plus everything below)
- Agency page's second section is headed with the collection's configured
  name, e.g. 'Linkage Products for 2026-Q2'.
- ORDER: the split first, then REQ-PIPE-255/257/258 built per asset; the daily
  asset's publish is refused in between.
- The pre-split snapshot archive is DELETED from the tree (not served); git
  history NOT rewritten.
- LAYOUT: one folder per asset, `assets/<asset>/`, holds everything for it:
  data-asset.yaml, the agency folders (contracts, Soda, Evidently), `dbt/` (a
  dbt project of its own: models/, tests/, retired/ per collection),
  `collections/` (QA adapters), `synthetic/` (generator providers under
  synthetic/collections/, scripted_decisions.yaml, synthetic_inputs.yaml,
  eras.yaml). contract/ is RENAMED assets/. Shared macro and generic dbt tests
  in one shared local dbt package (dbt_shared/). The shared code tree holds no
  per-collection file. Diagram: docs/drafts/repo-layout-after-split.svg (both
  assets name a Cloudflare project).
- Adapters and providers are LOADED BY PATH (importlib), not a package - Keith
  first chose a package, then switched on hearing it would tie assets/ to this
  repository and complicate #55's injected configuration. A spawned process is
  handed the asset AND the collection id.
- Nothing per-collection is shared between assets, so no cross-asset id check.
- The move map (assets/moved-paths.yaml) is DELETED in the push after the move,
  with the code that reads it; a one-off check in that push confirms it.
- Daily publish held by a SETTING in each asset's data-asset.yaml (only
  quarterly holds it until REQ-PIPE-255 gives daily its own project); a refused
  publish exits NON-ZERO and points to `mothman dashboard rebuild`.
- C1, CLAUDE.md's three snapshot statements, SIGNED AS DRAFTED (one archive per
  asset; 'one deliberate deletion, not a precedent'; 'licenses no other
  deletion').
- daily_batch.py and each apply_*_presets fold INTO their collection's provider
  file (pandas/numpy imported inside functions).
- `mothman population` takes MOTHMAN_ASSET and applies only that asset's
  presets.
- A setting version moves to eras.yaml if it is BACK-DATED or its changelog
  calls it a 'synthetic era' (plus its 'era ends' version).
- Interim gap ACCEPTED: no moved notice until REQ-PIPE-354; the moved notice
  fires on DEEP LINKS ONLY, no home-page note, no persistent masthead link.
- Demo tab on BOTH sites, captioned on quarterly.
- Signed as v4 with the scoper's choices: A43 (REQ-TEST-160 c1, providers out of
  the replay inputs), cross-asset feedback links kept where moved_to covers the
  route else dropped, the requirements drawer is repository-wide, the
  snapshots_from key, an emptied setting level is removed, 'Day: latest',
  automated publishes gated by config.
- REQ-PIPE-369 criterion 6 AMENDED: coverage `source` plus
  `include_namespace_packages` (include is ignored when source is set).
- Groundwork first (an asset resolver that maps today's contract/ as one
  asset), then ONE move commit proven by REQ-TEST-239, then four post-move
  streams; the ~200 hard-coded data/report paths become per-asset call-time
  lookups before the move.

## #134 (generator and bootstrap separation)
- The code half is queued behind the split, scoped only once geocoding is fully
  signed (it is).

## Build run terms (2026-11-01)
- Order: 341 and 374, then PWF, then geocoding, then the split; parallel
  streams in separate worktrees; critics per batch; questions to Keith.
- No bootstrap, no full gate between batches; targeted tests only.
- ONE bootstrap per asset at the end, then one full gate, one push, one CI run.
- Every checkpoint pushed to `wip/build-2026-11-01` ([skip ci]).
