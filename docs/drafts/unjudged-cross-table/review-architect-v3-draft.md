# delivery-architect on requirements-draft-v3 (2026-10-21)

Verdict: the shape review is mostly resolved. Two blockers are confirmed in code (N1, N2), plus one contradiction (N3).

## Status of earlier findings

- **Resolved:**
  - B1 (266 c6, pending Q9), B3 (267 c3-6), B5 (269 c1-6 plus the amendments).
  - T1, T4, T5, T6, T7 (pending Q7), T8.
  - The `from_warehouse` mechanism.
- **Partly resolved:**
  - B2: the fourth gate, the re-check executor (`recheck.py:363-366`; re-file, un-supersede, settlement), is not covered. That is T14, and N1's fix covers it.
  - B4: resolved for a single arrival only; it should be the same rule as 268 (N1).
  - T2: 271 c5-6 pending Q4, with T18 still open.
  - T3: 266 c10 plus Q6. This matters more under N2.

## Claims checked

- **268 is correct for two tables.** `runs_about` orders by the supply's receipt instant (`supply_status.py:51-60`), and Clients' run evaluates every check reading `cp_clients` (`base_scope_of_run` 327-339).
- **267's n-1 rounds and order-independence hold, if:**
  - each step is evaluated over the whole set at once (write that into c6); and
  - every cross-table check reads exactly two tables. All ten `reads_tables` in the CP Soda file name one other table today.

  Holding a failing pair together is a deliberate choice; record it as a decision. A check reading three or more tables would make the result stricter than needed; record that as an accepted limit.
- **271 is mechanically fine.**
  - `open_period` runs outside other transactions, and `inherit_into` walks every dataset, so an ED filing opens a CP quarter.
  - The census is fine, and nothing reads `qa.period` as "something was promoted".
  - REQ-PIPE-262 c12's pins (`requirements.yaml:39249-39252`), TS-63 and REQ-GEN-251 c3 are at risk from strict red as well. They may need a generator fix, not a re-pin.
- **N3 (contradiction).**
  - 266 NFR 2 and 267 NFR 3 write refusals only after the gate settles, but 267 c9 makes the re-check's cause the refusal, and `qa.run` requires a cause (`qa_store.py:216-217`). The owed package gate has no cause either (`qa_store.py:1330`).
  - Fix: write each refusal the moment it is final (safe, because the held set only grows); keep 267 c10's hide-until-settled rule; give the owed package-gate item the last sibling's load as its cause, or a new owed kind.
- **T13 (a person deciding mid-cascade).** Refuse a decision on a supply whose package-gate item is uncleared. `promote()` re-confirms under the slot locks that the read holders are unchanged (as `inheritance._still_stands_on` does, 462-475), and restarts the gate if they changed.

## New scenarios

- **N1 BLOCKER: three or more separate arrivals deadlock under 268 as drafted.** 268 judges each waiting supply alone.
  - S10 (2024-Q4, empty):
    - Notifications v2 arrives at 08:40 and is red.
    - Clients v2 arrives at 09:00. Its Client reference passes, but Notifications v2's Escalation completeness still reads no Investigations, so Notifications v2 isn't added, and Clients v2 is refused against no Notifications.
    - Investigations v2 arrives at 09:20, and Notifications v2 needs both partners counted as promoting.
    - All three wait forever.
  - S11: Notifications and Investigations, waiting on each other, are never added.
  - Fix: a gate application = the arrival plus every waiting supply in the period connected to it through recorded cross-table verdicts, TRANSITIVELY; run 267's fixed point over all of them, never running a check for a waiting supply; at every gate entry.
  - That folds 268 and 267 c14 into one rule, solves T14 and settlement, and makes REQ-DOCS-274 c2 true.
- **N2 BLOCKER-level: under strict red, a referenced table is hostage to every reader.** 269 c4 counts a not-evaluated record toward every supply its run read. Clients declares no cross-table checks, but Notifications, Investigations (twice) and Placements read it.
  - S14 (a first-time zip of all six tables): Placements v2 is red on its own data.
    - Clients v2's Placements-check records are re-run against no Placements: red.
    - Notifications and Investigations are then red against no Clients.
    - Case Workers and Carers go red the same way.
    - One Placements file holds the WHOLE quarter.
  - S14b: the zip without Placements: Clients is red for want of a reader.
  - New **Q13**: what does a could-not-run check count toward?
    - A, as drafted: every supply its run read.
    - **B (recommended):** if the DECLARING table (Placements) is absent, it counts toward nothing; if the REFERENCED table (Clients) is absent, it counts toward the declaring table only. Clients promotes on its own data, and a later Placements with dangling clients is held back without turning Clients red.
    - B reverses v2's Q8 answer, which was given for Incomplete. It is not "not supplied = empty": the absence is still red for the table asking the question.
- **S15:** with N1 fixed, the early arrival in S10 is red for days, until its last partner arrives. That is T8, for #113.
- **S16:** a person promotes Notifications v2 during the Clients re-check against v1, so Clients promotes on a verdict about v1. Closed by the refusal and lock re-confirmation above.
- **S17:** Q2 inheriting Q1 at filing blocks a green Q1 resupply more often (`promotion.py:983-995`). That is today's behaviour, widening; record it in 271.

## Recommendations

- **Q1: CHANGE to "A, transitively"** (see N1). Q2 then needs no separate answer; it becomes A.
- **Q13: B.**
- Q4 A, with a warning about the pins.
- Q6 A, which is now necessary rather than tidier.
- Agrees with the rest.
- Build order: N1's rule lands in the same push as 266, 267, 268, 270 and 273 behind one bootstrap; N3's schema change goes with 266.
