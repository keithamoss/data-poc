# REQ-DOCS-358 - the wording for Keith to approve

Drafted 2026-11-15 (Perth), for split tranche T5. **Nothing here is applied.**
This file edits nothing else. The main session applies what Keith approves to
`requirements.yaml`, CLAUDE.md, README.md and `.env.example`.

**What it was checked against**
- The register, CLAUDE.md, README.md and `.env.example` on `work` at `dad4ca1c`
  (T1 and T4 merged).
- `wip/split-t2` at `da5bd1d4` (REQ-PIPE-345, not merged), read with
  `git show wip/split-t2:<path>`.
- `wip/split-t3` at `3aa2d022` (REQ-PIPE-365 and REQ-TEST-353, not merged).
  A19 and A43 describe what T3 does.

No tests were run. Every "CURRENT" below is quoted from `requirements.yaml` at
`dad4ca1c`. Where the text has moved on since REQ-DOCS-358's own decisions
quoted it (an `AMENDED ...` suffix added, a requirement retired), I say so.

## How to read it

**When** says in which change the item is applied (REQ-DOCS-358 c1: each
amendment goes in the change that builds the requirement it serves):
- **NOW**: the requirement it serves is already built on `work`, so it can go
  in T5.
- **T2**: with `wip/split-t2`'s merge (REQ-PIPE-345).
- **T3**: with `wip/split-t3`'s merge.
- **LATER (REQ-x)**: the requirement it serves is one of the split's features,
  which Keith put after #134's core and the speed batch (decisions-2026-11-01,
  "Finishing the split"). The wording can be approved now and applied then.

**Mechanics:**
- A rewording ends with ` AMENDED <date applied> by <requirement>.`, after any
  `AMENDED` suffix already there.
- A retirement is a `retired_criteria:` entry (`criterion`, `date`, `by: Keith`,
  `replaced_by`, `reason`). The criterion's text is left as it is, and its
  tests are removed in the same change.

**CHOICE** marks a place where the wording is a genuine choice. Each one gives
the options and a recommendation. There are 12, all listed in section 6.

## Contents

1. Batch 1 - pure path renames (9 amendments, 16 criteria), plus 4
   dangling-reference fixes and one blanket-rule gap.
2. Batch 2 - retirements (14 criteria, plus A20 withdrawn).
3. Batch 3 - substantive rewordings (38 items: 29 amendments, C1 and
   A36 included, 3 knock-ons, 5 found beyond the list, and c3 itself).
4. CLAUDE.md, README.md and `.env.example`.
5. The plans entries criterion 4 takes out.
6. The genuine choices, in one list.

Each knock-on criterion on the REQ-PIPE-345 list is placed by kind:
- Already an amendment: REQ-PIPE-049 c1/c7 are A1/A3; REQ-PIPE-110 c1, c10,
  c11, c25 and c35 are A4/A7/A8; REQ-PIPE-181 c9 is A10; REQ-PIPE-331 c2 is
  A13; REQ-QAC-330 c6 is A14.
- Retirements (batch 2): REQ-PIPE-050 c8 and c14, REQ-PIPE-320 c13,
  REQ-PIPE-378 c5, REQ-PIPE-379 c3.
- Rewordings (batch 3): REQ-PIPE-111 c2 and c4, REQ-PIPE-113 c10.

---

## 1. Batch 1 - pure path renames

In each of these, only the file's place changes, or the scope narrows from
"the asset" to "the selected asset" or "each asset", which one-asset-per-process
already makes true. The meaning does not change.

### A15 (part) - REQ-PIPE-107 criterion 1. When: NOW (REQ-PIPE-343, built)
- **Current:** "THE SYSTEM SHALL record, in the database itself, the data asset id (contract/data-asset.yaml's data_asset_id) and the environment id that database belongs to."
- **Proposed:** "THE SYSTEM SHALL record, in the database itself, the data asset id (the selected asset's data_asset_id, REQ-PIPE-343) and the environment id that database belongs to."
- **Why:** contract/data-asset.yaml no longer exists; each asset has its own.

### A18 - REQ-PIPE-240 criteria 1, 2, 4 and 9. When: NOW (REQ-PIPE-342, 363 and 369, built)
- **c1 current:** "THE SYSTEM SHALL declare on each collection in contract/data-asset.yaml's hierarchy a `short` and a `run_prefix` - bdm and run_ for Civil Registration, cp and cp_run_ for Child Protection."
- **c1 proposed:** "THE SYSTEM SHALL declare on each collection in its asset's data-asset.yaml hierarchy a `short` and a `run_prefix` - bdm and run_ for Civil Registration, cp and cp_run_ for Child Protection."
- **c2 current:** "THE SYSTEM SHALL provide one registry module that lists collections only from the hierarchy, in hierarchy order, and resolves a collection by id, by short or by run_prefix, and a dataset by id through one dataset-id index across every collection."
- **c2 proposed:** "THE SYSTEM SHALL provide one registry module that lists collections only from the selected asset's hierarchy, in hierarchy order, and resolves a collection of that asset by id, by short or by run_prefix, and a dataset by id through one dataset-id index across every collection of that asset."
- **c4 current:** "THE SYSTEM SHALL load each collection's adapter only from the qa_tools.collections package, by a module name derived from the collection id, and SHALL NOT import a module path taken from configuration."
- **c4 proposed:** "THE SYSTEM SHALL load each collection's adapter only from its asset's collections/ folder, by a file path built from the asset and a module name derived from the collection id (REQ-PIPE-369), and SHALL NOT import a module path taken from configuration."
- **c9 current:** "THE SYSTEM SHALL exempt from criterion 8 contract/, qa_tools/collections/, generator/collections/ and aws/, and in the scenario register only the INJECTIONS and INHERITING_DATASET values, each exemption listed in the gate with its reason."
- **c9 proposed:** "THE SYSTEM SHALL exempt from criterion 8 assets/ and aws/, and in the scenario register only the INJECTIONS and INHERITING_DATASET values, each exemption listed in the gate with its reason."
- **Why:** the adapters are loaded by path from `assets/<asset>/collections/` (`qa_tools/common/assets.py`). `validate_collections.EXEMPT_DIRS` is already `{"assets", "aws"}` on `work`, so the status audit's surprise 6 is fixed and c9 is now true as proposed. c2 adds "of that asset" to the dataset-id index, which REQ-PIPE-364 c3 (uniqueness within an asset) needs.

### A21 (part) - REQ-QAC-241 criteria 4, 5, 8 and 11. When: NOW (REQ-QAC-368 and REQ-GEN-370, built)
For criterion 2, see batch 3 (CHOICE G3).
- **c4 current:** "THE SYSTEM SHALL keep each collection's dbt models, sources, schema files and singular tests under dbt_project/models/<collection_id>/ and dbt_project/tests/<collection_id>/, leaving shared macros and generic tests where they are."
- **c4 proposed:** "THE SYSTEM SHALL keep each collection's dbt models, sources, schema files and singular tests under its asset's dbt project, assets/<asset>/dbt/models/<collection_id>/ and assets/<asset>/dbt/tests/<collection_id>/, with shared macros and generic tests in the shared local package dbt_shared/ (REQ-QAC-368)."
- **c5 current:** "WHEN `mothman check` runs, IF a dbt model, source, schema file or singular test sits outside every collection's folder and is not a shared macro or generic test, or two collections declare a singular test of the same name, THEN THE SYSTEM SHALL fail naming each."
- **c5 proposed:** "WHEN `mothman check` runs, IF a dbt model, source, schema file or singular test of an asset's project sits outside every one of that asset's collection folders, or a file in dbt_shared/ is not a shared macro or generic test, or two collections of one asset declare a singular test of the same name, THEN THE SYSTEM SHALL fail naming each."
- **c8 current:** "THE SYSTEM SHALL derive the check-source lists in validate_check_lifecycle.py, tables_read.py, soda_common.py, check_bands.py and check_lifecycle.py from the registry - each collection's contract, Soda, Evidently and retired-sibling files and its dbt folders - plus the shared dbt files and contract/file-checks.yaml."
- **c8 proposed:** "THE SYSTEM SHALL derive the check-source lists in validate_check_lifecycle.py, tables_read.py, soda_common.py, check_bands.py and check_lifecycle.py from the selected asset's registry - each collection's contract, Soda, Evidently and retired-sibling files and its dbt folders - plus dbt_shared/ and that asset's file-checks.yaml."
- **c11 current:** "THE SYSTEM SHALL include the new Evidently files and the per-collection dbt folders in validate_check_lifecycle.sources_fingerprint(), so that REQ-PIPE-192's cache sees an edit to them."
- **c11 proposed:** "THE SYSTEM SHALL include each asset's Evidently files and per-collection dbt folders, and dbt_shared/, in validate_check_lifecycle.sources_fingerprint(), so that REQ-PIPE-192's cache sees an edit to them."
- **Why:** this is the layout on disk. `sources_fingerprint()` reads `collections.SHARED_DBT_DIRS` and each collection's dbt folders.

### A23 - REQ-PIPE-248 criterion 7. When: NOW (REQ-PIPE-364, built; reports/<asset>/ already in place)
- **Current, in part:** "THE SYSTEM SHALL declare a `short` on each agency in contract/data-asset.yaml's hierarchy, unique across the asset (REQ-PIPE-240's gate extended to it), and SHALL write every collection's results as reports/results_<agency short>_<collection_id>.json and its dashboard data as reports/<agency short>_<collection_id>_dashboard.json, ..."
- **Proposed:** "THE SYSTEM SHALL declare a `short` on each agency in its asset's data-asset.yaml hierarchy, unique across that asset (REQ-PIPE-240's gate extended to it; REQ-PIPE-364 criterion 3), and SHALL write every collection's results as reports/<asset>/results_<agency short>_<collection_id>.json and its dashboard data as reports/<asset>/<agency short>_<collection_id>_dashboard.json, replacing the four current names, and every reader of those paths, in the same change."
- **Why:** the files are `reports/quarterly/results_cpfs_child-protection.json` and so on. The signed A23 rewrote the results path only; the dashboard-data path is the same rename, so it is added here.

### A26 - REQ-GHUB-258 criterion 1. When: LATER (REQ-PIPE-354)
- **Current:** "THE SYSTEM SHALL take the published dashboard's address from contract/data-asset.yaml, beside the Pages project name, and SHALL NOT hardcode a dashboard address in product code."
- **Proposed:** "THE SYSTEM SHALL take each asset's published dashboard address from that asset's data-asset.yaml, beside its Pages project name, and SHALL NOT hardcode a dashboard address in product code."
- **Why:** one Pages project per asset (REQ-PIPE-354).

### A37 - REQ-PIPE-157 criterion 1. When: NOW (REQ-QAC-368, built)
- **Current:** "WHILE one process runs a collection's arrivals, THE SYSTEM SHALL parse the dbt project in full at most once, every later run reusing dbt's own partial parse, and in full again only if dbt_project/, the profile or a dbt package changes."
- **Proposed:** "WHILE one process runs a collection's arrivals, THE SYSTEM SHALL parse the selected asset's dbt project in full at most once, every later run reusing dbt's own partial parse, and in full again only if that project, dbt_shared/, the profile or a dbt package changes."
- **Why:** `tests/test_dbt_packages_per_asset.py::TestTheParseCacheSeesTheSharedFolder` already proves the dbt_shared/ half.

### A38 - REQ-QAC-223 criterion 8. When: NOW (REQ-QAC-368, built). CHOICE G4
- **Current:** "THE SYSTEM SHALL be covered by a test that runs the changelog gate over a change to dbt_project/macros/matches_regex.sql with no changelog entry and asserts that it fails, naming that file once and every check whose test type it defines."
- **Signed A38:** "... over a change to dbt_shared/macros/matches_regex.sql with no changelog entry and asserts that it fails, naming that file once and every check, in each asset, whose test type it defines."
- **Recommended:** "THE SYSTEM SHALL be covered by a test that runs the changelog gate over a change to dbt_shared/macros/matches_regex.sql with no changelog entry and asserts that it fails, naming that file once and every check of the selected asset whose test type it defines."
- **Why:**
  - The existing test (`tests/test_validate_check_lifecycle.py::test_an_unexplained_macro_edit_fails_naming_the_file_once_and_every_check_it_backs`) builds a one-asset fixture repository, so "in each asset" is not proven.
  - The gate also runs once per asset (`cli/check.py`), so "once" holds per asset run.
  - The other option is to keep A38 as signed and write a two-asset fixture test.

### A39 - REQ-GEN-246 criteria 1 and 3. When: NOW (REQ-GEN-370 and REQ-PIPE-364, built)
- **c1 current, in part:** "... with each collection's rows, seed schedule and period plan in a provider module of its own at generator/collections/<id>.py, separate from the collection's QA adapter."
- **c1 proposed:** "... with each collection's rows, seed schedule and period plan in a provider module of its own at assets/<asset>/synthetic/collections/<module>.py, loaded by path (REQ-GEN-370), separate from the collection's QA adapter." The rest is unchanged.
- **c3 current:** "WHEN `mothman check` runs, IF two providers' declared seed ranges overlap, THEN THE SYSTEM SHALL fail naming both."
- **c3 proposed:** "WHEN `mothman check` runs, IF two providers of one asset declare overlapping seed ranges, THEN THE SYSTEM SHALL fail naming both and the asset."
- **Why:** providers live per asset, and the gate runs per asset (`[daily] providers OK`). REQ-PIPE-364 c3 does not compare seed ranges across assets.

### A40 - REQ-PIPE-089 criterion 10. When: LATER (REQ-DASH-373; snapshots are not yet per asset)
- **Current:** "THE SYSTEM SHALL keep code, contract/*.yaml, the hand-authored check definitions, plans/*.md, CHANGELOG.yaml and dashboard/snapshots/*.html.gz in the repository."
- **Proposed:** "THE SYSTEM SHALL keep code, assets/ (each asset's configuration, check definitions, dbt project, adapters and synthetic configuration), dbt_shared/, plans/*.md, CHANGELOG.yaml and each asset's dashboard/snapshots/<asset>/*.html.gz in the repository."
- **Why:**
  - The contract/ half is already false.
  - Option: apply the assets/ and dbt_shared/ half NOW and the snapshots half with REQ-DASH-373, as two AMENDED markers. I recommend that split, because the criterion is untrue today.

### 1.1 Dangling references T2 leaves (housekeeping, no criterion text). When: T2
T2's own commit message says the requirements gate fails on these. They are `implemented_by` and `linked_tests` entries naming a function or test that T2 deletes. Decisions that mention the function stay, because decisions are history.

| Requirement | Field (line at dad4ca1c) | Entry | Proposed |
|---|---|---|---|
| REQ-PIPE-049 | implemented_by (7763) | `qa_tools/common/schedule.py::dataset_dates_override` | remove; add `qa_tools/common/schedule.py::baseline` |
| REQ-PIPE-110 | implemented_by (24252) | `qa_tools/common/schedule.py::dataset_dates_override` | remove |
| REQ-PIPE-322 | linked_tests (45190) | `tests/test_files_go_to_period_change.py::test_a_fall_is_reported_on_every_calendar_its_collection_names` | remove (a collection names no calendar) |
| REQ-QAC-330 | linked_tests (45554) | `tests/test_linked_datasets.py::TestCriterionSix::test_a_dataset_on_no_shared_calendar` | remove with A14 |

### 1.2 The blanket rule (criterion 2): one gap, and a recount
- **The gap:**
  - c2 maps "an asset-wide file under contract/" to `assets/<asset>/`.
  - But `contract/environments.yaml` moved to `assets/environments.yaml`, which belongs to no single asset.
  - 6 signed criteria in REQ-PIPE-093, REQ-PIPE-255 and REQ-TEST-114 name it.
- **Proposed addition to c2's list of mappings** (CHOICE G12): "..., except contract/environments.yaml, which reads as assets/environments.yaml - ".
- **The recount** is a rough script count at `dad4ca1c`: signed or built, live criteria only, the explicit amendments included. Criterion 2 needs an exact before-and-after count when the sweep runs.

| Path | Criteria | Requirements |
|---|---|---|
| `contract/` | 124 | 69 |
| `dbt_project/` | 11 | 10 |
| `qa_tools/collections/` | 10 | 9 |
| `generator/collections/` | 12 | 10 |
| `reports/` | 8 | 6 |
| `SCENARIOS.md` | 10 | 9 |
| `dashboard/snapshots/` | 7 | 6 |
| `data/` | 27 | 26 |

  No criterion names `qa_tools/collections/base.py` or `generator/collections/base.py`. Those base files stay in the shared tree, so the rule's mapping of those two folders is safe.

---

## 2. Batch 2 - retirements

Each is a `retired_criteria:` entry, with its tests removed in the same change. T2 has already removed the tests and code for every one marked T2.

### A3 - REQ-PIPE-049 criterion 7. When: T2. CHOICE G1
- **Current:** "THE SYSTEM SHALL let a dataset override its calendar with its own authored dates instead of subsetting it."
- **Signed A3 (a restatement):** "THE SYSTEM SHALL NOT let a dataset state authored dates of its own; a dataset slower than its baseline owes a subset of the baseline's periods (REQ-PIPE-345)."
- **Recommended, retire:** replaced_by `[REQ-PIPE-345]`; reason "A dataset states no dates of its own (REQ-PIPE-345 criteria 3 and 4): a slower one owes a subset of its asset's baseline periods, and the gate refuses own dates. T2 removed schedule.dataset_dates_override and its tests."
- **Why:**
  - The restatement repeats REQ-PIPE-345 c3/c4, so two criteria would state one refusal.
  - A7 and A8 retire the same feature in REQ-PIPE-110 rather than restate it.

### A7 - REQ-PIPE-110 criteria 10 and 11. When: T2
- **c10 current:** "THE SYSTEM SHALL let a collection name a calendar, and SHALL apply that calendar to every dataset in the collection that names none of its own."
- **c11 current:** "WHERE a dataset names its own calendar, THE SYSTEM SHALL use it in preference to the one its collection names."
- **Proposed:** both retired. replaced_by `[REQ-PIPE-345]`; reason "No collection or dataset names a calendar: every calendared dataset is on its asset's baseline (REQ-PIPE-345 criteria 2 and 3). T2 removed Agreement.collections, defaults_for's own-calendar branch and their tests."
- **Why:** T2's `calendar_for_dataset()` returns `baseline()` and reads no `calendar:` key.

### A8 - REQ-PIPE-110 criteria 25 and 35. When: T2
- **c25 current:** "WHERE a dataset states its own authored dates in place of its calendar's, THE SYSTEM SHALL hold them as effective-dated versions with a structured changelog, as a calendar's are, in the shape REQ-PIPE-111's freeze reads; and SHALL amend, in the same change, REQ-PIPE-111 so that its freeze and declared-correction rules protect them."
- **c35 current:** "IF a dataset's own authored dates use a period name that any calendar in the file also uses, THEN THE SYSTEM SHALL reject the configuration."
- **Proposed:** both retired. replaced_by `[REQ-PIPE-345]`; reason "A dataset states no dates of its own (REQ-PIPE-345 criterion 3 refuses them). T2 removed own dates, the schema's OwnDates, the freeze gate's own_version/own_date items and the criterion-35 name-clash check, with their tests."
- **Why:** the feature these criteria govern is gone. REQ-PIPE-111 c2 and c4 lose the matching clauses (batch 3).

### A10 - REQ-PIPE-181 criterion 9. When: T2
- **Current:** "IF a dataset names a calendar other than its collection's and would take any participation value from its collection's participation_defaults, THEN THE SYSTEM SHALL reject the configuration unless the dataset states that value itself, naming the dataset, both calendars and each value."
- **Proposed:** retired. replaced_by `[REQ-PIPE-345]`; reason "No dataset or collection names a calendar (REQ-PIPE-345), so a dataset cannot be on a calendar other than its collection's. T2 removed the refusal (correction_apply._on_own_calendar and its branch) and its tests."
- **Why:** the case cannot arise.

### Knock-on - REQ-PIPE-050 criterion 8. When: T2
- **Current:** "THE SYSTEM SHALL reject a dataset that both subsets and overrides its own calendar."
- **Proposed:** retired. replaced_by `[REQ-PIPE-345]`; reason "A dataset can no longer override its calendar (REQ-PIPE-345 criterion 3), so subsetting is the only form left. T2 removed the refusal with dataset_dates_override, and TestSubsettingAndOverridingAreDifferentActs with it."
- **Why:** there is nothing left to do both of.

### Knock-on - REQ-PIPE-050 criterion 14. When: T2
- **Current:** "THE SYSTEM SHALL reject a dataset naming a calendar the asset does not define."
- **Proposed:** retired. replaced_by `[REQ-PIPE-345]`; reason "No dataset names a calendar: a `calendar:` key on a dataset is itself refused (REQ-PIPE-345 criterion 3). T2 removed the unknown-calendar error and its typo hint (ConfigError.cause/cause_hint) and test_a_calendar_the_asset_does_not_define_is_rejected."
- **Why:** the stronger refusal in REQ-PIPE-345 replaces it.

### Knock-on - REQ-PIPE-320 criterion 13. When: T2
- **Current:** "IF a collection states a non-zero files_go_to_period on a version in force on the date of any round of a dataset of it that carries its own authored dates list (schedule.dataset_dates_override), THEN THE SYSTEM SHALL reject the configuration, naming the collection, the dataset and the version, and saying that a dataset with its own dates is supported only at 0."
- **Proposed:** retired. replaced_by `[REQ-PIPE-345]`; reason "No dataset carries its own dates (REQ-PIPE-345 criterion 3), so files_go_to_period applies to every calendared dataset alike. T2 removed the refusal and TestADatasetWithItsOwnDatesIsOnlySupportedAtZero."
- **Why:** the refusal it guards cannot be reached.

### Knock-on - REQ-PIPE-378 criterion 5 (signed 2026-11-14, not started). When: T2
- **Current:** "IF a dataset's own dates name a round before its calendar's first version, THEN `mothman schedule validate` SHALL fail, reported in the gate's existing form (validate_schedule._report: under the calendar file, scoped to the dataset, a problem line and a fix line), naming the dataset, the round, the calendar and its first version. (No dataset in either asset declares own dates at 72ec04d7.)"
- **Proposed:** retired. replaced_by `[REQ-PIPE-345]`; reason "Own dates are refused outright (REQ-PIPE-345 criterion 3), so no dataset's own dates can name a round; a round before the baseline's first version is criterion 4's case."
- **Why:** it is moot before it is built. Criterion 4 still covers the baseline's own rounds.

### Knock-on - REQ-PIPE-379 criterion 3 (signed 2026-11-14, not started). When: T2. CHOICE G6
- **Current:** "THE SYSTEM SHALL NOT branch on an asset's name or a calendar's name anywhere outside that asset's own folder: generator/scenario_injection.py line 1418's test for a calendar named 'daily' SHALL read whether the calendar version in force is a cadence rule instead."
- **Recommended, retire:** replaced_by `[REQ-PIPE-345, REQ-PIPE-342]`; reason "Overlaps: a calendar's name in shared code is REQ-PIPE-345 criterion 6's (built in T2: scenario_injection._lands_in asks Calendar.kind), and an asset's name in code is REQ-PIPE-342 criterion 5's ('SHALL NOT hold a list of assets, or name an asset, anywhere in code')."
- **Alternative:** restate c3 as "THE SYSTEM SHALL read every asset's baseline kind through asset_model/'s loader (criterion 1), never by testing an asset's or a calendar's name (REQ-PIPE-342 criterion 5, REQ-PIPE-345 criterion 6)." This keeps the asset_model/ angle.
- **Why retire:** both halves of c3 are already owned by built criteria, and its line number is stale.

### A13 (part) - the calendar_differs half of REQ-PIPE-331 criterion 2
This half is restated in batch 3, not retired as a separate criterion. The same change must also:
- delete `unrunnable.CALENDAR_DIFFERS`;
- delete `build_dashboard_data`'s calendar_differs branch (`pipeline/build_dashboard_data.py:394`);
- delete the template's wording branch (template:6829);
- delete `run_reads.declaration_problems`'s different-calendar branch;
- delete the calendar_differs cases in `tests-js/not-in-agreement.test.js:99` and `tests-js/geocoding-critic-fixes.test.js:63`;
- remove REQ-PIPE-331's `unmet_criteria` entry for "Criterion 2, the calendar_differs half". It was unreachable and is now gone.

**T2 left all of this code in place**, and said so in its decisions ("NOT RETIRED HERE, for T5's amendments"). So A13 is a code change in T5, not wording alone.

### A20 - REQ-TEST-239 criterion 1: WITHDRAWN
- REQ-TEST-239 was retired whole on 2026-11-14 (by Keith, replaced_by REQ-TEST-393: "the test suite is the proof that a refactor is sound").
- A retired requirement is not amended.
- **Proposed:** strike A20 from REQ-DOCS-358's list, noting "WITHDRAWN 2026-11-15: REQ-TEST-239 retired".

### A30, A34, A35 - REQ-DASH-209 criteria 6, 13 and 14. When: LATER (REQ-DASH-367)
- **c6 current, in part:** "THE SYSTEM SHALL give the view its own address in the dashboard's existing routing - #/agency/<agency>/collection/<collection>/period/<period> ..."
  - **Proposed:** retired. replaced_by `[REQ-DASH-367]`; reason "The period route is retired: old links open the agency page with the period set (REQ-DASH-367 criterion 3), and every link to the view goes there (criterion 6)."
- **c13 current:** "IF the address names an agency, collection or period the dashboard does not hold, THEN THE SYSTEM SHALL show the existing not-found page (renderNotFound) naming what was not found, and SHALL NOT show an empty view."
  - **Proposed:** retired. replaced_by `[REQ-DASH-367]`; reason "A retired period route's unknown agency, collection or period is REQ-DASH-367 criterion 5's."
- **c14 current, in part:** "THE SYSTEM SHALL show beside the view's h2 a link to the previous period's composition view and one to the next period's ..."
  - **Proposed:** retired. replaced_by `[REQ-DASH-367]`; reason "The previous/next links move to the agency page and set the global period control (REQ-DASH-367 criterion 2)."
- **Why:** these are unchanged from the signed A30/A34/A35. Their current text matches what REQ-DOCS-358 quoted.

---

## 3. Batch 3 - substantive rewordings

### 3.1 The calendar model (REQ-PIPE-345). When: T2 unless marked

**A1 - REQ-PIPE-049 criterion 1.** CHOICE G1
- **Current:** "THE SYSTEM SHALL hold one or more NAMED delivery calendars per data asset, and each dataset SHALL name exactly one of them."
- **Proposed:** "THE SYSTEM SHALL hold at most one NAMED delivery calendar per data asset, its baseline, and SHALL put every dataset that does not declare no calendar (REQ-PIPE-106) on it (REQ-PIPE-345)."
- **Why:**
  - This is A1 as signed, with "(REQ-PIPE-106)" added so that "declare no calendar" points at the key.
  - c1 is REQ-PIPE-049's headline, so it is restated rather than retired.
  - The title, "The asset carries named delivery calendars, and each dataset names one", is history and is left. Option: retitle it "The asset carries one named baseline calendar, and every calendared dataset is on it".

**Extra - REQ-PIPE-049 criterion 5 (A2's target).** CHOICE G10
- **Current:** "IF a dataset naming a cadence-rule calendar also names delivery months, THEN THE SYSTEM SHALL reject the configuration rather than ignoring the months."
- **Why it needs a word now:** after T2, "naming" is false, because no dataset names a calendar. A2 rewrites c5 for weekdays, but only with REQ-PIPE-346 (LATER).
- **Recommended interim edit at T2:** "IF a dataset on a cadence-rule baseline also names delivery months, THEN THE SYSTEM SHALL reject the configuration rather than ignoring the months." A2 then replaces it in full later.
- **Alternative:** leave it until A2.

**A4 - REQ-PIPE-110 criterion 1.** (Serves REQ-PIPE-342 and 345.)
- **Current:** "THE SYSTEM SHALL hold every delivery agreement belonging to a data asset in one file, contract/calendar.yaml - its named calendars, which calendar each collection and dataset is on, and each dataset's participation."
- **Proposed:** "THE SYSTEM SHALL hold every delivery agreement belonging to a data asset in one file, its asset folder's calendar.yaml - its baseline calendar, each collection's files_go_to_period and participation defaults, and each dataset's participation."
- **Why:** this is the file's real shape on T2: `calendars` (one), `collections` (files_go_to_period, participation_defaults), `datasets` (participation, corrections). It is unchanged from the signed A4.
- **Note:** the title "contract/calendar.yaml is the one place a delivery agreement lives" is history; option to retitle it "an asset's calendar.yaml is ...".

**A9 - REQ-PIPE-110 criterion 18.**
- **Current:** "IF a dataset in the asset's hierarchy has neither a calendar nor a deliberate no-calendar declaration, or contract/calendar.yaml names a dataset or collection the hierarchy does not hold, THEN THE SYSTEM SHALL reject the configuration naming both files."
- **Proposed:** "IF the asset declares no baseline calendar while a dataset of its hierarchy has no deliberate no-calendar declaration, or the asset's calendar.yaml names a dataset or collection its hierarchy does not hold, THEN THE SYSTEM SHALL reject the configuration naming both files and the asset."
- **Why:** T2's `calendar_for_dataset()` raises in exactly the first case. Unchanged from the signed A9.

**A12 - REQ-PIPE-262 criteria 1, 6 and 12.** When: NOW (REQ-PIPE-352, built). The code is the same before and after T2.
- **c1 current:** "THE SYSTEM SHALL group a bootstrap's collections into streams derived from configuration alone, two collections falling in one stream whenever any dataset of one resolves (schedule.calendar_for_dataset) to a calendar any dataset of the other resolves to, transitively, and SHALL hold no list of collections or calendars of its own."
- **c1 proposed:** "THE SYSTEM SHALL replay every collection of the selected asset that holds a calendared dataset as one stream, and each collection all of whose datasets declare no calendar (REQ-PIPE-106) as a stream of its own, and SHALL hold no list of collections of its own."
- **c6 current:** "WHEN a bootstrap of every collection runs without --sequential, THE SYSTEM SHALL run its streams side by side, each in a process of its own, so that a collection on a calendar no other collection uses (Birth Registrations, daily) still runs beside the quarterly stream."
- **c6 proposed:** "WHEN a bootstrap of every collection of the asset runs without --sequential, THE SYSTEM SHALL run its streams side by side, each in a process of its own, so that a no-calendar collection's stream runs beside the asset's calendared stream; the daily and quarterly assets are bootstrapped separately (REQ-PIPE-352)."
- **c12 current, in part:** "WHEN the synthetic history is bootstrapped from empty with all three collections, THE SYSTEM SHALL record ... AMENDED 2026-10-30 by REQ-GEN-325."
- **c12 proposed:** "with all three collections" becomes "the quarterly asset bootstrapped from empty". The rest is unchanged, including the existing AMENDED suffix.
- **Why:**
  - The signed A12 said "none of whose datasets names a calendar". Once nothing names a calendar, that phrase covers every collection, so it is reworded to "declare no calendar".
  - `bootstrap.streams()` still groups transitively through `calendar_for_dataset()`. With one baseline per asset that grouping is exactly the proposed c1.
  - c13 and c14 were retired 2026-11-15 (REQ-TEST-393).

**A13 - REQ-PIPE-331 criterion 2, plus REQ-PIPE-332 c10 and REQ-DASH-337 c12.** (Serves REQ-PIPE-345 and 364.) CHOICE G2
- **331 c2 current:** "IF a check declares a read of a table no dataset in the hierarchy owns, or of a dataset that is never on the same calendar as the declaring dataset in any period, or that names no calendar at all, THEN `mothman check` SHALL fail, naming the check, the table and the reason; and WHERE the two datasets are on different calendars for a given period, THE SYSTEM SHALL record the check NOT APPLICABLE for that period - in left_out with the reason code calendar_differs (REQ-PIPE-332 criterion 10), counting toward nothing - and SHALL record neither red nor a result for it."
- **Signed A13:** "IF a check declares a read of a table no dataset in its asset's hierarchy owns, or of a dataset that declares no calendar, THEN `mothman check` SHALL fail, naming the check, the table and the reason."
- **Recommended:** "IF a check declares a read of a table no dataset in its asset's hierarchy owns, or WHERE either the declaring dataset or the dataset it reads declares no calendar, THEN `mothman check` SHALL fail, naming the check, the table and the reason."
- **Why (G2):**
  - Today, a NO-CALENDAR DECLARING dataset reading a calendared table is refused. In `run_reads.declaration_problems`, `mine` is None, which differs from `theirs`.
  - Once the different-calendar branch is deleted, the signed A13 would let that read through silently.
  - The recommended wording keeps today's behaviour. It needs one small rewritten branch in place of the deleted one.
  - Alternative: the signed A13, accepting that such a read passes the gate. That is the quiet direction, so I do not recommend it.
- **332 c10 current:** "THE SYSTEM SHALL record a structured reason code on every left_out entry - not_in_agreement for REQ-PIPE-270 criterion 9's case, not_supplied_by_decision for criterion 7's and calendar_differs for REQ-PIPE-331 criterion 2's - so that the page words each from its code (REQ-DASH-337 criterion 12), never by matching the reason's text."
- **332 c10 proposed:** "THE SYSTEM SHALL record a structured reason code on every left_out entry - not_in_agreement for REQ-PIPE-270 criterion 9's case and not_supplied_by_decision for criterion 7's - so that the page words each from its code (REQ-DASH-337 criterion 12), never by matching the reason's text."
- **337 c12 current, in part:** "... e.g. 'Not checked: Client Register not supplied for 2024-Q2, by decision'), and 'Not checked: <dataset> was on the <calendar> calendar for <period>' for calendar_differs - and SHALL NOT word any entry by matching its reason text. AMENDED 2026-11-01 by REQ-DASH-299."
- **337 c12 proposed:** the same sentence, with ", and 'Not checked: <dataset> was on the <calendar> calendar for <period>' for calendar_differs" struck. The ", for not_supplied_by_decision ..." clause becomes the last item, joined by "and". It ends "... AMENDED 2026-11-01 by REQ-DASH-299. AMENDED <date> by REQ-PIPE-345."
- **Why:**
  - This is the line REQ-DASH-337's own decision said REQ-DOCS-358 would gain, "whichever lands second". Pass-warn-fail landed first, so it is due now.
  - The tests-js cases go with it (batch 2, A13 part).

**A14 - REQ-QAC-330 criterion 6 and REQ-QAC-294 criterion 4.** CHOICE G2
- **330 c6 current:** "IF a linked dataset is not in the hierarchy, is never on the same calendar as linkage-keys in any period, or names no calendar at all, names a source column its contract does not declare, or declares more identifier columns than the contract's id_N, or IF two linked datasets declare the same code, THEN `mothman check` SHALL fail, naming the dataset and the reason."
- **330 c6 recommended:** "IF a linked dataset is not in its asset's hierarchy, or it or linkage-keys declares no calendar, or it names a source column its contract does not declare, or declares more identifier columns than the contract's id_N, or IF two linked datasets declare the same code, THEN `mothman check` SHALL fail, naming the dataset and the reason."
- **294 c4 current, in part:** "IF a dataset's linked_datasets entry names a source not in the hierarchy, one naming no calendar, or one never on the same calendar as the declaring dataset in any period (REQ-QAC-330 decision 15's period-by-period rule), or names a source column ..."
- **294 c4 recommended:** "IF a dataset's linked_datasets entry names a source not in its asset's hierarchy, or where the source or the declaring dataset declares no calendar, or names a source column ..." The rest is unchanged.
- **Why:**
  - `linked_datasets.problems()` on T2 refuses `l_cal is None`, and `l_cal != product_cal`, which is the no-calendar product.
  - The signed A14 drops the second case. The same G2 choice applies here, and the recommendation is the same: keep both sides.
  - The `test_a_dataset_on_no_shared_calendar` test went with T2.

**Knock-on - REQ-PIPE-111 criterion 2.**
- **Current:** "THE SYSTEM SHALL treat each dated calendar entry, each dated entry of a dataset's own authored dates, calendar version, participation version (...) ... AMENDED 2026-10-15 by REQ-PIPE-179 criterion 30. AMENDED 2026-10-30 by REQ-PIPE-321."
- **Proposed:** the same sentence with ", each dated entry of a dataset's own authored dates" struck, so it begins "THE SYSTEM SHALL treat each dated calendar entry, calendar version, participation version (including a collection's default participation), files_go_to_period version (REQ-PIPE-320), ...". The rest is verbatim, and it ends "... AMENDED 2026-10-30 by REQ-PIPE-321. AMENDED <date> by REQ-PIPE-345."
- **Why:** T2 removed the freeze's own_date items. "On its calendar" in the same sentence now means the baseline and needs no change.

**Knock-on - REQ-PIPE-111 criterion 4.**
- **Current, in part:** "... a calendar's on that calendar; a dataset's (its participation, due time, participates, not_expected, own authored dates, effective_to and turned_off_reason) on that dataset's entry; ..."
- **Proposed:** "own authored dates, " struck from the dataset's list. The rest is verbatim, with the AMENDED suffix by REQ-PIPE-345 after the existing one.
- **Why:** there are no own dates left to correct.

**Knock-on - REQ-PIPE-113 criterion 10.**
- **Current:** "THE SYSTEM SHALL compute every slot's instants - from a calendar or from a dataset's own authored dates - through one slot-instants function that filing, the overlap gate (REQ-PIPE-134), the impact preview, the backstop and the dashboard build all call."
- **Proposed:** "THE SYSTEM SHALL compute every slot's instants, from the asset's baseline calendar (REQ-PIPE-345), through one slot-instants function that filing, the overlap gate (REQ-PIPE-134), the impact preview, the backstop and the dashboard build all call."
- **Why:** T2 removed the override branch from `slots._calendar_periods`.

**Found beyond the T2 list, recommended to add (same cause).** Each of these reads wrong once nothing names a calendar:
- **REQ-PIPE-262 c2:**
  - Current: "WHERE a dataset declares it has no calendar (REQ-PIPE-106), THE SYSTEM SHALL leave it out of the grouping, so that a collection none of whose datasets names a calendar is a stream of its own."
  - Proposed: "... so that a collection all of whose datasets declare no calendar is a stream of its own."
- **REQ-PIPE-320 c5:**
  - Current: "IF a collection none of whose datasets names a calendar (REQ-PIPE-106) states files_go_to_period, THEN THE SYSTEM SHALL reject the configuration, saying that a collection with no calendar has no periods to send files to."
  - Proposed: "IF a collection all of whose datasets declare no calendar (REQ-PIPE-106) states files_go_to_period, THEN ...". The rest is unchanged.
  - Read literally after T2, the current text refuses files_go_to_period on every collection.
- **REQ-QAC-039 c9:** "including the calendar a dataset names" becomes "including a dataset's participation and no-calendar declaration".
- **REQ-PIPE-379** (signed 2026-11-14, not started):
  - Title, "... named calendars of authored dates or the daily cadence rule, each dataset picking one ...", becomes "... the asset's one baseline calendar, authored dates or the daily cadence rule ...".
  - c1: "with the calendars' dates and versions per asset" becomes "with the baseline's dates and versions per asset".
  - c6: "WHERE a new asset declares its calendars in its own calendar.yaml" becomes "WHERE a new asset declares its baseline calendar in its own calendar.yaml".
  - Why: REQ-PIPE-379's v6 drafting predates REQ-PIPE-345 being built.

### 3.2 Weekday participation (REQ-PIPE-346 and REQ-DASH-347). When: LATER

**A2 - REQ-PIPE-049 criterion 5.**
- **Current:** as quoted under G10 above.
- **Proposed:** "IF a dataset's participation names periods in a vocabulary its baseline calendar version does not take - months on a daily rule, weekdays on an authored calendar - THEN THE SYSTEM SHALL reject the configuration rather than ignoring them (REQ-PIPE-346)."
- **Why:** unchanged from the signed A2.

**A5 - REQ-PIPE-110 criterion 5.**
- **Current, in part:** "... either as the keyword all or by naming delivery months in full and case-insensitively, naming the month of each round's CALENDAR DATE even where days before is set and whatever the collection's files_go_to_period, and SHALL NOT accept a month number, an abbreviation or a positional index. AMENDED 2026-10-30 by REQ-PIPE-321."
- **Proposed:** "by naming delivery months in full and case-insensitively, naming the month of each round's CALENDAR DATE" becomes "by naming, in full and case-insensitively, the month - or, on a daily baseline, the weekday - of each round's CALENDAR DATE (REQ-PIPE-346)". "which of its calendar's rounds" becomes "which of its baseline's rounds". The rest is verbatim, with the new AMENDED suffix after the existing one.
- **Why:** this is the signed A5, plus "its baseline's", because no dataset has "its calendar" in the old sense.

**A6 - REQ-PIPE-110 criterion 7.**
- **Current:** "IF participates resolves to delivery months for a dataset whose calendar version in force on any of its periods' dates is a cadence rule, THEN THE SYSTEM SHALL reject the configuration, checking each participation version against every calendar version it overlaps."
- **Proposed:** "IF participates resolves to months where the baseline calendar version in force on any of a dataset's periods' dates is a daily rule, or to weekdays where it is authored, THEN THE SYSTEM SHALL reject the configuration, checking each participation version against every calendar version it overlaps."
- **Why:** unchanged from the signed A6.

**A11 - REQ-PIPE-181 criterion 8.**
- **Current, in part:** "... naming the item, each dataset affected, the months newly owed and the periods those rounds fill, and SHALL give the fix to paste: the months, or all, written explicitly, together with the reason a list of some months needs. AMENDED 2026-10-30 by REQ-PIPE-321."
- **Proposed:** "the months newly owed" becomes "the rounds newly owed, named as participates names them (REQ-PIPE-346)". Also "the fix to paste: the months, or all, written explicitly, together with the reason a list of some months needs" becomes "the fix to paste: the months or weekdays, or all, written explicitly, together with the reason a list of some needs".
- **Why:** the signed A11 changed only the first phrase. The fix-to-paste would still say "months" for a weekday list, which REQ-PIPE-346 c2 forbids. This is a small widening.

**A17 - REQ-DASH-182 criteria 2 and 8.**
- **c8 current, in part:** "... 'Monthly' for twelve, otherwise '<N> times a year' - and 'various days' in place of the day ..."
- **c8 proposed:** "... 'Monthly' for twelve, otherwise '<N> times a year', and WHERE a dataset participates by weekday, as REQ-DASH-347 criterion 1 words it - and 'various days' in place of the day ...". The rest is unchanged.
- **c2 current, in part:** "... a participation row 'Not owed — it supplies only in the February and August rounds', naming the months of the rounds it supplies in ..."
- **c2 proposed:** "... a participation row 'Not owed — it supplies only in the February and August rounds' - or, WHERE it participates by weekday, 'Not owed — it supplies only on Mondays' (REQ-DASH-347) - naming the months or weekdays of the rounds it supplies in ...". The rest is verbatim, including "AMENDED 2026-10-30 by REQ-DASH-326."
- **Why:** this is the signed A17, written out in full.

### 3.3 Per-asset state and CI (REQ-PIPE-343, 352 and 365; REQ-TEST-353)

**A15 (part) - REQ-PIPE-107 criterion 12.** When: NOW (REQ-PIPE-343, built)
- **Current:** "THE SYSTEM SHALL mark the sandbox's database in the session-start hook, CI's database in its workflow, the dev container's database as local in .devcontainer/post-create.sh, and each test worker's database as test in its fixture, in the same change that adds the check."
- **Proposed:** "THE SYSTEM SHALL mark each asset's sandbox database in the session-start hook, each asset's CI database in its workflow, each asset's dev-container database as local in .devcontainer/post-create.sh, and each test worker's database as test, for the asset its fixture selects."
- **Why:** the hook marks each `supply_<asset>` with `env mark --confirm <asset>/sandbox` (session-start.sh:139-140). post-create.sh marks each asset's database after T1.

**A19 - REQ-TEST-117 criterion 1.** When: T3
- **Current:** "CI SHALL cache a dump of the bootstrapped database, keyed on a hash of every input that shapes it - generator/, synthetic_data_generator/, pipeline/, qa_tools/, contract/, dbt_project/, cli/pipeline.py, pyproject.toml, uv.lock and the workflow file itself. AMENDED 2026-10-06 (Keith): cli/pipeline.py added, because the bootstrap enters through it - and nothing else under cli/, so ordinary terminal changes still restore."
- **Proposed:** "CI SHALL cache a dump of each asset's bootstrapped database, with that asset's data/<asset>/ paths, keyed on a hash of every input that shapes it - generator/, synthetic_data_generator/, pipeline/, qa_tools/, dbt_shared/, cli/pipeline.py, pyproject.toml, uv.lock, the workflow file itself, that asset's whole folder under assets/ (its dbt project, adapters and synthetic/ included) and assets/environments.yaml (REQ-PIPE-365 criterion 3). AMENDED 2026-10-06 (Keith): cli/pipeline.py added, because the bootstrap enters through it - and nothing else under cli/, so ordinary terminal changes still restore. AMENDED <date> by REQ-PIPE-365."
- **Why:**
  - T3's `replay_inputs.INPUTS` is exactly that shared list plus `assets/<asset>/**`.
  - Its workflow caches `ci-cache/supply_<asset>.dump` and four `data/<asset>/` paths per asset.
  - c5 (synthetic data only, in GitHub's cache) is unchanged.

**A22 - REQ-PIPE-250 criteria 2 and 5** (in progress). When: c2 NOW (REQ-PIPE-352, built); c5 T3 (REQ-TEST-353)
- **c2 current:** "WHEN `mothman pipeline bootstrap` runs from empty on this sandbox with all three collections, THE SYSTEM SHALL finish within 12 minutes of wall clock, in each of three consecutive runs recorded in evidence."
- **c2 proposed:** "WHEN each asset's `mothman pipeline bootstrap` runs from empty on this sandbox, THE SYSTEM SHALL finish within 12 minutes of wall clock, in each of three consecutive runs recorded in evidence."
- **c5 current:** "THE SYSTEM SHALL record the CI deployment half's cache-miss bootstrap time alongside, without a budget of its own."
- **c5 proposed:** "THE SYSTEM SHALL record each asset's cache-miss bootstrap time in the CI deployment half alongside, without a budget of its own."
- **Why:**
  - These are unchanged from the signed A22.
  - For the record, the 2026-11-03 figures are daily 11m24s and quarterly 111m09s (morning report 12, post-build-review #318). So the reworded c2 is unmet for quarterly, as REQ-PIPE-352 c5 already records.

**A43 - REQ-TEST-160 criterion 1.** When: T3
- **Current:** "THE SYSTEM SHALL record with each checkpoint a digest of every delivery's files and receipt in the collection, in receipt order, and one digest of every other input that shapes a replay - REQ-TEST-117 criterion 1's input list, less generator/ and synthetic_data_generator/."
- **Proposed:** "THE SYSTEM SHALL record with each checkpoint a digest of every delivery's files and receipt in the collection, in receipt order, and one digest of every other input that shapes a replay - REQ-TEST-117 criterion 1's input list as amended by REQ-PIPE-365, less generator/, synthetic_data_generator/ and the asset's synthetic/collections/, whose providers are compared as deliveries."
- **Why:**
  - T3's `replay_patterns(asset)` is `REPLAY_INPUTS` plus `assets/<asset>/**`, less `assets/<asset>/synthetic/collections/**`.
  - "as amended by A19" becomes "as amended by REQ-PIPE-365", because once A19 is applied the register names the requirement, not the draft's amendment number.

### 3.4 Folder layout. When: NOW

**A21 (part) - REQ-QAC-241 criterion 2.** CHOICE G3
- **Current:** "THE SYSTEM SHALL keep each agency's contract, Soda, Evidently and retired-check files under contract/<agency-id>/, and only the asset-wide files (data-asset.yaml, calendar.yaml, people.yaml, environments.yaml, file-checks.yaml, scripted_decisions.yaml, presentation.yaml, synthetic_inputs.yaml) at the top of contract/; WHEN `mothman check` runs, IF a collection's file sits outside its agency's folder, THEN THE SYSTEM SHALL fail naming it. AMENDED 2026-11-01 by REQ-QAC-294."
- **Signed A21 c2** lists `eras.yaml` among the synthetic-only files, and carries a parenthetical about the move map.
- **Recommended:** "THE SYSTEM SHALL keep each agency's contract, Soda, Evidently and retired-check files under assets/<asset>/<agency-id>/, each asset's asset-wide files (data-asset.yaml, calendar.yaml, people.yaml, file-checks.yaml, presentation.yaml) at the top of assets/<asset>/, its synthetic-only configuration under assets/<asset>/synthetic/ (REQ-GEN-370 criterion 1), and only environments.yaml at the top of assets/; WHEN `mothman check` runs, IF a collection's file sits outside its agency's folder, THEN THE SYSTEM SHALL fail naming it. AMENDED 2026-11-01 by REQ-QAC-294. AMENDED <date> by REQ-PIPE-342."
- **Why:**
  - `eras.yaml` does not exist yet. It is REQ-GEN-371's (not started), and REQ-GEN-370 c1 already records it unmet.
  - Pointing at REQ-GEN-370 c1, rather than listing the files, avoids a third list that can drift.
  - The move-map parenthetical is dropped because the map was deleted (c8531b7b, REQ-TEST-366 c2).
  - The alternative is the signed list, with or without eras.yaml.

### 3.5 Hosting and the snapshot archive. When: LATER (REQ-PIPE-354 and REQ-DASH-373)
These are unchanged in meaning from the signed amendments. Here they are written out as full sentences where the signed text gave only "becomes".

**A16 - REQ-PIPE-092 criterion 7.**
- **Current:** "THE SYSTEM SHALL name, in the artifact itself, the environment it was built from."
- **Proposed:** "THE SYSTEM SHALL name, in the artifact itself, the data asset and the environment it was built from."
- **Why:** `BUILD_PROVENANCE` (embed_dashboard_data.py:512-548) carries the environment and commit only. Adding the asset is REQ-PIPE-354's work.

**A24 - REQ-PIPE-255 criteria 1, 8, 24 and 30.**
- **c1 proposed:** "THE SYSTEM SHALL deliver the published dashboard by uploading the whole tree prepare_deploy_site() builds - index.html, data/ with every data file and part it references (REQ-DASH-291, REQ-DASH-293), fonts/, vendor/, snapshots/ with every snapshot in the selected asset's archive (REQ-PIPE-354 criterion 8) in the split form REQ-DASH-292 publishes it and a copy of fonts/ and vendor/ beside them, snapshots/manifest.json, and the _headers file of the last criterion - to the selected asset's Cloudflare Pages project by direct upload."
- **c8 proposed:** "THE SYSTEM SHALL take the Pages project name, its production branch name, the dashboard's address and the expected Access sign-in domain from the selected asset's data-asset.yaml, one Cloudflare Pages project per asset (REQ-PIPE-354), and SHALL NOT hardcode any of them in code."
- **c24 proposed:** "the newest archived snapshot in dashboard/snapshots/" becomes "the newest archived snapshot in the selected asset's archive, dashboard/snapshots/<asset>/". The rest is unchanged.
- **c30 proposed:** "WHEN the test suite runs, THE SYSTEM SHALL drive `mothman dashboard publish` end to end for each asset, against a stub wrangler placed first on PATH that records its arguments and environment, including an unchanged second publish that invokes the stub zero times, and SHALL NOT need a Cloudflare account, a token or network access."

**A25 - REQ-PIPE-257 criteria 1, 3, 6, 8, 12 and 14.**
- **c1:** "THE SYSTEM SHALL require Cloudflare Access sign-in for each asset's Pages project's production hostname, <project>.pages.dev, and for every deployment and branch-alias hostname under *.<project>.pages.dev, under that project's own Access applications and policy."
- **c3:** "THE SYSTEM SHALL admit only email addresses listed one by one in each asset's own Access policy, and SHALL NOT admit by email domain, by an Everyone rule, or by a Bypass or Service Auth rule."
- **c6:** "THE SYSTEM SHALL carry a committed runbook, docs/dashboard-hosting.md, giving, once for each asset's Pages project, every console step that creates the Pages project, creates the least-privilege API token, enables One-time PIN, creates both Access applications and the policy, sets the session duration, sets each Access application's CF_Authorization cookie to SameSite=Lax explicitly, and adds and removes a person."
- **c8:** "THE SYSTEM SHALL take the Access sign-in domain it expects (the account's <team>.cloudflareaccess.com) from the selected asset's data-asset.yaml beside the project name."
- **c12:** "THE SYSTEM SHALL provide `mothman dashboard verify-access`, which runs the same check against the selected asset's production hostname and its most recent deployment's URL without uploading anything, and exits non-zero if either is reachable without sign-in."
- **c14:** "WHEN this requirement is first built, THE SYSTEM SHALL be verified once for each asset's project from an environment that can reach Cloudflare: ..." The rest is verbatim.

**A27 - REQ-DOCS-259 criteria 2, 5 and 7.**
- **c2:** "THE SYSTEM SHALL NOT have the repository made private until REQ-PIPE-255, REQ-PIPE-257 and REQ-GHUB-258 are built, a real publish is serving each asset's current dashboard and its snapshots from its own private project, and an allow-listed person other than Keith has signed in to each."
- **c5:** "... `mothman dashboard verify-access` passing for each asset, ..." The rest is verbatim.
- **c7:** "... that the repository is private, where each asset's dashboard is hosted, how a person is given access, ..." The rest is verbatim.

**A41 - REQ-DOCS-259 criterion 6.**
- **Current:** "WHEN the flip is verified, THE SYSTEM SHALL have the gh-pages branch deleted, since nothing publishes to it and every publish it holds is also in the committed snapshot archive."
- **Proposed:** "WHEN the flip is verified, THE SYSTEM SHALL have the gh-pages branch deleted, since nothing publishes to it; the pre-split publishes it holds are no longer in any committed archive (REQ-DASH-373) and remain in the main branch's git history, and every later publish is in its asset's archive."
- **Why:** unchanged from the signed A41.

**A42 - REQ-PIPE-081 criterion 21.**
- **Current:** "THE SYSTEM SHALL state, in the date control's own panel, that the view uses everything known today including decisions made since, and SHALL name the snapshot archive as the way to see what the page itself said on a past date."
- **Proposed:** "THE SYSTEM SHALL state, in the date control's own panel, that the view uses everything known today including decisions made since, and SHALL name this asset's snapshot archive as the way to see what the page itself said on a past date since the asset's first publish after the split (REQ-DASH-373)."

**C1 - CLAUDE.md, three statements about the archive.**
- Keith signed this as drafted on 2026-10-31. It is applied in REQ-DASH-373's deletion change.
- I re-checked it at `dad4ca1c`: all three CURRENT quotes still match CLAUDE.md, at the snapshots row (line 317), line 419 and line 426. No new wording is needed.

### 3.6 The period control (REQ-DASH-355 and REQ-DASH-367). When: LATER
- **A28 - REQ-DASH-209 c1:** "WHILE a period is chosen (REQ-DASH-355), THE SYSTEM SHALL show in each collection's panel on the agency page - daily collections included, one per day - a composition table with one row per dataset of that collection, each saying what the dataset holds in that period as at the end of the date on show - ..." The rest is verbatim from "'Promoted', 'Inherited from <period>', ...".
- **A29 - c5:** "THE SYSTEM SHALL make each dataset's name a real link (<a href>) to that dataset's page at the same date on show and period, and each 'from <period>' a real link to the agency page with that period set (REQ-DASH-367 criterion 6)."
- **A31 - c7 and REQ-DASH-208 c2:**
  - 209 c7: "THE SYSTEM SHALL let TS-55's chip in the test-scenarios panel open the agency page with its period set and its collection's composition table in view, TS-55's coordinate in the scenario map still naming the substituted dataset, with the table as its link's target, so that REQ-GEN-045 criterion 1 needs no change; and SHALL add the table to REQ-DASH-208 criterion 2's subjects, so that TS-55's chip lands with it in view."
  - 208 c2: "... a supply-history row, or a collection's composition table on the agency page (REQ-DASH-367) - and SHALL NOT name it by a CSS selector or a pixel offset."
- **A32 - c8:** "WHERE no dataset of the collection holds anything in the period on the date on show, THE SYSTEM SHALL say so in one line above the rows; and WHERE the date on show is before the period opened, THE SYSTEM SHALL show '<period> had not opened by <date>' in that collection's panel, in place of its table (REQ-DASH-355 criterion 9)."
- **A33 - c12:** "THE SYSTEM SHALL caption each composition table '<collection> · <period name> — what each dataset held at the end of <date on show>', SHALL leave the rail as the agency page's, and SHALL move focus to the caption on arrival from a retired period link (REQ-DASH-367 criterion 3)."
- **A36 - c2, c3, c4, c9, c10 and c11:** no wording change.
  - c3's `contract/people.yaml` is covered by the blanket rule (it becomes "its asset's people.yaml").
  - c10's test is re-pointed by REQ-DASH-367 c7.
  - Note: REQ-DASH-209 still has c7 and c10 unmet against REQ-GEN-206. REQ-GEN-206 was signed 2026-11-15, so their `owner` should move from "REQ-GEN-206 (drafted, unsigned)" to "REQ-GEN-206". This is not REQ-DOCS-358's to change, just seen in passing.
- **Why:** each is unchanged in meaning from the signed amendment, and its current text matches what REQ-DOCS-358 quoted.

### 3.7 REQ-DOCS-358 criterion 3 itself (the .env.example clause). CHOICE G7
- **Current, in part:** "... and .env.example (a MOTHMAN_ASSET= line beside MOTHMAN_SUPPLY_DSN, the two switched together), in the change that lands the split."
- **Why it needs amending:**
  - Since Keith's 2026-11-15 MOTHMAN_PG decision, `.env.example` carries `MOTHMAN_PG` and no `MOTHMAN_SUPPLY_DSN`.
  - "Switched together" describes a world where the DSN named the asset's database.
- **Recommended:** "... and .env.example (MOTHMAN_PG in place of MOTHMAN_SUPPLY_DSN, and a commented MOTHMAN_ASSET= line naming the asset folders, left unset because MOTHMAN_ASSET has no default), in the change that lands the split."
- **See section 4.3** for the line itself.

---

## 4. CLAUDE.md, README.md and `.env.example`

Line numbers are at `dad4ca1c`. Builder A's 2026-11-15 edits to the template and snapshots rows, and the approved setup block (`supply_quarterly`, `supply_daily`, `MOTHMAN_PG`), are already in; nothing here repeats them.

### 4.1 CLAUDE.md

**E1. Layout table, the `contract/` row (line 310) becomes an `assets/` row.** Replace the whole row with:

> | `assets/` | Each DATA ASSET's configuration, one folder per asset named for its `data_asset_id` - `assets/quarterly/` (Child Protection, Emergency Department, Linkage Products) and `assets/daily/` (Birth Registrations) - since the asset split (REQ-PIPE-342, 2026-11-01; it was `contract/` and `dbt_project/`). Assets are found by listing the folder, never named in code. Each holds: the asset-wide files at its top (`data-asset.yaml` - `data_asset_id`, the asset's `timezone` and the `hierarchy` of agencies/collections/datasets; `calendar.yaml` - its ONE baseline calendar, each collection's `files_go_to_period` and participation defaults and each dataset's participation, REQ-PIPE-345; `people.yaml`, `file-checks.yaml`, `presentation.yaml`); one folder per AGENCY holding each collection's real ODCS contract, SodaCL and Evidently checks, `<agency-id>/<stem>-{contract.yaml,soda-checks.yml,evidently-checks.yml}` plus each one's `-retired` sibling (REQ-QAC-241); its own dbt project, `dbt/` (`models/<collection-id>/`, `tests/<collection-id>/`, `retired/<collection-id>/schema-retired.yml`; REQ-QAC-368); `collections/<module>.py`, each collection's QA ADAPTER, loaded by path (REQ-PIPE-369 - not a Python package); and `synthetic/`, configuration only the generator and the bootstrap read (`collections/<module>.py` providers, `scripted_decisions.yaml`, `synthetic_inputs.yaml`; REQ-GEN-370). Only `environments.yaml` sits at the top of `assets/`. The shared dbt macros and generic tests are `dbt_shared/`, a local package both projects read through their macro-paths and test-paths. Every reader finds a file by convention from the selected asset's registry, and `mothman check` runs each asset-reading gate once per asset folder and fails a file out of place. `MOTHMAN_ASSET` selects the asset; it has no default (REQ-PIPE-363). `as_of_offset_days` (Thread C's flat global staleness offset) was removed 2026-09-17 when per-dataset cadence replaced it; a reference to it in older prose is history, not config |

Why: the old row describes the pre-split tree, the per-agency rule, a `calendars` key in `data-asset.yaml` and a dbt rule that have all moved. The `as_of_offset_days` history is kept in one clause.

**E2. The `generator/` row (line 311)**:
- Replace "and `collections/<id>.py` holds each collection's rows, seed schedule and period plan (`civil_registration.py`, `child_protection.py` - they were `generate_runs.py` and `generate_cp_runs.py`), each importable without pandas or numpy and found by the collection's id, never named; a provider declares its seed ranges (`mothman check`'s `providers` gate fails two that overlap)" with:
  > "and each collection's PROVIDER - its rows, seed schedule and period plan - lives in its asset's folder, `assets/<asset>/synthetic/collections/<module>.py`, loaded by path (REQ-GEN-370; `generator/collections/` keeps only the shared `base.py`). Today: `civil_registration.py` on the daily asset; `child_protection.py`, `emergency_department.py` and `linkage_products.py` on the quarterly (the first two were `generate_runs.py` and `generate_cp_runs.py`). Each is importable without pandas or numpy and found by the collection's id, never named. A provider declares its seed ranges (`mothman check`'s `providers` gate fails two of one asset that overlap, and a provider that imports another provider, an adapter or `assets/`)"
- "invoked via `mothman bdm generate-synthetic-data`/`mothman cp generate-synthetic-data`" becomes "invoked via `MOTHMAN_ASSET=daily mothman bdm generate-synthetic-data`/`MOTHMAN_ASSET=quarterly mothman cp generate-synthetic-data`".

**E3. The `pipeline/` row (line 313)**:
- "all supply data is in the one PostgreSQL database" becomes "all supply data is in PostgreSQL - one database per asset, `supply_<asset>`, since the split (REQ-PIPE-343)".
- "each collection's `reports/` results file" becomes "each collection's `reports/<asset>/` results file".
- "from `contract/presentation.yaml`" becomes "from its asset's `presentation.yaml`".

**E4. The `qa_tools/` row (line 314)**:
- "plus `collections/` - **the collection registry** (REQ-PIPE-240): which collections exist is read from `contract/data-asset.yaml`'s hierarchy (each declaring a `short` and a `run_prefix`) and each is run through a small adapter module named by its id." becomes:
  > "plus `collections/` - **the collection registry** (REQ-PIPE-240): which collections exist is read from the selected asset's `data-asset.yaml` hierarchy (each declaring a `short` and a `run_prefix`), and each is run through a small adapter module, `assets/<asset>/collections/<module>.py`, loaded by path from the collection's id (REQ-PIPE-369) - `qa_tools/collections/` holds only the shared `base.py`."
- "rebuilds `reports/results_rs_civil-registration.json`/`results_cpfs_child-protection.json`" becomes "rebuilds `reports/<asset>/results_<agency short>_<collection>.json` (e.g. `reports/daily/results_rs_civil-registration.json`)".

**E5. The template row (line 316)**:
- "embeds every registered collection's `reports/` dashboard file into one `COLLECTION_DATA` const" becomes "embeds every collection of the selected asset's `reports/<asset>/` dashboard file into one `COLLECTION_DATA` const".
- "`contract/data-asset.yaml` into `AS_OF_OFFSET_DAYS`," becomes "the selected asset's hierarchy into `HIERARCHY`,".
- Why: `AS_OF_OFFSET_DAYS` has not been embedded since 2026-09-17 (embed_dashboard_data.py:14). The `deploy-pages.yml`/`qa_results/` sentences in the same row are stale too, since REQ-PIPE-089, but they are not the split's; I am flagging them, not proposing them.

**E6. The snapshots row (line 317), line 419 and line 426:** C1, as signed, applied with REQ-DASH-373. No edit now.

**E7. The scale paragraph (line 285)**: "Today there are 2 datasets." becomes:
> "Today there are two data assets in this one repository, split 2026-11-01 (REQ-PIPE-342): the quarterly asset (Child Protection, Emergency Department, Linkage Products) and the daily one (Birth Registrations), each with its own configuration folder under `assets/`, its own database and its own baseline calendar."

Everything after that sentence stands.

**E8. "WHAT STILL BREAKS THE RULE" (lines 414-415)**: "`data/deliveries/` and `data/receipts/`" becomes "`data/<asset>/deliveries/` and `data/<asset>/receipts/`", and "`data/generator_bookkeeping.json`" becomes "`data/<asset>/generator_bookkeeping.json`".

**E9. The regenerated-paths bullet (line 424)**: "`data/raw/`, `reports/*.json` etc. are" becomes "`data/<asset>/`, `reports/<asset>/*.json` etc. are". C1 changes the snapshots sentence in the same bullet later.

**E10. "Regenerate via ..." (lines 435-438)**: "Regenerate via `mothman env reset-synthetic` then `mothman pipeline bootstrap` (... on an empty one it runs the whole pipeline for both collections - `--collection bdm`/`--collection cp` to scope to one)" becomes:
> "Regenerate via `MOTHMAN_ASSET=<asset> mothman env reset-synthetic` then `MOTHMAN_ASSET=<asset> mothman pipeline bootstrap`, once per asset (... on an empty database it runs the whole pipeline for every collection of the selected asset - `--collection <short>` to scope to one)"

The rest of the sentence is verbatim.

**E11. The fresh-sandbox note (line 769)**: "Check `dbt_project/dbt_packages/` exists" becomes "Check each asset's `assets/<asset>/dbt/dbt_packages/` exists".

**E12. After "THREE VARIABLES, NOT TWO" (after line 1244)**: change "`contract/environments.yaml`" to "`contract/environments.yaml` (`assets/environments.yaml` since the split)", and add this paragraph:
> "**AND NO MOTHMAN_ASSET, deliberately** (REQ-PIPE-363; Keith, 2026-11-15): it has no default, so a command that reads asset configuration names its asset - `MOTHMAN_ASSET=quarterly uv run mothman ...` - and refuses without one, listing the asset folders. With `MOTHMAN_SUPPLY_DSN` unset, it opens `supply_<asset>` on the server `MOTHMAN_PG` names (REQ-PIPE-343 criterion 7)."

**E13. "A running server is not a populated one" (lines 1262-1271)**: "`mothman pipeline bootstrap` generates both collections' synthetic data and runs the real checks over every supply;" becomes "`MOTHMAN_ASSET=<asset> mothman pipeline bootstrap`, once per asset, generates that asset's collections' synthetic data and runs the real checks over every supply;". The figures that follow are history and stay. After the 889-second paragraph, add:
> "**RE-MEASURED 2026-11-03 PER ASSET, from empty: daily 11m24s, quarterly 111m09s** (morning report 12; post-build-review #318), against REQ-PIPE-250's 12-minute budget. The quarterly asset is the one to start early."

**E14. The orphaned-runs and benchmark cautions (lines 1320, 1370)**:
- "count `ls data/deliveries | wc -l`" becomes "count `ls data/<asset>/deliveries | wc -l`".
- "never benchmark against the real `supply` database" becomes "never benchmark against a real `supply_<asset>` database".

**E15. Hosting notes (line 1892, "The repo is public ... GitHub Pages hosting depends on that").** CHOICE G9.
- Recommended: no edit in T5. Nothing about hosting has changed yet, because REQ-PIPE-354 is not built. REQ-DOCS-259 c7 rewrites this bullet when the hosting moves.
- That leaves REQ-DOCS-358 c3's "its hosting notes" unmet until then, blocked_by REQ-PIPE-354.

**Left alone, as history:** line 485 (`contract/*.yaml`, an incident), 507 (`dbt_project/target/`), 548, 553, 818, 867, 901, and 1808 (the Soda SQL incident's file name). Each records what was true when it happened.

**Not proposed, flag only: the `ci_probe` recipe (lines 993-998).**
- It sets `MOTHMAN_SUPPLY_DSN=.../ci_probe`. A set DSN still names its database outright (REQ-PIPE-343 c7), so the recipe is not obviously wrong.
- But CI's fast half now runs with no DSN at all, only `MOTHMAN_PG` (test.yml:197-201).
- Whether the recipe still reproduces CI's condition is untested. Re-run it once before deciding whether to edit it.

### 4.2 README.md

**R1. Quickstart (line 21)**: `./mothman pipeline run` becomes
```bash
for asset in quarterly daily; do MOTHMAN_ASSET=$asset ./mothman pipeline run; done
```
- Why: with no `MOTHMAN_ASSET`, mothman builds no command groups and refuses (REQ-PIPE-363). So the quickstart as written fails.

**R2. Child Protection run (lines 514-520)**: replace the block and its parenthetical with:
```bash
MOTHMAN_ASSET=quarterly ./mothman pipeline run --collection cp
```
> (Generates Child Protection's 55 quarterly deliveries, runs the real tools -> reports/quarterly/results_cpfs_child-protection.json, reshapes -> reports/quarterly/cpfs_child-protection_dashboard.json, then re-embeds the quarterly asset's collections into the dashboard HTML. `--collection all`, the default, does the same for every collection of the selected asset; Birth Registrations is the daily asset's, run with `MOTHMAN_ASSET=daily`.)

- Why: "re-embeds BOTH real datasets" and "does the same for Birth Registrations too in one call" are false with one asset per process.

**R3. Layout tour, `generator/collections/` (lines ~180-185)**: replace the `collections/` entry and its two children with:
```
  collections/                 the shared provider base (base.py) only - each collection's PROVIDER
                               (its rows, seed schedule and period plan, importable without pandas or
                               numpy) lives in its asset's folder, assets/<asset>/synthetic/collections/,
                               loaded by path (REQ-GEN-370): civil_registration.py (daily);
                               child_protection.py, emergency_department.py, linkage_products.py (quarterly)
```

**R4. Layout tour, `qa_tools/collections/`.** It is listed twice, near line 199 and at line 233.
- Replace the first entry with:
  ```
    collections/                 the collection registry (REQ-PIPE-240) and the shared adapter base: every
                                 collection the selected asset's data-asset.yaml hierarchy declares, each run
                                 through its adapter, assets/<asset>/collections/<module>.py, loaded by path
                                 (REQ-PIPE-369). A new collection is picked up everywhere through it, or refused
                                 by name; `mothman check`'s collections gate fails on one without an adapter
  ```
- Delete the second, one-line entry, which duplicates it.

**R5. Layout tour, `data/` and `reports/` (lines ~225-230)**: replace both entries with:
```
data/<asset>/                  generated, one folder per asset - its deliveries/, receipts/,
                               generator_bookkeeping.json and scenario_placements.json. The warehouse is
                               each asset's own PostgreSQL database, supply_<asset> (REQ-PIPE-343), not a
                               file here. Not checked in.
reports/<asset>/               generated, one folder per asset - each collection's
                               results_<agency short>_<collection>.json and
                               <agency short>_<collection>_dashboard.json (not checked in)
```
- Why: the `supply.duckdb` text predates REQ-PIPE-087.

**R6. Paths in prose:**
- Line 435: `generator/collections/civil_registration.py` becomes `assets/daily/synthetic/collections/civil_registration.py`.
- Line 490: `reports/results_rs_civil-registration.json` becomes `reports/daily/results_rs_civil-registration.json`.
- Line 529: `generator/collections/child_protection.py` becomes `assets/quarterly/synthetic/collections/child_protection.py`.

Already correct, no edit: the dbt-deps lines (20, 263), the warehouse block (266-272) and the `assets/<asset>/dbt/` mention at line 128.

### 4.3 `.env.example`. CHOICE G7

**X1.** After the `MOTHMAN_PG=` line, add:
```
# --- Which data asset -------------------------------------------------
# Every command acts for ONE asset, named by its folder under assets/
# (quarterly, daily). Deliberately NO DEFAULT (Keith, 2026-11-15): a
# command with none set refuses and lists the folders, rather than act
# for an asset you did not choose. Set it per command
# (MOTHMAN_ASSET=daily mothman ...), or uncomment this to work on one
# asset for a while.
# MOTHMAN_ASSET="quarterly"
```

**X2.** "One of the ids in contract/environments.yaml" becomes "One of the ids in assets/environments.yaml".

**G7 options:**
- (a) Commented out, as above. Recommended: it shows the variable without becoming the default Keith ruled out.
- (b) A live `MOTHMAN_ASSET="quarterly"` line. `.env` is loaded by every command and by pytest, so this would quietly become a default.
- (c) No line, and amend c3 to drop it.

---

## 5. The plans entries criterion 4 takes out

c4 removes each entry "once the last requirement of this batch they feed is built". Most of those requirements are the split's FEATURES, which come after #134's core. So **only #55 can come out in T5** (CHOICE G8).

| Entry | Feeds | Can it come out in T5? |
|---|---|---|
| #55 (running-thoughts.md:1055) | REQ-PIPE-342 (built) | **Yes** |
| #109 (:5656) | REQ-QAC-348/GEN-349 (Cancer), REQ-PIPE-346/DASH-347/QAC-350/GEN-351 (weekly) - not started | No |
| #131 (:5951) | REQ-DASH-355/356/367 (period control), REQ-PIPE-354/DASH-373 (hosting), 346 - not started | No |
| #134, configuration half (:6106, the "DECIDED (a)" and synthetic-config scan bullets) | REQ-GEN-370 (built, c1's eras.yaml unmet) and REQ-GEN-371 (not started) | No. The rest of #134 also stays until REQ-PIPE-376 to REQ-GHUB-396 are built, as the entry itself says |

**The carry-over check (CLAUDE.md rule 3).** Every decision in each entry, and whether a requirement carries it:

**#55 - nothing uncarried.**
- Option (a), (b)/(c) as a future decision point, and shapes 2-4 out of scope: all three are carried verbatim in REQ-PIPE-342's decisions ("ONE REPOSITORY, A CONFIGURATION FOLDER PER ASSET ...").
- Its NFR PORTABILITY carries the "inject the configuration" thread.
- The "two precedents" (REQ-PIPE-106's generated configuration, REQ-PIPE-107's guard) are context, not decisions, and both requirements are built.
- **Delete whole in T5.**

**#109 - nothing uncarried.**
- Keith's intent ("one schema for each release of the asset") and "per-cadence schemas, with or without a release layer, rejected" are in REQ-PIPE-345's decisions ("WHAT A PERIOD SCHEMA IS, SETTLED").
- "A weekly dataset on a daily asset; Keith thinks automatic inheritance covers it" is superseded by weekday participation, and REQ-PIPE-346 c5 keeps the inheritance ("inherited when the period is born").
- The monthly test dataset is REJECTED in REQ-QAC-348's decisions.
- The split remark is REQ-PIPE-342.

**#131 - two decisions found uncarried.** Each needs a home before deletion (REQ-PIPE-342 recommended for both):
1. **"THE SPLIT INCLUDES #109's TWO DATASETS (Keith, 2026-10-31 morning, (b)) ... REJECTED (a), splitting with today's datasets only."**
   - The rejected alternative is in no requirement. REQ-QAC-348 rejects only the monthly dataset.
   - Proposed REQ-PIPE-342 decision: "THE SPLIT INCLUDES TEST DATASETS OFF THE BASELINE'S CADENCE (Keith, 2026-10-31, #131 (b)): an annual dataset on the quarterly asset (REQ-QAC-348) and a weekly one on the daily (REQ-QAC-350), so the period control is designed against slower-than-baseline participation from the start. REJECTED (a), splitting with today's datasets only."
2. **"TWO DASHBOARDS ON ONE SITE ... REJECTED (b), one dashboard with an asset switcher, which mixes both assets into one build".**
   - The site half is superseded and carried in REQ-PIPE-354 ("ONE CLOUDFLARE PROJECT PER ASSET ... SUPERSEDES v1's two dashboards on one site").
   - The asset-switcher rejection is not explicit. REQ-PIPE-354 rejects "one combined project rebuilt from both databases", which is close but is about hosting, not the page.
   - Proposed REQ-PIPE-354 decision: "NO ASSET SWITCHER (Keith, 2026-10-31, #131): one dashboard switching between assets was REJECTED because it mixes both assets into one build; each asset's dashboard is built only from its own database."

Everything else in #131 is carried:

| #131 decision | Where the register carries it |
|---|---|
| GLOBAL, NOT ONE DATASET | REQ-DASH-355, line 48864 |
| A PERIOD VIEW ALONGSIDE AS-AT, the global control, REJECTED growing only the period page | 48860 |
| KEYED BY PERIOD, NOT ROUND, rejected (b)/(c) | 48912 |
| Two sections per workstream | 48888 and 48916 |
| Written against the post-split shape, REJECTED the interim rule | 48863 |
| Reopens REQ-DASH-054 decision 14 | REQ-DOCS-358's own decisions |
| One baseline per asset, nothing faster, slower is a subset, to go faster change the asset | REQ-PIPE-345, 48393-48394 |
| Repository shape (a) | REQ-PIPE-342 |
| The annual and weekly test datasets | REQ-QAC-348 and REQ-PIPE-346 |
| Refusal proven by a gate test | REQ-PIPE-345 c7 |
| One Cloudflare project per asset | REQ-PIPE-354, 48811 |
| The midnight "period mode on the as-at switcher" | 48870 |

The 2026-10-30 options (a)/(b)/(c), results on the period page or the dataset page by period, were superseded the next morning by the global control. They are not needed, because 48860 records what replaced them.

**#134, configuration half - nothing uncarried.**
- "DECIDED (a): the configuration half folded into the split; REJECTED (b) whole separation after the split, moves the configuration twice, and (c) before" is carried at requirements.yaml:49263 ("THE CODE HALF IS ITS OWN BATCH, AFTER THE SPLIT ...").
- The home for synthetic-only configuration is REQ-GEN-370 c1.
- The scan bullets are findings, not decisions, and REQ-PIPE-376 onwards re-scanned them.
- When it does come out, take only the scan bullet about synthetic-only configuration and the "DECIDED (a)" bullet. The rest of the entry is the code half's, and its own last line keeps it.

---

## 6. The genuine choices

| # | Where | Options | Recommended |
|---|---|---|---|
| G1 | A1/A3, REQ-PIPE-049 c1 and c7 | restate both as signed; retire both; restate c1, retire c7 | **restate c1** (with "(REQ-PIPE-106)"), **retire c7** (it repeats REQ-PIPE-345 c3/c4) |
| G2 | A13/A14, a no-calendar DECLARING dataset | signed text (only the read or linked side refused); refuse either side | **either side**, which is today's code. The signed text would quietly let such a read through once the different-calendar branch goes |
| G3 | A21, REQ-QAC-241 c2 | list the synthetic files (with or without eras.yaml); point at REQ-GEN-370 c1 | **point at REQ-GEN-370 c1**, and drop the move-map parenthetical |
| G4 | A38, REQ-QAC-223 c8 | "in each asset" plus a new two-asset test; "of the selected asset" | **of the selected asset**, which the existing test proves |
| G5 | A20 | withdraw; amend a retired requirement | **withdraw** (REQ-TEST-239 retired 2026-11-14) |
| G6 | REQ-PIPE-379 c3 | retire; restate for asset_model/ | **retire**, replaced_by REQ-PIPE-345 c6 and REQ-PIPE-342 c5 |
| G7 | REQ-DOCS-358 c3 and `.env.example` | commented MOTHMAN_ASSET; live line; no line | **commented**, and c3 reworded as in 3.7 |
| G8 | REQ-DOCS-358's status after T5 | flip to built with c1 (amendments for 346/347/354/355/367/373) and c4 (#109, #131, #134) unmet, blocked_by those; keep it in_progress | **built with two unmet criteria**, each blocked_by the requirements named, as REQ-GEN-370 was handled |
| G9 | CLAUDE.md hosting note | defer to REQ-PIPE-354/DOCS-259 c7; add an interim line now | **defer**. c3's "hosting notes" goes in G8's unmet list |
| G10 | REQ-PIPE-049 c5 before A2 | interim "on a cadence-rule baseline" at T2; leave until A2 | **interim edit**, since T2 makes "naming" false |
| G11 | A40, REQ-PIPE-089 c10 | all at REQ-DASH-373; assets/ half now, snapshots half later | **split**, because its contract/ half is false today |
| G12 | REQ-DOCS-358 c2, environments.yaml | add the exception clause; let the sweep map it into each asset (wrong) | **add the clause** |
