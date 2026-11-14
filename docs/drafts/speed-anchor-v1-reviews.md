# Speed + rolling anchor v1 - the pre-build reviews, 2026-11-14

## Dashboard UX (delivery-dashboard-ux)

## delivery-dashboard-ux review: speed-anchor v1 (mainly REQ-DASH-407)

I edited no files. I read the draft, the scoper's report, Keith's settled answers (R1-R5, SA Q1-Q5, Dash C, the v6 answers), `docs/hci-ux-psychology.md`, `docs/spa-best-practices.md` and the template. I have not reopened any settled question.

**Context (per `docs/hci-ux-psychology.md`).** This is mostly an **error/failure-state** moment: a quiet or late current period that is really caused by the demo's age, not by a supplier. **First-time use** comes second, because Keith puts the demo in front of people seeing it cold.

**Principles I checked against:**
- **Attribution theory (locus):** the page has to put the cause on the demo, not on a supplier.
- **Non-punitive framing.**
- **Visibility of system status.**
- **Paradox of the Active User:** a line nobody scrolls to does nothing.
- **Consistency:** reuse what's already there.

The weighting (error states first) is why point 1 gets the hardest look.

### 1. Where the date appears: the footer alone is the least visible place for it (question Q1)
- **Where the reader actually gets confused:** at the top of the page, on the overview and the dataset rows, where a late or quiet current period first shows. The footer (template lines 1120-1124) sits below every collection, and at around 30 collections almost nobody scrolls that far.
- **How often this happens:** the default bootstrap uses the fixed anchor (REQ-GEN-405 c4, without `--roll-anchor`), and the default as-of date is today on the asset's clock (`defaultInPlaceOn()`, line 4075, settled 2026-09-16). So the normal demo today shows about seven weeks of overdue daily slots after 25 Sep, and this one line is the only explanation on the page.
- **Patterns that already exist:**
  - The masthead build stamp, `renderBuildStamp()` (lines 13131-13179). Its own comment says it answers "how current is this, and is it mine", and it adds facts to one line with ` · ` rather than adding lines (REQ-PIPE-092 c7/c17).
  - The as-of panel (`#in-place-on-panel-body`, lines 1185-1207), which is where a reader goes when the date itself is the question.
- **Why this is open to change:** the scoper marked the footer as provisional ("Keith or delivery-dashboard-ux may change it"). Dash C settled where the existing synthetic sentence goes, not where a new fact goes.

### 2. The wording has to give the reason, not just a date
"Synthetic data generated up to <date>" has two gaps. It doesn't say whether that day is included, and it leaves the reader to work out why a later period is empty. I suggest replacing REQ-DASH-407 c1 with:

> "WHERE the asset declares `synthetic: true`, THE SYSTEM SHALL show in the footer, as its own sentence immediately after the synthetic wording (REQ-PIPE-385 c12) and before the codename line, using the footer's existing type and no new class: 'The synthetic supplies on this page were generated up to and including <date>; a period after that date has no supply.' <date> is formatted by `fmtDay()` as a plain date on the asset's clock, never an instant. The text SHALL be identical whether the date is today or months ago."

The last sentence keeps it a statement of fact rather than the staleness warning R3 rejected.

For c3 (no anchor recorded), I suggest a full sentence with no command in it, since page readers are not the people who regenerate the data: "The date this synthetic data was generated up to was not recorded." For consistency, the date should go in as a field on the existing `BUILD_PROVENANCE` embed (line 2626) rather than a new top-level const.

### 3. Keep the as-of picker's range and default as they are, and say so in a criterion
`coveredDateRange()` (lines 3176-3191) caps the picker at today, and the default is today. A builder could "helpfully" cap both at the recorded anchor instead. That would make `renderInPlaceOnRangeNotice()` (line 12997) show its banner on every load of an aged demo, which is exactly the staleness warning R3 rejected. Suggested new REQ-DASH-407 criterion:

> "THE SYSTEM SHALL leave the as-of date's default (today on the asset's clock) and the picker's range (REQ-DASH-054 c8 as amended by REQ-DASH-326) unchanged by the recorded anchor, so that no notice appears on the default view of a synthetic asset because of the anchor."

Also worth `delivery-dashboard-ux-critic` checking: SA Q5 often sets a rolled anchor to yesterday. So a demo built later on the day it was rolled will show today's daily slot with no supply. The new sentence is what explains that, so the critic should look at a same-day rolled build.

### 4. Saved scenario links break after a roll (deep links, `docs/spa-best-practices.md` A and C; question Q2)
- **What the link holds:** `scenarioChipHref()` (line 11999) writes both `?in-place-on=<date>` and `&scenario=<id>`.
- **What a cold load does:** `SCENARIO_ON_LOAD` (lines 13197-13209) uses the date in the URL (`to: CURRENT_IN_PLACE_ON`).
- **Why that breaks:** REQ-GEN-406 moves the daily scenarios' dates with the anchor. A scenario link copied before a roll then opens on the old date and says "Viewing <old date> for TS-62". `markScenarioSubject()` finds nothing to mark and gives up silently (line 12024). That is a silent dead end, which is the worst kind in the error-state context.
- **Why the scenario's date should win:** per guide A, the scenario id says which thing the reader wants, and its date follows from it.
- **Suggested criterion (REQ-DASH-407 or REQ-GEN-406):** "WHEN a page is opened cold with `?scenario=<id>` naming a known scenario whose current date differs from the link's `?in-place-on=`, THE SYSTEM SHALL show the scenario's current date and rewrite the address with `replaceState`; with a test that opens a link carrying a stale date."

### 5. Configuration dates written as offsets (REQ-GEN-406)
c3 already says the build reads resolved dates. Add a criterion the post-build critic can check on the page:

> "THE SYSTEM SHALL show every configuration date on the built page (calendar versions, correction dates in the 'decisions made since then' note, setting eras) as an absolute date formatted by `fmtDay()`, and no text on the page SHALL name an offset or the anchor."

### 6. Things I checked that need no change
- **Route-change accessibility:** this adds no new view or route, so there are no `document.title`, focus or `aria-live` changes to make.
- **Real `<a href>` links:** the change adds no new navigation elements, so none are needed.
- **Snapshots and printouts:** keeping the date in the footer means past snapshots and printed pages carry it automatically. That favours the footer as the base in every option below.
- **The CLI lines** in REQ-DASH-407 c4 (the bootstrap output and `mothman env current`) are for `delivery-cli-ux`, not me.

### For `delivery-dashboard-ux-critic`
Check the default view of a non-rolled demo and of a same-day rolled demo. Confirm the sentence explains the empty periods with no banner. Confirm the picker's maximum is still today. Cold-load an old scenario link after a roll.

### Questions for Keith (one batch)
**Q1. Where does "generated up to" appear?** (REQ-DASH-407)
- (a) The footer only, as drafted. Fits Dash C most strictly, but it's below the fold, which is where the confusion is least likely to be cleared up.
- (b) The footer, plus one quiet line in the as-of panel under the date picker ("Synthetic supplies run up to and including <date>"). It meets the reader exactly when they're asking about dates, and puts no synthetic text in the page's main chrome. **Recommended.**
- (c) The footer, plus "· synthetic data to <date>" added to the masthead build stamp. Seen on first load and follows REQ-PIPE-092's pattern, but it adds synthetic text to the always-visible masthead, which stretches Dash C's "footer only" further.

**Q2. A scenario link saved before a roll** (REQ-DASH-407 or REQ-GEN-406)
- (a) The scenario's current date wins on a cold load, and the address is quietly rewritten. The link always lands where it should. **Recommended.**
- (b) The link's date wins, plus a one-line note "TS-62 is now on <date>" with a link to it. More transparent, but it's one more thing to read.
- (c) No change. Links copied before a roll open on the old date and the scenario mark is missing. Acceptable only if nobody shares scenario links outside a single session.

Everything in points 2, 3 and 5 stands whichever way Q1 and Q2 are answered.

**Files:** `/home/user/data-poc/docs/drafts/speed-anchor-v1.yaml`, `/home/user/data-poc/dashboard/qa-reporting-dashboard.template.html`, `/home/user/data-poc/docs/drafts/decisions-2026-11-01.md`

## CLI UX (delivery-cli-ux)

## delivery-cli-ux note: speed-anchor v1 (REQ-PIPE-397 to REQ-GEN-408, REQ-PIPE-430 to 432)

This is advisory only. I edited nothing. I read the draft, the scoper's report, Keith's answers (S1-S4, R1-R5, SA Q1-Q5 and the amendments), `docs/hci-ux-psychology.md`, the personas, and the source of `cli/app.py`, `cli/env.py`, `cli/pipeline.py`, `cli/common.py`, `cli/lifecycle_report.py`, `qa_tools/common/bootstrap.py` and `qa_tools/common/synthetic_reset.py`. I don't re-ask anything Keith has settled.

**Which context this falls into.** Mostly **error/failure states**: the test refusal on a rolled database, the future-anchor and calendar-runs-out refusals, the worker failure, the digest mismatch, and a reset that now deletes more. Second is **configuration/setup**: the flags and the destructive reset. Because the doc ranks error states first, those findings lead below. The principles I checked against:
- Error states: non-punitive framing, attribution (say who caused it and whether it will recur), avoiding learned helplessness, clig.dev's "explain what broke and give a realistic next step".
- Configuration: error prevention (an honest confirmation before a destructive act), recognition over recall (don't make someone remember a flag).
- Peak-end: the bootstrap's closing lines after a run of about two hours.

`delivery-cli-ux-critic` should verify against those.

**Discoverability and tier are fine.** No new commands. `pipeline` and `env` stay Tier 2 (blue). Keeping `--roll-anchor`/`--anchor` flag-only is right: the TUI's "Set up this environment" is the newcomer path, and the fixed anchor is the correct smart default for a newcomer whose local gate must pass. The one thing a person has to remember is `--roll-anchor`, so the fix belongs where they will be standing when they need it (finding 2).

---

### Findings, most important first

**1. The reset's typed confirmation stops being honest once files go too (REQ-GEN-408).**
- The phrase is `delete all QA history for <asset>` (`synthetic_reset.confirmation_phrase`, line 63).
- REQ-PIPE-144 (requirements.yaml line 31117) requires "a typed confirmation naming what it will delete". A phrase that names only QA history, typed to delete the delivery and receipt trees as well, arguably breaks that built criterion. The phrase change is Q1 below.
- Hand-filed folders. A synthetic asset's delivery tree can hold folders the generator did not write: `handfiled-*` from `mothman <coll> qa --commit`, which is the 2026-09-28 incident 408's own decision cites. Those cannot be regenerated, and R4 rejected archiving. The confirmation should name them separately (Q2).
- The anchor. A reset is the last moment the deleted history's anchor can be read, and REQ-GEN-404's whole reproducibility promise is "give that date back". So say it.
- The command's `--help` docstring and its closing line ("Deleted N schema(s)") both describe the database only.

Suggested criteria for REQ-GEN-408:
- "BEFORE asking for the phrase, THE SYSTEM SHALL list, beside the row and schema counts, the delivery tree, the receipt tree and the bookkeeping file by path relative to the repository, each with its file count; SHALL list separately, under 'not written by the generator - these cannot be regenerated', any delivery folder the generator's bookkeeping does not list; and SHALL name the anchor recorded for the history being deleted, with the command that rebuilds it (`mothman pipeline bootstrap --anchor <date>`), or say 'no anchor recorded'."
- "WHEN the reset finishes, THE SYSTEM SHALL say what it deleted in each of the three parts (schemas, files, bookkeeping); IF any part failed, THEN it SHALL name what remains, say that nothing else was skipped, and say that running `mothman env reset-synthetic` again finishes it."
- "THE SYSTEM SHALL make reset-synthetic's `--help` name the files it deletes as well as the history."

**2. `--roll-anchor` on a database that already holds data silently does nothing (REQ-GEN-405).**
- Today, `bootstrap()` returns "N staged table(s) already present - nothing to do", in yellow, with exit 0 (`bootstrap.py` lines 225-230).
- So a person who typed `--roll-anchor` but forgot the reset gets a green-ish no-op after asking for something explicit. That is the dead end the "never a dead end" convention exists to prevent.

Suggested criterion: "IF `--roll-anchor` or `--anchor` is given and the database already holds staged tables or QA history, THEN THE SYSTEM SHALL refuse with a non-zero exit, naming the anchor recorded for the history that is there (or 'not recorded') and the command that replaces it (`mothman env reset-synthetic`, then this command again), before anything is generated."

**3. The test refusal on a rolled database (REQ-GEN-405 c6): one message, honest about cause, and the remedy must actually work.**
- **Repetition.** "Fail it at collection" over the roughly 277 deployment-half tests must not print 277 copies of the same error. That repetition is exactly what teaches people to stop reading errors.
- **Attribution.** This is an environment state, not a code fault, and it stays true until rebuilt. CLAUDE.md is full of "red local suite, actually setup" misdiagnoses. Say so in the message.
- **Is there a non-destructive route?** The decision note says "a demo and a gate-ready history can sit side by side in two databases (MOTHMAN_SUPPLY_DSN)". But the delivery and receipt trees are per ASSET, not per database (`assets.deliveries_dir()` resolves to `<asset data>/deliveries`). Bootstrapping a second database at the fixed anchor would regenerate the shared tree and leave the demo database out of step with its own files. So the message can only offer the reset route, which is destructive and deletes the demo the person rolled on purpose.
  - Unless the architect confirms a real side-by-side route (for example a second worktree), the message should not suggest a second database, and the decision note should be corrected. **This one is for the architect, not Keith.**

Suggested wording for c6: "...THE SYSTEM SHALL stop the session once, before any test runs, with one message stating: the anchor found and the fixed one; that this is the state of the local database, not a code fault; how many tests need it; and the rebuild commands, saying that the rebuild replaces the rolled demo. It SHALL NOT print the message once per test."

**4. Peak-end: the bootstrap's closing lines.** Three new lines arrive at the end of a run of about two hours: generation time (398 c3), the pin digest (399 c3) and "Generated up to" (407 c4). Problems with how they would land today:
- **The TUI breaks them.** The TUI's `step()` in `cli/app.py` (lines 217-226) adds "..." to every message that is not a budget line. Any new statement sent through `say()` would print as "Generated up to 2026-11-13...". The CLI's `_step` already handles this ("a statement keeps its own full stop").
- **"Generated up to" sits in the wrong place.** It belongs on the final line both surfaces already print ("Populated: N staged table(s)" in the CLI, "Ready - N staged table(s)" in the TUI). There it is the last thing read, and it reaches the TUI as well. "Beside the budget line" puts it among the dim progress lines.
- **The digest is noise to a person** unless it is short, labelled and dim.
- **Generation time should be an entry in the existing "Took ..." line** (`bootstrap.py` line 308), not a second format.

Suggested criterion (shared by 398, 399 and 407): "WHEN a bootstrap finishes, the CLI and the TUI SHALL print the same closing lines, in this order:
1. the 'Took ...' line, with generation as one of its entries;
2. the budget line;
3. 'Configuration pinned: <first 12 characters of the digest>', dimmed;
4. a closing line naming the staged tables and 'generated up to <date>', with '(the fixed test anchor)' or '(rolled to today on <zone>'s clock; `--anchor <date>` reproduces it)'.

No statement SHALL end in '...'."

Also, the TUI still says "This takes a few minutes. Continue?" (`cli/app.py` line 214) for a run measured at 6666s. REQ-PIPE-403's after measurement should replace that with the measured figure for the asset. Otherwise the first-run user's first impression is set by a broken promise.

**5. Discoverability of `--roll-anchor`: put it where the person is standing.**
- The flow is two commands, and the second needs a flag someone has to remember. The Paradox of the Active User says they won't read `--help` to find it.
- The reset's closing line is where they will be. Today it says "Run `mothman pipeline bootstrap` to regenerate."

Suggested criterion (REQ-GEN-405): "WHEN reset-synthetic finishes, THE SYSTEM SHALL name both next steps: `mothman pipeline bootstrap` (the fixed test anchor <date>; the local gate passes on it) and `mothman pipeline bootstrap --roll-anchor` (a demo up to today; the deployment-half tests refuse it)."

Also, give bootstrap's `--help` an examples block, as `schedule candidate-dates` already does (`cli/schedule.py` lines 390-391): plain, `--roll-anchor`, `--anchor 2026-11-13`.

**6. `--anchor` is under-specified as a flag (REQ-GEN-404 c5, c7).**
- Which commands take it isn't listed.
- Nothing says `--anchor` and `--roll-anchor` can't be used together.
- 405 c7 refuses `--roll-anchor` under test/ci but not `--anchor <other date>`, which breaks the cache key and the pins just as much.
- An anchor earlier than the fixed one is unbounded (Q4).
- Removing `GENERATOR_ANCHOR_DATE` silently is a trap. `load_local_env()` reads `.env`, so a developer's leftover variable would just stop working. It is still documented in README.md line 633 and in both providers.

Suggested criteria:
- "THE SYSTEM SHALL offer `--anchor YYYY-MM-DD` on `mothman pipeline bootstrap` and on every `mothman <collection> generate-synthetic-data`, and `--roll-anchor` on the bootstrap only. Giving both SHALL be a usage error naming both."
- "IF `--anchor` names a date other than the fixed test anchor where MOTHMAN_ENVIRONMENT is test or ci, THEN THE SYSTEM SHALL refuse as for `--roll-anchor`."
- "IF GENERATOR_ANCHOR_DATE is set, THEN any generation or bootstrap SHALL refuse, saying it is no longer read and naming `--anchor`."
- "README and every help text SHALL name `--anchor`, and none SHALL name the variable."

**7. The future-anchor and calendar-runs-out refusals must be complete enough to act on.**
- The future-anchor refusal should say: "<date> is after today, <today> on <zone>'s clock. A history cannot be generated up to a day that has not happened. Nothing was written."
- The calendar refusal (406 c5) names `mothman schedule candidate-dates`, but that command needs `--calendar` and `--year`. The message should give a pasteable example with the year needed, the file to extend (`assets/quarterly/calendar.yaml`), and the fallback that still works today: `mothman pipeline bootstrap` without `--roll-anchor`.
- This refusal arrives after the reset has already deleted the demo. Naming the working fallback is what keeps it from being a dead end.
- The SA Q5 step-back ("anchor on the latest day whose receipts have passed") must say why. For example: "Rolling to 2026-11-13: a receipt is still planned for 14:30 today, Perth time." Print it after the populated check and before generation, so a person can stop a two-hour run that has the wrong date.

**8. `mothman env current`'s new line (REQ-DASH-407 c4).**
- Today the command opens no database (`cli/env.py` lines 47-75). Adding a database read must not make it fail or hang. People run it as the "what am I about to act on" check.
- It is also the natural place to answer "will my local gate refuse this database?".

Suggested criterion: "WHERE the selected asset is synthetic, `env current` SHALL add one line: 'Synthetic data generated up to <date>', followed by '(the fixed test anchor)' or '(rolled; the deployment-half tests refuse it)'. IF the database cannot be reached within a few seconds, or holds no history, THEN that line SHALL say so in place of the date, and the command's other lines and exit status SHALL be unchanged." Put it in `_state_the_asset()`'s neighbourhood so that `env list` and `env current` say the same thing.

**9. The datacontract worker's failure messages (REQ-PIPE-431 c4).**
- Today a `WorkerLost` surfaces through `lifecycle_report.stage_failure` as "STOPPED - <run>: the ... stage failed (WorkerLost: the dbt worker process stopped mid-run (EOFError))". That reads as a code-internal crash.
- The two cases differ in stability and should read differently:
  - Lost mid-run is probably a one-off, and the next run restarts the worker.
  - Did not start will recur, so name what to check.
- Coordinate with timing-attempts v1's F3 wording ("Not checked - the run crashed").

Suggested criterion: "The failure SHALL name datacontract-cli, say the supply's data was not the cause, say that the run's other tools' results stand or do not, and say whether the next run restarts it (stopped mid-run) or will fail the same way (did not start), with what to check for the second."

Two smaller items:
- Update `--sequential`'s help on `bootstrap` and `resume`. `resume`'s says "rather than dbt beside the rest" (`cli/pipeline.py` line 577); it now needs to include datacontract-cli.
- REQ-PIPE-432's dbt threads setting needs a refusal for a bad value, naming the setting and the allowed values, not a dbt traceback.

**10. The digest-mismatch and changed-tree endings (399 c3, 430 c2).**
- "Mark the bootstrap's result as not to be trusted" needs a terminal meaning:
  - a non-zero exit;
  - the TUI does not print "Ready" (as it already does for target disagreements, `cli/app.py` lines 233-238);
  - say whether anything recorded was changed;
  - name the remedy.
- Attribution differs by case:
  - A pin-digest mismatch is our fault, since contents are handed to each stream. Say so and don't imply the user edited something.
  - A changed tree plausibly is a person's action (a hand filing or a generate in another terminal during the run). Name that neutrally as the likely cause.

---

### Questions for Keith (one batch; nothing above depends on them except where noted)

**Q1. Reset's typed phrase, now that files go too** (finding 1)
- (a) Change it to "delete all QA history and generated files for <asset>". This keeps REQ-PIPE-144's "naming what it will delete" true. Cost: the existing tests' phrase changes.
- (b) Keep the phrase and rely on the file listing above it. Cost: the thing typed understates what goes.
- **Recommend (a).**

**Q2. Delivery folders the generator didn't write (hand-filed) on a reset** (finding 1)
- (a) Delete them too, listed separately as not regenerable. This is R4's "replaces the whole history".
- (b) Keep them and delete only what the generator wrote. Cost: the bookkeeping is the record 408 says can't be trusted to be complete.
- (c) Refuse the reset while any exist, naming them.
- **Recommend (a).**

**Q3. What anchor `mothman <collection> generate-synthetic-data` uses by default.** Nothing in the draft says.
- (a) The anchor recorded for the asset's current history if there is one, otherwise the fixed one, and it says which. This keeps the TUI's "deterministic - same content either way" prompt (`cli/app.py` line 195) true.
- (b) Always the fixed anchor unless `--anchor` is given. Cost: on a rolled demo it quietly rewrites the tree at 2026-09-25, out of step with the database.
- (c) Refuse when the anchor would differ from the recorded history's.
- **Recommend (a).**

**Q4. An `--anchor` earlier than the fixed test anchor (2026-09-25)**
- (a) Refuse, naming 2026-09-25 as the earliest. 406 only promises a full, placeable history from the fixed anchor to today.
- (b) Allow it, refusing only if a scenario cannot place. Cost: the failure arrives late and in generator terms (CannotPlace).
- **Recommend (a).**

**Provisional on the answers:** finding 1's phrase (Q1) and hand-filed listing (Q2), finding 6's scope of `--anchor` (Q3) and its lower bound (Q4). Everything else stands as written.

**For the architect, not Keith:** finding 3. The draft's "two databases side by side" escape doesn't hold, because the delivery tree is per asset, not per database. Either a real side-by-side route exists (a second worktree?), or the decision note should be corrected and the refusal should offer only the reset route.

Files referenced:
- /home/user/data-poc/docs/drafts/speed-anchor-v1.yaml
- /home/user/data-poc/cli/env.py (reset-synthetic lines 97-143, current lines 47-75)
- /home/user/data-poc/cli/app.py (TUI bootstrap lines 204-240)
- /home/user/data-poc/cli/pipeline.py (bootstrap lines 422-498, resume `--sequential` line 577)
- /home/user/data-poc/qa_tools/common/bootstrap.py (lines 225-234, 308, 317)
- /home/user/data-poc/qa_tools/common/synthetic_reset.py (line 63)
- /home/user/data-poc/cli/lifecycle_report.py (stage_failure, line 361)
- /home/user/data-poc/qa_tools/common/assets.py (deliveries_dir, line 467)
- /home/user/data-poc/requirements.yaml (REQ-PIPE-144's phrase criterion, line 31117)
- /home/user/data-poc/README.md (GENERATOR_ANCHOR_DATE, line 633)
