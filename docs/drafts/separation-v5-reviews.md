# #134 v5 - the three pre-build reviews, 2026-11-14

Advisory reviews of docs/drafts/separation-v5.yaml, kept verbatim as each agent reported. Their questions go to Keith as ONE batch with the scoper's nine (Keith, 2026-11-14), asked one at a time.

## Dashboard UX (delivery-dashboard-ux) - questions A-D

delivery-dashboard-ux review: docs/drafts/separation-v5.yaml (REQ-PIPE-376 .. REQ-GEN-392), dashboard surface only

I read docs/project-context-for-agents.md, docs/hci-ux-psychology.md, docs/spa-best-practices.md (section list, plus A, C, D and F as they apply), the draft in full, the 2026-11-14 answers in docs/drafts/decisions-2026-11-01.md, and the relevant parts of dashboard/qa-reporting-dashboard.template.html, dashboard/embed_dashboard_data.py and pipeline/period_slots.py. I edited no files. I did not re-ask any of the scoper's 9 open questions.

Most of the 17 requirements are code moves that a reader cannot see, and the scoper has proved that through REQ-TEST-239. Four of them change what a reader sees: REQ-PIPE-385 (scenario features hidden on a real asset), REQ-QAC-389 (a new check on Emergency Department), REQ-GEN-392 (regenerated verdicts) and REQ-PIPE-378 (how a configuration error surfaces). The findings below are ranked, with the error-state ones first, as the HCI doc's weighting says they should be.

---

## 1. HIGHEST: the dashboard build still hides schedule configuration errors, and REQ-PIPE-378 does not name where (error/failure-state context)

**What I found in the code:**
- `dashboard/embed_dashboard_data.py` line 370 (`_slots_by_dataset`) catches `ScheduleConfigError` and skips the dataset with `continue`.
- `pipeline/period_slots.py` line 47 (`for_dataset`) catches it and returns `None`.

**Why it matters:** Q9 settled that "a configuration mistake is never read as an answer". Criteria 15-17 apply that to `is_owed_supplies`, `period_claimed_at` and their pipeline callers. They do not reach these two build sites, which are the last step before the page. So a dataset with broken schedule configuration still gets published with no slots and no due dates. To the reader it looks like "nothing owed / nothing due", the same quiet wrong answer Q9 removed from the pipeline. CLAUDE.md's rule about checking the last transform before the user applies directly.

Criterion 10 lists `period_slots.py` line 40 as "already raises", but the `try` on lines 44-48 in the same function still hides the error.

**Pattern to reuse if the page should say something:** `agreementNotice()` (`notice-exhausted` class, `data-agreement-refused`). It is one notice for the whole asset, lists each affected dataset as a link, and says "This is a configuration problem on our side, not a problem with anyone's data", naming the file with `assetFile("calendar.yaml")`. That is the right non-punitive framing: it places the fault with us, not the supplier. `BROKEN_COLLECTIONS` is the precedent for "show what loaded, name what broke, in one notice". → Question A.

**Suggested criterion (REQ-PIPE-378, new, after 17):** "WHEN the dashboard build (embed_dashboard_data._slots_by_dataset, pipeline/period_slots.for_dataset at a35066ff) meets a ScheduleConfigError for a dataset, THE SYSTEM SHALL [per question A] and SHALL NOT publish that dataset as having no slots; NoCalendarAgreed keeps its quiet answer." Plus a real-browser test, failing first, that a dataset with broken schedule configuration does not show as owing nothing.

## 2. HIGH: a step stopped by a configuration error probably shows on the page as the supplier's fault (error-state context)

Criterion 17 stops the arrivals and promotion steps on a `ScheduleConfigError`. That is correct for the pipeline. But `qa_tools/common/outstanding.py` has no configuration-error kind, so the only place a reader learns why is the CLI or log. On the dashboard, a supply that was never processed most likely shows as not received, late or missing against the supplier. Attribution theory is the reason this matters: the reader blames the wrong party for a fault that will repeat every run until someone fixes the config.

I have not driven this end to end, so treat "shows as late" as likely, not verified. delivery-architect can confirm it. → Question B.

## 3. HIGH: REQ-PIPE-385 criteria 5 and 7 need to name the actual scenario surfaces, or the build will miss some and the test will be impossible to pass (first-time-use and at-a-glance contexts)

On a real asset, the reader who matters is an agency data owner on a first visit. The principles I checked: Hick's Law (there are 11 header controls today, and one that leads nowhere is pure cost) and Jakob's Law (a real QA register has no "Scenarios" entry). Keith's ruling to hide them entirely is right. What the requirement needs is a list of the actual surfaces. Today they are:

- **Header button:** `#scenarios-btn` (template line 1094) is static HTML. Its listener on line 12228 calls `getElementById("scenarios-btn").addEventListener` with no guard. Deleting the button without guarding that line throws and breaks the page's zero-console-errors standard. Hide it with the `hidden` attribute, which also removes it from the accessibility tree that criterion 7 checks, or guard the listener.
- **Route `/scenarios`:** `stateToPath`/`pathToState` (lines 5933 and 5952), `COLLECTION_TIERS` (line 7383) and `renderScenarios`. A cold deep link (bookmarks travel between the demo and real deployments, which share one codebase and one URL scheme) renders a "Scenarios" heading plus the empty-state text "No scenario map embedded ... rebuilt with the synthetic history itself" (line 12186). That text directly breaks criterion 5.
- **Legacy `?panel=scenarios`:** handled on lines 7157 and 13192, same issue.
- **`?scenario=<id>`:** with an empty map, `SCENARIO_ON_LOAD` calls `scenarioNotOnPage(null)`, which prints "This link names a test scenario this dashboard does not hold" (line 12110). That also breaks criterion 5.
- **Jump bar, subject mark and label** (`scenarioJumpBar`, `markScenarioSubject`): already unreachable with an empty map, so they need nothing.

**SPA fit:**
- **Path or query string:** no new state is added, so nothing to decide. Under section A, `/scenarios` is identity (path) and `?scenario=` is view state (query). On a real asset both need a defined landing, with the address fixed by `replaceState` so it is not left in history. The existing precedent is `forgetStaleSegment()`.
- **Route-change accessibility (section F):** if `/scenarios` is redirected, the title and route-announcer text must be the overview's, never "Scenarios".
- → Question D for the exact landing.

**The test trap in criterion 7:** "finds no scenario control or label in the page's text" will fail on any honest build. The Requirements, Plans and Release-notes tabs, and `RELEASE_NOTES` embedded on the page, all contain authored text about scenarios. Suggested wording:

> "...finds no scenario control, tab, link, count, jump bar or label in the header, the drill-down pages (exec, agency, collection, period, dataset, column, check) or their accessible names, and that a cold load of /scenarios, ?panel=scenarios and ?scenario=<any id> each lands as question D settles with the scenario parameter removed from the address; authored text in the Requirements, Plans, Feedback and Release-notes tabs is excluded. The same page built with a non-empty map shows the button, the tab and a working jump."

Also add: "the raw template's 'No scenario map embedded' empty state SHALL be removed, not left unreachable". Once an empty map always hides the tab, that branch can never run.

## 4. MEDIUM: regenerated verdicts (REQ-GEN-392) need a release note, not anything on the page (routine-daily-use context; error-state for whoever notices the change)

**The principle:** for routine use the research says predictability matters more than delight. The people who will notice are Keith and anyone he has demoed to, who remember which supply was red. A verdict that changes with no explanation looks like the tool being unreliable. That is the trust damage negativity bias predicts.

**Why not on the page:** I would not put a banner on the page. The Scenarios tab's own principle (line 12196: "Nothing on the pages labels them, because a failing supply should read the way a real one would") rules it out. The Scenarios tab, re-captured under criterion 7, is already the one place that says what is deliberate.

**The release note:** CLAUDE.md already requires a `CHANGELOG.yaml` entry in the same push for this. Neither REQ-GEN-392 nor REQ-QAC-389 says so, so delivery-critic has nothing to check. Suggested criteria:

- **REQ-GEN-392:** "THE SYSTEM SHALL ship, in the same push, a CHANGELOG.yaml entry telling a reader that Birth Registrations' and Child Protection's sample history was regenerated on purpose, with how many supplies' verdicts moved in each direction per collection, taken from criterion 6's evidence."
- **REQ-QAC-389:** "...a CHANGELOG.yaml entry saying Emergency Department's age_group is now also checked by datacontract-cli, with results across the whole sample history."

**One more thing to list in evidence:** supply-history resupply chains are built from red status (template line 9465: "a red status is exactly what starts/continues a chain"). OQ3 (i)(a) moves Child Protection's amber partial resupplies from red to amber, so on the Supply history panel some chains will regroup or shorten, not just change colour, and the promoted badges (`redPromotedBadge`/`amberPromotedTag`) will change. Suggest criterion 6 adds "every supply-history chain whose grouping changed".

**Lower:** shared `?scenario=...&<as-of>` links carry the old as-of date. If a scenario's coordinates move, an old link lands on the existing "has nothing to show on this page ... opens at the top" notice. That works, but it is a dead end. Criterion 8 already stops the build if a target no longer lands, so I suggest only noting it in the release note.

## 5. LOW: the new Emergency Department check (REQ-QAC-389) fits existing patterns; no new UI needed (investigating/drill-down context)

- It shows up as one more card on the age_group column, next to its dbt accepted_values sibling.
- Its changelog is `[]`, so the "Definition changelog" block (line 11224) correctly stays hidden.
- It does not appear in Recent activity (`CHANGELOG_FEED` holds publish events and corrections, not check additions). Correct.
- **Wording:** I agree with taking failure_indicates from the dbt sibling ("age banding"), even though the table's own triage_category and sex datacontract checks say "a new code" (contract lines 107 and 138). The reader sees the checks for one column together, so matching within the column is the consistency that counts.
- **On OQ1 (introduced_date), supporting the recommendation, not re-asking:** the page never shows `introduced_date` (grep finds no use of it), so on the dashboard option (a) reads consistently. Option (b) would make no visible difference on the page, but the register's date would contradict results the page shows back to 2013.

## Which context and which principles, for delivery-dashboard-ux-critic to check

| Requirement | Context | Principles checked |
|---|---|---|
| REQ-PIPE-378 (configuration errors) | error/failure states | non-punitive framing; fault placed with us not the supplier (attribution theory); no quiet wrong answer; don't teach readers to distrust the page (learned helplessness) |
| REQ-PIPE-385 (scenarios hidden) | first-time use, at-a-glance | Hick's Law; Jakob's Law; recognition over recall; SPA section A (cold deep link rebuilds the view), section F (title and announcer) |
| REQ-GEN-392 (regenerated verdicts) | routine daily use, plus error states for whoever notices | predictability; peak-end; changes explained with the cause stated as deliberate and one-off |
| REQ-QAC-389 (new check) | investigating/drill-down | consistency with sibling cards; progressive disclosure (no new chrome) |

---

## New questions for Keith (none of these repeat the scoper's 9)

**A. A dataset's schedule configuration breaks: what does the published dashboard do?** (finding 1)
- (a) The build refuses, naming the dataset and the file. The live page stays at the last good build, so readers see stale data with no sign anything is wrong.
- (b) The build carries on. The page shows one notice for the whole asset in the `agreementNotice` style ("a configuration problem on our side, not a problem with anyone's data"), listing each affected dataset, and those datasets show no due or owed state rather than "nothing owed".
- (c) Keep hiding it as today. This contradicts Q9 at the layer the reader sees.
- **Recommended: (b).** It matches your 2026-10-25 call that one bad file no longer blocks the page, and it scales to 30 collections as one notice, not 30.

**B. A pipeline step stopped by a configuration error (REQ-PIPE-378 criterion 17): should the dashboard know?** (finding 2)
- (a) Record it as a new blocking kind in the "needs a person" queue (`outstanding.py`), naming the configuration, so the page says why a supply is missing.
- (b) CLI and log only; the page shows whatever an unprocessed supply shows (probably late or missing, against the supplier).
- **Recommended: (a).** Under (b) our fault reads as the supplier's, and it repeats every run until fixed. It could be its own small requirement rather than widening REQ-PIPE-378.

**C. On a real asset, should page text that assumes synthetic data also go?** Footer, line 1121: "...against generated synthetic supplies". Demo tab, line 12730: "run for real against real synthetic Birth Registrations data".
- (a) Footer and Demo tab both gated on the asset's `synthetic: true` declaration (embedded through REQ-PIPE-382's single reader).
- (b) Footer only. The Demo tab stays, since it is plainly labelled as a recording of the tool.
- (c) Neither. Out of #134's scope; leave it to a later requirement.
- **Recommended: (b).** On a real asset the footer becomes false. The Demo tab is labelled honestly wherever it appears.

**D. Where does an old scenario link land on a real asset?** (finding 3)
- (a) `/scenarios` and `?panel=scenarios` go to the overview, with the address fixed by `replaceState` and one neutral line: "This link points at a page this dashboard does not have." The `?scenario=` parameter is dropped silently, since everything else in that URL still resolves.
- (b) A plain not-found page at `/scenarios` (`renderNotFound`), which repeats the word "scenarios" from the URL back to the reader.
- (c) Every case drops silently to the overview, with no line at all.
- **Recommended: (a).** It follows the existing `forgetStaleSegment()` precedent, says nothing about scenarios, and leaves Back working.

**Provisional on the answers:** the criterion wording in findings 1 and 3 depends on A and D. Finding 2's criterion depends on B. Everything else stands either way.

## Files referenced
- /home/user/data-poc/docs/drafts/separation-v5.yaml
- /home/user/data-poc/docs/drafts/decisions-2026-11-01.md
- /home/user/data-poc/dashboard/qa-reporting-dashboard.template.html (lines 1094, 1121, 5929-5969, 7157, 9465, 11224, 12101-12123, 12172-12228, 12730, 13191-13236; `agreementNotice` at 5199)
- /home/user/data-poc/dashboard/embed_dashboard_data.py (line 370)
- /home/user/data-poc/pipeline/period_slots.py (lines 36-48)
- /home/user/data-poc/qa_tools/common/outstanding.py (no configuration-error kind)
- /home/user/data-poc/assets/quarterly/department-of-health/emergency-department-contract.yaml (lines 86-138)

## CLI UX (delivery-cli-ux) - questions A-D

delivery-cli-ux review: docs/drafts/separation-v5.yaml (REQ-PIPE-376 to REQ-GEN-392)

Advisory only. I edited no files. I read the draft in full, the 2026-11-14 decisions (docs/drafts/decisions-2026-11-01.md, lines 419-473) and the cli/ source. I do not re-ask the scoper's 9 open questions. Where my UX view bears on one of them I say so briefly.

**Contexts and the principles checked**
- **Error/failure states (most weight):** REQ-PIPE-378's newly raised configuration errors, REQ-PIPE-385's refusals, the gate failures. Checked against non-punitive framing, attribution theory (say whether the cause will keep recurring) and clig.dev's "say what broke and a realistic next step".
- **First-time use:** what someone sees on their first `mothman`, `mothman --help` or menu on a real deployment. Checked against the Paradox of the Active User (don't rely on docs being read) and Jakob's Law.
- **Configuration/setup:** the `imports` and dbt-packages gates, file-checks overrides, the new contract rule. Checked against error prevention and recognition over recall.
- **Routine daily use:** the horizon's cost in the filing TUI and `supply queue`. Checked against the Doherty Threshold (under 400ms) and predictability.

None of the 17 adds a command, so no Tier choice comes up. The two gates take `mothman check`'s Tier 3.

---

## Findings, most important first

### 1. `mothman pipeline run` on a real asset is not specified, yet two criteria depend on it
- `cli/pipeline.py` lines 35-61: `_run_collection` and `_run_stream` always call `generate_synthetic_data()` first.
- The help text (lines 72, 81-83) says "regenerate synthetic data, run the real tools against every run in the manifest".
- After the replay it runs `bootstrap_mod.targets_agree` and `_confirm_corrections` (lines 135, 146).
- REQ-GEN-381 criterion 2 calls `pipeline run` "a real asset's first run". REQ-PIPE-385 criterion 6 requires it to succeed with the generator unimportable. No criterion says what it does instead, or what its help says.
- On a synthetic asset, REQ-PIPE-383 criterion 5 now stops it playing scripted decisions. It still compares targets afterwards, so a scenario whose outcome depends on a scripted decision could end that run with a red "disagreement". That is a new failure a developer would hit with nothing to explain it. This needs Keith (question A below).

Suggested criterion for REQ-PIPE-385, whichever way A goes:
> "WHERE the selected asset has no synthetic/ folder, `mothman pipeline run --help` and `mothman pipeline --help` SHALL say nothing of synthetic data, manifests, regeneration or targets, and the run SHALL print no 'Generating synthetic data' or 'Comparing every targeted supply' line."

### 2. The newly raised configuration errors would reach a person as a traceback
- Only `mothman schedule show` turns a ScheduleConfigError into a ClickException (`cli/schedule.py` line 149).
- `_MothmanGroup.invoke` (`cli/app.py` lines 264-290) catches AssetError, SchemaVersionError, StageFailed, SupplyDbError, EnvironmentError_ and YAMLError, but not ScheduleConfigError. Nothing in `cli/pipeline.py` catches it either.
- Today the errors are swallowed. Once REQ-PIPE-378 criteria 15-17 let them through `arrivals.py`, `promotion.py` and `slots`, they can surface from `mothman pipeline process`, `pipeline run`, `<short> qa --commit` and the filing TUI.
- The message (`schedule.py` lines 181-183) names the calendar, the date and the earliest version. It does not name the file to edit, the dataset that asked, or a next step. NFR OBSERVABILITY's "needs no extra words" doesn't hold from a terminal.
- Attribution: `pipeline process` documents exit 2 as "left for the next pass", which implies something passing. A configuration error fails the same way on every pass until the file is fixed, and the message should say so.

Suggested criteria for REQ-PIPE-378:
> "WHEN a ScheduleConfigError reaches a `mothman` command, THE SYSTEM SHALL show it as a refusal of one paragraph, never a traceback, naming the asset's calendar file (assets/<asset>/calendar.yaml), the dataset whose date asked, the date and the calendar's earliest version, and ending 'Fix the configuration, then `mothman schedule validate` checks it'; in the terminal's menus the menu SHALL carry on, as for any refusal (cli/app.py's main loop)."

> "WHEN `mothman pipeline process` or `mothman pipeline run` stops a step on a ScheduleConfigError, its report SHALL say what was recorded before the stop (the existing StageFailed report) and that the step will fail the same way on every pass until the named configuration is fixed."

Suggested change to REQ-PIPE-378 criterion 4: add "reported in the gate's existing form - under the calendar file, scoped to the dataset, with a problem line and a fix line (validate_schedule._report)".

On open question 2 (not re-asking): from the error-state view, option (a) is right. A supplier's early file becoming a pipeline failure is the user being blamed for something outside their control.

### 3. Nobody lists which commands are "synthetic commands", so the post-build critic cannot check criteria 2 and 3
I counted these today:
- `mothman <short> generate-synthetic-data` for every collection
- `mothman pipeline bootstrap`, `pipeline resume`, `pipeline checkpoint list|arrivals|delete`, `pipeline cache-key`
- `mothman scenarios map|list|validate|bands`
- `mothman population`
- `mothman env reset-synthetic`

Three more places that are not commands but show the same thing:
- **Main menu** (`cli/app.py` lines 72, 75, 86-91): "Generate synthetic data" and "Set up this environment", and the menu's `flag_hint` string naming both commands.
- **QA wizard source picker**: "Synthetic - pick or generate a run" is the first choice in `cli/one_table.py` line 206 and `cli/many_tables.py` line 475. It offers to generate data (one_table.py lines 219-225). `qa --help` advertises "Synthetic (--run-id)". On a real deployment the first choice of the most-used flow would fail. Question B.
- **Subgroup level**: the refusal has to work at the subgroup level. Today only the root group's `resolve_command` (app.py lines 248-262) handles an unknown name, and it says "No such command", which criterion 3 forbids. `pipeline bootstrap` and `env reset-synthetic` sit inside groups, and `generate-synthetic-data` inside each collection group.

Suggested replacement for REQ-PIPE-385 criterion 2:
> "...SHALL list a synthetic command only WHERE...; the synthetic commands are, at the build commit, `mothman <short> generate-synthetic-data`, `mothman pipeline bootstrap`, `resume`, `checkpoint` and `cache-key`, `mothman scenarios`, `mothman population` and `mothman env reset-synthetic`, and WHERE they are not listed the main menu SHALL offer neither 'Generate synthetic data' nor 'Set up this environment' and its flag hint SHALL name neither command."

Suggested addition to criterion 3:
> "...at whatever level it is invoked (`mothman pipeline bootstrap`, `mothman <short> generate-synthetic-data`, `mothman env reset-synthetic` included), in one sentence of the form '`mothman pipeline bootstrap` generates synthetic data, and asset '<asset>' has no synthetic/ folder (assets/<asset>/synthetic/) - this deployment processes real supplies only.'"

REQ-GEN-381 criterion 2's refusal should follow the existing reset-synthetic shape (`cli/env.py` lines 113-116), and come from REQ-PIPE-382 criterion 4's single reader of `synthetic: true`:
> "...refuse, naming the asset and its data-asset.yaml, saying that nothing was generated, and naming `mothman pipeline run` as a real asset's first run."

### 4. `mothman check` on a real deployment would fail, or overstate what ran
- The `providers` gate runs `python3 -m generator.validate_providers` (`cli/check.py` line 87). With the generator absent that is a ModuleNotFoundError.
- `scenarios` and `scenario map` (lines 139-145) call commands REQ-PIPE-385 removes.
- REQ-PIPE-385 criterion 1 says "pass every gate". Showing these as "passed" breaks check.py's own rule ("never 'every gate passed' when one of them did not run"). Showing "not installed" (exit 127) points at CLAUDE.md's toolchain setup, which is the wrong fix. Question C.
- The two new gates must be in `_REPOSITORY_WIDE` (line 190). Otherwise, with no asset selected, each runs once per asset folder and prints the same findings twice. The dbt gate compares across assets, so a per-asset run would also be misleading.

Suggested criterion for REQ-TEST-384 and REQ-TEST-388:
> "THE SYSTEM SHALL run the gate once per `mothman check`, whatever MOTHMAN_ASSET says, under the label `imports` (REQ-TEST-388: `dbt packages`), reachable by `mothman check --only <label>`, with a one-line 'What it covers' entry in the summary table, placed among the cheap gates before `schedule`."

### 5. The imports gate's failure output should look like ruff's
- ruff is the first gate in the same command, and `path:line:` is what editors make clickable (Jakob's Law).

Suggested criterion for REQ-TEST-384:
> "Each finding SHALL be one line of the form `<path>:<line>: <side> imports <side> (<module>) - forbidden edge`, followed by one closing line giving the count and saying the fix is to move the code across the boundary, not to add an allowlist entry."
- A stale entry should say "<allowlist file>: entry '<file> imports <module>' (<REQ>) matches no import any more - delete it". That is framed as progress, not blame.
- An added entry should say "the list only shrinks (REQ-TEST-384); this entry is absent at <base commit>". It has to name the base commit, because locally a person can't otherwise tell what it compared against.
- REQ-TEST-388 criterion 2 should end with the next step: "make both match, then run `mothman env dbt-deps` for each asset".
- REQ-QAC-389 criterion 4 and REQ-QAC-387 criterion 8 should name WHICH `mothman check` gate fails, so `--only <gate>` can be driven post-build. Criterion 4's run-time refusal should name the fix ("add an invalidValues rule or `enum:` to <column> in <contract>").

### 6. A person's first contact is not in the import-blocking test
- `cli/app.py` lines 44-45 import `cli.scenarios` at module level, which imports `qa_tools.common.scenarios` and `scenario_map`. Both move out under these requirements.
- So unless that import becomes conditional, `mothman --help` itself raises ImportError on a real deployment, before any command.
- REQ-PIPE-385 criterion 6 tests `pipeline run`, `dashboard rebuild` and `check`, but not the first thing anyone runs.

Suggested addition to criterion 6:
> "...and `mothman --help`, `mothman pipeline --help` and `mothman <short> --help` exit 0 listing no synthetic command, and bare `mothman` without a terminal gives its existing flag-hint refusal (NotInteractive), not an ImportError."

REQ-PIPE-380's NFR says "the CLI's import time is unchanged". Make it checkable: "the wall-clock time of `mothman --help` is measured before and after, on the same sandbox, and is within 5 percent; deciding whether a synthetic command is listed SHALL NOT import the generator, scenarios/ or the bootstrap package (importlib.util.find_spec, not import)." That keeps `--help` under the Doherty Threshold.

### 7. `mothman scenarios bands` is useful on a real deployment, and it would disappear with its group
- It answers "can this rule read Warn, at this row count" from committed check files (`cli/scenarios.py` lines 142-168). That is a check-author's question, not only the generator's.
- Its reader, `check_bands`, moves into `asset_model/` (REQ-PIPE-380 criterion 9), so it could run on a real deployment.
- Question D.

### 8. The horizon and routine latency (supports the scoper's open question 3 (a))
- Under option (b), `slot_named`, `placing` and `turned_off` stop seeing periods more than about 13 months ahead. Re-filing into one becomes a refusal, which is the quiet direction the error-state weighting warns against. So UX supports option (a).
- But option (a) roughly triples the periods a daily dataset generates per look-up. Look-ups run on every keypress-to-answer step in `settle_tui` (`relative_period`, `cli/settle_tui.py` line 180), the filing TUI and `supply queue`. NFR 3 measures only the dashboard build.
- Suggested addition to REQ-PIPE-378 NFR PERFORMANCE: "...and `mothman supply queue`, `mothman schedule show --dataset birth-registrations` and one step of the filing TUI are timed before and after on the daily asset; any that moves past 400ms, or slows by more than 20 percent, is reported to Keith."
- Wherever a look-up beyond the horizon becomes a refusal, the refusal should name the horizon and its reach, not just "not found".

### 9. A concrete, drivable check for REQ-PIPE-378 criterion 8
Today `mothman schedule show --dataset cp-clients --on 2012-06-01` silently borrows the first version's window. Suggested criterion:
> "`mothman schedule show --dataset cp-clients --on 2012-06-01` SHALL exit 0, show the claim window as stated by no calendar version on that date, naming the calendar's earliest version (2013-01-01), and print no traceback."

### 10. What the regenerated history changes in the CLI (REQ-GEN-392)
- Criterion 6's evidence should also list what a person reads at the terminal, not only records:
  - the bootstrap's closing "Ready - N staged table(s)" count
  - `mothman supply queue`'s counts per dataset (Child Protection amber partial resupplies move from red to amber, which changes what waits on a decision)
  - `mothman scenarios list`
- Criterion 7's re-capture list should either include `dashboard/demos/qa_wizard.cast` (a recorded Birth Registrations Synthetic-mode QA run), or explicitly say the recording's run is unaffected. Someone should look at which run it shows.

### 11. Smaller points
- REQ-PIPE-383 criterion 5 (settled) changes what `pipeline run` leaves in the queue on a synthetic asset. One dim line would prevent a "why is my queue full" moment: "Scripted decisions are played only by `mothman pipeline bootstrap`; this run played none."
- REQ-PIPE-385 NFR RELIABILITY ("never a traceback") is good. Criterion 3 should state the exit code: 1, as a ClickException, matching every other refusal by design. Not 2, which Click uses for usage errors.

---

## Questions for Keith (none of these are among the scoper's 9)

**A. What does `mothman pipeline run` do on each kind of asset after this split?**
- (a) It never generates, on any asset. It runs whatever has arrived, then builds, with help text that is true everywhere. Generation is `generate-synthetic-data` and the bootstrap. One meaning per command name.
- (b) On a real asset it skips generation and the target comparison. On a synthetic asset it keeps generating as today, minus scripted decisions. That keeps today's developer habit, but the same command means two things, and the comparison may fail on decision-dependent targets.
- (c) It becomes synthetic-only and is hidden on a real deployment like the bootstrap, with `mothman pipeline process` as a real asset's first run. That reverses REQ-GEN-381 criterion 2's wording.
- **Recommended: (a).** It is consistent across deployments, makes criterion 6 achievable, and stops the red disagreement in (b).

**B. Does Q3's "present only where they can run" cover the QA wizard's Synthetic source and `qa --run-id`/`--reference-run-id`?**
- (a) Yes, fully. The source choice is not offered, the flags are not listed in `qa --help`, and passing one is refused by name as criterion 3 does.
- (b) Hide the wizard choice, keep the flags listed, and refuse them at run time.
- (c) Leave both, refusing at run time.
- **Recommended: (a).** It is the same rule Q3 already chose for commands, applied to the most-used flow's first question.

**C. On a real deployment, how do `mothman check`'s synthetic-only gates (`providers`, `scenarios`, `scenario map`) report?**
- (a) One row each saying "not applicable (no synthetic/ folder)". The closing line and the paste-into-commit line say "every gate that applies passed" and name them.
- (b) Left out of the table entirely, as the commands are.
- (c) Shown as passed.
- **Recommended: (a).** check.py's rule is never to overstate what ran. (b) is defensible but makes "did that gate run?" unanswerable from the output. (c) is a false green.

**D. Where does `mothman scenarios bands` live?**
- (a) Move it to a group a real deployment keeps, for example `mothman debug check-bands` (Tier 3, a check author's aid). The old name is not kept, per the no-forwarding rule.
- (b) Leave it under `scenarios`, gone on real deployments.
- (c) Keep `scenarios bands` alone visible on real deployments.
- **Recommended: (a).** Its reader moves into asset_model/ anyway, and someone tuning a real check's warn/fail bands is exactly who asks whether a rule can read Warn. (c) leaves a half-group.

**Provisional on the answers:** finding 1's suggested criterion holds under any answer to A. Finding 3's wizard wording depends on B, and finding 4's report wording on C. Everything else above is independent of these four.

Files referenced: /home/user/data-poc/docs/drafts/separation-v5.yaml, /home/user/data-poc/docs/drafts/decisions-2026-11-01.md, /home/user/data-poc/cli/app.py, /home/user/data-poc/cli/pipeline.py, /home/user/data-poc/cli/check.py, /home/user/data-poc/cli/one_table.py, /home/user/data-poc/cli/many_tables.py, /home/user/data-poc/cli/collection_cli.py, /home/user/data-poc/cli/schedule.py, /home/user/data-poc/cli/scenarios.py, /home/user/data-poc/cli/env.py, /home/user/data-poc/cli/settle_tui.py, /home/user/data-poc/qa_tools/common/schedule.py, /home/user/data-poc/qa_tools/common/validate_schedule.py, /home/user/data-poc/dashboard/demos/qa_wizard.cast

## Architect (delivery-architect) - questions QA-QD

I reviewed docs/drafts/separation-v5.yaml for technical fit against the tree at a35066ff. Six findings block the build as worded, and four new questions for Keith are at the end. All of this is advisory. I edited no file.

## Blocking findings

**B1. REQ-PIPE-382 treats two different times as one.**
- There are two readings today:
  - **The stamp:** `replay_clock.now()` gives the instant written on a record. During a replay it is simulated.
  - **"Today":** `asset_time.now()` gives the current time. It is the wall clock, or `MOTHMAN_PINNED_NOW`, and it is never the replay clock.
- Criteria 1, 3 and 7 merge them into "one installation call". That breaks real behaviour. For example, `promotion.effective_at_for` (promotion.py line 421) computes `min(asset_time.now(), received + lag)`. If "today" became the simulated instant, every backdated promotion would collapse to its receipt time.
- The equivalence harness also needs both at once: it pins "today" (REQ-TEST-239 criterion 17) while the bootstrap runs a replay clock.
- **Fix:** the requirement should state that the replay clock replaces only the stamp, that the pinned time only replaces "today", and that both can be active together, with the replay clock falling back to the pinned time before its first anchor.

**B2. The hooks in REQ-PIPE-383 cannot carry what REQ-PIPE-382 criterion 5 moves into them.** Criterion 1's hook runs "before each arrival and after the last". The code needs more than that:
- `correction_replay.for_arrival` (arrival_lifecycle.py lines 168-179) is a context manager. It reverts later corrections around an arrival's processing, so it is a scope, not a before-call.
- The anchor at arrival_lifecycle.py line 241 sits inside `staged_as_it_arrives`' `prepare`. It runs once per co-arriving arrival.
- `decision_log._recorded_at` (lines 965-973) moves the clock forward for **every** decision recorded during a replay. That includes rule-made ones written deep inside promotion, where no bootstrap hook can reach.

So either the hook set has to grow into a protocol (before, around, per staged file, on each decision), or the design changes. This is question QA below.

**B3. The scenario-map split contradicts itself.**
- REQ-GEN-386 criterion 6 moves the map's writer (`build_map`/`write_map`) to the generator.
- But the writer imports `qa_tools.common.scenarios` (scenario_map.py line 55, `parse_register`), which REQ-GEN-381 criterion 1 moves to bootstrap/. The generator importing the bootstrap is forbidden.
- The writer also imports `dataset_status.status_words` from the real pipeline (line 56).
- `Placement`/`read_placements`/`PLACEMENTS_FILE` have no home. Their readers are generator/targets.py, the bootstrap's scripted_decisions and scripted_corrections, and cli/scenarios.py.
- The vocabulary REQ-GEN-386 criterion 4 assigns to scenarios/ (SUBJECTS, AS_AT_PANEL and the rest) lives in **scenario_map.py lines 88-95**, not in scripted_decisions.

**Fix:** put the register parser, the placements reader and the vocabulary in scenarios/. Take "scenarios" out of REQ-GEN-381 criterion 1's list. Move `status_words` with the status order under REQ-PIPE-390. The dashboard keeps only `read_map_data`. Keith's Q4 of 2026-11-02 supports this ("REJECTED the generator owning the readers"), but it departs from the split overview's sentence that "the TS register's parser goes to bootstrap/", so tell him.

**B4. REQ-PIPE-380 criterion 9 names a function that cannot move and leaves out several that must.**
- `promotion.next_receipt` opens `supply_db` and queries `qa.delivery_file` (promotion.py lines 466-472). It cannot go into asset_model/ under criterion 8 or the SECURITY NFR. The generator only calls `effective_at_for`, so drop `next_receipt`.
- Missing from the list, each of which will trigger criterion 13 mid-build:
  - `arrivals.arrivals_for`, called by generator/driver.py line 273. The same module's `arrivals_from_records` reads the database and S3 inside a function.
  - `correction_apply._declared` with `correction_trial.working`, called by generator/correction_claims.py and scenario_injection.py line 237. `_declared` reaches `agreement_freeze`, which runs `git` via subprocess.
  - check_lifecycle's closure: `check_fingerprint` (rfc8785, frozen_defaults), `check_id`, and `file_checks.TOOL`/`check_id_for`. file_checks is a database-touching module.
  - `amber_setting` → `schemas` (801 lines) → `vocab`.
- asset_model/ will be roughly 2-2.5x the 3,649 lines quoted.
- **Fix:** put a full closure list, with line counts, in the requirement before sign-off. Add "no subprocess, no git" to criterion 8, so git-reading code never ships as shared code.

**B5. REQ-PIPE-385 criteria 1 and 6 ("pass every `mothman check` gate") cannot be met as worded.**
- With the generator unimportable, these gates fail by design:
  - `providers` (`generator.validate_providers`, cli/check.py line 87)
  - `scenarios validate`
  - `scenario map --check`
  - `pytest`, because tests import the generator
- The criteria need to name the synthetic-only gates. Those gates should be skipped by name where the asset has no synthetic/ folder, and criterion 6 should run `mothman check --no-pytest` or a named set of gates.
- Separately, criterion 2 decides what the CLI lists by whether the parts can be imported. Two cautions:
  - `importlib.util.find_spec` would still find the package under criterion 6's import blocker, so the detection must match the blocking method.
  - A real import at CLI start-up would break REQ-PIPE-380's NFR that CLI import time is unchanged.

**B6. Several gates and config lists would silently stop covering the moved code — a false green on each.** None of these has a criterion today:
- `validate_caches.SCANNED` (line 50) and `validate_collections.SCANNED` (line 39), plus the latter's path special case at line 93. Moved code would escape REQ-PIPE-254's cache gate and the collection-naming gate.
- The coverage source: pyproject.toml line 175, cli/check.py `COVERAGE_PACKAGES`, and test.yml lines 304 and 589. asset_model/, bootstrap/ and scenarios/ would be unmeasured while `fail_under` still passes.
- replay_inputs `INPUTS`/`REPLAY_INPUTS` plus a `KEY_PREFIX` bump. REQ-GEN-381 criterion 7 covers the new packages, but not REQ-QAC-387's new root file-checks.yaml, which also needs to be in validate-config.yml's `paths:`.

Each needs a criterion in the requirement that creates or moves the path.

## Non-blocking findings

- **Overlap with existing code.** Three new syntax-tree readers are proposed: REQ-TEST-384's gate, REQ-PIPE-376 criterion 8 (underscore names) and REQ-PIPE-390 criterion 4 (status ranking). validate_caches.py already walks syntax trees. Build one walker, and make 376 c8 and 390 c4 rules of the imports gate rather than two more scanners. I found nothing else that already does what the batch proposes; no existing dbt-packages agreement gate exists, so REQ-TEST-388 is new.
- **Register and test churn.** About 323 `implemented_by`/evidence lines in requirements.yaml name the moving qa_tools/common files. Rewriting them is a register-claim edit, so ask Keith to sign one "path-only rewrite" in REQ-PIPE-380/REQ-GEN-381. Tests have about 425 import sites and about 57 monkeypatches of module attributes such as `replay_clock`/`asset_time`/`schedule`. A patch left on the old module silently stops applying, and the test passes without testing anything.
- **REQ-PIPE-382 criteria 9-10 cannot be evidenced by the compare.** equivalence.py's `CLOCK_COLUMNS` normalise those instants away, so "list every moved instant" needs a raw dump of those columns instead. If QA is answered (a), the criteria go away.
- **Q6 misses one caller.** `dashboard/embed_dashboard_data._slots_by_dataset` (lines 359-371) catches `ScheduleConfigError` and silently drops a dataset's slots. Under Q6 a date before the first version would make a dataset's timeline vanish from the page without a word. Name it in REQ-PIPE-378.
- **REQ-PIPE-378 open question 3 (the horizon).** (a) is right for look-ups. But the dashboard's 366 days is a display window, and (a) triples the future slots of every daily dataset embedded in the page, which grows at 30 collections. Have Keith confirm that explicitly, or keep the display window out of the horizon. Send it to delivery-dashboard-ux too.
- **REQ-QAC-387.** The lifecycle gate compares against the base commit. Merging two old per-asset files into one root file needs a many-to-one moved_paths entry, or every file check reads as new on that push.
- **Fixture asset for REQ-PIPE-379 criterion 5 and REQ-PIPE-385 criterion 6.**
  - Share one fixture asset between them.
  - It needs copied dbt_packages (no network) and the test database.
  - "Costs seconds" is unrealistic; a real four-tool run takes tens of seconds or more.
  - These tests cannot be marked critical.
- **REQ-TEST-384 and REQ-TEST-388.**
  - validate-config.yml runs individual commands rather than `mothman check`, so each gate needs a named `mothman` subcommand.
  - REQ-TEST-384 criterion 1 should also fail any Python file that falls into no side.
- **REQ-GEN-392 risks.**
  - dirty.py gives each injector its own seed, so planting an exact count moves only the faulted rows, which is good.
  - But every future band edit in a Birth Registrations or Child Protection check file will now regenerate the history and may break REQ-GEN-186's scenario agreement. Keith should hear that as a lasting cost of Q5.
- **Risk in Q4 (age_group) is low.** `run_datacontract` records invalidValues rules. If any fault ever aims at age_group, the new single-tier rule empties that rule's amber band and REQ-GEN-392 refuses to generate, which is loud rather than quiet.
- **Later batch (pinned speed mode and rolling anchor).** S2's pinned mode must go through REQ-PIPE-382's seam, or it puts back the replay flag 382 removes, so build 382 and 383 first. R1's fixed test anchor should equal ANCHOR_DATE 2026-09-25, so the pins REQ-GEN-392 re-captures are not re-captured a third time.
- **Security.** No new external access. The clock install now lives in shipped code, guarded only by the asset's own `synthetic: true`. Optionally also refuse it when `MOTHMAN_ENVIRONMENT` is a production one.
- **Scoper's open questions.** I agree with the recommendations for 380 OQ1 (a), as long as the B4 closure is named, 378 OQ1, OQ2 and OQ4, 389 OQ1, and 392 OQ1-3. The only caveat is 378 OQ3, above.

## Fit, components touched, build order

**Structure.** No new command group is needed:
- the gates go under `mothman dashboard validate-*`;
- the bootstrap stays `mothman pipeline bootstrap`;
- the synthetic commands keep their groups, now conditional.

**Components touched.** Six of the seven: GEN, PIPE, QAC, TEST, DASH and DOCS. That is the size of a plans/wider.md cross-component item, not a single scoped change.

**Build order.** Each equivalence capture is a full from-empty bootstrap of about 58 minutes. Recommended order:

| Step | Requirements | Capture |
|---|---|---|
| 1 | 384 + 388, gate-only | None — they cannot change a bootstrap |
| 2 | 380 + 376 + 390 | One |
| 3 | 383 + 382 + 381 | One |
| 4 | 386 + 391 | One |
| 5 | 385 + 379 | One, or none if help and menus are unchanged |
| 6 | 377, then 378 | One each |
| 7 | 387 | One |
| 8 | 389 | One |
| 9 | 392, last | One |

- Anything with a "stop and report to Keith" outcome (377 c5, 378 c20, 389 c12) must land **before** 392, or the history is regenerated twice.
- Do one sandbox `reset-synthetic` + bootstrap after 392, not after 389. Run the deployment-half tests only after that reset.
- Expect one hand-started test.yml cache miss after 392.

## Code-quality expectations for the builder (for delivery-critic to check)

- No forwarding modules. After each move, `grep` for the old dotted path across code, tests, monkeypatch strings and requirements.yaml should return zero hits.
- For every monkeypatch of a moved module, prove the patch still takes effect by breaking it once and watching the test fail.
- Extend asset_time with the stamping clock. Do not add a third time module. Its docstring states the stamp-versus-today rule.
- Wherever a module is split (arrivals, check_lifecycle, scenario_map, evidently_common), each half's docstring names the other half and why the cut sits there.
- The imports gate reuses one syntax-tree walker. Every failure names file, line, both sides and the module. The allowlist file says on each entry which requirement removes it.
- Every fallback caller of the new Q6 error has a failing-first test naming that caller.

## Sketch: where the unhomed pieces should land

- **asset_model/:** asset_time and its clock, hierarchy, schedule, slots, the registry's declaration half, check_bands and check_lifecycle's working-tree parsers with their closure, the drift module, the status order and `status_words`.
- **Real pipeline keeps:** adapter loading, `next_receipt`, the git-comparing lifecycle gate, agreement_freeze's git reads, `arrivals_from_records`.
- **scenarios/:** the TS register parser, the placements reader, the map vocabulary, the scripted_decisions.yaml reader.
- **generator/:** the map writer.
- **bootstrap/:** the players, correction_replay and the replay clock's simulated half.

## New questions for Keith (one batch of four)

**QA. How the replay moves the clock (REQ-PIPE-382/383).**
- (a) The asset_model clock offers neutral events, such as "received at X" and "a decision takes effect at Y". The wall clock ignores them and an installed replay clock acts on them. The pipeline keeps those calls but imports nothing of the replay, and no recorded instant moves.
- (b) A hook protocol the bootstrap passes in, with before, around, per-staged-file and on-each-decision calls threaded down to promotion. This is what v5 implies, and the hook surface gets large.
- (c) Keep v5's two hooks and accept that rule-made decisions stop moving the clock. That changes recorded instants widely.
- **Recommend (a).** It meets "the pipeline never knows a replay is running" and removes the instant-evidence problem.

**QB. The generator checks its placements against the pipeline's arrival recognition (`arrivals.arrivals_for`), which reads the delivery tree — that is state, not configuration.**
- (a) Move tree recognition into asset_model/ and widen its charter to "configuration and the delivery tree, never the database".
- (b) Move those checks (`resolve_run_ids` and its neighbours) out of the generator into the bootstrap. Standalone generation then writes placements without run ids.
- (c) Leave one permanent allowlist entry.
- **Recommend (a).** Q1 of 2026-11-02 already said the pure functions move, and (b) changes what `generate-synthetic-data` writes.

**QC. `mothman population --dirty` under REQ-GEN-392.** It runs with no asset selected and dirties both Birth Registrations (daily) and Child Protection (quarterly) tables in one process.
- (a) Population keeps its own literal rates, held in synthetic_data_generator/ as exploratory defaults.
- (b) It reads both assets' bands, which adds a third exception to REQ-PIPE-342 criterion 8.
- (c) It needs one selected asset and dirties only that asset's tables.
- **Recommend (a).** Its output is recorded nowhere.

**QD. How often to take equivalence captures (~58 minutes each).**
- (a) Once per build group, as in the order above — about 8, and none for gate-only commits.
- (b) Once per requirement — about 14.
- (c) A first and a last only.
- **Recommend (a).** (c) loses the ability to say which change moved what.
