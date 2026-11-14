# Check timing + failed attempts v1 - the scoper's report, 2026-11-14

I've drafted 8 requirements in a new file, /home/user/data-poc/docs/drafts/timing-attempts-v1.yaml. `uv run mothman dashboard validate-requirements --draft` reports only the 4 expected cross-reference errors, for REQ-PIPE-279 and REQ-DASH-148, which this draft depends on but doesn't contain. No other file was touched and nothing is committed. Ids 409-416 were free in requirements.yaml, docs/drafts/ and plans/ today; whoever applies this should re-check. Code was read at HEAD bf1263a4. None of this is signed, and 8 open questions are still with Keith.

**The main finding: #121's premise is out of date.** REQ-PIPE-279 (built, signed 2026-10-23) already added `qa.run_attempt` (qa_store.py:286-311). It keeps one row per attempt, and a reopen, retry or re-record never removes one. The outcomes are COMPLETED / TIMED-OUT / INTERRUPTED / CRASHED (qa_results_writer.py:893-918). That requirement's own non-functional note says the table exists so #120 and #121 "can be read from it later. Nothing here displays it." So F1 is mostly built. This batch adds:
- the run time;
- the TOOL-ERROR outcome F1 names, which today is CRASHED with error type "QaRunFailure";
- everything that displays attempts.

**The clock.** Attempt start and end are stamped by `qa_store._stamp()` (2143-2147), which is the replay clock during a replay. REQ-PIPE-382 makes that the one clock, and in a replay it jumps forward on decision events. So a run time is never the difference of two recorded instants. It comes from `time.monotonic()`, read deliberately outside the clock seam so no installed clock can replace it. Which clock stamps the start and end instants is question 1.

## Requirements
| Id | Title (short) | One line |
|---|---|---|
| REQ-PIPE-409 | Every attempt records its real run time | New `elapsed_seconds` column, filled from a monotonic counter in the end-of-attempt update. NULL when the next attempt finds this one dead. The run's time is its newest completed attempt's. Schema version 50 bumped. |
| REQ-PIPE-410 | TOOL-ERROR outcome naming the tool | `QaRunFailure` carries the tool's name as a field. The error type recorded is the tool's own exception, not the wrapper. TIMED-OUT now keeps its message too. |
| REQ-PIPE-411 | The results file and dashboard data carry run times and attempts | Includes runs whose attempts all failed, which are outside `qa.run_visible` today. Reads only `qa.run` and `qa.run_attempt`, never pg_locks. Builds stay byte-identical. |
| REQ-PIPE-412 | The 'slow' rule (T3), computed once in the build | Strictly more than 2x the median of earlier-ranked runs. A run's mark never flips when later runs arrive. Never a status, never a block, no alert. |
| REQ-DASH-413 | Run-time trend per dataset, and the time on each supply-history row | 'Slow' is a word, never Pass/Warn/Fail colours. Clipped to the as-of date. Nothing on mock datasets. |
| REQ-DASH-414 | A retried run carries one note, and its attempts can be listed (F2) | Pass/Warn/Fail comes from the successful attempt only. |
| REQ-DASH-415 | 'Not checked - the run timed out/crashed/…' (F3) | Every check reads 'No result'. That supply replaces the earlier one as the dataset's own, so no stale Pass. Running and dead-but-not-yet-found attempts get the same words, because the build reads no locks. |
| REQ-TEST-416 | `mothman` prints the run time, or how an attempt failed | One line from `orchestrate.run_one`, so every command that runs QA prints it. One duration format shared by the Python and JS sides, with a parity test. |

## Open questions (two relay-ready sets, each with a recommendation)
**Set 1**
1. **(409) Which clock stamps start and end?** (a) The one clock, as today. (b) Always the wall clock. **Recommend (a).** The two are identical on a real asset. (b) would make replayed records read as made today, which REQ-PIPE-081 criteria 27-31 fixed, and it breaks the as-of view of 'not checked'.
2. **(412) Which runs feed the trend and the median?** (a) Whole-supply runs only (arrival and full re-check); readers-only runs show their time but aren't judged. (b) Every run. (c) One series per scope. **Recommend (a).**
3. **(412) What baseline counts as 'previous runs'?** (a) All earlier runs, minimum 3. (b) The last 20, minimum 3. (c) All earlier runs, from the second run on. **Recommend (b),** stated as a choice rather than a measurement.
4. **(415) What is the dataset's status while its supply is not checked?** (a) Like a supply that couldn't be loaded (REQ-DASH-148): one dataset-level red reason, 'Could not be checked', plus an item on the 'needs a person' queue, with no Fail recorded on the supply. (b) A new 'Not checked' status. (c) As (a) without the queue item. **Recommend (a).** F3's "as today's could not run does" alongside "REJECTED failing the supply" is genuinely ambiguous.

**Set 2**
5. **(411) Privacy: is an error's message published on the page?** (a) As recorded. (b) Only outcome, tool and error type, with the message left to `mothman` and the database. (c) Scrubbed. **Recommend (b).** A message can quote supply values or hosts, and a build may never read actual data.
6. **(409) What does a run time span?** (a) The attempt, from open to complete. (b) The whole arrival, including staging and the gate. **Recommend (a).**
7. **(412) Should the demo plant a failed attempt?** (a) No, tests prove it. (b) The replay forces a first-attempt failure. (c) A supply left permanently not checked. **Recommend (a).** (b) needs a fault hook the replay can reach, which is the kind of seam #134 v6 removes.
8. **(414) The word 'attempt' already means a resupply** ('Resupply, attempt N', template:9464). (a) "Checked on the second try - the first timed out after 45 min". (b) "Check attempt 2…". (c) F2's words as given. **Recommend (a).** This one goes to the dashboard UX reviewer first.

## Carry-over check
- **T1** (one time per run, never the simulated clock; rejected per-check and per-tool timing) → 409's decisions 1-2 and criteria 4-5.
- **T2** (trend, the time beside each run, and the CLI; rejected dashboard-only and CLI/logs-only) → 413's decision 1 and 416's decision 1.
- **T3** (more than 2x the median, 'slow', never status or block; rejected trend-only and a per-dataset rule) → 412's decisions 1, 2 and 6, and 413's decision 2.
- **F1** (every attempt kept; rejected a count plus the last reason) → mostly built in REQ-PIPE-279. Run time → 409's decision 4. 'Tool error' → 410's decision 1. INTERRUPTED is kept (410's decision 2).
- **F2** (note plus list, verdict from the successful attempt; rejected detail-only and lifting to Warn) → 414's decision 1 and criterion 4, and 411's decision 3.
- **F3** ('Not checked', 'No result', the status like 'could not run'; rejected failing the supply) → 415's decision 1. The ambiguity is question 4.
- **ROUTING** → the file header and the reviewer flags.
- **#120's "maybe alerting"** → 412's decision 'NO ALERT', pointing to #124.
- **#121's "for the UX review"** → reviewer flags in the header and in 414.
- **#124 and post-build-review #262 R3** (lock keepalive and heartbeat, "leave until AWS") → not carried, deliberately. 409's decision 'UNKNOWN STAYS UNKNOWN' cites it.
- **#119** (show start or end time) → not carried; it stays its own item.
- **REQ-TEST-239 retired, and the standing rule that the synthetic demo may move** → the header and 409's last decision. No criterion relies on the equivalence compare.
- **REQ-PIPE-382's one clock** → the header, plus 409's decision 3 and question 1.

## For the reviewers
- **Architect:**
  - Does `time.monotonic()` in a real pipeline module clash with REQ-PIPE-382 criterion 1 or REQ-TEST-384's imports gate?
  - 411 is the first build read of runs that aren't visible.
  - The median's cost at about 30 collections.
  - A Lambda killed at its limit ends INTERRUPTED with no end time and no run time.
- **Dashboard UX:**
  - The 'attempt' wording clash (question 8).
  - There is no run-level detail panel today, so the attempts list is drafted as a disclosure on the supply-history row.
  - 'Slow' must not read as a status.
  - The trend must not crowd the page.
- **CLI UX:**
  - The one-line output on every QA command, including the bootstrap's per-run header.
  - Whether the CLI should also say 'slow'; T3 doesn't name the CLI.
  - Nothing in `mothman` lists incomplete runs or attempts today.

## Draft plans entry (for a human to apply; running-thoughts.md owns #120/#121)
Add to the end of both #120 and #121: "**Scoped 2026-11-14** (T1-T3, F1-F3) into REQ-PIPE-409 to REQ-TEST-416, docs/drafts/timing-attempts-v1.yaml - not signed. #121's 'a retry leaves no trace' has been untrue since REQ-PIPE-279 added qa.run_attempt; this batch adds the run time, TOOL-ERROR and everything that shows them." Change both status tags from `todo` to `in-progress`, or leave them as they are until sign-off; that's for whoever applies it.

## What I decided myself
- **Angles answered from the code:** recording performance, storage growth (on the order of 10k attempt rows a year at 30 collections, and per-check timing not recorded), reliability, security, compatibility (no new dependencies or vendored assets), auditability, determinism, and dashboard weight (an attempt list only where it says something, with the measured size recorded as evidence rather than an invented budget).
- **Angles ruled out:** compliance and retention (attempts are history and never pruned, per REQ-PIPE-279), and cost (negligible).
- **Provisional calls, to be checked:** run time comes only from completed attempts; there is no per-tool time limit today, so "timed out after 45 min" can only mean a lock or statement timeout on our side, or a stop from outside; a failure before an attempt opens is out of scope.

## Addendum (Keith's eight answers applied; new Q9)

I've applied all eight of Keith's answers (TA Q1-Q8) in place to /home/user/data-poc/docs/drafts/timing-attempts-v1.yaml. Each is now a SETTLED decision with its rejected options, and every criterion that used to say "as open question N settles" now carries the answer. Applying Q4 raised one new question (Q9 below).

The draft check (`validate-requirements --draft`) shows only the 4 expected cross-reference errors (to REQ-PIPE-279 and REQ-DASH-148, which the file doesn't contain). I read the changed fields back with `yaml.safe_load` to confirm they're on disk. Only that file was touched and nothing is committed. git now shows it as `M` rather than `??`, so someone else had already committed v1.

## What changed
- **Header:** notes the in-place update and the new question 9. The clock line now reads SETTLED, and the dashboard-UX flag now says the 'second try' wording was settled.
- **REQ-PIPE-409**
  - New criterion: an attempt's start and end stay stamped by the one clock (`qa_store._stamp()`, REQ-PIPE-382).
  - Decisions added: TA Q1 (rejected: always the wall clock).
  - The provisional "what an attempt spans" decision is now TA Q6 SETTLED (rejected: the whole arrival including staging and the gate).
  - open_questions is now empty.
- **REQ-PIPE-410:** the privacy note now says the message is never published, only outcome, tool and error type (TA Q5).
- **REQ-PIPE-411** (now 11 criteria)
  - The attempt list emits the error type, never the message. New criterion: no `error_message` anywhere in the results file, dashboard data or built page.
  - Two new criteria for TA Q4:
    - a new UNCHECKED kind in `dataset_blockers.py`, beside REFUSED. It reads 'Could not be checked', opens at the supply's receipt as a refused load's does (post-build-review #118 D-B), and records no Fail on the supply.
    - a matching blocking 'needs a person' item in `outstanding.py`, beside FAILED_LOAD.
  - Tests extended to cover both.
  - Decisions added:
    - TA Q5 (rejected: publishing the message as recorded; publishing it scrubbed).
    - TA Q4 (rejected: a new 'Not checked' status; the red reason with no queue item).
    - Opened at receipt (mine; flagged for the architect).
    - Not the same thing as REQ-DASH-394's configuration-error item, because no attempt opens in that case.
  - The open question is replaced by Q9.
- **REQ-PIPE-412**
  - Criterion 1 now judges against the last 20 earlier whole-supply runs (scope arrival or full).
  - New criterion: a readers-only run is neither judged nor counted in anyone's baseline.
  - The minimum is now 3 earlier whole-supply runs.
  - Tests added: the 4th run is the first judged, a 22nd run is judged against runs 2-21 only, and readers-only runs are excluded.
  - Scale note: the window makes the cost linear.
  - Decisions added:
    - TA Q2 (rejected: every run in one series; one series per scope).
    - TA Q3, recorded as a choice (rejected: all earlier runs with a minimum of 3; all earlier runs from the second).
    - TA Q7 (rejected: the replay forcing a failure; a supply left not checked for good).
  - open_questions is now empty.
- **REQ-DASH-413:** the trend has one point per whole-supply run.
- **REQ-DASH-414**
  - Note wording: "Checked on the second try - the first timed out after 45 min", with 'crashed' / 'failed in <tool>' / 'was stopped' substituted as the earlier try ended. 'Attempt' is never used, because it stays the resupply word.
  - The attempt list shows the error type, never the message.
  - Decision TA Q8 added (rejected: 'Check attempt 2 succeeded'; F2's words as given).
  - open_questions is now empty.
- **REQ-DASH-415**
  - Not-checked words carry the tool and error type, never the message.
  - The dataset reads red through the UNCHECKED blocker with 'Could not be checked' shown once, and its queue item is labelled the same, exactly as REQ-DASH-148 does for a failed load. No check is shown as Fail.
  - The as-of window now runs from the supply's receipt until the blocker resolves. v1 started it at the failed attempt's end; I changed it to match the failed-load precedent, and the decision says so.
  - Decision TA Q4 added. open_questions is now empty.
- **REQ-TEST-416:** unchanged. The terminal still prints the full stored message, which TA Q5 allows.

## The new question (on REQ-PIPE-411)
**Q9. What clears a 'Could not be checked' item, and what does it offer?** A failed load is cleared by a reload or by a person rejecting the supply, and its item offers 'reject the supply'. A failed run is retried by the next processing pass (`processing_pass.py` line 207), so a one-off crash clears itself. But a run that fails every time, such as a file that loads but crashes a tool, never will.
- (a) Like a failed load: cleared by a completing attempt OR a person rejecting the supply. The item offers 'reject the supply' and says the next pass will retry it.
- (b) Cleared only by a completing attempt. The item offers nothing to decide, only something to investigate.

**I recommend (a).** Under (b), a supply that always crashes keeps its dataset red until the code is fixed, with nothing a person can do about it. Under (a) it's the same decision people already make for a file that won't load, through the existing decision log.

## One call of mine for the architect to check
The UNCHECKED blocker and the not-checked window start at the supply's receipt, following the failed-load precedent. The alternative is to start them when the failed attempt ended.
