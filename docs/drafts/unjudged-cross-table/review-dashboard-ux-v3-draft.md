# delivery-dashboard-ux on requirements-draft-v3 (2026-10-21)

**Landed:**
- 272 c1, c3 and c7 (the clause), c2 (the pill), and c6 ("read against", provisional on Q12).
- The 264 c1 amendment via 269 c6.
- 272 c8 (a re-check is not a second run), 267 c10 (no intermediate results), 269 c10 and 272 c14 (S4).
- S8's wording, 272 c11 (rejecting returns the page to the warehouse verdict), and Q-D.

**Partly landed:**
- 272 c4's S1-red row wording (see D3).
- The card line: in Q11's option only, with no 204 criterion, although the carry-over table claims one.
- S6, root and chain: sign-off only.
- S5's "cleared" note: sign-off only.

**Missing:** the names in 272 c4 must be real `<a href>` links via `navHref`/`affectsLinks` that keep `in-place-on`; without them a cascade is a dead end. S15 needs no criterion: 268 resolves it.

## Defects (fix before sign-off)

- **D1.** 272 c2 and c7 both add the red-promoted text, so it prints twice. Keep c7 and delete "with REQ-DASH-126's label beside it" from c2.
- **D2.** c1's example and c14's assertion don't match `fmtInstant` ("9:00am Monday, 1 July 2024") or STATUS_LABEL ("…, and is Green.").
- **D3.** Vocabulary.
  - The dashboard should say "held back", not "was not promoted".
  - Use "received <instant>", not <date>.
  - Use "Held back together" / "Held back with" (plain "held" collides with REQ-PIPE-078).
- **D4.** 272 c6 has no "nothing in place" form. Add "Read against: no <table> in place for <period>", and leave c6 off rows that carry c4's sentence.
- **D5.** summary-v3 contradicts itself on S1-red's top-of-page line (lines 117-119 against 762-763). That is Q3 below.

## Wordings

- **S1-red row:** "Re-checked 9:05am Friday, 3 July 2024 against the Notifications in place (received 9:00am Wednesday, 1 July 2024): the Notifications received with this supply was held back."
- **S2 row:** "Could not be checked 9:05am Friday, 3 July 2024: no Notifications is in place, and the Notifications received with this supply was held back."
- **S1-red top line (proposed):** "**Held back with the Notifications received with it.** That file (received …) was held back, so this supply was re-checked against the Notifications in place, and 1 cross-table check fails against it. It is checked again by itself once a Notifications supply is promoted." No "not a fault" clause.
- **S2, 204 c2:** v2's wording is now partly untrue. Proposed: "**No promoted Notifications for 2024-Q3.** The Notifications received with this supply (…) was held back, so 3 of this supply's checks could not run. That is not a fault in this supply's own data. They run again by themselves once a 2024-Q3 Notifications supply is promoted."

## New scenarios

- **N1.** A partner not yet due, e.g. Clients Q4 on 2 Jan with Notifications not due until 15 Jan: 13 days of red, explained only on a page that says nothing about it. Proposed: a muted line on the partner's page, "Not due until … — Client Register is waiting on it" (`noSupplyNote`'s shape).
- **N2.** Q5's owed re-check is itself a flicker. Proposed: "Not yet re-checked against the Notifications promoted 4:55pm …; the re-check runs on the next processing pass." Don't notify unless the re-check fails.
- **N3.** 268 c4's "promoted by the rule, with …" record goes on the supply-history row. That replaces the S5 "cleared" note and makes Q-F concrete.
- **N4.** An inherited supply in the clause: `verdictLine`'s in-place branch reads `promotionState.promoted` (2834-2836) and may miss an inherited supply, saying "Nothing is in place". Proposed: "…carried forward from 2024-Q3 (received …)". The builder must check `promotionStateOn`.
- **N5.** S7's hand promotion: the "turned red after <cause>" text names the person's promotion from the decision log.

## Questions (merged)

1. Q11, the card. Recommended A: keep the rollup and add one "Held back together: … (one delivery, received …)" line.
2. Q12. Recommended A: "read against" on every row, with D4's rules.
3. S1-red, top of page or row only? Recommended: a top line.
4. S2, may the "No promoted" line name the package-mate? Recommended: yes.
5. S6, name the root of a chain? Recommended: links always, and name the root when the chain is longer than one hop.
6. N1, a partner not yet due. Recommended: the muted line.
7. Q5. Recommended A, with N2's wording and no notification.
8. Q-F via N3. Recommended: show the record on the history row.

Agrees with Q10 A and Q6 A.
