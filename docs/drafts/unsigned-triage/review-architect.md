# delivery-architect review of both batches (2026-10-14)

Advisory; recorded by the main session. Covers docs/drafts/unsigned-triage/
(batch A) and docs/drafts/road-testing-feedback/ (batch B).

## closePanel() defect - CONFIRMED in a browser by the main session
template :7285 `closePanel(){ if(STATE && STATE.panel) history.back(); ... }` -
no "did the app push this entry" guard. A cold-loaded `?panel=` sets
STATE.panel (panelFromUrl 4447, stateFromLocation 4467), so X / backdrop /
Escape (8528) call back() over an entry the app never pushed. Main session
reproduced: cold-load template?panel=requirements, Escape -> about:blank. In a
truly fresh tab back() does nothing and the panel cannot be closed. All five
SIDE_PANELS (4446). Guarded patterns exist: closeCheckPanel (7183, panelPushed),
closeDrawer (6717). Written up as post-build-review #180.

## Batch A
- 164 HIGH: recheck._run_claimed always calls promotion.after_runs
  (recheck.py:337); c8 needs it skipped for a promoted supply. MED: c15 should
  name decision.promoted_status (qa_store.py:947,962); c2 should reuse
  filing_decisions._readers_rechecked (314). LOW: recheck.RECHECK (40) already
  names an owed kind - new action needs its own constant; c19 already met, mark
  as linked existing test.
- 165 HIGH: c5 fails whenever a state has no example; the bootstrap can't be
  relied on for every state -> build one example per state in the test's own
  database (MOTHMAN_TEST_DSN). MED: rolled-back transaction traps -
  filing_decisions.py:477 opens a second connection that can't see uncommitted
  seed rows. Needs a connection-taking supersede_offers(conn, state) beside
  excuse_offers (filing_queue.py:299). Needs REQ-PIPE-163 built.
- 166 MED: generalise excuse.history (excuse.py:72-102)/pipeline/excuses.py
  rather than two more copies; name the withdrawn entry via caused_by_decision
  (qa_store.py:952) not by position; reader list misses pipeline/slot_timeline.py,
  build_*_dashboard_data.py, acknowledgement.py (acknowledged_by takes the
  EARLIEST ack, LIMIT 1, 38-43 - stale after withdraw+re-ack) and DECISION_DONE
  (template 8295). LOW: a test tying DECISION_DONE to decision_log.ACTIONS.
- 175: sound, buildable with 163.
- 221 HIGH (ordering): depends on 177, which hard-depends on 176 (held behind
  #89) - so 221 is effectively held; say so in its source.
- 176: no structural issues; leave held.
- 223: buildable now. MED: c4's one reader = validate_check_lifecycle.
  _old_file_content (86) extended to ref=None. LOW: don't merge with
  sources_fingerprint() (64-83, REQ-PIPE-192's digest). Evidently thresholds
  move from shared constants (evidently_common.py:18-19) - comment why.
- 177: c24 confirmed unmet (processing_pass.py:520); c17 needs an ids= filter on
  run_all_owed (recheck.py:391). Fits as `mothman supply recheck`.
- 178: held via 176.

## Batch B
- 219 MED: validator belongs under `mothman dashboard` (cli/plans.py:3-8 draws
  that line). MED: "date first raised" needs a home - the entry tag's date, not
  changed when status changes; restored entries carry their original date. MED:
  build the card parser in dashboard/plans_md.py on _parse_numbered_items.
  Fold RQ1-RQ3 (c17, c27 not-reproduced, c28, c33 all eleven).
- 220 MED (security, public site): the `?`/`#/` href check must sit in the
  shared parser so the build refuses a bad target, not only CI. LOW: reuse
  renderPlansMarkdown escaping (7890); share sprint_state.survey's "Built"
  predicate (242-261).
- 222 LOW: rows need data-req-id, found by iteration not a selector built from
  req=; navUrl (4431-4434) carries panel=/req= across navigate() - drop both.

## Questions
1. closePanel defect: A fix now test-first for all five panels / B leave to 222 c9.
2. Validator: A `mothman dashboard validate-feedback` / B `mothman plans ...`.
3. 165 parity examples: A built in the test's own DB / B the bootstrap.

## Build order
closePanel fix; 223 and 222; 219 then 220; 163 with 175, then 179; 164 then
166; 165; held behind #89: 176, 177, 178, 221.

## Keith's answers (2026-10-14 afternoon)
1. closePanel defect: **A** - fix now, test-first, all five panels (#180).
2. Validator: **A** - `mothman dashboard validate-feedback`.
3. 165 parity examples: **A** - one seeded example per state in the test's own database.
