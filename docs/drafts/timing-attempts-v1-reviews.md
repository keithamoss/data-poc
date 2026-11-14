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
