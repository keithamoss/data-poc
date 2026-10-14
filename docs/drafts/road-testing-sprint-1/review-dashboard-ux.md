# delivery-dashboard-ux review of sprint 1 (REQ-DASH-224..228), 2026-10-14

Advisory; recorded by the main session. Read as if the ~17:15 answers were folded.

## Severe
- S1: on a 0-100% scale an all-green history draws a solid red line along the
  bottom of every row (both series at 0%, red on top). Proposed (225, reused by
  226/227): neutral 0% baseline (--line-strong); a series is drawn in red/amber
  only where above 0%; a dataset green on every run shows no red or amber pixel.
- S2: .spark is width:100% with preserveAspectRatio="none" (L480, L3324) and the
  tile is 16px tall, not 28 (L588); non-uniform scaling distorts dash and stroke.
  Proposed: vector-effect="non-scaling-stroke", stroke >= 1.5px; NFR says ~16px.
- S3: M = 0 reads "All 0 columns green". Proposed: "No column has a verdict on
  this date" in faint ink, no lines (same for 226 with datasets).

## Significant
- G1: dashed already means something on the check chart (amber/red dashed =
  warn/fail thresholds, grey dashed = did not report; L3545-3546, L3467, L3539).
  Recommend amber as round-capped DOTTED (1.5,2.5). (Q2)
- G2: dark --bad #EF5A6F vs --warn-fill #BC7600 ~1.1:1 lightness; light
  --warn-fill on white ~2.7:1 (< 3:1). Proposed: amber series >= 3:1 against the
  surface in both themes; red and amber distinguishable in greyscale captures;
  use --warn not --warn-fill.
- G3: row overload. Line 1 bold "3 of 15"; line 2 "2 red, 1 amber · incl.
  Supply-level checks"; lines to the right of the text. Header "Columns not
  green"; all-green "All 15 green". (Q1)
- G4: key as a .legend-key line above each collection table (exec L5447, dataset
  page L6387): "Columns not green - [solid] red · [dotted] amber, share of columns
  on each QA run. Supply-level, table-level and cross-table checks each count as
  one column." Same sentence under the dataset page trend's title. (Q4)
- G5: agency card M vs its "8 datasets" footer (card-meta L5473): "2 of 8 datasets
  not green" when nothing is left out, "2 of 5 counted datasets not green" when
  some are, with REQ-DASH-180's not-counted line directly beneath. (Q5)
- G6: card trend per NQ2 B plots a date grid; label must say which, e.g.
  "Datasets red and amber, each week" (Q3); accessible name with latest values;
  a render budget the critic can check: Agencies tier renders in under 400ms on
  the built page; if not, raise it rather than thinning the series.

## Minor
- Quiet states per element: list reason rows keep colspan; Turned off / Not
  counted cards show no count but the trend in neutral ink with its label (#57);
  tiles with no verdicts or < 2 runs show no lines; one run so far reads "One QA
  run so far".
- 228: the measure as horizontal text above the plot's top-left, not rotated.
- 226 and 227 also say a cold-loaded past-date link shows that date's figures.
- Reuse pill(), .legend-key, the View-as-table toggle; the count as plain muted
  text, no new chip.

## Questions
1. Row text: A "3 of 15" bold + "2 red, 1 amber", unit only in header / B unit on every row.
2. Amber style: A dotted / B dashed.
3. Card trend grid: A weekly / B per period.
4. Key: A .legend-key line above each table / B in the column header.
5. Card wording when some not counted: A "2 of 5 counted datasets not green" + the not-counted line under it / B as drafted.
