# delivery-dashboard-ux on the #95 v3 shape (2026-10-21, before the scoper's draft)

Line numbers refer to dashboard/qa-reporting-dashboard.template.html.

1. **One view per page, said where the reader looks.**
   - (a) verdictLine (6044) ends with the in-place supply's status as `pill(status,"sm")` followed by a sentence, in the `redPromotedMarker` (6952) shape.
   - (b) That status is computed by the warehouse-view rule only. Test: in S4, Clients v1 stays green.
   - (c) Every cross-table row says which supply it was read against: "Read against the Notifications in place, received …" or "Read against the Notifications supply received …, not in place yet". Supplies are named by when they were received, never "v1/v2". This goes after REQ-DASH-264 c7.
2. **The clause in every combination.**
   - Green and amber: "…, and is [pill]."
   - Red, promoted while red: "…, and is [Red]: it was promoted while red."
   - Red, turned red later: "…: it turned red <time>, after <cause>" (reusing `redPromotedBadge`'s how-text, 6895).
   - Nothing in place: unchanged, no pill.
   - Put a `<br>` before the in-place half (it wraps to ~6 lines at 360px). Browser test: reject both v2 files and the page reads green with the promoted line.
3. **A sibling held because of its partner: two wordings,** chosen from the structured record and never by parsing text.
   - S2 (could not run): "**No promoted Notifications for 2026-Q3.** The Notifications supply that came with this one (received …) was held, so 3 of this supply's checks could not run, and this supply is held with it. That is not a fault in this supply's own data. It is checked again by itself once a Notifications supply for 2026-Q3 is promoted."
   - S1 red (ran and failed): "**Held with the Notifications file it came with.** That file (received …) was held, so this supply was re-checked against the Notifications in place, and 1 cross-table check fails against it. It is checked again by itself once a Notifications supply is promoted." Deliberately with NO "not a fault" clause.
   - On the cause's page: "Also holding back the Client Register supply received …, which came in the same delivery." (`affectsLinks`), plus, in S1 red, "If this file is turned down, the Client Register supply needs its own decision."
4. **Aggregates.**
   - One card line per held delivery: "[Red] Held together: Notifications, Client Register (one delivery, received …)". The count stays honest.
   - OPEN FORK: rollups mix staging and warehouse verdicts across datasets (Q-A).
   - Notify once per delivery, naming the cause file (goes with running-thoughts #113).
   - The exec explanation gains a sentence on sibling holds.
5. **REQ-DASH-264.**
   - c1: "the newest result of the view on show". Test with S4.
   - c7: append "Read against…". The S2 could-not-run form becomes "Could not be checked <time>, when the Client Register was re-checked: no Notifications in place for 2026-Q3." Needs Keith's OK.
   - c11: a package re-check of a table's own supply has no `recorded_by` and would count as a second run in `sameDelivery()` (1120). Label it "re-checked against the Notifications in place".
   - c3 and c4 stand.
   - New test for S1 green.
6. **REQ-DASH-204: re-fold to red.**
   - Title, story, c3 and c18.
   - Add the S1-red form and c16's "holding back" form.
   - The v2 findings still apply: c15 vs c7; c1 uses `.notice-exhausted` role=status with no new class; c1's position in the blocked branch.
   - `var(--amber)` is already logged as road-testing #20.
7. **Navigation.** No new URL state. Links via `navHref`/`affectsLinks`, keeping `in-place-on`.

**Questions for Keith:**
- Q-A, the collection card in S1. Recommended: the staging verdict plus a "Held together" line. Alternatives: the warehouse view plus "2 awaiting", or count one delivery as one item.
- Q-B, S1 red wording. Recommended: no "not a fault" clause.
- Q-C, "Read against …" on every cross-table row. Recommended: yes, on both views.
- Q-D, phone width. Recommended: the clause on its own line with a small pill.

## Addendum: further scenarios (2026-10-21)

- **S6, three-file cascade (a dead end).** Investigations v2 red, which holds Notifications v2, which holds Clients v2.
  - The held-with line names the root and the chain: "Held with its delivery: the Investigations file was held, and Notifications with it."
  - The root's page lists everything it is holding back.
- **S8, one sibling turned down.** The line is reworded from the decision log ("…was turned down…; this supply now needs its own decision"). It never names an action that can no longer happen.
- **S15, the partner resupplied (v3 supersedes v2).** The line names the partner's newest supply and what is happening to it.
- **S12, cascade intermediates flicker.** Show and notify only a package's SETTLED result. Results recorded during one cascade count as one delivery (264 c11). Architect: can a build run mid-cascade?
- **S5, a staggered red that cleared minutes later** (accepted). Its supply-history row says so, with the supplier guidance: "Cleared 9:06am, when the Client Register supply received 9:05am was promoted. Send related files together to avoid this." The time window is for Keith.
- **S10, read against a carried-forward supply.** The row label says "…in place for 2026-Q3, carried forward from 2026-Q2 (received …)". The verdict-line clause follows the same rule.
- **S7, one sibling promoted by hand.** Notifications v1 turns red promoted. The clause names the promotion and who made it, from the decision log. Browser test.
- **S16, a staging row's label goes stale** once its partner promotes. Work out "in place / not in place yet" from the date on show, not from when the result was recorded.
- **S9, a past date.** The in-place clause is judged as at the date on show.
- **S13, a widely read table at scale.** "[Red] Held together: Client Register and 4 more (one delivery)". One alert per held delivery, naming the root.

**Further questions for Keith:**
- Q-E (S6): name the root and the chain? Recommended: yes.
- Q-F (S5): a "cleared minutes later" note plus guidance on the history row? Recommended: yes, same-day window.
- Q-G (S12): can a build run mid-cascade? Recommended: no, hold a package's results back until it settles.
