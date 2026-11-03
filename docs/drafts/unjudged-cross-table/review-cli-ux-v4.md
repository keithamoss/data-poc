# delivery-cli-ux on #95 v4 (2026-10-22)

(Returned as a report - the agent has no write tool - and saved here by the main session. Content as returned; see the session transcript for the verbatim text.)

Context: mostly error/failure states (hold-backs, refusals, owed re-checks, overrides) plus routine daily use (the queue). Keith's #113 (red drives notifications, so no flickering reds) is part of the bar.

## Blocking

**B1. The "S2 strict" scenario contradicts Q13 = B, and the terminal fixtures are built on it.** `cp-clients` declares no cross-table check (every `reads_tables` in `contract/child-protection-family-support/child-protection-soda-checks.yml` sits on notifications, investigations or placements). So in S2 strict (Notifications v2 held back) the only check involved is Notifications' Client reference, which could not run and is declared by the held-back table; by 269 c4 it counts toward nothing, as Placements does in S14, so Clients v2 promotes. The draft says the opposite in 267's S2 STRICT test, 204 c2's package form and its test, 210 c9's test, 278's `test_s2_strict_raises_one_ticket_naming_both`, 273 c3/c4's pinned gate outcome, and the summary-v4 scenario table and walk-through step 6. The working version swaps the roles: Clients v2 is red on its own data and held back; Notifications v2 is re-checked against no Clients, is red and is held back. In the terminal Notifications v2 then sits beneath Clients v2 and Clients v2's ticket names Notifications v2 - and it is the only case where 267 c12's second wording ("could not be checked - no <dataset> is in place in the warehouse") can occur. For the scoper and architect, not Keith: no decision moves, but the walk-through scenario has to be the right one.

**B2. Acting on 271's stale-carry-forward warning causes the flicker red Keith ruled out.** The warning says "un-inherit, then inherit". `INHERIT` on a period that already inherits returns "already inherits. Nothing to do." (`filing_decisions.py:728-730`), so re-pointing is two decisions with a knock-on each. Between them the later period holds no Case Workers (or Clients); every reader's cross-table check becomes could-not-run, red; promoted readers turn red-promoted, and waiting readers write still-failing records or tickets under 278, whose root-cause function has no "un-inherited, re-point pending" cause. A "red that clears by itself" that #113 must not notify on. Question 1 below.

## Should-fix

- **S1. Exit codes.** Real order in `processing_pass.exit_status`: failure 2, refused 3, red 1, OK 0 (EXIT_LOCKED 75 raised separately). 276 c2 / decision 2 state only "backstop 3 over red 1" - state the full order. `mothman cp qa` has no `exit_status`: it exits `1 if has_failures(results)` on its own run (`one_table.py:460-486`, `many_tables.py:712-757`). The re-check is a separate readers-only run, so 276 c2 must feed the gate's re-check results or outcome into `cp qa`'s exit decision; otherwise Clients v2 checked last, green against staged v2, red on the warehouse re-check, exits 0.
- **S2. 266 c5's "SHALL exit 0" for a not-yet-gated file is wrong** (from the reviewer's own v3 S6). A first file red on its own data must still exit 1. Reword: "exits as its own results say, and never non-zero only because it is waiting for its package".
- **S3. Mid-gate refusal (266 c15).** (a) Gating form: "is being gated (2 of 2 files checked); decide once it is gated." (b) After a crash or budget stop, retrying is a dead end; when no run holds the package add "It is finished by the next processing pass:\nmothman pipeline process". (c) On the flag route `apply_decision` returns None and `supply decide` exits 1 (`supply.py:1126-1127`), same as a permanent refusal; use EXIT_LOCKED 75 and document it. (d) A package checked-and-waiting or being gated should not be pickable from the queue: a quiet uncounted group like "Received while turned off" (`filing_tui.queue_flow`:936-941), "Checking a delivery received <instant> (1 of 2 files checked)", so the refusal is a backstop for the flag route only.
- **S4. `promotion-withheld` already exists with a different word** (amber hold stand-back `promotion._record_amber_waiting`, replacement stand-back `_record_withheld`; kept-run report says "withheld by the rule (...), not by you", `lifecycle_report.py:108-111`). 276 c1 must name `lifecycle_report.outcome_of` as a surface and decide whether every promotion-withheld says "held back" or only package ones. One action, one word. Add to 276 c14's tests.
- **S5. Don't let a person's rejection pass through `_gate_words`**, which rewrites `refused|rejected` as "held back" (`filing_tui.py:603-608`). Pin Q10's "turned down": post-rejection text must not contain "rejected"; test "turned down" in `outcome_panel` after a rejection.
- **S6. The owed re-check (269 c5) has no terminal wording.** Door words a red in-warehouse supply "in place - <reason>" (`filing_tui.py:709`); a person may read promoted Clients v2 red as "re-checked worse" and demote it. Add a 276 criterion: door and `_follow_up` use 204 c7's sentence plus `mothman pipeline process`; a `recheck-owed` supply is never shown or offered as "Promoted, then re-checked worse"; test it.
- **S7. The rule-made promotion after a warehouse re-check is silent in the terminal** (v3-shape point 2, S1 green, not carried). Add to kept report and outcome panel: "promoted by the rule - Client reference re-checked against the cp-notifications in place in the warehouse (received <instant>), green, because the cp-notifications received with it was held back".
- **S8. Grouping drifted from v3.** 276 c5 says "one line per supply it holds back"; reword to "one line per resulting outcome, naming its supplies up to eight (`_NAMED = 8`), then 'and <n> more'", root's own line first.
- **S9. Override consequences (276 c6-c8).** (a) Name both ends and the resulting state: "cp-notifications (in the warehouse, received 1 Jul) is re-checked against this supply. Client reference already failed for that pair (re-check <instant>), so cp-notifications will very likely become 'Promoted, then re-checked worse'." (b) Rejecting or superseding the root needs a line: "cp-clients (received <instant>) is not re-checked; it becomes a decision of its own in the queue". (c) Promoting over a not-yet-due could-not-run (S15, 270 c7): "Client reference could not run: cp-clients is not due until 09:00 today. Promoting now promotes on a check nobody could run; it is re-checked when cp-clients is promoted."
- **S10. Printed override command must be complete and copyable**: include `--supply <id>` and `--reason '<why>'` as `_recheck_panel` does (`filing_tui.py:578-583`); name the menu route too ("...or from the 2024-Q3 door").
- **S11. Terminal "held back together" wording.** Don't copy the card's "[Red] Held back together" - Rich parses `[Red]` as a style tag and it vanishes under NO_COLOR; the terminal uses ids. Proposed:

```
1 supply waiting on a decision in Child Protection (1 more held back with it, listed beneath)

cp-notifications  2024-Q3  received 21 Oct 09:00  red - 3 of its own checks fail
  held back with it (same delivery):
  - cp-clients  nothing to decide here - Client reference failed against the
    cp-notifications in place in the warehouse (received 1 Jul).
    Deciding cp-notifications settles it. To override: mothman supply decide
    --operation promote --dataset cp-clients --period 2024-Q3 --supply <id> --reason '<why>'
```

  "held back with it" mirrors 275 c3's "Holding back with it". The parenthesis extends 210 OQ1's recommendation. Wording only; Q8 = A stands.
- **S12.** "This supply's own checks passed" can contradict 267 c12's could-not-run wording; use "This supply's checks of its own data passed."
- **S13. 271's warning in the terminal**: the period-items group above the slot rows (`queue_flow`:903-916), not counted; in the door too; commands on their own lines; test the door as well. If Q1 = B, un-inherit's consequence panel must name the gap.

## Notes

- Correctly carried from v3: "held back" vocabulary and never under "Held - no period yet" (276 c1); next step conditioned on cause still waiting (276 c3); the locus clause (267 c12, 276 c4); `describe()` every reason (270 c5); T13/S5 in consequences (276 c7-c8); N1-N5 (276 c10-c12, 210 c2); NO_COLOR and pipe (276 c13); v3 S8 implicitly.
- Not carried, low priority: v3-shape S9 (dim supplier-guidance hint on separate deliveries); v3-shape point 7 (pin that the package reason wins over ANOTHER_VERSION_WAITING on the beneath line, `filing_queue.py:226`).
- Hide-until-settled vs live log: `promotion-withheld` written when final (266 c9) while re-check results stay hidden (267 c11); S3(d)'s quiet "being gated" group keeps the terminal from showing a half-settled package.
- Counts disagree page vs terminal unless 210 OQ2 = A; support A.
- 277 adds ~17 characters to queue state cells; check 80 columns and pipe; truncate by the existing shortening.
- 276 c11 crashed sibling: add "...the next pass re-runs it and gates both:\nmothman pipeline process".

## Questions for Keith

**Q1 (blocks B2).** Carrying a newer supply forward after a stale/refused inheritance warning.
- A (recommended): one "carry the newer one forward" step (door + flags) doing un-inherit + inherit as one decision with one re-check of the readers (same shape as 121 c9), so nothing turns red between. Widens REQ-PIPE-099 by one operation.
- B: keep two steps; un-inherit warns "N readers read red until you inherit the newer one", the follow-up offers the inherit, and the gap raises no ticket or still-failing record. A real red window a script or interrupted person can leave standing.

**Q2 (S3c, minor).** Exit code when a decision is refused because its delivery is still being checked.
- A (recommended): 75, temporary, as `pipeline process` uses for the lock.
- B: 1, like any refusal.
