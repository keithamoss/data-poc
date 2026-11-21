# #95 draft: delivery-architect review (2026-10-14)

Advisory; recorded by the main session from the agent's report. The agent had
no shell, so the main session ran its database estimate: of the 69 Child
Protection supplies the rule promoted, 9 had an unjudged cross-table check
(cp-carers 2/15, cp-clients 3/14, cp-investigations 2/14, cp-notifications
1/14, cp-placements 1/12; 5 of the 9 'not yet due') - a lower bound, since
checks filed under a sibling's run are not counted, and B1's deadlock is
unbounded until fixed.

Verdict: a distinct, ordered INCOMPLETE status is the right shape and
duplicates nothing; not buildable yet, for two blockers.

- B1 BLOCKER - the "no deadlock" claim is wrong. The arrival gate gates only
  the arrival's own supply; an earlier waiting supply is re-gated only by a
  knock-on, which fires only when a table is PROMOTED. A red/held/contested
  sibling never promoted leaves its neighbours staged. And in
  non-participation quarters (May/Nov) a period schema is born only at its
  first promotion and inheritance runs only then, so if the last arrival is a
  reader of cp_case_workers nothing ever promotes. Fix: re-gate waiting
  supplies of other datasets in the same period in the same promotion step
  whenever a run records a cross-table result counting toward them (amends
  REQ-PIPE-121's "a file landing in staging stays outside this mechanism" -
  Keith's call, A1). Delete the draft's "no deadlock" decision.
- B2 BLOCKER - a staged INCOMPLETE supply is classified AWAITING_DECISION
  (slot_state), which is in NEEDS_ACTION: a ticket, a queue row and "needs a
  person" for every early Child Protection arrival. Fix: a new slot state
  "waiting on <table>", read from a structured withheld record, not in
  NEEDS_ACTION, responses "see <table>" only. Amends REQ-PIPE-083 c21,
  REQ-PIPE-064 c5, REQ-PIPE-132 c10, REQ-GHUB-082 c16, REQ-DASH-056 and
  REQ-DASH-197. (A4.)
- H1 - Q4 option A (a staged dependency counts as checked) contradicts case 9
  and REQ-PIPE-215 c6, and does not meet Keith's literal "if clients is red and
  not promoted, notifications shouts"; only option B does (A2).
- H2 - a refused inheritance (no earlier promoted supply when the period
  opens) is never retried, and the draft's delayed promotions make that more
  likely; readers then stay INCOMPLETE. Inherited and substituted
  dependencies DO count as readable. Recommended: retry a refused inheritance
  when an earlier promotion makes it possible - rubs against REQ-PIPE-098
  c2's "once" (A3).
- H3 - RECORD INCOMPLETE at the two writers (unrunnable, held_blast_radius),
  never derive it from "not evaluated" (that would also catch Soda's left-out
  checks and Evidently's reference_not_evaluated); the vocabulary must land
  before the gate reads it.
- H4 - one predicate for "unreadable tables of a record", used in four places.
- H5 - three test-first claims would not fail first (case 11, case 13,
  REQ-PIPE-215 c2); rewrite them around moves that leave the period holding
  nothing.
- H6 - target_agreement.after_replay must read the gate's own reading.
- M1 - gate, knock-on, promoted_status, mandatory reason and ticket wording
  each need INCOMPLETE handled explicitly (structural, not substring).
- M2 - REQ-GEN-199 quoted texts move (TS-75, TS-76, TS-77); REQ-GEN-196 does
  not; the characterization pin must be re-run.
- M3 - one structured withheld record per supply, not one per reason.
- M4 - REQ-GEN-203's signed dependency on REQ-PIPE-211 may be unnecessary
  (TS-42 and TS-80 end with a promoted file) - B1.
- M5 - REQ-PIPE-210's "not counted" becomes essential.
- M6 - superseded decisions to record (REQ-PIPE-115's "not a new status",
  REQ-DASH-204's "never removes the red", held_blast_radius's "not a fourth
  status").
- L1 - renumber both status orderings identically; pill, legend, labels.

Amendments needed beyond the draft's six: REQ-PIPE-083 c21, REQ-PIPE-064 c5,
REQ-PIPE-132 c10, REQ-GHUB-082 c16, REQ-DASH-056, REQ-DASH-197, REQ-PIPE-130,
REQ-PIPE-074, REQ-GEN-186, REQ-GEN-199 c9, REQ-PIPE-121's staging decision,
REQ-PIPE-098 c2 (if A3 option A), the M6 decisions; REQ-PIPE-079 c4's wording
under Q4 option A.

Touches six of seven components: build as one sprint in a fixed order.

Keith's questions from this review: A1 (re-gate on a staged arrival), A2 (=
the scoper's Q4, with its consequence stated), A3 (retry refused
inheritance), A4 (a "waiting on <table>" slot state), B1 (REQ-GEN-203's
dependency on REQ-PIPE-211).
