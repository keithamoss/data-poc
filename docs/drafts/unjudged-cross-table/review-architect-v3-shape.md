# delivery-architect on the #95 v3 shape (2026-10-21, before the scoper's draft)

Verdict: the shape holds, and inherit-on-filing removes the owe-nothing deadlock. Five blockers would make it fail as built.

## Blockers

**B1. The S3/Lambda path has no packages.**
- `s3_arrival.record_object` (`s3_arrival.py:83-110`) makes every object its own delivery, received at that object's own LastModified (`:71-80`), so a shared instant never forms.
- A pass triggered by object 1 can't know object 2 is coming.
- Either scope packages to the delivery tree's zip "for now", with S3 a known limitation until `plans/supply-thoughts.md` defines a boundary, or define an S3 boundary now. That is Q-D.

**B2. The gate runs per arrival, from four places.**
- `arrival_lifecycle.process` (57-82) / `orchestrate` (402-417) gate each file straight after its own run.
- The processing pass treats checked-but-ungated as a failure (`processing_pass.py:594-614`, `fail_arrival` 368-375). A Lambda budget stop or arrival lock (490-504) between siblings means sibling 1 is later gated ALONE from its records (564-584).
- The knock-on re-gates waiting staged supplies (`knock_on.py:132-137, 224-247`).
- `recheck._run_claimed` gates a single supply (`recheck.py:363-366`).
- Fix:
  - ONE package-gate function, run when the last member completes its check.
  - A derived state, "checked, waiting for its package": not a failure, but it holds back later arrivals the way UNGATED does.
  - The knock-on and re-check skip a pending package.
  - The package gate is an owed item, so a timeout or crash resumes it.

**B3. "If a sibling is held" needs an algorithm.** S3: Clients v2 is red on a column; Notifications v2 is red only because it references clients that Clients v2 dropped. Holding every red member at once holds Notifications v2 too, though it would be green against Clients v1; releasing members can oscillate around the Notifications <-> Investigations cycle. Proposed:
1. held₀ = members red on checks that read no non-held member.
2. Re-run the non-held members' cross-table checks that read a held member, with those read from the warehouse.
3. Add any member now red to held, and repeat.
4. Members red only against each other's v2s are held together; go back to step 2.
5. Stop when held stops growing.

The held set only grows, so it ends in at most n rounds. Refusals are final when written, and promotions are written at the end.

**B4. A held staged partner from an EARLIER arrival is still read** (`period_overlay.py:44-86,106-107`; staged wins in `period_schema.py:438-462`).
- S4a (false green): Clients v2 arrives alone and is held. Notifications v3 then reads Clients v2, is green, and promotes. The warehouse becomes Notifications v3 + Clients v1, which is broken; the knock-on shows red-promoted only afterwards.
- S4b (false red, stuck): Notifications v3 is red against the held v2 but would be green against v1, and nothing ever re-checks it.
- Ignoring held staged partners deadlocks two cases:
  - S6, staggered first-time: Notifications v1 is held on Monday, and Clients v1 on Wednesday must read it to release both.
  - Settlement of a contested pair.
- Q-A: (A) accept it, since red-promoted catches it; or (B) every gate is a GROUP gate (the arrival plus the waiting staged supplies connected to it, through B3). (B) fixes S4a, S4b, S5 and S6, but re-gates a waiting supply on an arrival.

**B5. Status and page take the newest result whatever it read.**
- Where: `supply_status.runs_about`/`latest_results` (40-77), `red_promoted.py:84`, `build_dashboard_data.share_cross_table_results` (316-339), and template 2897 `clipDatasetToInPlaceOn`.
- What the requirements must say:
  - FILTER FIRST, then take the newest, falling back to the newest qualifying record.
  - Say what a check with no qualifying record reads as (strict: could-not-run, so red).
  - "In place" = promoted, substituted or inherited (`knock_on._now_holds` 85-94).
- Amend REQ-DASH-264 c1 and REQ-QAC-037 c7 to "against the supplies in the view on show". Re-check TS-80's c6 expectations.
- Word Keith's 265 rule for ANY cross-table record, not just carried ones.

## Tensions and gaps

- **T1. The re-check is a third view**: "what the warehouse would hold if this promoted". Define it as the view the GATE decides on.
- **T2. Inherit-on-filing.**
  - 098 c2 "once" survives, and its consequence is permanent. S7: a held 2021-Q4 Carers leaves 2022-Q1 inheriting 2021-Q3 Carers for good.
  - S9 deadlock: a period with nothing earlier to inherit (INHERIT_REFUSED) is red until a person acts. Q-B: retry only refused inheritances.
  - A period before a partner's participation starts gets could-not-run red with no way out.
  - REQ-PIPE-079 c14 ("not red ... not supplied yet") is reversed by strict and needs explicit amendment.
  - Fine as is: the knock-on fires on inheritance; opening sits outside other transactions. Add a census test on an inherited-only period.
- **T3. Tickets.**
  - A package-held member is AWAITING_DECISION (`slot_state.py:77-80`), so it gets a ticket, with the generic "status is red" reason (`promotion.py:465-468`).
  - Per-promotion knock-ons give up to k identical "still-failing" shouts (`knock_on.py:245-296`).
  - Fix: a structured cause on the refusal, one owed re-evaluation per package gate, and no re-shouting. Q-C: ticket of its own?
- **T4. What counts as held:** contested, held without a slot, load-refused, slot filled with no replacement, amber under hold, superseded, AND frozen by the backstop (`promotion.py:890-895`). S1's "Clients v2 promotes" depends on REQ-PIPE-123's replacement setting.
- **T5. Order.** The warehouse re-check is caused by the held sibling's refusal record, so newest-cause ordering holds. One effective_at for the whole package gate (today it is seeded per arrival, `orchestrate.py:413-416`).
- **T6. A package ends at its gate.** After that, re-file, supersession, rejection, settlement, corrections and hand promotions act per supply.
  - S5: settling a contested pair works only because the overlay reads held staged partners.
  - Partition a package by period.
- **T7. Bootstrap.**
  - Audit the scenario map (`scripted_decisions.py:666-707` refuses a changed target).
  - GEN-186 `after_replay` reads the arrival run (`target_agreement.py:132-137`). Decide whether a target is about the file (recommended) or the gate's view.
- **T8. Cost.** At most k × rounds scoped readers-only runs, batched per round, usually 1-2 rounds. Test the count on a 4-member chain.

## Mechanism for "re-check against the warehouse partner"

- A readers-only run with `from_warehouse=<held tables>` via `recheck.execute(purpose=...)` (`knock_on.py:193-200`, `recheck.py:185-247`).
- Persist it on qa.run (`qa_results_writer.py:343-358`).
- `period_overlay.rebuild_for_arrival`/`build` drop those tables from `staged` (106-107), so the read falls to the promoted table, or to absent, which is red.
- `_supplies_held` (151-168) records which supplies were read.
- `__rN` runs carry nothing (`carried.py:68-69`).

## Lesser points

- A cycle test.
- The hand-filed path gets the package gate only if the deferral lives in the gate entry.
- Checkpoints between siblings are fine once "waiting for its package" exists.
- The awaiting-line clause is computed in Python, not re-derived in JS.

## For delivery-critic

1. One package-gate function.
2. One record-selection function with an explicit view argument.
3. B3 in one place, with tests for S1, S3, the cycle and a first-time zip.
4. `from_warehouse` recorded on the run.
5. Failing-first tests naming `processing_pass.py:613`, `knock_on.py:236`, `template:2897`, `supply_status.py:58`.
6. Named held classes, no shortcuts.

## Build order

1. B5 selection, plus the 037 c7 / 264 c1 amendments. This fixes the live issue on its own.
2. Inherit-on-filing, plus the retry (Q-B), plus 079 c14.
3. `from_warehouse`.
4. The package gate, plus a bootstrap and the scenario-map audit.
5. Display.

## Questions for Keith

- Q-A: S4, a held earlier partner. (A) Accept. (B) Group gate.
- Q-B: S9, a period with nothing to inherit. (A) Retry refused inheritances. (B) Keep "once".
- Q-C: a package-held supply's ticket. (A) None; the sibling's ticket names it. (B) Its own.
- Q-D: S3 uploads. (A) Zip-only for now. (B) Define an S3 boundary now.
