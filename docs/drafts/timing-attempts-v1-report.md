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
