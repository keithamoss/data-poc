# Geocoding v6 - architect delta review of the new parts (2026-10-31)

## BLOCKING (both in REQ-GEN-298 criterion 11)
1. Criterion 11 breaks signed REQ-PIPE-331 criterion 3 (requirements.yaml:45679): another collection's table is "never a staged one", and is "ABSENT where … filed to no period". The code matches that criterion:
   - period_overlay.py:122-124 and 303-306 clear a staged foreign table;
   - stage.py:99-105 leaves it absent until filing;
   - filed_tables (:70) joins on qa.filing.
   Fix: a signed amendment to REQ-PIPE-331 criterion 3, plus an explicit period_overlay.build branch for trial-supplied foreign tables. A6 covers only REQ-PIPE-079 criterion 9.
2. Criterion 11 stages "the last source supply filed" whatever its verdict. In replay, the source is read only if it was promoted before the geocoding is checked. So for a red source, an amber held by its setting, or TS-93a/100a/101, the trial judges against rows the warehouse never holds, and trial and replay disagree. Fix: stage a source only where the generator's plan promotes it before the delivery (REQ-GEN-334 c12's scheduling already knows this), otherwise stage nothing and expect could-not-run.

## SHOULD
- Keep the new rule inside the trial. Do not change own_results: it serves only the post-replay comparison (target_agreement.py:201, REQ-GEN-273 c1), and changing it would turn c8's could-not-run quarters into failures.
- try_targets assumes one table (one_table.py:65, 87, 171, 217). targets.written gives ambers only, with no day, filename or period (targets.py:84-93). Criterion 12 needs filenames on every Built.
- Trial isolation: promoted_in(period) (period_overlay.py:154) reads the real database. The trial's foreign reads must use its own copy only.
- Cost: generation runs before any replay (bootstrap.py:275), so about 10 minutes of trials lands on the critical path, against a 12-minute budget per asset. Run trials in parallel; trial schemas and per-worker dbt already keep them apart.
- notchecked:
  - it must join _QUIET_PRECEDENCE (dataset_status.py:188) at a stated position;
  - adding it to CHECK_STATUSES (:91) is a decision;
  - status-cases.json needs its cases;
  - say how 'Not checked' differs from 'Not counted';
  - Pass/Warn/Fail must list it and give its verb form.
  Build Pass/Warn/Fail first.
- list_settings:
  - it needs a path into a nested container (_settings :197-208, _resolve_on :99);
  - timeline hard-codes "amber_setting" (:115), a bug that already affects replacement_setting;
  - standing_problems (:192) and resolve (:167) demand an asset-level value;
  - Resolved.value is typed str (:61).
- contract/synthetic_inputs.yaml is not on the ASSET_WIDE allowlist (validate_collections.py:183-223). Under the asset split it belongs in contract/<asset>/.
- calendar_differs: asset-split A13 retires it, but REQ-DASH-299's A1 and A2 still word it. Whichever lands second reconciles.

## NIT
- The register lacks "AMENDED ... by REQ-GEN-298" on REQ-PIPE-079 c9 (A6).

## For Keith
- Q1: in the trial, stage (a) only the sources the plan promotes before the delivery, so the trial matches replay (recommended), or (b) every filed source, as drafted?
- Sign-off of the wording of a new REQ-PIPE-331 criterion 3 amendment.
