# delivery-dashboard-ux review (2026-10-14): Feedback tab (219/220/222) and
# the dashboard halves of 175/221/166

Advisory; recorded by the main session.

## High
- H1: closePanel cold-load defect (see unsigned-triage/review-architect.md;
  post-build-review #180). Proposed 222 c9 / general fix: close in place with
  replaceState when the page did not push the panel; new-tab test.
- H2: past-date evidence links (#18, #19) have no landing mechanism - as-of is
  global and sticky. Proposed: 219 allows in-place-on= in Evidence; 220 follows
  it like a Scenarios jump (setInPlaceOnQuietly + jump bar, Back restores the
  date), with a neutral jump-bar wording.
- H3: two status palettes on one card - REQ_STATUS_CLASS (:7497) colours built
  green. Proposed: requirement status as plain words in the link text; exactly
  one status pill per card; say the divergence from Plans/Requirements is
  deliberate.

## Medium
- M1: "Heard" undersells items already in a road-testing sprint (#1, 2, 4, 6,
  9, 10). (Q2)
- M2: Parked / Won't do / Couldn't reproduce label the fourth line "Why not",
  not "What we built".
- M3: ordering interleaves "We noticed" with the reviewer's own. (Q1)
- M4: a withdrawn not-supplied mark has no supply-history row - show it in the
  cycle-table cell (:6057) and accepted-gaps list (:6242) in excuseNote()'s
  shape '<annotation> · withdrawn by <person>, <instant>: <reason>'.
- M5: a withdrawn acknowledgement: the awaiting tag returns with the withdrawn
  line beneath; the ack reason as visible text, not only title=.
- M6: DECISION_DONE wording: "no longer acknowledged", "no longer marked not
  supplied" (REQ-DASH-198's de-substitute/un-inherit precedent).

## Low
- 222 mark reuses .arrival-notice's left accent bar; rows get data-req-id, title
  tabindex=-1. Stale req= reuses .stale-link-notice with role=status (not
  forgetStaleSegment). Header button opens at top and drops req=; req in STATE.
- Focus returns to the opening link when the panel closes; list scroll kept.
- 220: <h2>Feedback</h2>; header link as <a href="#/feedback"> with emoji like
  its siblings; don't show entry numbers; "Evidence" -> "Where to see it" (Q5).
- 175's open question (placed turned-off hold stays in the quiet section): yes.

## Questions
1. Card order: A reviewer's cards first, then a "We noticed" section / B one list.
2. Sprint-scheduled items with no requirement: A cite the sprint, derives
   "Planned" / B keep "Heard" / C rename "Heard".
3. Past-date evidence links: A allow in-place-on=, land via the jump bar / B today only.
4. closePanel fix scope: A all five panels / B Requirements only.
5. Fourth line's label: A "Where to see it" / B "Evidence".

## Keith's answers (2026-10-14 afternoon)
1. Card order: **A** - the reviewer's "You told us" cards first by date, then a
   "We noticed" section; the summary line counts each group.
2. Sprint-scheduled items: **A** - a card may cite its road-testing sprint in its
   links, which derives "Planned".
3. Past-date links: **A** - allow in-place-on=, land via the Scenarios jump bar
   (neutral wording), Back restores the Feedback tab's date.
4. closePanel: **A** - fixed now as post-build-review #180, all five panels.
5. Fourth line: **A** - "Where to see it".
