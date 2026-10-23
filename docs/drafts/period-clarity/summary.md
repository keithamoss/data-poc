# Period clarity: sign-off brief (draft v1, 2026-10-23 Perth)

Scoped by delivery-scoper from `review-ux-critic.md` (findings plus Keith's
Q1 to Q3 answers), the dashboard UX reviewer's P1 to P6
(`docs/drafts/review-dashboard-ux-279v3-95v5.md` section 5) and
`plans/post-build-review.md` #260. **A proposal: nothing is built and
nothing is signed.** The requirements are in `requirements-draft.yaml` beside
this file: REQ-DASH-284 to REQ-DASH-290, the next free ids across the
register and every draft (281-283 went to REQ-TEST in
docs/drafts/small-2026-10-23/; renumbered from 281-287 on 2026-10-23).

**Provenance.** All seven came through delivery-scoper. None has had a
dashboard UX review or an architect review yet. Those are worth running
before the walk-through, on 286 and 287 above all.

## The seven, in one line each

| Id | MoSCoW | What it does | Depends on |
|---|---|---|---|
| REQ-DASH-284 | must | The build embeds each authored-calendar period's open, close and due, per dataset and as the calendar default, plus a "differs" flag. One page function says which period a date is in. Statuses are untouched. | 054, PIPE-131 |
| REQ-DASH-285 | must | Every supply name goes through #95's one helper (272 c22), which gains the period. Where the supply's period is not the page's, the name says it: "the 2026-Q3 supply, received ...". | 272, 275, 204, 277, 284 |
| REQ-DASH-286 | must | The period line under the dataset name gives the window, what the period holds and how old the results are. The panels and supply history name the period too. | 284, 285, 182, 133 |
| REQ-DASH-287 | must | The header button gets "· 2026-Q4" (both calendars on spanning pages), and so does the document title. The picker gives each calendar's window, plus a "differs" note only where real. | 284, 277, 054 |
| REQ-DASH-288 | should | Collection and agency pages get a period line from the calendar default, with a note only where a dataset in scope differs. The Latest arrival cell carries the period through the helper. | 284-286 |
| REQ-DASH-289 | must | Keith's Q3 = A: a cross-table row that could not run reads "Not evaluated — no Client Register in the warehouse for 2025-Q2" and stays Red. The collection row gets a short note, and the panel names the supply. | 272, 204, 270, 285 |
| REQ-DASH-290 | should | #260's leftover behaviour question: open on the newest covered date when today is past it. | 054, 284 |

Build order: 284 first, then 285, then 286 and 287 together, then 288, 289
and 290 in any order. 287 shares one narrow control with REQ-DASH-277 and
should be built in the same change as 277 or after it (reviewer P4).

## Where each finding went

| Finding | Where |
|---|---|
| B1, no tier names the period | 286 (dataset line and panels), 287 (button), 288 (collection and agency), 285 (supply names) |
| B2, cross-table red from the other table's missing supply | 289 |
| S1, "2026-Q3" is not Jul-Sep | 284 and 286, using Keith's open-to-close range |
| S2, empty current period hides its age | 286 c4 (the second line and the age), 286 c8 (the cycle named), 285 (the results named by period) |
| S3, period on the header button | 287 |
| S4, dead reset button | Already fixed (#260). Its leftover question is 290 |
| N1, ED promotion block as precedent | 286 decision |
| N2, weekly sparklines on quarterly agencies | **Out of scope**: bucketing would merge K3 = C's points (P6). 288 decision |
| N3, document.title | 287 c5 |
| N4, sample counts disagree | **Out of scope**: REQ-PIPE-279 criterion 10 (one counting function). Re-check once 279 lands. 289 decision |
| N5, date input renders 10/23/2026 | **Out of scope**: the browser locale controls a native input. 287 decision |
| P1, one supply-naming helper | 285 |
| P2, not a third rewording of 081 c1, and above the notices | 286 c1, 285 NFR |
| P3, `<period>` through fmtPeriodOrDay with no range | 285 c3 |
| P4, shared control with 277 | 287 c2 and NFR |
| P5, 204 c17 uses the partner's own window | Already carried in signed REQ-DASH-204 c17 (v6). Nothing to add |
| P6, no period bucketing of sparklines | 288 decision |

## Questions for Keith (relay-ready, one set of four)

Every criterion marked PROVISIONAL is written to the recommended answer.

**P-Q1. On 22 October, which quarter does a Child Protection page name?**
By your own definition, 2026-Q3 closed on 18 October, when 2026-Q4's claim
window opened (Q4 is due 1 Nov). The page today decides a date's period by the
period's DATE, so it still says Q3, and so did the mock-up you approved. That
mock-up put "In place on 22 Oct · 2026-Q3" beside "open 18 Jul – 18 Oct 2026",
a range that does not contain the date on show.
- **A (recommended):** name the period whose window is open at the end of the
  date. The page reads "2026-Q4 · open 18 Oct 2026 – 18 Jan 2027 · due 9:00am
  Sunday, 1 November 2026" and "Nothing received for 2026-Q4 yet ... The
  results below are 82 days old.", and the results are named "the 2026-Q3
  supply". The button, the picker and supply history's "Current cycle" tag all
  follow. Status and staleness keep using period dates, so nothing turns red or
  "No data" on 18 October (284 c6, with a regression test).
- **B:** keep naming by the period's date, as the mock-up did. It is simpler and
  matches what you saw. The cost is that for about two weeks every quarter
  (18-31 Oct, 18-31 Jul and so on) the range shown beside the date on show
  excludes it, and between 18 and 31 July a page says Q2 while Q3 is open and
  taking supplies.
- **C:** name the period of the supply on show (Q3, marked "closed 18 Oct"),
  and mention the open period only once something has arrived for it. This
  never names an empty period, but it hides S2's "nothing yet" case on
  quarterly feeds, which is the case the critic flagged.

**P-Q2. Where should the dashboard open the morning after a build?** (#260's
leftover question.) Today's default is the asset's "today", and the covered
dates end at the build day.
- **A (recommended):** today if it is covered, otherwise the newest covered
  date. The page opens on an answer with no notice, the build line already says
  when it was built, and "Reset to default" always does something.
- **B:** keep today. The notice says it is outside the range and offers the
  newest covered date, which is how it has behaved since #260. Every page
  carries that notice every morning.
- **C:** extend coverage to today and open on it, saying that nothing after the
  build is known. Today's period is then named honestly, but the page shows a
  date it has no data for.

**P-Q3. Should a supply's name carry its period?** This covers the verdict line,
the #95 notices, the cross-table cell notes and the collection list.
- **A (recommended):** only where the supply's period is not the period the page
  names. On a Q4 page showing Q3 results it reads "the 2026-Q3 supply, received
  ...", and on a Q3 page nothing changes. The period appears only where it is
  news.
- **B:** always. This is the most uniform, but the period repeats a dozen times
  on a page whose period line already says it, and it lengthens REQ-DASH-275's
  and 204's long notices.
- **C:** never. The period line alone carries the period. This is the smallest
  change, but S2's four-week-old results stay unnamed by period everywhere
  except that one line.

**P-Q4. What should a cross-table row that could not run say?** (B2, your Q3 = A.)
- **A (recommended):** "Not evaluated — no Client Register in the warehouse for
  2025-Q2", with the collection row reading "Red because no Client Register is
  in the warehouse for 2025-Q2". This is #95's existing note (272 c8), so there
  is one vocabulary, and it is true for every cause.
- **B:** your example wording, "Not evaluated — Client Register has no 2025-Q2
  supply". It is shorter, but it is false in the B2 case itself, where the
  Client Register's 2025-Q2 supply was received and could not be loaded.

## Decided without asking (say at the walk-through if any is wrong)

- **"Differs" is judged by date** (284). A due time of 14:00 against 09:00 on
  the same day does not count as a different window. Today no Child Protection
  or Emergency Department dataset differs at all, so no note would show yet.
- **Daily calendars get no window**, only the day (Q1 option C). Nothing is
  embedded for them.
- **The period line sits before the description**, not after it as in the
  mock-up (286). The critic found the verdict line below the fold on a phone.
- **No Period column on the collection list** (288). The period goes into the
  Latest arrival cell, and only when it differs from the page's.
- **The results' age is measured to the date on show**, so a past date reads as
  it did then (286).
- **The cell word is "Not evaluated"**, a word the page already uses, rather
  than the worst of the marks, which has no word for a check no tool ran (289).

## Old and new wording of signed criteria these amend

Each is applied only once Keith approves it, and changes nothing else in the
criterion. "Where differs" below is short for "where that supply's period is
not the period the page names for the date on show" (285 c2, P-Q3 = A).

**REQ-DASH-054 c3 (284 c5, P-Q1 = A).**
- Old: "THE SYSTEM SHALL end each embedded sequence at the period the present
  moment falls in on the asset's own clock, and SHALL NOT embed a period that
  has not begun."
- New: "THE SYSTEM SHALL end each embedded sequence at the period whose claim
  window, by its calendar's default, has opened by the present moment on the
  asset's own clock, and SHALL NOT embed a period whose window has not opened."

**REQ-DASH-054 c6 (287 c6).**
- Old: "WHEN a viewer opens the in-place-on panel, THE SYSTEM SHALL state, for
  each of the asset's named calendars, which period the selected date falls
  in."
- New: "... which period the selected date falls in (REQ-DASH-284 criterion 4,
  by the calendar's default) and, for a calendar of authored dates, that
  period's window - '<period>, open <date> – <date>' - and for a cadence
  calendar 'the <day> supply'." (The built text "<period>, which began <day>"
  goes.)

**REQ-DASH-182 c10 (286 c8).**
- Old: "... in place of 'No deliveries in the current cycle yet.'"
- New: "... in place of 'Nothing received for <period> yet.'"

**REQ-DASH-204 c19 (289 c4, P-Q4 = A).**
- Old: "... a quiet note under each such reader's status pill naming the causing
  table, in the noSupplyNote shape, ..."
- New: "... a quiet note under each such reader's status pill naming the causing
  table and the period - 'Red because no <dataset> is in the warehouse for
  <period>' - in the noSupplyNote shape, ..."

**Supply-naming forms (285 c6).** Each quoted form keeps its old text and gains
a "where differs" alternative:

| Criterion | Old fragment | Added alternative, where differs |
|---|---|---|
| 272 c1 | "The supply in place in the warehouse is the one received <instant>, and is <status>." | "The supply in place in the warehouse is the <period> supply, received <instant>, and is <status>." |
| 272 c8 | "'<dataset> received <day>'" | "'<dataset> <period>, received <day>'" |
| 272 c12 | "'Read against the <dataset> in place in the warehouse, received <instant>'", and the four other "received <instant>" sentences | "'Read against the <dataset> in place in the warehouse, the <period> supply received <instant>'", and likewise for each |
| 272 c20 | "'Promoted <time> with the <dataset> supply received <instant>'" | "'Promoted <time> with the <dataset> <period> supply received <instant>'" |
| 275 c1 | "That file (received <instant>)" | "That file (the <period> supply, received <instant>)" |
| 275 c4 | "(one delivery, received <instant>)" / "(received <instant> and <instant>)" | "(one delivery, the <period> supply, received <instant>)" / "(the <period> supplies, received ...)" |
| 275 c6 | "has been replaced by the one received <instant>" | "has been replaced by the <period> supply received <instant>" |
| 204 c2 | "The <dataset> received with this supply (<instant>)"; "replaced by the one received <instant>" | "(<period>, <instant>)"; "replaced by the <period> supply received <instant>" |
| 277 c1 | "'The results below are the supply in place in the warehouse, received ...'" | "'The results below are the <period> supply in place in the warehouse, received ...'" |

Left alone on purpose: 272 c4 (it already names its period with "carried
forward from <period>"), 272 c21 (these are the waiting supply's own forms, so
always the page's period), and 204 c7 (it names a promotion instant, not a
receipt).

## Non-functional angles

Each requirement carries its own NFRs. Keith hasn't been asked about any of
these angles. I judged them myself from the codebase:

- **Answered from the codebase:** the build rule (configuration plus recorded
  results only), performance on a ~16MB page (about 1,000 small window entries,
  under 1% of the page, measured at build, with index lookups and no history
  walks), scale to ~30 collections (one line per calendar, notes capped at three
  names, no new column), accessibility (words, never colour alone; the range
  spelled out in full), phone width (wrap, never truncate the period), dark mode
  (existing tokens only), compatibility (no new asset, file:// and offline
  unaffected, the query parameter unchanged), privacy (period and dataset names,
  never files or rows), and maintainability (one helper and one membership
  function).
- **Ruled out as not applying:** reliability (the page computes nothing that
  can fail partway), security, observability (it records nothing),
  compliance and retention, and cost.
- **One angle worth Keith's view at the walk-through, not blocking:** whether
  the results' age ("82 days old") reads as alarming on a quarterly feed that
  is not yet due. It is factual, and the first line says the period is not due
  until 1 Nov. Dropping it from quarterly before the due date is a one-line
  change if he prefers.

## Validation

`uv run mothman dashboard validate-requirements --draft` was run on this draft
alone and on a merged copy (`requirements.yaml` plus REQ-PIPE-279's draft plus
#95 v6 plus this draft). The draft alone reports only the expected
cross-references to requirements it does not contain. The merged copy reports
one error, and it is not this draft's: #95 v6's REQ-DASH-204 depends on
REQ-PIPE-211, which exists only in the calendar close-out draft.

## Draft plans entry (for a human to apply to plans/running-thoughts.md #118)

Replace #118's status and append:

> 118. **[in-progress, 2026-10-23]** **[Dashboard UI]** **Is it obvious which
>      period a page is talking about?** ... (existing text kept) ...
>      **Scoped 2026-10-23** as REQ-DASH-284 to REQ-DASH-290
>      (docs/drafts/period-clarity/requirements-draft.yaml, summary.md), from
>      the critic's report and Keith's Q1 to Q3. Four questions are with Keith
>      (P-Q1 which period a date is in, P-Q2 the default date, P-Q3 periods in
>      supply names, P-Q4 the not-evaluated wording). N2, N4 and N5 are out of
>      scope, with the reason recorded on 288, 289 and 287. Delete this entry
>      once the seven are built.
