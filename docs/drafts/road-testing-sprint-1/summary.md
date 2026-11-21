# Draft: road-testing sprint 1, "where do I put my effort?" (plans/road-testing.md #1, #2)

Scoped by delivery-scoper on 2026-10-14 (Perth). Revised ~17:00 to fold in
Keith's answers to Q1-Q8, and again ~17:30 to fold in his answers to NQ1-NQ3,
the **delivery-dashboard-ux** review (`review-dashboard-ux.md`) and the
**delivery-architect** review (`review-architect.md`), with his answers to both.
Revised once more on the evening of 2026-10-14 to fold in his answers at the
sign-off readiness check (last section). **Still a proposal until Keith signs
the batch.** Nothing here is in `requirements.yaml` or `plans/`. No criterion is
PROVISIONAL and no open question remains; see "Ready for sign-off".

Requirements: `docs/drafts/road-testing-sprint-1/requirements-draft.yaml`

| Id | What | MoSCoW | Depends on |
|---|---|---|---|
| **REQ-DASH-224** | Two counting functions, one per unit: `unitCounts` decides red / amber / green / not counted per check, per column (worst check) and per check section, per **checked** QA run, keyed by run; `datasetStatusesOn(date)`, taken out of `buildData()`, gives every dataset's full status as of a date. File checks are out. Builds on post-build-review #181 (commit cf060e9). | must | - |
| **REQ-DASH-225** | Dataset list: "Columns not green" header; bold "3 of 15", "2 red, 1 amber · incl. Supply-level checks" beneath; two small lines to the right (red solid, amber dotted) on a fixed 0-100% scale over a neutral baseline; one key line above each collection table. | must | 224 |
| **REQ-DASH-226** | Agency cards: "2 of 8 datasets not green" (or "2 of 5 counted datasets not green"), red and amber in words, and a two-line trend of each dataset's full status on a weekly grid, labelled "Datasets red and amber, each week", under a 400ms budget for the tier. Collection headings on the agency tier get the same count line and the same two-line weekly trend. | must | 224, 225 |
| **REQ-DASH-227** | Dataset page: a new two-line red/amber trend with axis titles, the key under its title and "View as table"; the same style in the column panel and on the ~16px column tiles. | should | 224, 225 |
| **REQ-DASH-228** | A check's own chart names its measure, as horizontal text, from its rule kind through one mapping, with a completeness test reading committed configuration. | should | - |

Plus a **proposed amendment to signed REQ-DASH-180** (below), which takes the
turned-off clauses out of 225 and 226.

## Reviews folded, per requirement

Every finding went into a criterion, an NFR or a decision. Where a review
offered wording and it was sound, that wording was used. Numbering was kept:
a criterion that changed meaning was rewritten in place, and new ones were
appended.

### REQ-DASH-224 (13 criteria, was 11)
- **NQ1 (Keith: neither, split out).** c5 rewritten: reads `ds.columns` only,
  never `fileChecks` (architect L1). Decision records both rejected options and
  points at plans/running-thoughts.md #96. REQ-DASH-097 untouched.
- **Architect Q2 (Keith: only checked runs are points).** c1 now says a check
  with no entry on a run is not counted on it, with no carry-forward; c8 says a
  held, never-checked arrival adds no point. Decision cites the real figure:
  10 of 208 runs never checked (9 Child Protection, 8 of them cp-case-workers
  in months it owes nothing in; 1 Birth Registrations).
- **H1 (count vs last point).** Not adopted as carry-forward (Keith's Q2 answer).
  A decision explains why the two agree today: a never-checked run's only
  entries are always-inactive "No rule defined" placeholders, and **no check in
  the built reports has a gap between checked runs (0, both collections)**. The
  real-browser tests in 225 c18 and 226 c12 now assert the last point equals the
  count, so a future gap goes red rather than drifting.
- **H2 (two functions).** c7 rewritten: columns and checks through the unit
  counter, datasets through `datasetStatusesOn(date)` out of `buildData()`.
  Rejected: a Python precompute, or a second dataset-status routine.
- **M1** - new c12: points come from the runs in place or awaiting, as the pill
  clips them. **M2** - c6 keys by run_id, not date. **M3 / Keith Q3 (A)** -
  new c13 excludes retired checks from past points; the divergence from
  `datasetStatusByRun` / `status_by_run` is recorded as a decision.
  **M4** - c10 gains a test that drives the list row's real drawn trend
  (50% red / 0% amber where today plots 2 of 3 failing), so it fails on
  behaviour. **L2** - c4 finds sections by `scope`. **L6** - no Python twin,
  confirmed. Code shape (unitCounts, twoLineSparkline, datasetStatusesOn, the
  named rollup predicate, removing the floor and the dot) is a decision marked
  advisory.

### REQ-DASH-225 (23 criteria, was 18)
- **UX Q1 (A).** c1 header "Columns not green", unit only there; c3 bold
  "<N> of <M>"; c4 "2 red, 1 amber" beneath; c5 "· incl. Supply-level checks";
  c6 "All <M> green"; c8 lines to the right of the text.
- **UX Q2 (A) / G1.** c9 amber dotted with round caps (1.5,2.5), red solid, in
  --bad and --warn. Dashed is taken on the check chart (thresholds, "did not
  report").
- **UX Q4 (A) / G4.** c2 is now the key line above each collection table, with
  the review's sentence (minus file checks). Replaces the header note.
- **S1** - new c19, neutral baseline, colour only above 0%; c17 gains a test
  that an all-green history draws no red or amber stroke. **S2 / L3** - new c20,
  non-scaling stroke at least 1.5px. **S3** - new c21 "No column has a verdict on
  this date"; **declined** its "no lines" where history exists, citing Keith's
  #57 words. **G2** - new CONTRAST NFR (--warn, 3:1 in both themes, greyscale).
  **Minors** - new c22 ("One QA run so far" / no lines under two runs), c23
  (reason rows keep spanning the column), REUSE NFR, cold-load in c15.
- **B1 (b).** c16 keeps only the owes-nothing case, which REQ-DASH-182 c15 says
  already holds today; the turned-off case moves to REQ-DASH-180. REQ-DASH-180
  and 182 leave this requirement's dependencies.
- **M1** - the "per QA run" decision no longer says "including supplies later
  withdrawn". **M5** - c13 removes tests-js/sparkline-endpoint.test.js's dot
  assertions in the same change, keeping its `statusColorVar()` guard.
- **Sorting by red count** - out of sprint 1, recorded as a decision (not
  trivial: it changes what a row position means in links, tests and
  screenshots). The open question is gone. A plans/running-thoughts.md entry is
  drafted below for the main session to apply.

### REQ-DASH-226 (13 criteria, was 12)
- **NQ2 (B) + UX Q3 (A) + G6.** c9 is a weekly grid anchored on the date on
  show, each dataset's full status through `datasetStatusesOn`, as a share of
  that date's counted datasets, so the last point is the count. c8 label
  "Datasets red and amber, each week" with an accessible name.
- **NQ3 (A).** c7 two lines, no longer provisional.
- **UX Q5 (A) / G5.** c1 and c4 say "counted" when the rollup leaves some out;
  c3 puts the count line directly above the not-counted line. A decision records
  the interim gap until REQ-DASH-180 c10's partial line exists.
- **B1 (b).** c3 and c6 lose "turned off"; c11's test uses a no-schedule-agreed
  dataset and now reads "2 of 3 counted datasets not green". c3 uses rollup()'s
  filter lifted into one named predicate (architect code note).
- **H3 + G6.** New c13: the tier renders in under 400ms; trends may draw after
  first paint, one `datasetStatusesOn` per grid date for all cards, cached by
  date. NFR: memoise `datasetTile()` first (it is quadratic today) and measure
  with a 30-dataset fixture; if over budget, raise it with Keith. **Declined**
  the architect's "at most N points" cap, since it shortens history silently
  (decision).
- **L4 / UX minors.** c6: a quiet or "Not counted" card shows no count but keeps
  its trend, neutral, with its label. Cold-load in c10 and an NFR.
- **Collection headings (Keith, sign-off readiness check: count AND trend).**
  c5 rewritten: each collection heading gets the count line and the same
  two-line weekly trend as the card, over the collection's counted datasets.
  c6, c11, c12 and c13 now cover headings too. The performance NFR and c13 put
  card and heading trends under the one 400ms budget; headings share the cards'
  grid dates, so one `datasetStatusesOn(date)` per grid point serves all of
  them. The decision records the rejected count-only proposal. The open
  question is gone.

### REQ-DASH-227 (11 criteria, was 9)
- **UX Q4 (A).** c1 puts the key line under the trend's title, in the same
  sentence as the list's key.
- **UX Q2 (A).** c2 and c5 now say dotted.
- **Tiles call (Keith: two lines everywhere).** The decision is now confirmed,
  not "not asked".
- **S2.** New c10: tiles about 16px with non-scaling stroke, and no lines
  without a counted check or two checked runs. LEGIBILITY AT TILE SIZE NFR.
- **UX minors.** New c11 cold-load; c4 reuses the existing View-as-table toggle.
  c6 ends at the newest checked run (224 c12).

### REQ-DASH-228 (5 criteria)
- **UX minor.** c1: the measure is horizontal text above the plot's top-left,
  not rotated.
- **L5.** c4's completeness test reads rule kinds from committed configuration,
  not recorded results, so it runs in CI's fast half. A decision notes that the
  criterion 3 fallback covers a kind found only in old history.

## Amendment to REQ-DASH-180 (signed 2026-10-14, not started) - APPROVED (Keith, 2026-10-14)

Keith's answer to architect B1 was (b): the turned-off clauses leave sprint 1
and become part of REQ-DASH-180. Since that requirement is signed, this
amendment needed his approval in its own right. **He approved it as worded
below at the sign-off readiness check, 2026-10-14. It is to be applied to
`requirements.yaml` when this batch is signed, not before.** The wording below
is unchanged.

**Criterion 29 (new, appended).** OLD: none. REQ-DASH-180 ends at criterion 28,
which reads in the live file:

> IF a turn-off was authored after its effective_to, THEN THE SYSTEM SHALL show
> no 'Turning off after' marker for it on any date, and criteria 4 and 25 SHALL
> apply on their own terms.

NEW criterion 29:

> THE SYSTEM SHALL treat a turned-off dataset in REQ-DASH-225's and
> REQ-DASH-226's counts as criterion 7 treats it in the rollup: WHILE it is left
> out of its group's rollup, SHALL leave it out of the '<N> of <M>' on its agency
> card and collection heading (REQ-DASH-226 criterion 3); SHALL show on its
> dataset-list row the count and trend lines for the supply in place, just as
> its pill shows that supply's verdict (REQ-DASH-225); WHERE a group's status is
> 'Turned off', SHALL show no count line on it, never '0 of 0 datasets not
> green', and SHALL draw its trend in neutral ink with its label (REQ-DASH-226
> criterion 6); and SHALL extend REQ-DASH-226 criterion 11's tests-js test with a
> turned-off dataset owing nothing, written first and seen to fail, under which
> the agency still reads '2 of 3 counted datasets not green'.

**Dependencies.** OLD:

> REQ-PIPE-179, REQ-PIPE-110, REQ-DASH-182, REQ-DASH-071, REQ-DASH-155,
> REQ-PIPE-053, REQ-PIPE-181, REQ-PIPE-164, REQ-DASH-162, REQ-PIPE-115

NEW: the same list followed by **REQ-DASH-225, REQ-DASH-226**.

**Decision to add to REQ-DASH-180:**

> "SPRINT 1'S TURNED-OFF CLAUSES LIVE HERE (Keith, 2026-10-14, delivery-architect
> review of road-testing sprint 1, B1, option b). 'Turned off' did not exist in
> the page when REQ-DASH-225 and REQ-DASH-226 were scoped, so a criterion about
> it there could be neither built nor seen failing first. REJECTED holding
> sprint 1 until this requirement was built (option a)."

Nothing else in REQ-DASH-180 changes. Criterion 10's not-counted line is left as
it is. REQ-DASH-226 c3 only says where the count line sits relative to it.

## Build order (from the architect review, adjusted for B1)

0. **Groundwork, no visible change:** memoise each feed's dataset build so that
   `datasetTile()` stops rebuilding every Child Protection dataset per dataset,
   and lift `rollup()`'s live filter into a named predicate. Both serve 226 and
   are cheapest with nothing else moving.
1. **REQ-DASH-228**, which is independent and small.
2. **REQ-DASH-224**, the counting functions with their failing-first tests.
   `datasetStatusesOn` can wait until step 5 if that is simpler, but it belongs
   to this requirement.
3. **REQ-DASH-225**, the dataset list. The endpoint-dot test goes in this step.
4. **REQ-DASH-227**, the dataset page, column panel and tiles.
5. **REQ-DASH-226**, the cards. Measure the 400ms budget here, and stop and
   raise it if the budget is missed.
6. **The REQ-DASH-180 amendment**, built as part of REQ-DASH-180, not sprint 1.

## Ready for sign-off

**Nothing remains open.** Every open question is answered, the wording is
approved, the REQ-DASH-180 amendment is approved and the four judgement calls
are confirmed (Keith, 2026-10-14, sign-off readiness check). What is left is
Keith's own sign-off of the batch itself, which is his to give.

How each answer landed:

1. **Collection headings: count and trend.** REQ-DASH-226 c5 rewritten; c6,
   c11, c12, c13, the performance NFR and the budget decision extended to
   headings; a new decision records the rejected count-only option. Its open
   question is removed.
2. **Wording approved, zero parts kept.** REQ-DASH-225 c4 now always gives both
   numbers ("2 red, 0 amber"), and c17's test expects "1 red, 0 amber · incl.
   Supply-level checks". REQ-DASH-226's "<r> red, <a> amber" follows c4. A new
   REQ-DASH-225 decision records it, with the rejected omit-a-zero rule. The
   "proposed exact text" notes in 225 c2 and c5, 226 c8 and 227 c5 now read
   "Wording approved by Keith, 2026-10-14". The approved wording:
   - The key line (225 c2, also 227 c1): "Columns not green — [solid] red ·
     [dotted] amber, share of columns on each QA run. Supply-level, table-level
     and cross-table checks each count as one column."
   - The row's second line (225 c4/c5): "2 red, 1 amber · incl. Supply-level
     checks", and "2 red, 0 amber" where there is no amber.
   - Empty and short states (225 c21, c22): "No column has a verdict on this
     date"; "One QA run so far".
   - Card and heading trend label and accessible name (226 c8): "Datasets red
     and amber, each week".
   - Dataset page (227 c1, c3, c5): "Columns red and amber, each QA run" / y-axis
     "% of columns"; panel "Checks on this column red and amber, each QA run" /
     "% of checks"; grid label "Each column's lines: share of its checks red
     (solid) and amber (dotted), each QA run".
3. **The REQ-DASH-180 amendment: approved**, marked so above, to be applied
   when the batch is signed.
4. **The four judgement calls: confirmed.** Each decision now ends "Confirmed
   by Keith, 2026-10-14, at the sign-off readiness check":
   - No carry-forward for a check missing from a checked run (224, "WHY THE
     COUNT AND THE LAST POINT AGREE").
   - The architect's point cap declined (226, "THE TIER HAS A BUDGET").
   - S3's "no lines" declined where history exists (225, "NOTHING TO COUNT
     READS AS NOTHING TO COUNT").
   - The interim gap until REQ-DASH-180 c10 (226, "'COUNTED' IN THE WORDS").

## Non-functional angles: what I settled and what I ruled out

- **Settled myself, now with the reviews folded in:**
  - **Scale.** One count per row, one shared scale, and cards carry counts
    rather than names.
  - **Accessibility and contrast.** Red and amber are given in words and by
    line style (solid vs dotted), with --warn reaching 3:1 in both themes and
    the two readable in greyscale. Every trend has a text equivalent, and axis
    titles are horizontal text.
  - **Performance.** The unit counter is one pass. The card trend now has a real
    budget: under 400ms for the tier, memoised builds, trends after first paint,
    measured on a 30-dataset fixture, covering card and collection-heading
    trends together.
  - **The build rule.** Everything is computed in the page from embedded
    recorded results, with no supply rows and no Python precompute.
  - **As-of correctness.** Every figure is judged on the date on show, with
    tests at a past date and cold-loaded links.
  - **Compatibility.** No new assets, so file:// and offline viewing are
    unaffected. A phone is not a target.
  - **Maintainability.** Two counting functions, one per unit, with no Python
    twin. The rule-kind mapping is guarded by a fast-half test, and the
    obsolete endpoint-dot test goes in the same change as the dot.
  - **Test-first claims that can fail.** Every browser test asserts its subject
    exists first, and one unit test fails on behaviour, not just on a missing
    name.
  - **Observability.** These changes are CHANGELOG.yaml-worthy.
- **Ruled out as not applying:** security, privacy, compliance and retention,
  and cost (counts only, nothing new stored or computed server-side). Also
  reliability, since these are pure page computations with no network.

## Carry-over check (the source threads and both reviews against the draft)

- #1, the Trend column plots a rate: REQ-DASH-224, "rate in the line stands".
- #1, the endpoint dot is the run's worst status: REQ-DASH-225, "no endpoint dot", plus c13 (the test goes too).
- #1, the aria-label is the only text: REQ-DASH-225 c12.
- #1, the per-check chart's missing y-axis title and "Value" header: REQ-DASH-228.
- #1, "a falling line means different things": REQ-DASH-227 CONSISTENCY NFR and REQ-DASH-228.
- #1, the 0.05 floor: REQ-DASH-225, "one fixed 0-100% scale".
- #1, named in place or a different treatment: REQ-DASH-225, "named in place".
- #1, "Rows, latest run" read as the same series: not needed as its own criterion, as before.
- #2, worst-of is deliberate: REQ-DASH-226, "the pill stays worst-of".
- #2, checks or columns: REQ-DASH-225 (Q1) and REQ-DASH-226 (Q4, datasets).
- #2, what Tier 1 shows / where the count sits / how many amber and red: REQ-DASH-225 and 226, as before.
- "Every red looking the same stops triage at 30": scale NFRs on 225 and 226.
- The Trend defect: post-build-review #181, cited by REQ-DASH-224.
- UX review S1-S3, G1-G6, minors, Q1-Q5: all placed, as listed under "Reviews folded". One part declined, with a decision: S3's "no lines" where history exists.
- Architect review B1, H1-H3, M1-M5, L1-L6, code notes, build order, Q1-Q3: all placed. Declined with decisions: H1's carry-forward (Keith's Q2) and H3's point cap.

## Draft entry for plans/road-testing.md (for a human to apply, replacing the Sprint 1 bullet)

```
- **Sprint 1 - "where do I put my effort?" (#1, #2; M).** SCOPED 2026-10-14 by
  delivery-scoper as REQ-DASH-224 to 228, with Keith's Q1-Q8 and NQ1-NQ3 answers,
  the delivery-dashboard-ux and delivery-architect reviews and his answers to
  both folded in the same day. Awaiting his sign-off
  (docs/drafts/road-testing-sprint-1/), together with a proposed amendment to
  REQ-DASH-180 that takes over the turned-off clauses. The Trend defect found
  while scoping was fixed separately first (post-build-review #181). 224 is the
  counting (columns per checked run, and datasets' full status per date); 225
  the dataset list's count and red/amber lines; 226 the agency cards' datasets
  count and weekly trend; 227 the dataset page's, column panel's and tiles'
  labelled trends; 228 a check chart's named axis. File checks are out of every
  count (plans/running-thoughts.md #96).
```

Entries #1 and #2 stay until their requirements are built.

## Draft entry for plans/running-thoughts.md (for a human to apply)

```
NN. **[todo, 2026-10-14]** **[Dashboard UI]** **Sort the dataset list by red
    count?** Raised while scoping road-testing sprint 1 (REQ-DASH-225): once each
    row says "3 of 15" with "2 red, 1 amber", a sort by red count (or one by
    default) is the obvious next step at about thirty datasets. Left out of
    sprint 1 because it is not trivial: the list's order is the hierarchy's
    today, and a sort changes what a row position means in links, tests and
    screenshots. Not yet put to Keith.
```

## Validation (re-run after this revision)

Re-run 2026-10-14 (17:31 Perth) after folding in the sign-off readiness answers:

- `uv run mothman dashboard validate-requirements --draft docs/drafts/road-testing-sprint-1/requirements-draft.yaml`
  reports only the 3 expected cross-reference errors: REQ-DASH-070 (from 225 and
  226) and REQ-PIPE-115 (from 227), which the draft does not contain.
- The live `requirements.yaml` validates on its own (208 requirements, zero
  errors), so the earlier evidently-work errors below are gone.
- With the draft appended to a fresh copy of it (scratchpad
  `requirements-merged.yaml`, 213 requirements): **OK, zero errors.**

### Earlier run, before the sign-off readiness answers

- `uv run mothman dashboard validate-requirements --draft docs/drafts/road-testing-sprint-1/requirements-draft.yaml`
  reports only the expected cross-reference errors: REQ-DASH-070 (from 225 and
  226) and REQ-PIPE-115 (from 227), which the draft does not contain.
- With the draft appended to a copy of `requirements.yaml` (scratchpad
  `requirements-merged.yaml`, 213 requirements), the check reports **5 errors,
  none of them in this draft**. All 5 are in REQ-QAC-108 and REQ-QAC-223
  `implemented_by`, and an unmodified copy of the live `requirements.yaml`
  reports the same 5. They come from uncommitted evidently work in the working
  tree (`qa_tools/*/evidently_*`, `run_evidently_*`), not from this draft. On
  2026-10-14 earlier the same merge reported zero errors.

## Keith's answers (2026-10-14, ~17:00)

- Q1: **A** - the dataset-list row counts COLUMNS, and the small trend beside
  it measures the same thing.
- Q2: **A, with a change** - a column counts once at its worst check; and
  "maybe have separate lines for red vs orange" - clarified: TWO TREND LINES,
  red columns and amber columns drawn as separate series.
- Q3: **B (not the recommendation)** - checks that belong to no column
  (supply-level, table-level, file, cross-table) COUNT AS EXTRA "COLUMNS".
- Q4: **C (not the recommendation)** - agency cards count DATASETS not green
  ("N of M datasets not green"), not checks.
- Q5: **B (not the recommendation)** - the agency card KEEPS a small labelled
  trend (of datasets not green over time).
- Q6: **A** - small trends share one fixed 0-100% scale.
- Q7: **A** - a new dataset-level trend on the dataset page (red and amber as
  two lines, matching the list) plus a label over the column grid.
- Q8: **A** - a check chart's measure name comes from its rule kind through one
  mapping, with a test naming any kind missing from it.
- The Trend defect (inactive/nodata counted as failing): **fix now,
  test-first**, as a post-build-review defect; REQ-DASH-224 then builds on it.

## Keith's answers to NQ1-NQ3 and the tiles call (2026-10-14, ~17:15)

- NQ1 (file checks as a column): **NEITHER - split out and scoped separately.**
  Keith: "Let's separate this and scope it separately - I do think they need
  to display through all levels of the dashboard, but just not sure how yet."
  So sprint 1 leaves file checks OUT of every count and trend (REQ-DASH-097
  stands untouched for now), and how file-check verdicts surface at every
  level of the dashboard is its own item: plans/running-thoughts.md #96.
- NQ2 (agency card trend points): **B** - each dataset's full status as of
  each date (always ends at the card's count; needs per-dataset cadence logic
  and a date grid).
- NQ3: **A** - the agency card trend is two lines, red and amber.
- Column tiles and column panel: **two lines everywhere** (the scoper's call,
  confirmed).

## Keith's answers to the two reviews (2026-10-14 evening)

Recorded in full at the end of `review-dashboard-ux.md` (Q1-Q5, all A) and
`review-architect.md` (B1 option b; Q2 only checked runs are points; Q3 retired
checks excluded). Each one is a decision in the draft, citing "Keith,
2026-10-14, <review> Q<n>", with the option he rejected.

## Keith's answers at the sign-off readiness check (2026-10-14 evening)

1. Collection headings: **count AND trend** (not the recommendation of count
   only) - each collection heading on the agency tier gets "N of M datasets not
   green" and the same small two-line weekly trend as the agency card.
2. Wording: **approved, but KEEP ZERO PARTS** - "2 red, 0 amber", always both
   (not the drafted "leave a zero part out"). Everything else as drafted.
3. The REQ-DASH-180 amendment (criterion 29, dependencies, decision):
   **approved**, applied when this batch is signed.
4. The four judgement calls: **all fine**.
