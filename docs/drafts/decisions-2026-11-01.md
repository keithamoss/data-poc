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
- COUNT FORM (rebuild, 2026-11-01): in a count list the re-check reads
  '1 failing on re-check after promotion' (and 'warning on re-check after
  promotion'); the HEADING stays 'Promoted, then failing on re-check'.
  REJECTED '1 promoted, then failing on re-check' (the comma reads as two
  things) and dropping the comma.

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

## Rebuild sign-offs (2026-11-01, after the lost container)
- PWF v2 regenerated: signed as drafted, with the COUNT FORM above applied
  (A35-A39, A28's promotion-date wording and D8d/D8e as REQ-DASH-359 c18/c19
  accepted under "approve all but significant").
- Asset split v4 regenerated: Keith signed the scoper's five new choices as
  drafted - REQ-PIPE-352 c3 per-asset scenario check; REQ-GEN-371 c5 eras.yaml
  frozen with data-asset.yaml as one combined history; REQ-GEN-370 c8 an asset
  with no synthetic/ folder runs, only generate refused; REQ-PIPE-372's setting
  named publish_to_gh_pages, removed once REQ-PIPE-255 is built; the quarterly
  Demo caption text.
- PWF build-time wordings, SETTLED by Keith 2026-11-01 (all four accepted):
  the warehouse clause's pill reads the verb ('..., and is passing'); the
  re-check panel reads 'was passing; on re-check it is failing'; with no
  verdict the heading reads 'Promoted, then worse on re-check'; D8d's trend
  axis shows short dates and drops the middle label when it would collide.
- running-thoughts #132 is DELETED under the delete-on-built rule once its
  decisions are carried into REQ-DASH-359; REQ-DOCS-362 c4 gets an explicit
  carve-out (it means 'do not reword history', not 'never delete a built
  entry'). SETTLED by Keith 2026-11-01.
- `mothman lp qa --folder` trials what the folder holds: the tables present
  are checked against what is in place in the warehouse for the rest, as a
  real arrival is. REPLACES the rule that a trial needs all 3 tables (no
  Linkage Products delivery carries all three). SETTLED by Keith 2026-11-01.

## Overnight (Keith 22:2x Perth, 2026-11-01: "Keep going overnight as far as you can")
- Same build-run terms. Keith is asleep: a question a builder cannot settle from
  this file takes the recommended option, marked PROVISIONAL in the
  requirement's decisions with the question worded for Keith, and is listed in
  the morning report's question list (REQ-TEST-374 c5). Nothing waits on him.
- Order: geocoding fixes -> REQ-GEN-298 -> REQ-DASH-299; split groundwork ->
  state-path sweep -> the move -> four streams; then one bootstrap per asset,
  clear proven unmet_criteria, full gate, ONE push to
  claude/qac-024-explanations-qx8hx8, check CI, write the morning report in
  plans/morning-reports.md.
- Anything significant (a defect needing a product decision, a criterion that
  cannot be met) is stopped and reported, not decided.
- STOPPED OVERNIGHT, FOR KEITH (the move, 2026-11-02 early): after the move each
  asset keeps its own generator bookkeeping, so quarterly receipts' sequence
  numbers restart within the asset (order kept) and two quarterly delivery
  directories are named differently. All 614 delivery FILES are byte-identical.
  REQ-TEST-357 c3 ("the compare reports no difference") cannot hold as signed.
  Recommendation: the compare normalises per-asset sequence numbering and
  delivery-folder names, and c3 is amended to say so - a shared cross-asset
  counter would break the isolation the split exists for. Alternative: change
  delivery naming so it does not depend on the sequence.

## Keith's morning answers (2026-11-02, morning report 12)
- A1 SETTLED by Keith 2026-11-02: the equivalence compare NORMALISES per-asset
  receipt sequence numbers and delivery-folder names (comparing contents and
  order); REQ-TEST-357 c3 is amended to say so. REJECTED a shared cross-asset
  counter (breaks isolation) and sequence-free delivery naming.
- A2 SETTLED by Keith 2026-11-02: REQ-GEN-295 c7's drift-warning planning is
  computed from the same inputs the real drift check uses (reference and
  current value counts), replacing the fitted 'red source with blank address
  fields' rule; c7 is amended to say verdicts are planned from the not-geocoded
  share AND the drift check. REJECTED accepting the fitted rule, and dropping
  drift planning.
- B2-B10, B12, B13 SETTLED by Keith 2026-11-02 as RECOMMENDED (shared scenario
  quarters accepted; ordinary geocoding faults allowed in linkage-scenario
  quarters; one geocoding scenario a quarter kept; TS-93c/100c/101b keep their
  letters; resupply re-sends only the failed files from the latest source;
  inheritance left unmodelled for the replay to judge; year faults 1-3 records;
  trials one per core; drift reference the last PROMOTED earlier delivery;
  tile words per dataset; Geocodes tile names its source without a period).
- B1 CHANGED by Keith 2026-11-02 (against the recommendation): a Linkage
  Products folder trial ALSO reads a staged, undecided supply in the period,
  as a real arrival's overlay does (REQ-PIPE-202 d17). To BUILD.
- B11 CHANGED by Keith 2026-11-02 (against the recommendation): a NULL middle
  part of a sample key reads '—', as REQ-DASH-299 c8's letter says, the same
  as an empty one (REQ-DASH-299 d36). To BUILD.
- B14 SETTLED by Keith 2026-11-02: the withdrawal of REQ-DASH-299's
  PROVISIONAL #4 is confirmed; mark that item answered. The gate's rule is
  unchanged.
- C1-C5, C8-C10, C14-C16 SETTLED by Keith 2026-11-02 as RECOMMENDED
  (environments.yaml shared; `mothman check` per-asset gates per asset with
  the tools once; asset named in confirmation prompts; bare mothman checks the
  asset before the terminal; module-name pattern and clash refusal confirmed;
  tidy-test-databases exempt; dbt scratch and ticket files per asset; feedback
  cross-asset links accepted until REQ-PIPE-354; scenario table accepted until
  REQ-PIPE-352 c3; the move map's member lists and dbt_shared coverage).
- C13 SETTLED by Keith 2026-11-02 as recommended: both dbt projects renamed
  mothman_<asset> in the follow-on push; recorded unique_ids change once.
- CHANGED by Keith 2026-11-02 (against the recommendation), all to BUILD:
  - C6: "dbt packages installed" is decided by dbt's own package-lock.yml,
    not a stamp file (REQ-QAC-368 d5).
  - C7: a repo-relative path request for an asset folder outside the
    repository REFUSES (REQ-PIPE-342 d18).
  - C11: every test module names its asset; no quarterly default, and an
    unmarked module is refused (REQ-PIPE-363 d12).
  - C12: no forwarding macros file; each asset's dbt project points
    macro-paths and test-paths at dbt_shared; REQ-QAC-368 c2 amended.
- D1 CHANGED by Keith 2026-11-02 (recommended was scope first): FIX NOW. Linkage
  Products releases read only source supplies whose file actually arrived, the
  same rule as geocoding (plans/qa-pipeline.md #89); a regenerated change to
  built REQ-GEN-334 deliveries, and the report lists every release that moved.
- END-OF-RUN PUSH WAITS for the fast critical CI set (running-thoughts #136,
  REQ-TEST next free above 374) to be signed and built, so the push runs the
  fast set, not the full test.yml (~145 billable minutes on a cache miss, with
  the month near its allowance). SETTLED by Keith 2026-11-02.
