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
- PLAN, Keith 2026-11-02 morning: once the in-flight builds finish (the move,
  the morning answers, the fast CI set), tonight returns to finishing the
  scoping of the rest of the split, "starting with the ..." (message cut off;
  CONFIRMED by Keith: the split-overview page's four decisions and #134
  v3, then the architect and UX reviewers). Notify Keith only when there is something to
  look at or an input is needed.
- The one-publish-path guard's named exception for `mothman debug
  snapshot-worktrees` (it pushes wip/<branch>-snap refs only, never publishes)
  is SETTLED by Keith 2026-11-02: kept, with its pinning tests made critical.
  REJECTED moving the push out of cli/, and removing the command. It had been
  added by the coordinator without sign-off; the REQ-TEST-375 critic caught it.
- THE MOVE CRITIC'S THREE DECISIONS, SETTLED by Keith 2026-11-02 afternoon:
  1. Feedback links' mistyped-agency check (REQ-PIPE-342 c8), dropped by the
     move because each asset knows only its own agencies: WAITS for
     REQ-PIPE-354. REJECTED reading every asset's hierarchy now.
  2. A scenario naming a dataset in neither asset (REQ-GEN-246 c8), now
     silently dropped by `scenario_injection.this_assets_injections`: WAITS
     for REQ-PIPE-354, and meanwhile the drop is made VISIBLE (a warning
     naming each dropped scenario), not silent. REJECTED reading both assets
     now, and waiting silently.
  3. The settle pointer on a one-collection asset (`supply_files.where_to_settle`
     names a collection step the menu skips): the POINTER DROPS the collection
     step when the asset has one collection; the menu is unchanged. REJECTED
     always showing the collection picker.
- SCENARIOS.md AFTER THE MOVE, SETTLED by Keith 2026-11-02 ~21:55 Perth:
  (a) build REQ-PIPE-352 criterion 3 (one SCENARIOS-<asset>.md per asset,
  generated from that asset's own history) INSIDE the move, before it
  merges. REJECTED (b), merging the move with the scenario-map gate red
  until c3 is built separately.

## Keith's answers to morning report 12's 14 questions (2026-11-03, Perth)
- Q1 SETTLED by Keith 2026-11-03 (as recommended): the PAGE is right. The
  dataset-list row counts cross-table verdicts too, so a Warn or Fail the
  warehouse holds shows on the row even when the period on show has no supply
  (REQ-DASH-225 c18 keeps the page as the reference). REJECTED amending the
  test to leave cross-table sections out, and making the page say no verdict.
- Q2 CHANGED by Keith 2026-11-03 ("get rid of it"): REQ-DASH-299 c15(7)'s
  whole check - no nine-digit run AND no area code on a geocoding page - is
  REMOVED, criterion and test. REJECTED amending the pattern, excluding
  identifier cells, and masking Client Register ids on the page.
- Q3 CHANGED by Keith 2026-11-03 (against the recommendation): REQ-TEST-361
  c1 keeps 'a re-checked-worse supply' and the 'Re-checked <t>: became <X>'
  row, but they are covered by a JS test (tests-js/, jsdom) against mock data,
  not the real page; the real-page guard scans what the data shows.
  REJECTED planting a scenario for each, and dropping them from c1.
- Q4 CHANGED by Keith 2026-11-03: the synthetic ANCHOR_DATE becomes ROLLING
  (follows the build date) rather than a fixed date bumped by hand. Needs
  scoping before building (reproducibility and the equivalence compare depend
  on a fixed anchor) - plans/running-thoughts.md #138. Until it is built the
  anchor stays 2026-09-25. REJECTED a one-off bump, and leaving it fixed.
- Q5 SETTLED by Keith 2026-11-03 (as recommended): each asset's scenario map
  lists the scenarios its OWN asset placed, plus those naming one of its
  datasets; an unplaced scenario naming no dataset is in neither map (the
  register in plans/supply-model.md still holds everything). REJECTED
  unplaced-in-both, and keeping membership from the injections table.
  Replaces REQ-PIPE-352's PROVISIONAL membership choice.
- Q6 SETTLED by Keith 2026-11-03 (as recommended): the dropped-scenario
  warning stays quiet about scenarios belonging to the OTHER asset - reading
  both assets' hierarchies, configuration only, to tell them apart - and warns
  only for a dataset NEITHER asset declares (the typo case). This narrows
  2026-11-02's "wait for REQ-PIPE-354" for the warning only: the refusal of
  REQ-GEN-246 c8 still waits (see Q8). REJECTED a one-line summary, and the
  full list on every run.
- Q7 SETTLED by Keith 2026-11-03 (as recommended): the settle hint checks
  the same condition the filing menu does - it names the collection step
  whenever the menu will ask it (corrections, parked moves or nudges pending)
  and leaves it out otherwise. REJECTED accepting the gap, and changing the
  menu.
- Q8 SETTLED by Keith 2026-11-03 (as recommended): RESTORE BOTH NOW, using
  the both-hierarchies configuration read Q6 allows - the feedback validator
  catches a mistyped agency again (REQ-DOCS-219 c10) and a scenario naming a
  dataset neither asset declares is refused again (REQ-GEN-246 c8); both
  unmet criteria clear. This REVERSES 2026-11-02's "wait for REQ-PIPE-354"
  for these two. REJECTED adding them to REQ-PIPE-354, and a new requirement.
- Q9 SETTLED by Keith 2026-11-03 (as recommended): for an asset folder
  outside the repository the dashboard BUILDS, leaving that asset's GitHub
  links out with a quiet note that its configuration is not in this
  repository. REJECTED refusing the build.
- Q10 SETTLED by Keith 2026-11-03 (as recommended): the pre-run check uses
  the same package-lock rule as `mothman env dbt-deps` and REFUSES on stale
  packages, naming `mothman env dbt-deps`; one meaning of "installed"
  everywhere. REQ-QAC-368 c6 amended. REJECTED keeping it as signed.
- Q11 SETTLED by Keith 2026-11-03, wording approved as written:
  REQ-TEST-357 c2 ends "...collection by collection, normalising the
  data_asset_id segment REQ-QAC-344 renames and the database identity row,
  and the delivery names and receipt sequences criterion 3 lists."
  REQ-QAC-368's title becomes "Each asset has a dbt project of its own under
  assets/<asset>/dbt/, taking the shared macros and generic tests from
  dbt_shared/ through its macro-paths and test-paths, and its packages are
  installed by `mothman env dbt-deps`".
- Q12 SETTLED by Keith 2026-11-03 (as recommended): NO regression test for
  the .devcontainer/post-create.sh wiring fix - the hard-coded path is gone
  and the script calls the one command that knows the paths. REJECTED a test
  that every dbt path named in the setup scripts exists.
- Q13 CHANGED by Keith 2026-11-03 (against the recommendation): the schedule
  gate's git-ref guards (agreement freeze, amber, replacement and list-setting)
  REFUSE an asset folder outside the repository only when a deployment has
  deliberately injected its asset root elsewhere (REQ-PIPE-342's injection);
  other outside paths keep reading as "no previous state". REJECTED refusing
  every outside folder (moving nine tests' copies inside the repository), and
  never refusing.
- Q14 SETTLED by Keith 2026-11-03 (as recommended): C7's line stays as built
  - only code building a repository path refuses an outside asset folder;
  plain file readers accept one (REQ-PIPE-342 d20). REJECTED refusing in
  every reader.

## The split overview's decisions (Keith, 2026-11-03, Perth)
- SPLIT D1 SETTLED by Keith 2026-11-03: the cut is right - each asset defines
  its own hierarchy, calendar and time zone in assets/<asset>/; shared code
  that only READS those definitions sits in one package the real pipeline and
  the generator both import; the generator, bootstrap and scenarios stay out
  of a real deployment. CHANGED: the package is named `asset_model/`, not
  `domain/` (which read as though it held the definitions). REJECTED shared/,
  model/ and core/. #134 v3 (docs/drafts/separation-v3.yaml) to be re-drafted
  with the new name.
- SPLIT D1b SETTLED by Keith 2026-11-03 (as recommended): ONE calendar
  mechanism for every asset (named calendars of authored dates, each dataset
  picking one), with per-asset dates; a project extraction with no cadence is
  a calendar with no slots. REJECTED a per-asset calendar plug-in.
- SPLIT D2 is decided FILE BY FILE (Keith 2026-11-03). people.yaml and
  data-asset.yaml stay COPIED in each asset with NO agreement gate (as
  recommended): each team owns its own; the shared lines are format and
  comments. REJECTED a shared default for either. file-checks.yaml and the
  dbt package files: pending.
- SPLIT D2, file-checks.yaml, SETTLED by Keith 2026-11-03 (as recommended):
  ONE SHARED default for every asset (beside dbt_shared/), which an asset may
  add to or override; a new file-level check reaches every asset at once.
  REJECTED a copy per asset, with or without a gate.
- SPLIT D2, dbt packages, SETTLED by Keith 2026-11-03 (as recommended): every
  asset uses the SAME dbt packages and versions; the per-project packages.yml
  and package-lock.yml stay (dbt needs them in each project) and a gate FAILS
  if they differ. REJECTED packages per asset, and one shared install folder.
- SPLIT D3 SETTLED by Keith 2026-11-03: the three per-tool copies of an
  allowed-value list (ODCS contract, Soda, dbt) STAY - the tool comparison is
  still running and one or more checks, or a whole tool, will go. The QA
  adapter's statistics READ THE LIST FROM THE CONTRACT at run time (as
  recommended), so its hand copy (_SUBURB_VALID and any like it) goes; the
  contract is the copy that survives whichever tool is dropped. CHANGED: the
  generator's pools (generator/names_au.py) stay INDEPENDENT - test data need
  not follow the rule exactly. REJECTED declaring once with every tool
  reading, an agreement gate, one check per rule, and the contract driving the
  generator. Applies to every collection, not only Civil Registration.
- SPLIT D4 SETTLED by Keith 2026-11-03 (as recommended): the near-copies JOIN
  #134 - the status order moves into asset_model/; the Child Protection
  provider reads the quarterly calendar and the older providers (dirty.py's
  fault rates) read thresholds through the readers Linkage Products uses; the
  hand-written geocoding verdict table is derived. They go to the scoper with
  #134 v3, #137's groups B-D, and the new work from D2 (a shared
  file-checks default; the dbt-packages agreement gate) and D3 (adapters read
  allowed values from the contract). REJECTED status order only, and waiting.
- NEXT (Keith 2026-11-03): with all four split decisions made, #134 goes back
  to delivery-scoper for a v4 carrying them, then to the architect and the
  CLI and dashboard UX reviewers before sign-off.
- SPLIT RISK 5 (geocoding check files) SETTLED by Keith 2026-11-03: KEEP
  HAND-WRITTEN - each geocoded source's Soda, dbt and contract sections stay
  their own hand-reviewed artefact, although only three facts differ between
  sources. REJECTED a template from the three facts, and waiting for a third
  source.
- SPLIT RISK 6 (status copies inside the dashboard page) SETTLED by Keith
  2026-11-03: LEAVE THEM - RECHECK_RANK, xtStatusCounts' order list and
  XT_WORD ('No result') stay as they are. REJECTED reading STATUS_ORDER from
  both repeats, and one wording everywhere.
- Q6/Q8 FOLLOW-UP (answers critic H1) SETTLED by Keith 2026-11-03: no change.
  Scenarios exist only for SYNTHETIC assets, and both synthetic assets are
  always present together for demo and test, so the both-hierarchies read
  always finds both; a single-asset injected deployment is a real one, which
  carries no scenarios. Recorded as the premise of the read. REJECTED staying
  quiet when the other folder is absent, and deferring to REQ-PIPE-354.
- REQ-PIPE-342 c8 AMENDED, wording approved by Keith 2026-11-03 as written:
  append "except that the generator's scenario check and the feedback
  validator may read every asset's data-asset.yaml, configuration only, to
  tell another asset's dataset or agency from a mistyped one (Keith,
  2026-11-03)."

## Keith's answers to #134 v4's eleven open questions (2026-11-14, Perth, one at a time)

- Q1 (REQ-PIPE-380, the generator's drift planning) SETTLED: option (a) - one
  small drift module in asset_model/ holding fold_value_counts, status_for,
  excluding, psi_of_counts and compute_psi, pandas and Evidently imported
  inside functions only; the generator and the real run_evidently both call
  it. REJECTED: a second PSI copy in the generator; a permanent allowlist entry.
- Q2 (REQ-PIPE-379, what "one mechanism" covers) SETTLED: option (a) - both
  calendar shapes as today (authored dates and the daily cadence rule), and
  `no_calendar: never` stays how an extraction has no slots. REJECTED: authored
  dates only; an extraction naming an empty calendar.
- Q3 (REQ-QAC-387, overriding the shared file checks) SETTLED: option (a) - by
  check name: a same-named `check:` replaces the shared entry whole, a new name
  adds an asset-only check, and `retired_as_of` on an override stops a shared
  check for that asset. REJECTED: field-by-field inheritance; additions only.
- Q4 (REQ-QAC-389, Emergency Department's age_group) SETTLED, NOT THE
  RECOMMENDATION: option (b) - the ten bands become a real allowed-values rule
  on the column in the contract (`enum:`/validValues), so datacontract-cli
  checks age_group: a new check with its own lifecycle entry, and the
  statistics read the same list. REJECTED: a custom property no tool checks
  (the recommendation); a hand copy in the adapter.
- Q5 (REQ-GEN-392, dirty.py's fault rates) SETTLED, NOT THE RECOMMENDATION:
  option (b) - derive each rate from its check's bands at generation time (the
  rule, e.g. the middle of the band aimed at, to be set in scoping). Birth
  Registrations' and Child Protection's dirty supplies regenerate; every moved
  supply and verdict is listed, and the pins and scenario expectations built on
  today's history are re-captured with each move accounted for. REJECTED:
  literal rates checked by a gate (the recommendation); both.
- Q6 (REQ-PIPE-378, two "in force" policies) SETTLED, NOT THE RECOMMENDATION:
  option (b) - a date before a calendar's first version RAISES, for every
  caller. The callers that fall back today (claim windows, agreement_drift,
  participation_view, verdict.py) must meet the error and say what they do
  instead; the scoper and architect to name each, and REQ-TEST-239's compare to
  show whether any recorded result moves. REJECTED: falling back to the first
  version everywhere (the recommendation); keeping both, renamed.
- Q7 (REQ-PIPE-378, the cadence check made twice) SETTLED: option (a) - keep
  only the per-round check, against the version in force on each round's date.
  REJECTED: only the current-version check; keeping both.
- Q8 (REQ-PIPE-378, six look-ahead horizons) SETTLED: option (a) - one named
  horizon in asset_model/ for every look-up from now, relative_period counting
  within it; REQ-TEST-239's compare shows what moves. REJECTED: keeping each,
  documented.
- Q9 (REQ-PIPE-378, swallowed configuration errors) SETTLED: option (a) - the
  two slot helpers raise a ScheduleConfigError; NoCalendarAgreed keeps its
  deliberate quiet "nothing owed". REJECTED: keep swallowing.
- Q10 (REQ-PIPE-378, DatasetPeriod.round) SETTLED: option (a) - required; the
  two "or period" fallbacks go. REJECTED: leave it optional.
- Q11 (the new gates on a push) SETTLED: option (a) - the imports gate
  (REQ-TEST-384) joins validate-config.yml beside the other configuration
  gates, and its own tests are marked `critical`. Under Q5's answer the fault
  rates are derived rather than gated, so no fault-rate gate is needed.
  REJECTED: local gate only; critical tests only.
- NEXT (Keith, 2026-11-14): update the split overview artifact with these
  answers; Keith takes another look; then v4 goes back to delivery-scoper and
  on to delivery-architect, delivery-cli-ux and delivery-dashboard-ux.

## Two quick decisions (Keith, 2026-11-14)

- post-build-review #321 (validate-config.yml ran with no asset): NO
  regression test. The fix stands; a future workflow that forgets the asset is
  caught by its first red run. REJECTED: a test reading every workflow.
  (To be recorded in post-build-review #321 once the running suite finishes -
  plans files are read by tests, so they are not edited mid-run.)
- running-thoughts #139 (/tmp leftovers): REMOVE /tmp/tmp* and /tmp/mothman-*
  once nothing is running that could use them - after the current suite run.
  (Also to be recorded in #139 then.)

## Speed scoping (#318, #136; Keith, 2026-11-14, one at a time)

- S1 SETTLED: a generation and a bootstrap PIN the asset's configuration once
  per run - read at the start, used throughout, with slots and periods derived
  from it worked out once. An edit made mid-run is seen by the next run.
  REQ-PIPE-254 criterion 15 (read whole on every call) stays for everything
  else: the pipeline, the CLI, the dashboard build. REJECTED: caching by file
  change; pinning everywhere (withdrawing criterion 15).
- S2 SETTLED, NOT THE RECOMMENDATION: the replay inside a bootstrap ALSO runs
  the real pipeline on the pinned configuration - the pipeline gains a pinned
  mode used only by the synthetic replay; outside a bootstrap it reads as now
  (criterion 15). REJECTED: profiling first and deciding later (the
  recommendation); pinning the generator only.
- S3 SETTLED: the suite generates ONCE and shares - one generated history per
  test session (or a cached one keyed by the generator's inputs), read-only to
  every test that needs it, a cheap copy for a test that must change it;
  measured with --durations before and after. REJECTED: smaller test-only
  histories; both.
- S4 SETTLED: S1-S3 go to delivery-scoper as their own batch AFTER the #134 v5
  reviews (so the two don't overlap), then the architect, then Keith's
  sign-off. Likely touches: REQ-PIPE-254 criterion 15's scope, REQ-PIPE-352's
  12-minute budget, and a new test-suite requirement (#136). REJECTED: scoping
  in parallel now; folding into #134.

## Rolling anchor date scoping (#138; Keith, 2026-11-14, one at a time)

- R1 SETTLED: only a real regeneration of the DEMO data (reset + bootstrap)
  rolls the anchor; the test suite and CI always build from one fixed test
  anchor, so the arrival pin, the CI bootstrap cache key and REQ-TEST-239's
  compares stay byte-stable. Accepted cost: tests exercise one fixed date, not
  the demo's. REJECTED: everything rolls (pins rewritten relative to the
  anchor; CI cache missing on every roll).
- R2 SETTLED: a demo regeneration rolls the anchor to TODAY on the asset's own
  clock (its time zone), and the date used is recorded with the history so a
  re-run with that date reproduces the same bytes. REJECTED: start of the
  week; the last quarterly round.
- R3 SETTLED: the dashboard and `mothman` say which date the demo data was
  generated up to; regeneration stays a deliberate reset + bootstrap.
  REJECTED: a scheduled regeneration; a staleness warning.
- R4 SETTLED: a regeneration REPLACES the whole history - the generated
  delivery and receipt files and the database (the existing typed-confirmation
  reset) - with one history up to the new date; a guard test proves two
  regenerations on different dates leave one history, not two. REJECTED:
  archiving the previous history.
- R5 SETTLED: R1-R4 go to delivery-scoper together with the speed decisions
  (S1-S3), after the #134 v5 reviews - one scoping pass for both, since both
  change how generation and bootstrapping get their inputs. REJECTED: a
  separate later batch; scoping now in parallel.

## Check timing scoping (#120; Keith, 2026-11-14, one at a time)

- T1 SETTLED (Keith first chose every check, then on the follow-up about how
  shared Soda queries and whole-tool runs would be split: "on second thought,
  let's just time the run"): ONE real elapsed time per QA RUN, recorded with
  the run, never from the replay's simulated clock (qa.run's created_at and
  completed_at are replay-clock stamps in a synthetic history - 6.3 days for
  one quarterly run - so they cannot be used). REJECTED: every check (needs
  each tool run per check, or shared time invented); per tool per run.
- T2 SETTLED: shown on the dashboard as a run-time trend per dataset (each
  supply's run time over its history) and beside each run in the supply
  history, and printed by `mothman` when a run finishes. REJECTED: dashboard
  only; CLI and logs only.
- T3 SETTLED: a run taking more than twice the median of that dataset's
  previous runs is marked 'slow' on its trend point and in the supply history;
  it never changes a dataset's Pass/Warn/Fail or blocks anything. REJECTED:
  trend only; a configurable per-dataset rule.

## Failed attempts scoping (#121; Keith, 2026-11-14, one at a time)

- F1 SETTLED: EVERY ATTEMPT of a run is kept - its number, real start and end,
  how it ended (completed, timed out, crashed, tool error) and the error's
  message; a retry adds an attempt rather than erasing the last (today
  reopen_run clears completed_at and the results are replaced). Each attempt
  carries its own run time (T1). REJECTED: only a failed-attempt count and the
  last reason.
- F2 SETTLED: a run that needed more than one attempt carries a short note in
  the supply history (e.g. "Succeeded on attempt 2 - attempt 1 timed out after
  45 min"), and the run's detail lists every attempt; the dataset's
  Pass/Warn/Fail comes from the successful attempt only. REJECTED: detail only;
  lifting the supply to Warn.
- F3 SETTLED: a run whose last attempt failed and is not yet retried shows as
  "Not checked - the run timed out" (or crashed), with when and the error; its
  checks read "No result", never a stale Pass from an earlier supply; the
  dataset's status reflects that the supply could not be checked, as today's
  "could not run" does. REJECTED: failing the supply.
- ROUTING (#120 + #121) SETTLED: one batch to delivery-scoper, then the
  architect and the dashboard and CLI UX reviewers, AFTER the #134 v5 reviews
  and the speed + rolling-anchor batch. REJECTED: joining the speed batch;
  scoping now.

## #130 small-count suppression, scoped with Keith 2026-11-14

Purpose recalled: insurance for a real deployment's published QA page; REQ-QAC-333 c9 keeps the large-key-group histogram exact (Keith, 2026-10-30) and said suppression, if ever needed, is one generic rule on the binned-distribution field, not a linkage case.

- **SC1 scope:** scope it now, generic.
- **SC2 threshold:** optional, per check, declared beside the bin edges (e.g. `suppress_below: 5`); no default, so off unless a check asks.
- **SC3 where the count stops:** recorded exact in qa.*; the dashboard build writes `<N` in its place, so the published page and its embedded data never carry the small number.
- **SC4 back-calculation from the total:** accepted and documented - only bins under the threshold are hidden; the total stays exact and can be differenced. REJECTED complementary suppression and hiding the total.
- **SC5 first user:** none - large key groups stays exact (REQ-QAC-333 c9 unchanged); proved by tests on a test check declaring a threshold.
- Routing: to the scoper after #134, with the other queued batches.

## #134 v5 review batch - Keith's answers, 2026-11-14 (one at a time)

- **QA (architect, clock):** (a) NEUTRAL CLOCK EVENTS - asset_model's clock offers plain events ('received at X', 'a decision takes effect at Y'); the wall clock ignores them, an installed replay clock acts on them; the pipeline imports nothing of the replay and no recorded instant moves. REJECTED (b) a grown hook protocol threaded into promotion, (c) v5's two hooks with rule-made decisions no longer moving the clock.
- **B1 (architect, two times):** MERGE to one clock, as v5 says; promotion's effective-at and the equivalence harness are rewritten to read it. Confirmed when asked again: promotions in the synthetic history get new effective times, listed in the compare and ACCEPTED, as REQ-PIPE-382 does for anchors. REJECTED keeping two readings (stamp vs today). Note for the scoper: QA's events still apply; what no longer holds is QA's 'no recorded instant moves'.
- **B3 (architect, scenario map):** ALL INTO scenarios/ - the TS register parser, the placements reader, the map vocabulary and the scripted_decisions.yaml reader; the generator keeps the map writer; status_words moves with the status order into asset_model/ (REQ-PIPE-390); the dashboard keeps only read_map_data. SUPERSEDES the overview's 'the TS register's parser goes to bootstrap/'. REJECTED the writer moving to the bootstrap.
- **QB (architect, arrival recognition):** INTO asset_model/, its charter widened to 'configuration and the delivery tree, never the database'; arrivals_from_records (database and S3) stays in the real pipeline; generate-synthetic-data keeps writing placements with run ids. REJECTED moving the checks into the bootstrap, and a permanent allowlist entry.
- **QC (architect, population --dirty):** ITS OWN LITERAL RATES, held in synthetic_data_generator/ as exploratory defaults, not the asset bands. REJECTED reading both assets' bands (a third exception to REQ-PIPE-342 c8), and requiring one asset.
- **QD (architect, equivalence captures) - ANSWERED AS: DELETE THE EQUIVALENCE COMPARE EVERYWHERE** (Keith, 2026-11-14, dictated): "Just delete the equivalence thing, I told you I do not care. Synthetic [can] be removed. We have tests approved and we don't need to assure that [the] demo hasn't moved - a layer of additional testing [we don't need]." The same stance as plans/supply-model.md's "I don't care. This is all just fake data" and morning report "I don't care about reviewing the list of moved verdicts". So:
  - every "proven by REQ-TEST-239's compare" criterion and BEHAVIOUR-PRESERVING NFR comes out of #134 (about 18 across the batch); the TEST SUITE is the proof, and the synthetic history may move;
  - no equivalence captures are taken; B1's "listed in the compare and accepted" falls with it - the history simply regenerates;
  - asked how far: DELETE IT EVERYWHERE - propose retiring REQ-TEST-239's harness (built) and rewording REQ-TEST-357 (signed, asset split) to "proven by the test suite". Exact wording to Keith before any register edit (changes to built/signed requirements).
- **CLI A (pipeline run):** NEVER GENERATES, on any asset - processes what has arrived, then builds; help text true everywhere; generation is only generate-synthetic-data and the bootstrap; a real asset's first run (REQ-GEN-381 c2). REJECTED generating on synthetic assets only, and making it synthetic-only.
- **CLI B (QA wizard's Synthetic source):** Q3 COVERS IT FULLY - on a real deployment the Synthetic source is not offered, --run-id/--reference-run-id are not listed in qa --help, and passing one is refused by name. REJECTED hiding the choice but keeping the flags, and leaving both with a run-time refusal.
- **CLI C (synthetic-only check gates on a real deployment):** 'NOT APPLICABLE (no synthetic/ folder)' ROWS for providers, scenarios and scenario map; the closing and paste-into-commit lines say 'every gate that applies passed' and name them. REJECTED leaving them out of the table, and showing them as passed.
- **CLI D (scenarios bands):** Keith asked why a human would ever run it; explained (REQ-GEN-183's debug print of check_bands, rarely run, and REQ-GEN-392's refusal names an empty band anyway). DELETE THE COMMAND and its tests; check_bands stays for the generator and REQ-GEN-392. REJECTED keeping it synthetic-only, and moving it to debug. NOTE: REQ-GEN-183's own claims name the command - a built-requirement edit, wording to Keith.
- **Dash A (broken schedule config on the page):** THE BUILD REFUSES, naming the dataset and the file; the live page stays at the last good build. REJECTED (b) one asset-wide notice with the build continuing (recommended; it matched the 2026-10-25 'one bad file no longer blocks the page' call - this answer narrows that call for schedule configuration), and (c) hiding it. embed_dashboard_data._slots_by_dataset and period_slots.py line 47 stop catching ScheduleConfigError.
- **Dash B (a step stopped by a configuration error):** YES, A NEW BLOCKING KIND IN THE 'NEEDS A PERSON' QUEUE (outstanding.py), naming the configuration, so the page says why a supply is missing - as its own small requirement rather than widening REQ-PIPE-378. REJECTED CLI and log only.
- **Dash C (synthetic-assuming page text):** FOOTER ONLY - gated on the asset's synthetic: true (through REQ-PIPE-382's single reader); the Demo tab stays, labelled as a recording. REJECTED gating the Demo tab too, and deferring.
- **Dash D (old scenario links on a real asset):** A PLAIN NOT-FOUND PAGE at /scenarios (renderNotFound), echoing the URL's word back. REJECTED the overview with one neutral line (recommended), and a silent drop. Open for the scoper: how ?panel=scenarios and ?scenario= are treated under this answer (not-found as well, or dropped).
- **Scoper 380 Q1 (check-file readers):** (a) check_lifecycle's parsing half and collect_checks' working-tree read MOVE INTO asset_model/; the git-comparing gate stays in the pipeline. REJECTED deciding mid-build, and a second parser.
- **Scoper 378 Q1 (participation versions):** CALENDAR VERSIONS ONLY - the participation fallback (slots._participation_for, REQ-PIPE-113 c2) is unchanged, a period before a dataset's first participation version keeps reading 'not owed'. Explained first: under (b) the CP build would likely refuse (Dash A) over a dataset that merely starts later than its calendar. REJECTED participation too.
- **Scoper 378 Q2 (orchestrate._claim_window on the error):** (c) FALL BACK TO THE ADAPTER'S claim_window_dataset. REJECTED (a) leaving the dataset out of the minimum (recommended), and (b) raising. Note for the scoper: this is a deliberate borrowed window in one place, an exception to Q6's 'never borrow', and _claim_window's docstring rule ('never a borrowed one', REQ-PIPE-243 c2) changes with it.
- **Scoper 378 Q2 - ANSWER WITHDRAWN** (Keith, 2026-11-14: "that was the wrong response, I hadn't decided yet"); the "fall back to the adapter's" line above no longer stands. Example asked for and given; still open.
- **HORIZONS PARKED (Keith, 2026-11-14)**: Q3 (the one horizon's reach) and Q4 (look-aheads from a given date), after the 17 sites were listed for him: "that needs a separate focused bit of thinking ... I'm not happy with the shape of that, guessing random numbers." Q8's 'one named horizon' is reopened with them - the shape, not just the number, is in question. Not in #134's build until that thinking happens.
- **#130 PARKED, NOT TO BE BUILT** (Keith, 2026-11-14): scoped (SC1-SC5 above) then parked - "I can't remember the actual reason I wanted it ... if I look at how the dashboard has linkage keys I might remember". Supersedes SC routing 'to the scoper after #134'. Trigger to revisit: Keith looking at Linkage Keys on the dashboard.
- **STANDING (Keith, 2026-11-14, said twice in one sitting)**: "I do not give two shits if the synthetic demo history moves. That can happen whenever." No requirement proves the synthetic history unchanged; it is regenerated whenever a change needs it.
- **Scoper 378 Q2, RE-ASKED with an example:** (a) LEAVE THE DATASET OUT of the shortest-window minimum, none if none remain - the function's own 'never a borrowed one' rule stands. Noted when explaining: it caps only the replay's simulated pass delay (live it is simply now), and (c) would raise too, because the adapter's default dataset has no early window either. REJECTED raising.
- **Scoper 389 Q1 (new ED check's introduced_date):** 2013-01-01, its siblings' date; the changelog and the requirement record when it was written. REJECTED the build date.
- **Scoper 392 Q1 (Warn size):** THE MIDDLE of the aimed rules' amber intersection at the frame's row count, in rows, rounded down (targeting._target's rule). REJECTED lower third, upper third.
- **Scoper 392 Q2 (Fail size):** THE LOWEST FAILING COUNT PLUS THE WIDTH OF THE RULE'S AMBER BAND. REJECTED 1.5x and 2x the fail line.
- **Scoper 392 Q3(i) (single-tier rules):** A Warn preset plants NOTHING on a single-tier rule (as REQ-GEN-184); a Fail plants a FIXED 5 ROWS, declared once beside the derivation (told plainly it is a chosen number - it only sets how many failing rows the page shows). CP's amber partial resupplies move from Fail to Warn. REJECTED planting in Warn presets, and 1 row.
- **Scoper 392 Q3(ii) (how a size is planted):** EXACTLY THE DERIVED COUNT, as targeting's _set_nulls. REJECTED per-row probability.

**BATCH STATUS, 2026-11-14:** every question answered except the parked horizons (378 Q3, Q4, with Q8 reopened). Still to come to Keith: the exact wording to retire REQ-TEST-239 and reword REQ-TEST-357 (and REQ-GEN-183's command claim); whether to delete the rarely-run CLI commands listed for him (equivalence, build-warehouses, changelog, capture-arrival-golden, sync-tickets/leaderboard, the rebuild steps, cache-key, population). Then: v6 from the scoper with all of the above and the architect's six blocking findings (B2 answered by QA, B4-B6 are criteria fixes), then the artifact.
- **RETIRING THE EQUIVALENCE HARNESS - WORDING APPROVED (Keith, 2026-11-14, 'Yes, as worded')**, to apply after the suite run, in the same push:
  1. REQ-TEST-239 -> retired, no replaced_by, reason: "Retired by Keith, 2026-11-14: the synthetic demo history may move whenever a change needs it, and the test suite is the proof that a refactor is sound. A before-and-after capture of a ~58-minute bootstrap proves something nobody needs proved. The `mothman debug equivalence` commands, their module and their tests are deleted."
  2. REQ-TEST-239 dropped from the dependencies of REQ-PIPE-240, REQ-QAC-242, REQ-GEN-246, REQ-PIPE-254, REQ-PIPE-250, REQ-PIPE-265, REQ-PIPE-331, REQ-PIPE-332, REQ-GEN-295, REQ-PIPE-341, REQ-GEN-370, REQ-GEN-349, REQ-TEST-357; their own text unchanged.
  3. REQ-TEST-357 retitled "The move to two assets changes nothing a collection records, generates, builds or offers - proven by the test suite and the existing pins, never by re-capturing them"; criteria 2 and 3 retired with item 1's reason.
  4. REQ-GEN-183's `mothman scenarios bands` claims removed when #134 deletes the command.
- **TO CHECK (found 2026-11-14):** all 20 asset-split requirements (REQ-PIPE-342..REQ-DOCS-358) read not_started though assets/ exists and commits adapted tests to the split - the register looks stale against the code.

## Evidence walk-through (docs/drafts/unmet-evidence-2026-11-14.md), Keith's answers 2026-11-14

- **[14] REQ-GEN-298 c3/c4, TS-107 and TS-111:** each also shows drift Fail from a reference gap (2013-Q4 held, 2025-Q4 TS-110's refused empty file) - Keith's 2026-10-04 gap rule working, the scenarios placed straight after gaps. DECIDED: MOVE THE TWO SCENARIOS to quarters whose previous quarter was accepted (a defect fix, test-first, written up in post-build-review once the suite run ends). REJECTED rewording c3/c4 to allow a gap red, and adding a target-check rule on top.
- **[4] REQ-PIPE-296 c3, datacontract-cli asks nothing of geocoding/linkage (no quality: blocks):** MET - 'run by all four tools' is enough; the reading goes in the evidence. REJECTED adding contract rules now (a new requirement if ever needed).
- **[2] REQ-GEN-295 c2 and [21] REQ-PIPE-341 c7 (proofs by the equivalence compare):** RETIRED under retired_criteria with REQ-TEST-239's reason, in the same register change. REJECTED rewording to 'by the suite'.
- **[8] REQ-PIPE-296 c7, [13] REQ-GEN-298 c13, [16] REQ-DASH-299 NFR 6 (before/after timings, only 'after' exists):** RECORD THE 'AFTER' FIGURES as evidence (bootstrap 6666s; trials 43 supplies in 53s on 4 workers; page size/e2e duration to be read off the current build), RETIRE THE 'BEFORE' HALVES (nobody needs the history). The bootstrap at ~9x its 720s budget goes to the speed batch (S1-S4) as its headline problem - not called met. REJECTED capturing befores, and retiring all three.
- **[9], [28], [29] (GitHub):** NOT YET for a hand-started test.yml - [9] and [29]'s hand half wait for the next merge to main, when one is due anyway; the push's critical run is read for [28] and [29]'s push half.
- **[20] REQ-QAC-340 c11, [23] REQ-PIPE-341 c8 (on-demand thirty-dataset tests):** RUN LOCALLY after the suite's push, own MOTHMAN_TEST_DB_TAG, timed, result and duration as evidence.
- **[18] REQ-QAC-340 c8 out-of-scope half (geocoding in a source-not-supplied quarter):** PROVEN BY A TEST driving the real pipeline on a test database, seen failing first if the rule does not hold. REJECTED planting a scenario, and leaning on linkage's proof.
- **[25] REQ-DASH-359 c14 (recorded text inside its mark on the built page):** THE JS TESTS ARE ENOUGH (tests-js/pass-warn-fail, rechecks, withdrawal) - recorded as the evidence on Keith's reading, wording unchanged. REJECTED adding a real-browser test.
- **[27] REQ-DASH-359 c16's checklist half:** RETIRE THE CHECKLIST - the e2e half and the colour-word guard are enough. REJECTED an after-only checklist and rebuilding a before page.
- **[30] REQ-TEST-375 c9 (whole mothman check):** THE CHUNKED SUITE with combined coverage against fail_under PLUS mothman check --no-pytest is the stand-in - recorded as met with this run's figures and the reason a whole run cannot finish here (the 2-hour background-job limit). REJECTED making check resumable, and a whole run.

**WALK-THROUGH COMPLETE (2026-11-14).** Register edits to make after the suite: the evidence and verdicts above, the retired criteria and halves, with the REQ-TEST-239 change. Still to do: TS-107/TS-111 move (defect fix, test-first, post-build-review entry), the [18] test, the [20]/[23] on-demand runs, reading [28] off the push's critical run.
