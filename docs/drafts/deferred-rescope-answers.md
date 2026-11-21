# Keith's answers on the four deferred criteria, 2026-11-21

Against `deferred-rescope-v1.yaml` and `deferred-rescope-amendments-v1.yaml`
(delivery-scoper, the same day). Answers only; nothing is applied to
requirements.yaml until each requirement is presented and signed.

## Set A

- **Q1.1, REQ-PIPE-065:** (a) the wording goes in the existing queue item (when the
  promoted supply was accepted; the near-the-next-window hint); retire c7 and c8,
  keep c5 and c6, delete `qa_tools/common/landed_on_accepted.py` and its test.
- **Q1.2, an automatic replacement's history entry:** (a) yes, wording only - the
  same accepted-at and proximity words (`new_criterion_if_Q1b_yes`).
- **Q2.1, REQ-GHUB-082 c1:** (a) `mothman pipeline process` polls ticket comments
  (REQ-GHUB-433 as drafted).
- **Q3.1, REQ-PIPE-352:** (a) retire c5 (to REQ-PIPE-250) and c6
  (`replaced_by: [REQ-PIPE-403]`).

## Set B - project extractions (REQ-PIPE-379 c5)

- **Q4.1, does an extraction's QA count?** (a) Yes - `never` verdicts are real
  history and roll up within the extraction's own dashboard; REQ-PIPE-106's
  not-counted rules apply to `not-yet-agreed` only (one small amending requirement).
- **Q4.2, the outcome:** (b) a recorded release-or-withhold decision for the whole
  extraction, with actor and reason.
- **Q4.3, a second package in one extraction's database:** (a) refused; a re-send
  is a new extraction (sprint 29 point 9).
- **Q4.4, scope now:** (b) scope sprint 29's five alongside the lifecycle four -
  recipe format, hierarchy from the recipe, the two check layers, the ephemeral
  database and TUI path, publishing - so the end-to-end test runs a real recipe
  package. (Not the recommendation, which was the lifecycle only.)

## Set C - extractions, non-functional

- **Q4.5, privacy:** (b) the same as recurring datasets - up to 5 failing-row
  identifier keys per check. (Not the recommendation, counts only.)
- **Q4.6, retention:** (a) a person drops the ephemeral database from the TUI,
  typed confirmation; never automatic.
- **Q4.7, mixing:** (a) a `never` dataset lives only on an extraction deployment
  of its own; a recurring asset's configuration refuses one.

## An addition, mid-draft

- Keith: "maybe it doesn't have a database." Confirmed: explore an extraction with
  **no ephemeral database at all** as a real option beside sprint 29's
  ephemeral-database-plus-TUI requirement. Not decided; the scoper drafts both
  shapes and one settling question.

## Round 2, on deferred-rescope-v2.yaml

1. **Database:** (a) shape A, an ephemeral PostgreSQL database per extraction
   (REQ-PIPE-442); REQ-PIPE-445 (no database) is rejected and comes out of the draft.
2. **Where an extraction's configuration lives:** (b) a generated `assets/<extraction>/`
   folder committed for each extraction. (Not the recommendation, a shared template;
   the scoper flagged it as 30-40 a year and closer to state than configuration.)
3. **Publishing and the decision:** (b) publish at any time as a QA report, showing
   the decision once there is one. (Not the recommendation, decision first.)
4. **What a release does:** (a) recorded only; the system never moves data.
5. **Dropping an extraction never published:** (b) allowed with the typed
   confirmation, which warns that no record will remain. (Not the recommendation.)
6. **Recipe v1:** (b) the core fields plus optional expected row counts per table,
   checked when present. (Not the recommendation.)
7. **A declared table missing or an undeclared file present:** (a) failing
   default-layer checks; QA carries on.
8. **The root `file-checks.yaml`:** (a) applies to extractions.

## Round 3, on deferred-rescope-v3.yaml

1. **Commit the generated folder before loading:** (a) yes - loading is refused
   until it is committed. AND (Keith's own addition): the one-offs live apart from
   the enduring assets - **`extractions/<id>/` at the repository root**, beside
   `assets/`, holding the extraction template and one folder per extraction.
   Selected by MOTHMAN_ASSET and given its own database as any asset is, but never
   listed by the enduring-asset loops in CI or the session-start hook.
