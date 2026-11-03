# delivery-cli-ux on the #95 v3 shape (2026-10-21, before the scoper's draft)

1. **Say "held back", never "held", for a gate outcome.**
   - "Held" already means a filing hold: queue group "Held - no period yet" (`filing_tui.queue_flow`:921), `held_blast_radius`, and "held - out of <slot>".
   - The gate's own word is "held back" (`decision_words`, `_gate_words`).
   - Check with NO_COLOR and a pipe.
2. **The cause is read from the record and names the partner supply.**
   - S1-red: "held back by the rule, not by you - Notifications' 'Client reference' check, re-run against the cp-notifications supply in place (received <date>) because cp-notifications' supply in this delivery (received <date>) was held back, came back red."
   - S1-green: "promoted by the rule ... re-checked against the cp-notifications supply in place ...: green."
   - S2: reuse the `Unrunnable` STAGED_AWAITING_DECISION wording, plus "This supply's own checks passed; it is promoted once a cp-notifications supply is."
   - Say so when the supply's own checks were green.
3. **Outcome panels.** The next step names the sibling first: "Decide cp-notifications <period> (received <date>) - promoting it re-checks this one". A hand promotion of this supply comes second. Today's text is "Promote or reject it next".
4. **At ~30 datasets.**
   - One cause line, then one line per resulting outcome, using `_grouped`'s eight-name limit.
   - A cascade prints the final state only, naming what each hold traces to.
5. **Exit codes.**
   - Red-only means the existing EXIT_RED=1 is right. v2's exit 3 is withdrawn (3 is already used twice).
   - REAL FALL-THROUGH (S7): `one_table.py`/`many_tables.py` exit from the run's own staging-view results, so a cp-clients v2 that was green against staged v2 and then red on the package re-check would exit 0.
   - Criterion: `mothman cp qa` and `mothman pipeline process` exit 1 when any supply they touched ends held back on a red, a package re-check's red included. The re-check's results appear in the report.
6. **Override confirmations predict the knock-on**, read from the recorded verdict, on the flag route too.
   - Promoting cp-notifications v2 by hand: "Re-checks cp-clients' waiting supply ... against this one; if green, the rule promotes it."
   - Promoting cp-clients v2 by hand over its red: "will very likely become 'Promoted, then re-checked worse'".
7. **The queue.**
   - A sibling-held-back supply keeps its own row, sorted directly after its cause: "held back - waits on cp-notifications <period> (same delivery)".
   - Picking it prints "Deciding cp-notifications <period> settles this one".
   - The sibling reason wins over the ANOTHER_VERSION_WAITING wording.

**Other scenarios:**
- S3 (a real gap?): in S2, a person REJECTS cp-notifications v2. Re-checks run only on promotion, so cp-clients v2's reason stays "a supply for cp-notifications is staged awaiting a decision". That is now false, and the queue sends the person to decide something already decided. Does `knock_on` fire on rejecting a never-promoted staged supply? Needs the architect.
- S4: a three-table cascade (clients, notifications and investigations, all v2 over v1, notifications red). investigations v2 is held back, clients v2 promotes. Show the final state and what each traces to, and never say investigations' own data failed.
- S6: `mothman cp qa --commit` on one file of an unchecked package should say "not gated yet - waits until every file in delivery <name> is checked (1 of 2)", exit 0, and offer no decision.
- S8: a decision lands mid-cascade. The "Somebody else's decision changed what this one does" re-confirm must include the package re-check in its key.
- S9: low priority. A dim line with the supplier guidance when related files arrive as separate deliveries.

**Questions for Keith:**
- Q1, the queue in S1-red. Recommended A: its own row under the cause. Alternative B: indented only.
- Q2, the count. Recommended A: "12 waiting on a decision (3 only because another file in their delivery is)".
- Q3, S3. Recommended A: rejecting a package sibling also re-evaluates the others (bends "only on promotion" for package siblings). Alternative B: leave the reason stale until the next promotion.
