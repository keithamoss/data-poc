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

## Architect (delivery-architect)

I reviewed speed-anchor-v1 (REQ-PIPE-397 to REQ-GEN-408, REQ-PIPE-430 to 432) against the code at HEAD. This was advisory only: I edited nothing and wrote no files. I did not re-ask anything Keith has already settled. The batch fits the separation-v6 seams in principle. Six findings would make a criterion wrong, unsafe or untestable as worded (B1-B6), and I answer the coordinator's CLI point after them.

## Blocking findings

**B1. The pin is lazy, but the stream processes are supposed to be handed its contents (397 c1 against 399 c2/c3).**
- 397 c1 pins "the text read when that file was first read inside the pin". So at the moment a child process starts, the parent holds only the files it has read so far. Any file the child reads first is read fresh, so the "handed, not re-read" promise and the digest comparison in 399 c3 cannot both hold.
- The handing is also incomplete. There are three process pools, and 399 names only one:
  - `bootstrap._run_concurrently` (bootstrap.py:778-781);
  - the target-trial pool (cli/target_trial.py:171-174), which uses `initializer=assets.select` rather than `assets.handoff`;
  - `parallel_orchestrate.run_manifest`'s pool (parallel_orchestrate.py:101-103).
- **Fix:**
  - At install time, snapshot a declared set of files up front: the asset folder's *.yaml/*.yml (excluding `dbt/dbt_packages/`), assets/environments.yaml and the shared file-checks default.
  - Hand that snapshot to every child through `assets.handoff()`/`adopt()`, which REQ-PIPE-369 c4 already makes the one hand-off. Move target_trial onto `handoff` too.
  - 397 c9's digest is then just the snapshot's digest.
  - Reword 399 c2 to "every process the bootstrap or generation starts".

**B2. config_yaml.read is not the choke point (397 decision 4 and criterion 7).**
- Only about 27 call sites go through `read`/`load`/`Built`. 54 `config_yaml.parse(...)` sites in 26 files read the file themselves first (`Path.read_text()` or `open()`), and a pin cannot see a read that only hands it text. Examples:
  - file_checks.py:95, 357
  - check_bands.py:269, 339, 364, 432, 459
  - check_lifecycle.py:404, 545, 656, 680, 747, 813
  - amber_setting.py:124
  - agreement.py:506
  - environments.py:78
- About 20 more sites bypass config_yaml entirely with `yaml.safe_load`, among them generator/synthetic_inputs.py:54, 73, 90, linked_datasets.py:31, list_setting_members.py:186, 253 and dbt_common.py:193 (mothman's own read of dbt_project.yml).
- c7's only named example, synthetic_reset (lines 43 and 60), never runs inside a pin, and REQ-PIPE-382 c7 already routes it through `declared_synthetic`.
- As worded, "no configuration read inside a pin escapes it" cannot be tested.
- **Fix:**
  - Have c7 say "every reader of a file under the snapshot set goes through `config_yaml.read`/`load`/`Built`".
  - Make that mechanical with a `mothman check` gate in the style of validate_caches: no `read_text`/`open`/`yaml.safe_load` of such a path outside config_yaml in asset_model/, qa_tools/, generator/ or the asset providers.
  - Add a test that installs a `sys.addaudithook` "open" hook around a pinned generation of a test asset, and asserts that no file in the snapshot set is opened from a mothman frame. Tool frames are allowed, per SA Q4.

**B3. REQ-PIPE-400's key misses the staged timezone (c1/c2).**
- `correction_trial.configured` swaps both `agreement.current` and `asset_time.timezone_versions` (correction_trial.py:185-193), and slots resolve zones through the latter. A memo keyed "on the agreement in force" would answer a staged timezone correction with slots worked out under the pinned zones. That is a silent wrong filing.
- Two names are wrong:
  - `slots_for_dataset` is `slots.slots_for_dataset` (slots.py:254), not in schedule.
  - `standing_on` is the method `Agreement.standing_on` (agreement.py:257).
- All four functions take an explicit `agreement=` (schedule._agreement, schedule.py:325). The key must be the agreement actually used, not `agreement.current()`.
- **Fix:**
  - Key on the identity of (agreement used, zone versions tuple). `Agreement` is a frozen dataclass with MappingProxyType fields, so it cannot be hashed; the memo must hold a strong reference so an id is never reused.
  - Better still, memoise on the immutable Agreement instance itself. Built already hands back the same instance for the same text, so this is content-keyed by construction, and it is correct pinned or unpinned. c3 can then drop "remember nothing without a pin".

**B4. REQ-PIPE-430's tree memo is keyed on the configuration pin, which is also installed during generation (c1).**
- REQ-GEN-398 pins generation, and generation recognises the tree it has just written (driver.py:273; linkage_products.py:1424 and 1594, which read the CP and ED trees written earlier under the same pin).
- `checkpoints.arrivals_of` (checkpoints.py:218) generates into a temp tree and recognises that.
- The bootstrap's one-collection and checkpoint branch generates and replays each collection in turn (bootstrap.py:261-270).
- A pin-keyed recognition would therefore serve stale arrivals.
- **Fix:** make the tree snapshot its own installation, done by the bootstrap after the collections it is about to replay have finished generating. Alternatively, invalidate it on every `write_delivery`/`remove_deliveries`. Either way, never memoise during generation. c2's end-of-run digest stays.
- Also: `Arrival` is frozen, but `files_by_dataset` is a plain dict, so c4 needs a deep copy or a MappingProxyType, not just "its own list".

**B5. REQ-PIPE-431 moves all of run_datacontract.evaluate into a worker (c1).**
`evaluate` depends on state that lives only in the pipeline process:
- `asked_for.ask`/`SCOPED` (run_datacontract.py:86-87);
- `run_owner` → `bulk_recheck._TRIAL_OWNERS` (qa_results_writer.py:227; bulk_recheck.py:736), whose docstring says the registry works only because "the tools ... all run in this process";
- `left_out.note` (line 188; left_out.py says "IN MEMORY, PER PROCESS");
- `write_qa_result` stamping records from the process-wide replay clock;
- correction_trial's monkeypatched agreement.

In a worker, records would be stamped with the wall clock, the left-out comparison would raise `LeftOutMismatch`, and re-check trials would lose their scope.

**Fix:**
- Send only the datacontract-cli library call (`datacontract_common.run_against_warehouse`, line 96) to the worker, and return a picklable result (type, model, diagnostics, qualityDefinition per check).
- Keep asking, unreadable-table filtering, left-out notes and recording in the parent.
- Add tests that a replayed run's datacontract records carry the replay clock's instant, and that a re-check trial's datacontract scope survives.

**B6. asset_model/ cannot read the recorded anchor (REQ-GEN-406 c3).**
- 406 resolves offset dates "in asset_model/ against the anchor recorded for the history (REQ-GEN-404)". REQ-GEN-404 records it in only two places:
  - the qa schema, but asset_model never opens the database (REQ-PIPE-380 c8);
  - the generator's bookkeeping, which no pipeline module may read (REQ-GEN-043 c7).
- Nothing at the seam can supply the anchor to `mothman pipeline run`, the CLI, the dashboard build, or the critical CI half (empty database, no data/), all of which read the daily calendar.
- This is a real fork, so it is Q1 below. 406 c3 and 404 c3/c4 are provisional on the answer.

## The coordinator's CLI point: confirmed

- `assets.deliveries_dir()`/`receipts_dir()` are `data_path("deliveries"/"receipts")` (assets.py:467-472), and `data` is `ROOT / "data" / name` (assets.py:187). The tree is per asset per checkout and has nothing to do with `MOTHMAN_SUPPLY_DSN`.
- So a second database at the fixed anchor would regenerate the one shared tree. The demo database would then be out of step with its files, which `replay_inputs.deliveries_print` and a resume would also trip over.
- REQ-GEN-405 decision 6's "side by side in two databases" is wrong and should be corrected.
- **The only real side-by-side route is a second worktree**, which has its own `data/`, with its own `MOTHMAN_SUPPLY_DSN` and its own from-empty bootstrap (about 1h50m for the quarterly asset). There is a catch: `tests/conftest.py`'s `deployment_dsn_for` (lines 783-807) prefers `supply_<asset>` on the server whenever that database exists. So in that arrangement the gate-ready history has to be the `supply_<asset>` database (or sit on another server), and the demo has to use another name.
- **Recommendation:** fix the note, have 405 c6's refusal name the reset route only, and mention the worktree route in a docstring (Q2).

## Non-blocking findings

**REQ-PIPE-397**
- The PERFORMANCE NFR's "inside a pin a configuration read makes no system call" is untrue. `assets.Resolver.names()` calls `os.stat` on every call (assets.py:155-164), and callers check `exists()`/`is_file()` before reading. Reword to "no file read".
- Say what the pin does with a missing file: raise every time, as unpinned.
- Key the pin on the resolved path, because callers mix `REPO/...` paths with resolver paths.
- `load()` still deep-copies on every call inside a pin, which is correct (callers mutate). Say so, so nobody "optimises" it away.

**REQ-PIPE-401**
- It is a real defect: `_SCHEMAS` is keyed on `(path, st_mtime_ns, st_size)` at list_setting_members.py:183-184, and it is also unbounded and not behind a lock. It does not need the pin; build it first, test-first.
- Line 253 of the same file reads data-asset.yaml raw, which is B2's class.

**REQ-TEST-402**
- c6's list is incomplete. These also generate:
  - tests/test_kept_routes_agree.py, test_target_agreement.py, test_scenario_map.py, test_replay_clock.py, test_emergency_department.py and test_correction_claims.py;
  - CLI-driven generations in test_cli_cp, test_cli_bdm, test_cli_pipeline, test_cli_app, test_arrivals, test_scenario_injection and test_processing_pass;
  - test_bootstrap_equivalence, which is deleted with the harness.

  Replace the list with a rule plus a build-time grep recorded in evidence.
- c7 allows any gitignored folder, including `data/`, which everything that recognises arrivals reads (the 2026-09-28 incident). It should say "never under data/".
- c4 cannot rely on file permissions, because the sandbox runs as root and root ignores them. Guard the writers instead, as `_no_test_files_a_real_delivery` does: `write_delivery`, `write_receipts`, `remove_deliveries`, `write_bookkeeping` and `write_placements` refusing paths under the shared root. Add a digest of the tree at session end as a backstop.
- For the cross-worker lock use stdlib `fcntl.flock`; `filelock` is only a transitive dependency in uv.lock.
- Two sessions with different `MOTHMAN_TEST_DB_TAG` share the folder. The "remove a stale key" rule in c7 must not delete a history another session holds; take a shared lock while reading, or keep one folder per tag.
- The cache key must follow REQ-GEN-381 c7's change to INPUTS and its KEY_PREFIX bump.

**REQ-GEN-404 and 405**
- Making "given the anchor by its caller" work in practice means a process-wide installed anchor. It needs the same hand-off to spawned children as B1, because providers call `get_anchor_date()` with no arguments in about 15 places, including correction_claims, scenario_injection and all four providers.
- Fold the anchor into `replay_inputs.cache_key()`. It is constant at the fixed anchor, so 405 c9 still holds, and a rolled history can never match the fixed key.
- 405 c6 "at collection": `deployment_history` is a function-scoped fixture (conftest.py:755), so this needs a `pytest_collection_modifyitems` hook or a session fixture, checked once per asset's database. Specify what happens with no recorded anchor: every local deployment bootstrapped before 404 lands has none, so the first gate after 404 forces a rebuild. Say so.
- 405 c5's "latest day whose planned receipts have all passed" needs the built arrivals (driver.py step 3, `received_at`), not just `plan()`. That is a dry build per candidate day, normally at most one day back.
- A bare `generate-synthetic-data` after a rolled bootstrap would rewrite the tree at the fixed anchor underneath a rolled database. It should refuse when the bookkeeping's recorded anchor differs, unless a reset has run (Q4).

**REQ-GEN-406**
Offset dates break every reader that parses the file raw:
- validate_schedule.py:2307 and 2330;
- agreement_freeze's git-text comparison, where an unchanged offset's meaning moves with the anchor;
- generator/synthetic_inputs.

All of these must go through asset_model's resolver (B2's gate catches them).

**REQ-GEN-408**
- Also delete the scenario placements file (`data_path(scenario_map.PLACEMENTS_FILE)`, scenario_injection.py:56-57), which sits in the same data folder.
- Resolve real paths and refuse symlinks or a `data_dir` outside `ROOT/data/<asset>` or an injected root's own data folder.

**REQ-PIPE-432**
- Pass `--threads` (a documented flag) from one constant, not the profiles.yml literal. Keep it constant for the life of each worker so the partial parse stays valid.
- Sort parsed `run_results` by unique_id before recording, so thread scheduling cannot reorder results.
- The connection NFR should also count the test suite: about 4 xdist workers × threads, times two concurrent sessions.

**REQ-PIPE-403 duplicates REQ-PIPE-250.**
- 403 c2 (three runs against 720s) is REQ-PIPE-250 c2 and REQ-PIPE-352 c5; 403 c3 is 250 c5.
- When 403 is built, 250 c2 stays unmet beside it, so two requirements own one claim (Q3).
- 250's title still says "all three collections", which predates the asset split.

**Seam note on 430, for the builder of REQ-PIPE-382.**
- The tree half of `promotion.next_receipt` (promotion.py:479, 510) is replay-only work living in the real pipeline. Its own docstring says the live pass has no tree.
- Under one clock, only the replay clock uses B. If 382 let the replay clock work out B itself, the pipeline would stop reading the tree on every promotion, and half of 430's work would disappear.
- That would be an edit to v6 382 c4, so I flag it rather than ask it.

**No duplication with REQ-TEST-116.** Its c3 already says a run's four tools are evaluated concurrently, and 431 moves towards that.

**Components touched.** PIPE (qa_tools/common config_yaml, slots, schedule, agreement, arrivals, promotion, run_datacontract, dbt_worker, list_setting_members, assets), GEN (generator/, the providers, bootstrap/), TEST (conftest, 402), DASH (407), DOCS (the CLAUDE.md log). That is wide, but it is already sequenced behind #134.

**Security.**
- The pin and the offset dates are refused on a real asset in shared code: correct, keep it.
- The datacontract worker should copy dbt_worker's authenticated socket and pass credentials by environment, never on the command line.
- More dbt threads means more database connections, nothing wider.
- The test cache holds synthetic rows only, and must be in .gitignore before its first write.

## What "done well" looks like (for delivery-critic)
1. There is one snapshot object in asset_model/ with `install()`/`release()`, and its docstring states the snapshot set. Nothing outside config_yaml and that module mentions it (checked by B2's gate).
2. Every hand-off of the pin and the anchor goes through `assets.handoff()`/`adopt()`. No pool has its own initializer.
3. Every memo has a docstring saying what it is keyed on, why that key is complete (naming the staged agreement and zones), and that it holds strong references. There is no `lru_cache`.
4. Every new test is seen failing first. Each staged-correction test plants a timezone correction as well as a calendar one.
5. The datacontract worker reuses dbt_worker's start, lock and restart code through one shared helper, not a copy. Nothing that records results runs in it.
6. 402's guards refuse by function and name the file. There are no permission-based guards.
7. Each measurement in 403 records the load average and the commit.

## Sketch
bootstrap → `asset_model.snapshot.install(files)` → generate (anchor installed, pinned, no tree memo) → `asset_model.tree.install(collections)` → replay; each spawned child gets `handoff()` = (asset, layout, snapshot, anchor, clock seed) → release in reverse order. Per run: dbt worker (threads N) ‖ datacontract worker (library call only) ‖ foreground Soda then Evidently; recording happens in the parent, in tool order.

## Build order
1. After v6's 380, 382, 383 and 381/386: 403 c1 (the baseline), then 401 (a defect fix that needs no pin).
2. 397 (eager snapshot plus B2's gate), then 400, 398, 399.
3. 432 (its baseline is in 403 c1), then 430 (after 399, separate install), then 431.
4. 404, then 405, then 406 (once Q1 is answered), then 408, then 407.
5. 402 (after 405 and 398).
6. 403's remaining criteria last.

## Questions for Keith (one batch)
**Q1. Where does asset_model get a synthetic history's anchor, to resolve offset dates? (REQ-GEN-406, B6)**
- (a) The generator writes the anchor as a one-line file beside the delivery tree under `data/<asset>/`. asset_model reads it (its charter covers the delivery tree). With no tree, offsets resolve to the fixed test anchor only under the test and ci environments, and are refused elsewhere. A real asset is refused. Cost: a third record of the anchor, though all three are written from one value.
- (b) The real pipeline reads the anchor recorded in the qa schema and installs it into asset_model before reading configuration, at every entry point (pipeline run, CLI, build). Cost: a synthetic-only concept in every real entry point, close to the replay flag 382 removes.
- (c) Every caller passes the anchor as an argument. Cost: wider signatures everywhere, the shape 382 already rejected for the clock.
- **Recommend (a).**

**Q2. A rolled demo beside a gate-ready history (REQ-GEN-405 decision 6, the coordinator's point)**
- (a) Correct the note: the tree is per checkout. The refusal names reset then bootstrap only, and a docstring mentions a second worktree whose gate-ready database is `supply_<asset>`.
- (b) Make the delivery tree per database (`data/<asset>/<db>/`), so one checkout can hold both. Cost: every path resolver and the guard changes.
- **Recommend (a).**

**Q3. REQ-PIPE-403 against REQ-PIPE-250 c2/c5 (a register-claim edit)**
- (a) 403 records the batch's before and after, and is the evidence for 250 c2 and c5. Drop 403's restated "three runs against 720s" and point it at 250 c2, so one requirement owns the budget.
- (b) Keep both as drafted. Cost: two requirements carrying one unmet claim.
- **Recommend (a).**

**Q4. A bare `generate-synthetic-data` after a rolled bootstrap**
- (a) Refuse when the bookkeeping's recorded anchor differs from the one requested, naming reset then bootstrap.
- (b) Default to the bookkeeping's recorded anchor instead of the fixed one.
- (c) Leave it as drafted (always the fixed anchor). Cost: the tree silently goes out of step with the database.
- **Recommend (a).**

**What is provisional on the answers:** 406 c3, 404 c3/c4 and 405 decision 6's wording wait on Q1 and Q2. Everything else above is my technical call.

## Files
- /home/user/data-poc/docs/drafts/speed-anchor-v1.yaml
- /home/user/data-poc/docs/drafts/separation-v6.yaml
- /home/user/data-poc/qa_tools/common/config_yaml.py
- /home/user/data-poc/qa_tools/common/correction_trial.py
- /home/user/data-poc/qa_tools/common/bootstrap.py
- /home/user/data-poc/qa_tools/tools/run_datacontract.py
- /home/user/data-poc/qa_tools/common/left_out.py
- /home/user/data-poc/qa_tools/common/assets.py
- /home/user/data-poc/generator/driver.py
- /home/user/data-poc/tests/conftest.py
