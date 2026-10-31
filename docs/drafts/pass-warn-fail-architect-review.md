# Pass / Warn / Fail v1 - architect review (2026-10-31)

## BLOCKING
1. knock_on.py:378 `_fails_the_rules()` tests `"status is red" in why`, where `why` is the gate's refusal text built at promotion.py:533. REQ-TEST-360 c6 rewords promotion.py, so this test would silently return False. Fix: compare a structured field or constant, never reason text, with a test seen failing first (as for lifecycle_report).
2. REQ-TEST-360 c4 (refuse an unknown status) would crash the terminal. lifecycle_report.outcome_lines' status slot carries plain phrases as well as raw values:
   - 'no verdict' and 'verdict could not be read' (knock_on.py:363-365);
   - 'not yet re-checked' (filing_tui.py:686);
   - the already-worded 'red - could not run…' (settle_tui.py:755).
   Fix: make the tuple (dataset, status_value | None, words, result).

## SHOULD
- Raw values the inventory missed:
  - ticket_sync.py:292 and :309;
  - scenario_map.py:207-208 ('Built to');
  - target_agreement.py:71-75;
  - dataset_status.py:135.
- SCENARIOS.md's intro ('which red was on purpose') lives in scenario_map.py:169-173, so add it to REQ-DOCS-362 c3. Also resolve whether generator strings feeding SCENARIOS.md are reworded or frozen (REQ-TEST-360 c10).
- Check changelog `description:` entries say 'read red' and are rendered (template :10841):
  - bdm-birth-registrations-soda-checks.yml:200, 218, 540;
  - bdm-birth-registrations-contract.yaml:370, 566, 611.
  They are history, so the guard needs a marked exclusion for them and for rendered recorded reasons.
- The guard's scope (REQ-TEST-361 c1) must name the Scenarios tab, the needs-action queue (:7282, :7287) and the cross-table grid, and exclude Demo.
- ticket_sync._already_said compares worded bodies, so re-enabling the workflow would post one duplicate comment per open ticket. Note it.
- Test churn is about 27 files, not 12. Make c4, c6 and c9's before/after tables the scripted checklist, and record per-phrase zero counts as evidence.
- Cost: qa_tools/** is in replay_inputs.INPUTS, so the push misses the CI bootstrap cache and invalidates checkpoints. Say so in the cost NFR.

## NIT
- template :9054 would read '[Fail] 1 promoted, failing'.
- Chart tooltips (:4842) appear only on hover.
- REQ-GEN-183 ('no amber band', line 32849) may need an amendment.
- markerKindLabel's 'worse' fallback stays allowed.

## Interactions
- This batch goes before REQ-DASH-299, which is right.
- If the asset split is built first, its tests are written in the old words.

## For the builder
- One statusWords(value, form) on each side, with form = label / verb / count.
- The words live in status-cases.json, read by both parity tests.

## For Keith
- Q-A: 'false green' becomes 'false pass' on the dashboard, left alone in history (recommended).
- Q-B: old recorded reasons are shown with their original wording beside the new words, not translated (recommended).
