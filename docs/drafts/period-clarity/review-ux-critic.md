# Period clarity: UX critique of the built dashboard (running-thoughts #118), 2026-10-22

(Returned as a report - the critic is read-only - and saved here by the main session, condensed with every finding kept. Screenshots: /home/user/data-poc/.playwright-mcp/period-01..17-*.png. Built page reviewed: /home/user/ed-wt/dashboard/qa-reporting-dashboard.html, served over HTTPS by scripts/dev/serve_dashboard_https.py, 1440x900 and 390x844. Default "In place on" was Friday 23 Oct 2026.)

Short answer: no. Apart from one panel the dashboard never says which period a page is about; it names the supply by when it was received. The period the data already holds (`lastArrival.slot = "2026-Q3"`) appears only inside the "In place on" picker and in an ED-only block. `main.innerText.indexOf("2026-Q3") === -1` on cp-notifications at the default date. Corrections to the brief: ED Presentations is quarterly; Birth Registrations is the only daily feed.

## Per tier

| Tier | What it says | Evidence |
|---|---|---|
| Header | "In place on: Friday, 23 October 2026" - a date, not a period | period-01 |
| Agency overview | No period/supply; sparkline "each week" even for quarterly agencies | period-01, 02 |
| Collection list | "LATEST ARRIVAL: On time 9:00am Saturday, 1 August 2026", no period column | period-17 |
| Collection cross-table section | check name, table pair, status; no period, supply or date | period-03 |
| Dataset page | grey 12.5px, 4th block: "The results below are the supply in place, received 9:00am Saturday, 1 August 2026." No quarter; below the fold on mobile (y=1030) | period-05, 15 |
| Supply history | "Cycle starting Saturday, 1 August 2026 · Current cycle" beside "Periods with no supply ... 2014-Q2 to 2015-Q3" - two vocabularies | period-04 |
| Column drawer | "CURRENT RUN — ROW COUNTS", no date/period | period-10 |
| Check panel/compare | "COMPARED RUN [Wed 27 May 2026 (previous)]" vs unlabelled "CURRENT RUN"; 45-date dropdown mixing scheduled supplies and resupplies, no quarter | period-11 |
| History table | "Run date" only | - |
| Picker | only place the period is named: "daily 2026-10-22 ... quarterly 2026-Q3, which began Saturday, 1 August 2026"; only after a click | period-14 |

## Blocking

**B1. No tier names the period its numbers are about.** Fails recognition over recall. Proposed: one period line, same place and wording on every dataset-scoped tier, directly under the dataset name - e.g. "2026-Q3 (from 1 Aug 2026) — supply received 9:00am Sat 1 Aug 2026, in place"; repeat in drawer/panel subtitle ("risk_rating · 2026-Q3"); a Period column on the collection list; label the CURRENT RUN card with period and received date; daily feeds put the date in the same slot. `fmtPeriodOrDay()` already exists.

**B2. Cross-table red on one table's page gives no sign the cause is the OTHER table's missing period** (the REQ-PIPE-279 case, at `?in-place-on=2025-05-15`). Clients' page handles it well (period-07: "Could not be loaded ... The cross-table checks could not run either"). Notifications' page (period-08): Investigations-based rows say "Checked ... when the Investigations supply arrived"; the three Client-reference rows show only the rule and Red, no "checked when", no reason. Collection list (period-17): Notifications, Investigations, Placements "Red ... incl. Cross-table checks", nothing points at Clients. Cause only in the opened panel (period-09: "NOT EVALUATED IN THE CURRENT RUN — could not run - cp_clients arrived and could not be loaded"), and "the current run" unnamed. Proposed: every cross-table row carries both sides' period and supply ("Notifications 2025-Q2 (rec'd 1 May 2025) ↔ Client Register: no checkable 2025-Q2 supply — not evaluated"), on the row and on the collection-list row ("red because Client Register has no 2025-Q2 supply").

## Should-fix

**S1. "2026-Q3" is the 1 Aug-31 Oct delivery slot, not Jul-Sep** (`contract/calendar.yaml`: "deliberately NOT calendar quarters"); a WA reader may read financial-year Q3 (Jan-Mar). Show the date range beside every quarter label, or decide whether the label should carry the reference period. Needs Keith (Q1).

**S2. An empty current period names neither the empty period nor the age of the results shown.** Birth Registrations (daily): honest "No supply — 26 days ... 26 Sep to 21 Oct 2026" banner, but `verdictLine()` returns "" so nothing says the checks are the 25 Sep supply, four weeks old; supply history ends "No deliveries in the current cycle yet." (period-13), cycle unnamed. Client Register at default date (period-06): two receipts 15 months apart, no period on either. Proposed: always render B1's period line incl. gap/blocked states ("Current period 2026-10-22: nothing yet (due 2:00pm). Checks below: 2026-09-25 supply, 27 days old."); name the period instead of "the current cycle"; name the period on every blocking notice.

**S3. Picker date and page period are linked only inside the picker.** Put the cadence-specific period in the header button ("In place on Fri 23 Oct 2026 · 2026-Q3"), cadence of the dataset on show (both on the agency tier).

**S4. DEFECT: the "outside the dates" notice's reset button does nothing.** At the default date: "You are viewing what was in place on Friday, 23 October 2026, which is outside the dates ... to Thursday, 22 October 2026. [View Friday, 23 October 2026 instead]". Clicking leaves `CURRENT_IN_PLACE_ON` = `DEFAULT_IN_PLACE_ON` = "2026-10-23" and the notice unchanged; template ~10294 `applyInPlaceOn(DEFAULT_IN_PLACE_ON)` offers the default even when the default is out of range; the picker's "Reset to default" is the same no-op. Shows on every page each morning after a build. Offer the last covered date and say why today has nothing yet. Needs a failing test first.

## Notes

- N1. The ED "newest file is not the newest promotion" block (period-16) already uses the right pattern ("PROMOTED INTO 2026-Q3 / 2026-Q3 / ed-presentations@...") - a precedent for B1.
- N2. Quarterly agency/collection sparklines labelled "each week" - label or bucket by period.
- N3. `document.title` omits in-place-on date and period; two tabs on different dates look identical.
- N4. Sample counts disagree at 2025-05-15: header "41 computed runs", panel chart "46 runs", its table ~52 rows (includes Client Register's runs). Undiagnosed.
- N5. Picker date input renders "10/23/2026" (browser locale) beside "Friday, 23 October 2026".

## Daily vs quarterly

"received <instant>" reads acceptably for daily (receipt close to its period) and badly for quarterly; and on daily the gap case hides result age. One period slot - a date for daily, "YYYY-Qn (range)" for quarterly - fixes both.

## What worked

"Periods with no supply" tables name periods precisely on both cadences; Clients' no-data wording at 2025-05-15 is a good model; "Awaiting a decision ... not in place yet. The supply in place is the one received 1 February 2025" separates in-place from newest; `?in-place-on=` deep links cold-load correctly; no console errors beyond a favicon 404.

## Questions for Keith

1. What should "2026-Q3" mean to a reader? (a) keep slot labels, always show the range ("2026-Q3 · 1 Aug–31 Oct"); (b) label by reference period the data covers (needs a field the model lacks); (c) drop "Qn", say "the 1 August 2026 supply period".
2. Where should the period line live? (a) under the dataset name only; (b) also in the header "In place on" button (agency tier would need both cadences).
3. A cross-table check red only because the other table has no supply for the period (B2): (a) keep red, say "not evaluated — Client Register has no 2025-Q2 supply" on the row; (b) a distinct "Not evaluated" state (changes a status rule; note Keith's #95 decision is red only, no new status).

## Keith's answers, 2026-10-22 (Perth)

**Period Q1 - what a period label means, by calendar kind.** Keith: for a calendar of AUTHORED dates (quarters, months, blocks of weeks) the label plus its range, "but option A should show the range as the open and close period" - not the critic's "1 Aug-31 Oct": a period opens when its claim window opens and closes when the next period's claim window opens (qa_tools/common/slots.py `closes_at`; 2026-Q3, due 1 Aug with a 14-day window, is open 18 Jul-18 Oct 2026). For a CADENCE calendar (daily), option C: name it by its day ("the 22 October 2026 supply"). The model already distinguishes the two (authored `dates` vs `cadence: {rule: ...}`).

**Per-dataset windows.** A slot's open/close is per dataset (own due time, claim-window override, days_before). Keith: "Option A, make it clear by showing the calendar's default, and that individual data set may differ." Read as (to confirm): a dataset's own pages show that dataset's window, with the calendar's default beside it where they differ; pages spanning datasets (agency, collection list, picker) show the calendar's default and say that individual datasets may differ.
Confirmed by Keith for a dataset's own pages. Refined for pages spanning datasets (collection, agency, picker): show the calendar's default, and show a note that individual datasets differ ONLY when at least one dataset in that page's scope actually has a different window for that period - computed from the agreement, never a standing caveat; no difference, no note.

**Period Q2 = B: the period line under the dataset name (and in the column/check panels) AND the period on the header "In place on" button.** Mock-ups shown 2026-10-22 (scratchpad mock2/: quarterly-A/B, daily-A/B, overview-A/B): Notifications' button "In place on: Thursday, 22 October 2026 · 2026-Q3"; Birth Registrations' "· the 22 Oct supply"; the agency overview, spanning both calendars, "· 2026-Q3 / the 22 Oct supply" (phone width will need to wrap or abbreviate). Rejected: A, the line under the dataset name only. Dashboard UX reviewer's P4: this shares one narrow control with REQ-DASH-277's "In the warehouse on" relabel - coordinate before either is built.

**Period Q3 = A: a cross-table red caused only by the other table's missing supply stays red and says why on the row**, with the period - "Not evaluated — Client Register has no 2025-Q2 supply" - and the collection-list row in short ("red because Client Register has no 2025-Q2 supply"). Consistent with #95 (strict, red only, no new status) and Q13 = B (counts only toward the declaring table). Rejected: B, a distinct "Not evaluated" state. Per the dashboard UX reviewer (review-dashboard-ux-279v3-95v5.md §4-5), this extends #95's REQ-DASH-272 cell notes and panel sentences through one supply-naming helper rather than adding a second vocabulary.
