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

## Addendum (command clean-up and sync-tickets guard)

ADDENDUM to my v6 report. Keith's COMMAND CLEAN-UP and sync-tickets GUARD are now in v6 as two new requirements.

File: /home/user/data-poc/docs/drafts/separation-v6.yaml. Nothing else was edited and nothing is committed. I re-ran `uv run mothman dashboard validate-requirements --draft` after the change. The only errors left are links to requirements outside the draft, which are expected.

**REQ-TEST-395: delete four commands**
- **`mothman debug build-warehouses`** (cli/debug.py, line 165). The help describes a DuckDB warehouse that no longer exists, and the command duplicates `mothman supply load`. `stage.build_all` and its own test stay.
- **`mothman debug changelog`** (line 176). The help is stale and its own example returns []. `build_changelog` stays, because the dashboard embed calls it directly.
- **`mothman debug capture-arrival-golden`** (line 186). It rewrites the shared golden file from one asset's collections, which drops the other asset's arrivals. `tests/test_asset_time_semantics.py` (lines 20 and 168) must then describe a per-asset re-capture instead. REQ-GEN-392 criterion 11 depends on that. There is no regression test, because the command is deleted rather than fixed.
- **`mothman dashboard snapshot`** (cli/dashboard.py, line 239). Only the command goes. `prepare_deploy_site` and `take_snapshot` stay, because publish and pipeline run call them.
- **Tests and docs:** each command's own tests go (test_cli_debug, test_cli_app line 198, test_cli_dashboard line 146). README.md lines 46-48 lose them, along with the retired acceptance sync still listed there. CLAUDE.md and docs/ drop any mention of them as commands to run.
- **Register claims:** every `linked_tests` and `implemented_by` entry naming a deleted command or test is removed in the same change. Each is listed for Keith, because they are claims on built requirements. Among them are REQ-GEN-043's and the snapshot command's under REQ-DASH-013, REQ-DASH-292 and REQ-PIPE-089.
- **Kept as they are:** snapshot-worktrees, cache-key, rebuild-results, build-data, embed, check-renders, population, sync-tickets and sync-leaderboard are named in the requirement so nobody removes them by mistake.
- A deleted name gets the normal "No such command" answer, with no alias left behind.

**REQ-GHUB-396: the sync-tickets guard**
- `mothman github sync-tickets` refuses with exit 1, naming the environment, unless that environment's `ticketing` is on. This is the same rule `ticket_reconciler.py` line 334 applies.
- The refusal happens before any report is read or any GitHub call is made.
- The guard sits in `ticket_sync` itself, not only the command. That way the disabled ticket-sync workflow would also meet it if it were ever re-enabled.
- It is treated as a defect fix: a regression test seen failing against today's code first, plus a test that it still runs when ticketing is on.
- The overlap with the reconciler and the empty leaderboard are recorded as still for Keith to raise.

**Build order and ids**
- Both requirements go in build step 1, alongside REQ-TEST-393 and before the imports gate.
- The header comment now lists all four new ids: REQ-TEST-393, REQ-DASH-394, REQ-TEST-395 and REQ-GHUB-396. None of them appears in requirements.yaml or plans/, but whoever applies the draft should check again.

Neither requirement has open questions. One choice of mine to flag: I made the deletions a requirement of their own. They could be folded into REQ-TEST-393 if Keith would rather have one fewer id.

Everything in my earlier v6 report still stands, including its six open questions.

## Second addendum (Keith's six v6 answers applied)

I applied Keith's answers to all six of v6's open questions, in place, in /home/user/data-poc/docs/drafts/separation-v6.yaml. Nothing else was edited and nothing is committed. After the edits I re-ran `uv run mothman dashboard validate-requirements --draft` and read the changed fields back. The only errors are the expected references to requirements outside the draft.

Five of the six are closed as SETTLED decisions. Q2 is settled too, but Keith's wording leaves one fork on where the lag lives, which I've raised as a new question.

## What changed

**Q1. The writer stays in the pipeline; the generator gets its own (REQ-PIPE-380, REQ-GEN-386)**
- REQ-PIPE-380 criterion 2: `write_delivery`, `write_receipts` and `next_sequence` stay in the real pipeline, because `hand_filing.py` (line 275) calls them.
- REQ-PIPE-380, new criterion 18: asset_model/ reads the delivery tree and writes it nowhere.
- The read half still moves under QB, because `arrivals_for` reads the tree through it and the generator checks its placements with `arrivals_for`. A new decision records that Keith rejected writing in asset_model/, not reading. Open question 1 is closed.
- REQ-GEN-386 criterion 7: the generator gets its own delivery writer in generator/, and the generator-only removers and bookkeeping move beside it. The generator imports nothing of the pipeline's writer.
- REQ-GEN-386, new criterion 8, keeps the two writers in agreement. It is a critical test that needs no database:
  - It writes one delivery (several files, one receipt per file, both zip-shaped and folder) through both writers into two empty trees.
  - It fails on any byte difference, or if asset_model's reader reads either tree back differently.
- Decisions record how agreement is kept and why the test is critical. They also record a rejected alternative: a schema document both writers are reviewed against, rejected because nothing would fail when the writers drifted.

**Q2. The spread comes back (REQ-PIPE-382)**

Two new criteria (3 and 4) carry the design.
- **The rule.** The seeded lag stays one rule in asset_model/: `promotion.effective_at_for`, moved there by REQ-PIPE-380.
  - A supply received at R takes effect at R plus a lag seeded off its run id.
  - The lag is spread across the claim window W where one is given, and one hour to three days otherwise.
  - It is never at or past the next receipt B; just before it, never before R.
- **What the clock decides.** The one cap that differs between a replay and a real run is "the latest instant a decision may take effect", and the rule asks the clock for it.
  - The wall clock and a pinned clock answer now, which gives today's min(now, R + lag).
  - An installed replay clock answers the real wall-clock present.
  - So a replayed promotion keeps its spread and can never land in the real future. That matters once the anchor rolls (#138, R2).
- **What the pipeline passes.** It passes facts it already has:
  - R and the run id.
  - B from `next_receipt`.
  - W from `_claim_window`, which under 378 Q2(a) leaves out a dataset dated before its calendar's first version and gives no W if none remain.

  It then announces the result as the "decision takes effect" event. An installed replay clock moves forward on it, never backwards; the wall clock ignores it. The pipeline imports nothing of the replay.
- Criterion 2 now says every reader of "now" reads the one clock, with this single exception.
- Criterion 13's tests now cover four cases:
  - a replayed promotion spreading while the replay clock sits at its simulated instant;
  - a real-run promotion matching today exactly, including a retried package gate (#274 D1);
  - no replayed decision taking effect after the real present;
  - the unchanged cases.
- Decisions added: the spread comes back (rejected: keeping the dead code with a note, and removing the lag); how the event carries the lag and its caps; the claim-window cap following 378 Q2(a); never after the real present.
- The old open question is replaced by the new one below. Cross-references shifted by the two new criteria and were re-pointed in REQ-PIPE-383, REQ-PIPE-378, REQ-TEST-393 and REQ-PIPE-382's own text.

**Q3. Both old scenario links show not-found (REQ-PIPE-385)**
- Criterion 13: `?panel=scenarios` and `?scenario=<id>` both land on the plain not-found page, even when the rest of the address is a real page.
- The parameter is removed with replaceState so a reload doesn't repeat it.
- The browser test (criterion 15) is updated to match.
- Settled decision added; rejected: dropping `?scenario=` silently, and dropping both. Open question closed.

**Q4. REQ-PIPE-248 criterion 8 retired (REQ-TEST-393)**
- Criterion 1 now says criterion 8 moves to REQ-PIPE-248's retired_criteria, with REQ-TEST-239's approved reason.
- The decision is now settled; rejected: amending it. Open question closed.

**Q5 and Q6. One item per error; the build-refusal split accepted (REQ-DASH-394)**
- Criterion 5: one queue item per distinct configuration error, listing and blocking every dataset it stopped. Each dataset's page still shows it is blocked.
- Settled decisions added for both answers:
  - Q5 rejected one item per dataset.
  - Q6: errors the build reads stop the build (Dash A) and are named by the CLI and logs; the queue item covers only what the build doesn't read. Rejected: refusing the build while an item is open, and revisiting Dash A.
- Both open questions closed.

The header now notes the in-place update. One open question remains in the whole draft, the one below.

## New open question

**REQ-PIPE-382 OQ1: where does the seeded lag live?** Keith said the replay clock "applies the seeded lag", and that can be read two ways.
- **(a) As drafted.** The lag stays one rule in asset_model/, used on every asset as today. The replay clock only lifts the "not after now" cap to the real present, then moves forward on the decision event.
- **(b) The lag moves into the replay clock (bootstrap/)** and the wall clock answers simply now. The lag code would leave shipped code, but:
  - a retried package gate on a real asset would take effect at the retry instead of when its first attempt would have, reversing post-build-review #274 D1;
  - REQ-PIPE-081's "a rule, not a replay flag" decision would be reversed too.

**I recommend (a).** It brings the spread back with no change to what a real asset records and no second copy of the lag; the replay decides only how late a replayed decision may land.

## Third addendum (the lag in the replay clock)

I applied Keith's REQ-PIPE-382 OQ1 answer, (b), in place in /home/user/data-poc/docs/drafts/separation-v6.yaml. Nothing else was edited and nothing is committed. After the edits I re-ran `uv run mothman dashboard validate-requirements --draft` and read the changed fields back. The only errors it reports are links to requirements outside the draft, which are expected.

## What changed in REQ-PIPE-382 (now 14 criteria)

- **Criterion 3 (rewritten).** The pipeline asks the clock one neutral question in asset_model/: "a decision on a supply received at R, run id S, next receipt B, claim window W - when does it take effect?"
  - The wall clock and a pinned clock answer **now** on every asset.
  - An installed replay clock answers R plus Keith's 2026-10-02 seeded lag, under these bounds:
    - spread across W where one is given, and one hour to three days where none is;
    - just before B and never before R;
    - never after the real wall-clock present.
  - The lag rule leaves shipped code.
- **Criterion 4 (rewritten).** The pipeline asks with facts it already has: R, the run id, B from `next_receipt`, and W from `_claim_window`. Under 378 Q2(a), `_claim_window` leaves out a dataset dated before its calendar's first version and gives no W when none remain.
  - The answer is announced as the "decision takes effect" event, and the replay clock moves forward on it.
  - The pipeline imports nothing of the replay, and no lag, seed arithmetic or cap remains in the pipeline or asset_model/.
- **Criterion 2.** Its exception is reworded to refer to this question.
- **Criterion 13's tests** now cover:
  - wall and pinned clocks promoting at now;
  - a real asset's retried gate taking effect at the retry;
  - a replayed promotion spreading while the replay clock sits at its own instant;
  - no replayed decision after the real present;
  - a replayed retried gate still taking effect when its first attempt did.
- **Criterion 14 (new).** In the same change as the build, two built requirements' decisions get an appended amendment, signed by signing this requirement. The `implemented_by` entries naming `promotion.py::effective_at_for` (REQ-PIPE-081, REQ-GEN-185) are repointed.
- **New dependencies:** REQ-PIPE-267, REQ-GEN-185, REQ-GEN-386.

### The exact wording for Keith
This is in the decision "THE TWO REVERSALS, WORDED FOR KEITH". Both are appended, so the original text stays as the record of its day.

- **REQ-PIPE-081, decision "FIXED AS A RULE, NOT A REPLAY FLAG", append:**
  > REVERSED by Keith, 2026-11-14 (REQ-PIPE-382): the seeded lag now lives with the replay - scenarios/' lag rule, applied by the bootstrap's replay clock when the pipeline asks the clock when a decision takes effect - and on a real asset a promotion takes effect at the instant it is made. The pipeline still carries no replaying flag; the clock it asks is what differs.
- **REQ-PIPE-267, decision "A RETRIED OR RESUMED PACKAGE GATE TAKES EFFECT WHEN ITS FIRST ATTEMPT DID (post-build-review #274 D1)", append:**
  > REVERSED FOR A REAL ASSET by Keith, 2026-11-14 (REQ-PIPE-382): on a real asset a retried or resumed package gate takes effect at the retry, the instant it is actually made; in a replay it still takes effect when its first attempt did, the replay clock answering from the arrival that completed the package.

#274 D1 lives in REQ-PIPE-267's decisions, not in a criterion. Its replay half still holds, which matters because two bootstraps differing is where it was found.

### Decisions
- **Settled:** "THE LAG LIVES WITH THE REPLAY" records (b), chosen with both costs read to Keith, and that (a) was rejected.
- **Added:** REVERSAL 1 (REQ-PIPE-081) and REVERSAL 2 (#274 D1 on a real asset).
- **Adjusted:** the claim-window cap decision now says W is passed and ignored on a real asset.
- **Withdrawn:** the old "HOW THE EVENT CARRIES" decision, which described (a).
- OQ1 is closed.

## Knock-on edits
- **REQ-PIPE-380 (criterion 2 and decision B4).** Nothing of promotion moves now. The clock's question joins asset_time, the lag goes to scenarios/, and `next_receipt` stays in the pipeline.
- **REQ-GEN-386 criterion 4.** scenarios/ also holds the seeded lag rule: `effective_at_for`'s lag, `_LAG_MIN` and `_LAG_SPAN`.
- **REQ-GEN-381 criterion 1.** The bootstrap's replay clock answers the question with scenarios/' lag.

## New open question (REQ-PIPE-382 OQ1, replacing the closed one)
**Where the lag rule itself sits.** Keith put the lag in the replay clock (bootstrap/). But the Linkage Products provider computes the same rule to predict promotion instants (linkage_products.py lines 1742 and 1797), and the generator may not import bootstrap/.

- **(a) As drafted:** the rule goes in scenarios/, which is synthetic-only, left out of a real deployment, and importable by both sides. The bootstrap's replay clock applies it.
- **(b)** The rule goes in bootstrap/, with a second copy in the generator. The copies could drift and planned releases would miss.
- **(c)** The rule goes in bootstrap/, with a permanent allowlisted generator-to-bootstrap edge. This goes against Q1 of 2026-11-02.

I recommend **(a)**. It is Keith's answer in substance: the lag is out of shipped code and the replay clock applies it, with one copy, for the same reason drift arithmetic went into one module.
