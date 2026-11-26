# REQ-DASH-182: its own dashboard UX review (2026-10-14), and Keith's answers

Requested by Keith before signing ("send it to the UX reviewer first"). The
review is advisory; recorded here by the main session from the agent's report.

## Findings (ranked)

1. HIGH - a period a dataset owes nothing in reads as missing supply at the
   top of the page. `clipDatasetToInPlaceOn` marks the supply in place stale
   when the run date is before `periodStartDate(...)`, which reads the
   CALENDAR's periods, not the dataset's participation. So on a May or
   November date cp-case-workers (Feb and Aug only) gets a "No data" pill and
   "nothing has landed yet in this dataset's current expected cycle", in the
   dataset page and the collection table - directly above 182's "Not owed"
   row. At ~30 quarterly datasets, ~30% deliver once or twice a year: 6 to 9
   false "No data" in a typical quarter. REQ-DASH-180 c5 covers it but is
   built later. Proposed new 182 criterion: WHERE the current period on the
   date on show is one the dataset owes nothing in by participation or
   not_expected, THE SYSTEM SHALL NOT treat the supply in place as stale, SHALL
   show its verdict as for any dataset between deliveries, and SHALL NOT show
   that line or a No data pill because of that period. 180 c5 keeps only the
   turned-off case.
   **BROWSER CHECK (main session, 2026-10-14): the reviewer's case did NOT
   reproduce** - cp-case-workers at 2025-06-15 and 2026-06-15 shows no "No
   data" and no "nothing has landed yet". A DIFFERENT, real false "No data"
   did: a supply received inside its claim window but before its period's
   start (Child Protection's 2025-Q3 delivery, 2025-07-19) reads "No data"
   for the whole period on every dataset - post-build-review #178. The SLA
   tile mismatch (finding 2) WAS confirmed.
2. HIGH - the SLA tile contradicts the row: `agreement.cadence()` takes months
   from the calendar ("Quarterly (Feb/May/Aug/Nov)") while the row says
   "outside its agreed months (Feb, Aug)". And the draft names the tile three
   ways ("agreement tile", "delivery-time tile", "SLA tile"); the page's key
   reads SLA (`.sla-tile`). Proposed: the SLA tile names the months the
   dataset participates in on the date on show, in the row's form, with a
   frequency word matching the count, and the authored reason as a visible
   muted second line while participation is not `all`; 180 c16 says "SLA
   tile" too.
3. MED-HIGH - what a quiet row looks like: a label-only `.supply-cycle-label`
   block, no table, kind label where "N deliveries" sits, newest first among
   the cycles, no pill of any kind, never in "Periods with no supply"
   (recorded as a decision so the critic does not flag the contrast), period
   worded with `cycleLabel()` like its neighbours, hierarchy red "No supply" >
   "Accepted" tag > owed-nothing (no pill, muted).
4. MED - collapsed runs reuse `gapText()`'s range and unit; no count for a
   single period; a run still open on the date on show says "so far"; the run
   holding the current period is the current-cycle block with its "Current
   cycle" tag, not shown twice; runs group by kind, reason and stands-on;
   "Show all history (N cycles)" counts what it hides.
5. MED - criterion 9 names `standingInHeading` (the standingInDetail panel's
   heading near the top, not "above that row"); its wording is the kind label,
   the reason in `.promo-why`; the row itself says "Inherited from <period>"
   as muted text, no pill.
6. MED - "Not yet owing" has nowhere to appear: before the first participation
   version the page takes the never-supplied branch ("Nothing had been
   supplied by this date ... Pick a later date"). Proposed: that banner reads
   "Not owed yet - owes supplies from <date>", and the SLA tile reads the same
   where it exists.
7. MED - one function returns {kind word, label, reason} for every
   owed-nothing period, used by 182's rows, 180's turned-off rows (c15),
   209's "Not owed" group and counting line, and the standing-in heading; the
   separator is the page's em dash.
8. LOW - c7 rewords built behaviour: `cadenceLabel` already handles
   days_before (post-build-review #142); test both the 1-day and N-day forms.
   The CLI's `schedule show` probably needs the same words (for
   delivery-cli-ux).
9. LOW - c8's words: 1 Yearly, 2 Twice a year, 4 Quarterly, 12 Monthly,
   otherwise "N times a year"; "various days" where days differ (also the
   "authored" type, blank today).
10. LOW - c1 scoped to the dataset page's supply history (and 209's view), and
    rows appear even when the dataset has no supply cycles yet.
11. NOTE - no route or URL work; a cold-loaded past-date link rebuilds that
    date's rows and SLA label (for the post-build critic); words, never colour
    alone.

## Keith's answers (2026-10-14)

- Q1 SLA tile: A - the dataset's own months and frequency ("Twice a year
  (Feb, Aug, day 1), by 09:00"), the reason on a muted line beneath.
- Q2 the false "No data": A - REQ-DASH-182 takes the participation and
  not-expected cases; REQ-DASH-180 c5 keeps only turned-off. Confirm in a
  browser first and write it up as a post-build finding.
- Q3 before a dataset owes anything: A - "Not owed yet - owes supplies from
  <date>", replacing "Nothing had been supplied by this date".
- Q4 inside 209's "Not owed" group: A - labels unchanged on every page.

Findings 3-5 and 7-11 are the reviewer's proposals, not dependent on the
answers; they are folded with the answers before REQ-DASH-182 is presented
again for sign-off.
