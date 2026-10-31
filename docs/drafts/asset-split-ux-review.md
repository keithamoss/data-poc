# Asset split v1 - dashboard UX review (2026-10-31)

Reviewed REQ-DASH-347, REQ-PIPE-354, REQ-DASH-355 and REQ-DASH-356 against the template and the two guides. Advisory; nothing edited.

## MUST
1. The period list stops at the period holding the build's date (355 c2). At files_go_to_period 1, collections are already filling next quarter, so a period with real supplies could not be chosen. Bound the list by the newest period any slot has opened (periodOpenedOn).
2. "Had not opened" is per collection, not per page (355 c6). On the agencies list some collections will have opened P and others not, so put the sentence in each collection's panel instead of replacing the page.
3. What the date means once a period is set. "In the warehouse on" and the past-date notice are both false when the supply on show is no longer in place (the J1 case). While a period is set, show one statement in #in-place-on-past-notice, styled .in-place-on-range-notice, e.g. "Showing 2026-Q2 — results recorded by the end of 31 Oct 2026 · Clear period". This also prevents the mode error of reading Q2's green as today's.
4. Back and forward. The date is a filter that history does not step through, except for scenario jumps. Under Q1 (a), Back from a period page would leave the period set and the agency page silently changed. Reuse the jump's from/to pattern so Back undoes a period set by navigating there; the control itself uses replaceState, as the date does.
5. The old-link redirect (354 c5). Routes live in the hash, which never reaches the server, so the redirect has to be landing-page JS.
   - It must use location.replace.
   - It must map by collection where the route names one.
   - It needs a landing for routes with no agency (#/plans, #/feedback, #/demo).
   - The test loads a real old URL and asserts the final location.

## SHOULD
- Say which wins when the path's period and ?period= disagree: the path, rewriting the parameter.
- Label the control "For day" on the daily asset.
- Read "Period: all current" when nothing is chosen.
- Put the period in document.title and #route-announcer.
- Name the agency sections "Source supplies for <P>" and "Derived releases for <P>", hide an empty one, and say what happens to a mixed collection.
- Resolve the clash between 356 c7 and 347 c2 on a not-owed row.

## NIT
- "Weekdays" rather than "5 days a week".
- Group a 55-quarter list by year.
- A one-line description of each asset on the landing page.

## Proofs that cannot fail
- 355 c7 should compare before and after DOM captures of three pages, asserting each is non-empty.
- 356 c7 should first assert that the chosen day is not a Monday and that the dataset is there.

On Q1: (a), with MUST 4. The arrival-context drill keeps setting the date, not the period.

## Questions for Keith
1. Section names: (a) Source supplies / Derived releases (recommended); (b) the draft's wording; (c) Source supplies / Linkage and geocoding.
2. Where old links with no agency go: (a) the landing page with a note (recommended); (b) the quarterly dashboard.
3. Does Back undo a period set by opening a period page? (a) yes (recommended); (b) no.
4. On the daily asset: (a) keep the control, labelled "For day" (recommended); (b) hide it.
