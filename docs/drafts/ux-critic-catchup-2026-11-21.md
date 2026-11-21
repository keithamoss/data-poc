# delivery-dashboard-ux-critic, catch-up review, 2026-11-21

Built pages of 724752c4 (quarterly and daily), plus doctored copies for a retried
run and a could-not-be-checked supply (the real builds hold neither). Screenshots
in the session scratchpad (ux-shots/). Claims to verify before writing up in
plans/post-build-review.md; not yet verified.

HIGH
- H1 defect (REQ-DASH-413 c2/c4, minor): ED Presentations' 10 Oct 2013 row reads
  "Checked in 8s · slow" - that is the full re-check __r1 (cause decision:678, Sep
  2026), not the 793ms arrival; the row is keyed on r1 after a correction moved the
  supply.
- H2 gap (Keith): one 45-minute failed try flattens the run-time trend's y-axis so
  every 2-4s run sits on zero - the very story the requirement names. Log scale, an
  off-scale marker, or scaling to completed runs.
- H3 (REQ-DASH-148 check; Keith on whether unchecked runs belong in the trend):
  cp-clients' 1 May 2025 supply is "Fail - Could not be loaded ... nothing is
  checked" in the queue while its cycle row reads "Pass · Checked in under 1s";
  three two-files supplies too (run_time_ms ~74, not_checked false), so the CP
  trend dips to zero four times.

MEDIUM
- M1 the could-not-be-checked banner says it twice (blockedBannerLead and
  couldNotCheckWords); "crashed on 9:09am" -> "at"; mixed dashes.
- M2 (Keith, REQ-DASH-148's model) our own failure shown red with a Fail pill,
  against REQ-DASH-415's "don't chase the supplier for our own failure".
- M3 a weekly dataset's missed Mondays counted as "9 days" across 57 days.
- M4 four separate "No earlier supply to stand on" items for days a weekly dataset
  never owes, out of order (Thu sorts last).
- M5 defect: the run-time axis labels a middle tick "under 1s" (0s / under 1s / 1s).
- M6 the tries note's summary names only the try before the success (hides the 45m
  timeout); doubled numbering; full dates twice per line; "2m 00s"; ~25 lines tall
  on a phone. The summary wording is signed.

LOW / NITS
- moved notice at column/check depth (fixed after this build, #492 F2); the period
  banner still shows on a moved page with ?period=; the moved link's text is the
  bare URL; an ambiguous comma in the not-owed weekday row; raw dataset ids in
  held-supply headlines and the calendar notice; hollow markers labelled only by
  tooltip; "View as table" lacks aria-expanded; the snapshots panel leaves focus on
  its trigger; the demo caption's MOTHMAN_ASSET not code-styled.
- probably older: the supply-cycle table makes the page scroll sideways at 390px;
  a supply row moves the as-of date and is not keyboard-reachable; an empty
  current cycle hides the newest tries note behind "Show all history".

Verified working: the asset name everywhere, the not-production marker, the moved
notice at agency and dataset depth (announced, Back/Forward, mobile), the empty
archive wording, #488's fix, the slow marker, View as table, no run times on home
or agency pages, the weekday and annual labels.

## Keith's answers to the five product questions, 2026-11-21

1. Trend scale: an off-scale marker for a value beyond the chart's range.
2. Unchecked supplies: say "not checked" and leave them off the trend.
3. M2, our own could-not-check failure: KEEP the red Fail and its rollup, and reword the banner so its first line says our pipeline could not check the supply and that this is not a problem with the supplier's data.
4. M3/M4, weekly gaps: count what the dataset owes, in its own unit - "9 Mondays with no supply, 21 September to 16 November"; several weekdays -> "9 owed days"; daily keeps "days".
5. M6, tries note: amend REQ-DASH-414's signed summary to name how the last try ended (e.g. "3 tries - the last stopped at the 45-minute limit"); inside, one number and one date per try. Exact amended wording still needs Keith's yes.

These go into post-build-review #493 with H1, M5, M1 and the nits; fixes are built test-first.
