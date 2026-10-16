# delivery-architect review of sprint 1 (REQ-DASH-224..228), 2026-10-14

Advisory; recorded by the main session. No new embedded data, no new command
group, no supply rows read.

- B1 BLOCKER: 'turnedoff' does not exist in the page (REQ-DASH-180/182 signed,
  not_started). 225 c16, 226 c3/c6 and 226 c11's turned-off test cannot be built
  or failed first. Options: (a) build sprint 1 after REQ-DASH-180; (b,
  recommended) drop the turned-off clauses here and add to REQ-DASH-180 a
  criterion extending 226's count test with a turned-off dataset; 226 c11 uses
  a scheduleNotAgreed dataset (inNoRollup, template:2820).
- H1: the pill carries a check's last verdict forward (clipDatasetToInPlaceOn,
  template:2670-2679); a per-run line does not, so count and last point can
  disagree. Proposed 224 c1: a check's verdict on a run is its most recent
  recorded verdict on or before that run among the runs in place on the date on
  show, as clipDatasetToInPlaceOn takes it, so the last point equals the count.
- H2: with NQ2 B "one function" is two. No per-date dataset-status series
  exists; the only full-status-as-at function is buildData(date)
  (template:3120-3218). Extract datasetStatusesOn(dateStr) from buildData, used
  for the card count and its trend; never precompute in Python
  (dataset_status.py knows no blockers/noSupply/refusals). 224 c7 amended
  accordingly.
- H3: cost - buildData per point is the whole page's work, and datasetTile
  (3114-3117) is quadratic (rebuilds every CP dataset per dataset). Memoise
  per-feed builds first; bounded grid; one buildData per grid point for all
  cards; compute after first paint, cache by date; at most N points; measure
  with a synthetic 30-dataset fixture.
- M1: "including supplies later withdrawn" contradicts clipping (2605-2607):
  "runs in place or awaiting on the date on show, as the pill uses".
- M2: key points by run_id, not h.date (two runs on one day are summed today).
- M3: retired checks - excluded from history (224 c1) but included in
  datasetStatusByRun / status_by_run (dataset_status.py:313-317): state the
  divergence or add a consistency test.
- M4: 224 c10 cases fail only because the function doesn't exist; add one that
  fails on behaviour (amber + red on one column -> 1 red unit).
- M5: tests-js/sparkline-endpoint.test.js asserts the endpoint dot; remove or
  rewrite in the same change as 225 c13.
- L1: file checks out is free (fileChecks beside columns, 4319-4326): "reads
  ds.columns only, never fileChecks (REQ-DASH-097 c2)". L2: group sections by
  c.scope. L3: vector-effect non-scaling-stroke. L4: say whether a quiet card
  shows the trend. L5: 228's rule kinds from committed contract/ YAML (fast CI
  half). L6: no Python twin needed.
- Code: one pure unitCounts(columns, runIds); one twoLineSparkline(series,
  {quiet,label}); datasetStatusesOn(date); lift rollup()'s live filter (2833)
  into a named predicate; remove the 0.05 floor and endpoint-dot code.
- Questions: Q1 card trend grid (answered: weekly, Keith's UX Q3); Q2 a check
  with no result on a run - carry forward (A) / leave out (B); Q3 retired checks
  in historical points - excluded (A) / included (B).
- Build order: 0 memoise datasetTile + rollup predicate; 1 228; 2 224; 3 225;
  4 227; 5 226; 6 the turned-off clauses in REQ-DASH-180's build.

## Keith's answers (2026-10-14 evening)
- B1: **(b)** - the turned-off clauses move out of sprint 1 into REQ-DASH-180 (a
  new criterion extending sprint 1's count test with a turned-off dataset);
  226's test uses a no-schedule-agreed dataset meanwhile. Needs an amendment
  to signed REQ-DASH-180, wording for Keith at sign-off.
- Q2 (a check with no result on a run): Keith asked "how could it have no
  result?". Checked against the real reports: 9 runs (8 cp-case-workers in
  May/Nov deliveries it owes nothing, 1 cp-clients) are arrivals received but
  HELD and never checked, carrying only 'no rule defined' (inactive)
  placeholders; otherwise a check added later simply has no earlier history.
  Answer: **no point for a run that was never checked** - only checked runs
  become trend points, so the count and the line's last point agree by
  construction.
- Q3: **(A)** - retired checks excluded from historical points; the divergence
  from the supply-history per-run pill (datasetStatusByRun includes them) is
  recorded as a decision.
