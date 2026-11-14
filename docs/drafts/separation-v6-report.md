# #134 v6 - the scoper's report, 2026-11-14 (first pass)

v6 is written to /home/user/data-poc/docs/drafts/separation-v6.yaml. It is a new file. I edited nothing else and committed nothing. (The decisions file already showed as modified before I started.)

**Validation.** I ran `uv run mothman dashboard validate-requirements --draft` on the final file. Every error it reports is a cross-reference to a requirement outside the draft, which is expected. There are no other errors.

**Code checked.** I checked against the tree at 72ec04d7. No product code has changed since v5's a35066ff, so the a35066ff line numbers still hold. Two v5 lines were wrong: knock_on's streams call is at line 478, not 475, and scenario_injection's calendar-name test is at 1418, not 1419.

**New ids.**
- REQ-TEST-393 deletes the equivalence harness.
- REQ-DASH-394 covers Dash B (the new queue kind).

Nothing else in `requirements.yaml` or `docs/drafts` uses 393 or 394, but whoever applies this should check again.

**The horizons.** I did not split them into their own parked requirement, because any criterion written now would assert a shape Keith has said he is not happy with. Instead:
- REQ-PIPE-378 criterion 20 says to leave every horizon as it is.
- A 378 decision keeps the full list of 17 sites and the reviewers' points, so the later thinking starts from them.

## What changed from v5, per requirement

- **REQ-PIPE-380.**
  - B4 closure: 21 whole modules (7,310 lines) plus named parts of 15 others, about 9,000 lines in all. `next_receipt` is dropped. Added: `arrivals_for`, the corrections readers, `check_lifecycle` moved whole, the `file_checks` definitions, and `AMBER_SETTINGS` moved into `amber_setting`.
  - QB charter written in. Criterion 8 now says no subprocess and no git.
  - 380 Q1(a) is now a criterion. Note that `check_lifecycle` turned out to be entirely the parsing half.
  - New criteria: old-path searches find nothing (monkeypatch strings and `implemented_by` included); a path-only register rewrite; B6 (both SCANNED lists, coverage sources, `INPUTS` plus a `KEY_PREFIX` bump, the workflow paths).
  - Compare removed. Build order and the architect's code-quality expectations recorded as decisions.
- **REQ-GEN-381.**
  - B3: the register parser is out of `bootstrap/`; it gets the player halves.
  - `holds_history` and `HISTORY_REFUSAL` move to the pipeline beside `streams`.
  - The refusal follows the CLI review's wording. Cache key: `cli/pipeline.py` dropped, `KEY_PREFIX` bumped. B6 lists. Compare removed.
- **REQ-PIPE-382.** Rewritten around QA's neutral clock events and B1's single clock:
  - One clock: `asset_time` is extended, no third time module.
  - Events at every site that sets the simulated time today: an arrival being processed (as a context), a delivery being staged, a decision taking effect.
  - Corrections are staged through the arrival event's context.
  - Where the time is pinned and a replay starts, the replay reads the pinned instant until its first event.
  - `MOTHMAN_PINNED_NOW` stays, because `test_cli_cp` uses it.
  - The moved-instant evidence criteria are removed.
- **REQ-PIPE-383.** Corrections go through the event, not a hook (this answers B2). Added: on a synthetic asset, `pipeline run` prints a line saying it played no scripted decisions (CLI finding 11). Recorded that `pipeline run` on a synthetic asset stamps the wall clock. Compare removed.
- **REQ-TEST-384.**
  - Runs as `mothman dashboard validate-imports` and is repository-wide in `mothman check`, with `--only imports` and a summary row.
  - Ruff-style output lines. Stale and added allowlist entries get worded messages, the added one naming the base commit.
  - A file in no side fails: `aws/` goes to the real pipeline, `docs/` is exempt.
  - One syntax-tree walker; REQ-PIPE-376 c8 and REQ-PIPE-390 c4 become rules of this gate.
  - One test fails if any created package is missing from the paths filter, either SCANNED list, the coverage sources or `INPUTS` (B6).
- **REQ-PIPE-385.**
  - B5: `--no-pytest`, and the CLI C not-applicable rows.
  - The synthetic commands are listed by name. Detection uses `find_spec` and matches how the test blocks imports.
  - CLI A: `pipeline run` never generates, has no target comparison or correction confirmation, and its help is cleaned.
  - Main menu and flag hint. Refusal sentence with exit 1 at every subgroup level. CLI B: the wizard's Synthetic source and both run-id flags.
  - CLI D: `scenarios bands` deleted, with its tests and REQ-GEN-183's claims.
  - Dashboard surfaces listed; the empty-state branch is removed; Dash C footer; Dash D not-found page.
  - Tests now cover `--help` and bare `mothman`; the browser test uses the reviewer's exclusion wording.
- **REQ-GEN-386.** B3: register parser, placements reader, map vocabulary and the `scripted_decisions.yaml` reader go to `scenarios/`; the generator keeps the map writer; the dashboard keeps only `read_map_data`. `correction_replay`'s two calls go to `asset_model`. The delivery writer finding is below. B6 lists. Compare removed.
- **REQ-PIPE-376.** The underscore test becomes a gate rule; the closure's private names are added. Compare removed.
- **REQ-PIPE-377.** Compare removed. Criterion 5's stop is kept, because it is about a product-behaviour disagreement between copies, not the synthetic history.
- **REQ-PIPE-378.**
  - Horizons out (criteria 12-14 and open questions 3 and 4).
  - 378 Q1: calendar versions only. 378 Q2(a): leave the dataset out of the minimum.
  - Dash A: the build refuses. The CLI refusal paragraph, and a pass report saying the step will stop the same way every time.
  - `validate_schedule._report` form. The drivable `schedule show --on 2012-06-01` check.
  - Compare and "stop if a result moves" removed.
- **REQ-PIPE-379.** Shares the fixture asset with 385; the cost estimate is now realistic. Compare NFR removed.
- **REQ-QAC-387.** Gates named. The lifecycle gate reads the base from the two old per-asset files. Root `file-checks.yaml` added to `INPUTS` and the workflow paths. Compare replaced by a test of today's six checks. The lifecycle gate is not a `mothman check` row today, so the criterion names its command.
- **REQ-TEST-388.** Runs as `mothman dashboard validate-dbt-packages`, repository-wide, with a `dbt packages` label. The message ends with the next step.
- **REQ-QAC-389.** `introduced_date` is 2013-01-01 (settled). Adds a `CHANGELOG.yaml` release-note criterion; the gate and the fix are named. Criterion 12's compare and stop removed.
- **REQ-PIPE-390.** `status_words` joins. The ranking test becomes a gate rule. Compare removed.
- **REQ-GEN-391.** The stop-on-difference and compare criteria are removed; a decision says the derived verdict stands.
- **REQ-GEN-392.**
  - Q1, Q2 and Q3(i)/(ii) are criteria. QC: population keeps literal rates.
  - Moved-record evidence and accounting removed; the re-capture stays.
  - The release note is added. The architect's lasting-cost point is an NFR.
  - Criterion 12's scenario stop is kept: it protects designed demonstrations and REQ-GEN-186's own check, not the history.
- **REQ-TEST-393 (new).** Deletes the commands, `equivalence.py`, the three harness-only tests, `--run-full-capture`, `test_no_job_takes_full_captures` and `fetch-depth: 0`.
  - The four tests from your message stay: they compare two runs of today's code, each under a signed criterion. Their helper code moves into `tests/equiv_support.py`.
  - Removes the register claims naming deleted files; that includes REQ-PIPE-248's `--renamed-by`.
- **REQ-DASH-394 (new).** Dash B: the stop is recorded in the qa schema, gets a needs-action blocking kind worded as our fault, and clears on a clean pass. The builder first confirms what such a supply shows today, which the review flagged as unverified.

## Review findings not carried, and why

- **Dashboard 4, chain list.** The dashboard review asked for supply-history chain regrouping to be listed in evidence. QD and Keith's earlier "I don't care about reviewing the list of moved verdicts" remove all moved-record evidence.
- **Dashboard 4, verdict counts.** The release note drops the per-direction counts, because they would have come from that evidence.
- **Dashboard 4, stale scenario links.** Old `?scenario=` links carrying an as-of date were to be mentioned in the release note. Dash D and the open question below cover that behaviour instead.
- **CLI 8 (horizon latency and naming).** Parked with the horizons; kept in a 378 decision for that thinking.
- **CLI 10.** The terminal counts fall under QD. `qa_wizard.cast` is a dated recording that no test compares, so it is not re-captured.
- **Architect, 382 c9-10 evidence.** Moot: both criteria are gone under QD.
- **Architect, refuse the clock install on a production environment.** Not carried: the published demo is a synthetic asset, and `environments.yaml` keys behaviour off properties, not the word "production".
- **Architect, path-only rewrite.** Only partly carried. v6 rewrites `implemented_by` and `linked_tests`, which the gate checks against real files. Evidence and decisions prose is left as the record of its day.
- **Architect, the "harness" in B1's fix.** Moot: the harness is deleted.

## Open questions (each with a recommendation)

1. **380 OQ1, the one delivery writer** (found in the code). `hand_filing.py` line 275, in the real pipeline, and `generator/driver.py` line 234 both call `write_delivery`, so v5's move of it to the generator would break hand filing.
   - Recommend (a): `write_delivery` and `write_receipts` go into `asset_model/` under QB's "delivery tree" charter, and the generator-only removers go to the generator.
   - This widens `asset_model` from reading the tree to writing it.
2. **382 OQ1, `effective_at_for` under one clock.** A synthetic promotion now takes effect seconds after receipt. The 2026-10-02 lag, which Keith chose so the receipt-to-promotion interval shows a spread, then never applies on any asset, and neither do its two caps.
   - Recommend (a): keep the code as written, rewrite its docstring, and add a decision to REQ-PIPE-081.
   - Removing the lag can follow later as its own tidy-up.
3. **385 OQ1, Dash D's other two links.**
   - Recommend `?panel=scenarios` lands on the same not-found page.
   - Recommend `?scenario=` is dropped silently and the real page underneath renders as normal.
4. **393 OQ1, REQ-PIPE-248 criterion 8 wording.** Recommend retiring it with REQ-TEST-239's already-approved reason.
5. **394 OQ1.** Recommend one item per distinct configuration error, listing every dataset it stopped, rather than one item per dataset.
6. **394 OQ2.** Most errors the build meets now refuse the build (Dash A), so this new queue item will mostly show only for errors the build never reads. Recommend accepting that rather than also refusing the build while an item is open, which would mean the item is never seen.

**Smaller choices left as my proposals in decisions:** the footer replacement wording, `aws/` and `docs/` sides, both matrix legs, and REQ-TEST-393 as its own requirement (it could fold into REQ-TEST-384).

**Not yet done:** the matching `plans/*.md` draft entry. This pass covered only the YAML; I can draft it if you want.
