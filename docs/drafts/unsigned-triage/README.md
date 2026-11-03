# Triage of the seven older unsigned requirements (2026-10-14)

Keith's ask (running-thoughts #92 step 3, 2026-10-14): triage in parallel
with the road-testing feedback-tab scoping. Read-only pass by a background
agent, recorded here by the main session. Nothing signed or edited.

**Headline: none is overtaken.** Nothing built since covers person-raised
re-checks, fingerprints, withdrawals or the dashboard wording. REQ-PIPE-163
(placement, signed today, NOT built) is a prerequisite for four of them.

| Req | Asks for | Verdict | Size | Scoper pass? |
|---|---|---|---|---|
| PIPE-164 | A person re-checks one supply in place | Stands (c19 met by REQ-PIPE-140's claim) | 21 c, large | yes |
| GHUB-165 | Terminal offers every decision the flags allow | Partly overtaken: c1 gap, c3 moot (choose-file only for pairs), c4 now REQ-PIPE-163 c10/c17, c5-c6 parity test unmet | 6 c, small | yes |
| PIPE-166 | Withdraw a not-supplied mark or an acknowledgement | Stands, nothing built | 8 c, small, could | yes |
| DASH-175 | Page says "placed" / "re-checked" | Stands; placement half needs 163, re-check half 164/177; amendment 2 (c12) approved with 163, applied when 175 is signed | 17 c, medium | **no** |
| QAC-176 | Fingerprint of each check's definition on every result | Stands; **c18 (refuse old DB, reset+bootstrap) collides with parked #89 migrations**; digest length never asked | 23 c, large | **no** |
| PIPE-177 | Bulk re-check of one fixed check | Stands (c16 claim, c24 deadline met) | 26 c, large | **no** |
| PIPE-178 | Trial a bulk re-check, record nothing | Stands | 17 c, med-large | **no** |

Evidence (from the agent, file:line): no re-check operation in
qa_tools/common/filing_decisions.py:77 OPERATIONS; cli/common.py:620-627
refuses a recorded re-run unless a decision owes it; un-supersede offered only
on a REJECTED slot (filing_queue.py:352-355); tests/test_filing_queue.py:82
checks only that each operation is offered somewhere; check_result has no
fingerprint column (qa_store.py:238-263); check_lifecycle._config_hash is a
16-char json.dumps hash (check_lifecycle.py:210-216); REQ-PIPE-076 c7 not yet
amended per 164 c20.

**Recommended order:** 175's placement half with 163; GHUB-165 re-scoped (c1 +
parity test + updated operation list); PIPE-166; PIPE-164; QAC-176 after #89
settles c18 and the digest question; PIPE-177; PIPE-178; rest of 175. 175,
176, 177 and 178 go through delivery-scoper before sign-off.

## Keith's answers (2026-10-14)

- Scope them all now, in parallel with the feedback-tab scoping (delivery-scoper
  pass started the same afternoon: 165 re-scoped; 175, 176, 177, 178 first
  scoper pass; 164 and 166 checked for currency).
- REQ-QAC-176: sign-off HELD behind the parked schema-migrations question
  (running-thoughts #89) - its criterion 18 is the wipe-and-rebuild dead end.
