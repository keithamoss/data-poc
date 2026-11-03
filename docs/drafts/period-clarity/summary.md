# Period clarity: sign-off brief (draft v2, 2026-10-23 Perth)

Scoped by delivery-scoper from `review-ux-critic.md` (findings plus Keith's
Q1 to Q3), the dashboard UX reviewer's P1 to P6
(`docs/drafts/review-dashboard-ux-279v3-95v5.md` section 5) and
`plans/post-build-review.md` #260. v2 folds the architect review
(`review-architect.md`) and the dashboard UX review
(`review-dashboard-ux.md`). Every item is mapped below. **This is a proposal:
nothing is built and nothing is signed.** The requirements are in
`requirements-draft.yaml` beside this file: REQ-DASH-284 to REQ-DASH-290.
They were renumbered from 281-287 because 281-283 went to REQ-TEST in
`docs/drafts/small-2026-10-23/`.

**Provenance.** All seven came through delivery-scoper. v1 was reviewed by the
architect and by the dashboard UX reviewer. v2 has not been re-reviewed.

**A transitive block to say at the walk-through (architect S9).**
REQ-DASH-204 is signed, but it depends on REQ-PIPE-211, which is in the
register unsigned and ordered before 204. REQ-DASH-285 and REQ-DASH-289
depend on 204, so they cannot be built until 211 is signed and built. Nothing
else in this batch waits on 211, apart from REQ-DASH-286, 287 and 288's use of
285's helper.

## The seven, in one line each

| Id | MoSCoW | What it does | Depends on (in batch) |
|---|---|---|---|
| REQ-DASH-284 | must | A new `slots.py` `default_window()`. The window embed extends `_slots_by_dataset()`, dated and sparse. One page function NAMES a date's period, and every caller is classified as names or judges. The covered range ends at the build's date. Statuses are untouched. | - |
| REQ-DASH-285 | must | #95's one helper (272 c22) returns structured parts, including the period. Names carry the period where it is news. One period formatter. | 284 |
| REQ-DASH-286 | must | A period line between `<h2>` and `.view-sub` on all four render branches: the window, what the period holds, and the results' age once the period is overdue. Panel subtitles, the compare list, history rows and supply-history headings name the period. | 284, 285 |
| REQ-DASH-287 | must | A period suffix on the header button in its own span, the button wrapping at phone width, an accessible name and the document title via `describeRoute()`. The picker gives each calendar's window, with a "differs" note only where real. | 284 |
| REQ-DASH-288 | should | Collection and agency pages get a period line from the calendar default, with a note only where a dataset differs. The Latest arrival cell carries the period. | 284-286 |
| REQ-DASH-289 | must | A cross-table cell reads "Not evaluated" only when every tool's result is not evaluated, and keeps its marks and 272's note. The collection-row note is a link that doesn't trigger the row. The panel names the supply. | 285 |
| REQ-DASH-290 | should | Open on the build's date when today is past it. | 284 |

**Build order.**
1. The covered-range defect fix (AQ2 = A).
2. The one-line amendment to 272 c22 (AQ1 = A), before 272 is built.
3. 284.
4. 285, after 272/275/204/277 and after 211 (S9).
5. 286 and 287 together, with 287 in the same change as 277 or after it.
6. 288, 289 and 290 in any order.

If 288 slips, collection and agency pages name the period on the button alone
until it lands (UX N4).

## Questions for Keith, ordered by how much the answer changes the build

Every criterion marked PROVISIONAL is written to the recommended answer. Both
reviewers agree with A on P-Q1 to P-Q4. There are eight questions, so the
relay needs two sets: the first four, then the last four.

**P-Q1. On 22 October, which quarter does a Child Protection page name?**
By your rule, 2026-Q3 closed on 18 October, when 2026-Q4's window opened (Q4 is
due 1 November). The page today still names Q3 until 1 November, and so did the
approved mock-up. That mock-up put "22 Oct · 2026-Q3" beside "open 18 Jul – 18
Oct 2026", a range that does not contain the date on show.
- **A (recommended):** name the period whose window holds the date. The page
  reads "2026-Q4 · open 18 Oct 2026 – 18 Jan 2027 · due 1 Nov 2026", then
  "Nothing received for 2026-Q4 yet — due 9:00am Sunday, 1 November 2026."
  The results are named "the 2026-Q3 supply". The button, picker and "Current
  cycle" tag follow, the tag on an empty Q4 row. Status, staleness and the
  composition view stay on dates, so nothing turns red or "No data" on 18
  October. Two latent bugs get fixed along the way: an early Q4 supply heads
  as Q3, and `/period/2026-Q4` is not found. This departs from the mock-up.
- **B:** keep naming by the period's date, as the mock-up did. 284 shrinks to
  display only, but for about two weeks every quarter the range shown excludes
  the date on show, and the two latent bugs need their own fixes.
- **C:** name the period of the supply on show. Pages spanning datasets then
  have nothing to name, so 287 and 288 do not fit as drafted.

**AQ1. Should #95's helper return structured parts now, before 272 is built?**
Signed 272 c22 builds every supply name in Python and forbids re-deriving names
in the page. 285 needs the period as a separate part, so the page can show it
only where it is news.
- **A (recommended):** add one line to 272 c22 now, before it is built: the
  helper returns its receipt instant, its period and its forms. The period goes
  unused until 285. That is one small amendment to a signed requirement, and
  nothing is rebuilt.
- **B:** build 272 flat. 285 then rewrites the helper and every caller, and
  amends 272 c22 at that point.

**AQ2. When should the covered-range defect be fixed?** `coveredDateRange()`
ends at the newest period's start date, not at the build's date. A
quarterly-only deployment, the target shape, is out of range every day after
its period starts, so under P-Q2 = A it would open on 1 August. Under P-Q1 = A,
embedding Q4 from 18 October would make 1 November pickable.
- **A (recommended):** fix it now as a defect, independent of this batch: a
  `post-build-review` entry and a failing test first, including a
  quarterly-only fixture. 284 c7 then becomes its regression guard. This fixes
  a real bug for the target shape without waiting on a sign-off.
- **B:** fold it into REQ-DASH-290, which then becomes a must.

**P-Q3. Should a supply's name carry its period?** This covers the verdict
line, the #95 notices, cell notes and the Latest arrival cell.
- **A (recommended):** only where the supply's period isn't the page's. A Q4
  page reads "the 2026-Q3 supply, received ..." and a Q3 page is unchanged.
- **B:** always. It is uniform, but the period repeats a dozen times and
  lengthens 275's and 204's notices.
- **C:** never, leaving the period line alone. S2's old results then go
  unnamed by period everywhere else.

**P-Q2. Where should the dashboard open the morning after a build?**
- **A (recommended):** today if it is covered, otherwise the build's date. The
  page opens on an answer with no notice, and "Reset to default" always does
  something.
- **B:** keep today, with the notice offering the build's date, as now since
  #260. Every page shows a notice every morning.
- **C:** extend coverage to today and say that nothing after the build is
  known. The page shows a date it has no data for.

**P-Q5. When should the results' age show?** (UX S2.) The scenario: on 22
October Notifications is green and Q4 isn't due until 1 November.
- **A (recommended):** show the age only once the named period is past its late
  instant, and always in a daily gap. On 22 October the line says "Nothing
  received for 2026-Q4 yet — due ..." with no age, and the verdict line already
  says "the 2026-Q3 supply". On 2 November it adds "The results below are 93
  days old." An age appears only when it is news.
- **B:** show it whenever the results are another period's, as v1 did. "82
  days old" on a green, not-yet-due feed reads as an alarm.

**P-Q6. Should 204's lead say "in the warehouse"?** (UX S10, a signed
requirement.) In the B2 case, Notifications' page says one cause three ways:
- 204's notice: "**No promoted Client Register for 2025-Q2.**"
- 289's row: "no Client Register in the warehouse for 2025-Q2"
- the collection note: "Red because no Client Register is in the warehouse for
  2025-Q2"

277 made "in the warehouse" the vocabulary.
- **A (recommended):** amend REQ-DASH-204 c2's lead, in every form of the line,
  from "<b>No promoted <dataset> for <period>.</b>" to "<b>No <dataset> in place
  in the warehouse for <period>.</b>", in this batch. The rest of c2 is
  unchanged, and so are the `data-no-promoted` attribute and c7's two forms.
  One cause then gets one phrase.
- **B:** keep "No promoted", and record why: the line is about the promotion
  that would clear it. That costs nothing, but the page keeps two words for one
  fact.

**P-Q4. What should a cross-table row that could not run say?** (B2, your
Q3 = A.)
- **A (recommended):** "Not evaluated — no Client Register in the warehouse for
  2025-Q2", which is #95's existing note.
- **B:** "Not evaluated — Client Register has no 2025-Q2 supply". This is false
  in the B2 case itself, where the supply arrived and couldn't be loaded.

## Where every review item went

### Architect (`review-architect.md`)

| Item | Where |
|---|---|
| B1, picker and 290 offering a future date | 284 c6 (embed by the build's date) and c7 (covered range ends at the build's date), JS test c12, 290 test |
| B2, covered range wrong for a quarterly-only deployment | 284 c7, AQ2, and 290's quarterly-only fixture. It needs a `post-build-review` entry and a failing test first if AQ2 = A, which the main session files |
| B3, which `periodNameFor` callers name and which judge | 284 c8. I checked each caller in the template. Callers that move: the arrival-from banner (~4714), the owed-nothing "current"/"so far" (~7222), the Current cycle tag (~7937), and the picker (~10116). Callers that stay: promotionStateOn (~2806, with the reasoning in the 284 decisions), settledPairPeriod (~6760), notSuppliedWord (~7440), the no-data banner (~7781), decisionsChangingDate (~10216), and the cycle-link lookup (~7327, a cycle's own date, unaffected). Staying callers carry a greppable comment |
| S1, overlap with the existing slot embeds | 284 c2: extend `_slots_by_dataset()`, filtered, with one source for due dates |
| S2, dates not instants, sparse, size at target scale | 284 c3, c4 and the size NFR, with the 90KB / 500KB figures recorded |
| S3, no Python calendar-default function | 284 c1: `default_window()` in `slots.py`, with the date rule and REQ-PIPE-173 handling |
| S4, periods with no slot, and `dataset_dates_override` | 284 c5 (no slot takes the default) and c4 (own dates always differ). JS test for cp-case-workers in June |
| S5, build-day edge (merged with UX B1) | 284 c6 and test c11 (a build at 08:00 on 18 October embeds Q4) |
| S6, the helper shape and the 272 c22 amendment | 285 c1 and c6, AQ1, and the old/new below |
| S7, text moved into the helper beyond 272's scope | 285 c1 names the `supplyNames` map and each moved text |
| S8, "Not evaluated" replacing 272 c8's word | 289 c1 (only when every tool is not evaluated), the JS test, and the old/new below |
| S9, the transitive block on REQ-PIPE-211 | Header, the 285 and 289 NFRs, and the note at the top of this brief |
| Note: P-Q1 consequences (latent heading bug, `/period/2026-Q4`) | 284 c14 |
| Note: composition-list guard | 284 c13 (no Q4 row before 1 November; notSuppliedWord stays on dates) |
| Note: 286 c8's tag needs an empty Q4 row | 286 c10 |
| Note: 287 c5's title in one path | 287 c5, `describeRoute()` |
| Note: 289's missing period from a structured field | 289 c7 |
| For delivery-critic, items 1-6 | 284 c1, c2, c5, c7, c8 and c10 (bytes printed); 284 c11 (assert non-empty first); 285 c2 (one comparison, commented) |

### Dashboard UX (`review-dashboard-ux.md`)

| Item | Where |
|---|---|
| B1, morning a window opens | Merged with architect S5: 284 c6 |
| S1, due instant twice | 286 c2 (date on the first line) and c4 (instant on the second) |
| S2, age only when it's news | 286 c5 and **P-Q5** |
| S3, element and style | 286 c1 and c7: between `<h2>` and `.view-sub`, plain text, no `--surface-2` |
| S4, four render branches | 286 c1 and its test |
| S5, "above every notice" was literally false | 286 c1: "inside the dataset view", with the past-date notice left above `<h2>` |
| S6, a link inside a clickable row | 289 c5 (stop propagation, middle-click), and real links in 287 c7 and 288 c2 |
| S7, button mechanics at phone width and accessible name | 287 c1, c3 and c4 |
| S8, one title writer, no announcer on a date change | 287 c5 |
| S9, the range's accessible text | 286 c12 (`.sr-only`, visible text `aria-hidden`) |
| S10, three phrasings for one cause | **P-Q6**, with old/new below. Not changed silently |
| S11, per-tool marks under "Not evaluated" | 289 c2 |
| S12, two period formatters | 285 c3 (fold `fmtPeriodName` into `fmtPeriodOrDay`) |
| N1, compare dropdown and history "Run date" | 286 c9 |
| N2, "open" may read as "open now" on a past date | 286 decision, for the walk-through only |
| N3, the tier-1 overview has only the button | 287 and 288 decisions |
| N4, 288 is a should | 288 NFR and the build order |
| Phone-width stack for 289's cell | 289 test at 375px (272 c16) |
| Post-build critic checklist | Covered by the 284, 286, 287 and 289 tests |

### Carried from v1 (unchanged)

Critic findings: B1 went to 285-288, B2 to 289, S1 to 284 and 286, S2 to 285
and 286, S3 to 287, S4 to #260 and 290, N1 to a 286 decision and N3 to 287.
Three are out of scope: N2 (P6), N4 (REQ-PIPE-279 c10) and N5 (browser locale).
Reviewer hooks: P1 went to 285, P2 to 286 c1, P3 to 285 c3 and P4 to 287 c2.
P5 is already in REQ-DASH-204 c17, and P6 is a 288 decision.

## Old and new wording of signed criteria these amend

Each is applied only once Keith approves it, and changes nothing else in the
criterion. "Where differs" means "where that supply's period is not the period
the page names for the date on show" (285 c2, P-Q3 = A).

**REQ-DASH-054 c3 (284 c6, P-Q1 = A).**
- Old: "THE SYSTEM SHALL end each embedded sequence at the period the present
  moment falls in on the asset's own clock, and SHALL NOT embed a period that
  has not begun."
- New: "THE SYSTEM SHALL end each embedded sequence at the last period whose
  default claim window opens on or before the build's date on the asset's own
  clock, and SHALL NOT embed a period whose window opens on a later date."

**REQ-DASH-054 c6 (287 c6).**
- Old: "WHEN a viewer opens the in-place-on panel, THE SYSTEM SHALL state, for
  each of the asset's named calendars, which period the selected date falls
  in."
- New: "... which period the selected date is named by (REQ-DASH-284 criterion
  5, on the calendar's default) and, for a calendar of authored dates, that
  period's window - '<period>, open <date> – <date>' - and for a cadence
  calendar 'the <day> supply'."

**REQ-DASH-182 c10 (286 c10).**
- Old: "... in place of 'No deliveries in the current cycle yet.'"
- New: "... in place of 'Nothing received for <period> yet.'"

**REQ-DASH-272 c22 (285 c6, AQ1 = A, applied before 272 is built).**
- Old: "... naming every supply through ONE Python helper (so that the
  period-clarity work changes supply naming once), and SHALL NOT re-derive them
  in the page's script."
- New: "... naming every supply through ONE Python helper, which returns each
  name's structured parts - its receipt instant, the period it was filed to,
  and its forms with and without the period - so that the period-clarity work
  (REQ-DASH-285) changes supply naming once; and SHALL NOT re-derive them in
  the page's script, the page's choice between the two forms being one
  comparison of two period names."

**REQ-DASH-272 c8 (289 c1).**
- Old: "THE SYSTEM SHALL show in each filled cell the result's word - the WORST
  of its marks, through rollupStatuses, never the first tool's - then ..."
- New: "THE SYSTEM SHALL show in each filled cell the result's word - the WORST
  of its marks, through rollupStatuses, never the first tool's, except that a
  cell whose EVERY tool's result was not evaluated reads 'Not evaluated'
  (REQ-DASH-289) - then ..."

**REQ-DASH-204 c18 (289 c5, P-Q4 = A).**
- Old: "THE SYSTEM SHALL show, in the collection table, a quiet note under each
  such reader's status pill naming the causing table, in the noSupplyNote
  shape, ..."
- New: "... a quiet note under each such reader's status pill naming the
  causing table and the period - 'Red because no <dataset> is in the warehouse
  for <period>', the dataset a link that does not trigger the row - in the
  noSupplyNote shape, ..."

**REQ-DASH-204 c2 (P-Q6 = A only).**
- Old lead, in every form: "'<b>No promoted <dataset> for <period>.</b> ...'"
- New lead: "'<b>No <dataset> in place in the warehouse for <period>.</b> ...'"

The rest of each form is unchanged, and so are the `data-no-promoted`
attribute, 204 c7's two forms, and c14's scenario quotes, which quote the page
and follow it.

**Supply-naming forms (285 c6).** Each quoted form keeps its text and gains a
"where differs" alternative:

| Criterion | Old fragment | Added alternative, where differs |
|---|---|---|
| 272 c1 | "The supply in place in the warehouse is the one received <instant>, and is <status>." | "The supply in place in the warehouse is the <period> supply, received <instant>, and is <status>." |
| 272 c8 | "'<dataset> received <day>'" | "'<dataset> <period>, received <day>'" |
| 272 c12 | "'Read against the <dataset> in place in the warehouse, received <instant>'", and the other "received <instant>" sentences | "'..., the <period> supply received <instant>'", and likewise for each |
| 272 c20 | "'Promoted <time> with the <dataset> supply received <instant>'" | "'Promoted <time> with the <dataset> <period> supply received <instant>'" |
| 275 c1 | "That file (received <instant>)" | "That file (the <period> supply, received <instant>)" |
| 275 c4 | "(one delivery, received <instant>)" / "(received <instant> and <instant>)" | "(one delivery, the <period> supply, received <instant>)" / "(the <period> supplies, received ...)" |
| 275 c6 | "has been replaced by the one received <instant>" | "has been replaced by the <period> supply received <instant>" |
| 204 c2 | "The <dataset> received with this supply (<instant>)"; "replaced by the one received <instant>" | "(<period>, <instant>)"; "replaced by the <period> supply received <instant>" |
| 277 c1 | "'The results below are the supply in place in the warehouse, received ...'" | "'The results below are the <period> supply in place in the warehouse, received ...'" |

Left alone: 272 c4 (it already names its period), 272 c21 (the waiting supply's
own forms) and 204 c7 (it names a promotion instant).

## Decided without asking (both reviewers agree with each)

- "Differs" is judged by date.
- Daily calendars get no window.
- The line sits before the description, which departs from the mock-up. It is
  plain text, not a callout.
- No Period column.
- The age is measured to the date on show (and is now gated by P-Q5).
- "Not evaluated" is the cell word, now only when every tool is not evaluated.
- New in v2: a period with no slot takes the calendar default, and a dataset
  with its own dates always differs (architect S4).
- New in v2: `promotionStateOn` stays on dates (B3).

## Non-functional angles

- **Answered from the codebase:** the build rule, performance and size (now
  sparse dates, measured), scale, accessibility (`.sr-only` range, accessible
  names, no swallowed links, no announcer churn), phone width (button at most
  two lines, line wraps, 289's stacked cell), dark mode, compatibility, privacy
  and maintainability (one helper, one formatter, one membership function, a
  greppable split).
- **Ruled out:** reliability, security (the architect agrees), observability,
  compliance and cost.

## Validation

`uv run mothman dashboard validate-requirements --draft` was run on this draft
alone and on a merged copy (`requirements.yaml`, which now holds the signed #95
batch, REQ-PIPE-279 and REQ-PIPE-211, plus the small-items draft, plus this
draft), after the last edit to either file. The draft alone reports only
cross-references to requirements it does not contain. The merged copy reports
"requirements validation OK - 276 requirements, zero errors", with ids 281-290
held by REQ-TEST-281..283 and REQ-DASH-284..290 and no collision.
`requirements.yaml` itself is untouched.

## Draft plans entry (for a human to apply to plans/running-thoughts.md #118)

> 118. **[in-progress, 2026-10-23]** **[Dashboard UI]** **Is it obvious which
>      period a page is talking about?** ... (existing text kept) ...
>      **Scoped 2026-10-23** as REQ-DASH-284 to REQ-DASH-290
>      (docs/drafts/period-clarity/, v2 after the architect and dashboard UX
>      reviews). Eight questions are with Keith (P-Q1, AQ1, AQ2, P-Q3, P-Q2,
>      P-Q5, P-Q6, P-Q4). 285 and 289 are transitively blocked on REQ-PIPE-211.
>      N2, N4 and N5 are out of scope, with the reasons recorded. Delete this
>      entry once the seven are built.
