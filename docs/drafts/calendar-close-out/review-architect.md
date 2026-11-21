Architect review round 3 (2026-10-14): 2 blockers, 8 high, 10 medium, 4 low.
A1 BLOCKER growth: amber_setting/replacement_setting asset versions start 2023-01-01 with NO DEFAULT (data-asset.yaml:138-145,191-198; replacement_setting.py:38-43) -> grown 2021-22 supplies raise. Amend: add setting versions on/before first grown claim-opening; register note on checks' introduced_date 2023-01-15.
A2 BLOCKER "no existing scenario moves" false: N_QUARTERS/RUN_PLAN reshuffle (generate_cp_runs.py:170-194), seed/slot from oldest (:706), keep_clean index0 (:663), TS-79b oldest. Option A keep existing quarters byte-identical (draw added quarters separately; TS-79b stays) / B accept redraw + recapture golden & CP quotes + re-place refused. Keith Q1.
A3 HIGH quarter budget under-counted (~17 quarters, not 8); -15 claimed via TS-77a stands_on (collision rule ignores stood-on period). Amend: size by dry run of collision refusal over all planned scenarios; stood-on period claimed.
A4 HIGH commit order: freeze gate exempts newly ADDED versions on synthetic (agreement_freeze.py:731-736) and refuses declared change with no change (:690-699) -> growth in its own change, corrections later. cp-carers participation is shared alias *cp_participation (calendar.yaml:273,349) - split before effective_to.
A5 HIGH deps: drop 179 from 205 deps; add growth owner to 179 and 203; re-point 170 c23 unmet entry at sign-off (205 c17 clears TS-57..62; 179 c40 clears TS-63).
A6 MED correction claim counted once per correction, checked against injections, post-generation placements (TS-52, TS-79) and TS-63's correction.
A7 MED config-dated scenarios don't move with ANCHOR_DATE: refuse when outside history.
B8 HIGH 205 c4: confirm-correction read only by correction_replay.confirm_due; out of Player & filing-decision validation; change_reference, no dataset; resolve keeps via _supply_of.
B9 HIGH 205 c8: use recheck.run_all_owed inside bootstrap's pass lock (not run_pass); stop bootstrap if not complete, as scripted decision does.
B10 MED probable DEFECT built: _confirm_corrections opens fresh replay_clock -> confirm stamped with real now, not end of replay (replay_clock.py:101-105,56-62; correction_replay.py:85) - test first, own post-build-review entry. Amend: anchor at later of both collections' last replayed instants.
B11 MED approver must be Keith's real identity (agreement_freeze.approvers excludes synthetic); Q4.
B12 LOW 205 c15 TS-60 hold stands at end.
B13 LOW bootstrap.resume never confirms corrections - accept or carry.
C14 MED 206 TS-52: from configuration and deliveries alone, not a supply any correction touches.
C15 MED 206 TS-50 needs CP targeting (same fork Q5).
C16 LOW 206 c11 TS-47 following day claimed, refused not shifted.
D17 MED 204 c10: one unrunnable_code per record (first table name order); per-table reasons not recorded; held in held_blast_radius. Amend: record unrunnable_codes_by_table + carry held_tables; identify blocker from fields only; old records by single code. (touches PIPE recorder)
D18 MED 204 "results in place" undefined for red reader -> "the run the dataset's status is computed from on the date on show".
D19 MED after reject-both readers stay red forever (knock-on only when holdings change, decision_log.py:945-948) - PIPE question Q3.
E20 HIGH 203 c3/c10 "built green" hits CP targeting refusal (generate_cp_runs.py:616-623) - Q5.
E21 MED 179 c39: gap deliveries carry cp_carers.csv held as turned off, counted in quiet line; amend generator NFR "no supply the dataset owes". Q2 TS-63 correction date.
E22 LOW bootstrap budget ~9-10 min; one growth owner measures before/after.
F23 HIGH 163 c2 contradicts decision_log.py:389-402 (person REFILE with no from_slot refused; only rule); refiling.plan refuses held (:79-86) and contest (:98-105); duplication: correction_apply._place and schedule_ended.refile_holds - one shared placer. Amend wording given. decide --wait on pair placement refused (c27); readers in target period owed re-eval?
F24 LOW 163 decision 'refiling.plan has no such refusal NOT REPRODUCED' now built (refiling.py:91-96, #172) - update; 179 c19 drain re-files held pair whole.
Build order: growth; 202; 203; 204; 182; 163; 179; 180; 205; 206.
QUESTIONS: Q1 growth owner & bytes (A own GEN req, sized by dry run, existing quarters byte-identical / B 205 owns, redraw+recapture / C A but redraw); Q2 TS-63 correction date (A before gap: arrival-time hold shown, awaiting confirmation for years / B late); Q3 reject-both readers re-checked (A yes PIPE follow-up / B no); Q4 fictional corrections approver (A Keith's email, reason says fictional / B synthetic exception); Q5 CP built green (A build CP lead-ins+targeting in 203 / B built clean).
