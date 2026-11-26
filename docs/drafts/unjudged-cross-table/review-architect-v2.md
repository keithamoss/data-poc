# delivery-architect on #95 v2 (2026-10-20, advisory)

Verdict: self-promotion removes v1's B1 deadlock and B2. Two new blockers remain.

## Blockers

**X1. There are four status rankings, not two; two of them drop Incomplete.**
- `promotion.py:196,205` (`_status_at_promotion` keeps green, amber and red only): an Incomplete promotion records `promoted_status = NULL`. That breaks 214 c2 and `_manifest` (130 c11).
- `rechecking.py:117,182` (`_RANK` green/amber/red; `worse_than_promoted` skips anything else): an Incomplete-promoted supply re-checked red never appears in "Promoted, then re-checked red" (164 c15), and is not counted as needing a person (c22). A false quiet.
- `target_agreement.py:25` has its own `_RANK`.
- Fix: 212 c5 names all of these, or requires ONE shared Python ranking. Add a 214 test: re-check an Incomplete-promoted supply red through the real executor, and assert it is listed. Decision to record: green to Incomplete on re-check is also listed as "worse".

**X2. 214 c8 must compare the EVALUATED status.** `target_agreement` reads `promotion.status_of(for_gate=True)` (`target_agreement.py:45-49`). Once `status_of` returns `incomplete`, every staggered targeted CP supply disagrees with its target (case 16: 312 pairs), and REQ-GEN-186 c3 fails the bootstrap. Fix: after-replay compares 214 c1's evaluated status. Sketch: ONE function returns both the displayed and the evaluated status, read by the gate, after_replay, `_status_at_promotion` and rechecking.

## Answers

1. **Deadlock.** None remains, including quarters a dataset sits out.
   - Inheritance goes through `apply_decision` (`inheritance.py:290,311-327`), which changes the slot, so `knock_on.owe` fires (`decision_log.py:1044-1046, 973-976`; `knock_on.py:93,156`).
   - 121's "staging stays outside the mechanism" rule can stay: every staging route has its own run scoped to its readers. The routes are arrival, re-file (`refiling.py:188`), un-supersede (`supersession.py:368`) and settlement.
2. **Case 9 / 215 OQ1.** The premise is wrong.
   - Re-runs use the arrival overlay (`recheck.py:239`). It reads a single loaded staged sibling (`period_overlay.py:44-86,106-107`), and staged wins over promoted (`period_schema.py:438-462`).
   - So the re-run reaches a verdict. c16 fires only when no single loadable staged version exists.
   - Delete OQ1. 213 c13's case 5 test must build a staged dependency the overlay cannot offer (e.g. one with no load record).
3. **Failing-first tests.**
   - Case 10 fails first: rejecting doesn't change the slot, so nothing is owed.
   - Case 11 fails first only with an injected `knock_on.owe` for an empty period table, then `complete`; it fails at `knock_on.py:156`, None == None. 215 c9 should name the injection.
   - Case 13 CANNOT be built: `supersession.py:171-179` refuses to let a load-refused file supersede. Replace it with a person-supersede with nothing newer (`supersession.py:296-324`), or a re-file out of a staged supply.
4. **074, 130 and GEN-186 need no amendment.**
   - 074: promote with `promoted_status='incomplete'`; `qa_store.py:985-986` allows it.
   - 130: add a decision that `_manifest` now shows a new value. Widening `promotion.py:196/205` is X1 build work.
   - GEN-186: covered by X2's wording.
5. **Retrying a refused inheritance.** Not needed. Log it as a follow-up (it conflicts with 098 c2's "once").
6. **Staged-superseded trigger.** Not needed for supersession by a later file, but needed when worded by effect: "WHEN a decision takes a staged supply out of what the period offers, and a reader's latest result read it". That covers reject, person-supersede, re-file out and settlement. Fold it into the 121 c1 text.
7. **105 c5 and re-files.** No amendment: the overlay reads siblings via `filing.CURRENT` (`period_overlay.py:68-78`). Case 12's test asserts the end state after every sibling's re-check. If that is still Incomplete, it is a real defect and needs its own requirement.
8. **Build order.**
   - The order is fine, but 213's writer change and 214's gate MUST land in one push, with the bootstrap after both. Otherwise `promotion.py:465-468` holds every early reader and B2 returns.
   - X1's fixes go with 212 and 214.
   - v1's B2 amendments are confirmed unneeded.

**Q11:** recommends A. The gate decides on the checks that ran, which is never less safe than B and is safer under hold.

## Lesser findings

- 213 c4's unreadable-tables predicate must stay separate from the wider `carried.not_evaluated_reason` / `NOT_EVALUATED_KEYS` (`carried.py:44-57`) and `build_dashboard_data._not_evaluated_reason`.
- 214 c1 edge case: if every record is a not-evaluated cross-table one, the evaluated status is None, and `should_promote` says "no ACTIVE checks". One line saying the reason is the missing table fixes it.

## For delivery-critic

1. One Python ranking.
2. One displayed/evaluated status function.
3. One structured unreadable-tables predicate.
4. The new trigger detected as a before/after staged-set change in `apply_decision`, not added per route.
5. Each rewritten test's docstring names the line it fails on.
6. No "not green or amber" fallbacks.

Security: no concern. No open questions from this review for Keith.
