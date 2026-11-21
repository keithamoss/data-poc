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
