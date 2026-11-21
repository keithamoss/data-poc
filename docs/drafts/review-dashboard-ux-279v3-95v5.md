# delivery-dashboard-ux on #95 v5 and REQ-PIPE-279 v3 (2026-10-22)

(Returned as a report - no write tool - saved by the main session, condensed with every finding kept. Line numbers: dashboard/qa-reporting-dashboard.template.html.)

Contexts: 272 c21 waiting state and 275/204 notices = error/failure (weighted highest); grid = at-a-glance; 279 trend/compare/N1 = drill-down; 277 = routine. No new URL state; ids and `in-place-on` kept; links via navHref/affectsLinks. One existing deep-link defect made worse by N1 (S7).

## 1. v4 carry-over
Landed: 272 B1 (c7 third bucket), S1 (c8 worst of marks), S2 (c8/c11 "·"), S3 (c12/c15 row stays one button), S4 (c16 phone labels), S5 (c21), hide empty column (c6), crossTableRowOrder kept, joint-promotion row for earlier hold-back (c20), could-not-run panel clause; 275 data-held-back, before 204's notice, superseded+rejected, root forewarning; 204 data-no-promoted, "was turned down"; 277 both label places + 182's sentence; 264 c5 open question B and its test. Not landed: S5 incomplete (B1), 204 stale test (B2), S15 reached 275 not 204 (S5).

## 2. Blocking
**B1. 272 c21's waiting state is worded for one of four cases; walk-through 1 step 2 never says what Notifications' page shows.** (a) Sibling not yet checked: at step 2 Clients' run has recorded Client reference against Notifications v2 before Notifications' own run - its page could show one Pass and nothing else (half-built view, possible false green). (b) Every file checked, gate still owed (crash after checking, budget stop, contended lock): "2 of 2 files checked" contradicts "waiting for the rest". (c) A package of one with a contended period lock: owed as package-gate, no "rest of its delivery". Fix: mirror 266 c15's forms - unchecked member "Being checked with its delivery (received <instant>): <n> of <m> files checked. Nothing needs deciding yet." (no pill other than that line); checked, partners not yet: today's wording; all checked or package of one: "Checked, being gated (received <instant>). Nothing needs deciding yet."; keep the crash line. Add Notifications' page to walk-through step 2 and an e2e case for the unchecked member.
**B2. 204 c12 and c13 contradict.** c13 is the stale v4 S2-strict test V4-Q1 made false. Delete c13.

## 3. Should-fix
- **S1.** An awaiting page showing only "Against what's in the warehouse" reads as the warehouse's own result (Order A 9:00: verdict clause "The supply in place in the warehouse ... is Green", grid below shows Client reference Fail). Hiding the empty column removes the contrast. Caption the grid on an awaiting page: "Results for the supply received <instant>, awaiting a decision" (reuse the blurb's slot); e2e assertion.
- **S2.** Third bucket has no truthful panel sentence (c12's four forms say in-warehouse or "not in the warehouse yet", both false for Clients v1 after Clients v2 promotes). Add "Read against the <dataset> received <instant>, since replaced in the warehouse by the one received <instant>" and "..., since turned down"; same in the compare list.
- **S3.** "— why it is held back" only for criterion-6 re-checks. Order B red, 9:05: Clients' row Staged "Pass, Notifications received 21 Oct", Warehouse "Fail, Notifications received 1 Jul", Red pill, no suffix, no notice (the Fail is the 9:00 arrival result). c9's condition becomes "the cells differ and the counted result is the warehouse one", whichever run recorded it; accessible name gets c14's "read against a supply itself awaiting a decision".
- **S4.** Trend rule for a result whose partner left stated two ways (walk-through keeps Notifications v2's 9:00 point; c18 drops results about a supply not in the warehouse from an in-warehouse page's sparklines, so Clients' trend loses its 9:00 Fail while history says held back at 9:00). 279 c10 sides with the walk-through. History and trend show every evaluation of the supply on show; pill, counts and grid cells use counted results only; reword c18.
- **S5.** 204 c2 has no "superseded" form (mirror case, Clients v3 replaces held-back v2): add "has been replaced by the one received <instant>".
- **S6.** c7 and c18 overlap on an in-warehouse page (S1 5a: Clients v2's arrival result read waiting Notifications v2 - c7 staged cell vs c18 forbids). c7's staged bucket applies only on a waiting supply's page.
- **S7. Existing deep-link defect, more common under N1 (b).** `setCompareIdx` (line 8648) drops `?cmp=` when `idx === history.length-2`, but the panel's real default is `defaultCompareIndex()` (line 5152), which skips not-evaluated and same-delivery points. When they differ, choosing "(previous)" writes an unneeded `?cmp=`, and choosing the point just before drops it, so a cold load or copied link opens a different comparison. 264 c11's amendment should require one function for default and URL rule, with a JS test. Also a road-testing sighting (failing test first, then fix).

## 4. REQ-PIPE-279 consequences
- N1: agree (b), on two conditions: each compare/history entry names its cause and (with #95) its view and partner (264 c11 "from the <table>'s run" + 272 c13 + S2); and S7's one-function rule.
- More trend points: a staggered quarterly delivery gives 2-3 points minutes apart vs one for a zip, reads as several supplies; extend 264 c11 to the sparkline tooltip (a non-own point names its cause, "from the Client Register's run, 9:05"); list counts, sparkline and panel count one function (279 c10) - also period-clarity N4.
- Retiring the same-day merge is right (312 same-day pairs now two points, honest under K3 = C; N1 (b) keeps comparison useful).
- K7 overtaken for cross-table rows: #95's 272 c8 notes and c12 sentences (Q12 = A) name the supply read; period-clarity B2 must extend those, not add a second vocabulary. Tell both scopers.

## 5. Conflicts with period-clarity
- P1 (should-fix): 272 names supplies by receipt day/instant only; have 272 c22 build every supply name through one Python helper so period-clarity changes it once.
- P2 (should-fix): REQ-PIPE-081 c1's sentence is reworded by 277 and extended by 272 c1; period-clarity's line goes above the 275/204 notices and the verdict line, not a third rewording of 081 c1.
- P3 (note): `<period>` in 204/275 notices and 271 warnings - leave the open/close window to the period line; format through `fmtPeriodOrDay`.
- P4 (note): 277's "In the warehouse on" and the critic's S3 period suffix share one narrow control; coordinate.
- P5 (note): 204 c17's "Not due until <instant>" uses the partner dataset's own window (Keith's per-dataset answer).
- P6 (note): bucketing sparklines by period (critic N2) would merge K3 = C's separate points.

## 6. Notes
277 NFR LENGTH still says "hence open question 1" (stale). 275 c4's joined card line compresses a shared date - state the rule, two full instants when days differ. Joined forms read well; "Nothing needs deciding yet" is the right framing. Walk-throughs otherwise consistent end to end.

## Questions for Keith
None.
