# Speed + rolling anchor v1 - the scoper's report, 2026-11-14

I drafted the speed and rolling-anchor batch as 12 small requirements in `/home/user/data-poc/docs/drafts/speed-anchor-v1.yaml`, all unsigned. `uv run mothman dashboard validate-requirements --draft` reports only the 25 expected cross-reference errors, and every one of those ids exists in requirements.yaml or separation-v6.yaml.

That is the only file I wrote. I did not touch requirements.yaml, plans/, code, tests or separation-v6.yaml, and committed nothing. The only other writes were two probe scripts in the scratchpad. Line references are at HEAD 5b502c46. Ids 397-408 were free in requirements.yaml, docs/drafts and plans.

## The biggest risk: a rolling anchor breaks the daily asset as it is configured
I ran the real generator's planning functions with `GENERATOR_ANCHOR_DATE` set (read-only, nothing written):
- **At 2026-09-25:** every dataset's owed periods equal its generated ones.
- **At 2026-11-14, Birth Registrations:** it owes 150 days but 100 are generated, so 50 days are owed with no supply. The daily calendar starts 2026-06-18 and the 100-day window slides. This is the front tail the guard in `tests/test_schedule.py:135` warns about.
- **At 2026-11-14, TS-78a:** it refuses to place (CannotPlace), because it falls outside its hold era in `assets/daily/data-asset.yaml`.
- **Child Protection:** each of its 6 datasets owes one quarter with no supply, because its fixed 47-quarter window slides.
- **The rest of the quarterly asset is fine:** all 52 scenarios placed at 2026-11-14 and at 2027-03-01, and Emergency Department, Linkage Products and geocoding grow without owing anything new.
- **The quarterly calendar runs out:** its authored dates stop at 2027-11-01.

The daily asset's whole scenario setup is written at fixed dates around 2026-09-25 (calendar versions, TS-62's version and correction, the setting versions). R1-R5 don't settle how those dates follow a rolled anchor, so it is question 1. REQ-GEN-406 is drafted provisionally on its recommended answer.

## Requirements
1. **REQ-PIPE-397** – a configuration pin in asset_model/. It is installed by the synthetic side, refused on an asset that is not synthetic, and works inside `config_yaml.read`, so no pipeline module checks for it (the architect's note: through REQ-PIPE-382's clock seam). Staged corrections sit on top of it. It also amends REQ-PIPE-254 criterion 15 to "outside a pinned run"; wording goes to Keith.
2. **REQ-GEN-398** – a generation (the driver, target trials, the scenario map, `arrivals_of`) runs pinned (S1).
3. **REQ-GEN-399** – the bootstrap's replay runs the real pipeline pinned (S2). Each stream process is handed the parent's pinned contents rather than re-reading, and a digest is printed beside the budget line. `pipeline run`, the CLI and the build read as now.
4. **REQ-PIPE-400** – slots, periods and agreement standings are worked out once per pinned configuration, keyed on the agreement actually in force so a staged correction is never answered from the unstaged calendar.
5. **REQ-PIPE-401** – #318's fix keyed dbt schema parses in `list_setting_members` on mtime and size (lines 183-184). That breaks REQ-PIPE-254 criteria 15 and 2, so this keys them on content. I treated it as a defect against a built requirement, not polish; Keith may disagree.
6. **REQ-TEST-402** – the suite generates each asset's history once and shares it (S3): built once across all xdist workers under a file lock, or restored from a cache keyed on the generator's inputs plus the fixed test anchor. Tests can only read it, a write fails the test, a test that must change it gets a copy, and the cache lives outside /tmp. The before/after `--durations` profiles are criteria.
7. **REQ-PIPE-403** – the headline [8]: re-measure first, per asset and by stage, on this sandbox, then three runs after. The CI cache-miss bootstrap time is recorded beside it without a budget. It also retires REQ-PIPE-250 criterion 4 (proof by the retired REQ-TEST-239 compare).
8. **REQ-GEN-404** – the anchor becomes a recorded input: one source; Child Protection's import-time anchor read (`child_protection.py:273`) moved to call time; recorded in the generator's bookkeeping and the qa schema; `--anchor` replaces `GENERATOR_ANCHOR_DATE`; resume uses the recorded anchor; a future date is refused. It amends REQ-GEN-042 criteria 7 and 8; wording goes to Keith.
9. **REQ-GEN-405** – which regenerations roll (R1, R2): the fixed test anchor is 2026-09-25, as the architect asked. The suite and CI always use it, so the CI cache key never moves with the date. A demo regeneration rolls to today on the asset's clock. Deployment-half tests and the arrival pin fail loudly at collection on a history generated at any other anchor.
10. **REQ-GEN-406** – configuration dates follow a rolled anchor (question 1). Also: Child Protection grows like its neighbours, and generation is refused past the calendar's last authored round.
11. **REQ-DASH-407** – the footer and `mothman` (the bootstrap's output and `mothman env current`) say "generated up to <date>" (R3), read from recorded QA results only.
12. **REQ-GEN-408** – reset-synthetic also deletes the asset's generated delivery and receipt trees and the bookkeeping, plus a guard test that two regenerations leave one history (R4). Today reset drops database schemas only.

## Measured baselines in the NFRs
- **Quarterly bootstrap:** 6666s against a 720s budget. Generation was about 411s (including trials, 53s on 4 workers) and the stream replay 6242s.
- **Daily bootstrap:** 681s.
- **Before #318:** both bootstrap figures predate #318's two fixes, so they are an upper bound and REQ-PIPE-403 re-measures first.
- **Full suite:** it exceeded the 2-hour background limit.
- **How to measure here:** reset-synthetic then bootstrap, one asset at a time, nothing else running, load average noted.
- **How to measure on CI:** read the hand-started test.yml's cache-miss bootstrap step. It is recorded, never gated (REQ-PIPE-250's settled rule).

## Carry-over check
- **S1** (pin once per run; slots and periods derived once; edits seen next run; REQ-PIPE-254 c15 kept for everything else; rejected: caching by file change, pinning everywhere): 397 d1/d2, 398, 400, and the c15 amendment in 397 c9.
- **S2** (the replay also runs pinned, not the recommendation; rejected: profile first, generator only): 399 d1.
- **S3** (generate once and share, measured with `--durations`; rejected: smaller histories, both): 402 d1. Sharing across workers is my choice; Keith may change it.
- **S4** (routing, and what it likely touches): the file header and build order, the c15 amendment, 403 d3 on REQ-PIPE-352's budget, and 402 for #136.
- **R1:** 405 d1, with 2026-09-25 as the fixed anchor in 405 d4.
- **R2:** 404 d1 and 405 d2.
- **R3:** 405 d3 and 407 d1.
- **R4:** 408 d1.
- **R5:** the header.
- **#318:**
  - Its two fixes are kept (398 d2).
  - The design part becomes 397 d4.
  - The stat-keyed cache conflict with REQ-PIPE-254 becomes 401.
- **#136:** the audit becomes 402. The interim fast set is already built as REQ-TEST-375, so nothing more is needed (402 d4).
- **#138:**
  - The anchor as a recorded input: 404.
  - The rounding rule: rejected by R2.
  - What a test uses as "today": 405 c6.
  - CI cache behaviour: 405 c7.
  - The doubled-history history: 404 d3.
- **Architect's note:** pinning through the 382 seam (397 d3, 399 d2); fixed anchor = 2026-09-25 (405 d4).
- **Context:**
  - One clock (B1) and neutral clock events: 397 copies the installation pattern.
  - The seeded promotion lag, now inside the replay clock per Keith's latest answer: noted in 405 d6.
  - REQ-TEST-239 retired and the standing rule: no compare criteria anywhere; 397 d7 and 403 c6.
  - Evidence item [8]: 403 d1.
- **Not needed here:** v6's own questions (Q1-Q6), the parked horizons, and #120/#121 (routed after this batch).

## Open questions (relay-ready)
**Set 1:**
1. **How do the daily asset's configured dates follow a rolled anchor?** (REQ-GEN-406)
   - (a) A synthetic asset may write a date as an offset from its history's anchor, resolved in asset_model/ and refused on a real asset; Child Protection grows; quarterly rounds stay fixed.
   - (b) Every history grows from its configured start. The daily bootstrap is 39s under budget, so it goes over within about a week of rolling, and TS-78a and TS-62 still need moving.
   - (c) Only the quarterly asset rolls.
   - **Recommend (a).**
2. **A rolled demo and the local full gate share one `supply` database.** (REQ-GEN-405)
   - (a) A bootstrap rolls only when given `--roll-anchor`, and tests refuse a rolled database.
   - (b) Roll by default; the local full gate fails until the database is rebuilt.
   - (c) Roll by default; the gate bootstraps its own test database, about 1h50m more for quarterly.
   - **Recommend (a).**
3. **What does this batch commit to against 720s?** (REQ-PIPE-403) The profile puts the replay's time mostly in dbt (49%), datacontract (18%) and re-reading the delivery tree (25%), not configuration reads.
   - (a) Build S1-S3, measure and report; REQ-PIPE-250's three profiled speed-ups go to a follow-on batch.
   - (b) Add those three now.
   - (c) Revisit the budget.
   - **Recommend (a).**
4. **What does the pin cover?** (REQ-PIPE-397) dbt and Soda read their own project files themselves.
   - (a) The pin covers mothman's own reads only; the cache key and resume digest catch a mid-run edit afterwards.
   - (b) Copy each dbt project and its check files into a pinned scratch folder.
   - **Recommend (a).**

**Set 2:**
5. **A planned receipt later today than the regeneration** (for example a 14:30 supply when regenerating at 09:00) would be in the real future, and the replay clock cannot place a decision after the real present. (REQ-GEN-405 c4)
   - (a) Anchor on the latest day whose receipts have all passed.
   - (b) Anchor today and drop the receipts not yet due.
   - (c) Anchor today and keep receipts in the future.
   - **Recommend (a).**

## NFR angles
- **Answered myself:** performance (baselines and how to measure), reliability, security (the pin and offset dates are refused on a real asset), privacy (the build reads only recorded QA results), compatibility (asset clock, no new dependencies), maintainability (one seam; the quarterly calendar needs extending yearly), observability (pin digest, "generated up to", generation time), and cost (the CI key is stable; read CI figures off runs that are due anyway).
- **Ruled out:** compliance and retention (synthetic only; R4 settled replacing rather than archiving) and scalability beyond the memo's size.
- **One left for Keith:** whether the suite should have a time target. I drafted "measure and report, no target", in line with CLAUDE.md's informal runtime log.

## Draft plans entries (for a human to apply after the suite finishes)
- **plans/running-thoughts.md #138:** append "**SCOPED 2026-11-14** with S1-S3 as docs/drafts/speed-anchor-v1.yaml (REQ-GEN-404 to 406, REQ-DASH-407, REQ-GEN-408); a read-only probe found the daily asset's configured dates do not follow a rolled anchor (question 1). Not signed."
- **#136:** append "The audit's first step is SCOPED as REQ-TEST-402 (speed-anchor v1)."
- **post-build-review #318:** append "The design remainder is SCOPED as REQ-PIPE-397 to 401, REQ-GEN-398/399 and REQ-PIPE-403 (speed-anchor v1); the second fix's mtime/size keying conflicts with REQ-PIPE-254 criteria 2 and 15 (REQ-PIPE-401)."

## Register edits needing Keith's exact-wording approval
- REQ-PIPE-254 criterion 15 scoped to "outside a pinned run".
- REQ-GEN-042 criteria 7 and 8 amended for an anchor recorded with the history.
- REQ-PIPE-250 criterion 4 retired with REQ-TEST-239's reason, and its BEHAVIOUR-PRESERVING NFR dropped.

## Provisional choices of mine that Keith may change
- Pinning is refused on a real asset (397).
- Stream processes are handed the parent's contents rather than re-reading (399).
- The anchor is recorded in two places, the bookkeeping and the qa schema (404).
- The "generated up to" line goes in the footer (407).
- The suite builds its shared history once across workers (402).

## Files
- `/home/user/data-poc/docs/drafts/speed-anchor-v1.yaml`
- Probe scripts: `/tmp/claude-0/-home-user-data-poc/5735d9c2-23bf-590b-afe1-e67b136c7e21/scratchpad/probe.py` and `/tmp/claude-0/-home-user-data-poc/5735d9c2-23bf-590b-afe1-e67b136c7e21/scratchpad/probe2.py`

## Addendum (Keith's answers applied; REQ-PIPE-430 to 432 added)

I applied Keith's answers in place to `/home/user/data-poc/docs/drafts/speed-anchor-v1.yaml` and added REQ-PIPE-250's three profiled speed-ups as REQ-PIPE-430, 431 and 432. The draft check now reports only the 31 expected cross-reference errors, and every dependency resolves to requirements.yaml, separation-v6.yaml or this file. I touched no other file and committed nothing. `docs/drafts/decisions-2026-11-01.md` also shows as modified, but that edit isn't mine.

Every open question is now `[]`, closed in `decisions:` as SETTLED by Keith 2026-11-14 with the rejected options. My five earlier provisional choices stand; none conflicted with his answers.

## What changed in the existing requirements
- **Header:** records Keith's answers and that ids 430+ were taken to stay clear of timing-attempts-v1's 409-416 (I checked 430-436 were free in requirements.yaml, docs/drafts and plans). The build order adds 432, then 430, then 431. The three register amendments are marked APPROVED AS WORDED, each applied when its requirement is built.
- **REQ-PIPE-397 (Q4):** new criterion 8 says the pin covers mothman's own reads only; dbt's and Soda's own reads of their files stay live and are caught afterwards by the cache key and the resume digest. The tests criterion now includes a dbt model edited inside a pin still reaching dbt. The REQ-PIPE-254 criterion 15 amendment is approved.
- **REQ-PIPE-403 (Q3):**
  - The before and after measurements now include REQ-PIPE-430 to 432, and the before breaks the replay down by the profile's shares so each speed-up has its own baseline.
  - The PERFORMANCE NFR now gives an honest estimate (below). REQ-PIPE-250 criterion 4's retirement is approved.
- **REQ-GEN-404:** the REQ-GEN-042 criteria 7 and 8 amendment is approved.
- **REQ-GEN-405 (Q2, Q5):** the title is rewritten. A bootstrap rolls the anchor only with `--roll-anchor`, and without it uses the fixed 2026-09-25 everywhere (new criterion 4). It anchors on the latest day whose planned receipts have all passed (criterion 5). Tests meeting a rolled database fail with one clear message naming the anchor found and the rebuild commands (criterion 6). New criterion 7 refuses `--roll-anchor` under the test and ci environments. Cross-references were renumbered.
- **REQ-GEN-406 (Q1):** the PROVISIONAL markers are gone. A new criterion writes the daily asset's calendar versions, correction dates and setting eras as offsets from the anchor. At the fixed anchor they resolve to today's dates, and the quarterly rounds and older dates stay absolute.
- **REQ-TEST-402 (suite target):**
  - **Target:** under 30 minutes on this 4-core sandbox, reported and never gated, recorded as a decision with Keith's rejected options.
  - **New criterion:** if the suite is still over 30 minutes, the slowest modules and classes are recorded and the target is not called met.
  - **What beyond S3 it likely takes:**
    - The speed-ups in this batch reaching every test that runs a real pipeline.
    - Trimming the slowest browser classes. `tests/test_dashboard_e2e.py` was 659-717s at REQ-TEST-281, with `TestEveryScenarioJumpLands` alone 400-500s on one worker.
    - Moving tests that re-run all four tools onto shared, already-evaluated runs where the tool itself isn't what's being tested.
  - Each of those changes which tests exist, so each would be its own requirement for Keith.

## New requirements
- **REQ-PIPE-430 (must):** inside a pinned bootstrap, each collection's delivery tree is recognised once, which covers the calls from orchestrate, stage, the bootstrap and the next-receipt look-ups. A digest of the tree is checked at the end, and a mismatch is reported. Unpinned, it reads the tree as today. This targets the 25% share. I keyed it on the pin rather than on the tree's content, because checking the content means reading every receipt, which is most of the cost.
- **REQ-PIPE-431 (should):** datacontract-cli moves into a long-lived worker process, shaped like `dbt_worker`, so there are three lanes at once: dbt, datacontract, and Soda then Evidently. Results stay in tool order, a dead worker fails only that step, and `--sequential` stays in-process. This targets the 18% share. A process, not a thread, because these tools can't safely share an interpreter.
- **REQ-PIPE-432 (must):** first profile one dbt invocation by phase over ten or more runs. Then make dbt's `threads` a named setting (it is 1 today in `qa_tools/dbt_profiles/profiles.yml`), measured at 1, 2 and 4 with both streams running. Then cut any repeated per-run phase using dbt's documented options only. Verdicts still come from each run's own `run_results.json`. This targets the 49% share.

## Honest NFR on what's reachable
dbt already runs beside the other three tools, and the 49% "waiting on dbt" means it outlasts all of them. That is why 432 comes first and 431 pays nothing until 432 lands.
- **Tree work (430):** saves up to about 1,500s of today's 6242s replay.
- **Estimate if all land well:** the quarterly replay comes down to about 2,000-3,000s plus generation, still several times the 720s budget.
- **Why:** the asset replays roughly 450 runs, so 720s would need well under 1.5s per run with everything included.
- **Daily asset:** should stay within its budget.
- **Caveat:** this estimate comes from one profile. REQ-PIPE-403's measurement is the real answer, and its criterion 5 records the shortfall rather than calling the budget met.

## New questions
None blocking. One thing Keith should hear: on Keith's own numbers the quarterly 720s budget is not expected to be met even with all six speed-ups. Whether to then shrink the history, accept a larger budget, or go after per-run cost further is a decision for after REQ-PIPE-403's measurement, not now.

## v2 report (reviews and SR1-SR9 folded in)

v2 is written as a new file, `/home/user/data-poc/docs/drafts/speed-anchor-v2.yaml`, with all 15 ids kept and every open question `[]`. The draft check reports nothing except the 31 expected cross-reference errors, and every id the file names exists in requirements.yaml, separation-v6.yaml or the draft itself. I spot-checked the reviewers' line references against the code at HEAD before carrying any finding, and all the ones I checked held. v1 is untouched, nothing else was edited, and nothing is committed. The `decisions-2026-11-01.md` change in the working tree is not mine.

## Changes, one line per requirement
- **REQ-PIPE-397:**
  - The pin reads a declared set of files up front at install (the asset's *.yaml/*.yml without dbt_packages, environments.yaml, the shared file-checks default), keyed on resolved path (B1).
  - It is handed to every pool through `assets.handoff()`, and the target-trial pool (`cli/target_trial.py:171-174`) moves onto it (B1).
  - Every read of those files goes through config_yaml, enforced by a gate rule on REQ-TEST-384's walker plus an audit-hook test (B2). I found 54 `config_yaml.parse` calls in 26 files and 34 `yaml.safe_load` calls that read the file themselves.
  - Smaller fixes: a missing file raises every time, `load()` keeps its deep copy, and the "no system call" NFR now says "no file read".
- **REQ-GEN-398:** generation time becomes an entry in the existing "Took" line, and generation never snapshots the delivery tree (B4).
- **REQ-GEN-399:**
  - Every process the bootstrap starts is handed the snapshot.
  - A digest mismatch exits non-zero, the TUI doesn't print "Ready", and the message says the fault is ours.
  - One closing block for CLI and TUI: Took line, budget line, a dimmed 12-character pinned digest, then "generated up to <date>" with which anchor. No statement ends in "..." (CLI 4, 10).
- **REQ-PIPE-400:**
  - Function names corrected: `slots.slots_for_dataset`, `Agreement.standing_on`.
  - The memo is keyed on the Agreement actually used plus the time-zone versions in force. It holds strong references and is bounded, so it is correct pinned or not (B3).
  - Tests plant a time-zone correction as well as a calendar one.
- **REQ-PIPE-401:** content-keyed through a bounded, locked Built store; no longer depends on the pin, so it is built first and test-first. `list_setting_members.py:253`'s raw read is routed too.
- **REQ-TEST-402:**
  - The hand list of generating tests becomes a rule plus a build-time grep recorded in evidence.
  - The shared history is never under `data/` and is gitignored before its first write.
  - Writes are refused by guarding the five writers, not by permissions, with an end-of-session digest as a backstop.
  - Concurrency: `fcntl.flock` exclusive to build and shared to read; a stale history is removed only if no other session holds it.
  - The cache key follows REQ-GEN-381's inputs and includes the anchor.
- **REQ-PIPE-403 (SR7):**
  - It records before and after by stage and is cited as evidence for REQ-PIPE-250 c2 and c5; its own restated-budget and CI-figure criteria are gone.
  - It records commit and load average per measurement.
  - The TUI's "a few minutes" becomes the measured figure.
  - The REQ-PIPE-250 c4 retirement waits on REQ-TEST-393.
- **REQ-GEN-404:**
  - The anchor is recorded in a third place, a one-line file beside the delivery tree (SR1).
  - `--anchor` on the bootstrap and every generate command; `--roll-anchor` on the bootstrap only; both together is a usage error.
  - Refusals:
    - a future date (with the CLI's wording);
    - a date before 2026-09-25 (SR6);
    - a bare generate whose anchor differs from the recorded one (SR3);
    - `GENERATOR_ANCHOR_DATE` set (README lines 631-635 updated).
  - The anchor is installed process-wide and handed to children, and folded into the cache key.
  - With no tree, offsets resolve to the fixed anchor only under test and ci.
- **REQ-GEN-405:**
  - The deployment database is checked once per asset before any test runs, with one message. It also refuses a database with no recorded anchor, and offers reset then bootstrap only (SR2, CLI 3).
  - Refusals: `--anchor` other than the fixed date under test or ci; `--roll-anchor` or `--anchor` on a populated database (non-zero exit).
  - The step-back to an earlier anchor day is worked out from the built arrivals and said before the long part.
  - Reset names both next steps, and bootstrap `--help` gets an examples block.
  - v1's "two databases side by side" note is corrected: one checkout holds one history. The route for both side by side is a second worktree, with the `deployment_dsn_for` caveat.
- **REQ-GEN-406:**
  - Offsets resolve from the anchor file (SR1, B6).
  - Readers that parse the file raw (`validate_schedule.py:2307` and `:2330`, `synthetic_inputs`) go through the resolver.
  - The freeze gate resolves both versions it compares against one anchor.
  - The page shows only absolute dates (dashboard 5).
  - A scenario link with a stale date lands on the scenario's current date, corrected with `replaceState` (SR9).
  - The calendar refusal gives a pasteable `candidate-dates` command and a fallback.
- **REQ-DASH-407 (rewritten):**
  - Footer sentence: "...generated up to and including <date>; a period after that date has no supply." Plus the as-of panel line under the picker (SR8).
  - The date travels as a `BUILD_PROVENANCE` field; the not-recorded wording carries no command.
  - The picker's default and range are unchanged (dashboard 3).
  - `env current` and `env list` read the anchor file, so they never need the database (CLI 8).
- **REQ-GEN-408:**
  - The reset also deletes the placements file and the anchor file.
  - Before the phrase it lists each tree with file counts and the anchor about to be deleted.
  - New phrase: "delete all QA history and generated files for <asset>" (SR4).
  - It refuses while any delivery folder the bookkeeping doesn't list exists (SR5).
  - It refuses symlinks and data folders outside the asset's own, and gives a per-part closing report and updated `--help`.
- **REQ-PIPE-430:**
  - The tree snapshot is its own installation, made after generation and per collection in the one-collection branch (B4).
  - `files_by_dataset` is read-only per caller.
  - A changed tree exits non-zero and names the likely cause neutrally.
- **REQ-PIPE-431:**
  - Only the datacontract-cli library call goes to the worker. Asking, filtering, left-out notes and recording stay in the run's process (B5), and tests check the replay-clock stamp and that a re-check's scope survives.
  - Worker code is shared with `dbt_worker`, and credentials go by environment.
  - Failure wording follows CLI 9, and the `--sequential` help is updated.
- **REQ-PIPE-432:** threads passed as dbt's `--threads` flag from one constant per worker, a bad value refused by name, results sorted by unique_id, and the connection count now includes the test suite.

## Findings not carried, and why
- **Architect's seam note on `promotion.next_receipt`** (let the replay clock work out the next receipt, removing half of REQ-PIPE-430's work): recorded as a decision on 430 for whoever builds REQ-PIPE-382. Doing it would edit v6, which this batch must not.
- **REQ-PIPE-250's stale title** ("all three collections"): flagged in a 403 decision as a retitle for Keith to word. It is a register edit to another requirement and wasn't approved.
- **Dashboard finding 1:** settled by SR8. **Finding 6** said no change was needed.
- **Architect's no-duplication note on REQ-TEST-116:** confirmation only; nothing to carry.
- Everything else (B1-B6, the non-blocking list, CLI 1-11, dashboard 2-5) is carried.

## Choices I made for Keith to check (each marked "Keith may change it")
- **A database with no recorded anchor is refused too.** Every local database bootstrapped before REQ-GEN-404 has none, so the first full gate after it forces one rebuild per asset. That coincides with v6's planned post-build reset, so it shouldn't cost an extra rebuild.
- **The test cache is one folder shared across `MOTHMAN_TEST_DB_TAG` values, using shared locks,** rather than a folder per tag.

## New open questions
None that block. The one thing worth Keith's attention is that SR5 and SR3 together tighten the reset path: a hand-filed folder blocks the reset, and a mismatched anchor blocks a bare generate. So a person can be stopped twice before getting a clean demo. Both messages name the next step.
