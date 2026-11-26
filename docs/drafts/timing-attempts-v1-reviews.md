# Check timing + failed attempts v1 - the pre-build reviews, 2026-11-14

## Dashboard UX (delivery-dashboard-ux)

I reviewed docs/drafts/timing-attempts-v1.yaml (REQ-PIPE-411/412 as they reach the page, and REQ-DASH-413/414/415) against the template, docs/hci-ux-psychology.md, docs/spa-best-practices.md, docs/project-context-for-agents.md and REQ-DASH-148 as built. This is advisory only: I edited no files and re-asked none of TA Q1-Q9. Findings are most important first. The questions at the end are new forks, not re-asks.

## Contexts and the principles I checked against
- **REQ-DASH-415 is an error/failure state.** That is the heaviest weight in the doc's ordering. I checked it for: non-punitive framing; attribution (who is responsible, and is it one-off or recurring); a realistic next step so it doesn't teach learned helplessness; and no stale Pass (negativity bias).
- **REQ-DASH-414 is investigating/drill-down, close to error states.** I checked progressive disclosure, and the peak-end rule: a run that passed on retry should end clean, not alarming.
- **REQ-DASH-413 / 412 are investigating/drill-down for the pipeline maintainer, and routine daily use for the data team leader.** I checked: Hick's Law and Gestalt hierarchy (the trend must not crowd "is my dataset OK"); consistency (reuse the chart frame); and Von Restorff (a slow run stands out, but not as a verdict).

## 1. Blocking: "Not checked" and "No result" clash with words the page already uses (REQ-DASH-415 c1, c2)
- **"Not checked" is already a status word.** It is `STATUS_WORDS.notchecked` (template ~2256), drawn as a dashed `.pill.notchecked` and listed in `LEFT_OUT_STATUSES`. The page defines it in words in `notCheckedNote()` (~6857): "means the check did not run on this supply, for the reason given. It is neither a Fail nor a result, and does not count toward this dataset's status." 415 uses "Not checked - the run timed out" for a supply that makes the dataset red. A reader would meet two meanings of the same label on one page, and one of them says "does not count toward status".
- **"No result" doesn't match the failed-load pattern 415 says it follows.** "No result" is only the cross-table grid's word (`XT_WORD`, ~6383). REQ-DASH-148 c2 and its decision say a blocked dataset's checks read the existing grey "No data". The blocked banner says so in words (~10219: "Every check on this dataset's own data reads No data").
- **REQ-DASH-148 already has a ready-made shape for this.** `blockedBanner` (~10213) reads "<label> — this dataset's own supply is not checked until …", from `BLOCKER_LABEL` and `BLOCKER_SAYS`. With label "Could not be checked" it says everything F3 asked for, in the page's own words.
- **Suggested c1/c2 wording:** "THE SYSTEM SHALL lead with 'Could not be checked' everywhere it labels such a supply (BLOCKER_LABEL, OUTSTANDING_KIND_LABEL, the supply-history row, the dataset banner), with BLOCKER_SAYS 'its supply arrived and our check of it did not finish', and SHALL show its checks as the existing grey 'No data', exactly as REQ-DASH-148 criterion 2. It SHALL NOT use the 'Not checked' label or the `notchecked` pill for it."
- This puts F3's wording against TA Q4's "like a failed load" in a way Keith hasn't seen. That is Q1 below.

## 2. Blocking: the as-of view would describe events that hadn't happened yet (REQ-DASH-415 c6, REQ-DASH-414 c5)
- **The problem.** The red window opens at receipt (fine, matching REQ-DASH-148 c3). But c1's words ("the run timed out", "a tool failed (dbt)", the time it ended) describe the failed attempt's end. On any date between receipt and that end, the as-of view would state a timeout that had not yet happened.
- **This is not an edge case in a replay.** One quarterly run spans about 6.3 simulated days.
- **414 c5 has the same flaw.** "Only attempts that began by that date" would show an attempt that began before the date with an outcome from after it.
- **Suggested criterion:** "WHILE a date is on show, THE SYSTEM SHALL judge each attempt as at that date: before it began, it is not shown; after it began and before it ended, it reads as the unfinished words of criterion 5 ('a check began <time> and has not finished'), with no outcome, end or run time; only once it has ended does its outcome show. The red window still opens at receipt."
- Add an as-of test of a date between receipt and the failed attempt's end.

## 3. The run time must not go in the supply history's "Timing" column (REQ-DASH-413 c2)
- **"Timing" already means something else.** The columns are Arrived / Status / Timing / Rows / Outcome / How it got here (`SUPPLY_CYCLE_HEAD`, ~9525). Timing is about arrival: the arrival pill, the receipt, and `waitedChip()`, which is itself a bare mono duration ("4h").
- **The code already warns about this.** `waitedTitle()`'s comment (~2022) says: "'4h' beside an arrival time reads as part of the arrival unless something says otherwise." A second bare duration in that cell would be read as the supplier's lateness.
- **Put the run time in the Status cell instead.** That is where the existing note about how the check went already lives: the muted 12px `span.arrived-as.rechecked` note in `supplyRowStatus` (~9388). Facts about our check then sit together: the pill, how long it took, and whether it needed a second try.
- **Suggested c2 wording:** "THE SYSTEM SHALL show each run's run time in the supply-history row's Status cell, after its status, as muted text carrying its own words ('Checked in 3m 12s'), styled as the existing re-check note, and SHALL NOT put a run time in the Timing column."

## 4. "Slow" has to sit outside the status grammar (REQ-DASH-412 / 413 c3)
- **Supply-history row.** Every `.pill` in the Status cell is about the verdict: status, acknowledgement, red-promoted, "Promoted, then warning on re-check". A "Slow" pill there would join that family, even in the neutral `pill tag` style. Make it a plain word inside the run-time text instead: "Checked in 2h 05m · **slow**". Bold ink gives Von Restorff contrast; muted ink keeps it a note.
- **Trend: reuse `unitTrendBlock()`'s frame** (~4692), not a new chart. That means `.unit-trend` / `.unit-trend-title` / `.chart-axis-title` and its "View as table" toggle into a `.trend-table`.
  - Draw it in neutral ink only, the way the quiet mode already draws history.
  - Mark a slow point by shape (a ring) plus a text label, never red or amber.
  - y-axis labels use the duration format.
- **Hover AND focus.** The existing per-point tooltip (the `spark-tip` `<title>`, ~4559) works on hover only. Use the existing "View as table" as the focusable, text route instead of inventing focusable SVG points. Suggested c3 addition: "The trend's 'View as table' SHALL list every run, newest first, with its run time and, where judged slow, 'Slow - median <d> over <n> runs' in words; a run judged against too few earlier runs SHALL read 'too few earlier runs to judge' there, and nothing on its supply-history row."
- **Keep it off every tier above the dataset.** Suggested new criterion: "THE SYSTEM SHALL NOT show run times or the slow mark on agency or collection cards, the dataset list, the 'needs a person' queue or any rollup." At about 30 collections, an aggregated "slow" count beside a status pill would become a status in all but name.

## 5. Trend placement at ~30 collections (REQ-DASH-413 NFR 'UX BAR')
The per-page count doesn't change with more collections. What matters is the dataset page's own hierarchy. Today that is:
- the header pill and banners;
- the sla-strip tiles;
- the "Columns failing and warning" `unitTrendBlock`;
- the scope sections and column grid;
- the supply history, at the bottom.

A second full-size chart above the grid would compete with the one that answers "is my dataset OK".

**My recommendation: head of the Supply history section, above the cycles.** That is where the maintainer reads per-run facts. It is also rendered on the blocked and not-checked branches (via `#supply-history-wrap`), which the column trend deliberately isn't (`ds.blocked ? "" : unitTrendBlock(...)`). That matters: #120's own story is a run growing from 5 minutes to 3 hours, then timing out, so the trend is most useful on exactly the page where the dataset reads "Could not be checked". This is Q2.

## 6. Which run a row's time and note belong to (REQ-DASH-413 c1/c2, REQ-DASH-414 c1)
- **The counts don't line up.** Supply-history rows are supplies (`data-run-id` is the arrival run). The trend includes full re-check runs (TA Q2), and those have no row of their own. A slow full re-check would be a marked point with nowhere on any row to say so.
- **Suggested criterion:** "A row shows its arrival run's run time and try-note; a full re-check's run time, slow mark and try-note SHALL appear in that row's existing re-check note ('re-checked 14 Nov in 2h 05m · slow'), and a readers-only re-check's time likewise, never judged."
- **REQ-PIPE-411 c3 also doesn't exclude re-check runs** from "not checked". That is Q3.

## 7. Retried runs: make the note itself the disclosure (REQ-DASH-414 c1, c2; NFR ACCESSIBILITY)
- **Use native `<details>`/`<summary>`.** It is already the page's disclosure pattern (`details.file-passed`, `.category-group`; CSS ~876, ~915). It opens by keyboard and is announced by the browser for free, which meets 414's accessibility NFR with no new mechanism.
- **Make the one-line note the `<summary>`** and the attempt list its body. That gives one click target where the draft has two (a note plus a separate opener).
- **Suggested c2 wording:** "THE SYSTEM SHALL render the note as the summary of a native details element on the row's Status cell, closed by default, whose body lists the attempts; opening it SHALL NOT change the URL."
- **'Second try' and 'Resupply, attempt N' on the same row read clearly enough.** The resupply badge is a `pill tag` in How it got here (~9464); the try-note is muted prose in Status. Different columns and different forms keep the two apart. One addition: a `title` on the note, "Our check of this supply needed another try; this is not about the supplier's delivery", following the `ARRIVAL_FOLLOWS_FILING` tooltip precedent. Keith's wording stays as settled.
- **Peak-end.** The note stays muted, with no red, amber or alert styling, because the run ended clean. Add to c1: "styled as the existing muted re-check note, never in a status colour."

## 8. One duration format on the page, not three (REQ-TEST-416 c4, REQ-DASH-414 c1)
- Three formats are in play:
  - `fmtWaited()` (~2014) gives "45m" / "4h" / "3d".
  - 416 proposes '45s' / '3m 12s' / '2h 05m'.
  - 414's example says "45 min".
- `fmtWaited` rounds to minutes, so it can't be reused for runs under a minute. The new formatter should use the same unit letters, and 414's example should read "…the first timed out after 45m".
- Add '45m' to 416 c4's parity cases, and require that 414's note gets its duration from that one JS function.

## 9. Not-checked framing for the error-state context (REQ-DASH-415)
- **Locus.** A refused load points at the supplier. "Could not be checked" usually doesn't. Without saying so, a team leader may chase the supplier (the same reason REQ-DASH-148 made "Could not be loaded" outrank "overdue"). Suggested addition to c1: "…and SHALL say that nothing is yet known about this supply's data and that the next processing pass retries it (TA Q9), and that a person can reject it if it keeps failing."
- **Stability.** A one-off crash and a supply that crashes every pass shouldn't read the same. Suggested: "WHERE more than one attempt has failed, the words SHALL say how many ('could not be checked on 3 tries')."
- **Keep jargon down a level.** Show the outcome in words, the tool, and when, on the banner, row and queue item. Put the error type (e.g. a psycopg exception class) in the attempt list only. That is progressive disclosure for the data team leader, who finds raw tool jargon the main source of noise.
- **The withheld message is currently a dead end.** TA Q5 keeps it off the page, which is right. But the scoper's own report says nothing in `mothman` lists attempts or incomplete runs, so a maintainer who sees "QueryCanceled" can't find the message unless they watched the run happen. That is Q4.
- **Name the REQ-DASH-148 criteria so the critic can check each one.** Replace "exactly as REQ-DASH-148 does" in c3 with: "as REQ-DASH-148 criteria 2 (grey 'No data'), 11 (a supply-history row whatever the period), 14 (the agency-tier single reason row, '—' rows, no earlier supply's run date, arrival or sparkline) and 10 (one label everywhere)".
- **Two small consistency fixes.**
  - The blocker table's subtitle (`blockerHistoryRows`, ~9544) currently reads "supplies with no period yet, two files for one table, or a file that could not be loaded". Suggested: "…, a file that could not be loaded, or a supply that could not be checked".
  - State whether the supply appears in the blocker table, the cycle table, or both. If both, the cycle row shows a grey `pill("nodata")` (never red, never `notchecked`) and doesn't repeat the reason.

## 10. Navigation and URLs: nothing new needed
- **No new URL state.** No new route, path segment or query parameter. The attempt disclosure and the trend's table toggle are local view state and stay out of the URL, like the existing `#supply-history-toggle` and "View as table".
- **Deep links.** A cold-loaded `?asof=` link rebuilds the not-checked view from recorded data. Finding 2 is what makes that view honest.
- **Route-change a11y.** No `document.title`, focus or live-region work, since nothing route-changes.
- **One carry-over from §D of the SPA guide.** If the new "Could not be checked" queue item links to its dataset, it inherits whatever the failed-load item does. Use a real `<a href>` if that item is built fresh.
- **For the post-build critic:** confirm that opening the attempt list doesn't touch `location`.

## Questions for Keith (one batch; Q5 can wait for the architect's round if the call is full)

**Q1. Two settled answers disagree on what a not-checked supply is called.** F3 said "Not checked - …" with checks reading "No result". TA Q4 said "like a failed load", which on the page means a "Could not be checked"-style label with checks reading "No data". "Not checked" is also already a status that says it doesn't count toward status.
- (a) **Recommended.** "Could not be checked" leads everywhere and checks read "No data", exactly as a failed load does. One phrase, no clash.
- (b) Keep "Not checked - …" and "No result", and reword the page's existing Not-checked definition to cover both meanings.
- (c) "Could not be checked" as the label, keep "No result" for the checks.

**Q2. Where the run-time trend sits on a dataset page.**
- (a) **Recommended.** At the head of the Supply history section, in the column trend's existing frame. Below the "is my dataset OK" answer, and visible on blocked or not-checked pages.
- (b) Beside the existing "Columns failing and warning" chart, near the top. More visible, but competes with the verdict.
- (c) In Supply history, collapsed behind "Run times". Quietest, but a slow run is no longer visible at a glance (T3's "visually obvious").

**Q3. Does a re-check whose attempts all fail make a supply that already has a verdict "Could not be checked"?** REQ-PIPE-411 c3 currently says yes, for any run.
- (a) **Recommended.** Only a run with no earlier verdict does: an arrival run, or a reload's re-check. A failed re-check of a checked supply is a note on its row ("re-check on 14 Nov crashed; the next pass retries it"), and the supply keeps its verdict.
- (b) Any run, as drafted. A promoted green supply turns red "Could not be checked" whenever a re-check crashes.
- This is the architect's call as much as Keith's.

**Q4. Where can a maintainer read the error message the page withholds?**
- (a) **Recommended.** A `mothman` command lists a dataset's or supply's attempts with their messages (perhaps alongside `mothman supply failures`), and the page's attempt list names that command. This is new CLI scope, for delivery-cli-ux.
- (b) The page says "the full error is in the output of the run that failed". No new command, but a dead end after the fact.
- (c) Nothing: the type and tool are enough.

**Q5. Do failed attempts appear on the trend?** As drafted, only completed runs have a run time, so a run that grew and then timed out drops off the chart at the moment that matters most.
- (a) **Recommended.** Show a failed whole-supply attempt's measured time as a distinct hollow marker labelled in words ("timed out after 45m"), not joined to the line and not counted in any median.
- (b) Completed runs only, as drafted.

## Provisional parts of this note
- Finding 1's suggested wording depends on Q1.
- Findings 4 and 5's placement depend on Q2.
- Finding 6's second half depends on Q3.
- Finding 9's next-step sentence depends on Q4.
- Everything else stands without an answer.

## CLI UX (delivery-cli-ux)

CLI/TUI UX review of docs/drafts/timing-attempts-v1.yaml (REQ-TEST-416, plus how REQ-PIPE-410 and 411 reach the terminal). This is advice only and I edited no file. I treated TA Q1-Q9 as settled, including Q9's answer: a person can reject the supply, and the next pass retries it.

**Contexts (docs/hci-ux-psychology.md).** The draft mostly falls into **error/failure states**: the TOOL-ERROR line and 'Could not be checked'. The doc ranks that context highest, so it gets the harder look. I checked it against four things:
- non-punitive framing;
- attribution theory: say whose fault it is and whether it will happen again;
- clig.dev's "explain what broke and give a realistic next step";
- avoiding learned helplessness: a supply that fails every time must offer something a person can do.

The run-time line on every QA command is the secondary context, **routine daily use**. There I checked predictability: the same line, in the same place and the same format, every time, with no extra database reads in the run step. Peak-end applies to both, because the line printed when a run ends is the end of the session.

## Findings, most important first

**1. 'Could not be checked' never reaches the terminal's decision surfaces, but Q9 made "reject the supply" its response.**
- REQ-PIPE-411 adds the item to `qa_tools/common/outstanding.py` only. That is the dashboard's queue.
- The terminal's surfaces all read `qa_tools/common/filing_queue.py`: `mothman supply queue` (cli/supply.py:862, "THE SAME DEFINITION THE TICKET POLICY USES"), the Filing decisions TUI, and its period door.
- Rejecting a supply from the terminal goes through `filing_queue.operations_for`.
- So, as drafted, the dashboard item names a response that no terminal surface offers. outstanding.py's own docstring warns about exactly that: "a hold nobody can clear is indistinguishable from a bug".
- I believe such a supply lists today with "(no verdict recorded)" (`filing_queue.NO_VERDICT`), which says nothing about why. I did not confirm the exact state it lands in.
- The failed load is the pattern to copy, and it is complete:
  - `COULD_NOT_LOAD` and `could_not_load()` (filing_queue.py:86, 122);
  - kept out of `awaiting()`'s slot states (line 170);
  - `operations_for` offering REJECT only (line 744);
  - words in `_HOW_IT_READS` and `_LISTED_AS` (filing_tui.py:184, 204);
  - `_decide_on` printing the recorded reason plus `filing_queue.REPROCESS` (filing_tui.py:1397);
  - the door going straight to that supply's decision when it is alone in its period (filing_tui.py:2087);
  - `mothman supply failures`.
- Suggested criterion, on 411 or a new one:
  > "WHILE a supply's UNCHECKED blocker is open, THE SYSTEM SHALL list it in filing_queue as a state of its own beside COULD_NOT_LOAD, read 'could not be checked - <how the newest try ended>, <tool>, <error type>', offered REJECT alone through filing_queue.operations_for, with `mothman pipeline process` named as the other response (it retries). The state shall be shown by `mothman supply queue`, the Filing decisions queue and its period door exactly as a failed load is, and SHALL be resolved there by a rejection recorded through the decision log."
- For the architect: tickets read the same filing_queue definition, so this also decides ticket parity.

**2. One failure would be printed three times.** Today a failed tool step already reaches the person twice, and each copy carries the message twice:
- In `mothman <coll> qa`: `arrival_lifecycle.StageFailed`, rendered by `cli/lifecycle_report.stage_failure`: "STOPPED - X: the checks stage failed (QaRunFailure: ... dbt-core failed - CompilationError: <msg>. This run is INCOMPLETE ...)".
- In a pass: `processing_pass.fail_arrival` (line 417): "X: FAILED - QaRunFailure: <same>; it and every later ... are left for the next pass".
- REQ-TEST-416 adds a third copy from `run_one`. That is noise at the exact moment the error context says to be clearest.
- Suggested criterion:
  > "WHEN a QA attempt fails, THE SYSTEM SHALL say its outcome, tool, run time, error type and message once, in run_one's line; the stage-failure report (lifecycle_report.stage_failure, REQ-TEST-150 criterion 7) and the processing pass's failure line SHALL then name only the arrival, the stage and what follows, never the message again."
- In the same change, replace QaRunFailure's "This run is INCOMPLETE ... under an unfinished run" with the consequence and the next step. Something like: "Its supply shows as 'Could not be checked'. The next `mothman pipeline process` tries it again; if it fails the same way every time, reject the supply in Filing decisions or fix the cause."
- That covers attribution (whose fault, and whether it will recur) and gives the next step.
- REQ-TEST-150 criterion 7 needs amending, so list it as a dependency.

**3. "One line" cannot hold the message.**
- `ERROR_MESSAGE_LIMIT` is 1000 characters (qa_store.py:165), and dbt's messages are multi-line.
- Suggested replacement for 416 criteria 2 and 5:
  > "THE SYSTEM SHALL print one summary line beginning with the run id - '<run>: checked in 3m 12s' / '<run>: crashed in dbt-core after 1m 04s (CompilationError)' / '<run>: timed out after 45m 00s (LockNotAvailable)' / '<run>: stopped after 2m 10s' - then the stored message on the lines beneath, indented, so the summary line stays one line and greppable. WHILE NO_COLOR is set or stdout is not a terminal THE SYSTEM SHALL print the same words; no meaning SHALL be carried by colour alone."
- Why it starts with the run id: a parallel bootstrap runs its streams in spawned processes writing to one terminal (bootstrap.py:754-783), so their lines interleave.
- The current TTY criterion is met trivially, because `run_one` uses a bare `print()` and has no colour to strip.
- Ctrl-C gets its own line ("stopped after ..."), which also tells the person what their keypress did.

**4. The shared duration format: where it lives, its name, and its neighbours.**
- **Home.** The Python half must live in `qa_tools/common`, because `orchestrate` cannot import `cli/`. The natural place is `qa_tools/common/display_time.py`, which already holds the shared instant formatter `format_instant`.
- **Name.** Give it a name distinct from `schedule.format_duration`. That one deliberately renders the authored config form ("14d", "4h"; post-build-review #27) and should stay as it is.
- **Parity test.** Reuse the REQ-QAC-047 pattern: a repo-root `duration-cases.json`, read by a pytest like `tests/test_status_parity.py` and by a vitest. Make the criterion name rounding edge cases so the two halves cannot drift:
  - 0 and 0.4s (say "under 1s", not "0s", which reads as nothing ran);
  - 59.6s (must become "1m 00s", not "60s");
  - 3599.5s;
  - over 24h (hours, not days).
- **Conflict with TA Q8's words.** TA Q8's settled sentence reads "after 45 min", but 416 criterion 4's example style gives "45m 00s" or "45m". REQ-DASH-414's note has to use the shared format, or the shared format has to be "45 min". The dashboard UX reviewer should pick one with you; terminal and page must match.
- **Neighbours.** Other durations already sit on the same screens in different formats (question 3 below):
  - the bootstrap's "Took Birth Registrations 330s" (bootstrap.py:308);
  - `bulk_recheck_tui._minutes` ("3m");
  - Rich's `TimeElapsedColumn` "0:00:13" in `chain_progress`;
  - the page's own `fmtWaited` ("4m"/"3h"/"2d", template line 2014).

**5. Use the page's words in the terminal.**
- **Try, not attempt.** Apply TA Q8's 'try' wording to 416's retried line: "<run>: checked in 3m 12s, on the second try - the first crashed in dbt-core after 1m 04s".
- **Found-dead tries.** A try found dead must say "the first stopped without a record of its end, its run time unknown", and never show a time. This mirrors REQ-PIPE-409 criterion 3. 416 criterion 1 doesn't cover it yet.
- **Existing "attempt" wording.** `mothman supply queue` already says "- last attempt: <failure>" for a failed owed re-check (cli/supply.py:958). Reword it to "last try" in the same change, or the terminal ends up with two words for one thing.
- **Tool names.** `_run_step` names tools "dbt-core" and "Soda Core", but REQ-DASH-415's example says "a tool failed (dbt)". Pick one string per tool (the run step's name is the source) for the database, the page and the terminal.

**6. The interactive wizard.**
- 416 criterion 3 (run time in `report_recorded`'s "Recorded" panel) is right, and it improves the end-of-run moment.
- The failure path has no matching criterion. Suggested:
  > "WHEN a try fails in the interactive qa wizard, THE SYSTEM SHALL show the outcome line and the next step, then return to the menu (never a bare exit), with '<- Back' available as everywhere else."
- I did not verify what the wizard does today after a StageFailed raises SystemExit(2) through `_MothmanGroup`. delivery-cli-ux-critic should drive it.

**7. Smaller points.**
- **A token reused.** `processing_pass.UNCHECKED` already means "owed the whole lifecycle", which includes "never tried". The new blocker kind reusing the token means something narrower. Suggest naming it after `COULD_NOT_LOAD`, e.g. `COULD_NOT_CHECK`.
- **For the architect.** REQ-PIPE-411 criterion 3 could also catch a crashed owed re-check, which `supply queue` already lists as owed with its last failure. That would put one supply in two terminal places.
- **Residual privacy risk, not a re-ask.** Under Q5, full messages also land in GitHub Actions logs on a public repo during CI bootstraps. That is harmless while the data is synthetic; it is worth knowing when the repo goes private or the data becomes real.

**What delivery-cli-ux-critic can check by driving the built command (scripts/dev/tui_drive.py):**
- one summary line per run, beginning with the run id;
- the message printed exactly once on a forced dbt failure, in both `cp qa` and `pipeline process`;
- the same words with NO_COLOR=1 and through a pipe;
- the run time in the Recorded panel;
- Ctrl-C prints "stopped after";
- the not-checked supply in `supply queue` and the Filing decisions door offers reject only, plus the reprocess hint;
- the duration strings match `duration-cases.json`.

## On "slow" in the terminal
I agree with the scoper's call: no. It is question 1 below, because T3 didn't mention the CLI. Computing the median in the run step would be a second copy of REQ-PIPE-412's one rule ("one rule in one place"). It would also add a recorded-history read to every run, and it can't be judged the same way mid-replay.

## Questions for Keith (one batch)

1. **Should the terminal ever say "slow"?**
   - (a) No. The terminal prints the run time and the dashboard judges it.
   - (b) The run step computes it from recorded history: a second copy of the rule, plus a read on every run.
   - (c) Only read-only commands repeat the build's mark.
   - **Recommend (a).**
2. **Beyond the queue items in finding 1 (required by Q9), how much of the try history should the terminal show?**
   - (a) `mothman supply failures` lists "could not be checked" beside "could not be loaded", and `mothman supply history --dataset` gains a run-time column.
   - (b) (a) plus a new `mothman supply tries --dataset X`, the terminal twin of REQ-DASH-414's list.
   - (c) Neither; history stays on the dashboard.
   - **Recommend (a).** It extends the two commands a person would already reach for. (b) adds a command to remember for a rare case.
3. **Which existing terminal durations move to the shared format?**
   - (a) Run times only.
   - (b) Also the bootstrap's "Took ... 330s" line and the bulk re-check's elapsed/left, which sit on the same screens as the new line.
   - (c) Every duration, including `mothman check`'s commit line and Rich's progress timer.
   - **Recommend (b).** (c) touches lines that are fine as they are. Claim windows keep their authored form in every option.
4. **What does the shared format look like (the conflict in finding 4)?**
   - (a) Compact: "45s", "3m 12s", "2h 05m", with TA Q8's sentence reading "after 45m 00s".
   - (b) Words: "45 sec", "3 min 12 sec", "2 hr 5 min", matching TA Q8's "45 min" as written.
   - **Recommend (a).** It is narrower in an 80-column queue line and closer to the page's existing "4m/3h".

Everything else above is advice that doesn't depend on these answers. Findings 1 and 2 hold whichever way they go.

Key files:
- /home/user/data-poc/docs/drafts/timing-attempts-v1.yaml
- /home/user/data-poc/qa_tools/tools/orchestrate.py
- /home/user/data-poc/qa_tools/common/filing_queue.py
- /home/user/data-poc/qa_tools/common/processing_pass.py
- /home/user/data-poc/qa_tools/common/display_time.py
- /home/user/data-poc/cli/lifecycle_report.py
- /home/user/data-poc/cli/filing_tui.py
- /home/user/data-poc/cli/supply.py
- /home/user/data-poc/cli/common.py
- /home/user/data-poc/tests/test_status_parity.py

## Architect (delivery-architect)

## Architect review: timing-attempts v1 (REQ-PIPE-409 to REQ-TEST-416), checked against HEAD

Advisory only. I edited no file. Settled answers (T1-T3, F1-F3, TA Q1-Q9, with Q9 = (a)) are treated as given.

**Verdict:** the draft's direction is sound and fits the existing structure. There are **6 blocking findings**. The biggest is that a feature already reads failed attempts, and the draft doesn't know about it: REQ-DASH-272 c21 in `pipeline/package_gating.py`. Two others are about which failed runs count. None of them needs a new command group or new design work.

### Blocking findings

**B1. REQ-PIPE-411 c3/c5 counts too many runs as "not checked".** "each run (qa.run, not qa.run_visible, trials excluded)" also picks up:
- **Runs inside a gate application.** When a gate's re-check crashes, `gate.py:570-576` abandons the application and queues a retry. REQ-PIPE-267 c12 (`qa_store.py:1486-1504`) says such a run "counts for nothing ... toward no status, page, count, ticket". A red blocker plus a queue item breaks that rule.
- **Readers-only runs.** They are not about the supply (`supply_current_run` leaves them out, `qa_store.py:1525`).
- **Full re-runs triggered by a decision.** Their supply already has a verdict from its arrival run. A blocker opened at receipt would paint its whole history red, back to receipt, in the as-of view.
- **Fix:** limit c3/c5 to runs that are `scope = 'arrival'`, `NOT trial`, `gate_application IS NULL` and have a `supply_id`. What a failed full re-run shows is question QA below.

**B2. REQ-PIPE-411 c3's "and that has no completed attempt" lets a stale Pass through.**
- Every `open_run` calls `reopen_run` (`qa_results_writer.py:784` → `qa_store.py:2185-2193`), which sets `completed_at` back to NULL.
- So a run that completed, was reopened, and then failed is hidden from `run_visible` and also excluded by c3. It disappears, and the supply falls back to an older run's verdict. That is the stale Pass REQ-DASH-415 exists to prevent.
- **Fix:** define the not-checked condition as `completed_at IS NULL` and the newest attempt (by run_seq) not COMPLETED, whether or not it has ended.
- Align REQ-PIPE-409 c7 with this: a run's run time is its newest attempt's `elapsed_seconds` where that attempt COMPLETED, otherwise none. An older completed attempt doesn't count.

**B3. REQ-PIPE-410 c1 ("the chained cause") picks the wrong tool when two tools fail.**
- When dbt and a foreground tool both fail, `parallel_orchestrate.beside` (`parallel_orchestrate.py:147-151`) does `raise first from None`.
- That overwrites dbt's `QaRunFailure.__cause__` with None and leaves `__context__` pointing at the *other* tool's `QaRunFailure`.
- Both c1's cause and `_outcome`'s timeout walk (`qa_results_writer.py:906-911`) would then report the other tool's exception type and SQLSTATE.
- **Fix:** extend c2 so `QaRunFailure` carries `tool` *and* `cause` as fields, set in `_run_step` (`orchestrate.py:57-67`). `_outcome` should read the fields, not the chain. Add a test where two tools fail and dbt's error is a timeout.

**B4. The draft overlaps and contradicts REQ-DASH-272 c21, which is built (`pipeline/package_gating.py`).**
- That module's lines 1-55 and 139-146 already read `qa.run_attempt` for attempts that didn't complete.
- For an arrival whose run isn't recorded, it shows "Being checked with its delivery ... Nothing needs deciding yet" with "no pill and no check results". When a package-mate's run stopped, it adds "'<dataset>'s run stopped; the next processing pass re-runs it." (lines 246-268).
- REQ-DASH-415 would show a red "Could not be checked" plus a blocking "needs a person" item for the same supply on the same date. That is a direct contradiction.
- It also corrects the reviewer flag. REQ-PIPE-411 is **not** the first build-side read of runs outside `run_visible`: `package_gating.py:132-176` and `pipeline/red_promoted.py:35-59` already read `qa.run` and `qa.run_attempt` directly.
- **Fix:** add a criterion saying which wording wins, and amend REQ-DASH-272's wording in the same change (question QB). Take attempts from one shared reader rather than a second query.

**B5. Attempt lists grow without limit for a supply that always crashes.**
- The processing pass retries every UNCHECKED arrival on every pass with no back-off (`processing_pass.py:204-210`, and nothing else stops it).
- With Q9 = (a), a run that always crashes stays stuck until someone rejects it, adding one attempt per pass. REQ-PIPE-411 c2 emits "every attempt" into the dashboard data, and REQ-DASH-414/415 list them all.
- REQ-PIPE-409's STORAGE NFR ("of the order of ten thousand rows a year") doesn't allow for this either.
- **Fix:** bound what is emitted (question QC), and correct the NFR to cover retries.

**B6. A built requirement's wording changes without saying so.**
- REQ-PIPE-279 c6 (`requirements.yaml:40219-40229`) says "a tool's own timeout arriving as QaRunFailure ... records CRASHED", and its outcome list has no TOOL-ERROR.
- REQ-PIPE-410 changes both. Under the post-build sign-off rule that is a change to a `requirements.yaml` claim.
- **Fix:** add a REQ-PIPE-410 criterion that amends REQ-PIPE-279 c6 in the same change, with the exact appended wording, so Keith signs it by signing REQ-PIPE-410. This is the pattern REQ-PIPE-382 c14 uses.

### Non-blocking findings

**N1. `time.monotonic()` against REQ-PIPE-382 and REQ-TEST-384: no clash.**
- REQ-TEST-384 (separation-v6 l.268-270) only fails imports *between sides*. The standard-library `time` module is in no side and isn't a file the gate reads.
- REQ-PIPE-382 c1/c2 (l.173-174) cover recorded instants and "today", not durations.
- Real pipeline modules already do this: `processing_pass.py:366-377`, `recheck.py:538-548`, and `replay_clock.py:61` itself.
- Guidance for the build:
  - Read the counter in `qa_results_writer.Attempt` and pass the elapsed value into `qa_store.end_attempt`. `qa_store` is on REQ-PIPE-382's list of 17 modules, so keep it a pure recorder.
  - Have REQ-PIPE-409 require one sentence in `asset_time`'s docstring (the single place REQ-PIPE-382's MAINTAINABILITY note states the time rule): durations come from `time.monotonic()`, never the clock. Otherwise REQ-PIPE-382's sweep may "fix" the read into the clock seam.
  - Record as a decision that on Linux the monotonic clock excludes suspend, so a container that sleeps mid-run under-reports. That suits "how long the work took".

**N2.** REQ-PIPE-411 c1 cites "REQ-PIPE-409 criterion 6" for the run time. It should be **criterion 7**; c6 is the one-clock stamping. The numbers shifted when TA Q1's criterion was inserted.

**N3.** Make REQ-PIPE-409 c8 two-way: `(ended_at IS NULL) = (elapsed IS NULL)`. Store **integer milliseconds** (e.g. `elapsed_ms bigint`). Then REQ-PIPE-412's "exactly twice is not slow" test is exact; Decimal or float values going out through JSON make that boundary flaky.

**N4.** REQ-PIPE-409 c10's "within a tolerance of a known real duration" will flake under xdist. Inject the counter (monkeypatch the time source `Attempt` uses) and assert exact values. If a real-sleep test is wanted, give it a lower bound only.

**N5. REQ-PIPE-411 c5's wording and lifecycle.**
- It says "record a dataset blocker", but blockers are *derived* when read (`dataset_blockers.py:370-413`, `all_blockers` 433-438). Reword to "derive".
- Define when it closes if the supply is superseded or re-filed before a retry completes; otherwise it stays red for good. Mirror `_failed_loads`.

**N6.** The new kind's name, UNCHECKED, collides with `processing_pass.UNCHECKED` (l.62), which means "owed the whole lifecycle". Call it `NOT_CHECKED` / "not-checked".

**N7. Not-checked runs have no rank.**
- `run_facts` ranks only visible runs (`qa_results_reader.py:368-406`), so a not-checked run has nothing to order it by. REQ-DASH-415 c1 ("shown as the dataset's own") needs that.
- REQ-PIPE-411 should say they join the same dense rank from their newest run_seq. That renumbers later ranks, which is still deterministic, but it should be stated.
- Put the new reader in `qa_results_reader` beside `run_facts`/`incomplete_runs` (l.234), and have `package_gating` share it.

**N8. A Lambda killed at its limit.**
- Lambda's limit is 15 minutes (`aws/cdk/data_pipeline_stack.py:113`). The `deadline` budget only stops the pass taking *new* arrivals, and a hard kill isn't guaranteed to deliver any signal.
- So the outcome stays NULL until the next attempt of that run key opens. The advisory lock can also outlive the dead sandbox until TCP keepalive notices (#262 R3), so the next pass may hit `AttemptInProgress`.
- The draft handles this honestly: no end, no run time, "has not finished".
- But the runs closest to the limit, which are exactly what #120 wanted to see, never get a run time, so the trend can't show them. Record that as a decision. Having the pass stop itself just before the limit (INTERRUPTED with an end and an elapsed value) belongs to #124/AWS.
- REQ-DASH-414 c1's note needs wording for an earlier try with no recorded end ("the first did not finish"), because "after <duration>" can't be filled in.

**N9. REQ-PIPE-412's cost at about 30 collections is trivial.** A sliding window of 20 is O(runs × 20), milliseconds even for daily datasets with thousands of runs. For page weight, emit median and count only for runs marked slow and for the newest run; REQ-DASH-413's hover and text alternative need nothing else.

**N10.** REQ-PIPE-411 c10 should refuse on the *key* being absent, as the `run_facts` check does (`build_dashboard_data.py:1121`), not on null values, which are legitimate.

**N11. Schema bump to version 51 (`qa_store.py:203` is at 50).**
- Edit the `CREATE TABLE` in place (`IF NOT EXISTS` never alters an existing table) and *replace* the CHECK at l.313. Older databases are refused (l.1930-1950), so that's consistent.
- Expect `tests/test_check_read_and_attempts.py:501` (which asserts `error_type == "QaRunFailure"`) to change.
- Budget a cache-miss bootstrap. This is unavoidable, since any change under `qa_tools/**` misses the cache anyway.

**N12. REQ-TEST-416.**
- Have `Attempt.end` return the outcome and elapsed time so `run_one` (`orchestrate.py:84-107`) prints without a re-read. "Earlier attempts" costs one `attempts_of` query, which is fine.
- The line is printed from `qa_tools/tools/` rather than `cli/`. TEST is acceptable as the code, but the scoper may prefer PIPE.

**On the receipt-opened blocker:** I agree with it **for arrival runs**. It matches REFUSED and #118 D-B: the supply has had no verdict since it arrived, and the attempt's end time depends on when a pass happened to run, which D-B rejected. The cost to state in the decision is that the as-of red window includes the normal wait between receipt and the check. It is wrong for full re-runs (see B1 and QA).

### Duplication / overlap
- **Real overlap:** `pipeline/package_gating.py` (REQ-DASH-272 c21), covered in B4.
- **Intended extension points, not duplication:** `dataset_blockers.py` (beside REFUSED) and `outstanding.py` (`_from_loads`, l.472-507). The CLI's `cli/supply.py:380` lists only failed loads, so decide whether `mothman` lists not-checked supplies too (CLI UX reviewer).
- **One reader:** `qa_store.incomplete_runs`/`attempts_of` and `qa_results_reader.incomplete_runs` already exist. Build the build-side attempt reader beside them, not inside `results_history` or `dataset_blockers`.

### Structural fit, blast radius, security
- **Fit:** no new command group. Everything is in existing modules.
- **Components:** QAC (orchestrate, writer), PIPE (qa_store, reader, results_history, build_dashboard_data, dataset_blockers, outstanding, package_gating), DASH (template), TEST (cli report panel, tests). Four components, but one data path, so a batch scoped like this is the right treatment rather than a cross-component `plans/wider.md` item.
- **Security:** no new access. `qa.run_attempt` is covered by the publisher's existing grant (`qa_store.py:2013-2016`). TA Q5 keeps error messages off the page. Make sure the attempt fields are emitted from an explicit list that leaves out `error_message`, and test the built HTML for it.

### Code-quality expectations (for delivery-critic)
1. One counter read at each end of an attempt, both in `Attempt`, with a comment saying why it's monotonic and not the clock. `qa_store` stays a recorder.
2. The outcome is decided only in `_outcome`, from `QaRunFailure`'s fields. No reading the chain for the tool and no parsing text, with a test where two tools fail.
3. One reader of attempts for the build, used by `results_history`, `dataset_blockers` and `package_gating`, with a docstring that names the condition from B1/B2 exactly.
4. The slow rule is one pure function (`runs → marks`) with the window and minimum as named constants citing TA Q3, and no DB access.
5. Emitted attempt fields come from an explicit list that leaves out `error_message`, with a comment citing TA Q5 (the one justified exception to spread-then-override).
6. The Python and JS duration formatters are kept equal by one shared case list.
7. Every new criterion has a test seen failing first. Timing tests inject the counter.

### Sketch
```
open_run → Attempt(t0=monotonic) ── tools (_run_step sets QaRunFailure.tool/.cause)
   └ end(): outcome=_outcome(exc); elapsed_ms=monotonic-t0 → qa_store.end_attempt(…, elapsed_ms, tool)
build: qa_results_reader.attempts_for(collection)  ← qa.run ⋈ qa.run_attempt
   ├ results_history → run_time per run, attempts (no message), not_checked arrivals (B1/B2)
   ├ dataset_blockers NOT_CHECKED (receipt → completing attempt | rejection) → outstanding item
   ├ package_gating (shares the reader; precedence per QB)
   └ build_dashboard_data → slow marks (pure fn) → template renders
```

### Build order
1. REQ-PIPE-410 + REQ-PIPE-409 together: one schema bump, the `QaRunFailure` fields, the B3 fix, and B6's amendment to REQ-PIPE-279. Preferably after separation-v6's REQ-PIPE-382, so the "replay clock advances mid-attempt" test uses REQ-PIPE-382's install call rather than `replay_clock` directly, which would need rewriting. Nothing here adds an import edge, so either order is safe.
2. REQ-TEST-416. It needs only steps 1's two requirements and gives the maintainer the data while the rest is built.
3. REQ-PIPE-411, including the shared reader and the REQ-DASH-272 reconciliation.
4. REQ-PIPE-412.
5. REQ-DASH-413, REQ-DASH-414, REQ-DASH-415, after the dashboard UX review.

### Questions for Keith (one batch, relay-ready)

**QA. Which failed runs make a supply read "Could not be checked"?** (B1 is otherwise provisional on this.)
- (a) Only a supply's **arrival** run. A failed re-check after a decision leaves the supply's earlier verdict standing, with the existing "re-check owed" display and its tries listed. Gate re-checks and readers-only runs never count. This keeps REQ-PIPE-267 c12 intact and the receipt start honest.
- (b) Arrival runs **and** decision-caused full re-checks. A re-check's window opens when its decision took effect, not at receipt. This catches a correction that can't be checked, at the cost of a second opening rule.
- **Recommend (a).**

**QB. A failed run inside a multi-file delivery** currently reads "Being checked with its delivery ... Nothing needs deciding yet" plus "'X's run stopped; the next pass re-runs it" (REQ-DASH-272, built).
- (a) The failed supply's own row and its dataset show the new "Not checked" red with its queue item. Its package-mates keep "X's run stopped", but lose "Nothing needs deciding yet" while a mate can't be checked. This amends REQ-DASH-272's wording.
- (b) Inside an unfinished package the failure stays in REQ-DASH-272's neutral form, with no red and no item, until the package is otherwise complete. No amendment, but a package with a mate that always crashes never goes red.
- **Recommend (a).**

**QC. A supply that crashes on every pass gains one try per pass** with no limit.
- (a) Emit and list every try: complete, but unbounded page weight.
- (b) Emit the count, the first try and the newest 5, with "and N more". The full list stays in `mothman` and the database. Always bounded.
- (c) Collapse back-to-back tries that ended the same way with the same tool and error type into one line ("crashed in dbt (KeyError) ×37, from X to Y"). Compact, but unbounded if the errors alternate.
- **Recommend (b).**

**QD. The schema bump: regenerate or migrate?** The parked note `docs/drafts/schema-migrations/README.md` records your 2026-10-14 call that every bump from version 41 ships a migration. That was never applied (versions 41-50 all regenerated), and the code still refuses older databases.
- (a) Regenerate, as drafted. It matches the code and every signed requirement since, and leaves the migration work for when it's scoped.
- (b) Also ship a hand-written additive migration (new nullable columns; the new CHECKs added `NOT VALID` so older TIMED-OUT rows with no error type pass) as a first worked example. That pre-empts the Alembic-vs-Django choice and is close to the home-grown runner you rejected.
- **Recommend (a).**

Decided by me, not asked: everything under "Non-blocking". Provisional on the answers: B1's scope wording (QA), B4's precedence (QB), and B5's limit (QC).

### Files
- /home/user/data-poc/docs/drafts/timing-attempts-v1.yaml
- /home/user/data-poc/pipeline/package_gating.py
- /home/user/data-poc/qa_tools/common/parallel_orchestrate.py
- /home/user/data-poc/qa_tools/common/qa_results_writer.py
- /home/user/data-poc/qa_tools/common/qa_store.py
- /home/user/data-poc/qa_tools/common/qa_results_reader.py
- /home/user/data-poc/qa_tools/common/dataset_blockers.py
- /home/user/data-poc/qa_tools/common/outstanding.py
- /home/user/data-poc/qa_tools/tools/orchestrate.py
- /home/user/data-poc/qa_tools/common/gate.py
- /home/user/data-poc/docs/drafts/schema-migrations/README.md
