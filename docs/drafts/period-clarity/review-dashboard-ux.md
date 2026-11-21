# Dashboard UX review: period clarity, REQ-DASH-284 to 290 (draft v1), 2026-10-23

(Returned as a report - no write tool - saved by the main session, condensed with every finding kept. Template line refs are to dashboard/qa-reporting-dashboard.template.html.)

Overall: carries Keith's answers faithfully; structure right (one helper, one membership function, naming separate from status, notes only where something differs). One blocking edge case; the rest is wording seen twice and template mechanics the criteria don't name.

Contexts: error/failure (289 - passes: names other table and period, collection note links to it; see S6); at-a-glance (286 c1-c6, 287, 288 - S1, S2); drill-down (286 c7-c8 - panels always name the supply, right); routine daily (290, header button - P-Q2 = A serves it).

## Blocking
**B1. 284 c4 and c5 disagree on the morning a window opens.** c4 puts a date in the period open at the END of that date (18 Oct reads 2026-Q4); c5 stops the embedded sequence at the period whose window has opened by the PRESENT moment. A build at 08:17 on 18 Oct doesn't embed Q4 though today asks for Q4 - period line, button and picker have no entry or fall back to Q3 all day. Fix: c5 embeds every period whose default window opens by the end of the build day on the asset clock (c4's own rule). Test: a build at 08:00 on a window-opening day.

## Should-fix
- **S1. Due instant appears twice** (286 c13 expected text). First line shortens to a date ("2026-Q4 · open 18 Oct 2026 – 18 Jan 2027 · due 1 Nov 2026", as the mock-up had); full instant only on the second line. Daily "· due 2:00pm" fine.
- **S2. Results' age only when it's news.** On 22 Oct under P-Q1 = A, Notifications isn't yet due and green, yet "The results below are 82 days old." reads as an alarm. Show age only once the named period is past its due/late instant, and always for a cadence calendar in a gap. Before due: "Nothing received for 2026-Q4 yet — due 9:00am Sunday, 1 November 2026. The results below are the 2026-Q3 supply's." Put to Keith as the recommended reading.
- **S3. Element and style.** "Before its description" = between `<h2>` and `.view-sub`, in `.view-head`'s left column - say so. Don't copy the mock-up's bordered callout (`--surface-2` is undefined; line 327 uses it with a `transparent` fallback; a box reads as a notice, competing with `.notice-exhausted`). Plain text: period bold `var(--ink)`, rest at `.view-sub` size `var(--ink-muted)`, second line muted 12.5px like `.verdict-of`/`.amber-setting-line`. Precedent: the ED "Latest arrival — promoted into 2026-Q3" label (~4789).
- **S4. Four dataset render branches** - no data on date (~7680), blocked (~7704), owed nothing/never supplied (~7729), normal (~7756) - each writes its own `.view-head`; 286 c6 lists them by name; add a never-supplied/owed-nothing test case.
- **S5. "Above every notice" (286 c1) literally false for the global past-date notice** ("Showing what was in place on ..."), rendered above `<h2>`. Reword "above every notice inside the dataset view"; the past-date notice stays where it is.
- **S6. A link inside a clickable row must not trigger the row.** 289 c4, 287 c7, 288 c2: use `navHref`/`a[data-nav]` (real `<a href>`, spa-best-practices §D, REQ-DASH-272 c14). 289 c4's link sits inside the collection table's `<tr data-nav tabindex="0">` (~6594); stop propagation as `ticketBadge()` does (~4844) - otherwise a click opens the reader's page, defeating B2. Add to the 289 test.
- **S7. Header button at phone width and its accessible name.** `.snapshots-btn` is `white-space:nowrap`, pill (822, 902); 287 c3 overrides nowrap for `#in-place-on-btn` only and puts the suffix in its own span (`updateInPlaceOnButtonLabel()` sets textContent on the date span alone) - name both. At ≤480px shorten the date to "Thu 22 Oct 2026" so the button is ≤2 lines. 287 c4's accessible name "period 2026-Q4" is right only for authored calendars; cadence spells "the 22 October 2026 supply"; spanning pages give both.
- **S8. Page title and announcer: one writer.** 287 c5 amends `describeRoute()` (5558), today's single writer of `document.title`. `#route-announcer` stays the view name - a date change is a `replaceState` filter, not a navigation; re-announcing would be noise.
- **S9. Range accessible text (286 c12) mechanism**: `.sr-only` full range with the abbreviated visual `aria-hidden="true"`, not `aria-label` on a static div/span (many readers ignore it).
- **S10. Three phrasings for one cause on one Notifications page** (B2 case): 204 c1's notice "**No promoted Client Register for 2025-Q2.**"; 289's row "no Client Register in the warehouse for 2025-Q2"; 289's collection note "Red because no Client Register is in the warehouse for 2025-Q2". P-Q4 = A is right, but 204's lead says "promoted" where 277 made the vocabulary "in the warehouse". Raise at the walk-through: amend 204 c1's lead to "No <dataset> in place in the warehouse for <period>." in this batch, or record why they differ. It's signed - don't change silently.
- **S11. 289 c1 doesn't say what happens to the per-tool marks** (272 c8: word, one mark per tool, note). State whether ✓/✗/· still show and which mark a tool that couldn't run gets.
- **S12. Two period formatters**: `fmtPeriodOrDay()` (6149) and `fmtPeriodName()` (4826; builds a local-time Date, may disagree with `fmtDay` on the asset clock). Fold the ED block's use into `fmtPeriodOrDay`.

## Notes
- N1. Two critic items without a home: the check panel's compare dropdown (45 dates mixing scheduled supplies and resupplies, no quarter) and the history table's bare "Run date". Suggest 286 c7 labels dropdown options and history rows through 285's helper in short form for authored calendars, or record out of scope with a reason.
- N2. "open 18 Oct – 18 Jan" can read as "open now" on a past date; Keith's word; "window 18 Oct – 18 Jan" an alternative for the walk-through only.
- N3. 288 covers collection and agency pages, not tier-1 Agencies (overview-B) - there only the button names the period; fits Q2, say so.
- N4. 288 is "should" while 286/287 "must"; if 288 slips, collection pages show the period only on the button - say so in the build order.

## The four questions
- P-Q1: agree A, with B1 fixed. Follows Keith's open-to-close rule; the approved mock-up was internally inconsistent ("22 Oct · 2026-Q3" beside "open 18 Jul – 18 Oct 2026"). B shows a range excluding the date on show ~two weeks a quarter; C hides the empty-period case (critic S2). A's cost (Q4 named while Q3 results and green status show) is coherent only via 285's "the 2026-Q3 supply" and 286's second line - so P-Q3 = A and S2 go with it. Tell Keith plainly it departs from the mock-up.
- P-Q2: agree A (opens on an answer; c3 - no notice when the address carries no date - is the important part).
- P-Q3: agree A (named only where it's news; panels always carry it).
- P-Q4: agree A, plus S10's alignment of 204's lead.

## "Decided without asking"
Agree with all: differs judged by date; no window for daily; period line before the description (departs from the mock-up - mention; see S3/S5); no Period column (period in Latest arrival cell - a column repeats the page's period 30 times); age to the date on show (subject to S2); "Not evaluated" as the cell word (existing: trend chart 4194, compare column 8409; see S11).

## Consistency with #95
277: 287 c2 leaves the label's words to 277, coordination recorded both sides; compatible with 277's `test_no_visible_text_says_in_place_alone`; build 277 first or together. 272: 285 extends c22's helper; 289's note is c8's form, accessible name follows c14; at phone width 272 c15 stacks "Staged:"/"In the warehouse:" - 289's "Not evaluated — ..." must fit; add to the 289 test at 375px. 275/204: table-driven amendments limited to the "where differs" alternative; 204 c17's partner window already carried (P5).

## For the post-build UX critic
1. On 22 Oct, cp-notifications' period line, button and picker all say 2026-Q4 and the range contains the date on show; also a build before 09:00 on 18 Oct (B1). 2. Period line plain text, between h2 and .view-sub on all four branches, below the past-date notice; light and dark. 3. No due instant twice; no age line before the due date on a quarterly feed. 4. At 375px: button ≤2 lines, period not cut off, no horizontal scroll, 289's stacked cell fits. 5. The collection note's link opens the Client Register at the same date, not the reader's row; middle-click opens a new tab. 6. `document.title` changes via `describeRoute()`; the announcer doesn't re-fire on a date change. 7. A screen reader reads the range in full via `.sr-only`.
