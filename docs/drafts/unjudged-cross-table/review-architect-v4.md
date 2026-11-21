# delivery-architect on requirements-draft-v4 (2026-10-22)

(Returned as a report - the agent has no write tool - and saved here by the main session. Code read in /home/user/ed-wt.)

Verdict: the structure holds. N1's transitive gate, the N3 write-when-final rule, `from_warehouse` and the 268 fold are carried. Three blockers: B1 contradicts Keith's own Q13 = B; B2 is a counting rule at the wrong grain that quietly undoes Q13 = B; B3 is a promotion-on-stale-results path the transitive join opens.

## 1. v3 points

Carried correctly: N1 (267 c2-c3); B3 held set only grows (267 c6); N3 hold-backs written when final (266 c9); cause on re-check runs and `from_warehouse` on `qa.run` (267 c10); whole set at once and the two-table limit (c7, d6); holding a failing pair together (d5); 271's mechanics (S17, pins c9); S14, S15; the build order.

Carried with defects:
- N3 owed package gate (266 c3): "or a new owed kind" is a false choice - see S2.
- T13/S16 (266 c16): "restart the gate application" on a person's promotion; should refuse and re-show like `_still_stands_on` - see S3.
- v3 268 c3 lost "leave the waiting supply ... results and decisions unchanged" - the fold dropped "decisions unchanged"; see S4.
- Recheck-owed skip: `knock_on.readers` already skips a supply with an owed RECHECK (post-build-review #173 L3); 267's joining rule does not - see B3.

## 2. Withdrawing 268 into 267; gate at every entry

- Lost: only the "decisions unchanged" clause. v3 268 c4 is now 266 c10.
- Unbounded cascade: none. A hold-back moves no table, so owes no knock-on; each promotion owes one knock-on; each supply promotes at most once; within an application the held set is monotone.
- Re-entrancy: real, in the wording only. 267 c2 names `recheck.execute` as a gate entry, but `execute()` only runs tools (`recheck.py:185-247`); the gate entries are `recheck._run_claimed` (363) and `knock_on.complete` (236). 267 c5's own re-evaluations go through `execute()`, so a gate there nests. Name the entries as `_run_claimed`, `knock_on.complete`, the package gate and the UNGATED path (`processing_pass._one`, 564-584), and say a c5 re-evaluation is never a gate entry.
- Deadlock: none designed in; two builder traps in S1.

## Blocking

**B1. S2 strict and S10 contradict Q13 = B.** Q13 = B: where the declaring table is held back, its record counts toward nothing. Clients declares no cross-table check, so in S2 strict (first-time zip, Notifications v2 red) Clients v2's re-check of Notifications' Client reference against no Notifications is declared on the held-back table, counts toward nothing (269 c4), and Clients v2 promotes. Six places assert the opposite: 267 c15, 273 c4, 278's `s2_strict_raises_one_ticket_naming_both`, 210's S2 test, 204's tests and package-form rationale, and the summary's S2-strict row and walk-through. Keith's "Clients is held too" (2026-10-21) predates Q13 = B, which supersedes it; per his sign-off terms this moved decision goes to him explicitly.
S10 changes too: Notifications 08:40, Clients 09:00, Investigations 09:20 -> Clients v2 promotes alone at 09:00, Notifications and Investigations together at 09:20 via S11's join; "all three together at the last arrival" (267 c18, 273 c4) is wrong.
Fix: re-cast S2 strict as its mirror (Clients v2 red on its own data, Notifications v2 green, re-checked against no Clients -> could-not-run declared on Notifications -> held back; what 204's package form is for). Re-order S10 as Notifications 08:40, Investigations 09:00, Clients 09:20 so all three promote at Clients' arrival and the gate is genuinely transitive; keep the original order as a second test asserting Clients promotes at 09:00.

**B2. "Every supply that result's run read (`qa.tables_read`)" is run-level and must be per check** (267 c1, 269 c1-c2, 272 c17). `qa.tables_read` is one row per logical table per run (`qa_store.py:311-321`) and `period_overlay.build` resolves every agreed table (96-107), so a run "reads" all six. In S14 (six-table first-time zip, Placements v2 red) every cross-table verdict from every run stops counting once Placements v2 is held back, and the quarter is held back again - N2 returns through the counting rule. Fix: count by the supplies of the tables THAT CHECK reads (declared reads plus its own table, `carried._reads_of`), resolved through the run's `tables_read.supply` / `supply_files`. `carried._same_supplies` already does this per check; reuse it inside 269 c7's one selection function.

**B3. A joined waiting supply can be promoted on results not about its current filing.** T14 under 267 c2: a person re-files Clients v2 and Notifications v2 from 2024-Q3 to Q4 (two owed RECHECKs). Clients' re-check passes Client reference against staged Notifications v2; the application joins Notifications v2 and decides it from its recorded results - its Q3 run's, including period-dependent own checks - and promotes it into Q4 unchecked; its own re-check then takes `_promoted_outcome` (no gate, red-promoted at best). Same shape with a package mid-check: an application joins a member "checked, waiting for its package" (266 c3) and promotes it alone, breaching 266 c2/c7. Fix (267 c2-c3): define JOINABLE - a waiting supply is not joinable (and not marked held back) while it has an uncleared owed recheck or package-gate item, belongs to a package not yet gated, or its newest results come from a run whose period is not its current filing. Mirrors `knock_on.readers`' #173 L3 skip.

## Should-fix

- **S1. Concurrency and transactions.** Two RULE applications in one period can overlap (terminal runs owed items after a decision while the pass gates a package); nothing locks above the slot (`decision_log.py:790`). Add one advisory lock per (collection, period) held for the whole application, try-lock; on contention leave the entry owed, never block-wait (a nested call on a second connection self-deadlocks). No tools inside a decision transaction (uncommitted table-move DDL blocks dbt/Soda reads - the Soda lock hunt shape). All or nothing: "promote the rest together" must be one outer `decision_transaction` with savepoints; today `promote_each` lets Clients v2 commit then Notifications v2's move fail, half-and-half warehouse. A failure inside the component returns it to the fixed point with that supply not promoting. Gives 121 c9's one knock-on per application for free; `census.after_move` then runs after the outer commit.
- **S2. 266 c3 needs a new owed KIND.** `owed_run.kind` is constrained to `recheck`/`reevaluate` (`qa_store.py:1315`); a `recheck` caused by the last arrival would make `_run_claimed` re-run that supply's full QA. Make `package-gate` mandatory and add it to `run_all_owed` / the processing pass.
- **S3. 266 c16 and a person's override.** "Re-confirm ... else restart the gate application" fails every deliberate override of a supply whose verdict read a staged partner (e.g. promoting Notifications v2 in S1). A person's promotion is not a gate application. Compare-and-swap against the read holders shown in the consequences (276 c6-c7); on change refuse "something changed while this was being decided; try again", as `_still_stands_on`.
- **S4. Repeated `promotion-withheld` for joined supplies.** 266 c9 writes one per supply each application holds back; `_record_withheld` de-duplicates on (supply, reason text) and the text names instants, so log noise and 278 churn. Also, once `promotion-withheld` is latest, `_record_refused` (`promotion.py:1097-1100`) suppresses later refusals until the supply moves. Restore v3 268 c3 (unchanged not-promoting outcome -> no new decision); de-duplicate on the structured fields (267 c12).
- **S5. 269 c5 "a re-check owed by a promotion" too narrow.** Demotion, reject-after-promotion, un-inherit, de-substitute, re-file out also leave an in-warehouse reader without a qualifying result until the knock-on. Word it for any decision that moved a table (the `apply_decision` hook trigger); say what a counted check with no qualifying result reads as when nothing is owed (red, same reason). Judge "owed at T" from the cause decision's `effective_at` and the clearing run's cause instant, not wall clock.
- **S6. Fixtures can't produce assertions** (S3, S10, S11, T14 "nothing in the warehouse"): Notifications and Investigations both read `cp_case_workers` (`assigned_worker_id`, `lead_worker_id`; Soda file lines 423-427, 626-630); with no Case Workers both are strictly red. State full period content (Case Workers inherited or promoted).
- **S7. 266 c5 "SHALL exit 0"** masks the file's own reds (`one_table.py:460-486` exits 1 on any red). "The not-yet-gated state does not change the exit code."
- **S8. 278 vs Q10 = A.** After the root is rejected, 210 c6 / 275 c6 / 204 c16 say the held-back supply needs its own decision, but 278 c1-c2 still give it no ticket. In 278 c1, a supply whose root was rejected or superseded becomes its own root.
- **S9. 267 c11 "until the application has settled" needs a recorded marker** - a gate-application id on `qa.run` with a settled instant (or the cleared package-gate item); the build filters on it.

## Notes

- REQ-PIPE-265 carried verdicts: read correctly given B2's fix. `carried.records_for` rewrites `run_id` to the carrier and keeps `carried_from`; resolve reads through `carried_from` / `run_key`. Equivalent today only because 265 c5 guarantees same supplies for that check's tables - per check again.
- 270 must keep writing `unrunnable_reason` / `held_reason` when setting red; `carried.not_evaluated_reason` detects by key.
- Same instant for every application (266 c4 gives one per package; say it for knock-on and re-check entries too), and a decision-caused run outranks an arrival run at an equal instant - today a tie falls to `run_key` order, where `cp_notifications__X` sorts after `cp_clients__X__r1` (`supply_status.py:58`).
- 267 c3 re-evaluated every round of the fixed point.
- 269 c6 duplicates 278 c5; keep 278 as owner.
- 277's walk-all-visible-text test: scope to dataset and collection views (Release Notes and Plans render CHANGELOG/plans text saying "in place").
- No surface shows "checked, waiting for its package": a build between two siblings' runs shows Clients v2 green, then red once gated - a transient green. Add one line to 272 or 275.
- New requirements vs code: no duplication; 276's named functions exist; existing `promotion-withheld` doesn't empty a slot (`slot_state._amber_waiting` keys on `amber_setting='hold'`). Amendments changing agreed behaviour: 079 c14/d23 (strict), 121 c12/083 c21 (root cause), both flagged; B1 is the one that changes a Keith answer without saying so.

## Open questions A-E and readings

- A: no consequence; keeping ids needs only the 081 c23 amendment.
- B: agree, provided 269 c7's one function separates SHOWN from COUNTED; 272 c18 doesn't conflict (a held table isn't in the warehouse).
- C: agree; implement as "out of the run's scope", recorded in `left_out` with a reason, not a third outcome.
- D: none. E1/E2: agree.
- Readings: "S2 pinned as S2 strict" - pin the mirrored form (B1). Case 3a: under Q13 = B only the declaring table stays red. 267 OQ1: pin a replacement setting that permits green in every fixture, or S1 green reads as a deadlock under "hold".
