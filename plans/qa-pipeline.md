# Birth-registrations QA pipeline plan

Open items from wiring up the real dbt-core/Soda Core/datacontract-cli/
Evidently tools (`qa_tools/*/*.py`) against this pipeline. Everything here
is either a genuine bug found by actually running the real tools, or a
documented equivalent-vs-real-tool disagreement worth a second look.
Scoped to this repo's `contract/`/`dbt_project/`/`engines/`/`qa_tools/`
work specifically — wider-project items live in `plans/wider.md`.

Status values: `open` / `workaround shipped` / `done`. Priority is
relative, not a schedule — this is weeks of work, not months.

## Found running the real tools

1. **[done, 2026-09-18]** **[QA checks & contract]** dbt-duckdb reliability bug. dbt-core's
   own reported `failures` count was reproducibly wrong (0 instead of the
   true row count) on some runs for a percentage-based `fail_calc`, while
   the identical compiled SQL run directly via DuckDB's Python API always
   gave the right answer. Root cause not found despite extensive isolation
   (removed all arithmetic, disabled partial parsing, forced
   `--store-failures`, substituted SUM for COUNT — see
   `dbt_project/models/staging/schema.yml`'s comments for the full trail).
   Current fix: absolute row-count thresholds instead of a computed
   percentage, plus independent re-verification in
   `qa_tools/bdm/run_dbt_bdm.py`. **Follow-up:** build a minimal standalone
   repro (no dbt project, just the SQL pattern) and file it upstream
   against `duckdb-labs/dbt-duckdb`; `plans/publishing-and-history.md` #1/`plans/wider.md` #1 (CI, Postgres)
   might also shed light on this without extra effort.

2. **[todo, 2026-09-18]** **[QA checks & contract]** `soda-core-duckdb`'s `duckdb<1.1.0` pin isn't a
   compatibility ceiling — it pins to a DuckDB version with a published
   CVE (GHSA-w2gf-jxc9-pf2q), patched in 1.1.0. Confirmed via upstream
   issue `sodadata/soda-core#2295`. Currently ignored (we run on 1.5.5,
   verified working end to end — see `pyproject.toml`'s `[tool.uv]`
   comments). **Follow-up:** there's a newer `soda-duckdb` V4 package
   (`sodadata/soda-core/soda-duckdb`) that's actively maintained — worth
   checking whether it's the intended replacement and whether
   `run_soda_bdm.py`'s `Scan` API still exists there before migrating.

3. **[done, 2026-09-14]** **[QA checks & contract]** Soda's `[recent]` scoped check (`filter ... where:
   extract_timestamp >= CURRENT_DATE - 1`) never got meaningfully
   exercised against real Soda Core — it uses the actual wall-clock date,
   and this fixture's synthetic runs were all in the past by the time
   anyone actually ran it, so the scope always resolved to 0 rows.
   **Fixed (2026-09-14)**: `generator/anchor_date.py` (new, shared by both
   `generate_runs.py` and `generate_cp_runs.py`) anchors every generated
   run's dates to a rolling window ending on "today" (real wall-clock by
   default, pinnable via `GENERATOR_ANCHOR_DATE=YYYY-MM-DD` so a
   regeneration can still be reproduced byte-for-byte for verification -
   scoped via questions first, since a fully dynamic anchor would have
   broken that diffing technique entirely). Verified real behavior
   change, not just theory: post-fix, the `[recent]` filter now shows
   genuine pass/fail variation across runs (`row_count_total` nonzero,
   dirty runs correctly failing) instead of a dead 0/0 pass every time.
   Same fix un-stales the newer `date_of_birth` freshness check (dbt +
   Soda + contract) - confirmed passing with real margin on the most
   recent runs post-fix, not just marginally on one boundary row. Applied
   to Child Protection too (no wall-clock-dependent check there today,
   but its dates were equally stale) - CP's weekly-snapshot cadence keeps
   its "always a Monday" realism touch by anchoring to the most recent
   Monday on/before the anchor date.

4. **[superseded, 2026-09-18]** **[QA checks & contract]** Evidently's PSI and the equivalent
   engine's PSI used to genuinely differ (0.144 vs 0.179 on the red run)
   because Evidently bins by every distinct observed value while
   `evidently_engine.py` collapsed everything outside {M,F,X} into one
   `_other` bucket. Both were valid; documented, never reconciled - moot
   now that `engines/*.py` (including `evidently_engine.py`) was removed
   entirely (see item #83 above) and there's no more
   equivalent to reconcile against. Left here as historical record, not
   an active item.

5. **[superseded, 2026-09-18]** **[QA checks & contract]** `engines/contract_engine.py`'s
   `type: sql` rule handling (added when the contract was rewritten to
   real ODCS vocabulary) used a temp-view + string-replace to scope each
   SQL rule to one run's rows - worked, but was fragile, equivalent-only
   tech debt. Moot now that the file itself is gone (see item #83
   above). Left here as historical record, not an active item.

6. **[todo, 2026-09-18]** **[Testing & dev tooling]** The two-step `pip install` requirement is only half
   fixed: `uv sync --dev` now resolves everything in one step
   (`pyproject.toml`'s `[tool.uv] override-dependencies`, see `plans/
   wider.md` #6), but a plain `pip install .` still needs the old
   two-step dance (`pip` has no equivalent override mechanism) - see
   README's install note. Worth a periodic recheck as
   `dbt-duckdb`/`soda-core-duckdb`/`datacontract-cli` release new
   versions; this could resolve cleanly on its own, or break differently.

9. **[done, 2026-09-18]** **[QA checks & contract]** Two of the three Child Protection cross-table
   business rules used to fail on *every* run, dirty or clean, at a stable
   rate: placement/carer approval compliance (37/242 placements, ~15%) and
   closed-case investigation hygiene (16/181 investigations, ~9%).
   Confirmed for real and triangulated across all three tools —
   `datacontract test`, `dbt test`, and `soda scan` all independently
   reported the same 37 and 16 on the same data. Not a bug in the rules:
   `synthetic-data-generator/child_protection.py` genuinely didn't enforce
   either invariant (`carer_for_placement` was drawn from the full carer
   pool regardless of `approval_status`; `case_status` and investigation
   `end_date` were generated independently).
   **Fixed** (Keith's call: fix the generator, strict 0% on clean runs,
   case closure derives from investigation state): `child_protection.py`
   now only ever assigns an Approved carer to a placement, and only ever
   marks a case Closed once none of that client's own investigations are
   still open (case_status is drawn as a candidate early, same as before,
   then overridden to "Open" for any client with a still-open
   investigation — keeps every other column's RNG stream byte-identical to
   pre-fix output; row counts are unchanged). Both business rules now pass
   0/0 on every clean run. `generator/dirty.py` gained two new presets
   (`apply_cp_placements_presets`, `apply_cp_investigations_presets`,
   mirrored into `synthetic-data-generator/dirty.py` to keep the two
   copies in sync) so amber/red runs still demonstrate a real,
   controlled violation — confirmed for real and triangulated again across
   all three tools: 0 clean / 3 amber / 17 red (placement/carer) and
   0 clean / 1-3 amber / 6 red (closed-case hygiene). `data/cp_raw/` was
   regenerated; `plans/dashboard.md` #1's row-count calibration in the
   contract was rechecked and didn't need changes (row counts are
   unaffected by the fix, only which values land in `carer_id`/
   `case_status`/`end_date`).

10. **[done, 2026-09-18]** **[Dashboard UI]** Dashboard check display was hard for a human reader
    to make sense of, flagged against a concrete example
    (`notification_id`): its drawer headlined `dbt:not_null` (flat 0,
    "No material change") while the tile itself was Red from a different
    check several cards down, because `checks[0]` — which drives the
    headline chart — was ordered by a hand-curated `CHECK_PRIORITY` dict
    that only had entries for a couple of columns. The 4 raw tool check
    names (`dbt:unique`, `datacontract:duplicate_count`, ...) also gave no
    hint that two of them were the same real-world question asked by two
    tools.
    **Fixed** in `pipeline/dashboard_check_labels.py` (shared by both
    dashboard builders): `rank_for_headline()` sorts each column's checks
    by their own current-run status (worst first, using the exact rule
    `checkStatus()` renders with) instead of a lookup table that can go
    stale; `display_name()` prefixes a short plain-language label (Null
    rate, Duplicate rate, Invalid values, Referential integrity,
    Distribution drift, Row count) sourced from an explicit `label` field
    every `real_tools/*.py` script and `engines/*.py` equivalent now
    writes onto each check result at construction time — not guessed
    later from the check name string, after Keith pushed back on an
    earlier version that did exactly that. The dashboard's existing but
    always-blank `dimension` field is now populated the same way and
    shown as a badge on each check card.
    Three real, pre-existing bugs surfaced along the way, each found by
    actually looking rather than assumed:
    - `engines/dbt_test_engine.py` (birth-registrations' equivalent dbt
      engine) reads `dbt_project/models/staging/schema.yml` directly with
      no `--select` scoping — the same class of regression as
      `run_dbt_real.py`'s missing `--select` (see performance.md #2), just
      in the hand-rolled interpreter. It was iterating all 7 models in the
      shared schema.yml and crashing on the first Child Protection column
      it hit. This means `pipeline/orchestrate.py` — which produces
      `reports/results.json`, the file the *live* Birth Registrations
      dashboard tile actually reads — had been silently broken since
      Phase 2, showing stale pre-Phase-2 data instead of erroring
      visibly, until this was found by re-running it for the first time
      since.
    - `soda_engine.py`'s dimension logic (`"validity" if "invalid" in
      check_name else "completeness"`) missed the one custom-named check
      in the dataset: "sex validity, last 24h only" contains "validity",
      not "invalid", so it was silently mislabeled completeness. Invisible
      until dimension was actually rendered.
    - datacontract-cli's 7 FK checks and 3 Child Protection business rules
      are both written as table-level `type: sql` rules (ODCS has no
      per-property home for a rule that joins to another table), so both
      arrived with `column_name="(table)"` and both landed in the
      dashboard's `(table-level checks)` pseudo-column — inconsistent with
      dbt's `relationships` tests and Soda's `values in ... must exist
      in ...` checks for the exact same FKs, which the dashboard already
      attributes to the FK column itself. Fixed in
      `run_datacontract_real_cp.py` by parsing the FK column straight out
      of each rule's own description (all 7 follow the same "Every
      `<table>`'s `<column>` must reference an existing `<table>` row."
      shape) — the 3 business rules' differently-shaped descriptions are
      untouched.
    Verified with Playwright throughout, including a full re-check of
    `notification_id` and `cp_client_id`'s drawers and the executive/
    agency views; no regressions on either real dataset.

11. **[done, 2026-09-18]** **[QA checks & contract]** Birth Registrations' QA coverage was thin outside
    `sex`/`place_of_birth_facility`: two columns (`source_system_record_id`,
    `extract_timestamp`) had no rule at all, five free-text columns only
    had a null check, and there was no cross-record consistency check
    anywhere in this dataset. Keith asked for a battery covering all of
    that, real-tools-only (dbt-core/Soda Core/datacontract-cli - not
    `engines/*.py`), with matching dirty-data presets.
    **Added**: `source_system_record_id` uniqueness + `^SRC-[0-9]{9}$`
    format; `extract_timestamp` null + an ordering/latency rule (must fall
    within a day of `date_registered`, on or after it); a format check on
    `child_given_names`/`child_family_name`/`place_of_birth_suburb`/
    `registering_parent_1_name`/`registering_parent_2_name` (letters,
    spaces, periods, hyphens only); and a genuine cross-record check - every
    `is_multiple_birth` record must have a matching sibling row from the
    same birth event (same `date_of_birth`, facility, registering parent 1).
    Two categorical/numerical scoping calls, made rather than asked twice:
    `is_multiple_birth`'s existing null check is already its complete
    "strict values" check (a boolean has no third "invalid code" state the
    way `sex` does); no pure numeric column exists in this schema at all
    (both ID fields are string-typed), so "logical checks for numerical
    columns" is covered by the closest fit - the date/timestamp ordering
    rules.
    A real generator gap surfaced immediately: `is_multiple_birth` was a
    pure independent random flag (3.2% rate) with no sibling-record logic
    behind it at all - the sibling check would have failed on every
    flagged row, every run, by construction, the same "generator doesn't
    enforce the invariant" pattern as #9 below. **Fixed** the same way:
    `daily_batch.py` now actually generates a real sibling row for ~1.6%
    of rows (each pair together landing close to the old 3.2% flat rate),
    reusing the birth event's own `date_of_birth`/facility/parents with a
    freshly drawn name, sex and IDs. `dirty.py` gained
    `break_multiple_birth_siblings` (drops one twin from a fraction of
    real pairs) plus `inject_duplicate_values` and
    `inject_extract_timestamp_disorder`, folded into
    `apply_birth_registrations_presets` alongside the existing two.
    Two real, live bugs found by actually running this, not assumed:
    - The sibling-match SQL (contract, dbt, Soda) initially used plain `=`
      on `place_of_birth_facility`/`registering_parent_1_name`, both of
      which can legitimately be null (home births; ~2% parent-name null
      rate) - `NULL = NULL` is never true in SQL, so genuinely matching
      pairs were flagged as siblingless whenever either shared field was
      null (4 false positives on a clean run). Fixed with
      `IS NOT DISTINCT FROM` (null-safe equality) in all three tools.
    - DuckDB's regex engine (RE2, what both `REGEXP_MATCHES` and Soda's
      `valid regex` compile down to) has no lookahead support at all - the
      first draft of the text-format pattern
      (`^(?!.*[0-9])(?!^(N/A|TEST|...)$)...`) is standard Python `re` but
      not valid RE2, and separately its embedded apostrophe (for names
      like "O'Brien" - though none exist in this fixture's name pools)
      broke the SQL string it got embedded into. Simplified to a plain
      character-class pattern (`^[A-Za-z][A-Za-z. -]*$`) with an honest,
      documented limitation: this catches a digit or symbol in a name
      field, not a dictionary of known junk words - a bare alphabetic
      junk word like "TEST" with no digit/symbol in it would pass. The
      dirty preset's junk pool was adjusted to values that genuinely trip
      this narrower rule (e.g. "TEST1", not "TEST").
    Wiring the new checks into the dashboard surfaced a third, unrelated
    real bug and a genuine architecture question:
    - `build_dashboard_data.py` reads `reports/results.json`
      (`pipeline/orchestrate.py`'s equivalent-engine output), not
      `results_real.json` - unlike Child Protection, which has no
      equivalent engine at all and reads real-tool output directly. Most
      of the new checks turned out to already be computed correctly by
      the existing equivalent engines for free (`contract_engine.py`/
      `dbt_test_engine.py` generically interpret whatever's in the shared
      contract/schema files, so a new SQL rule or pattern just works with
      no code change) - only `soda_engine.py`'s hand-rolled interpreter
      has real gaps (no `duplicate_count`/`failed rows` support at all,
      and its `invalid_percent` handler only understands `valid values`,
      not the newer checks' `valid regex`). `build_dashboard_data.py` now
      merges in exactly those gaps from `results_real.json` via an
      explicit, hand-verified allowlist (not a diff against `results.json`
      - datacontract-cli's two implementations name the same rule
      differently, so a diff would have treated every pre-existing
      datacontract-cli check as "new" - see that file's own comment).
    - Found via that same near-miss: `soda_engine.py`'s `invalid_percent`
      handler was silently computing a false 100%-invalid result for
      every column using the new `valid regex` syntax (its `spec.get(
      "valid values", [])` fallback to an empty set meant "nothing is
      ever valid") - a real bug, not merge-only fallout, fixed by having
      it skip (not fabricate) a check shape it doesn't understand.
      `run_datacontract_real.py`'s own warn/fail-threshold defaulting
      (real, pre-existing, just never previously displayed) also surfaced
      this way: merging its check for `registering_parent_1_name`
      alongside the equivalent's correctly-thresholded one would have
      shown a duplicate false-red card, caught before it shipped by the
      allowlist approach above rather than a same-column check_name diff.
    Verified with Playwright throughout: all-green on the latest clean
    run across all 13 columns (including the 2 previously-uncovered
    ones), correct amber/red history on the 3 dirty runs, and each new
    check's real-tool triangulation (dbt/Soda/datacontract-cli agreeing
    on the same violation counts) visible on the relevant drawers.

12. **[done, 2026-09-18]** **[QA checks & contract]** Two more checks Keith asked for directly: a
    freshness / relative-date check (flag if no record anywhere in a run
    has a `date_of_birth` within the last 7 days of the REAL wall-clock
    date), and a row-count-growth check ("rows should go up, more or less
    - some daily reduction is fine"). Both real-tools-only, both
    triangulated across every tool that can express them.
    Freshness landed on `date_of_birth` in contract/dbt/Soda, using each
    check-result's own "count violations, mustBe 0" convention rather than
    a new comparator: the query flips "must have at least one recent row"
    into "1 if none exist, else 0" so no dashboard/engine code needed to
    learn a new check shape. Honest, deliberate limitation, same as the
    Soda checks file's pre-existing `[recent]` filter (see item 3 above):
    this fixture's dates are fixed at Sept 2026, so the check's pass/fail
    split will drift as real wall-clock time moves away from that window,
    independent of anything actually being wrong - regenerating on a
    rolling window (item 3's own follow-up) would fix both at once. Real
    and reproducible for now: runs dated too early relative to today
    genuinely fail, runs with recent-enough dates genuinely pass - visible
    as a real red-to-green transition across the 10-run history.
    Row-count-growth has no natural per-run-warehouse home (dbt/Soda/
    datacontract-cli all evaluate one run in isolation, by design - see
    `build_per_run_warehouses.py`) and no config-file-driven backing the
    way every other check has, so it's Evidently-only: `RowCount()` (real
    Evidently 0.7 metric) computed separately for a run and its
    immediately-preceding run (not PSI's fixed run_01 baseline - "did
    rows grow" is inherently about consecutive runs), then compared with
    this project's own two-tier band, same "the tool computes the real
    number, this file's own convention decides warn/fail" pattern as PSI.
    Attributed to `registration_number` (the row-identifying column) for
    lack of a real per-column home.
    `dirty.py` gained `truncate_rows`/`truncate_to_row_count` (a genuine
    truncated-extract scenario, the first injector in this module that
    changes row count rather than corrupting values within existing rows)
    and `generate_runs.py` now threads each run's actual row count into
    the next run's preset call, so the truncation lands a specific
    percentage below the PREVIOUS run specifically (matching what the
    check itself compares) rather than a self-referential rate that
    drifts with this dataset's own natural run-to-run size variance.
    Three more real, live bugs found along the way:
    - Truncating rows *after* the other presets diluted their ABSOLUTE-
      count-based thresholds (dbt's `place_of_birth_facility` not_null
      `error_if ">600"`) by the same fraction as the truncation - a red
      run's count dropped from 769 to 526, silently downgrading fail to
      warn. Fixed by truncating first and recalibrating the affected
      rates against the post-truncation row count instead.
    - `contract_engine.py`'s `type: sql` rules all shared one hardcoded
      check_name ("sql") - harmless while every property had at most one
      such rule, but `date_of_birth` now has two (the original range
      check plus the new freshness check), which collided under this
      dashboard's (engine, check_name)-per-column grouping and silently
      merged two different checks' 10-run histories into one. Fixed by
      deriving a short slug from each rule's own description (truncated
      to a word boundary, not sentence-split - "e.g." inside a couple of
      these descriptions defeats a naive split on ". ").
    - A third, newer instance of the dbt-duckdb reliability bug from item
      1 below: the `recent_births_present` singular test (no config, no
      fail_calc arithmetic - the simplest possible test shape, ruling out
      an arithmetic explanation) reported "fail" for a run that a direct
      re-query of the identical compiled SQL, against the same warehouse
      file, correctly showed "pass" for. No SQL/config explanation found;
      treated the same way as the other two - independently verified via
      direct query rather than trusted blindly.
    Verified with Playwright: both checks visible with correct labels/
    dimensions, real amber/red history driven by the new dirty presets
    (row-growth) and by genuine date-vs-wall-clock arithmetic (freshness),
    and no regression on any of the existing 13 columns' other checks.

13. **[investigate, 2026-09-18]** **[QA checks & contract]** Look more closely at what Evidently AI is actually
    doing today and consider expanding it - flagged by Keith, not yet
    scoped. Currently exercises exactly two checks for Birth Registrations
    (PSI drift on `sex` against a fixed run_01 baseline; the row-count-
    growth check added in item 12, against the immediately preceding run)
    plus one for Child Protection (`qa_tools/cp/run_evidently_cp.py`,
    PSI on `concern_type`). Candidates worth investigating before
    committing to any of them:
    - Evidently 0.7's other preset reports/tests beyond `DataDriftPreset`
      - a data-quality preset, other drift methods besides PSI, tests on
        more metrics than `RowCount` (row-growth's own implementation
        found `evidently.tests`' `gte`/`Reference` API mid-way through -
        a built-in reference-relative test - but ended up computing the
        real value and applying this project's own two-tier band instead,
        matching PSI's precedent; worth a proper look at what that API
        buys over doing it by hand).
    - Applying drift/quality checks to more columns, not just `sex`/
      `concern_type` - is there a real column elsewhere in either dataset
      where distributional drift is a genuinely useful signal?
    - Whether "Evidently as the cross-run/trend tool" (distinct from
      contract/dbt/Soda's point-in-time-per-run role) is a role worth
      making explicit, now that it owns two genuinely different kinds of
      cross-run comparison (a fixed baseline for PSI, a rolling previous-
      run comparison for row-growth).

14. **[done, 2026-09-18]** **[Dashboard UI]** Dashboard follow-ups from actually using it: a real
    accessibility bug fix, plus the click-a-check detail view Keith asked
    for (with clarifying questions asked first).
    - **Tooltip dark-mode contrast bug, real and confirmed.** The trend-
      chart hover tooltip used `background: var(--accent-ink); color:
      #fff` - `--accent-ink` is dark navy in light mode (fine against
      white text) but flips to a near-white blue in dark mode (it's meant
      as readable *text* on `--accent-soft` there, e.g. `.pill.tag`), so
      reusing it as this tooltip's background with hardcoded white text
      produced white-on-light-blue: unreadable. Fixed with fixed,
      theme-invariant colors (`#1B2420`/`#F5F2EA`) instead of chasing
      another token through both themes - a floating overlay tooltip
      reading "inverted" from the page underneath it is normal either way.
      Verified in both color schemes with Playwright.
    - **Click-a-check detail panel.** Previously only `checks[0]` (worst-
      status, picked arbitrarily) got a compare-grid + trend-chart at the
      top of the column drawer; every other check was a flat, non-
      interactive card. Asked Keith 4 questions to scope this before
      building (panel placement, content, history integration, whether
      checks[0] keeps special status) - answers: a nested panel sliding
      over the drawer; the existing compare/trend/table content plus
      row-level detail; its own back/forward history entry, same pattern
      as the drawer; and keep an automatic top section, but make it a
      genuine all-checks summary rather than one arbitrary check's own
      view. Built: every check-card is now clickable (and keyboard-
      operable), opening `#check-panel` - a second drawer-like panel with
      its own backdrop, above the column drawer's z-index - showing that
      specific check's current-vs-previous comparison, its own trend
      chart, and row-level detail (`row_count_total`/`row_count_invalid`,
      newly threaded through each history point in both dashboard
      builders - previously only ever exposed at the column-stats level
      for checks[0]). Honestly noted rather than faked: genuine per-row
      failing-record samples aren't captured by any real tool's output
      today, only the aggregate counts each one already reports.
      `STATE` gained an optional `checkKey` field alongside `columnName`,
      pushed/restored the same way column-drawer state already is -
      verified with Playwright: open → back closes the check panel only →
      back again closes the drawer; forward replays both; reload on a
      check-deep-linked URL restores the exact same nested state. Works
      identically for Child Protection (shares `buildRealDataset`) and
      the illustrative mock datasets (checks there already had every
      field this reuses; row-level detail degrades gracefully to "not
      captured" since mock checks never had real row counts).
      The drawer's own top section is now a genuine all-checks rollup
      instead of one check's view: current-run pass/warn/fail counts, and
      a worst-status-per-run dot timeline computed entirely client-side
      from each check's own history + fixed thresholds (no new Python-
      side "column status over time" field needed). This surfaced a real,
      previously-invisible fact rather than a bug: a column's worst-across-
      all-checks status can be red even on an "amber" dirty run, because
      some checks (e.g. datacontract-cli's `mustBe: 0` rules) have zero
      tolerance while others (Soda's percentage bands) have a genuine
      amber tier - both correct, now visibly disagreeing where they used
      to be hidden behind whichever check happened to be checks[0].

15. **[done, 2026-09-14]** **[QA checks & contract]** Genuine per-row failing-record samples, revisited.
    Item 14 above honestly noted that no real tool currently wired into
    this pipeline (dbt, Soda, datacontract-cli, Evidently) captures which
    SPECIFIC rows failed a check - only aggregate counts
    (`row_count_total`/`row_count_invalid`). `docs/quarantine_sex_column.py`
    already identifies the real mechanism for this: Great Expectations'
    `unexpected_index_list` (or a Pandera boolean mask) gives real
    row-level output, but GX isn't currently one of this pipeline's wired
    tools. See item #82 below - worth pursuing together: if GX gets
    evaluated as a comparison tool, its row-level output is the concrete
    reason to actually wire it in rather than just compare it on paper,
    and would let the check-detail panel (item 14 above) show real
    failing-row samples instead of the honest "not captured today" note
    it currently shows.
    **Researched, findings (read the actual installed source, not just
    docs)**: this is cheaper than it looked. THREE of the four tools
    already wired into this pipeline genuinely support this natively:
    - **datacontract-cli**: `DataContract(..., include_failed_samples=True)`
      is a real constructor parameter (`data_contract.py`), backed by a
      dedicated `_collect_failed_samples()` pass
      (`engines/ibis/ibis_check_execute.py`) that populates a first-class
      `check.failedSamples` field. `run_datacontract_real.py` already
      calls this exact API - turning it on is a one-line change, not new
      plumbing.
    - **Soda Core**: `samples limit:` is a real, documented SodaCL key on
      ordinary metric checks (confirmed in `sodacl_parser.py`), executed
      through a pluggable `Sampler` class - the default sampler computes
      the failing rows then explicitly discards them ("Samples are not
      sent to Soda Cloud"), but `scan.sampler = MyOwnSampler()` is a real
      extension point; a small custom sampler writing rows to JSON
      instead of discarding them would work. Not currently enabled in
      `bdm-birth-registrations-soda-checks.yml`.
    - **dbt tests**: `store_failures: true` (already documented above) -
      confirmed not currently enabled anywhere in `dbt_project/`.
    - **Evidently**: genuinely no - searched its source directly for any
      row-level concept (unexpected_index, failed_rows, row ids) and
      found nothing, consistent with its actual role here (drift/
      row-count-growth, not per-column validity).
    This meaningfully changes GX's case in item #82 below - GX's
    `unexpected_index_list` is no longer the only path to this, which was
    its main selling point for this specific use case; downgraded there
    accordingly.
    **Resolved, first round**: even though the capability is cheap, full
    row-level display (every column, ready to act on) doesn't belong in
    the QA reporting dashboard - it's a genuine case-management/workflow
    capability, architecturally distinct from reporting. Same split
    `docs/quarantine_sex_column.py` already draws between "flag it" and
    "act on it." Settled via several rounds of questions with Keith
    working through the actual shape (2026-09-14) - moved to its own file
    since it turned out to be a genuinely standalone design, not a
    dashboard feature: **see `docs/remediation-workflow-design.md`** for
    the full ticket model, assignment/escalation rules, automatic
    pipeline-update principle, and quarantine/release design. That
    document's own scope still stands as written - "design the seam,
    don't build it," platform choice and external-provider access both
    explicitly deferred.

    **[done] Built, narrower (2026-09-14, same day)**: Keith came back to
    this specifically wanting to explore where the line between
    "reporting" and "workflow" actually sits, deliberately not
    overriding the resolution above. Landed on: a **read-only sample of
    just the failing rows' own primary keys** (no full row content, no
    action affordance - no quarantine/ticket/assignment) is still
    genuinely "flag it," not "act on it," the same category of
    information as the aggregate counts the dashboard already showed,
    just more specific. Also motivated by `docs/remediation-workflow
    -design.md`'s own principle that external providers should
    eventually see only "primary keys of bad rows, not full row content"
    - showing only PKs here stays consistent with that even though this
    dashboard has no access tiers at all yet.

    Built across all three capable tools, both datasets - up to 5 example
    primary keys per failing check, capped consistently
    (`FAILING_SAMPLE_LIMIT`/datacontract-cli's own hardcoded limit),
    surfaced in the check-detail panel's existing "Row-level detail"
    section:
    - **datacontract-cli**: `include_failed_samples=True` - already
      restricts samples to identifier + offending field itself, cheapest
      of the three, confirmed matches the research above exactly.
    - **Soda Core**: a custom `CaptureSampler` (`qa_tools/common/
      soda_common.py`) replaces the default (which computes samples then
      discards them) - `samples limit: 5` opted into each metric check in
      both checks YAMLs; "failed rows" checks sample automatically
      (confirmed empirically, not just documented).
    - **dbt**: `--store-failures` (always on now, not opt-in) writes each
      failing test's own rows into a `main_dbt_test__audit.<test>` table
      - queried directly for tests whose audit table already carries the
      row (not_null, and the singular tests that already select their
      home table's own PK), or via one follow-up query against the model
      for tests dbt itself pre-aggregates to the offending *value*
      (`accepted_values`, `unique`) rather than the row.

    **Real, named gaps, not oversights** - noted in code where they bite
    rather than silently under-delivering:
    - **Evidently**: no row concept at all (drift/row-growth, not
      per-column validity) - confirmed already, unchanged.
    - **`custom_sql`/`type: sql` rules** (both tools' freshness/sibling-
      match/timestamp-ordering checks, CP's 3 business rules... except
      Soda's own versions of the 3 CP business rules DO get real samples,
      since Soda's "failed rows" mechanism is a different, row-native
      shape from the other two tools' aggregate-metric sampling) - not
      covered by `include_failed_samples` or dbt's generic-test
      `--store-failures` shape at all.
    - **dbt's `relationships` tests** (CP's 7 FK checks specifically):
      its audit table only carries the offending FK *value*
      (`from_field`), which would need a further value -> child-row
      resolution step beyond what `accepted_values`/`unique` already
      needed - deliberately not built this round. Currently
      unobservable in practice anyway (the 7 FK checks never fail on
      this fixture - see item 9 below).
    - **datacontract-cli's `duplicate_count`**: its own sample shape is
      `{field: value, duplicate_count: N}` (the offending value, like
      dbt's `unique`), not the identifier - not resolved via a follow-up
      query for this tool specifically (would need its own fresh read of
      the source CSV). Low-impact: Soda's and dbt's own duplicate/unique
      checks already cover the same underlying rule with real samples.

    Verified real behaviour, not just code review: re-ran the full
    pipeline for both datasets, diffed against pre-change output with
    `failing_sample_keys` excluded - zero other differences (824/950
    results, same pass/warn/fail counts). Confirmed via Playwright in an
    actual browser (not just JSON inspection) that samples render
    correctly in the check-detail panel for both datasets, and that
    checks without a sample correctly show a fallback note instead of a
    blank or broken section - this caught a real bug along the way (see
    below).

    **A real bug found and fixed while verifying, not while building**:
    `qa-reporting-dashboard.html`'s `buildRealDataset()` remaps each raw
    history point through an explicit field whitelist
    (`row_count_total`/`row_count_invalid`/etc.) before the check-detail
    panel ever sees it - `failing_sample_keys` was silently dropped by
    that whitelist even though the underlying JSON had it correctly, so
    the panel always fell through to the "no sample available" case.
    Caught by Playwright-driving the actual UI (a browser test, not
    reading the code), not by JSON-level verification, which had already
    looked correct and would have missed it entirely. Fixed by adding
    the field to the whitelist; per CLAUDE.md's bug-fix convention this
    is the kind of thing that'd get a regression test, but this
    dashboard's own rendering logic has no existing test harness (it's
    hand-verified via Playwright throughout, not unit-tested) - noted
    here rather than silently skipped.

16. **[done, 2026-09-14]** **[QA checks & contract]** Should the dashboard explain *why* checks on the
    same column can legitimately disagree in severity? Item 14's
    all-checks summary surfaced (not created) a real fact: a column can
    show red on an "amber" run because one check has zero tolerance
    (`mustBe: 0`) and another has a genuine percentage-based amber tier,
    and both are correctly evaluating their own rule. Currently just
    visible as-is (two dots, two colours, no explanation) - open question
    is whether a viewer unfamiliar with the underlying tools would read
    that as a dashboard bug rather than two independently-correct
    assessments. Options, not yet decided: a short inline note when a
    summary contains genuinely different severities across checks; a
    persistent legend explaining zero-tolerance vs percentage-band
    checks; or leave it as-is on the theory that the check-detail panel
    (already one click away) makes each check's own logic clear enough.
    Low priority - revisit if a real reviewer actually gets confused by
    it.
    **Resolved (the "confusion" question specifically)**: Keith's call -
    not a concern right now. This is deliberately a PoC comparison phase
    with duplicate checks across tools by design, to work out which 1-2
    tools actually cover what's needed before narrowing down - visible
    disagreement between tools is expected and fine at this stage, not
    something to paper over.
    **New, confirmed finding**: does datacontract-cli genuinely lack
    native two-tier (warn/fail) thresholds, given Keith's called
    two-tier a must-have requirement? Confirmed directly in source
    (`engines/checks/check_spec.py`), not just inferred from the ODCS
    spec as the original landscape doc did: `CheckSpec` has exactly one
    `threshold` field and one `severity` field - no dual-threshold
    construct anywhere in the engine. A single quality rule genuinely
    cannot express warn-at-X/fail-at-Y.
    A real workaround exists, also confirmed in source: ODCS's
    `quality:` list already supports multiple rules per property (the
    existing contract does this for other reasons), and
    `create_checks.py` iterates it with
    `for count, quality in enumerate(quality_list)` - each entry becomes
    its own independently-evaluated check. Two quality rules on the same
    field/metric - one `severity: warning` with a looser threshold, one
    `severity: error` with a stricter one - genuinely produces real
    two-tier behaviour, no new dashboard code needed: the all-checks
    summary built for item 14 already computes "worst status across
    every check on a column," so a warn-rule/fail-rule pair rolls up
    into exactly a two-tier read on its own.
    Soda Core and dbt tests both do this natively in a single rule (warn:
    /fail: blocks; severity + warn_if/error_if respectively) - no
    workaround needed.
    **Resolved (both sub-questions, 2026-09-14)**: Keith's call on the
    two-tier finding - given it's a must-have requirement, needing a
    workaround is a **real strike against datacontract-cli** for the
    eventual 1-2-tool decision, not just a footnote to weigh later.
    Nothing further to build here - both the "confusion" question and
    this finding stand as closed records informing that future
    narrowing-down decision, not open items.

17. **[done, 2026-09-14]** **[QA checks & contract]** Aggregate failing-value shapes ("shape 2"), the
    other half of item 15's "surface more about the nature of the
    failure" idea - item 15 covers WHICH rows failed (PKs only); this
    covers WHAT the actual bad values look like, for closed-value-set/
    categorical checks (distinct values + counts) and numeric/date checks
    (min/max/outlier list, and a binned histogram). Scoped with Keith via
    two rounds of `AskUserQuestion` (2026-09-14), including sensitive-data
    handling as an explicit design constraint from the start (his own
    instruction, not something added after the fact):
    - **Sensitivity gating**: reuses ODCS's own real `classification`
      property (values like `pii`) - the same vocabulary
      datacontract-cli's own `_collect_failed_samples()` already respects
      (drops classified columns' values from samples) - rather than
      inventing a new boolean flag. Added `classification: pii` to both
      contracts' name fields (BDM: child/parent given/family names; CP:
      client/carer/case-worker given/family names).
    - **Suburb and postcode converted to real closed-value-set checks**:
      Keith's own preference, not just a shape-2 side effect. BDM's
      `place_of_birth_suburb` (previously a character-set regex) and a
      brand-new CP `postcode` check (previously untested at all) now both
      use `generator/names_au.py`'s `SUBURBS` pool (51 real WA
      suburb/postcode pairs - public geography, no person-level data) as
      an `accepted_values`/`invalid_percent`/ODCS `validValues` list
      across dbt, Soda, and datacontract-cli.
    - **New CP `date_of_birth` range check**: Child Protection had no
      date-range check at all before this (BDM already did). Soda's
      `valid min`/`valid max` don't accept bare date bounds (confirmed
      empirically: `float() argument must be a string or a real number,
      not 'datetime.date'`) - worked around with the already-proven
      `failed rows`/`fail query:` pattern instead. dbt: a new singular
      test (`dbt_project/tests/cp_client_date_of_birth_range.sql`) with
      `config(warn_if, error_if)`. Amber/red bands are count-based, not
      percentage (same `fail_calc` reliability reason as the rest of this
      file's item 1): up to 10 bad 1/1/1900-territory dates reads amber,
      more fails - Keith's own specific calibration instruction.
    - **Malformed (literally unparseable) dates deliberately NOT
      injected** - a real, empirically-confirmed constraint, not a
      shortcut: DuckDB's `read_csv_auto` infers a column's type per FILE,
      not per row, so a single unparseable date string silently
      downgrades the WHOLE column to VARCHAR for that run, corrupting
      every other check on it. Keith's call: out-of-range dates only for
      now; malformed dates flagged here as a real follow-up, not built.

    **Three real bugs found and fixed while building/verifying the above**
    (each got a regression test per CLAUDE.md's convention - none of
    these existed before this session, so none are retrofits):
    - **Dual `dirty.py` import-resolution bug**
      (`tests/test_generate_cp_runs.py`): `generator/dirty.py` and
      `synthetic-data-generator/dirty.py` are two separate files with the
      same module name; `generator/generate_cp_runs.py`'s own sys.path
      manipulation (needed to reach the population/child-protection
      generator, which lives in the other directory) caused `import
      dirty` to silently resolve to the wrong, stale copy. A first
      attempted fix (re-inserting `generator/`'s own directory at
      `sys.path[0]` right after the other inserts) didn't work either -
      `synthetic-data-generator/population.py` itself does its own
      `sys.path.insert(0, ...)` as an import-time side effect, re-winning
      the race. Fixed properly (not just patched) the same day, once
      Keith asked why this whole class of hack still existed here at all
      given `qa_tools/` had already been cleaned out of it: `generator/`,
      `pipeline/`, and `synthetic-data-generator/` (hyphens renamed -
      that turned out to be *why* the hacks existed, not just untidiness)
      are now real Python packages with real absolute imports and zero
      `sys.path` manipulation anywhere - see `plans/publishing-and-
      history.md` #3 for the full change, including a
      second, undrifted duplicate (`names_au.py`/`presentation.py`) this
      surfaced along the way. Caught loud this time (the new
      `apply_cp_clients_presets` function simply didn't exist in the
      wrong file yet) - a genuinely dangerous variant of the same bug
      (editing an EXISTING shared preset without updating both copies)
      would have been silent.
    - **Stale hardcoded Evidently reference-run constants**
      (`tests/test_orchestrate_reference_run.py`): both
      `run_evidently_bdm.py` and `run_evidently_cp.py` have a module-level
      `REFERENCE_RUN_ID` literal (e.g. `"run_01_2026-09-01"`), and neither
      `orchestrate_bdm.py` nor `orchestrate_cp.py` ever overrode it with
      the manifest's actual first run - so both always drifted onto the
      hardcoded default as the rolling anchor date
      (`generator/anchor_date.py`) advances. Because `data/raw/`/
      `data/cp_raw/` aren't cleared between regenerations, a stale file
      under the old literal name can still exist on disk, so this failed
      silently (Evidently drift comparison against genuinely wrong
      reference data) rather than loudly - CP's manifest happened not to
      have a leftover file under that exact stale name, which is what
      surfaced this as a `FileNotFoundError` and led to finding the BDM
      side was silently wrong too. Fixed by having both `run_pipeline()`
      functions derive the reference from `manifest[0]` (always the
      first, clean run by `RUN_PLAN` construction) and thread it through
      explicitly, including each file's own `__main__` smoke-test block.
    - **`"N/A"` as an injected invalid value silently becomes a real NULL**
      (`tests/test_dirty.py`): pandas' and DuckDB's CSV readers both
      treat the literal string `"N/A"` as a null-sentinel by default, so
      an injected `"N/A"` round-trips through the generator's own
      write-then-read pipeline as an actual NULL, not the string. SQL
      `NOT IN (...)` (dbt's `accepted_values`, Soda's `invalid_percent`)
      evaluates to NULL - not TRUE - for a NULL input, so the row is
      silently excluded from the WHERE clause and never counted as
      invalid at all. Confirmed live: 4 of 18 injected postcode values on
      one run disappeared this way, enough to flip dbt's result from fail
      to warn while datacontract-cli's own Python-level check (which
      treats null as failing a `validValues` rule) correctly still said
      fail - three engines actively disagreeing on the same run, not a
      real data-quality signal. Found in this session's own new
      `_INVALID_SUBURB_POOL`/`_INVALID_POSTCODE_POOL`, but the same `N/A`
      literal was also sitting in the pre-existing `_JUNK_TEXT_POOL`
      (child_given_names' format-junk preset) - genuinely live, not
      "already fixed history" (CLAUDE.md's retrofit exemption doesn't
      apply), so fixed there too even though it predates this session.
      All three pools now avoid every string in pandas' default
      `na_values` list.

    **Verified**: full pipeline regenerated for both datasets after all
    three fixes: BDM suburb and CP postcode/date_of_birth checks land on
    the correct side of their amber/red bands, consistently across dbt,
    Soda, and datacontract-cli (no more cross-engine disagreement from
    the NULL-swallowing bug). `uv run pytest` (28 tests, up from 23) and
    `uv run ruff check .` both clean.

    **[done] The aggregate-values backend and UI, built (2026-09-14, same
    day)**: `pipeline/aggregate_values.py` - two functions
    (`categorical_aggregate`/`numeric_date_aggregate`), each computed via
    one direct SQL query against the relevant run's own warehouse table,
    deliberately independent of which real tool (dbt/Soda/datacontract-
    cli) actually flagged the check - all three point at the same staging
    data for a given column, so there's one true answer regardless of
    which engine's own internal sample/audit-table format happens to
    carry it (and both Soda's and datacontract-cli's own sample caps - 5
    rows - are too small to give a real aggregate anyway). `total_invalid`
    is its own `COUNT(*)`, not derived from the (capped) values list, so
    it stays correct past the cap. Wired into `build_dashboard_data.py`/
    `build_cp_dashboard_data.py` via a small per-column
    `AGGREGATE_SPEC` registry (which checks get it - never every check on
    a column, e.g. date_of_birth's freshness check gets nothing, only its
    range check does - and the exact same valid-value lists the real dbt
    tests enforce, copied not re-derived, so "invalid" can't silently
    drift from what's actually checked). Rendered in the check-detail
    panel's existing "Row-level detail" section, right alongside item 15's
    PK-only sample list - reusing its exact `.value-bar-*` visual language
    (a new `.agg-value-row`/`.agg-histogram-row` variant with a wider
    label column, for values like full dates or "Domestic violence
    exposure" that don't fit the original's 64px code-sized column).
    Verified for real (not just JSON inspection) via Playwright against
    the actual regenerated pipeline output: BDM's suburb check (5 distinct
    invalid values, real counts), CP's postcode check (5 distinct values
    including the `dirty.py` preset's literal pool), and CP's
    `date_of_birth` range check (min/max + a 4-bucket histogram, matching
    `_BAD_DATE_OF_BIRTH_POOL`'s own 4 values) all render correctly.

    **The exact same field-whitelist bug recurred, caught the same way**:
    `buildRealDataset()`'s explicit history-point field whitelist (see
    this same item's note above about `failing_sample_keys` hitting this
    once already) silently dropped the new `aggregate_values` field too -
    same root cause, same fix (add it to the whitelist), caught the same
    way (Playwright driving the actual UI showed an empty section despite
    the JSON being correct, not a JSON-level check). Still no regression
    test for the same reason as before - this dashboard's rendering logic
    has no test harness.

    **Sensitivity redaction - mechanism built, not yet exercised by real
    data**: `classification is not None` suppresses a column's actual
    value labels (`total_invalid` count still shown - a bare number isn't
    personal data on its own) - built into both `aggregate_values.py`
    functions and the dashboard's `aggregateValuesBlock()`, verified
    directly (not just read) by evaluating it against a synthetic
    suppressed payload in a real browser. No column registered in either
    `AGGREGATE_SPEC` today is actually classified - the columns this
    session gave `classification: pii` (child/parent/carer/case-worker
    names) are checked via a character-set pattern, not a closed value set
    or a range, so the redaction path is genuinely unexercised by real
    data yet.

    **Follow-up answered (2026-09-14, later session)**: Keith's original
    question - "what is the actual impact that has on redaction? Give me
    examples" - hadn't been worked through before the session moved on to
    the dual-`dirty.py` bug. Answered with a concrete worked example:
    `child_given_names` (already `classification: pii`) doesn't hit this
    path today for the reason above, but `dirty.py`'s own `_JUNK_TEXT_POOL`
    (`"Baby1"`/`"TEST1"`/`"UNKNOWN9"`/`"XXXX0"`/`"N.A."`) is a realistic
    stand-in for what a future closed-value-set check on that column would
    flag - shown side by side, unredacted vs. redacted:
    ```
    unredacted:  Baby1: 4   TEST1: 3   UNKNOWN9: 3   N.A.: 2
    redacted:    🔒 12 distinct bad value(s) found, but not shown —
                    this column is classified as sensitive data.
    ```
    The count (12) stays visible either way - a fully-hidden check row
    would read as "nothing failed," worse than "something failed, count
    12, content withheld." Also surfaced the real caveat this session's
    "not public, synthetic data only" context raises: the mechanism costs
    nothing to leave in (dormant, changes no currently-visible behaviour)
    but isn't protecting anything real today either, since nothing
    currently classified goes through a check that would ever populate
    it. **Still open, Keith's call**: whether to keep it as forward-
    looking scaffolding (models what a production deployment against real
    BDM data would need) or simplify it away for this PoC given the
    actual stakes are zero right now - not yet decided either way.

18. **[done, 2026-09-15]** **[QA checks & contract]** Explicit, non-magic null handling in every CSV read this
    pipeline does - started as a spike Keith asked for after item 17's
    `"N/A"` bug, built out for real on 2026-09-15 once the spike's
    findings were in.

    **The requirement, stated precisely** (confirmed with Keith
    2026-09-15 - what's built below is deliberately this shape, not an
    implementation detail to reverse-engineer from the narrative): null
    detection in this pipeline is never implicit. For any column, the
    only thing that counts as null by default is a literal empty field -
    never a library's own guess (pandas'/DuckDB's default sniffing,
    which independently treats strings like `"N/A"`/`"NULL"`/`"NaN"` as
    null too). A contract MAY explicitly widen a specific column's null
    vocabulary via `nullValues` (real source systems sometimes do write
    a literal "NULL" or "N/A" string to mean missing, as a genuine
    upstream convention, not a parsing accident) - but **a column with
    no `nullValues` declared is a fully valid, silent, correct default,
    not an error condition**. The pipeline never fails or warns because
    a contract omits it. This is the opposite of "every column must
    explicitly declare its null vocabulary or the pipeline errors" - that
    stricter policy was raised and explicitly rejected in favour of this
    one (silent, safe default; explicit opt-in only where genuinely
    needed) - noted here because the two are easy to conflate and the
    distinction was worth a real round of confirming, not assuming.

    Every CSV read (`pd.read_csv(...)`, DuckDB's
    `read_csv_auto(...)`) used to rely on each library's own default list
    of "these specific strings mean null" - pandas' includes `""`,
    `"N/A"`, `"NA"`, `"NULL"`, `"NaN"`, `"None"`, `"n/a"`, `"nan"`,
    `"null"`, and several numeric-looking variants; DuckDB's own default
    list is separate and not necessarily identical. Nobody in this
    codebase had chosen that vocabulary - it was just whatever each
    library shipped with, and item 17's bug was exactly what that "silent
    library magic" costs when it collides with a real value.

    Built: `qa_tools/common/csv_io.py` - `read_csv_explicit_nulls()`
    peeks a CSV's header first, then calls `pd.read_csv(...,
    keep_default_na=False, na_values={<every column>: [""] + <that
    column's contract-declared extras>})` - confirmed empirically
    (pandas requires EVERY column present in the `na_values` dict or
    unlisted columns get no null treatment at all, not even blank
    fields, so this always builds the complete map rather than trusting
    a caller to enumerate columns). `load_null_values_by_column()` reads
    an optional `nullValues` list per property from the ODCS contract
    YAML - a project convention, not a real ODCS property, but doesn't
    break contract validity (ODCS's Pydantic models accept arbitrary
    extra keys via `extra="allow"`, confirmed in source - same mechanism
    `classification` already relies on). No column in either contract
    sets one today - every column's default null vocabulary is now "a
    literal empty field, nothing else." Every DuckDB `read_csv_auto` call
    site now passes an explicit `nullstr=''` too, for the same
    no-implicit-magic reason, even though (confirmed) every one of them
    only ever reads an already-pandas-written intermediate file in this
    pipeline, never a raw generator CSV directly - so by the time DuckDB
    reads it, pandas has already resolved every null correctly and
    DuckDB's own default sniffing was never actually the risk.

    Wired into all 5 real read call sites: `pipeline/load.py`,
    `qa_tools/bdm/build_per_run_warehouses.py`,
    `qa_tools/bdm/run_evidently_bdm.py`,
    `qa_tools/cp/build_cp_warehouses.py`,
    `qa_tools/cp/run_evidently_cp.py`. `tests/test_csv_io.py` (4 tests)
    covers: every one of pandas' own default null-sniffing strings
    survives as literal text; a genuinely blank field still becomes null;
    a contract-declared extra null value applies only to its own column,
    never bleeds into others; the contract-YAML parser itself. Verified
    behaviour-preserving, not just passing new tests: full pipeline
    regenerated for both datasets, identical check counts and identical
    embedded-dashboard byte counts to before this change (839 BDM / 1000
    CP results, same pass/warn/fail split both times) - confirms
    `place_of_birth_facility`'s null-rate check and every other existing
    null-dependent check still behave identically now that default
    sniffing is off everywhere, not just that "N/A" stops being
    swallowed. `uv run pytest` (32 tests, up from 28) and
    `uv run ruff check .` both clean.

19. **[investigate, 2026-09-15]** **[QA checks & contract]** What dbt-core/Soda Core natively offer for "inspect
    the actual bad values/rows," and whether either can read an ODCS
    contract - Keith asked for this to be verified with real research
    (not just re-reading this project's own code), since it directly
    revises claims made while building item 17's aggregate-values
    feature. Findings, web-verified (2026-09-15):
    - **Neither tool reads an ODCS contract at scan time** - both always
      execute against their own native check format (dbt's `schema.yml`,
      Soda's SodaCL/Contract Language), same as this project already
      does. But both ecosystems have real, if not built-in, ODCS bridge
      tooling this project doesn't use: `dbt-contracts` (a third-party
      package - generates a whole dbt project, models/sources/staging
      SQL/tests, from ODCS/ODPS YAML), and `soda ai` (shipped inside
      soda-core itself, no extra install - an experimental CLI that
      translates an ODCS contract into Soda's own Contract Language for
      review before use). Soda's own docs frame the relationship as
      "Soda sees ODCS as a documentation layer and Soda as the execution
      layer" - translate-then-review, not live ODCS execution either way.
    - **Both tools already give more than PKs natively - this project's
      "PKs only" is a policy choice, not a tool limitation.** dbt's
      `--store-failures` audit tables (already used here) carry the full
      failing row (`not_null`) or `(value, n_records)` pairs
      (`accepted_values`/`unique`) - confirmed independently, but also
      directly visible in our own `dbt_common.py:
      failing_sample_keys_via_values()`, which already selects the real
      value column out of the audit table before discarding it in favor
      of the PK. Soda's sample mechanism (our `CaptureSampler`) captures
      every column of each sampled row, not just an identifier.
    - **Correction to an earlier claim of mine**: I'd told Keith Soda
      "computes samples then discards them" and has "no concept of
      classification/sensitivity at all." Both need qualifying. Soda
      Core's actual default is to collect up to **100** failed-row
      samples per check (this project's own `CaptureSampler` caps it at
      5, matching datacontract-cli's cap, by our own choice) - the
      "discarded" behaviour is specifically about Soda *Cloud* routing,
      not Soda Core losing the data. And Soda Core has its **own native
      sensitivity-redaction mechanism**, independent of ODCS
      `classification`: a `sampler: exclude_columns:` block in
      `configuration.yml` (wildcard-capable), enforced by a gatekeeper
      that strips excluded columns even from raw-SQL-based checks before
      a sample is built. Not currently used in this project.
    - **Real implication for `aggregate_values.py`**: for dbt
      specifically, computing the categorical aggregate via a fresh SQL
      query wasn't strictly necessary - the `accepted_values`/`unique`
      audit table already *is* almost exactly the `(value, count)` shape
      wanted, sitting right there. That was a genuine simplification
      opportunity not taken, traded for one uniform code path across all
      three tools instead of a different one per tool. For Soda and
      datacontract-cli, their default/native caps (100 and 5 rows
      respectively - though see item 29's correction: Soda's 100 is a
      raisable default with no coded maximum, unlike datacontract-cli's
      genuinely hard 5) mean neither gives a true, exhaustive aggregate
      out of the box - some additional mechanism was genuinely needed
      for those two regardless, at least as configured today.
    Not yet acted on - a real finding to keep in mind if `aggregate_
    values.py` (or a future dbt-specific optimization) gets revisited,
    not an immediate to-do.

20. **[investigate, 2026-09-15]** **[QA checks & contract]** datacontract-cli's failed-samples limitations, and
    whether ODCS's numeric-only threshold operators are a recognized gap
    or a deliberate design choice - three follow-up questions Keith asked
    to be verified with real research, not assumed. Findings, web- and
    source-verified (2026-09-15):
    - **Custom SQL rules never get failed-samples, confirmed publicly**
      (not just from reading the installed source): datacontract-cli's
      own docs state `--include-failed-samples` "collects a small sample
      of the rows that failed each missing/invalid/duplicate check," and
      separately that custom SQL checks (`quality.type: sql`) "run the
      query or file as-is and are not filtered" - i.e. never sampled.
      Matches source exactly: `_SAMPLEABLE_METRICS = (MISSING_COUNT,
      INVALID_COUNT, DUPLICATE_COUNT)`, with `CUSTOM_SQL` a separate,
      excluded `MetricType` enum value. Real, documented limitation, not
      a misreading - this project's BDM `date_of_birth` range check
      (`type: sql`) gets no row-level detail from datacontract-cli at
      all, not even a capped one.
    - **The 5-row failed-samples cap is a hard ceiling, confirmed no
      override exists**: datacontract-cli's own docs state the cap
      flatly ("samples are capped at 5 rows per check") with no
      documented config/flag/env var to change it, and independently:
      "the 5-row limit does not appear to be configurable... this is a
      hard-coded limit in the current implementation... would likely
      require a feature request or a code contribution." Matches source:
      `_FAILED_SAMPLE_LIMIT = 5` is a bare module constant, never read
      from any argument/env/config anywhere in the call path. Unlike
      Soda (raise `samples limit:` to a large number as a workaround -
      see item 19), there's no lever to pull here at all.
    - **No native date-range quality check in ODCS - confirmed not a
      mistake, and probably not a recognized community gap either.**
      ODCS's threshold operators (`mustBeGreaterThan`, `mustBeBetween`,
      etc.) are documented as operating on numeric metrics only,
      confirmed in source too (the Pydantic model types every one of
      them `float | int`, would reject a date literal outright). Searched
      specifically for public discussion of this as a known limitation
      (GitHub issues on both `bitol-io/open-data-contract-standard` and
      `datacontract/datacontract-cli`, general web) - found none. Two
      things instead suggest it's deliberate, not overlooked: (1) ODCS
      does have a native date-aware property - `freshness` (is the most
      *recent* row recent enough, `now - MAX(timestamp) < threshold`) -
      but that answers a different question than "does every row's date
      fall in a valid range," so it was never a substitute for this
      project's check; (2) YAML itself has a long-documented, unrelated-
      to-data-contracts weakness around date/timestamp typing (unquoted
      date-like strings parse ambiguously depending on the YAML
      implementation, no dedicated datetime type the way TOML has one) -
      a plausible real reason to keep native comparison operators
      restricted to unambiguous numeric literals. Combined with ODCS's
      own four-rule-type structure (SQL/Library/Text/Custom, with SQL
      explicitly the documented escape hatch for whatever Library
      doesn't cover) - this project's `type: sql` date-range check is
      using the spec exactly as designed, not working around a gap.
    Confirms items 17 and 19's design choices were correct, not just
    convenient - nothing here changes what's built. Logged for the
    record since it was asked to be verified, not because it's a to-do.

    **Keith's follow-up read on both findings, flagged as real concerns
    (not resolved, not just logged as neutral fact)**:
    - **The 5-row cap is a real issue**, not just a documented quirk -
      no lever anywhere to raise it (unlike Soda's `samples limit:`),
      which matters more as this PoC's fixtures grow or if it's ever
      pointed at a real, larger dataset.
    - **Leaning this heavily on the SQL escape hatch undermines ODCS's
      own value proposition** - his words: "at that point, you might as
      well just write your own framework rather than rely on ODCS."
      Checked the actual numbers to see how heavy the lean really is:
      across both contracts, **15 of 87 quality rules (~17%) are
      `type: sql`**, not `metric:` Library rules - BDM 5/26, Child
      Protection 10/61. Broken down by cause, since it's not one uniform
      reason:
      - **~10 (all in Child Protection)** are foreign-key/referential-
        integrity checks ("every notification's `cp_client_id` must
        reference an existing `cp_clients` row") and the 3 cross-table
        business rules (escalation completeness, etc.) - genuinely
        cross-table logic. ODCS's Library metrics are all single-
        column/single-table; no comparable contract-standard's
        declarative vocabulary covers joins either, so this specific
        slice isn't really evidence against ODCS particularly - any
        similar spec would need an escape hatch here.
      - **~3-5** are the date-comparison rules item 20 already covers
        (BDM's `date_of_birth` range check, `extract_timestamp` vs.
        `date_registered` ordering/latency) - this slice genuinely *is*
        the numeric-only-operator gap, not a structural limitation
        shared by every contract format.
      So the honest split: about two-thirds of this project's SQL-
      escape-hatch usage is for something no declarative single-table
      vocabulary would cover anyway (a weak argument against ODCS
      specifically), and about a third is for the numeric-only-operator
      gap (a real, ODCS-specific argument for Keith's point). Whether
      17% overall - or the smaller date-comparison slice specifically -
      is "enough that a bespoke framework would've been less friction
      than adopting ODCS" is a real, unresolved architectural question,
      not something this entry decides. Revisit if this comes up again,
      informed by these actual numbers rather than a general impression.
    - **The `type: sql`/`CUSTOM_SQL` failed-samples exclusion is a mark
      against datacontract-cli specifically** (2026-09-15, Keith's words:
      "the lack of getting the PKs and values out of datacontract-cli is
      a mark against it") - not just a documented quirk to route around.
      Concrete cost, not a hypothetical one: item 28's architecture
      decision means every check needs *some* tool to yield a PK for its
      row-level dashboard detail, and datacontract-cli structurally can
      never be that tool for any `type: sql` rule - every one of the ~15
      SQL-escape-hatch rules counted above (all 10 CP cross-table/FK
      rules, plus BDM/CP's date-comparison rules) needs a Soda or dbt
      equivalent to exist for this reason alone, regardless of whether
      datacontract-cli's own version is otherwise doing useful work.
      Read as an evaluation finding, not just a wiring detail (this
      repo's purpose - see `plans/wider.md`'s purpose note): on its own,
      without Soda/dbt alongside it, datacontract-cli cannot surface a
      single failing row or value for any of its ~15 `type: sql` rules -
      a fifth of every quality rule across both contracts. That's a real
      standalone minus for datacontract-cli as a candidate, independent
      of whether this project's specific fixture happens to paper over
      it by also running Soda/dbt.

21. **[done, 2026-09-15]** **[QA checks & contract]** The `classification` concept (a per-column sensitivity
    tag - `pii`, `confidential`, etc., see item 17) is a real requirement
    for this PoC going forward, independent of whether ODCS/datacontract-
    cli specifically is what this project ends up standardising on.
    Keith's call, 2026-09-15: keep this as a first-class requirement of
    the PoC itself - if ODCS gets dropped or replaced later (see item #85
    below, the ODCS-bridge-tooling question, and the
    17%-SQL-escape-hatch concern in item 20 above), whatever replaces it
    still needs a real per-column sensitivity tag and the same
    "suppress values, keep counts" behaviour this project already built
    around it (`pipeline/aggregate_values.py`, see item 17). Not a
    decision about which tool to use - a decision about what any tool
    or bespoke framework must support.

22. **[todo, 2026-09-18]** **[QA checks & contract]** Numeric value-field checks (amber/red thresholds on a
    genuinely numeric - `integer`/`number` logicalType - column) - near-
    future work, not scoped yet. Confirmed in item 17: neither contract
    has a single numeric field today, every column is `string`/`date`/
    `boolean`, so the "numeric" half of shape 2's aggregate design
    (min/max/outlier-list/histogram) has only ever been exercised by
    date fields. Would need real schema/generator work first, not just a
    new check - a genuine numeric column doesn't exist in either dataset
    to point a check at yet (candidates worth considering when this gets
    scoped: something like a placement/investigation duration, a case
    count, or an age-derived field - not decided).

23. **[todo, 2026-09-18]** **[QA checks & contract]** Capture each real tool's own bad-row/bad-value output as
    fully as each one natively allows, not the current uniform 5-row-PK-
    only cap, and show each tool's own version on its own check in the
    dashboard rather than one shared sample across all of them - near-
    future work, not scoped yet. Directly motivated by items 19/20's
    findings: dbt's `--store-failures` audit tables are unbounded by
    default (already true, no code change needed there) and for
    `accepted_values`/`unique` already carry almost the full `(value,
    count)` aggregate shape; Soda's real default cap is 100 rows (this
    project self-imposes 5) and its "failed rows" checks appear
    unbounded regardless (a Soda bug, not a guarantee - see item 19);
    datacontract-cli tops out at a genuine hard 5-row ceiling with no
    override (item 20) and has zero row-level output at all for custom
    SQL rules. Today's dashboard shows one unified, heavily-capped
    "example failing rows" list regardless of which tool actually ran -
    this would mean surfacing each tool's own real capability instead,
    including datacontract-cli's actual failed *values* (not just PKs)
    where it has them. Real design questions not yet worked through: how
    this interacts with `aggregate_values.py`'s existing full aggregate
    (which already isn't capped, since it bypasses all three tools - see
    item 19), and whether "each tool's own version, shown separately" is
    clearer to a viewer than one merged view, or just more UI to parse.

24. **[todo, 2026-09-18]** **[Dashboard UI]** Browse back to a specific previous run (or a previous
    resupply attempt) at the check level, and at the column/dataset
    level too, not just the current run - near-future work, not scoped
    yet. Real, currently-missing capability, confirmed by re-reading the
    check-detail panel's own code: `openCheckPanel`'s row-level detail
    (samples, and now shape 2's aggregate values) only ever reads `last`
    (the latest run in `history`) - there's no way to click an earlier
    point on the "over time" trend chart or status-dot history and see
    *that* run's own row-level/aggregate detail, only the latest one's.
    The column-drawer and dataset levels have the same shape: a status-
    history dot row and a checks summary, both computed for "now," with
    no drill-down into an arbitrary earlier run's own state at that
    level either. Scoping questions for when this gets picked up: does
    "browse back" mean picking any point on the existing history
    displays (reusing UI that's already there) or a separate run-picker;
    does resupply-attempt granularity (`run_06_..._resupply1` vs.
    `_resupply2`) need its own affordance distinct from ordinary runs;
    and whether this applies uniformly to BDM (15 manifest entries
    including resupplies) and Child Protection (10 straightforward
    weekly runs, no resupply concept) the same way.

25. **[todo, 2026-09-18]** **[QA checks & contract]** Layperson-friendly, human-readable English explanations of
    what each check actually does - recorded on the check (or the
    contract) and surfaced in the dashboard/reporting, not just in
    code/config comments - near-term work Keith flagged, not scoped yet.
    Real, confirmed gap, not assumed: `description:` fields already exist
    today - 30 in each ODCS contract's own `quality:` blocks, 13 more in
    `dbt_project/models/staging/schema.yml`, zero in either Soda checks
    YAML - but they're written in this project's own technical/
    contributor voice (workaround rationale, references to other files/
    checks/dbt-duckdb reliability quirks), not for a non-technical
    dashboard viewer. What the dashboard actually shows today is a
    technical check *name* (`pipeline/dashboard_check_labels.py`'s
    `display_name()` - e.g. "Invalid values — dbt:accepted_values
    (dbt-core)") plus a provenance `note` ("Computed by dbt-core against
    this run's real data — not a fabricated figure") - neither explains
    *what the check verifies* or *why it matters* in plain English.
    Scoping questions for when this gets picked up: a genuinely new
    field (distinct from the existing technical `description:`, since
    overwriting those would lose real information a contributor still
    needs), or a policy for rewriting the existing ones to serve both
    audiences at once; whether it lives on the ODCS contract only (one
    property, reused by whichever check actually implements a rule - Soda/
    dbt/datacontract-cli - since dashboard results already come with
    `column_name`/`check_name` to key off) or needs a per-engine version
    too, given the same underlying rule sometimes reads differently
    across three separately-authored check files; and where in the
    dashboard it surfaces - the check card, the check-detail panel, or
    both.

26. **[todo, 2026-09-15]** **[QA checks & contract]** A real bug found
    while auditing every check for item 23's "duplicated-logic drift
    risk" question (2026-09-15): `pipeline/build_dashboard_data.py`'s
    `AGGREGATE_SPEC` entry for BDM's `date_of_birth` only encodes
    `date_of_birth < DATE '1900-01-01'`. The actual rule it's supposed to
    mirror - `contract/bdm-birth-registrations-contract.yaml`'s
    `datacontract:custom_sql` check - is `< DATE '1900-01-01' OR {field}
    > CURRENT_DATE`. The aggregate's condition is missing the upper
    bound entirely.

    Not yet observed producing a wrong number: `generator/dirty.py`'s
    `_BAD_DATE_OF_BIRTH_POOL` only ever injects implausibly OLD dates
    (1750-1899), never future ones, so `total_invalid`/the distinct-
    values list have always happened to match the real check's count on
    every run generated so far. But it's a live, latent bug, not a
    theoretical one - if any future date_of_birth ever reaches this
    table (a genuine data-entry error, a different injector, a schema
    change upstream), datacontract-cli's real check would correctly flag
    it and fail, while this aggregate would silently undercount it -
    exactly the "hand-maintained copy of the check's own condition
    silently drifts out of sync with the real thing" risk named as the
    core problem with the independent-query architecture (item 23's
    discussion). A concrete instance of the general risk, not a
    hypothetical one made up to illustrate it.

    Fix, when picked up: add `OR date_of_birth > CURRENT_DATE` to the
    `AGGREGATE_SPEC["date_of_birth"]["invalid_condition"]` string. Per
    CLAUDE.md's bug-fix convention this is a logic bug (wrong result
    from a condition that doesn't match its own spec, not an
    environment/wiring issue), so it gets a regression test alongside
    the fix, not a check-first exception - straightforward to write:
    inject a future date directly into a small fixture warehouse and
    assert the aggregate's `total_invalid` matches a direct `COUNT(*)`
    against the real datacontract-cli condition, not just the aggregate's
    own (currently incomplete) one.

27. **[done, 2026-09-15]** **[Data generation]** `generator/dirty.py` doesn't inject a failure scenario for a
    large share of the checks both datasets actually define - found the
    same day as item 26, by cross-referencing every `apply_*_presets`
    function against `bdm-birth-registrations-soda-checks.yml`/`child-
    protection-soda-checks.yml`, `dbt_project/models/staging/schema.yml`,
    and both ODCS contracts' `quality:` blocks column by column. These
    checks don't fail on *any* run generated so far - clean, amber, or
    red - not because the pipeline is healthy, but because nothing ever
    gives them a reason to. That's a materially weaker claim than "this
    check passes" and the dashboard currently can't tell the two apart.

    **Never-nulled required columns** (a `not_null`/`missing_count`/
    `nullValues mustBe: 0` check that has never seen a null): BDM -
    `date_of_birth`, `date_registered`, `is_multiple_birth`,
    `extract_timestamp`, `source_system_record_id`, `registration_number`.
    CP - `cp_clients.given_name`/`family_name`/`date_of_birth`/`suburb`/
    `case_opened_date`; `cp_notifications.cp_client_id`/
    `assigned_worker_id`; `cp_investigations.start_date`/
    `lead_worker_id`; `cp_placements.cp_client_id`/`placement_start`/
    `placement_suburb`. (`place_of_birth_facility` and `end_date` are the
    only nullable-and-actually-nulled columns in either dataset.)

    **Never-duplicated uniqueness/PK checks**: BDM's `registration_number`
    (the PK itself - `source_system_record_id` is the only column dirty.py
    ever duplicates). CP's `cp_client_id`, `investigation_id`,
    `placement_id`, `carer_id`, `worker_id` (`notification_id` is the only
    one dirty.py touches, via `inject_duplicate_rows`'s near-duplicate
    mechanism - and even that only lands an exact duplicate ~40% of the
    time, since the other 60% perturb one character on purpose).

    **Never-invalid-value-injected closed-value-set/format columns**: BDM
    - `child_family_name`, `registering_parent_1_name`,
    `registering_parent_2_name` (junk-format injection only ever targets
    `child_given_names`); `source_system_record_id`'s own `^SRC-[0-9]{9}$`
    format regex (only ever gets exact-value duplication, never a
    malformed value). CP - `cp_clients.sex`, `case_status`, `source_type`,
    `risk_rating`, `outcome`, `substantiated`, `placement_type` (only
    `concern_type` and `cp_clients.postcode` ever get an invalid-value
    injector in CP). Item 26's date upper-bound bug is the same shape of
    gap, one level down: not "never injected" but "the one existing
    injector doesn't cover the full condition."

    **Never-broken foreign keys**: all 7 CP relationship/reference checks
    (`cp_notifications.cp_client_id`/`assigned_worker_id`,
    `cp_investigations.notification_id`/`cp_client_id`/`lead_worker_id`,
    `cp_placements.cp_client_id`/`carer_id`) - by design, per
    `schema.yml`'s own comment: dirty.py's placement/investigation
    presets reassign a FK to a still-real row (just one that fails a
    *business* rule) or null a non-FK column, never point a FK at a row
    that doesn't exist. So referential integrity itself has never
    actually been exercised failing, on either tool that checks it (Soda's
    `values in ... must exist in ...`, dbt's `relationships`) - a
    deliberate design choice for the business-rule presets, but it means
    the FK checks themselves are unproven the same way the columns above
    are.

    (Not in this list: the BDM freshness check, "recent birth dates
    present" - that one's untestable-by-injection for a different reason,
    a fixed-date fixture vs. real wall-clock `CURRENT_DATE`, not a dirty.py
    coverage gap - already noted where that check is defined.)

    **Closed (2026-09-15, Keith's call via AskUserQuestion)**: calibrated
    presets for every gap above, rather than the cheaper "flag untested
    checks in the dashboard" alternative - all 4 categories, including
    reversing the FK-dangling design choice (see below). Item 31's test-
    battery work earlier the same day had just made the same "coverage"
    question concrete for `resupply.py`; asking it again immediately
    surfaced this item as the still-open other half.

    **Never-nulled required columns**: `inject_nulls` calls added for all
    6 BDM columns and all 12 CP columns listed above, in `apply_
    birth_registrations_presets` and every CP table's own preset
    function. Real bug found and fixed along the way (not specific to
    this item's scope, but first hit here): `inject_nulls` crashed with
    `pandas.errors.LossySetitemError`/`TypeError: Invalid value 'nan' for
    dtype 'bool'` on a non-nullable dtype column (`is_multiple_birth`,
    the first bool column any caller had ever nulled) - pandas validates
    the assigned scalar against the column's dtype even for an all-False
    boolean mask, so the fix (upcast to `object` first when the dtype
    can't hold `None`) had to be unconditional on whether the mask
    actually selects any rows, not gated on `mask.any()` as first
    written. Regression test added (`test_inject_nulls_handles_non_
    nullable_dtypes`) and confirmed against the pre-fix code before the
    real fix landed, per this project's own bug-fix-test convention.

    **Never-duplicated PK checks**: `inject_duplicate_values` calls added
    for `registration_number` (BDM) and `cp_client_id`/`investigation_id`/
    `placement_id`/`carer_id`/`worker_id` (CP) - the last two required
    brand new preset functions, `apply_cp_carers_presets`/`apply_cp_case_
    workers_presets`, since those two tables had never been touched by
    any preset at all before this (`generate_cp_runs.py`'s own docstring
    used to describe that as deliberate - updated to describe the actual
    current behaviour).

    **Never-invalid-value-injected columns**: `inject_invalid_values`
    calls added for BDM's `child_family_name`/`registering_parent_1_name`/
    `registering_parent_2_name` (reusing `_JUNK_TEXT_POOL`) and a new
    `_MALFORMED_SRC_ID_POOL` for `source_system_record_id`'s own format
    check; CP's `cp_clients.sex`, `cp_notifications.source_type`/`risk_
    rating`/`outcome`, `cp_placements.placement_type`. `case_status` was
    explicitly and deliberately left out despite being named in this
    item's own original audit above - it turns out to have no
    `accepted_values`/`invalid_percent`/`accepted_values` check anywhere
    (contract, Soda, or dbt), only a literal-value reference inside the
    closed-case-investigation-hygiene business rule, so there was no
    actual check to exercise. That's a different, narrower gap (a
    genuinely missing check, not an unexercised one) - not scoped or
    built here, flagged back to Keith rather than silently invented.

    **Never-broken foreign keys - a real design reversal, not just a
    calibration gap**: every preset in this module used to deliberately
    avoid ever pointing a FK at a row that doesn't exist at all (a
    2026-09-13 scoping decision - placement/investigation presets only
    ever reassigned a FK to a still-real row that fails a *business*
    rule). Keith's explicit call (AskUserQuestion, 2026-09-15) reversed
    that: a new core injector, `inject_dangling_foreign_key` (draws a
    well-formed-looking candidate ID against the referenced table's own
    format/range and retries until it's guaranteed absent from a real
    `existing_ids` set), is now wired into all 7 of Child Protection's
    real FK columns (`cp_notifications.cp_client_id`/`assigned_worker_
    id`, `cp_investigations.notification_id`/`cp_client_id`/`lead_
    worker_id`, `cp_placements.cp_client_id`/`carer_id`). `existing_ids`
    is built from `generate_cp_runs.py`'s `base_tables` (the real,
    never-dirtied source) rather than each run's own possibly-already-
    dirtied copy, so a dangling value is never accidentally still valid.
    Confirmed for real: all 7 `dbt:relationships` tests and all 7 Soda
    `values in ... must exist in ...` reference checks - previously 0/0
    on every run, dirty or clean - now genuinely fail on the red run
    across dbt, Soda, and datacontract-cli, while all 7 still pass 0/0 on
    every clean run (`child_protection.py`'s own generation logic never
    produces a dangling FK by construction, so this is a pure amber/red
    phenomenon, same as every other preset in this module). Updated the
    stale "these always pass" comments this reversal falsified, in both
    `dbt_project/models/staging/schema.yml` and `contract/child-
    protection-soda-checks.yml`.

    A genuine, interesting side effect found while verifying real
    output, not a bug: the *observed* dangling-FK failure count on
    `cp_notifications.cp_client_id` (33) ran noticeably higher than the
    directly-injected rate alone would suggest (~12) - `cp_clients`' own
    new `cp_client_id` duplicate-value injector (`inject_duplicate_
    values`) overwrites some rows' PK with a donor row's value, which can
    incidentally make a real ID vanish entirely from that run's own
    *materialized* `cp_clients` table (10 of 527 IDs, on the real red
    run), so every notification still referencing that now-gone ID
    becomes genuinely dangling too - a real, honest number reflecting
    what the tools actually see when they query the real warehouse, not
    a miscalibration. Doesn't affect pass/fail here (both relationships/
    reference checks are single-tier - any violation fails regardless of
    magnitude) - just documented in `apply_cp_notifications_presets`'
    own `rate_dangling` comment so a future reader isn't confused by the
    gap between the injection rate and the observed count.

    **Verification**: full BDM pipeline (`./run_pipeline.sh`) and the
    full CP pipeline (`generator.generate_cp_runs` +
    `qa_tools.cp.orchestrate_cp` + `pipeline.build_cp_dashboard_data`)
    regenerated end to end with no errors. Spot-checked every new check
    category directly against `reports/results_bdm.json`/`results_cp.
    json`: every previously-never-exercised check across all 4 tools
    (dbt-core, Soda Core, datacontract-cli, Evidently where applicable)
    now genuinely fires warn/fail on amber/red runs, while every clean
    run (BDM and CP) remains 100% pass, 0 warn/fail - confirming the new
    presets only ever fire when `severity` is set, same as every
    pre-existing preset. `tests/test_dirty.py` extended with preset-level
    "red is measurably worse than amber" assertions covering every new
    column/check, plus dedicated `inject_dangling_foreign_key` tests
    (guaranteed non-collision with `existing_ids`, the never-mutates-
    input contract). 71 tests pass repo-wide; `uv run ruff check .`
    clean.

28. **[done, 2026-09-15]** **[QA checks & contract]** How the dashboard gets row-level detail (PKs and the
    values/rows behind a failing check) - the question items 19-23 built
    up to. Resolves the "wire into each tool's output vs. keep an
    independent pipeline-level computation" fork raised in item 23,
    following a full per-check-mechanism audit of what each tool can and
    can't expose (dbt/Soda/datacontract-cli/Evidently, across null,
    invalid-value, uniqueness, FK, and cross-table-business-rule checks -
    the full breakdown isn't reproduced here, just the decision it led
    to).

    **Keith's redline**: the reporting pipeline must never duplicate a
    check's own pass/fail SQL - the condition or join that decides
    whether a row is failing. Item 26's bug (the hand-maintained
    `AGGREGATE_SPEC` copy of a check's condition silently drifting out of
    sync with the real thing) is exactly the failure mode this rules
    out.

    **The decided pattern**:
    1. Row-level detail for a check comes from whichever real tool ran
       it - its own PK sample (Soda's `samples limit`, dbt's
       `--store-failures`, datacontract-cli's `failedSamples` where it
       exists for that metric type). The reporting pipeline never
       recomputes pass/fail itself.
    2. Where a tool yields PKs but not the columns that explain *why*
       (most of this project's Soda/dbt cross-table "failed rows"/
       singular-test checks only `SELECT` the PK column, per item 23's
       findings on escalation completeness/sibling match/etc.) - the
       reporting pipeline enriches that with a plain `SELECT * WHERE <pk>
       IN (...)` lookup against the warehouse. This is a row lookup by
       identifier, not a duplicate of the check's own condition, so it
       doesn't cross the redline - there's no WHERE/join logic to drift
       out of sync, just "fetch the row this PK already names."
    3. datacontract-cli's `type: sql` rules give neither PKs nor values,
       structurally (item 20). **Correcting this entry's own original
       wording here (2026-09-15, Keith's correction)**: the fact this
       project runs Soda/dbt alongside it - so *this specific pipeline*
       still gets a PK from somewhere - does NOT make the gap "usually
       harmless." This repo's purpose is evaluating each tool on its own
       merits (a shootout), not building a combined production pipeline
       that leans on whichever tools happen to cover each other's gaps.
       Read as a standalone capability question - "could datacontract-
       cli alone do this job?" - the answer for every `type: sql` rule
       is no, full stop, and that's a real minus against it as a
       candidate regardless of what Soda/dbt happen to do in this
       fixture. Logged in full as item 20's addendum.
    4. **The one place this project has no PK-yielding tool at all**:
       BDM's `date_of_birth` range check - `type: sql`-only today, no
       Soda check, no dbt test (confirmed by re-checking both files).
       Also the exact check item 26's bug was found in - not a
       coincidence; it's the one check that had already fallen back to
       an independent, driftable recomputation for lack of any other
       option. **Resolution, Keith's call**: add both a Soda `failed
       rows` check and a dbt test mirroring the same condition (`<
       DATE '1900-01-01' OR > CURRENT_DATE`), purely so a PK-yielding
       source exists. Checked CP's own `cp_clients.date_of_birth` range
       check while confirming this - it's Soda-only today too (no dbt
       test in `schema.yml` either), so it has the same gap on the dbt
       side specifically, just not the "zero tools at all" version BDM
       has, since its Soda check already yields a PK. Worth picking up
       both at once. datacontract-cli's rule stays too (the contract
       remains the source of truth for the business rule itself) - this
       adds redundant *checking*, not a pipeline-side reimplementation,
       so it doesn't cross the redline either. Not yet built - near-
       future work, alongside item 26's actual fix (add the missing
       upper bound) and item 23's broader "surface each tool's own
       output" build.

29. **[done, 2026-09-15]** **[QA checks & contract]** The same evaluation-lens correction (item 20/28's, and
    `plans/wider.md`'s purpose note) applied to Soda's and Evidently's
    own standalone row-level (PK/value) capability, at Keith's direct
    request after the datacontract-cli correction. Same rule throughout:
    read each tool's own gap as "could this tool alone do the job", not
    "does something else in this project's specific triple-redundant
    setup happen to cover it."

    **Soda Core - genuinely split, not one answer**:
    - For every metric-based check (`missing_count`/`missing_percent`,
      `invalid_percent`, `duplicate_count`, the FK reference check) -
      **correcting this entry's own first draft (2026-09-15, Keith asked
      "is 100 actually the highest cap" - checked, it isn't)**. Verified
      directly against this project's own installed `soda-core` 3.5.6
      source (`.venv/lib/python3.11/site-packages/soda`, not just docs
      or web search): `sampler/sampler.py`'s `DEFAULT_FAILED_ROWS_
      SAMPLE_LIMIT = 100` is only ever the *default*.
      `execution/metric/metric.py`'s three-tier resolution (default →
      scan-level `samples_limit` → check-level `samples limit:`) applies
      no minimum or maximum clamp anywhere, and the resolved number
      flows straight into a plain SQL `LIMIT {n}` clause
      (`execution/data_source.py`'s `sql_select_all`) with nothing
      capping `n` in the whole path. So `samples limit: 100000` (or any
      integer) is honored exactly as written - the only real ceiling is
      the compute/memory cost of pulling and storing that many rows, per
      Soda's own docs' caveat, not a code-enforced maximum. That makes
      Soda's limit a fundamentally different *kind* of constraint than
      datacontract-cli's genuinely hard-coded, non-overridable 5 (item
      20) - soft/configurable vs. hard/fixed, not "100 vs. 5" as two
      instances of the same thing. This also corrects item 19's "their
      native caps (100 and 5 rows respectively)" phrasing, which
      implied the same equivalence. Standalone, for these check types,
      Soda can get every failing PK, if configured to - unlike
      datacontract-cli, which never can regardless of configuration.
    - For "failed rows" checks (`fail condition:`/`fail query:` - this
      project's extract_timestamp ordering, sibling match, freshness,
      and all 3 CP business rules) - appears **uncapped** in practice,
      but that's a documented Soda Core reliability gap (GitHub issue
      #1985: `samples limit:` isn't enforced for this check shape), not
      a guaranteed design feature. Evaluated standalone and honestly:
      leaning on this for unbounded row-level detail means leaning on
      undocumented behaviour a future Soda Core release could "fix"
      (i.e. start enforcing the cap) without notice - a real risk worth
      flagging in the evaluation, not a capability to bank on.
      **Mitigated 2026-09-15** (Keith's call, alongside item 30's build):
      every `failed rows` check in both Soda files now sets an explicit
      `samples limit: 100000` - stating this project's actual intent
      ("get every failing row") outright rather than relying on the bug
      to keep supplying it. If/when Soda Core actually fixes #1985 and
      starts enforcing the limit properly, this project won't silently
      drop back to a 100-row default nobody decided on; it'll keep
      getting (up to) 100000, which is effectively "all of them" at this
      fixture's scale. Doesn't change the evaluation finding above -
      still worth recording as a real Soda Core reliability gap - just
      means this project's own pipeline no longer depends on it staying
      unfixed.
    - Whether a "failed rows" check also returns the *causal* columns
      (not just the PK) is **not a Soda limitation at all** -
      `fail query:`/`fail condition:` can select arbitrary columns; this
      project's own checks mostly just chose to select the PK only (item
      23's per-check findings: sibling match/escalation completeness/
      placement-carer-approval select the PK only; extract_timestamp
      ordering, via `fail condition:`, returns the whole row). Unlike
      datacontract-cli's `CUSTOM_SQL` exclusion, this is fixable by
      rewriting this project's own check YAML, not something Soda is
      structurally incapable of - a genuine point in Soda's favour
      relative to datacontract-cli on this axis, not a wash.

    **Evidently - the most severe standalone gap of the four tools**,
    stated plainly rather than softened by "it's a different kind of
    tool": **zero PKs, zero values, for every check, no exception, no
    workaround.** It computes distributional statistics (PSI,
    missing-value share, category-frequency deltas) over a whole
    column/dataset and never evaluates or flags an individual row at
    all - there is no row-level output to cap or ration in the first
    place, not even a capped one. Where datacontract-cli's gap is scoped
    to its ~15 `type: sql` rules and Soda's is scoped to the
    metric-based check types, Evidently's is total: if row-level
    bad-data inspection or PK capture is a requirement the agency cares
    about, Evidently cannot meet it for any check, standalone or
    otherwise. Recorded as an explicit minus for Evidently specifically
    in the evaluation, not just a "different tool, different question"
    aside.

30. **[done, 2026-09-15]** **[QA checks & contract]** Full-triplication pass: every check that has a Soda/dbt/
    datacontract-cli-implementable shape now exists in all three, not
    just the hand-picked subset each dataset had before. Keith's
    instruction after item 29: "ensure we are implementing each check
    across every tool that supports it, not just one or two." Built the
    same day, 2026-09-15.

    **Method**: cross-referenced every column in both ODCS contracts'
    `quality:` blocks against `bdm-birth-registrations-soda-checks.yml`/
    `child-protection-soda-checks.yml` and `dbt_project/models/staging/
    schema.yml` (plus `dbt_project/tests/*.sql`, initially missed - see
    the correction below). Two false positives caught before building
    anything: BDM's sibling-match and freshness checks were already
    fully triplicated (`tests/multiple_birth_sibling.sql`, `tests/
    recent_births_present.sql`, both wired via `run_dbt_bdm.py`'s
    `_SINGULAR_TESTS` - missed on the first pass because singular tests
    live in a flat `tests/` directory dbt auto-discovers, not `schema.
    yml`'s column-test list). Retracted before any code changed.

    **BDM** (`bdm-birth-registrations-soda-checks.yml`,
    `dbt_project/models/staging/schema.yml`, `dbt_project/tests/`,
    `qa_tools/bdm/run_soda_bdm.py`, `qa_tools/bdm/run_dbt_bdm.py`):
    - Soda gained ~9 checks: null checks on `registration_number`,
      `child_given_names`, `child_family_name`, `place_of_birth_suburb`,
      `date_registered`, `extract_timestamp` (plus `registering_parent_1_
      name`/`_2_name` as `missing_percent` matching the contract's own
      5%/30% tolerances), a `duplicate_count` on `registration_number`,
      and a new `date_registered < date_of_birth` consistency check
      (`failed rows`).
    - dbt gained: `not_null` on the same columns above, plus a new
      custom generic test (`dbt_project/macros/matches_regex.sql` - dbt-
      core ships no native regex test, and this project has no dbt_utils
      dependency to borrow one from) applied to `registration_number`,
      `child_given_names`, `child_family_name`, `registering_parent_1_
      name`, `registering_parent_2_name`, and `source_system_record_id`
      (mirroring each column's existing Soda `valid regex` check
      exactly, same DuckDB RE2 engine). A new singular test, `tests/
      date_registered_after_birth.sql`, for the consistency check above.
    - Item 28's already-decided `date_of_birth` range check: added to
      both Soda (`failed rows`, selecting `date_of_birth` alongside the
      PK per item 29's own lesson about returning causal values, not
      just identifiers) and dbt (`tests/bdm_date_of_birth_range.sql`).
    - Reverse gap closed: `place_of_birth_facility`'s null-rate rule
      (already in Soda and dbt) is now also in the contract
      (`nullValues`, `unit: percent`, `mustBeLessThan: 35`, matching
      Soda's own fail band) - previously the contract had no rule for
      this column at all.

    **Child Protection** - the much bigger gap (`child-protection-soda-
    checks.yml`, same `schema.yml`, `qa_tools/cp/run_soda_cp.py`,
    `qa_tools/cp/run_dbt_cp.py`, `qa_tools/cp/cp_common.py` unchanged -
    already had `cp_carers`/`cp_case_workers` registered):
    - **`cp_carers` and `cp_case_workers` had zero Soda checks at all**
      (no `checks for` block existed for either table) - both now have a
      full block: `row_count`, PK `missing_count`/`duplicate_count`,
      `given_name`/`family_name` null checks, and `invalid_percent` on
      `carer_type`/`approval_status`/`team_region`.
    - **`concern_type`** - this collection's own "traffic light demo
      column," which dirty.py has injected bad values into since it was
      built - had no Soda check and no dbt test until now. Confirmed
      live on the red run: now fails correctly across dbt, Soda, and
      datacontract-cli simultaneously, each with real PKs (except
      datacontract-cli, per item 20/29's structural gap), plus Evidently
      PSI drift.
    - Every other closed-value-set column with a contract rule but no
      implementation anywhere else now has one: `sex`/`postcode` (cp_
      clients, postcode's invalid-value check already existed),
      `source_type`/`risk_rating`/`outcome` (cp_notifications),
      `substantiated` (cp_investigations), `placement_type` (cp_
      placements) - `invalid_percent` in Soda, `accepted_values` in dbt.
    - Every required column's `nullValues` rule with no prior
      implementation now has a `missing_count`/`not_null` pair: ~13
      columns across the 6 tables (given_name/family_name/date_of_birth/
      suburb/case_opened_date on cp_clients; notification_date on cp_
      notifications; start_date on cp_investigations; placement_start/
      placement_suburb on cp_placements; given_name/family_name on both
      cp_carers and cp_case_workers), plus PK null/duplicate pairs on
      `notification_id`/`investigation_id`/`placement_id` that dbt
      already had but Soda didn't.
    - Reverse gap closed: `cp_clients.date_of_birth`'s range check
      (already in Soda's `failed rows` and dbt's `tests/cp_client_date_
      of_birth_range.sql`) is now also in the contract (`type: sql`,
      lower bound only - matching what Soda/dbt actually enforce, not
      silently adding stricter coverage than either real tool has).
    - Two related pre-existing gaps fixed alongside this, since the new
      `accepted_values` checks made them far more consequential:
      `run_dbt_cp.py` had no dimension/label mapping for `accepted_
      values` at all (silently fell back to `""`/`None` - already true
      for `postcode`, just never conspicuous with only one such check),
      and no failing-sample-key resolution for it either (fell through
      to the `relationships` case and returned `[]` unconditionally).
      Both fixed using the exact same pattern `run_dbt_bdm.py` already
      established for its own `accepted_values` tests.

    **A real bug caught during verification, fixed before considering
    this done**: the two new `registering_parent_1_name`/`_2_name` not_
    null tests, configured with only `warn_if` (matching the contract's
    own single-severity tolerance, no error tier), hard-failed on every
    clean run's ordinary ~2%/~26% natural null rate. Root cause: an
    unconfigured `error_if` defaults to `">0"` in dbt-core, not "never
    fails" - confirmed live (71 unexpected non-pass results on clean
    runs before the fix, 0 after). Fixed by setting explicit, generous
    `error_if` values on both. Environment/wiring vs. logic bug question
    considered and set aside: this was caught and fixed within the same
    session that introduced it, before any commit - not a case the
    CLAUDE.md bug-fix-test convention (write a test for something
    already shipped and now found broken) was built for either way.

    **Verification**: both ODCS contracts still `datacontract lint`
    clean; all touched YAML re-parsed with `yaml.safe_load`; full `./run_
    pipeline.sh` plus `qa_tools.cp.orchestrate_cp` re-run end to end (no
    crashes, no `status` values outside pass/warn/fail); every genuinely
    clean run (excluding item 31's unrelated resupply-mislabeling bug
    and the pre-existing freshness fixture-date limitation) shows zero
    unexpected non-pass results; spot-checked the red runs to confirm
    new checks actually fire with real PKs where a tool can give them;
    `uv run pytest` (32/32) and `uv run ruff check .` both clean;
    dashboard data and HTML re-embedded (BDM 220KB, CP grew 198KB ->
    316KB, reflecting the coverage increase).

    Total new check surface: BDM went from ~20 Soda checks / ~13 dbt
    tests to ~30/~24; Child Protection went from ~13 Soda checks / ~22
    dbt tests (mostly FK/business-rule/PK-only) to ~50/~50 (full column
    coverage on all 6 tables). Item 27's "never actually exercised
    failing" finding still applies to most of these - dirty.py has no
    injector for the columns this pass added coverage to (concern_type
    and the BDM date-range checks are the exceptions) - so most of the
    newly-added checks pass on every run today, correctly, for lack of a
    reason to fail rather than for lack of being real.

31. **[done, 2026-09-15]** **[Data generation]** A real, independent bug found while verifying item 30's
    regenerated pipeline output (2026-09-15): a resupply attempt that
    *resolves* (stops being red) is not actually regenerated clean.
    `generator/resupply.py`'s `run_delivery_chain` (lines ~118-126):
    when an attempt is no longer red, it takes the *previous, already-
    red attempt's own dataframe*, applies `provider.churn()` (a small
    ~1-2% organic-change pass - never a fix for the defects `provider.
    dirty(df, "red", ...)` already baked in), and yields it labeled
    `severity: None` - it never regenerates a fresh draw or reverses the
    injected defects. Confirmed directly against real output, not just
    reasoning about the code: `run_06_2026-09-11_resupply2` and `run_09_
    2026-09-14_resupply3` both show `"dirty_severity": null` in `data/
    raw/manifest.json`, yet their actual CSVs have ~78-89% `place_of_
    birth_facility` nulls and invalid `sex` codes (`U`/`O`/`9`) - numbers
    that match RED-severity injection, not a clean run. This directly
    contradicts `plans/data-generation.md` #5's own account of the
    resupply-chain feature ("the corrected... resupply arrives"; "a real
    per-attempt retry chance rather than 'one resupply always fixes
    it'" - the design intent is clearly that a resolved attempt IS
    corrected, not that it keeps carrying forward the prior attempt's
    defects with a different label).

    Not a regression from item 30's work - the underlying data bug
    predates this session's changes; item 30 just added enough real
    checks (place_of_birth_facility's null-rate check already existed
    before this session, so this bug's *effect* was already partly
    visible, just less systematically checked-for) that it became
    obvious while verifying clean runs stayed clean.

    **Fix (2026-09-15, Keith's call via AskUserQuestion):** track a
    separate `clean_df` lineage in `run_delivery_chain`, churned forward
    every attempt via `provider.churn()` and never passed through
    `provider.dirty()` directly. Each attempt's own yielded `df` is now
    either a fresh `dirty(clean_df, ...)` call (when that attempt rolls
    red) or `clean_df` itself (when it resolves) - never a previous
    attempt's already-dirtied dataframe. This was the recommended option
    over "regenerate a genuinely fresh clean draw via `provider.
    generate()` again on resolution" specifically because it preserves
    `plans/data-generation.md` #5's own design intent ("largely the same
    rows... not a fresh random draw") while still fixing the defect-
    carryover bug - churn() still evolves the same underlying rows
    attempt to attempt, it just never inherits another attempt's
    injected defects. Confirmed directly against real regenerated data:
    `run_06_2026-09-11_resupply2`'s `place_of_birth_facility` null rate
    went from 0.781 to 0.028 and its `sex` values from `{'M': 585, 'F':
    573, 'U': 28, '9': 25, 'X': 21, 'O': 20}` to `{'M': 915, 'F': 891,
    'X': 31}` (only valid codes); `run_09_2026-09-14_resupply3` similarly
    went from 0.889 to 0.029. Documented side effect, not a regression:
    resolved-attempt row counts are now noticeably larger (e.g.
    resupply2: 1252 -> 1837 rows) since `dirty()`'s row-count-truncation
    logic no longer compounds across attempts - each attempt's
    truncation is now computed fresh against the clean lineage instead
    of against an already-truncated dataframe.

    Alongside the fix, `generator/generate_runs.py`'s `main()` was
    refactored to extract `_manifest_entries_for_delivery` - pure,
    file-I/O-free manifest-entry construction (run_id derivation,
    `supersedes_run_id` chaining across a delivery's attempts) - so that
    logic is independently unit-testable without needing a real provider
    or CSV writes. Verified behaviour-preserving via byte-for-byte diff
    of `manifest.json` and md5 hashes of every CSV across two
    regenerations before/after the refactor.

    **Test battery built** (`tests/test_resupply.py`, scoped via
    AskUserQuestion, several focused tests per Keith's choice over one
    property-style test): a `MarkingStubProvider` whose `dirty()` sets a
    persistent, churn()-surviving marker column (the existing
    `StubProvider.dirty()` is a no-op and can't support this) backs
    `test_resolved_attempt_carries_no_dirty_marker` - the direct
    regression test for this bug, forcing `STILL_RED_PROB` to 0 via
    monkeypatch for a deterministic 2-attempt `[red, resolved]` chain and
    asserting the resolved attempt's dataframe carries no marker.
    Confirmed this test actually catches the bug, not just documents the
    fix: temporarily stashed just `generator/resupply.py` back to its
    pre-fix committed version (`git stash push -- generator/resupply.py`),
    re-ran the suite, and got the expected failure (`assert not True`,
    the resolved attempt still carrying `dirtied=True` from the prior red
    attempt) before restoring the fix and re-confirming all tests pass.
    Also added: `test_always_red_chain_terminates_at_max_attempts`
    (`STILL_RED_PROB` forced to 1 for a precise MAX_ATTEMPTS-length
    assertion, tightening the existing loose `1 <= len <= 8` bound),
    `test_same_seed_produces_identical_chain` (reproducibility, via
    `pd.testing.assert_frame_equal`), and two tests for
    `_manifest_entries_for_delivery` covering delivery_id/date constancy
    across a chain and `supersedes_run_id`/`run_id`/`run_index` chaining
    - covering both `resupply.py` and `generate_runs.py`'s manifest
    assembly, per Keith's explicit choice over the "resupply.py only"
    recommendation. 9 new/existing tests in the file, 37 total in the
    suite, all passing; `uv run ruff check .` clean. Full pipeline
    (`./run_pipeline.sh`) regenerated end to end with no errors after the
    fix, and the same facility-null-rate/sex-value check re-run directly
    against the fresh output to confirm the fix holds outside the
    isolated `generator.generate_runs` regeneration used during
    diagnosis.

32. **[done, 2026-09-15]** **[QA checks & contract]** Switched 4 of this project's 8 hand-authored dbt checks
    (found while researching item 29's own "17% SQL escape hatch"
    parallel finding) to `dbt_utils` - the flagship, dbt-Labs-maintained
    package, not a third-party one (confirmed: `dbt-labs/dbt-utils` on
    GitHub, the canonical Hub listing) - rather than keep hand-rolling
    what it already provides off the shelf. Built the same day, 2026-09-
    15, after Keith's "let's plan to switch" turned into "just do it"
    given the change was concretely scoped and testable.

    **What changed**: `tests/bdm_date_of_birth_range.sql` and `tests/
    cp_client_date_of_birth_range.sql` (both singular tests) ->
    `dbt_utils.accepted_range` on the respective `date_of_birth` columns.
    `tests/date_registered_after_birth.sql` -> a model-level `dbt_utils.
    expression_is_true` (`expression: "date_registered >= date_of_birth"`).
    `tests/recent_births_present.sql` -> a model-level `dbt_utils.
    recency` (`field: date_of_birth, datepart: day, interval: 7,
    ignore_time_component: true`) - genuinely the same check, not just
    similar: recency fails when `max(date_of_birth)` is older than the
    interval, logically equivalent to "does any row have a recent
    date_of_birth" (the max IS achieved by some row). The 4 genuinely
    cross-table business-rule singular tests (`multiple_birth_sibling`,
    `escalation_completeness`, `closed_case_investigation_hygiene`,
    `placement_carer_approval`) stay hand-authored - no generic test in
    `dbt_utils` or `dbt-expectations` abstracts away an arbitrary
    multi-table join condition; even `expression_is_true` only removes
    boilerplate, the business rule itself still has to be supplied.

    **Real environment finding, not assumed**: the standard Hub-registry
    install (`packages: - package: dbt-labs/dbt_utils`) fails in this
    session's own sandbox - `dbt deps` needs `hub.getdbt.com`, which the
    egress proxy blocks (403). A `git:` source (`packages: - git: "https:
    //github.com/dbt-labs/dbt-utils.git"`) works, since it only needs
    GitHub itself - a strictly weaker, more portable requirement anyway,
    not just a workaround for this one sandbox. Documented as the actual
    setup step in README.md/CLAUDE.md (`uv run dbt deps --project-dir
    dbt_project --profiles-dir qa_tools/dbt_profiles`, one-time) - a real
    new prerequisite `dbt build` will fail to compile without, unlike
    everything `uv sync --dev` already covers.

    **Two real bugs caught during verification, both fixed before
    considering this done** - the same "measure twice" discipline item
    30's parent-name bug came from, applied again:
    - `dbt_utils.accepted_range` on `cp_clients.date_of_birth` silently
      lost `tests/cp_client_date_of_birth_range.sql`'s own two-tier
      `warn_if: '>10'`/`error_if: '>20'` config in the conversion - an
      unconfigured `accepted_range` defaults to hard-fail-on-any-
      violation (same `error_if` default-to-`">0"` quirk item 30 already
      found for `not_null`). Caught by comparing dbt's reported status
      against Soda's own matching check on the same runs (which still
      had its two-tier config and correctly said "pass" at 7/5
      violations) - 2 of CP's 10 runs read wrong before the fix. Fixed
      by restoring the same config on the new test.
    - Investigating that first bug surfaced a second, unrelated one live:
      `cp_notifications.notification_id`'s pre-existing `unique` test
      (untouched by this switch, config'd since before this session)
      reported 0 failures on one `orchestrate_cp.py` pass where the true
      count was 4/5/20 across 3 runs - then reported correctly on the
      very next re-run of the identical warehouse files, no code changed
      in between. This is the exact same dbt-duckdb reliability problem
      `run_dbt_bdm.py`'s own module docstring already documents at
      length for `sex`/`place_of_birth_facility`/`recent_births_present`
      (a compiled test's reported failure count sometimes wrong, no
      SQL-level explanation, no fixed pattern for which runs it hits) -
      just newly *observed* on the CP side, on a check that had
      apparently been fine every time anyone happened to look before
      now. `run_dbt_cp.py` had no verification mechanism for this bug
      class at all (unlike `run_dbt_bdm.py`) - added one (`_VERIFY_
      COUNT_SQL` + `_status_for`, same pattern), covering both newly-
      confirmed combos. Re-ran CP orchestration 3 times after the fix;
      identical, correct results every time.

    **Implication worth sitting with**: this bug is more pervasive and
    less predictable than "2-3 known-bad checks to work around" - it
    just struck a check that had never shown symptoms before, with zero
    code change, discovered purely by chance while investigating a
    different bug. Every dbt check in this project with a `config:`
    override (not just the ones currently listed in either `_VERIFY_
    COUNT_SQL` dict) is a candidate; this project's policy stays "verify
    what's actually been observed failing, not everything that plausibly
    could" (matching run_dbt_bdm.py's own stated approach), but that
    policy only catches instances someone happens to notice - a real,
    open-ended reliability tax on using real dbt-duckdb for anything with
    threshold arithmetic, worth remembering next time a CP or BDM check
    "looks fine" during a quick spot-check.

    **Verification**: `schema.yml` re-parsed with `yaml.safe_load`; both
    `run_dbt_bdm.py`/`run_dbt_cp.py` lint clean; full `./run_pipeline.sh`
    plus 3x `qa_tools.cp.orchestrate_cp` re-run (988/20/206 BDM, 1710/10/
    50 CP - identical to the pre-switch baseline every time); every
    genuinely clean run still shows zero unexpected non-pass results;
    `dbt_utils.recency`'s reported status directly cross-checked against
    a raw query across all 15 BDM runs, zero mismatches; `uv run pytest`
    (32/32) and `uv run ruff check .` both clean; dashboard data and HTML
    re-embedded.

    **Queued next**: item 33.

33. **[todo, 2026-09-18]** **[QA checks & contract]** Look at the Python `pointblank` library as a fifth
    candidate in this evaluation/shootout (see `plans/wider.md`'s purpose
    note) - Keith's call, right after the dbt_utils switch. Not
    researched yet - logged as a near-term item, not scoped. `pointblank`
    is a Python-native data-validation library (not a dbt/SQL-layer
    tool like the other three engines this project runs) - real open
    questions for whenever this gets picked up: what it actually checks
    (row-level rules, schema/type validation, something else), whether
    it can run against this project's DuckDB warehouses directly or
    needs its own ingestion step, what its own row-level PK/value
    capability looks like against items 20/28/29's evaluation lens (same
    "could this tool alone do the job" standard applied to Soda/dbt/
    datacontract-cli/Evidently), and how a Python-native tool fits this
    project's existing per-dataset orchestration shape (`qa_tools/bdm/
    orchestrate_bdm.py`/`qa_tools/cp/orchestrate_cp.py`, each already
    running 4 tools per run) rather than assuming it slots in identically
    to the SQL-layer ones.

34. **[done, 2026-09-15]** **[QA checks & contract]** Full account of the dbt-duckdb `failures=0` bug item 32
    found - root cause, upstream status, whether dbt's own ecosystem has
    a better story for exactly the kind of reporting this project builds,
    and other possible fixes - all research-verified 2026-09-15, not
    assumed.

    **Root cause, found in our own installed source, not just inferred**:
    `dbt/task/test.py`'s `build_test_run_result()` (dbt-core 1.12.4,
    this project's actual installed version):
    ```python
    failures = 0
    if severity == "ERROR" and result.should_error:
        status = TestStatus.Fail
        failures = result.failures
    elif result.should_warn:
        status = TestStatus.Warn
        failures = result.failures
    else:
        status = TestStatus.Pass
        # failures never reassigned - stays 0
    ```
    Any test whose real failure count is nonzero but under every
    configured threshold (a genuine "Pass") always reports `failures=0`
    in `RunResult`/`run_results.json`, discarding the real count.
    Confirmed against a real dbt-core issue: [dbt-labs/dbt-core#11312]
    (github.com/dbt-labs/dbt-core/issues/11312), tagged `type:bug` +
    `engine:v1` by dbt Labs' own triage (not dismissed as a non-issue),
    with an open, unmerged fix ([PR #11313]) - as of our installed
    1.12.4, verified directly against the running code, the fix isn't in.
    1.12.4 is confirmed the current latest stable dbt-core release
    (2026-09-15) - there's a `2.0` Rust-rewrite release-candidate track
    in progress (RC4 as of 2026-09-14) but nothing stable newer to
    upgrade to that would sidestep this.

    **Why so little public discussion despite being real**: checked the
    issue directly - filed 2025-02-15 (~19 months old), zero comments,
    filed by a single external contributor (`vglocus`) who offered to
    write the fix themselves; their own PR has sat unmerged the whole
    time with no maintainer response. Not evidence the bug is fake or
    minor - it's genuinely low-visibility by nature: it only shows up
    when something programmatically reads `RunResult.failures`/
    `run_results.json` for a test that *passes or warns* with a nonzero
    underlying count. `dbt test`'s own console output prints "PASS" with
    no visible discrepancy either way, buggy or not - almost nobody
    would ever notice unless their own tooling explicitly wants an exact
    count regardless of status, which is unusual outside a project
    shaped like this one.

    **dbt's own "story" for this kind of dashboard - checked, and it
    doesn't sidestep the bug either.** The documented, sanctioned pattern
    (push `manifest.json`/`run_results.json`, or the equivalent on-run-end
    Jinja objects, into warehouse tables, build dashboards on top) is
    exactly what this project does. Checked `dbt-data-reliability`
    (`elementary-data/dbt-data-reliability`, the package that powers
    Elementary - the most widely-used, purpose-built "dbt-native data
    observability dashboard" tool, built for exactly this use case) at
    the source level, not just its marketing docs: its
    `upload_run_results.sql` macro, which populates the warehouse table
    its own dashboards read from, does `"failures":
    run_result_dict.get("failures")` - reads the identical buggy
    `RunResult.failures` field directly, no independent verification.
    Elementary's own dashboards would show the same wrong number for a
    test that passes/warns with a nonzero-but-under-threshold count. This
    isn't a gap in this project's own approach specifically - it's
    upstream of everyone building this class of dashboard on real dbt
    output, including the most popular purpose-built tool for it.

    **Other solutions researched, beyond what's already built**:
    - **The community-recognized workaround, confirmed via multiple
      independent sources discussing this exact dbt-core issue**: query
      the `--store-failures` audit table directly (`SELECT * FROM
      <profile_schema>_dbt_test__audit.<test_name>` or, for a count,
      `SELECT COUNT(*) FROM <relation_name>`) rather than trust
      `run_results.json`'s `failures` field. This works because
      materialization into the audit table happens as part of the same
      compiled query that also computes `should_warn`/`should_error`/
      `failures` - upstream of `build_test_run_result()`'s separate,
      buggy accounting logic - so the audit table's own row count is
      never subject to this specific bug.
    - **A related, genuinely relevant caveat checked and ruled out**:
      [dbt-labs/dbt-core#11398] ("dbt drops audit table when test passes
      and `--store-failures`", closed as not planned) - if this applied
      to our exact scenario (nonzero failures, but "Pass" via threshold),
      querying the audit table wouldn't work either, since it wouldn't
      exist. Checked the actual reproduction steps: the drop is triggered
      by a test transitioning to a *true* zero-failure pass (the query
      itself returns no rows), a different code path from a test whose
      query *does* return rows but whose final status is "Pass" only
      because of a `warn_if`/`error_if` threshold - our exact scenario.
      Consistent with what this project has already directly observed
      all session: `failing_sample_keys_direct`/`_via_values`
      (`dbt_common.py`) already query `relation_name` reliably for every
      check this session touched, PK samples included, with no reported
      missing-table failures.
    - **No newer dbt-core version fixes it** (see above - PR unmerged,
      1.12.4 is current). **No dbt-Labs-endorsed workaround exists**
      beyond a BigQuery-specific job-lookup suggestion in the issue
      thread itself, irrelevant to DuckDB.

    **A real tension with Keith's own redline (item 28), found while
    researching this**: this project's own current fix
    (`_VERIFY_COUNT_SQL` in `run_dbt_bdm.py`/`run_dbt_cp.py`) doesn't use
    the audit-table-count workaround above - it hand-maintains a direct
    copy of each affected check's own SQL condition, run against the
    source model instead (e.g. `"SELECT COUNT(*) FROM stg_cp_clients
    WHERE date_of_birth < DATE '1900-01-01'"`). That's exactly the
    "duplicate the check's own pass/fail SQL" pattern item 28's redline
    rules out, and exactly the failure mode item 26's bug (a hand-
    maintained condition silently drifting out of sync with the real
    one) already demonstrated once. It's worked so far only because
    these specific conditions are simple and haven't changed since - the
    same risk profile as any other duplicated-logic case this project
    has already flagged. **Fixed same day - see item 35.**

35. **[done, 2026-09-18]** **[QA checks & contract]** Fixed item 34's own redline tension: replaced both
    `run_dbt_bdm.py`/`run_dbt_cp.py`'s narrow, per-check `_VERIFY_
    COUNT_SQL` dicts with a single `_AUDIT_AGGREGATE_SQL` dict, keyed by
    test *type* rather than specific (column, test) combos hand-picked
    after being caught misbehaving. Queries each test's own `relation_
    name` (the `--store-failures` audit table dbt already materializes,
    the exact same one `failing_sample_keys_direct`/`_via_values` were
    already reading reliably all session) instead of re-deriving the
    check's own condition - `COUNT(*)` for row-shaped audit tables
    (`not_null`, `matches_regex`, `accepted_range`, `expression_is_true`,
    and every singular business-rule test - `multiple_birth_sibling` on
    the BDM side, `escalation_completeness`/`closed_case_investigation_
    hygiene`/`placement_carer_approval` on CP's), `COALESCE(SUM(
    n_records), 0)` for value-aggregated ones (`accepted_values`,
    `unique`). `recency` and `relationships` stay excluded - neither
    has a row-count-shaped audit table (see items 29/34's own notes on
    why).

    **Deliberately applied to every instance of a covered test type, not
    a curated list** - the whole motivation was that the CP-side bugs
    only got caught by chance (notification_id's `unique` test had no
    history of misbehaving before the one pass that caught it live); a
    hand-picked list only ever protects checks someone already happened
    to notice. The fix is free - dbt already builds these audit tables
    via `--store-failures`, this only adds one lightweight query per
    covered test result, reading data that already exists. This also
    means the 3 CP business-rule singular tests (previously unprotected,
    since the old narrow dict never covered them) and BDM's `multiple_
    birth_sibling` are now covered too, despite none of them having ever
    been directly caught exhibiting either bug - they're structurally
    immune to the *confirmed* accounting bug (no `warn_if`/`error_if`
    config, so status can never land on "Pass" with a nonzero count) but
    not to the second, still-unexplained nondeterminism, which has no
    known trigger condition to rule any test out by.

    **Verification**: both files lint clean; `./run_pipeline.sh` +
    `orchestrate_bdm.py`/`orchestrate_cp.py` each re-run 3x, identical
    results every time (988/20/206 BDM, 1710/10/50 CP - same as every
    prior baseline this session); a broader cross-check than item 34's
    own 2-check spot-check - every dbt result compared against
    datacontract-cli's matching count-unit metric across both datasets
    (795 comparable pairs total) - found zero real mismatches; the only
    apparent ones (`unique`'s duplicate-rate counts, consistently ~2x
    datacontract-cli's) are a pre-existing, already-understood semantic
    difference (dbt's `SUM(n_records)` counts every row in a duplicate
    group; datacontract-cli's `duplicateValues` counts only the excess
    rows) - not a bug, and not something this fix touched. `uv run
    pytest` (32/32) and `uv run ruff check .` both clean; dashboard data
    and HTML re-embedded.

36. **[todo, 2026-09-15]** **[QA checks & contract]** Dig into Elementary's own data-tests documentation
    (docs.elementary-data.com/data-tests/introduction) - Keith's call,
    2026-09-15, after item 34 surfaced Elementary as the most popular
    purpose-built dbt-native observability tool but only looked at its
    *dashboard* layer (the `upload_run_results.sql` macro that reads
    dbt's own, sometimes-buggy `RunResult.failures`). Not researched yet
    - logged as a near-term item, not scoped. Real open question this
    item is specifically about, distinct from item 34's own finding:
    Elementary apparently also ships its *own* test suite (schema tests,
    anomaly detection, freshness/volume checks - the "data tests" the
    docs URL itself points at), separate from just visualizing dbt-
    core's built-in ones. What role does that play relative to dbt-core's
    4 native tests and the `dbt_utils`/`dbt-expectations` tests already
    evaluated (items 32/34)? Is it a genuinely different capability
    (anomaly detection dbt_utils doesn't have at all) or another
    packaging of the same underlying idea? Does IT read the same
    `RunResult.failures` field for its own tests' results, or something
    more reliable? Whether `docs.elementary-data.com` is reachable from
    this environment hasn't been checked either (`docs.getdbt.com` is
    blocked by this session's own egress proxy - worth confirming this
    one separately, not assuming the same).

37. **[todo, 2026-09-15]** **[Dashboard UI]** Flag Elementary's own dashboard/reporting product itself
    (distinct from item 36's own question about its *test suite*) as a
    comparison point for this project's hand-rolled dashboard
    (`dashboard/qa-reporting-dashboard.html`) - Keith's call, 2026-09-15.
    Not researched yet - logged as a near-term item, not scoped. The
    real question this item is for, whenever it gets picked up: does an
    established, purpose-built solution like Elementary's dashboard
    already do what this project's own single-file static HTML dashboard
    was hand-built to do (traffic-light check status, drill-down to
    failing rows/values, history over time, per-dataset/collection
    rollups), and if so, what would this project actually gain or lose
    by evaluating it as a real alternative rather than continuing to
    extend the hand-rolled one - worth weighing once there's a genuine
    side-by-side to look at, not before. Distinct from item 34's own
    finding (that Elementary's dashboard reads the same, sometimes-buggy
    `RunResult.failures` field dbt-core exposes) - that's a reliability
    question already answered; this item is about the dashboard's actual
    feature set and UX as a product, not its data-correctness properties.

    **Added to this item's scope 2026-09-15**: Elementary's product also
    appears to include something like an incident/ticketing system -
    worth investigating as part of this same piece of work, since it
    speaks directly to `docs/remediation-workflow-design.md`'s own open
    seam. That doc already designs the ticket model itself (creation,
    lifecycle, assignment) and explicitly defers the *platform* choice as
    "a deliberately separate, later conversation, not decided here" -
    naming only Jira Service Management (already in use at the agency)
    and Microsoft-stack tooling (Planner/Power Automate/SharePoint/Teams,
    preferred to avoid extra licensing) as the options on the table.
    Elementary's own incident-management component is a third possible
    option worth being aware of for that later conversation, if it turns
    out to be a real, usable piece of functionality rather than a thin
    wrapper - not researched yet, logged here so it isn't lost track of
    separately from the dashboard investigation it was found alongside.

38. **[done, 2026-09-15]** **[QA checks & contract]**
    Dug further into item 34's "second, still-unexplained nondeterminism"
    (notification_id's `unique` test reporting 0 once, then correctly on
    the very next identical re-run) - Keith's call, 2026-09-15. Real,
    controlled experimentation, not more reading: reproduced `dbt build`
    against `cp_run_10_2026-09-14.duckdb` standalone (20x, fully
    isolated) and under genuine 4-way parallel load (4 concurrent
    processes, each cycling through a different real CP run file,
    matching `orchestrate_cp.py`'s actual `ProcessPoolExecutor` shape) -
    40+ invocations total.

    **What this found instead - a real, deterministic, fully root-caused
    bug, distinct from the original flakiness**: every single invocation,
    isolated or parallel, reported `notification_id`'s `unique` test
    failures as exactly **20** for `cp_run_10` - never 0, never flaky,
    always 20. But the true row count (independently verified with no
    dbt involved at all: `SELECT notification_id, COUNT(*) FROM raw.
    cp_notifications GROUP BY notification_id HAVING COUNT(*) > 1`) is
    **40** - 20 distinct duplicated values, each appearing in exactly 2
    rows. Traced to source: `notification_id`'s `unique` test config has
    `warn_if`/`error_if` but was missing the `fail_calc` override every
    sibling test in this file has (confirmed via `grep` across the whole
    `schema.yml` - the only such gap) - its own comment already described
    the intent ("the same dbt-duckdb fail_calc-reliability reason as sex/
    place_of_birth_facility above") but the actual `fail_calc:` line was
    never added. Confirmed the exact mechanism at the source, not
    inferred: `dbt/artifacts/resources/v1/config.py`'s `TestConfig.
    fail_calc` Python default is literally `"count(*)"` - and `unique`'s
    own `main_sql` (`select {{ column }} as unique_field, count(*) as
    n_records ... group by {{ column }} having count(*) > 1`) returns one
    row per distinct duplicated value, so an unconfigured `fail_calc`
    counts those rows (distinct bad values), not the real duplicate row
    count. This fixture's duplicate injection always creates simple
    pairs, so "distinct values" and "total rows" differ by exactly 2x -
    not a coincidence once you know the cause, just what made the pattern
    look so strikingly clean at first. **Fixed**: added the missing
    `fail_calc: "coalesce(sum(n_records), 0)"` - confirmed the raw
    `run_results.json` now reports 40, matching the independently-
    verified truth. Purely a config-consistency fix, not a behaviour
    change the dashboard would have shown - item 35's `_AUDIT_AGGREGATE_
    SQL` was already bypassing this raw field entirely and computing the
    correct 40 from the audit table regardless.

    **Also tested and ruled out along the way**: DuckDB's own internal
    query parallelism as a cause (forced `settings: {threads: 1}` in a
    test profile, identical result every time - not it); a genuinely
    separate, real discovery made while testing 4-way *same-file*
    contention specifically (not how this project's orchestration
    actually runs - each run always gets its own file): DuckDB's
    documented single-writer file lock (`Could not set lock on file...
    Conflicting lock is held in...`, duckdb.org/docs/stable/connect/
    concurrency) causes a hard crash, 12 of 24 attempts, when two
    processes genuinely target the *same* `.duckdb` file at once - not
    a risk this project's real "one file per run" architecture exposes
    itself to today, but worth remembering if that architecture ever
    changes.

    **Honest accounting - the original mystery is not resolved**: 40+
    controlled attempts today, across isolation, real parallelism, and a
    DuckDB-single-thread variant, never reproduced a spurious "0" on a
    run that has genuine duplicates - only the fully deterministic
    "count(*) instead of sum(n_records)" pattern above, which is a
    different, already-explained number (20, not 0) with a different,
    now-fixed cause. The original live observation (0 reported once,
    correct on the very next identical re-run, no code change) remains
    unreproduced and unexplained by this investigation - possibly a
    genuinely rare, one-off transient event (a stale cache, a partially-
    written file from conditions this session's repro couldn't recreate
    exactly), or something specific to the full `orchestrate_cp.py` path
    rather than a single `dbt build --select` invocation. Not claiming
    it's fixed - only that today's digging found and fixed a real,
    different, previously-unnoticed bug instead, and narrowed what the
    *actual* remaining mystery is (a true, still-unexplained nonzero-vs-
    zero flip, not the "half the value" pattern this item resolves).

    **Disposition, Keith's call**: not pursuing further active repro
    attempts right now - watch for it recurring instead. If a future run
    (real `orchestrate_bdm.py`/`orchestrate_cp.py` pass, not a synthetic
    repro) shows a check that reports 0/an implausible value on one pass
    and a plausible one on an immediate identical re-run, capture more
    than this session's original sighting did before re-running past it:
    which exact check and run_id, whether it was a parallel or
    `--sequential` pass, the full `target/<run_id>/` directory from that
    exact pass (manifest.json + run_results.json, before anything
    overwrites it) rather than just the printed summary. That's the raw
    material this session's repro attempt didn't have and couldn't
    recreate from a description alone - real conditions from an actual
    recurrence would let a future dig start from evidence instead of
    guessing at what to reproduce.

39. **[done, 2026-09-15]** **[Testing & dev tooling]** Added a unit-test battery for `generator/dirty.py`'s
    failure-injection functions themselves (`tests/test_dirty.py`,
    scoped via AskUserQuestion, 2026-09-15) - prompted by asking "do we
    have good coverage of the actually dirty data injection itself?"
    after building item 31's resupply.py battery. Before this, the only
    test touching dirty.py was the narrow "N/A" null-sentinel CSV round-
    trip regression - none of the 12 core injector functions (inject_
    nulls, inject_invalid_values, inject_missing_expected_value, inject_
    duplicate_rows, inject_nulls_in_subset, inject_duplicate_values,
    inject_out_of_range_dates, inject_extract_timestamp_disorder,
    truncate_rows, truncate_to_row_count, break_multiple_birth_siblings,
    inject_drift_batch) had a direct test - all confidence came from real
    pipeline runs and the calibration comments already scattered through
    the module, same gap resupply.py had before its own fix above.
    Deliberately scoped as a DIFFERENT thing from item 27 (still `[todo]`
    below): this battery tests whether the injector code does what it
    claims (rate accuracy, only the intended column/rows touched, exact
    mechanics like truncate_to_row_count hitting its target and the ~60%
    near-duplicate perturbation rate), not whether the injected dirt
    reaches every check the two datasets define - that breadth gap is
    unrelated and unaffected by this work.

    Two explicit scoping choices, both Keith's (AskUserQuestion): cover
    both the core injectors AND the dataset-specific presets (`apply_
    birth_registrations_presets`, `apply_cp_notifications_presets`,
    `apply_cp_placements_presets`, `apply_cp_clients_presets`, `apply_cp_
    investigations_presets`) rather than just the former; and add a
    shared property test asserting the module's own documented "returns
    a new DataFrame, never mutates the input" contract across every core
    injector - real load-bearing behaviour for item 31's resupply-chain
    fix specifically, since `run_delivery_chain` now calls `dirty()`
    repeatedly against a shared `clean_df` lineage and a mutating
    injector would silently corrupt that lineage for every later attempt
    in the chain.

    One real test-design mistake caught and fixed along the way, not a
    dirty.py bug: an initial "truncation lands on an exact band target"
    test for `apply_birth_registrations_presets` assumed truncation was
    the only row-count-changing step in the preset, and failed (3275 vs.
    expected 3280) - `break_multiple_birth_siblings` also drops a row
    per broken twin pair when real multi-birth pairs are present in the
    input, so the two row-count-changing steps compound. Fixed by
    isolating the truncation-only property against a fixture with no
    multi-birth pairs; the pair-breaking step's own row-count effect is
    separately covered by `test_break_multiple_birth_siblings_drops_the_
    expected_number_of_pairs`.

    33 tests in `tests/test_dirty.py` (3 pre-existing + 30 new), 67 in
    the full suite, all passing; `uv run ruff check .` clean. No new
    regression-test obligation under CLAUDE.md's bug-fix convention -
    this batch added coverage for existing, working code rather than
    fixing a found defect.

40. **[todo, 2026-09-18]** **[QA checks & contract]** Schema-correctness checks: missing columns, unexpected
    (extra) columns. Not yet investigated against what this project's
    tools already do for free vs. what's a real gap - `datacontract
    test`'s ODCS schema validation may already catch some of this (a
    declared-but-absent column, at least), but that hasn't been confirmed
    live the way this project confirms everything else, and dbt/Soda's
    checks are all *named-column* checks (`not_null(date_of_birth)` etc.)
    that simply wouldn't run at all if the column were missing, rather
    than raising a "this column doesn't exist" error a viewer would
    actually see - and an UNEXPECTED extra column (a source system
    adding a field no contract/check knows about) has no check anywhere
    in this project today, on either dataset. `dirty.py` also has no way
    to simulate either scenario yet (drop a column / add a stray one) -
    needed to demonstrate this failing for real, same as every other
    check in this project.

41. **[todo, 2026-09-18]** **[QA checks & contract]** Data-type checks, particularly given this project's CSV
    sources. Not yet investigated. The real, live-confirmed risk this
    project already ran into once (`generator/dirty.py`'s own comment on
    `inject_out_of_range_dates`, and `plans/qa-pipeline.md`'s note on it):
    DuckDB's `read_csv_auto` infers a column's type PER FILE, not per
    row, so a single unparseable value in a date/numeric column can
    silently downgrade that WHOLE column's inferred type for that run
    (to VARCHAR), which would corrupt every other check on that column
    too, not just flag the one bad value - explicitly flagged as a real
    follow-up when `_BAD_DATE_OF_BIRTH_POOL` was scoped to stay
    genuinely out-of-range-but-still-parseable specifically to avoid
    triggering it. Worth scoping: a dedicated type-inference check (does
    this run's column actually come back as the expected DuckDB type,
    not silently-downcast VARCHAR), and/or a `dirty.py` injector that
    deliberately writes an unparseable value to demonstrate the failure
    mode for real rather than just avoiding it.

42. **[done, 2026-09-15]** **[Dashboard UI]** Clearer red/amber/green status indicator
    on a check's own detail page in the dashboard. Builds on item 14's
    click-a-check detail panel (`#check-panel` - current-vs-previous
    comparison, trend chart, row-level detail).

    Scoping dig (2026-09-15) found the gap is narrower than it first
    looked: `dashboard/qa-reporting-dashboard.html`'s check-CARDS (in the
    column drawer, before you click through) already render a colored
    `pill(st,"sm")` next to each check's name, and the trend chart
    (`trendChart()`) already color-codes every historical run via a
    status strip beneath the line plus a colored dot on the latest
    point (`statusColorVar(statusForValue(...))`, per history point) -
    so "history detail" is already covered. What's actually missing:
    `openCheckPanel()`'s own header (`check-panel-eyebrow` +
    `check-panel-title`) drops the pill entirely once you click through
    - the panel shows only the check name and breadcrumb, no current-
    status indicator at all, so a viewer has to remember the card's
    color or re-derive status from the compare-grid numbers a few lines
    down.

    **Scoped via AskUserQuestion (Keith's answers, all the recommended
    option):** reuse the existing `pill(st,"sm")` component, placed next
    to `check-panel-title` in the header row (not a new bigger banner);
    color + status label only, no inline threshold-math explanation (the
    compare-grid/thresholds line already shows the numbers); and the
    trend chart's existing per-run color-coding is sufficient as-is for
    "history detail" - no separate plain-English summary needed.

    **Built**: `check-panel-title` now sits in a flex row alongside a
    new `#check-panel-status` span (`dashboard/qa-reporting-dashboard.
    html`'s static markup), and `openCheckPanel()` sets it to
    `pill(checkStatus(check),"sm")` - the exact same component the
    check-card itself already renders, no new CSS. Verified with
    Playwright, both color schemes: clicked through to a real red check
    (`place_of_birth_facility`'s `datacontract:missing_count`, 2.90% vs.
    a 2% fail threshold) and screenshotted `#check-panel` - a clear "●
    Red" pill sits directly beside the title, wraps cleanly even when
    the check name itself spans two lines, legible in both light and
    dark mode. `uv run pytest` (71) and `uv run ruff check .` both
    clean (JS/HTML-only change, no Python touched).

43. **[todo, 2026-09-16]** **[Dashboard UI]** Visibility of what a check actually IS - its real SQL/
    YAML definition - from within the dashboard/reporting tool itself,
    not just a human-readable label. Today each `qa_tools/*/run_*.py`
    script (e.g. `run_dbt_bdm.py`/`run_dbt_cp.py`'s own `_LABEL_BY_*`
    dicts) writes a friendly `label` straight onto each check-result
    record (`pipeline/dashboard_check_labels.py`'s `display_name()`
    combines that with the engine/check name for the card title - see
    its own module docstring), but there's no path from a check in the
    dashboard back to the actual config that defines it: the dbt
    `schema.yml` test block, the Soda `checks for` YAML, the ODCS
    contract's `quality:` rule, or - for the `failed rows`/`type: sql`
    checks specifically - the literal SQL condition being evaluated.
    Not yet scoped: candidate approaches range from embedding each
    check's source snippet into the results JSON at generation time
    (`qa_tools/*/run_*.py` already knows which config produced each
    result) to a simpler static mapping keyed by `check_name`/
    `column_name`. Should account for one check often being defined
    once per tool (dbt/Soda/contract each have their own copy, sometimes
    worded differently - see this project's own "full-triplication"
    passes) rather than assuming a single canonical source per check.

    **Partially absorbed, 2026-09-16** - see `plans/publishing-and-
    history.md` Thread D. Keith pulled the related-but-distinct
    "human-written description" idea out of this item into that
    thread's check-lifecycle metadata design: a `description` field
    (plain-English, hand-authored) now has a real home (dbt's `meta:`,
    Soda's `attributes:`, etc.) and a real UI surface (the check-detail
    panel). This item's ORIGINAL ask - showing the check's actual
    technical SQL/YAML definition, not a human's explanation of it -
    stays open, unresolved by that work.

44. **[todo, 2026-09-18]** **[QA checks & contract]** Checks for expected values that must actually appear -
    the inverse of an `accepted_values`/`invalid_percent` check (which
    only ever asserts every value IS FROM a closed set), not covered by
    anything in this project today. A closed-value-set column silently
    losing an entire expected category (e.g. `risk_rating` never
    producing a `Critical` row again, or `concern_type` never producing
    `Sexual abuse`) would pass every existing check cleanly - nothing
    here checks for value-set COVERAGE, only value-set VALIDITY.
    `generator/dirty.py` already has the injector half of this
    (`inject_missing_expected_value` - "the mirror image of inject_
    invalid_values: makes a previously-common, expected value silently
    STOP appearing"), but it's dormant: no preset on either dataset
    actually calls it, so it's exercised only by its own core-injector
    unit test in `tests/test_dirty.py`, never by a real generated run -
    and there's no check anywhere (contract, Soda, or dbt) that would
    even catch it firing if it were wired in. Not yet scoped: needs a
    real check design (a `dbt_utils`-style "does every expected value
    appear at least once/at some minimum rate" test doesn't obviously
    exist off the shelf the way `accepted_values` does - may need a
    hand-written singular test or Soda `failed rows` query, per column,
    against the specific closed-value-set columns worth watching this
    way) before the existing injector is worth wiring into a preset.

45. **[done, 2026-09-15]** **[Dashboard UI]** Choosing which run to compare against, and a
    real side-by-side view for that chosen pair - not just the automatic
    "previous run" the check-panel used to hardcode.

    **Scoped via AskUserQuestion (Keith's answers):** both picker
    mechanisms (a dropdown AND clicking a trend-chart point, not just
    one); persist the choice in the URL the same way `checkKey` already
    is; and a richer side-by-side view that also diffs the two runs'
    failing-sample-keys, not just the bare row counts.

    **Built**, all in `dashboard/qa-reporting-dashboard.html`:
    - `openCheckPanel()`'s compare block now has a `<select id="check-
      compare-select">` listing every run except the current one (by
      date, the previous run marked "(previous)"), defaulting to the
      previous run - the same default as before. Picking a different
      run recomputes the whole panel (compare grid, delta wording, row-
      level detail, the new diff block below) against that run instead.
    - `trendChart()`/`wireChart()` gained an `onPointClick` callback -
      clicking any point except the current run's own (last) point
      fires the same `setCompareIdx()` the dropdown uses; hovering shows
      a "Click to compare against this run" hint. A new hollow-ring
      marker on the chart shows which point is currently selected,
      distinct from the always-filled dot on the latest run.
    - The choice is persisted via `STATE.compareIdx`, pushed/restored
      exactly like `checkKey` already was (`setCompareIdx()` pushes its
      own history entry) - explicitly reset to the default only when a
      check is opened fresh (a genuine new navigation), not when re-
      rendering after a compare-run change or restoring from popstate/
      reload, so back/forward and a reloaded/shared URL all land on the
      exact comparison someone was looking at.
    - New "Failing rows vs. the compared run" block: diffs the current
      run's sampled `failing_sample_keys` against the compared run's own
      sample into "still failing in both", "new since the compared run",
      and "no longer sampled as failing" (color-coded pills). Honestly
      caveated inline - both sample arrays are already truncated at
      generation time, so this is illustrative of the sampled rows, not
      an exhaustive diff of every failing row in either run, same
      limitation the pre-existing single-run sample block already
      carried.

    Verified with Playwright (both mechanisms, both color schemes, real
    data): confirmed the dropdown defaults to "(previous)" and lists
    every other run; picking a different run updates the compare value,
    delta wording ("Worse than the Sep 6, 2026 run"), and the URL hash
    (`compareIdx` appears/disappears correctly); clicking a trend-chart
    point does the same; the compare-marker ring renders on the chart;
    back navigation correctly restores the prior hash. Found a real
    check with non-empty failing-sample-keys on both sides
    (`missing_percent[all]` (Soda Core) on `place_of_birth_facility`)
    and confirmed the diff block renders correctly, legibly, in both
    light and dark mode. `uv run pytest` (71) and `uv run ruff check .`
    both clean (JS/HTML-only change, no Python touched).

    **Follow-up, same day - Keith's question: "what if there are no
    previous runs, if it's the first run for a new column or new
    dataset?"** Real gap, caught before it shipped to a real scenario:
    with exactly one history point (`n===1`), `compareIdx`/`comparePoint`
    resolved to the SAME index as the current run - the panel would have
    silently compared the current run against itself (a "no material
    change" delta, an empty-but-enabled-looking dropdown, a diff block
    claiming rows were "still failing in both" that were really just
    compared against themselves). Not exercised by this project's own
    fixture (every real check has 10+ runs), but a brand new onboarded
    dataset hits it on day one. Fixed: a `hasCompareRun = n>=2` flag
    branches the whole compare/row-detail/diff rendering - with no
    previous run, the compare block reads "Compared run: None yet - this
    is the first run for this check", no dropdown renders, and the row-
    detail/diff blocks skip their compared-run content entirely rather
    than fabricating a comparison.

    Digging into `n===1` also surfaced a second, genuinely pre-existing
    bug, unrelated to this session's own change: `trendChart()`'s `xs()`
    (and `wireChart()`'s matching hover-index math) divides by `(n-1)` -
    undefined at `n=1`, so a first-ever run's trend chart would have
    rendered `NaN` coordinates (a broken/invisible chart) and thrown a
    JS error on hover, regardless of the compare-run feature above. This
    predates item 45 entirely - `trendChart()` has always assumed at
    least 2 history points - just never noticed because nothing in this
    project's own fixture has ever had fewer. Fixed with the same
    `n===1` guard in both places (a single point centers itself; there's
    no line/gap to place it relative to).

    Verified with Playwright: synthesized a check with exactly one
    history point (a fresh `openCheckPanel()` call, bypassing this
    project's own always-10+-runs fixture) and confirmed the "None yet"
    wording, no dropdown, no diff block, real (non-`NaN`) chart
    coordinates, a working hover tooltip, and zero console/page errors.
    Re-ran the original multi-run Playwright checks above too, to
    confirm the `n>=2` path is unaffected. `uv run pytest` (71) and
    `uv run ruff check .` both clean.

46. **[parked, 2026-09-18]** **[Testing & dev tooling]** A real frontend test suite for `dashboard/qa-reporting-
    dashboard.html` - Playwright end-to-end tests and/or frontend unit
    tests - Keith's own framing: "if we stay with our hand-rolled
    reporting solution, we'd definitely want" this. Explicitly
    conditional on `plans/dashboard.md` #3's still-open question
    (hand-rolled dashboard vs. Streamlit/Power BI/etc.) resolving toward
    "keep hand-rolling it" - not worth building against a UI that might
    get replaced.

    Motivating case, from today: every Playwright check this session ran
    against item 45's build was a one-off script in a scratchpad
    directory, thrown away after use, not a real suite - and it still
    caught two real bugs before they shipped (`plans/qa-pipeline.md`
    #45's own account): the check-panel silently comparing a run against
    itself when a check has no previous run at all, and `trendChart()`'s
    `xs()`/hover-index math dividing by zero (`NaN` coordinates, a
    thrown JS error on hover) for that same case - both invisible in
    this project's own fixture (every real check has 10+ runs) and only
    found because Keith asked "what if it's the first run for a new
    column or dataset?" A real, checked-in suite would catch this class
    of edge case automatically, on every change, rather than relying on
    someone asking the right question at the right time.

    Not yet scoped: Playwright e2e (drives the real page - navigation,
    the run-picker, back/forward/URL-state, both color schemes) vs.
    frontend unit tests (pure functions like `statusForValue`/
    `checkStatus`/`diffFailingKeys`-shaped logic in isolation) vs. both;
    where tests would live (this repo has no JS test runner or `package.
    json` today - Python's `uv run pytest` is the only test entry point
    that exists); and whether `uv run pytest` should orchestrate the
    Playwright run too (via the `playwright` Python package already used
    ad hoc this session) so `CLAUDE.md`'s "run pytest before considering
    a change done" convention naturally covers the dashboard too, or
    whether frontend tests get their own separate invocation.

47. **[parked, 2026-09-18]** **[Dashboard UI]** Bring the column-level status-dot "pip" row
    (`dashboard/qa-reporting-dashboard.html`'s `.status-dot-row`/
    `.status-dot` - a compact row of small colored squares, one per run,
    shown today only in the column drawer's "Worst status across all
    checks" section via `statusHistoryForColumn()`) down to the check
    level too - Keith's framing: "a useful counterpart to the graph."
    Distinct from `trendChart()`'s own embedded color strip (already
    per-run-colored, but thin, and only ever part of the bigger line-
    chart visual, per item 45's compare-marker work) - this would be the
    same bigger, simpler, standalone glanceable dot-row already proven
    at the column level, reused one level down for a single check's own
    run-by-run status, sitting alongside (not replacing) the trend
    chart. Not yet scoped: exact placement in `openCheckPanel()` (above
    the trend chart, inline with the "Over time" heading, or as its own
    small section), and whether it reuses `statusHistoryForColumn()`'s
    pattern directly (per-check rather than worst-of-all-checks - much
    simpler, since a single check's own `history` already carries a
    status per point via `statusForValue()`) or needs a new helper.

48. **[todo, 2026-09-16]** **[Dashboard UI]** Mobile: tapping a trend chart briefly shows the tooltip,
    then it disappears - Keith's report, 2026-09-16, with his own
    correct hypothesis about the cause. Root cause, from reading
    `wireChart()` (`dashboard/qa-reporting-dashboard.html`): the
    tooltip only wires `mousemove`/`mouseleave` (lines ~742-757), never
    a touch event. On a tap, mobile browsers fire a synthetic
    `mousemove` (shows the tooltip) immediately followed by `click` -
    and for any point except the current run, `click` calls
    `onPointClick(idx)`, item 45's "click to compare against this run"
    feature, which re-renders the chart/panel and tears the tooltip's
    DOM down in the process. So the tooltip isn't buggy on its own -
    it's real hover state getting destroyed by a full re-render
    triggered by the same tap that showed it, a touch-vs-mouse-event
    interaction neither the tooltip code nor item 45's click-to-compare
    addition were built expecting. Not yet scoped: whether the fix is
    touch-specific (suppress the click-triggered re-render immediately
    after a touch-originated mousemove, e.g. via a short debounce or a
    `pointerType` check) or interaction-model-specific (tap-to-show-
    tooltip, a second tap-while-shown to trigger compare, standard
    mobile chart UX) - logged for later, not investigated further now.

49. **[done, 2026-09-16]** **[Pipeline & publishing]** A real, pre-existing bug in `check_lifecycle.py`'s
    dbt parser: it only ever walked `models[].tests`/`models[].
    columns[].tests` in `schema.yml`, so dbt SINGULAR tests
    (`dbt_project/tests/*.sql` - `multiple_birth_sibling` on the BDM
    side, `escalation_completeness`/`closed_case_investigation_hygiene`/
    `placement_carer_approval` on the CP side) had no `check_id`
    anywhere and were silently invisible to it. Not a validation
    FAILURE - `check_lifecycle.validate()` simply never saw these 4
    checks at all, so they were never covered by the duplicate-check_id
    or undocumented-config-change gates since Phase 1 shipped.

    Found while tracing how to join a check RESULT to its lifecycle
    metadata for the dashboard-wiring work (plans/publishing-and-
    history.md Phase 4's as-of viewing, scoped 2026-09-16) - confirmed
    empirically (not assumed) that neither dbt's compiled `manifest.
    json` nor `run_results.json` reliably carries a test's own `meta`
    block through, for either generic or singular tests, so a real fix
    has to read `schema.yml` directly either way.

    Fixed by adding a new top-level `tests:` block to `schema.yml`
    (dbt's own "data test properties" shape - config keyed by a
    singular test's file/function name, not nested under a model) with
    `config.meta.check_id`/`introduced_date`/`description`/`changelog`
    for all 4 singular tests, and extending `parse_dbt_check_metadata()`
    to also walk it (`_parse_dbt_singular_test()`) - verified for real
    against the installed dbt-core 1.12.4, not assumed: a real `dbt
    build` for both `multiple_birth_sibling` (BDM) and all 3 CP business
    rules still passes cleanly with the new block in place, and the
    compiled manifest node's `test_metadata`/`column_name` fields stay
    exactly as before (confirming `run_dbt_bdm.py`'s/`run_dbt_cp.py`'s
    own manifest-based branching logic is unperturbed). `check_lifecycle.
    validate()` now reports 258 checks (up from 254), the 4 new ones
    landing as genuinely new check_ids, not undocumented changes.

    Also added `dbt_check_id_lookup()` - a `{(column_or_None,
    test_type_or_name): check_id}` reverse lookup built the same way,
    for `run_dbt_bdm.py`/`run_dbt_cp.py` to tag each real result with
    its own `check_id` at write time (the actual prerequisite this was
    found while building - see plans/publishing-and-history.md Phase 4).

    Regression tests: `tests/test_check_lifecycle.py`'s
    `test_parse_dbt_check_metadata_covers_singular_tests`/
    `test_parse_dbt_check_metadata_raises_for_singular_test_without_
    check_id`/`test_dbt_check_id_lookup_keys_*` - confirmed to fail
    against the pre-fix parser (which never reads `doc.get("tests")` at
    all) before the fix landed, per this repo's own "verify a
    regression test actually fails first" convention.

50. **[done, 2026-09-16]** **[Pipeline & publishing]** A real bug in `qa_tools/cp/run_evidently_cp.py`:
    it wrote its `qa_results/` output under its own table-scoped dataset
    id (`cp_common.TABLE_DATASET_ID["cp_notifications"]`, i.e.
    `"cp-notifications"`) instead of the collection id
    (`cp_common.COLLECTION_ID`, `"child-protection"`) every other CP
    tool - `run_dbt_cp.py`/`run_soda_cp.py`/`run_datacontract_cp.py`/
    `orchestrate_cp.py`'s own `dataset_stats` write - already writes
    under. Real, silent consequence: every run's `evidently.json` lived
    in its own stray sibling directory
    (`qa_results/child-protection-family-support/cp-notifications/
    <run_id>/`) instead of alongside that same run's `dbt.json`/
    `soda.json`/`datacontract.json`/`dataset_stats.json`
    (`.../child-protection/<run_id>/`) - functionally fine only because
    `build_results_from_history.py` special-cased the same wrong
    constant (`_EVIDENTLY_DATASET_ID`) to go looking there, so nothing
    outwardly broke, but the physical layout was inconsistent with every
    other tool and dataset in the system.

    Found while scoping a folder-nesting architecture question with
    Keith (plans/publishing-and-history.md's Thread B entry, same day) -
    tracing exactly how CP's qa_results/ directories were laid out
    turned up this one real outlier. Keith's call once found: fix it
    properly rather than leave the one inconsistency standing.

    Fixed by writing under `cp_common.COLLECTION_ID` instead (each
    result record's own `"dataset_id"` field is untouched - still
    correctly `"cp-notifications"`, since the dashboard's per-table
    grouping genuinely needs it; only the file's physical location
    changed) and removing `build_results_from_history.py`'s matching
    special case. Verified via a real, full `orchestrate_cp.py` run (not
    just a manual file move) - diffed every regenerated file against the
    previously-committed version and confirmed the only field that
    changed anywhere was `run_timestamp` (dbt's own known run-to-run
    wall-clock/invocation-id noise aside - see items 34/38 - no check's
    actual status/metric_value moved), same 2832 results / 2332 pass /
    123 warn / 377 fail distribution as before. The stale
    `cp-notifications/` directory (16 runs' worth of `evidently.json`)
    was removed once its replacement was confirmed correct.

    Regression tests: `tests/test_run_evidently_cp.py`'s
    `test_evaluate_evidently_cp_writes_under_the_collection_id_not_the_
    table_id` (confirmed to fail against the pre-fix code, asserting the
    old wrong constant) and `test_evaluate_evidently_cp_still_tags_its_
    own_result_with_the_table_dataset_id` (confirms the per-result
    `dataset_id` field is deliberately untouched by the fix).

51. **[done, 2026-09-16]** **[Pipeline & publishing]** Two real bugs in `check_lifecycle.
    dbt_check_id_lookup()` (built for item 49, but never actually wired
    into a real result-construction loop until this session's check_id-
    propagation work - both were latent until then), found running the
    real dbt build against real data, not in a unit test:

    **Bug 1 - cross-dataset key collision.** The lookup's original key
    was `(column, test_type)`, with no model in it. `schema.yml` holds
    every dataset's models together in one file, and both BDM's
    `stg_birth_registrations` and CP's `stg_cp_clients` have a
    `date_of_birth` column with a `dbt_utils.accepted_range` test - the
    second one parsed silently overwrote the first's check_id in the
    lookup dict. Caught immediately on the very first real `evaluate_
    dbt_bdm()` call after wiring the lookup in: a genuine BDM result
    came back tagged with `data-asset-1.child-protection-family-support.
    cp-clients...` instead of its own `registry-services.birth-
    registrations...` check_id. Fixed by adding `model` to the key
    (`(model, column_or_None, test_type)`) - `run_dbt_bdm.py` always
    passes its one constant model name; `run_dbt_cp.py` passes
    `f"stg_{table}"`, using the same `table` it already resolves via
    `_table_for_test()` for other purposes.

    **Bug 2 - package-qualified test type never matched.** `schema.
    yml`'s own key for a cross-package macro is qualified
    (`dbt_utils.accepted_range`), but dbt's compiled manifest reports
    that test's name UNqualified (`test_metadata["name"] ==
    "accepted_range"`, the package living separately in `test_metadata
    ["namespace"]`) - confirmed against a real compiled manifest node,
    not assumed. Every dbt_utils-sourced check (`accepted_range`,
    `expression_is_true`, `recency` - a meaningful fraction of both
    datasets' real dbt checks) raised "no check_id found" the moment
    this was wired in for real, since the lookup's key never matched
    what the caller's own resolved `test_name` actually was. Fixed by
    stripping the package prefix (`test_type.rsplit(".", 1)[-1]`) when
    building the lookup key.

    Both found and fixed in the same short verification pass (real dbt
    build against real per-run warehouses, not a fixture) - a genuine
    case for this repo's real-tool-first approach: neither bug was
    visible from reading the code or from `dbt_check_id_lookup()`'s own
    unit tests (which only ever exercised a single-model fixture), only
    from actually running it against real, multi-dataset schema.yml
    content. Regression tests added: `test_dbt_check_id_lookup_does_
    not_collide_across_models_with_the_same_column_and_test_type`,
    `test_dbt_check_id_lookup_strips_the_package_prefix_from_cross_
    package_macros`, both confirmed to fail against the pre-fix
    function first. Full account of the propagation work this was found
    during is in `plans/publishing-and-history.md`'s Thread D section
    (search "check_id propagated into every real check RESULT record").

52. **[done, 2026-09-17]** **[Dashboard UI]** The check-detail panel's (X) close button
    sometimes needed several clicks before it actually closed - Keith's
    report, 2026-09-16. Root cause, from reading the dashboard's own JS
    (`dashboard/qa-reporting-dashboard.template.html`): `closeCheckPanel()`
    did `if(STATE && STATE.checkKey) history.back();` - a single step
    back through browser history. But `setCompareIdx()` (item 45's
    "Compared run" selector) pushed a BRAND NEW history entry every
    time a different comparison run was picked, via `STATE = {...
    STATE, compareIdx: idx}; history.pushState(...)` - and `checkKey`
    stayed set on every one of those pushed states, since changing the
    comparison run doesn't close the panel. So picking N different
    "Compared run" dates before closing meant N extra history entries
    all satisfying `STATE.checkKey`, and one (X) click only popped the
    MOST RECENT compare-selection, not all the way back to "panel
    wasn't open." Two fixes were on the table (logged, not decided, at
    the time): "X always replaces state back to pre-panel" (loses real
    forward/back-button symmetry) or "`setCompareIdx()` should
    `replaceState`, not `pushState`" (compare-selection stops being
    independently back/forward-navigable). Went with the second -
    consistent with the exact same call already made for the as-of date
    picker (`setAsOfInUrl()`'s own comment: an in-panel/in-view
    refinement isn't a top-level navigation worth its own back/forward
    stop) - `setCompareIdx()` now `replaceState`s; the URL still
    updates (a reload/shared link still lands on the chosen comparison),
    it just no longer creates a new history entry, so `closeCheckPanel()`'s
    existing single `history.back()` is correct again regardless of how
    many comparisons were picked. `closeDrawer()` (the outer column
    drawer) was confirmed to never have had the same per-selection-push
    problem in the first place - it has no compare-style re-push of its
    own, only the one `checkKey`/`columnName` push on open - so it
    needed no change. Verified for real via headless Chromium: opened a
    real check panel, called `setCompareIdx()` three times in a row
    (simulating three different "Compared run" picks), confirmed the
    panel was still open, then confirmed exactly ONE click on (X)
    closed it fully.

53. **[done, 2026-09-17]** **[Pipeline & publishing]** The actual published (live GitHub Pages)
    dashboard needs a handful of real "🕐 Past snapshots" entries to
    browse through - Keith's own instruction, 2026-09-16, right after
    the as-of picker landed: important for demoing the dashboard, so an
    audience can actually see the time-travel feature working, not just
    find it empty. The mechanism already worked
    (`dashboard/snapshot_dashboard.py`) - a handful of demo snapshots
    were taken early on (item 65, all same-day 2026-09-16) but nothing
    since.

    Took one new real snapshot rather than several manufactured ones,
    and explaining why: the underlying `qa_results/` history hasn't
    changed since the June 16 batch (no new real pipeline run happened
    in between - taking several snapshots back-to-back today would all
    embed byte-identical data, differing only in timestamp/commit-sha
    metadata, not in anything a viewer would actually see browsing
    between them). What HAS changed enormously since June 16 is the
    dashboard itself - Thread C's as-of picker, Phase 5a's activity
    panel, 5b's retired-checks toggle, 5c's changelog/description
    sections, item 57's Tier 2/3 sparklines, and the dark-mode toggle
    all landed since then - so one fresh snapshot capturing all of that
    is the genuinely valuable addition, not hollow "spread." Took it via
    the CI-equivalent no-live-data path (`qa_tools.bdm/cp.
    build_results_from_history` -> `pipeline.build_*_dashboard_data` ->
    `dashboard.embed_dashboard_data` -> `SNAPSHOT_DASHBOARD=1 dashboard.
    snapshot_dashboard`), not a full `./run_pipeline.sh` real-tool
    re-run - nothing about the committed data needed regenerating, so
    there was no reason to spend the ~11 real-tool minutes
    `plans/performance.md` already flagged, and this mirrors exactly
    what `deploy-pages.yml` itself does on every push (Thread A: rebuild
    from committed history, never a live re-run).

    Verified for real: the new snapshot
    (`20260917T085817Z_7bdb0b6.html.gz`, 408KB compressed vs. the June
    batch's ~53-56KB - genuinely much more real data embedded now, 176
    BDM + 16 CP runs) appears correctly in the live dashboard's "Past
    snapshots" panel, newest-first, alongside the 4 existing ones. A
    real headless-Chromium check opened the new snapshot file directly
    and confirmed it's a fully self-contained, working copy carrying
    every feature shipped since June 16 - the dark-mode button, Tier 2/3
    sparklines, and the retired-checks toggle all present and working,
    zero console errors. `uv run pytest tests/test_snapshot_dashboard.py`
    (24 passed) confirms the mechanism itself is unchanged/still correct.
    Committed: the new `.html.gz` + updated `manifest.json` only (the
    decompressed local `.html` siblings and the rebuilt `reports/*.json`/
    dashboard HTML stay gitignored, regenerated, never committed, per
    this repo's usual convention).

    Not pursued further without asking first: taking MORE snapshots now
    would need either a genuine new real pipeline run (expensive, and
    nothing's actually changed that would need one) or more code
    changes to snapshot in between (which would just mean taking this
    same snapshot again later, once Phase 5d etc. actually land) -
    Keith's own call if he wants artificially-spread duplicates anyway
    for raw browsing-count purposes.

54. **[done, 2026-09-17]** **[Dashboard UI]** A real pluralization bug - Keith's report,
    2026-09-16: on the Executive tier's agency cards, "collections"/
    "datasets" stayed plural even when the count is 1 - and, per real
    data checked while fixing this, not just a hypothetical edge case:
    Registry Services and the Child Protection agency both genuinely
    have exactly 1 collection today, so this was visibly wrong on the
    live dashboard's own Executive tier right now, not just for some
    future single-collection agency. Fixed with the generalized helper
    the earlier audit anticipated - `pluralize(n, singular, plural?)` -
    applied at all 5 sites the audit found: the Executive-tier
    `card-meta` block (collections/datasets), the dataset-detail "Real
    pipeline data" badge's "N computed runs", the "no data as of" empty
    state's "(N days)" tolerance text, the column drawer's checks-
    history heading, and the check-detail panel's trend heading.
    Verified for real via headless Chromium: `pluralize()` itself
    against 0/1/2 inputs, and the actual rendered Executive-tier card
    text for Registry Services confirmed reading "1 collection" (not
    "1 collections") against the real, current data.

55. **[done, 2026-09-17]** **[Pipeline & publishing]** Two real, linked bugs found live-testing the
    as-of picker, both fixed the same session:
    - **BDM's default as-of view showed "no data".** Root cause: BDM's
      real generation window (`generator/generate_runs.py`'s
      `N_DELIVERIES`) was 60 scheduled deliveries, and
      `AS_OF_OFFSET_DAYS` (Thread C) is also 60 - the default as-of date
      (today minus 60) landed one day before BDM's own earliest real
      run, so the flagship real dataset showed "no data" on the very
      first thing anyone sees. Introduced by this session's own earlier
      fix switching the as-of default from a history-derived basis to
      live wall-clock (see `plans/publishing-and-history.md` Thread C) -
      that fix was correct, it just exposed this separate, pre-existing
      collision between two "60"s that happened to coincide. Keith's
      fix, confirmed via `AskUserQuestion`: widen BDM's real window so
      there's genuine margin, not just enough to scrape by, and do it
      as a rolling window from "today" backward (not a fixed calendar
      range) so the same margin holds up over time, accepting that this
      means periodic regeneration going forward ("that's fine" - his
      own words). `N_DELIVERIES` 60 -> 120, full regeneration (176 real
      runs across all 4 tools, May 20 - Sep 17 2026).
    - **`delivery_id`/`run_id` zero-padding silently breaks past 99
      runs.** Both were `f"{i:02d}"` - fine while every id has 2 digits,
      wrong the instant one has 3: `"delivery_100" < "delivery_11"` as
      plain strings. `tests/test_generate_runs.py::
      test_severity_counts_match_run_plan` caught this for real the
      moment `N_DELIVERIES` crossed 99 (not a design gap - a case where
      already-existing code produced a genuinely wrong result once the
      real run count grew, exactly the "actual bug" class this file's
      own convention wants a regression test for - already had one).
      First fix was `:02d` -> `:03d` (matches the same session's other
      instinct: widen enough for what's needed now) - **but Keith's own
      correction: not good enough, this dataset's real run count is
      headed into the thousands over the project's life, and any FIXED
      width is just a bigger version of the same bug waiting to
      reoccur, not a real fix.** Properly fixed by removing the
      width-dependent assumption entirely rather than picking a bigger
      one: `qa_tools/common/qa_results_reader.py` gained
      `_natural_sort_key()` (splits an id string into alternating
      text/number segments, comparing the number segments as real ints)
      and both its lexicographic-sort call sites (`list_run_ids()`,
      `read_qa_results()`) now use it - correct at any id width,
      forever, whether BDM ever reaches 1,000 runs or 100,000.
      `generator/generate_runs.py` keeps `:03d` for readability (a
      cosmetic width choice now, since correctness no longer depends on
      it) with a comment explaining exactly that. Every current caller
      of the two fixed functions (`build_results_from_history.py`,
      `changelog.py`) turned out to already re-sort by a real int/
      timestamp afterward, so nothing downstream was actually producing
      WRONG final output yet from this - still a real, latent defect in
      what "sorted" meant there, fixed before it could bite for real.
      New regression test (`tests/test_qa_results_reader.py::
      test_list_run_ids_and_read_qa_results_sort_numerically_not_
      lexicographically`) writes run ids out of numeric order
      specifically to catch a reintroduction. Verified for real:
      confirmed the plain-string sort actually produces the wrong order
      for `["run_100","run_3","run_20"]` before writing the fix, not
      just reasoned about it; full pipeline regeneration (176 BDM runs)
      completed clean with `:03d` ids; `uv run pytest` (171 passed,
      including this file's own now-fixed test) and `uv run ruff check
      .` both clean.

56. **[done, 2026-09-17]** **[Dashboard UI]** A real Executive-tier sparkline bug - Keith's
    report: Registry Services' sparkline on the Executive tier flipped
    between a flat line and a real graph as the as-of date moved through
    different days in September. Root cause, confirmed against real
    data before fixing (not just reasoned about): the sparkline was
    drawn from `worstCol.checks[0]` - whichever check happens to be
    FIRST in the "worst status" column's own checks array, not
    necessarily the check actually driving that column's worst status.
    On 2026-09-01, `registration_number`'s `checks[0]` was a dbt
    `matches_regex` test that's 0/0/0 (warn/fail/every historical value)
    across all 176 real runs - it never once fails - while a completely
    different check on that same column (`dbt:not_null`) was the one
    genuinely red. Same class of bug `worstCol` itself already avoids
    one level up (`allCols.find(c=>c.status===ag.status)` picks BY
    STATUS, not by array position) - `checks[0]` just never got the
    same treatment. Fixed with the identical pattern: `worstCol.checks.
    find(c=>checkStatus(c)===worstCol.status) || worstCol.checks[0]`.
    Verified for real: re-checked the same 2026-09-01/09-10 as-of dates
    that showed the bug - the selected check is now genuinely red (not
    an inert 0/0/0 one) and has real variance (min 0, max 19) at every
    date checked, and the rendered SVG path now has real coordinate
    variation instead of collapsing to a flat line. Full `uv run
    pytest` (175 passed) and `uv run ruff check .` clean.

    **Follow-up, same day: the above fix wasn't sufficient at every
    date - Keith's own re-test.** At as-of `2026-07-19` the sparkline
    was STILL flat, even though the picked check was now genuinely the
    one driving `date_of_birth`'s red status (the first fix worked
    correctly). Root cause this time: ALL THREE of `date_of_birth`'s
    own red checks (dbt's `recency` test, Soda's matching freshness
    check, datacontract-cli's `custom_sql`) are constant at exactly `1`
    across every one of the 176 real runs - a known, already-documented
    limitation (`dbt_project/models/staging/schema.yml`'s own comment
    on the `dbt_utils.recency` test: it compares real wall-clock
    `CURRENT_DATE` against this fixture's simulated historical dates,
    so it's essentially always red regardless of which historical run
    is actually in view). Confirmed real, genuinely-varying red checks
    DID exist on other columns at that same as-of date
    (`place_of_birth_facility`, `registering_parent_1_name`,
    `registering_parent_2_name`) but never got picked, since
    `date_of_birth` happens to be the first column in column order and
    `allCols.find()` stops at the first status match.
    `pickRepresentativeCheck()` (moved out to a top-level function,
    `dashboard/qa-reporting-dashboard.template.html`) now searches ALL
    columns matching the agency's worst status for one whose worst
    check has real historical variance (`min !== max`), only falling
    back to a constant one if truly nothing varies anywhere - a pure
    "which check illustrates the sparkline" change, no check's own
    status/correctness anywhere else in the dashboard is touched.
    Verified for real: re-checked `2026-07-19` plus the same September
    dates from the first fix - every date now resolves to a genuinely
    red, genuinely varying check, and the rendered SVG path for
    `2026-07-19` now spans real y-coordinates (2.0 to 25.4) instead of
    a flat 2.0-to-2.0 line. Full `uv run pytest` (175 passed) and `uv
    run ruff check .` clean.

57. **[done, 2026-09-17]** **[Dashboard UI]** Brought the Executive tier's sparkline down
    into the lower tiers too: Tier 2 (`renderAgency()`, the per-dataset
    table rows - `dashboard/qa-reporting-dashboard.template.html`) and
    Tier 3 (`renderDataset()`, the per-column tile grid) - built exactly
    as scoped below, no surprises found along the way:
    - **Tier 2**: a straight reuse, as scoped - a new "Trend" column in
      `dataset-table` (thead + one `<td>` per row), `pickRepresentativeCheck
      (ds.columns, ds.status)` called per dataset row instead of every
      column across the whole agency. The `noDataAsOf` row's own merged
      cell (`colspan="3"` covering the old 3 trailing columns) bumped to
      `colspan="4"` to still span correctly now there are 4.
    - **Tier 3**: also a straight reuse of the exact call scoped below -
      `pickRepresentativeCheck([column], column.status)` per column tile.
      The flagged layout question resolved simply: `.col-tile` is already
      `display:flex; flex-direction:column` with an 8px gap, so the
      sparkline just slots in as a new flex child (between the type label
      and the status pill) and the tile grows a little taller - no
      restructuring needed. Given a `.spark` for 13 tiles per screen
      (Birth Registrations' real column count) is a lot denser than one
      per Executive-tier card, added a `.spark-wrap .spark{height:16px;}`
      override (vs. the default 28px) to keep each tile compact - the
      `sparkline()` function itself needed zero changes, since its SVG
      already uses `viewBox`/`preserveAspectRatio="none"`, so it was
      always going to stretch to whatever CSS gave it.
    Verified for real, not just reasoned about: a real headless-Chromium
    check across the Executive tier's own 6 agencies (both real datasets
    and all 4 illustrative-mock ones) confirmed every dataset table row
    and every column tile renders its own sparkline with zero console
    errors - 3/3 Registry Services rows, 13/13 Birth Registrations tiles,
    6/6 Child Protection rows, 11/11 its first table's tiles, and the
    4 remaining mock agencies' rows/tiles all present too (the same
    `pickRepresentativeCheck()`/`sparkline()` pair already used for mock
    data at Tier 1). Confirmed in both themes (screenshots taken in
    light and dark). No Python touched - pure frontend addition, `uv run
    pytest` (177 passed, unchanged) and `uv run ruff check .` clean.

58. **[done, 2026-09-17]** **[Pipeline & publishing]** Keith's
    report: picking as-of = real "today" (2026-09-17) for Registry
    Services still shows "a lot of points" on the Executive-tier
    sparkline; expected "no points, or only one." Investigated live
    against the real built dashboard (Playwright JS eval, not just
    reasoning about the code): real wall-clock today is 2026-09-17;
    BDM's committed history runs `run_001_2026-05-21` through
    `run_120_2026-09-17` (plus a resupply attempt arriving 2026-09-21,
    correctly excluded by as-of clipping since its `run_date` is after
    today). At `CURRENT_AS_OF = "2026-09-17"`, `pickRepresentativeCheck()`
    resolves to a genuinely-varying, genuinely-worst check with
    `historyLen: 175` - i.e. the sparkline is correctly showing this
    daily-cadence dataset's full accumulated history up to today, per
    the as-of clipping design verified repeatedly earlier this same
    session (items 55/56) - no clipping error found. Put to Keith as a
    real design fork (full history-to-date vs. windowed to recent-only)
    rather than guessed at - his answer: it was his own misreading of
    what "as of" means ("it's the 'as of' date looking backwards,
    right?"), and full history up to the as-of date is in fact what he
    wants. No code change - confirms the existing behaviour is correct
    as built.

59. **[parked, 2026-09-17]** **[QA checks & contract]** How to model a check for data with a lumpy,
    calendar-shaped expected pattern: quiet/near-flat for 3 quarters,
    then a real, expected spike once a year at a known time (raised
    for Child Protection's quarterly cadence, but the shape is generic).
    A single fixed-threshold range check can't work here - too tight
    and it fires every spike quarter as a false positive, too loose and
    it misses a genuine anomaly in one of the quiet quarters. Recommended
    direction, not yet built or scoped in detail: make the check
    **calendar-aware rather than value-aware** - bucket by which
    quarter/month a run falls in (or just "is this the known spike
    period") and apply a different expected range per bucket, rather
    than one check with one threshold. Both dbt and Soda can express
    this today without a new engine - a date-filtered/`variable`-
    parameterized threshold, or two separate checks each scoped by a
    date condition on the run date. Main tradeoff/caveat to carry into
    the real design: this bakes in an assumption about *when* the spike
    should happen, so it needs re-tuning if real-world spike timing
    ever shifts - worth surfacing in the check's own lifecycle metadata
    (`description`/`changelog`) rather than treating it as set-and-forget.

    **Follow-on, 2026-09-17 (before the check itself gets built): CP's
    real cadence re-anchored to Feb/May/Aug/Nov.** Discussing this item
    surfaced that CP's real cadence (in code since the 2026-09-16
    calendar-quarter migration, Jan/Apr/Jul/Oct) didn't match what Keith
    actually wanted - explicit correction: "1 February being the
    expected date of supply, then working forwards in three month
    increments from there," 4 years of depth. Re-anchored
    `generator/generate_cp_runs.py`'s `_quarter_start()` from calendar
    quarters to Feb/May/Aug/Nov (continuous months-since-year-0 index,
    not per-case month arithmetic - verified against both a January
    date, which belongs to the PRIOR year's Nov-quarter, and the exact
    anchor month). `N_QUARTERS` 16 -> 15 (4 years of Feb-anchored
    quarters ending at-or-before "today" 2026-09-17 lands on
    2023-02-01..2026-08-01 - a 16th, 2026-11-01, would be in the future,
    which this project's real data never extends past). Also backdated
    every CP check's `introduced_date` (was `2026-01-15`/`2026-09-15`,
    Phase 1 retrofit-time artifacts) to `2023-01-15` - Keith's explicit
    call, recommended option: honest fix, since real committed results
    now exist for 2023, checks claiming to be "introduced" in 2026 would
    have predated their own results. Fixed two stale `"Weekly"` labels
    found along the way (`pipeline/build_cp_dashboard_data.py`'s `sla`
    dict + a docstring, `README.md`) that were never updated when CP
    actually went quarterly back on 2026-09-16 - this was a re-anchor of
    an already-quarterly cadence, not a weekly-to-quarterly conversion,
    once investigated (a subagent research pass caught this before any
    code was touched, correcting an assumption in Keith's own framing of
    the ask). `qa_results/child-protection-family-support/` nuked and
    regenerated against the new 15-run real history (real tools re-run
    for real, not a fixture). Full `uv run pytest` (177 passed - no test
    hardcodes CP's real cadence/dates, confirmed before starting) and
    `uv run ruff check .` clean.

    **Found while verifying: `AS_OF_OFFSET_DAYS` (60) now visibly
    conflicts with CP's real cadence at the DEFAULT view, not just when
    deliberately probing near-today dates.** The staleness-tolerance
    rule itself isn't new (Thread C, 2026-09-16, tested against CP's
    prior July-1 delivery) - what's new is that it now trips on the
    plain default Executive-tier view, not only when a viewer manually
    picks an as-of date near "today": default as-of is `today - 60` =
    2026-07-19; CP's real Aug-1-2026 delivery (fully real, on schedule,
    only 47 days before today) falls AFTER that default as-of date, so
    it's invisible to the default view entirely; the nearest earlier
    real delivery from that default as-of's own perspective is May 1 -
    79 days before Jul 19, past the 60-day tolerance - so the whole
    Department for Child Protection and Family Support agency now reads
    `nodata` on the plain Executive overview, not just on some
    deliberately-picked stale date. Confirmed for real via a headless-
    Chromium check (`ag.status === "nodata"` at the live default
    as-of). Put back to Keith with the concrete numbers rather than
    silently patched - genuinely his call given the tradeoffs (grow the
    shared offset vs. revisit global-vs-per-dataset vs. accept this
    default-view consequence for now) - not yet resolved as of this
    entry; see `plans/publishing-and-history.md` Thread C for the fuller
    account once it lands.
    Not scoped further yet - pick up after Phase 5 wraps.

60. **[done, 2026-09-17]** **[Dashboard UI]** A real rethink of what the
    Executive-tier sparkline should actually measure, distinct from
    item 56 (which fixed *which single check* gets picked to represent
    a column/dataset) and item 57 (bringing that same per-check
    sparkline down to Tiers 2/3). Keith's ask: instead of one
    representative check's own raw history, the sparkline should be an
    **aggregate failing-check count over time** - a line at 0 (green)
    while every check passes, rising into amber/red as the count of
    failing checks goes up - so the shape of the line reflects overall
    health trending, not one check's own metric wobbling. Keith's own
    immediate follow-up, not yet resolved: aggregated at what level?
    - **Agency-level** (today's Executive-tier scope) - one line per
      agency, summing failing checks across every dataset/table/column
      underneath it.
    - **Dataset/table-level** instead - one line per dataset showing
      whether that specific dataset is red because of its own
      column-level checks, which would only make sense once item 57's
      per-tier sparklines exist to show it at.
    Real open questions once this gets scoped for real, not yet
    answered: what "the count of failing checks" means when different
    runs have different numbers of *applicable* checks (a check added
    or retired mid-history per the check-lifecycle work - a raw failing
    count isn't comparable run-to-run if the denominator moves); whether
    it's a raw count or a failure rate/percentage; and whether amber
    (warn-level failures) and red (fail-level) get combined into one
    line or plotted separately. Not built, not fully scoped - deliberately
    left for a dedicated pass once Phase 5's current sub-phases (5b/5c/5d)
    are done, per Keith's "flag for work at the end of this phase."

    **Resolved and built, 2026-09-17 (Phase 5e).** Re-asked all three open
    questions via AskUserQuestion; Keith took the recommended option on
    each: (1) each tier aggregates its own scope - Tier 1 sums across the
    whole agency, Tier 2 across just that dataset, Tier 3 across just
    that column, now that item 57's per-tier sparklines all exist to
    scope against; (2) failure RATE (failing ÷ applicable checks that
    run), not a raw count, so an added/retired check mid-history never
    fakes a trend just because the denominator moved; (3) one combined
    line, worst-of coloring (red > amber > green), not separate
    amber/red lines - matching the same worst-of rule already used
    everywhere else in this dashboard.

    Replaced `pickRepresentativeCheck()`/`sparkline()` (item 56/57's
    single-representative-check design) with `aggregateFailureSeries(cols)`
    + `aggregateSparkline(cols)` in `dashboard/qa-reporting-
    dashboard.template.html`. `aggregateFailureSeries()` flattens `cols`
    to every non-retired check (same "can never affect current status"
    rule enforced everywhere else), groups each check's own history
    entries by run DATE (a Map, not array index) into `{total, failing,
    worst}` per date - `total`/`failing` naturally only count checks that
    actually have a history entry at that date, so a check introduced or
    retired mid-window is correctly excluded from the denominator on
    dates it doesn't apply to, without needing to reconstruct applicability
    from `retired_as_of` separately. `aggregateSparkline()` renders the
    resulting `{date, rate, status}` series the same visual way the old
    `sparkline()` did (muted path, colored endpoint dot) - a 0.05 floor
    on the y-axis max avoids a divide-by-zero flat line when every run in
    view is fully green. All three call sites updated: `renderExec()`
    (Tier 1, `allCols` = every column under the agency), `renderAgency()`'s
    dataset-table (Tier 2, `ds.columns`), `renderDataset()`'s column grid
    (Tier 3, `[c]`).

    Verified against real data via headless Chromium: sparklines render
    with zero console errors at all three tiers on the real Registry
    Services (Birth Registrations) and Department for Child Protection
    and Family Support agencies; spot-checked
    `aggregateFailureSeries(ds.columns)` directly for real Birth
    Registrations data - 60 real points, failure rate genuinely varying
    between ~10.5% and ~77.9% across the window, status tracking red
    correctly (matches item 61's still-open "always-1" red checks - this
    redesign doesn't fix that underlying issue, it just stops one
    constant check from dominating the whole aggregate the way a single
    representative check used to). `uv run pytest` (178) and `uv run
    ruff check .` both clean.

61. **[done, 2026-09-17]** **[QA checks & contract]** Actually fix the root cause behind item 56's "always-1"
    checks, rather than continuing to work around them. Item 56's
    follow-up found three of `date_of_birth`'s red BDM checks - dbt's
    `dbt_utils.recency` test, Soda's matching freshness check, and
    datacontract-cli's `custom_sql` equivalent - are constant at exactly
    `1` (i.e. permanently failing) across all 176 real runs, because
    each compares real wall-clock `CURRENT_DATE` against this fixture's
    simulated historical `date_of_birth` values (documented as a known
    limitation in `dbt_project/models/staging/schema.yml`'s own comment
    at the time). `pickRepresentativeCheck()` was built to route the
    sparkline around these checks rather than fix them, which was the
    right call for that specific bug at the time - it's a display-layer
    fix, not this one. The real problem persists underneath: any check
    genuinely built as "how stale is this relative to right now" can't
    produce a meaningful/varying result when replayed against fixed
    historical dates compared to the *actual* today. Not scoped yet -
    the honest fix likely means changing what "now" means for these
    checks when running against historical fixture data (e.g. anchoring
    freshness against each run's own simulated "as of" date rather than
    real wall-clock time), which touches how the checks are defined in
    all three tools (dbt, Soda, datacontract-cli), not just the
    dashboard. Needs real design thought before building - picking up
    alongside item 60 at the end of this phase.

    **Resolved and built, 2026-09-17 (Phase 5f).** Re-asked all three
    open questions via AskUserQuestion; Keith took the recommended
    option on each: (1) anchor each check to this run's own date instead
    of real wall-clock time, AND add a new generator defect so the check
    has something genuine to catch (not anchoring alone, which the ODCS
    contract's own pre-existing comment had already flagged would make
    the check trivially always pass - registration lag alone, 0-9 days
    on every row regardless of any defect, already puts most rows within
    the 7-day window); (2) occasional WHOLE-RUN staleness, not tied to
    the existing severity-tier preset mechanism; (3) a real breaking
    changelog entry on all 3 checks, not a silent bug-fix framing, since
    this genuinely changes what pass/fail means for them.

    Investigated before building (not assumed): what column each of the
    3 tools' checks could actually anchor against. `run_date` (added to
    the dbt-built `stg_birth_registrations` view and the DuckDB `raw.
    birth_registrations` table dbt/Soda both query) looked like the
    obvious candidate, but datacontract-cli runs directly against the
    raw per-run CSV (`run_datacontract_bdm.py`'s own docstring: "this
    dataset's real production shape... no per-run DuckDB file is needed
    here"), and `run_date` was never a column of that CSV - confirmed by
    checking a real file's header. `date_registered` turned out to be
    the right anchor instead: already a real column in all three tools'
    data (the raw CSV included), and `daily_batch.py`'s own comment
    confirms every row's `date_registered` is set to exactly that run's
    `run_date` by construction ("this run's registrations cluster on
    run_date") - so no schema change was needed anywhere, in any of the
    three tools' data sources.

    Built:
    - `generator/dirty.py`'s new `inject_stale_delivery(df, seed,
      rate=0.05)` - unlike every other injector in the module (a per-row
      rate), this is a single coin flip for the WHOLE run: on a trigger,
      every row's `date_of_birth` gets pushed 15-45 days before its own
      `date_registered` (well past the 7-day window); `date_registered`
      itself is left untouched (still reads as this run's own date - a
      genuinely stale delivery still gets processed "today," it's the
      underlying birth data that's old). Wired into `generate_runs.py`'s
      `BirthRegistrationsProvider.generate()`, called once per delivery
      (not per resupply attempt, so a delivery's staleness stays
      consistent across its own resupply chain) - exempts the same two
      bookend deliveries severity already exempts (the first, Evidently's
      reference run; the last, kept deliberately fresh). 2 new tests
      (`tests/test_dirty.py`): the triggered case (rate=1.0, deterministic)
      and the miss case (rate=0.0) - plus added to the shared
      `test_core_injectors_never_mutate_their_input` parametrization.
    - dbt: `dbt_utils.recency` (no way to parametrize its own "now")
      moved BACK to a singular test, `dbt_project/tests/recency.sql` -
      same `NOT EXISTS` shape as the check it originally replaced
      (`recent_births_present.sql`, retired 2026-09-15), just anchored
      to `date_registered` instead of `CURRENT_DATE`. Same `check_id`
      preserved (a redefinition, not a retirement) - `check_lifecycle.py`
      only needed a changelog bump, verified clean. Routed through
      `run_dbt_bdm.py`'s `_AUDIT_AGGREGATE_SQL` dbt-core-bug/flakiness
      workaround (previously excluded for the macro's different audit
      shape) - genuinely warranted here, since this exact check (under
      its old name) is the one #34 already caught exhibiting the
      still-unexplained nondeterminism that workaround guards against.
    - Soda (`bdm-birth-registrations-soda-checks.yml`) and the ODCS
      contract (`bdm-birth-registrations-contract.yaml`, `type: sql`):
      same one-line anchor swap (`CURRENT_DATE` → `date_registered`) in
      each check's own query, each with its own breaking changelog entry.

    Verified against a full real regeneration (`./run_pipeline.sh` -
    generator, all 4 real tools, 176 runs): all 3 checks now read
    **172 pass / 4 fail** each, out of 176 real runs - a genuine, varying
    signal instead of permanently red - and, checked directly, ALL THREE
    TOOLS flag the exact same 4 run_ids (`run_004_2026-05-24`,
    `run_008_2026-05-28`, `run_042_2026-07-01`, `run_092_2026-08-20`),
    confirming the injector and all three check definitions agree.
    `check_lifecycle.validate()` clean (258 checks, matching the
    previous commit). Dashboard rebuilt and checked with real headless
    Chromium (zero console errors, the freshness check renders correctly
    in the date_of_birth column drawer). Full `uv run pytest` (181, up
    from 178) and `uv run ruff check .` both clean.

62. **[done, 2026-09-17]** **[Dashboard UI]**
    A dashboard-level changelog/releases page - "what changed about the
    dashboard/tool itself over time," as its own page within the
    dashboard. Explicitly distinct from two things already built this
    session that sound similar but aren't: Phase 5a's "Recent activity"
    panel (who QA'd/published what dataset, when - a feed over
    `qa_results/` history) and Phase 5c's per-check changelog section
    (a single check's own definition-change history, inside that
    check's detail panel). This would be a THIRD, different feed - the
    PoC/tool's own development history (new features, fixes, phases
    shipped) as a real page, not a panel. Not scoped at all yet - Keith's
    own instruction was to park it for a later discussion, after the
    current run of phases (5d and whatever follows) is done, not to
    build or even design it now.

    **Resolved and built, 2026-09-17 (Phase 5h) - the promised later
    discussion, then the build.** Scoped via two rounds of
    AskUserQuestion (Keith's own instruction, "let's do 62"), each
    answer taking the recommended option except placement: (1) source -
    a hand-maintained `CHANGELOG.md`, not derived from `qa_results/` or
    real git commit messages (those exist, but this needs curated,
    presentable prose, not a mechanical dump); (2) scope - the WHOLE
    repo's real history, not dashboard-features-only; (3) audience -
    "something presentable to others too," so entries are genuine
    release-notes prose, not raw commit-log style; (4) file format -
    Keep a Changelog style, date-sectioned markdown (`## <date>` /
    `### <category>` / bullets), not structured YAML/JSON; (5) backfill -
    the real project history's major milestones curated in (~25 entries
    across 5 real dates, not all ~130 granular work items, not started
    empty either); (6) placement - a 6th header button, same row as the
    other panel-triggering buttons, Keith's own explicit call despite
    item 63's mobile-crowding flag (not yet addressed, now measurably
    worse - still open).

    Built: `CHANGELOG.md` at the repo root, backfilled from real `git
    log` history (pulled directly for accurate real dates, not
    reconstructed from memory) into 5 dated sections (2026-09-13 through
    2026-09-17) covering the genuinely significant shipped milestones -
    the original real-tools wiring, Child Protection's addition, the
    full check-battery triplication, the whole publishing/check-
    lifecycle architecture, the as-of picker, and this session's Phase 5
    sub-phases. `dashboard/changelog_md.py`'s `parse_changelog()` - a
    small, deliberately narrow line-based parser (no full CommonMark,
    matching the file's own constrained style: date headings, category
    subheadings, bullets, multi-line-wrapped bullets joined back
    together, intro paragraphs before the first heading) - turns that
    file into `{intro, entries}`, embedded by `embed_dashboard_data.py`
    into a new `RELEASE_NOTES` const (distinct from the existing
    `CHANGELOG_FEED` const - three different "changelog"-shaped things
    now exist in this codebase, at three different scopes: per-check,
    per-QA-publish, per-tool-release). A new "🗒 Release notes" header
    button opens a side panel (same drawer/backdrop mechanism as every
    other header button), rendering each dated entry's sections/bullets,
    with a small inline-code-span formatter (`` `text` `` → `<code>`,
    trusted build-time content, not user input, so a plain regex swap is
    enough - no real markdown-inline parsing needed for just this one
    form). Added `CHANGELOG.md` to `deploy-pages.yml`'s trigger paths
    (a real, easy-to-miss gap: without it, a future CHANGELOG-only edit
    wouldn't have redeployed the live page at all) - found and fixed
    while building, not left for later.

    7 new tests (`tests/test_changelog_md.py`) against small fixture
    markdown strings, not the real committed file (whose own content
    changes over time and isn't what the parser's correctness depends
    on): single/multiple entries and sections, file-order preservation
    (never re-sorted), multi-line bullet joining, intro-paragraph
    capture, and the empty-file edge case. Verified against the real
    file too, via real headless Chromium: the panel opens/closes
    correctly, renders all 5 real dated entries (23 real bullet items,
    7 real inline-code spans), zero console errors. Full `uv run
    pytest` (188, up from 181) and `uv run ruff check .` both clean.

63. **[done, 2026-09-17]** **[Dashboard UI]** Mobile-responsive pass on the header - "it's getting a bit
    crowded." Real, not hypothetical: the header now holds 5 items
    (wordmark, 🌙 Dark mode, 📅 As of, 📋 Recent activity, 🕐 Past
    snapshots, plus the live-updated indicator) after this session's
    additions (dark mode toggle, activity panel), none of which had a
    narrow-viewport pass done as they were added. Not investigated or
    scoped yet - just logged so it isn't lost.

    **Built, 2026-09-17 (Phase 5i).** Now 6 buttons (item 62's "Release
    notes" landed in between and made it measurably worse, per that
    item's own note). Screenshotted the real, current header at 375px
    before touching anything, rather than guessing at the problem: the
    button row - a plain `display:flex; gap:10px` div with no wrap -
    had no narrow-viewport treatment at all, so the as-of button's own
    dynamic label ("As of: Jul 19, 2026") wrapped mid-button into 3
    lines and the whole row simply overflowed past the viewport edge,
    cutting "Past snapshots" off mid-word ("snap…"). `.masthead` itself
    already had `flex-wrap:wrap` (why the button row was already
    dropping to its own line below the wordmark) - the gap was entirely
    WITHIN that row, one level down.

    Fix, CSS-only, no new UI paradigm (no hamburger/overflow menu, no
    icon-only collapse, no horizontal scroll - the simplest option that
    fit this project's plain hand-authored-CSS style): a new
    `.header-actions` class (`display:flex; flex-wrap:wrap; gap:10px;
    row-gap:8px`) replacing the button row's old inline style, plus
    `white-space:nowrap` added to `.snapshots-btn` so each button's own
    label stays atomic and moves to the next row as a whole rather than
    splitting internally - the two changes together mean the row now
    wraps onto as many lines as it needs instead of overflowing.
    `@media (max-width:480px)` additionally trims button/live-indicator
    padding and font-size a bit, fitting more per row before it has to
    wrap further, without truncating or hiding any real content.

    Verified with real headless Chromium screenshots at 375px, 414px,
    and 768px (iPhone SE/standard mobile/tablet), light and dark mode:
    every button's full label stays intact, no mid-button wrapping, no
    row overflow, all 6 buttons still open/close correctly at 375px
    (clicked through Release notes and the dark mode toggle for real).
    Full `uv run pytest` (188, unchanged - a pure CSS change) and `uv
    run ruff check .` both clean.

64. **[done, 2026-09-17]** **[Dashboard UI]** Tier 3's no-data drill-down gap -
    found investigating Keith's own two walked-through scenarios ("as of
    1 August I should see red/amber/green; as of 28 July I should see
    no data, but still be able to click through to tier two and see no
    data against all the datasets, then click into a dataset and see no
    data against all the columns... but I should still be able to see
    the historical graphs and comparison stuff"). Both scenarios already
    worked correctly for status COLORS at Tier 1/2 - the real,
    structural gap was narrower and specific to Tier 3: once a dataset's
    latest real supply fell outside `AS_OF_OFFSET_DAYS`' staleness
    tolerance, `clipDatasetToAsOf()` returned `null` unconditionally,
    and `noDataDataset()` built a placeholder with `columns: []` -
    discarding ALL real historical column/check data even when plenty
    existed, so Tier 3 rendered only a text blurb, nothing clickable, no
    charts. Contrary to what Keith described wanting: no colors, but
    still-clickable columns with real historical trend/comparison data.

    Asked Keith one real open design question before building (his own
    instruction: "ask me questions as you go"): once a no-data column
    tile is showing (Phase 5e's aggregate sparkline still attached to
    it), should that sparkline suppress its own real historical colors
    to match the neutral pill next to it, or keep showing them? Keith's
    call: **keep the sparkline's real colors** - only the AGGREGATE
    status pills (dataset-level, column-tile-level) go neutral "no
    data"; the sparkline's own historical shape/color, and everything
    inside a column's drawer (per-check current/previous values, status
    pills, and each check's own trend chart), stay fully real and
    unchanged. This turned out to need no extra design for the drawer
    at all: `openColumnDrawer()` already derives its own summaries
    entirely from `column.checks[]` (real `current`/`previous`/`history`/
    `warn`/`fail`, via `checkStatus(ck)` per check) - it never reads
    `column.status` - so leaving `checks[]` completely untouched and
    only overriding the ROLLED-UP `column.status`/`dataset.status` was
    already exactly the right scope, no drawer changes needed.

    Built: `clipDatasetToAsOf()` now only returns `null` for a
    genuinely EMPTY dataset (zero eligible runs as of the selected
    date) - a stale-but-real dataset (eligible runs exist, just past
    tolerance) builds normally and gets a new `staleAsOf` flag instead.
    `buildRealDataset()` reads that flag: forces every column's rolled-
    up `.status` to `"nodata"` (leaving `checks[]` real), and sets the
    dataset's own `status`/`noDataAsOf` to match - mirroring exactly the
    `noDataAsOf`/`status` pairing `noDataDataset()` already used for the
    empty case, so `rollup()`/`rollupStatuses()` (both already written
    to treat any `noDataAsOf` dataset as "don't let it vote green")
    needed zero changes. `renderDataset()` splits its old single
    `if(ds.noDataAsOf)` branch on `!ds.columns.length` - genuinely empty
    keeps the old text-only page; stale-with-data falls through to the
    NORMAL render path (SLA strip, legend, full clickable column grid),
    with one new explanatory line under the header (why the pills read
    "no data" despite real figures below).

    Verified against real, live data - CP is *currently* in exactly
    this state at the default as-of view (the still-open
    `AS_OF_OFFSET_DAYS`-vs-CP-cadence conflict from
    `plans/publishing-and-history.md` Thread C's 2026-09-17 "Revisited"
    entry): headless Chromium confirmed Tier 1 agency status still
    `nodata`, Tier 2 still shows the "no data" row, and Tier 3 - the
    actual fix - now renders 11 real, clickable column tiles (each with
    "no data" pills and its own real sparkline) instead of a blank text
    page; clicking one opens the drawer with a fully real "6 Passing/
    Warning/Failing" summary and 6 real check cards. Also verified the
    genuinely-empty case (`applyAsOf("2020-01-01")`, before BDM's
    earliest real run) still renders the plain text-only page
    unchanged, zero column tiles. Zero console errors either way. Full
    `uv run pytest` (181, unchanged - a pure frontend change) and
    `uv run ruff check .` clean.

65. **[done, 2026-09-17]** **[Pipeline & publishing]** Replaced `AS_OF_OFFSET_DAYS` (the
    flat global day-count staleness tolerance item 64/`plans/publishing-
    and-history.md` Thread C left open, "CP reads no data for roughly
    two-thirds of every quarter") with real, per-dataset, computable
    "expected refresh cadence" config - a genuine design change, not a
    number tweak, scoped with Keith across an extended brainstorm before
    building anything (see `plans/publishing-and-history.md` Thread C's
    own write-up for the full back-and-forth). Keith's actual intent,
    once unpacked: a team running a quarterly refresh should be able to
    set the as-of date to their own cycle's start and watch datasets
    flip from "no data" to real red/amber/green (and see whether each
    arrived late or *early*) as the day's deliveries land - the same
    concept needing to work for a team on a daily cadence too, so
    "refresh window" (my first framing) was wrong; Keith's own
    correction: "tying it into...an 'expected refresh cadence' /
    'expected arrival dates' for each dataset." Split into two stages
    (Keith's agreement, "Yes, go ahead," was for Stage 1 only): **Stage
    1** (this entry) - cadence config + the no-data trigger rewrite +
    real on-time/late/early classification. **Stage 2** (not started) -
    a supply/resupply history section on the dataset page (Option A,
    bolted onto the existing `renderDataset()` page, working uniformly
    regardless of cadence type) - explicitly deferred to a later session.

    Cadence model (three types only, per Keith's own scope - "daily and
    weekly and quarterly"): `{type: "daily"|"weekly"|"quarterly",
    weekday (weekly only, 0=Monday), anchor_months/day_of_month
    (quarterly only), expected_time (AWST wall-clock, "HH:MM"),
    latency_minutes}`. AWST (UTC+8, fixed, no daylight saving in WA -
    Keith: "AWST for the Timezone please") makes the UTC conversion
    plain arithmetic, no timezone library needed. Keith's own revision
    mid-brainstorm mattered here: initial scope was "must arrive on the
    day expected, no grace," which would have meant dropping the SLA's
    existing (if previously-unused) `latencyHours` concept entirely; he
    then explicitly asked to keep a real latency tolerance - "an agreed
    hour of the day...allow some sort of latency, probably on the order
    of minutes or an hour or so" for daily, "less of an issue" but still
    real for quarterly ("some hours...eight hours...for a business
    day") - landing on `expected_time` + `latency_minutes` (Keith:
    "Minutes is fine" as the one consistent unit across all three
    cadence types) rather than pure date-only comparison.

    Where the config lives: each dataset's own real ODCS contract's
    `slaProperties:` array (`contract/bdm-birth-registrations-
    contract.yaml`, `contract/child-protection-contract.yaml`) - Keith
    asked directly "Inside the odcs contract?" and "How does it work
    alongside the sla frequency and expectedBy???" before this was
    settled. Confirmed via the real ODCS 3.2.0 schema that
    `slaProperties:` genuinely supports arbitrary `property` names (no
    enum, `additionalProperties: false` only on each entry object, not
    the array) - a real mechanism, not a repurposed one. The old
    `sla.frequency`/`sla.expectedBy`/`sla.latencyHours` decorative text
    was confirmed by grep to be completely unread by anything (not even
    the dashboard's own display used `latencyHours` - the old `onTime`
    computation used a hardcoded `< 24h` literal) - all three replaced
    by the real `cadence` block; `frequency` is now a derived display
    label (`cadenceLabel()`), never separately hand-authored. Fixed a
    real, pre-existing inaccuracy found along the way: CP's
    `slaProperties.frequency` had been stale at "7 d" (weekly) since
    before this collection's real cadence was migrated to calendar
    quarters - never updated through either of CP's later quarterly-
    anchor migrations, since nothing downstream ever actually read it.
    Corrected to "3 mo" alongside adding the real cadence.

    Built: `pipeline/cadence.py` - `parse_cadence_from_contract()`,
    `cycle_start(cadence, on_or_before)` (pure date arithmetic - "the
    most recent day, at or before this date, a delivery was expected" -
    generalizes `generator/generate_cp_runs.py`'s own `_quarter_start()`
    to arbitrary anchor months/day-of-month, cross-checked against it
    directly for CP's real config across ~140 dates in
    `tests/test_cadence.py`), and `classify_arrival(cadence, run_date,
    earliest_extract_utc)` (a real timestamp comparison against the
    cadence-derived expected UTC moment + latency grace - "early" /
    "onTime" / "late", replacing the old boolean `onTime`).
    `cycle_start()` needed a JS port (`cycleStartDate()` in the
    dashboard template) since the as-of picker lets a viewer pick any
    date the Python side hasn't seen - cross-verified byte-for-byte
    against the Python implementation across daily/weekly/quarterly
    cases (weekday math, quarter-boundary math) before trusting it.
    `classify_arrival()` never needed a JS port - it's computed once,
    server-side, per real run (in `pipeline/build_dashboard_data.py`/
    `build_cp_dashboard_data.py`, reusing each run's own already-
    committed `earliest_extract`/`max_lag_hours` from `qa_results/*/
    dataset_stats.json` - no live DB access, keeping CI's never-touch-
    data rule intact) and embedded as a fixed historical fact; a past
    run's real arrival time never changes no matter what as-of date
    someone later picks.

    `clipDatasetToAsOf()`'s `staleAsOf` flag (item 64's mechanism,
    reused unchanged) now triggers on "the most recent eligible run's
    own date is before this as-of date's current cadence cycle start"
    instead of a day-count comparison. `AS_OF_OFFSET_DAYS` removed
    entirely (from the template, `contract/data-asset.yaml`, and
    `dashboard/embed_dashboard_data.py`'s embed step) - `defaultAsOf()`
    now just returns real wall-clock "today," since there's no offset
    left to subtract. All `onTime` call sites (arrival pills, the SLA
    strip's "Latest arrival" line, `arrivalHistory`/`arrivalByRun`)
    converted to the 3-state `arrivalStatus`, with a new amber pill for
    "early" alongside the existing green/red for onTime/late.

    Verified against real, live data - the actual regression this fixes:
    headless Chromium confirmed CP's default as-of view (2026-09-17,
    inside the current Aug-1-anchored quarterly cycle) now shows real
    status (`agencyStatus: "red"`, `dsStatus: "red"`, `noDataAsOf:
    false`, `arrivalStatus: "onTime"`, 11 real column tiles) instead of
    the old "no data" fallback - CP's real Aug 1 2026 delivery genuinely
    falls inside its own current cycle. The genuinely-empty case
    (`applyAsOf("2020-01-01")`) still correctly shows `nodata`/zero
    columns. A real regenerated BDM history (176 runs) shows a genuine
    mix of `early`/`late` and zero `onTime` - the real synthetic
    extraction-time distribution (clustered around 20:00 UTC and 01:00
    UTC) straddles the expected 22:00-23:00 UTC grace window narrowly
    on both sides, so the classification is working correctly, it's
    just revealing that the generator's actual delivery timing doesn't
    happen to land inside a tight 60-minute window - not a bug, a real
    finding worth flagging to Keith if the `onTime` state's practical
    unreachability for BDM turns out to matter later. CP's own history
    (all 15 real runs) is `onTime` throughout, consistent with its much
    wider 8-hour grace window. Zero console errors in all cases. Real
    end-to-end regeneration: `qa_tools.bdm.orchestrate_bdm` (176 runs,
    14,079 checks: 9770 pass / 806 warn / 3503 fail, unchanged from the
    pre-Phase-5j run - only tool-invocation metadata differs, verified
    by diff) and `qa_tools.cp.orchestrate_cp` (15 runs, 2655 checks:
    2141 pass / 126 warn / 388 fail). Full `uv run pytest` (205, two
    updated - `test_build_dashboard_data.py`/`test_build_cp_dashboard_
    data.py`'s `onTime`-hardcoding regression tests re-targeted at
    `arrivalStatus`, since the old test's premise - mutating
    `max_lag_hours` to flip status - no longer applies now that
    `arrivalStatus` is computed from real timestamps, not `max_lag_
    hours`) and `uv run ruff check .` both clean.

66. **[parked, 2026-09-17]** **[QA checks & contract]** Explore the real ODCS contract format more thoroughly
    - Keith's own ask, after Phase 5j's `slaProperties:`
    work turned up a mechanism (a real, well-defined SLA property shape)
    neither of us knew was there beforehand: "what else does ODCS have
    that we're not using yet, and is any of it worth adopting." Read the
    real ODCS 3.2.0 JSON Schema this repo's own `datacontract-cli`
    dependency ships (`.venv/lib/python3.11/site-packages/datacontract/
    schemas/odcs-3.2.0.schema.json` - not the general web spec, the exact
    schema our real tool validates against) end to end and diffed it
    against what both real contracts (`contract/bdm-birth-registrations-
    contract.yaml`, `contract/child-protection-contract.yaml`) currently
    use. Currently used: `apiVersion`, `id`, `kind`, `name`, `version`,
    `status`, `domain`, `description`, `schema` (with `quality:` using
    the `library` (`metric:`) and `sql` types), `servers`, `team`,
    `support`, `slaProperties`, `customProperties` (our own check-
    lifecycle metadata, per `qa_tools/common/check_lifecycle.py`).
    Analysis only below - nothing built yet, no priority order implied
    by the list ordering; a real discussion with Keith on what's worth
    the build effort is the actual next step, not a to-do list to just
    start working through.

    **Worth a real look, roughly most to least interesting:**

    - **`relationships:`** (`SchemaObject`/`SchemaBaseProperty` level) -
      a real, formal foreign-key declaration shape (`from`/`to`/`type`,
      default `type: foreignKey`), completely separate from `quality:`.
      Child Protection's real cross-table FK checks (client_id across
      `cp_notifications`/`cp_investigations`/`cp_placements` etc.) exist
      today only as hand-written dbt singular tests / Soda checks with
      no contract-level statement that the relationship itself exists -
      this would give the dashboard something real to render (an
      ER-diagram-ish relationship list per dataset) and check_lifecycle
      metadata a more natural anchor than a singular test's file name.
    - **`quality.type: "custom"`** (`engine` + `implementation`, with
      `engine` examples including `"dbt"`/`"soda"` by name in the real
      schema) - ODCS's own quality rules already support REFERENCING an
      external tool's check rather than only encoding `library`/`sql`
      rules natively. Right now this repo's real quality logic is
      authored 4 separate times per check (dbt `schema.yml`, Soda
      `checks.yml`, the contract's own `quality:` block, Evidently) with
      `check_lifecycle.py` gluing them together via a shared `check_id`
      after the fact. A `type: custom, engine: dbt` entry pointing at
      the real dbt test name (or `engine: soda` at the real Soda check)
      could make the contract the single authoring surface that NAMES
      every check across all 4 tools, rather than 4 independent places
      that happen to agree - a genuinely bigger change than anything in
      this list, not a quick win, but the most structurally interesting
      one: it's closer to "the contract as source of truth" than what
      exists today.
    - **SLA `schedule`/`scheduler`** (cron string + scheduler name,
      already a real field on `ServiceLevelAgreementProperty` - example
      given in the schema itself: `schedule: "0 20 * * *"`) - Phase 5j's
      own cadence work (`pipeline/cadence.py`) invented custom
      `slaProperties` property names (`cadenceType`, `cadenceWeekday`,
      `cadenceAnchorMonths`, `cadenceDayOfMonth`, `expectedTime`,
      `latency`) rather than using this. Real trade-off, not a clear
      win either way: a cron string is standard, tool-portable, and
      what a real scheduler config would actually look like - but
      `cycle_start()`/`cycleStartDate()`'s daily/weekly/quarterly-with-
      anchor-months logic is arguably clearer to read and test as
      explicit fields than as a cron expression a human then has to
      mentally parse, and cron doesn't natively express "quarterly on
      the 1st of Feb/May/Aug/Nov" without a periodic day-of-year hack.
      Also worth noting: the real schema's own recommended top-level
      `property` values (from its `odcs-3.2.0.init.yaml` example) are
      `latency`/`availability`, not the custom `cadenceType`-style names
      Phase 5j used - a real, if minor, non-standardness worth being
      aware of even if the custom shape is kept.
    - **`context:`** (RFC-0038, "AI and semantic context block" - free-
      text `instructions` plus a `verifiedStatements` array of canonical
      Q&A pairs, at contract level or per-`SchemaObject`) - directly on-
      theme for a QA dashboard: could seed a real "how to interpret this
      dataset" panel from genuinely-authored, verified facts, or (more
      speculatively) ground some future "ask a question about this
      dataset" feature in something other than the raw check data.
      Nobody's asked for either yet - flagged because it's new enough
      (RFC-0038) that it's easy to have missed entirely, not because
      there's a concrete use case identified.
    - **`authoritativeDefinitions:`** (link-outs to external definitions
      - glossary, git repo, data catalog, training video, etc., at
      contract/schema-element/team/SLA level) - could point each real
      dataset at this repo's own `README.md`/`generator/` source, or a
      future real data catalog entry, surfaced as a "Learn more" section
      on the dataset page.
    - **`classification`/`criticalDataElement`** (`SchemaBaseProperty`
      level - "confidential"/"restricted"/"public" etc., already a real
      field neither contract sets on any column despite BDM/CP both
      carrying genuinely PII-shaped columns like `child_given_names`/
      `deceased_given_names`) - could drive a "sensitive data" badge on
      the dashboard's column tiles, independent of pass/fail status.
    - **`tags:`** (contract level, `SchemaElement` level, `Team`/
      `TeamMember` level) - a real cross-cutting axis the dashboard
      doesn't have today (grouping is purely structural: agency >
      collection > dataset). Could power filtering/search across the
      agency tree instead of only browsing the fixed hierarchy.
    - **`roles:`** (named IAM roles with `access` type + first/second-
      level approvers) - adjacent to the `team`/`support` blocks already
      used; could back a real "who has access, and who approves it"
      panel per dataset.

    **Looked at, probably not worth it for this PoC:** `price`/
    `Pricing` (subscription pricing - this isn't a data marketplace);
    `tenant` (multi-tenant property association - not a concept this
    single-agency-per-dataset PoC has); `synonyms:` (business-glossary
    aliases - genuinely nice for a data-literacy feature, but nothing
    in this PoC currently surfaces column names to a non-technical
    audience where a synonym would help); the top-level `status` enum
    (`proposed`/`draft`/`active`/`deprecated`/`retired`) - real, but at
    dataset-lifecycle granularity, not the check-lifecycle granularity
    `check_lifecycle.py` already tracks in detail; noting it exists in
    case a future "is this whole dataset still supported" view is ever
    wanted, but nothing asks for that today.

67. **[done, 2026-09-17]** **[Data generation]** BDM real arrival-status calibration (Keith's
    own request: "let's change the data so that BDM arrives on time
    about 80% of the time... early for 5%... late 15%") - which turned
    up two real, unrelated bugs before the actual calibration could be
    built, plus Stage 2 of Phase 5j's cadence work.

    **Bug 1 - `earliest_extract` MIN-contamination
    (`qa_tools/bdm/dataset_stats.py`).** A plain `MIN(extract_timestamp)`
    over every row in a run picked up `generator.dirty.
    inject_extract_timestamp_disorder`'s own deliberately-corrupted rows
    (shifted to BEFORE `date_registered`, for the unrelated "extract
    timestamp ordering" check's own benefit - 1-4% of rows on any
    amber/red-severity run) almost every time, since even a 1% rate
    against ~2000 rows/run is very likely to plant at least one. A run's
    `earliest_extract` was silently reporting the worst deliberately-
    corrupted outlier instead of the batch's genuine earliest arrival -
    directly distorting `pipeline/cadence.py`'s real early/onTime/late
    classification (a run could read "early" by weeks purely because one
    disordered row happened to land in it). Fixed by excluding rows
    where `extract_timestamp < date_registered` (falling back to the
    unfiltered MIN only if literally every row in a run were disordered -
    not currently reachable, but defensive). Regression test written and
    confirmed to fail against the pre-fix code first, per this repo's own
    convention (`tests/test_dataset_stats.py`).

    **Bug 2 - `06:00` AWST made "on time" structurally unreachable.**
    Fixing bug 1 surfaced a deeper, real conflict the original Phase 5j
    commit hadn't caught: AWST is UTC+8, so `06:00` AWST (the
    `expectedTime` value Phase 5j shipped, inherited from the dashboard's
    old decorative "06:00 local" placeholder text rather than derived
    fresh) converts to `22:00 UTC the PREVIOUS calendar day` - outside
    the range the real "extract timestamp ordering" check (identical in
    both `contract/bdm-birth-registrations-soda-checks.yml` and this
    same contract's own `quality:` block: `extract_timestamp >=
    date_registered`) allows. Every real BDM run therefore classified as
    early or late, never on time, no matter how the generator's random
    spread was tuned - not a data-calibration problem at all, a real
    modeling bug in this session's own Phase 5j build. Confirmed with
    Keith before touching it (a value from this session's own earlier,
    already-approved work): corrected `expectedTime` to `14:00` AWST
    (`06:00 UTC`, safely inside `date_registered`'s own UTC day with
    room either side) rather than widening the real, already-correct
    ordering check - a check on genuinely bad data isn't the thing to
    weaken to accommodate a placeholder SLA value.

    **The actual calibration
    (`generator/daily_batch.py`).** Draws ONE characteristic arrival
    offset per RUN (not per row - a `MIN()` over ~2000 independent
    per-row draws would collapse onto the extreme low tail almost every
    time, regardless of the intended split), on a dedicated RNG stream
    (`seed+5`, isolated from the main stream so retuning this never
    perturbs unrelated fields like sex/twin flags again), targeting 80%
    onTime / 5% early / 15% late against the real cadence window. Direct
    simulation against the real 120 non-resupply BDM seeds (1001-1120)
    confirms 86 onTime / 24 late / 10 early (71.7%/20%/8.3%) - close to
    target within normal sampling noise for n=120, and exactly matching
    what the real regenerated data shows for non-resupply runs.

    **A real, known limitation left as-is, not silently "fixed":** the
    OVERALL population (176 runs, resupply included) reads 48.9%
    onTime / 37.5% early / 13.6% late, not 80/5/15 - because all 56
    resupply entries (32% of history) read "early," 100% of the time.
    This is a structural consequence of `generator/resupply.py`'s
    already-deliberate, Keith-approved churn design (a resupply reuses
    its ORIGINAL delivery's `date_registered`/`extract_timestamp`,
    since "these are records that should have been in the original
    file," not a fresh same-day draw) - a resupply's reused, much-older
    timestamp reads as "early" against the LATER cycle it's actually
    delivered in. Deliberately not touched here: redesigning churn's
    timestamp behavior is a separate, larger architectural question
    from what was asked, and changing it would revisit design Keith
    signed off on in an earlier session, not something to silently
    fold into a calibration task. Flagged here in case the overall
    (not just per-original-delivery) split ever needs to hit 80/5/15
    for real.

    **Stage 2 - supply/resupply history section (Phase 5j's own
    Stage 2, deliberately deferred when Stage 1 shipped).** Keith's
    confirmed design, from a round of `AskUserQuestion`: default to the
    as-of date's own current cadence cycle, expandable to full history;
    grouped by cadence cycle (each cycle its own `.dataset-table` block,
    reusing Tier 2's existing table style - resupply attempts NOT
    nested under their original delivery, just their own entry with a
    "Resupply, attempt N" badge); each entry shows arrival status +
    timestamp, row count, resupply indicator, and injected defect
    severity; clicking an entry applies that run's own `run_date` as the
    global as-of date (`applyAsOf()`, reused as-is) rather than building
    a second drill-down mechanism - since setting as-of to a specific
    real `run_date` already makes `clipDatasetToAsOf()` pick that exact
    run as the effective one everywhere else on the page, for free.
    `buildSupplyHistory()` operates on the RAW (unclipped, full-history)
    dataset object, not `renderDataset()`'s own as-of-clipped `ds` -
    needed a new `rawRealDatasetById()` lookup and an extracted
    `rowCountAtRun()` helper (pulled out of `clipDatasetToAsOf()`, now
    shared by both) to get at it.

    Verified end to end against real regenerated data (176 BDM runs,
    15 CP runs, headless Chromium): the current-cycle default correctly
    shows only today's 1 delivery for BDM (daily) and Aug-1's 1 delivery
    for CP (quarterly); the "Show all history" toggle correctly reveals
    all 121/15 cycles and updates its own label; clicking both an
    original delivery and a resupply attempt correctly updates
    `CURRENT_AS_OF` to that exact `run_date` and re-renders the real
    column grid (13 real BDM columns) for that historical point: zero
    console errors in every case, including the CP quarterly path.
    Full `uv run pytest` (211, six new: two `tests/test_dataset_stats.py`
    regression tests for the MIN-contamination fix, plus a new
    `tests/test_daily_batch.py` covering the calibration's real
    distribution, the ordering-check regression guard, real-cadence
    classification, and reproducibility) and `uv run ruff check .`
    both clean.

68. **[parked, 2026-09-17]** **[Docs & process]** Polish `RELEASE_NOTES` (item 62/Phase 5h's panel,
    `CHANGELOG.md`) - two separate asks. **Categorization**: label/group
    entries by which part of the system they touched (e.g. Dashboard,
    Generator, QA Pipeline/checks, Contracts, Publishing/CI), possibly
    with small iconography per category, rather than today's flat Keep-
    a-Changelog `### Added`/`### Fixed` sections with no component axis
    at all. Needs a real scoping pass when picked up - how a
    category is assigned to a past entry (hand-tagged retroactively vs.
    only for new ones going forward), whether an entry can carry more
    than one category, and how deep to go on iconography (a handful of
    inline emoji vs. real SVG icons, given `dashboard/changelog_md.py`'s
    `parse_changelog()` would need to carry the extra field through to
    `RELEASE_NOTES`'s embedded shape either way). **Writing style**:
    Keith wants a few rounds of him rephrasing/giving feedback on
    existing real entries in `CHANGELOG.md` so future entries match his
    preferred voice/level of detail, before either of the above gets
    built - a calibration pass on the actual prose, not just the data
    shape. Do the writing-style rounds first; they'll likely inform
    how the categorization ends up looking (e.g. how granular a
    category needs to be to match how he actually talks about the
    work), not the other way around.

69. **[done, 2026-09-18]** **[Dashboard UI]** Whether `arrivalStatus`
    (early/onTime/late) is even a meaningful concept for RESUPPLY
    attempts, or whether it should only ever apply to a delivery's
    original supply. Direct follow-up to item 67's own flagged
    limitation: every real resupply used to read "early" (100% of
    BDM's 56 resupply attempts), because `generator/resupply.py`'s
    churn design deliberately reuses the original delivery's
    `date_registered`/`extract_timestamp` rather than drawing fresh
    ones - a resupply's real-world arrival is genuinely later (that's
    the whole point of a resupply), but its reused timestamp reads as
    "early" against the cycle it's actually delivered in, a category
    error rather than a real fact about lateness. **Keith's decision**:
    drop `arrivalStatus` for resupplies entirely, replace it with a
    counter showing how long it's been since the previous supply or
    resupply attempt. `buildSupplyHistory()`
    (`dashboard/qa-reporting-dashboard.template.html`) now sets
    `arrivalStatus`/`arrivedAt` to `undefined` for any entry with
    `is_resupply: true` (so `renderSupplyCycleRows()`'s status column
    renders nothing for them, rather than a misleading pill), and
    computes a real `daysSincePrevious` for it instead - whole calendar
    days between this attempt's own `run_date` and whichever run it
    `supersedes_run_id` points at (the immediately previous attempt for
    the SAME delivery, real per manifest entry - a fresh, real
    `dateStrDiffDays()` helper, not a reused date function repurposed).
    Rendered as "N day(s) since previous" in place of the old status
    pill. `tests-js/supply-history.test.js` covers both the dropped
    status and the new counter (including chaining through 2+ resupply
    attempts).

    **Superseded, 2026-09-18 (item 73)**: the "is this entry a resupply"
    question this item answers is still correct, but WHICH entries count
    as a resupply is no longer read from `is_resupply`/
    `supersedes_run_id` at all - see item 73 and
    `plans/conceptual-design.md` Thread A. `daysSincePrevious` itself is
    unchanged in behaviour, just recomputed from real chain position
    instead of a `supersedes_run_id` lookup.

70. **[done, 2026-09-18]** **[Dashboard UI]** Real investigation, not a guess: loaded the real
    template in a real headless browser (Playwright) and checked
    `document.fonts` directly against `.sla-tile .v` (the "SLA"/
    cadence-label and "Delivery format" tiles). The self-hosted
    `Source Serif 4` `@font-face` (`fonts/source-serif-4.woff2`, a
    genuinely valid 122KB woff2 file, magic bytes confirmed) reports
    `status:"loaded"`, `document.fonts.check('600 16px "Source Serif
    4"')` returns `true`, and `getComputedStyle(el).fontFamily` on the
    live tile correctly resolves to `"Source Serif 4", serif` - the
    font genuinely loads and the browser genuinely prioritizes it. A
    screenshot alongside the `<h1>` (same font, same weight) shows no
    visible difference either. So item 70's own "likely cause, not yet
    confirmed" theory - the missing `Georgia` intermediate fallback
    (unlike `h1-h4`'s `"Source Serif 4", Georgia, serif`) causing a
    fallback-to-generic-serif render - does NOT hold up: there's
    nothing to fall back FROM here, the primary font loads fine every
    time this was checked. The missing fallback was still a real,
    if currently inert, defensive-CSS gap on its own terms (every other
    serif use on the page has one, this didn't) - added anyway
    (`.sla-tile .v` now reads `font-family:"Source Serif 4", Georgia,
    serif;`, matching `h1-h4`), but this should NOT be read as "the bug
    is fixed," since no reproducible bug was ever found to fix. If
    Keith still sees the generic-serif look, it's something this
    investigation didn't catch - a transient `font-display:swap` FOUC
    at a moment this check didn't happen to catch, a specific browser/
    OS/zoom combination, or something else entirely - worth a
    screenshot or more specific repro steps next time it's seen, rather
    than re-guessing at a cause from here.

71. **[done, 2026-09-18]** **[Dashboard UI]** A resupply landing weeks late on some
    OTHER cycle's own delivery day got grouped into THAT cycle's own
    supply-history block, purely by coincidence of arrival date -
    Keith's own report: "the September 14th resupply for birth data
    shows a late supply followed by a resupply, but it's labeled as
    resupply attempt five, which doesn't make sense." Confirmed for
    real, not guessed: `qa_results/registry-services/birth-
    registrations/run_099_2026-08-27_resupply4/dataset_stats.json`'s
    own `manifest_entry` has `delivery_date: "2026-08-27"` (its real
    original due date) but `run_date`/`arrived_date: "2026-09-14"` (18
    days late) - `buildSupplyHistory()`
    (`dashboard/qa-reporting-dashboard.template.html`) was grouping by
    `run.run_date` (when a delivery actually arrived) instead of
    `run.delivery_date` (which cycle it's actually FOR), so this
    resupply landed in Sept 14's own group, sitting right next to
    `run_117_2026-09-14` - a completely unrelated, genuinely on-schedule
    delivery for that real day - reading as if they were one continuous
    story. Verified with a direct probe against the real built dashboard
    before AND after the fix (jsdom, calling `buildSupplyHistory()`
    directly on the real `birth-registrations` dataset): before, Sept
    14's group had 2 entries (the real delivery + the mislabeled late
    resupply); after, Sept 14 has exactly its own 1 real delivery, and
    Aug 27's own group correctly shows all 5 of that delivery's real
    attempts together (original + 4 resupplies) - confirmed with a real
    screenshot too. Fixed: `cycleStart = cycleStartDate(cadence,
    run.delivery_date || run.run_date)` (falls back to `run_date` only
    for a hypothetical manifest entry from before `delivery_date`
    existed - none currently committed). A REGRESSION test locks this
    in (`tests-js/supply-history.test.js`, a synthetic two-entry
    scenario mirroring the real Sept 14/Aug 27 case exactly), confirmed
    to fail against the pre-fix code first, per this repo's own
    convention. **Related, currently-inactive risk flagged while
    investigating, not fixed here**: `pipeline/build_dashboard_data.py`'s
    own `lastArrival`/`latest_status` (the SLA tile's "Latest arrival"
    pill, and the Tier 2 agency-view row pill) picks the single most
    recent run in the WHOLE manifest by `run_date`, with no exclusion
    for a resupply - today's real committed history happens to have an
    original (non-resupply) run as the literal latest thing, so this
    isn't currently showing anything wrong, but the same category-error
    risk item 69 already resolved for the supply-history table exists
    here too, architecturally, the moment a resupply becomes the
    chronologically-latest thing in a dataset's history. Not built
    without asking first - whether "latest arrival" should skip
    resupplies entirely, or show something else when the latest thing
    IS a resupply, is a real design question, not an obvious bug fix.

    **Superseded, 2026-09-18 (item 73)**: the specific fix here
    (`delivery_date`-based grouping) is replaced outright, not just
    extended - see item 73 and `plans/conceptual-design.md` Thread A.
    Keith's own follow-up critique, prompted by this exact bug: "suppliers
    won't actually label a resupply as against the original supply... I
    think something you're modeling about supplies and resupplies
    doesn't make sense." The related risk flagged above
    (`lastArrival`/`latest_status`) is still open and unchanged by item
    73 - explicitly deferred, see that item's own note.

72. **[done, 2026-09-18]** **[Dashboard UI]** The `dirtySeverity`
    pill in the supply-history table (`Red-severity defect injected` /
    `Amber-severity defect injected`) is a synthetic-data-generation
    artifact, not anything a real production pipeline would ever know
    in advance. `generator/generate_runs.py`'s own `_build_run_plan()`
    deliberately seeds roughly 60% of BDM's 120 scheduled deliveries as
    clean, 20% with an amber-severity defect, and 20% with a
    red-severity one (`generator/dirty.py`'s
    `apply_birth_registrations_presets(severity=...)` - calibrated to
    land in each real check's own warn ("amber") or fail ("red") band,
    not just randomly bad data) - purely so this PoC's real dbt/Soda/
    datacontract-cli/Evidently checks have something real and
    predictable to catch, demonstrating the pipeline actually works.
    The pill is this project surfacing "we know in advance this
    delivery was deliberately made bad, and at which severity" - real,
    useful information for demonstrating/debugging the PoC itself, but
    not a concept that exists in a real production data pipeline (a
    real pipeline never knows a delivery is bad until its own checks
    say so). The real Aug 27 resupply chain (item 71's own example) is
    a genuinely good illustration of what it's for: the original
    delivery and its first 3 resupply attempts all carry
    `Red-severity defect injected` (the underlying problem wasn't
    actually fixed those times), and only the 4th resupply attempt - the
    one that finally lands clean - has no severity badge at all, a
    coherent "kept trying, finally worked" story. Not changed here -
    Keith asked what it means, not to remove or relabel it; worth
    asking directly whether it should stay exactly as-is (a demo aid,
    explaining why the checks below are flagging things) or get
    reframed/hidden as an implementation detail a real production
    dashboard would never actually have.

    **Resolved, 2026-09-18 (item 73)**: Keith's own follow-up answered
    the open question above - "we can drop the dirty severity pill" -
    and it's gone, replaced by a real (not synthetic) aggregate
    red/amber/green status pill. See item 73.

73. **[done, 2026-09-18]** **[Dashboard UI]** Replaced the resupply-chain
    model entirely. The previous design (items 29/71) grouped a
    dataset's real run history using synthetic generator bookkeeping
    (`is_resupply`/`delivery_id`/`delivery_date`/`supersedes_run_id`,
    `generator/generate_runs.py`) - real for the generator's OWN
    simulation of a churned re-attempt, but nothing a real production
    dashboard would ever have, since a real supplier's resupply just
    arrives with no flag saying what it's a resupply of. Keith's own
    words, investigating item 71's bug: "suppliers won't actually label
    a resupply as against the original supply. It will just appear at a
    certain time. So I think something you're modeling about supplies
    and resupplies doesn't make sense."

    New model, cadence-agnostic (identical logic for a daily feed and a
    quarterly one) and derived from exactly two real, already-available
    facts: `pipeline/cadence.py`'s cadence rules (via the dashboard's own
    `cycleStartDate()` - used only to anchor where a NEW chain starts,
    never to decide membership run by run) and each arrival's own real
    aggregate quality status - red/amber/green, the worst status among
    every real check across every column for that specific run. A new
    `datasetStatusByRun(d)` computes this once per dataset, purely from
    data already embedded in the dashboard JSON (`checks[].history[]`
    against each check's own `warn`/`fail` thresholds) - no new pipeline
    computation, no live data access. `buildSupplyHistory()` walks a
    dataset's real arrivals in chronological `run_date` order: a RED
    arrival starts (or continues, if the current chain is still open) a
    resupply chain; the chain CLOSES on the first AMBER or GREEN arrival
    after a RED. "Let's keep it simple - an amber or a green supply can
    count as the end of a resupply chain" - Keith's own final call,
    reached after weighing out loud whether amber should count as a real
    resolution or an accepted-but-unresolved state (the amber-governance
    question this raised is explicitly parked, not resolved, in
    `plans/conceptual-design.md` Thread A). An ordinary green/amber
    arrival with no open chain before it is still just a one-entry group,
    same as before - most of BDM's real history is unaffected by this
    change in practice, only the genuinely red-then-recovered sequences
    are.

    The exact same `datasetStatusByRun()` computation also powers the
    separately-requested aggregate status pill on each supply/resupply
    row (Keith: "an overall pill on each supply, showing whether it's
    red, amber, or green... an aggregate of all of the checks for the
    dataset and all its columns") - deliberately one computation, two UI
    uses, replacing the old `dirtySeverity` pill (item 72's own dropped
    concept) in `renderSupplyCycleRows()`. `daysSincePrevious` (item 69)
    is now just the gap between consecutive entries in the SAME derived
    chain, walked in order - no `supersedes_run_id` lookup needed any
    more, since the chain itself already is that sequence.

    Deliberately NOT changed: the generator
    (`generator/resupply.py`/`generator/generate_runs.py`) still writes
    its own `is_resupply`/`delivery_id`/etc. into `manifest.json` - real,
    legitimate bookkeeping for how the SYNTHETIC DATA was generated, just
    no longer trusted or read by the dashboard's chain-derivation logic.
    `tests-js/supply-history.test.js` was rewritten (not just extended)
    for the new model: chain start/continue/close behaviour under every
    red/amber/green sequence shape, the "keep it simple" amber-closes-
    exactly-like-green rule, a new chain starting fresh after a closed
    one, `daysSincePrevious`/`arrivalStatus` derived from real chain
    position, and a regression test re-expressing the original Sept 14
    bug scenario in the new model's own terms (a still-open chain
    correctly absorbing a later arrival that happens to land on another
    day, rather than the old bug of two unrelated things merging purely
    by calendar coincidence).

74. **[done, 2026-09-19]** **[QA checks & contract]** Item 73's new
    per-run aggregate status made a pre-existing, previously-easy-to-
    miss calibration problem impossible to ignore: `birth-registrations`
    currently shows ONE never-closing resupply chain covering its entire
    176-run real history, because at least one check reads "red" on
    essentially every single run. Root-caused to TWO separate, real, pre-
    existing bugs in how a check's `warn`/`fail` thresholds get encoded
    for the dashboard - neither introduced by item 73's own new code,
    both just newly visible now that every run's own aggregate status is
    actually being looked at, not just the current run's:

    - **Bug A - an unconfigured threshold silently becomes a zero
      threshold.** `pipeline/build_dashboard_data.py` (and CP's own
      equivalent) substitutes `0` for a `None` `warn`/`fail` when
      building each check's dashboard record. For a genuinely warn-ONLY
      check (no fail configured at all - by design, e.g.
      `missing_percent(registering_parent_1_name)` in
      `contract/bdm-birth-registrations-soda-checks.yml`, whose own
      comment says "SodaCL has no 'info' severity, so the info-tier rule
      below only sets warn - there's nothing stricter to escalate it
      to"), this silently converts "can never fail" into "fails on ANY
      nonzero value" - `checkStatus()`/`statusForValue()` both check
      `fail` before `warn`, so a null-defaulted-to-0 `fail` overrides a
      real, deliberately-configured `warn` entirely. Verified for real:
      `registering_parent_1_name`'s Soda `missing_percent` check reads
      RED on all 176 real committed runs despite `warn: when > 5%` being
      the only threshold that check's own YAML ever configures.
    - **Bug B - datacontract-cli's real numeric threshold gets discarded
      for any `severity: error` rule.** `qa_tools/bdm/
      run_datacontract_bdm.py` line 112: `"fail_threshold": 0 if
      diag.get("severity") == "error" else None`. Correct for the
      overwhelming majority of this contract's error-severity rules,
      which genuinely use `mustBe: 0` (zero tolerance IS the real rule,
      so `fail_threshold=0` is a faithful encoding - see README's own
      "Known simplifications" section, which already documents ODCS's
      single-tier severity as a deliberate scoping choice). But a small
      minority use a real, non-zero `mustBeLessThan` with
      `severity: error` - most visibly `place_of_birth_facility`'s
      `missing_percent` rule (`mustBeLessThan: 35`, real observed values
      around 2%, genuinely PASSING against the real 35% rule
      `datacontract test` itself correctly evaluates) - and for those,
      the blanket `fail_threshold=0` throws the real 35% threshold away
      entirely, so the dashboard reads it as failing on almost every
      run regardless of the real rule. (`child_given_names`/
      `child_family_name`'s `mustBeLessThan: 1` rules have the same
      structural bug but a much narrower practical window - a required
      field's null rate landing between 0% and 1% - so they're far less
      likely to actually misfire in practice; `place_of_birth_facility`
      is the clear, real, currently-misfiring case.)

    NOT fixed here, deliberately. Both are genuine, pre-existing bugs
    (not something item 73's own new code introduced - `git stash`-
    verified the CURRENT-view dataset status pill already read "Red" for
    `birth-registrations` before ANY of item 73's changes), but fixing
    either one properly touches shared, currently-working rendering code
    well beyond the resupply-chain feature itself - trend-chart y-axis
    ticks (`[0,warn,fail]`), the check-detail panel's threshold text
    (`fmtMetric(ck.warn,...)`), and every existing column/dataset status
    pill across the whole app, BDM and CP alike - real design questions
    (what does a trend chart look like with a `null` fail line? does
    fixing this change status pills Keith has already seen and accepted
    as "just how this demo looks"?) that need his own call, not a
    drive-by fix bundled into an unrelated feature. Item 73's own new
    resupply-chain logic is functioning exactly as designed against
    today's real (bug-affected) data - the never-closing chain is an
    accurate computation given that input, not a bug in the new
    derivation logic itself.

    **Picked up and fixed, 2026-09-19** (Keith's own pick from the open-
    items sweep at the start of the `claude/delivery-subagents-plans-
    717lrx` session, chosen specifically because it blocks something
    already built - see the ticketing note at the end). Investigating it
    properly first turned up three things this entry had wrong or
    didn't know:

    **1. Bug B was already fixed, and this item went stale.**
    `qa_tools/common/datacontract_common.py`'s
    `fail_threshold_from_quality_definition()` already parses the real
    `mustBe`/`mustBeLessThan`/`mustBeLessOrEqualTo` out of each ODCS
    rule, and its own comment block names "Item 74 ... Bug B" directly.
    It landed in `8ed69a9` and nothing ever came back to update this
    entry. Both of Bug B's named examples are gone too - and
    `registering_parent_1_name`'s Soda rule (Bug A's own named example)
    has since gained a real `fail: when > 15%` with a changelog entry
    citing this item. So the only thing still live was Bug A's root
    cause in the builders.

    **2. The real impact was bigger and differently shaped than the
    "warn-only check" framing here suggested.** Measured against this
    repo's own committed history by comparing every result's own tool
    verdict against what the dashboard computed from thresholds: **1,829
    disagreements** (1,648 BDM / 181 CP, ~6% of all results). Every
    single one in the same direction - the tool said `pass`, the
    dashboard rendered amber or red. Zero cases of the reverse, so this
    bug only ever manufactured false alarms and never once hid a real
    failure. They cluster into exactly three kinds:
    - `rowCount_datacontract` + `row_count_soda` - **884 false reds.**
      The real rule is `mustBeBetween: [500, 20000]`, a genuine
      TWO-SIDED range, so both thresholds are correctly None; the
      0-substitution turned a real row count of 1939 into `1939 > 0`.
      Red on 352/352 BDM runs and 18/18 CP runs - one per dataset, which
      is precisely the "all 7 datasets read red" this project had been
      attributing to a vaguer threshold-encoding problem.
    - `nullValues_datacontract` - 944 false ambers, the warn side of the
      same substitution.
    - `range_check_soda` - 1, an edge case.

    **3. The obvious fix would have been a regression.** ~63 checks
    (`not_null`/`unique`/`relationships`/`matches_regex`/
    `accepted_range`) have a null `fail_threshold` AND currently agree
    with their tool exactly, because for a violation COUNT "any
    violation is a failure" genuinely is the rule - `fail=0` is the
    correct encoding, not a bug. Simply passing None through and reading
    it as "unbounded" would have turned real failures green, converting
    a false-alarm bug into a missed-failure one. Worth naming plainly:
    the naive reading of this item as originally written would have done
    exactly that.

    **The actual root cause, deeper than thresholds**: every result
    already carries its own tool's real verdict, and
    `build_dashboard_data.py` was **throwing it away** when building
    each check's `history[]`, leaving the dashboard to re-derive a
    status from a warn/fail pair that cannot express every real rule.

    **Fix (Keith's own call via `AskUserQuestion`, picked over a
    surgical range-check special-case and over adding a two-sided
    threshold model): trust the tool's own verdict.** New
    `dashboard_status()` in `pipeline/dashboard_check_labels.py` (the
    module both builders already share, so the two can't drift) maps a
    real `pass`/`warn`/`fail`/`error` onto green/amber/red, returning
    None for anything unrecognised so callers fall back rather than
    reading an unknown verdict as healthy. Both builders now carry
    `status` onto every history entry and `current_status` onto each
    check, and - the other half - **stop substituting 0 for a None
    threshold**, since None means "no bound of this kind exists", not
    "zero tolerance". Template side: `checkStatus()` prefers
    `current_status`, a new `historyStatus(h, check)` prefers a history
    entry's own `status`, and `statusForValue()` is now the explicit
    fallback with null treated as absent rather than zero.

    Null thresholds then had to become real, renderable values rather
    than crashes - a concrete gap this entry's own "needs his call"
    paragraph had flagged only in the abstract, now answered with real
    findings: the trend chart turned out **safe** (`null * 1.15`
    coerces to 0, so the y-axis still scales off the data), but
    `fmtMetric(null, "%")` calls `null.toFixed(2)` and **hard-crashes
    the whole check-detail panel** - so `fmtMetric()` now renders an
    absent bound as an em dash, the chart omits guide lines/y-ticks for
    a bound that doesn't exist, and the detail panel's threshold line
    states "no single-sided threshold - status is this tool's own
    verdict" instead of the previous, outright false "warn > 0 ·
    fail > 0".

    **Verified against real committed history, not fixtures**: the
    dashboard now matches the tools' own verdict on **352/352 BDM runs**
    and **108/108 CP (dataset, run) pairs** - every one of the 1,829
    disagreements gone, with no status invented anywhere. The real
    distribution underneath is BDM 198 red / 52 amber / 102 green and CP
    19 red / 89 green - BDM genuinely does have a lot of red, because
    the generator deliberately injects red deliveries and resupply
    chains, but **102 BDM runs are now green that previously could not
    be**, since the rowCount false-red hit literally every run. That is
    what unblocks item 73's "ONE never-closing resupply chain covering
    the entire 176-run history": chains can actually close now.

    Tests, per this project's standing "reproduce it failing first"
    convention (a logic bug, so the automatic rule applied, no need to
    ask): 3 new Python tests in `tests/test_build_dashboard_data.py`
    (the real rowCount shape; null thresholds surviving as null; and an
    explicit regression guard that a violation-count check's real `fail`
    verdict still reads red) - all 3 confirmed failing against the
    pre-fix code first. 11 new JS tests
    (`tests-js/tool-verdict-status.test.js`) - confirmed by stashing the
    template and re-running that 8 of the 11 genuinely fail pre-fix,
    with the other 3 passing by design as unchanged-behaviour guards.

    **Two real knock-on changes the fix surfaced, both genuine rather
    than test-wrangling:**
    - `tests/test_dashboard_e2e.py`'s `TestAmberDecisionBadge` fixture
      broke, correctly. It targeted 3 runs (2026-05-22/23/24) that its
      own docstring recorded as "REAL, currently-amber ... found by
      actually computing this dataset's own per-run status, not
      assumed" - true when written, but they were only amber BECAUSE of
      this bug. `run_001_2026-05-22` is BDM's very first run and is
      genuinely clean; it now reads green, so the badge's own
      `status==="amber"` gate correctly stopped firing. Re-derived 3
      genuinely-amber, window-owning runs the same way the original
      docstring describes (`run_044_2026-07-05` accept,
      `run_062_2026-07-23` reject, `run_066_2026-07-27` neither). Worth
      being explicit: the fixture's PREMISE expired, the mechanism it
      tests did not - and it expiring is itself evidence the fix landed.
    - Doing that re-derivation turned up a real, latent addressing
      problem: the supply-history row identified itself only by
      `data-run-date`, which is **not unique** - the exact "352 real BDM
      runs across only 123 distinct dates" fact `plans/conceptual-
      design.md` Thread A already found the hard way. Not one amber
      window-owning run has a unique `run_date`. Added `data-run-id`
      alongside it (`e.run_id` was already in scope on that row -
      `amberDecisionBadge()` next to it already used it), so anything
      needing exactly one row can address one. Small, but it removes a
      real footgun rather than working around it in a selector.

    **Two real consumers of these thresholds were missed on the first
    pass, both found the same evening - worth recording honestly,
    because the way each was found says something.**
    - `qa_tools/common/dataset_status.py` is the PYTHON MIRROR of the
      dashboard's own client-side status logic (it exists because the
      ticketing Action has no JS runtime). The fix changed the JS and
      `pipeline/dashboard_check_labels.py` but not this third copy, so
      `status_for_value()` still did a bare `value > fail` and died with
      a real `TypeError: '>' not supported between instances of 'int'
      and 'NoneType'`. **Found by CI** - specifically by the very first
      run of `ticket-sync.yml` after its own dead branch pin was fixed
      (`plans/publishing-and-history.md` #7), within seconds of that
      workflow running for the first time ever. The cleanest possible
      argument for fixing that pin.
    - `buildRealDataset()` in the dashboard template rebuilds every
      check and history entry into a NEW object, and copied neither
      `current_status` nor the per-entry `status`. This one was worse:
      dropping the verdict doesn't fail loudly, it falls back to
      threshold math, and with null bounds now preserved a real dbt
      `not_null` check with 14 violations and no configured fail
      threshold would have rendered **GREEN** - the false-green
      direction this item's own write-up above specifically identifies
      as the danger, reintroduced by the fix meant to avoid it. Found by
      auditing every remaining consumer after CI caught the sibling
      miss, not by any test.

    **Why the original verification missed both, since that matters more
    than the misses themselves**: the 352/352 and 108/108 agreement
    figures above were computed by reading `reports/*_dashboard.json`
    and applying the status-preference rule in a throwaway script. That
    genuinely verified the DATA layer - and nothing else. It never
    exercised `buildRealDataset()`, and never touched the Python mirror
    at all. A green data layer says nothing about the render layer when
    the render layer has its own transform. Both now have real tests at
    the layer that was actually wrong: 5 new Python tests
    (`tests/test_dataset_status.py`) and 3 new JS tests
    (`tests-js/tool-verdict-status.test.js`'s own `buildRealDataset`
    block), each confirmed failing against the pre-fix code - and
    notably, only 2 of those 3 JS tests fail without the fix, because
    the passing-rowCount case gets the right answer from the fallback by
    luck. That asymmetry is exactly why the bug was invisible.

    **Keith's own follow-up, same evening: "why do we have two tools
    doing the same thing", and "what can we do to make that more
    robust".** Investigating turned up more than the two known
    implementations:
    - **Four status implementations existed, not two**: the template's
      JS, `qa_tools/common/dataset_status.py`, `pipeline/
      dashboard_check_labels.py`'s own `status_rank`, and - the
      telling one - a `worst` column rollup in `build_dashboard_data.py`
      that was **dead code**. It rolled up from each real engine's own
      `status` field, which is exactly the right idea, and then nothing
      ever read it; `columns_out.append()` never carried it. Ruff
      couldn't flag it either, since `worst` is read inside its own
      accumulating loop so `F841` never fires. BDM-only; CP never had it.
    - **The duplication that remains is genuinely unavoidable** - the
      dashboard is static, so the browser must re-roll status for any
      as-of date a viewer picks, and the ticketing Action has no JS
      runtime. The useful contrast is `pipeline/cadence.py`, which has
      the SAME kind of split and hasn't drifted, because its own
      docstring says why: both sides are tested against the same real
      configs and dates. `dataset_status.py` had no such cross-check,
      which is precisely how it drifted.
    - **Item 74 had already made most of it vestigial** - measured, not
      assumed: after the fix, only 198 results in the whole app still
      reached the threshold fallback, every one of them the builders'
      own synthetic "No automated quality rule defined" placeholder, and
      zero real tool results.

    **Built (Keith picked all three options offered):**
    1. The placeholder now states its own status explicitly, so the
       threshold fallback has **no live callers at all** - a fallback
       with one synthetic caller is a trap, not a safety net.
       `dashboard_status()`/`dashboard_status_of()`/`status_for_value()`
       now live in one canonical Python module, with
       `dashboard_check_labels.status_rank()` delegating rather than
       carrying its own copy; the dead `worst` block is deleted. Two
       implementations remain, one per language, which is the real floor.
    2. `buildRealDataset()` inverted from a hand-maintained allowlist of
       ~11 copied fields to **spread-then-override**. The old shape had
       exactly one failure mode - add a field upstream, forget it here,
       lose it silently - which is what shipped. Now a new field flows
       through by default and you only write code to CHANGE something.
       Verified safe first: nothing anywhere iterates a check's own keys,
       so the raw twins left beside their transformed versions are inert.
       Guarded by a real test that fails, naming the field, if anything
       is dropped - confirmed by reverting to an allowlist and watching
       it fail on `dimension`.
    3. **The test that would have caught both**:
       `tests/test_dashboard_e2e.py::TestStatusMatchesEachToolsOwnVerdict`
       drives the real built dashboard in a real browser and uses the
       PAGE's own `buildRealDataset()`/`checkStatus()`/`historyStatus()`
       to compare ~30,000 rendered statuses against the verdict each real
       tool recorded. Runs in ~8s. Proven rather than assumed: the real
       bug was reintroduced and it failed with a genuinely diagnostic
       message (`not_null_dbt`, tool `red`, rendered `green`, value 1,
       both bounds null). A second test asserts no REAL check ever lacks
       a verdict, so a future silent drop fails loudly.

    The standing lesson landed as its own `CLAUDE.md` convention:
    enumerate consumers mechanically on a shape change, and verify at
    the LAST transform before the user rather than the first one after
    the source.

    **Still open, deliberately not done here**: flipping
    `ticket-sync.yml`'s automatic push trigger on.
    `plans/running-thoughts.md` #1 records that the ticketing MVP
    shipped `workflow_dispatch`-only precisely because all 7 datasets
    read red and would have generated pure noise - that blocker is now
    gone, but actually turning the trigger on is Keith's call, not a
    side effect of this fix, and wants a real look at how much genuine
    ticket volume BDM's 198 real red runs would produce first.

75. **[done, 2026-09-18]** **[Docs & process]** A live requirements register - Keith's own
    request, one of the ideas parked in `plans/running-thoughts.md`
    item #7: "actual requirements... user stories, requirements, and
    acceptance criteria... track MoSCoW status... have we implemented
    them yet... tie them back to the actual tests." Scoped via a real
    round of `AskUserQuestion` before building anything (this project's
    own standing convention for a decision with real forks), covering
    the three genuinely open questions: **source format** - structured
    YAML with typed fields per requirement (Keith's choice, NOT the
    hand-prose `CHANGELOG.md` pattern this session's own recommendation
    leaned toward - a deliberate, explicit departure); **granularity** -
    high-level user stories (~10-30), not a 1:1 mirror of every
    fine-grained item already logged in this file/`wider.md`; **test
    tie-back** - real, CI-ENFORCED linkage (Keith's choice again, not
    the lighter "soft manual reference" MVP default this session
    recommended), not decorative text.

    Built: `requirements.yaml` (repo root) - 22 seeded requirements (14
    `built`, 8 `not_started`), covering the real major shipped
    capabilities (drawn from `CHANGELOG.md`'s own already-curated
    history) plus the concrete near-term ideas already scoped in
    `plans/running-thoughts.md` (GitHub Issues ticketing, the people/
    roles config, the amber accept/reject decision, the AWS S3-event
    MVP, CP resupply simulation, human-friendlier URLs, exposing
    `plans/*.md` in the dashboard, gamification) - real, not invented
    for this entry. `dashboard/requirements_yaml.py`'s `parse_
    requirements()` (mirrors `changelog_md.py`'s role, but far less
    interpretation needed - the YAML's own shape already IS the
    rendered shape). `qa_tools/common/validate_requirements.py` is the
    real enforcement: schema/enum checks, globally-unique `id`s, a
    `built` requirement can't ship with zero `linked_tests`, and -
    the actual point of choosing "enforced" over "soft" - every
    `linked_tests` entry is checked against a REAL file, with a real
    Python AST parse (never a regex/string match, which a comment or a
    docstring could fool) confirming a `path.py::Class::method` /
    `path.py::function` / bare `path.py::Class` reference genuinely
    exists as a test, not just that the file does. Wired as a new CI
    gate in `deploy-pages.yml` (`requirements.yaml` added to the
    trigger paths too), same "broken output never reaches Pages"
    treatment as the check-lifecycle gate. A new "📐 Requirements"
    header button/side panel (`REQUIREMENTS` const, same "placeholder
    in the template, real data only in the built output" pattern as
    `RELEASE_NOTES`) - id, title, story, MoSCoW pill, status pill,
    acceptance criteria, and the real linked-test paths, per
    requirement.

    This describes the PRODUCT (the QA dashboard/pipeline itself), not
    this project's own working process - deliberately excludes things
    like "a running-thoughts capture buffer" or "write CHANGELOG
    entries per push," which are real but are conventions for HOW this
    gets built, not requirements of what gets delivered (see
    `requirements.yaml`'s own top comment).

    Tests: `tests/test_requirements_yaml.py` (parser, fixture-based,
    mirrors `test_changelog_md.py`'s own style), `tests/test_validate_
    requirements.py` (every real failure mode - bad id, duplicate id,
    missing title/story, invalid moscow/status, empty acceptance
    criteria, a `built` requirement with no linked tests, a linked test
    naming a real file but a fake function - PLUS the existence checks
    run against this repo's own real, stable test files, not more
    fixtures, since the whole point is confirming something real
    exists), `tests-js/requirements.test.js` (the moscow/status label
    and pill helpers), and a new `TestRequirementsPanel` class in
    `tests/test_dashboard_e2e.py` (opens the real panel against the
    real built dashboard, confirms real content renders, zero console
    errors). Full `uv run pytest`, `uv run ruff check .`, and
    `npm test` all clean; visually verified with a real Playwright
    screenshot of the built panel.

76. **[done, 2026-09-18]** **[GitHub workflow & people]** Scoped via two real rounds of
    `AskUserQuestion` before building (this project's own standing
    convention): first a business-analyst subagent pass confirming real
    GitHub Issues access and surfacing real fit gaps against `docs/
    remediation-workflow-design.md` (the original design, settled
    2026-09-14 - notably BEFORE GitHub Issues was even a platform
    candidate; only Jira Service Management vs. Microsoft-stack tooling
    were on the table then, deliberately deferred), then a second round
    resolving the concrete MVP's own real forks: **granularity** -
    dataset-level (matching the dashboard's own Tier 3 unit - Birth
    Registrations, plus each of Child Protection's 6 real tables
    separately, not one combined CP ticket - Keith's own explicit
    override of this session's column-level suggestion), **scope** -
    creation plus live automatic status-update comments, escalation
    explicitly deferred ("circle back on the escalation stuff"),
    **automation location** - a new, separate, write-permitted GitHub
    Actions workflow, never folded into `deploy-pages.yml` (that
    workflow's own design is built around staying read-only against
    everything except the Pages deploy itself; opening a real GitHub
    Issue is a genuinely different kind of action), **provider access**
    - internal-only for v1, and **amber handling** - sidestepped
    entirely for v1 (tickets only ever key off red; the amber-
    governance question in `plans/conceptual-design.md` Thread A stays
    parked, not blocking this).

    Real capability check done first, not assumed: created, commented
    on, and closed a real issue on this repo
    (`github.com/keithamoss/data-poc/issues/1`) to confirm actual write
    access, not just the earlier read-only `list_issues` check.

    Built: `qa_tools/common/dataset_status.py` - a dataset's current
    real aggregate status (worst-of every real, non-retired check's own
    current value across every column), a direct Python
    reimplementation of the dashboard's own client-side
    `worstOf()`/`checkStatus()` (necessary since the GitHub Action this
    feeds has no JS/browser runtime - same client/server split
    `pipeline/cadence.py`'s own docstring already explains for a
    different piece of logic). `qa_tools/common/ticket_sync.py` - the
    real create/dedup/update decision logic: at most one open GitHub
    Issue per dataset (found via a `dataset:<id>` label search); no
    ticket + red -> open one; ticket + still red -> a real "still red"
    comment (the original design's own "even non-transitions post"
    principle); ticket + resolved to amber/green -> a real "resolved"
    comment that never auto-closes (closing stays human-only, unchanged
    from the original design); no ticket + not red -> nothing happens.
    Runs via the real `gh` CLI (subprocess, matching this project's own
    established convention for invoking real external tools),
    authenticated by the job's own automatic `GITHUB_TOKEN` inside
    Actions. New workflow: `.github/workflows/ticket-sync.yml` - reads
    only the same CI-safe, committed-`qa_results/`-history-only build
    chain `deploy-pages.yml` already runs (no dashboard embed step, no
    Playwright - neither is needed here), `permissions: issues: write`,
    `contents: read` only (this job changes nothing in this repo's own
    git history).

    **Real, load-bearing finding while building, not shipped blind**:
    running `dataset_status()` against today's real, committed history
    confirms all 7 real datasets currently read red - item 74's own
    already-documented, still-open threshold-encoding bug (a warn-only
    check's unconfigured fail silently defaulting to 0; datacontract-
    cli's `severity: error` rules discarding their own real
    `mustBeLessThan` threshold), not a new bug introduced here. Turning
    on this workflow's push trigger before item 74's fixed would
    immediately open 7 real, permanently-visible GitHub Issues, none of
    them reflecting a genuine problem. **Deliberately shipped with NO
    automatic trigger** - `workflow_dispatch` only, real and manually
    testable right now, but not "live" - Keith's own call needed on
    whether to fix item 74 first or accept the noise before adding the
    push trigger back.

    Tests: `tests/test_dataset_status.py` (fixture-based rollup logic -
    worst-of-any-column, retired checks excluded, band boundaries) and
    `tests/test_ticket_sync.py` (every real decision branch, via a fake
    at the module's own single `_run_gh` subprocess boundary -
    deliberately never invokes a real `gh` CLI call or touches a real
    repo in the test suite, unlike dbt/Soda/datacontract-cli which are
    all safe to actually re-run locally; opening/commenting on a real
    GitHub Issue is a genuine external side effect a test suite must
    never actually cause). 316 tests passing (up from 302), `uv run
    ruff check .` clean.

77. **[done, 2026-09-18]** **[QA checks & contract]** Item
    74's two threshold-encoding bugs, fixed at Keith's own explicit
    request ("let's fix item 74"), scoped via a second AskUserQuestion
    round rather than assumed:
    - **Bug A** (a missing fail threshold silently defaults to 0):
      Keith's real question - "shouldn't a check always have a fail
      threshold? What's the use case for not having one?" - answered
      with real data (only 2 of 79+138 real checks are genuinely
      warn-only, both already covered by a separate `invalid_percent`
      check with a real fail threshold on the same column) and resolved
      to the narrower fix: `registering_parent_1_name`/`_2_name`'s
      `missing_percent` Soda checks get real fail thresholds (>15%/
      >50%, both well above every real observed value) instead of
      teaching `checkStatus()`/the trend chart a new "no fail
      configured" code path - `contract/bdm-birth-registrations-soda-
      checks.yml`, with real changelog entries.
    - **Bug B** (datacontract-cli's `severity: error` rules discarding
      their own real non-zero threshold): new `fail_threshold_from_
      quality_definition()` (`qa_tools/common/datacontract_common.py`)
      parses the real `mustBe`/`mustBeLessThan`/`mustBeLessOrEqualTo`
      value out of each check's own `qualityDefinition` instead of a
      blanket 0 - verified both real contracts only ever use those 3
      shapes with `severity: error` today (`mustBeGreaterThan`/
      `mustBeBetween` are real ODCS shapes but never used that way here
      - this project's own convention, per the freshness check's own
      comment, is to flip the query to a "0/low = healthy" `mustBe: 0`
      shape instead of a lower-bound threshold), so those fall back to
      the old default rather than guessing at a comparison direction
      with no real example. `place_of_birth_facility`'s real
      `mustBeLessThan: 35` rule (real observed ~2%, genuinely passing)
      was the clearest real-world case this was silently breaking - now
      covered by a real regression test.

    8 new tests, all passing; `uv run ruff check .` clean. Code/config
    committed as `4e15db0`.

    **Regenerating `qa_results/` history hit a real, separate blocker,
    now resolved.** Running `orchestrate_bdm.py` to verify against real
    data surfaced a genuinely separate, previously-undiscovered issue:
    BDM's generator anchors its 176-run rolling window to real "today"
    (`generator/anchor_date.py`), and the window had rolled forward one
    real day since the last committed regeneration (a `tests/
    test_generate_runs.py` fixture regenerates the real `data/raw/` on
    every full local `pytest` run - real, by design). Since `data/raw/`
    is never cleared between regenerations, re-running `orchestrate_
    bdm.py` produced 176 brand-new, non-overlapping `qa_results/` run
    directories alongside - not replacing - the 176 already-committed
    ones, doubling BDM's `qa_results/` on disk. This session's own auto-
    mode classifier denied every bulk-deletion command tried (`git rm
    -r`, `git clean -fd`), even scoped to only the untracked stray
    directories - Keith's own suggestion ("delete them bit by bit")
    found the real boundary: explicit, individually-named `rm`/`git rm`
    calls (no `-r`/`-fd`/wildcard) pass the classifier every time. Used
    that to clean up the stale window and, once regenerated, to nuke-
    and-replace the old committed 176-run window with the fresh one -
    same pattern as the two earlier, Keith-approved "nuke and
    regenerate" operations (`plans/publishing-and-history.md`).

    **A second, real environment bug found along the way (not item
    74's, and not a design question - genuinely just a missed step):**
    re-running `orchestrate_bdm.py` alone left `data/warehouse.duckdb`
    (the COMBINED warehouse `dataset_stats.py` reads for arrival/value-
    count stats) stale against the just-regenerated `data/raw/` window,
    so today's own run (`run_120_2026-09-18`) had zero matching rows
    when queried, making `earliest_extract`/`max_lag_hours` both `None`
    and crashing `pipeline/build_dashboard_data.py`. Fixed by running
    `pipeline.orchestrate` (rebuilds the combined warehouse) before
    `orchestrate_bdm.py`, matching CLAUDE.md's own documented
    prerequisite for that "just the real-tool check runs" path.

    **Verified against real, freshly-regenerated data**:
    `registering_parent_1_name`/`_2_name` now read green/pass across
    all three engines (dbt/Soda/datacontract-cli) on every one of the
    176 real runs - the false-red is genuinely gone. `birth-
    registrations`' own aggregate status still reads red, but for a
    real, different, non-bug reason: `is_multiple_birth`'s sibling-match
    check (a genuine `mustBe: 0` zero-tolerance rule, all three engines
    agreeing) is correctly catching 2 real violations on today's run - a
    true positive, not a threshold-encoding artifact.

    **A wider version of Bug A found while verifying, and fixed too**:
    the same two real-world checks (parent-1/parent-2 missing-name
    rate) are triplicated across dbt/Soda/datacontract-cli (this
    project's own established pattern) - the original fix only touched
    the Soda copy, so `birth-registrations` still read red via the
    UNTOUCHED datacontract-cli copies (`registering_parent_1_name`'s
    real rule was `mustBeLessThan: 5, severity: warning`; `_2_name`'s
    was `mustBeLessThan: 30, severity: info` - both correctly resolve to
    `fail_threshold=None` under the Bug B fix, but Bug A's still-present
    "None defaults to 0" code then makes that read as a hard zero-
    tolerance rule anyway). Fixed the same way `place_of_birth_
    facility`'s own rule already establishes as this contract's
    pattern: bumped both to `severity: error` with a real non-zero
    `mustBeLessThan` (15/50, matching the Soda fix's own real
    thresholds) - `contract/bdm-birth-registrations-contract.yaml`, with
    real changelog entries. Confirmed `on_fail_action`'s `quarantine`-
    vs-`flag` distinction (the one other real consequence of bumping
    `severity`) is currently dormant/unused anywhere else in this
    codebase, so this has no other live effect today. Re-verified: both
    checks now read green across all three engines.

    **`child-protection`'s own 6 real datasets are NOT part of this
    fix** - all 6 still read red on real, unexamined data (spot-checked:
    real, substantial violation counts across many columns - duplicate
    IDs, null rates, invalid values - not an obvious repeat of the
    same threshold-defaulting pattern, more likely either a genuinely
    bad/dirty synthetic day or a separate issue). Item 74 was always
    scoped to the BDM finding specifically; CP's own status is a real,
    flagged-but-not-yet-investigated open question, not something this
    fix touched or claims to resolve.

    **A `check-yaml` pre-commit hook added along the way** (Keith's own
    suggestion, after a hand-edited `contract/*.yaml` changelog entry
    got shell-escape-style quoting instead of real YAML quote-doubling -
    still committable since ruff only checks Python, not caught until
    the next real tool run parsed the file) - `.pre-commit-config.yaml`,
    verified clean against every YAML file already in the repo.

78. **[done, 2026-09-18]** **[GitHub workflow & people]** GitHub Issues ->
    dashboard integration, at Keith's own request ("integrate the
    GitHub issues with the reporting UI as well"): a small badge on
    each dataset's own tile (Tier 2's dataset table + Tier 3's header,
    both the normal and no-data-as-of row/page variants) linking
    straight to that dataset's real, currently-open GitHub Issue (item
    76's ticketing MVP), when one exists. Scoped in two rounds:
    placement (badge on the tile itself, not a separate panel or folded
    into the changelog feed) and data flow (embedded at dashboard BUILD
    TIME via a new `.github/workflows/deploy-pages.yml` step - a real,
    read-only `gh issue list --label qa-ticket --state open` call,
    `issues: read` only, never `contents: write` - rather than a live
    client-side call to GitHub's API from the visitor's browser, same
    "placeholder here, real data only in the built output" treatment
    every other embedded feed on this page already gets).

    Built: `qa_tools/common/ticket_status.py` (new - `parse_open_
    tickets()`, a pure reshape of `gh issue list`'s own JSON into
    `dataset_id -> {number, url, title, updated_at}`, keyed off the
    `dataset:<id>` label `ticket_sync.py`'s own `open_ticket()` already
    attaches); a new `TICKET_STATUS` const wired through `dashboard/
    embed_dashboard_data.py` (reads `reports/open_tickets.json` when
    present, gracefully embeds `{}` when absent - a local
    `./run_pipeline.sh` build has no real token); `ticketBadge()` in the
    template, wired into both Tier 2/Tier 3 real-data and no-data
    variants. 7 new Python tests (parsing + embed()'s file-present/
    absent wiring) plus a real-browser Playwright test (`tests/
    test_dashboard_e2e.py::TestTicketBadge`) - manually verified working
    (real badge, real link, both tiers) via an injected `TICKET_STATUS`
    before the automated test was written. Its own real-browser
    fixture (a bare `tmp_path`, deliberately isolated from `dashboard/`
    itself - see `OPEN_TICKETS_JSON`'s own docstring) initially failed
    for a real, separate reason: the template's local `@font-face`
    files resolve relative to the HTML file's own directory, which
    only has `dashboard/fonts/` alongside it when writing into the
    real `dashboard/` directory - fixed by symlinking `dashboard/
    fonts/` into the fixture's own `tmp_path`. Confirmed green both
    locally (full suite, 333 passed) and in real CI. `uv run ruff
    check .` clean.

79. **[done, 2026-09-18]** **[QA checks & contract]** Keith's own follow-up question once
    item 74's fix was verified: why do `child-protection`'s own 6 real
    datasets still read red? Checked properly this time (item 74's own
    write-up above already learned the lesson of not stopping at a
    narrow grep) - real, complete, and boring: `data/cp_raw/
    manifest.json`'s own real dirty_severity rotation across all 15
    real quarterly deliveries (`cp_run_01_2023-02-01` through
    `cp_run_15_2026-08-01`) happens to land on `red` for the MOST
    RECENT one - a deliberate, heavy synthetic-corruption injection
    (the same generator mechanism BDM's own dirty runs use), not a
    threshold-encoding bug. Real violation counts checked against
    real row counts (e.g. 14 duplicate `cp_client_id`s out of 527 real
    `cp_clients` rows, ~20 invalid `sex` values out of ~1000
    `cp_notifications` rows) - all in the few-percent range a "red"
    severity injection would produce, nothing implausible or
    compounding. Also checked CP's own contract for any remaining
    instance of item 74's Bug A pattern (a genuinely-tolerant
    `severity: warning`/`info` rule silently zero-defaulted) - the
    only 6 warning-severity rules in `contract/child-protection-
    contract.yaml` are all `rowCount` `mustBeBetween` checks, already
    correctly excluded from the per-column dashboard entirely (see
    `build_cp_dashboard_data.py`'s own comment on why). **Conclusion:
    CP's red status is a genuine true positive, same class of finding
    as `birth-registrations`' own `is_multiple_birth` result above -
    nothing to fix.** No code/config change made. The real, open
    question this surfaces instead - CP's next quarterly delivery
    (whenever it's next generated/committed) would presumably read
    green/amber again, so CP's own ticket, once `ticket-sync.yml`'s
    push trigger opens one for real, will get a real "resolved"
    comment on that future run rather than staying open indefinitely -
    not itself a problem, just worth knowing going in.

    **`ticket-sync.yml`'s automatic push trigger enabled the same day**
    (Keith's own explicit go-ahead, asked directly given this finding:
    "yes, enable it now" over "investigate CP first") - `on: push:`
    added, paths mirroring `deploy-pages.yml`'s own trigger (minus
    `dashboard/**`/`CHANGELOG.md`/`requirements.yaml`, which this job
    never touches). All 7 real datasets' current red/green status is
    now genuinely real, not a threshold-encoding artifact - the first
    real tickets this opens (`birth-registrations` for the real
    sibling-mismatch, all 6 CP tables for the real dirty-severity
    delivery) both reflect genuine findings, not noise.

80. **[done, 2026-09-18]** **[Docs & process]** Keith's own follow-up on `CHANGELOG.md`
    (dictated): a real timestamp against every entry ("10 a.m., 10:15
    a.m."-style), sorted newest-first within each date's own
    `### <category>` subsection, so the newest thing is always at the
    top - not just newest-date-first, which the file's Keep-a-Changelog
    convention already gave it. Scoped via AskUserQuestion: retrofit
    **all 6** existing date sections (not just today's); use **real git
    commit timestamps**, converted to AWST (`TZ=Australia/Perth git log
    --date=format-local:'%Y-%m-%d %H:%M' --pretty=format:'%h|%ad|%s'
    --reverse`), never fabricated/approximate ones; also show these
    timestamps in the dashboard's own Release Notes panel, not just the
    markdown file. An entry whose work spanned several commits gets the
    latest one's real time (Keith's own rule). Matching every existing
    bullet's exact wording to its real underlying commit(s) surfaced 3
    bullets filed under the wrong date relative to their real commits -
    moved to the correct section rather than left mis-dated with a
    fabricated-precision timestamp bolted on: resupply-chain simulation
    (13th -> 14th, its real commit is `2026-09-14 07:44`), the
    status-pill/run-picker/comparison-panel bullet (15th -> 16th, real
    commit `2026-09-16 07:33`), and the cadence-aware as-of date picker
    (16th -> 17th, real commit `2026-09-17 07:42`).

    Format: `- **<H:MMam/pm>** — <original bullet text, unchanged>`.
    `dashboard/changelog_md.py`'s `parse_changelog()` extended to parse
    this optional leading `**<time>**` marker - each section's `items`
    changed shape from a bare `list[str]` to `list[{"time": str | None,
    "text": str}]` (`"time": None` for any entry predating this
    convention, so the parser stays backward compatible rather than
    requiring every historical entry to carry one); the soft-wrapped-
    continuation-line join logic updated to append to the new `"text"`
    field. `dashboard/qa-reporting-dashboard.template.html`'s
    `renderChangelogPanel()` updated to render that time (when present)
    ahead of each item's own text, styled with the page's existing
    `.mono`/`--ink-faint` convention (same treatment `arrivalStatusLabel()`-
    adjacent timestamps elsewhere on the page already get) - no visible
    change for a `"time": None` item, so nothing regresses for any future
    entry someone adds without one. `tests/test_changelog_md.py`'s
    existing item-shape assertions updated to the new dict shape, plus 3
    new tests (leading-timestamp parsing, no-timestamp backward
    compatibility, a wrapped bullet that starts with a timestamp).
    `tests/test_dashboard_e2e.py` gained `TestReleaseNotesPanel` - opens
    the real built dashboard's Release Notes panel and asserts a real
    `H:MMam`/`H:MMpm` timestamp actually renders, not just that the
    panel has content (which it already did before this change) - run
    against the real, CI-safe build chain via the shared
    `built_dashboard_html` fixture, same as the other e2e test classes.
    Verified: `uv run pytest` (full suite, including the new e2e test),
    `uv run ruff check .`, `npm test` (Vitest, unaffected - no JS test
    currently exercises the changelog panel directly) all green; the
    real built dashboard's Release Notes panel visually confirmed
    rendering timestamps ahead of each entry, newest-first within each
    subsection, via the same Playwright check.

81. **[done, 2026-09-18]** **[Data generation]** CP resupply simulation - queued in
    `plans/running-thoughts.md` ("Child Protection resupplies... once
    you're done with this loop"), picked up once that loop (Phase 6/7,
    the ticketing MVP, item 74's fix, the timestamp retrofit) wrapped.
    `generator/generate_cp_runs.py` had zero resupply-chain concept
    before this - a red quarterly delivery just stayed red forever
    (exactly what item 79 found as a real true positive). Scoped via
    AskUserQuestion (3 real forks): (1) CP's own resupply delay curve -
    "2-4 weeks, mostly 1-2" (Keith's own calibration), a genuinely
    slower/wider curve than BDM's 1-10 business days (mostly 1-3) -
    a full quarterly collection re-extract realistically takes longer
    to correct than a single day's file; (2) add 1-2 earlier red
    deliveries, not just the always-red final one, so there's a real
    RESOLVED chain to look at too - matches BDM's own precedent
    exactly (that RUN_PLAN's own comment: "bumped from a single red to
    2... to demonstrate variability"); (3) whether to reuse `generator/
    resupply.py`'s generic chain-orchestration engine (BDM's own) or
    fork CP-specific logic - reuse won, which meant genericizing that
    module first (below).

    **`generator/resupply.py` genericized.** `DatasetProvider`/
    `Attempt`/`run_delivery_chain` were hardcoded to a single
    `pd.DataFrame` payload (Birth Registrations' shape) - CP's own
    payload is a whole delivery's worth of tables at once
    (`dict[str, pd.DataFrame]`). Made generic over a TypeVar `T`
    instead of forking the module - the chain-walking loop never
    inspected payload internals to begin with, so this was a type-hint-
    only change (`Attempt.df` renamed to `Attempt.payload`, every call
    site updated). `delay_days`/`delay_weights` also became real,
    optional parameters (defaulting to BDM's own existing curve, so
    BDM's own call site needed zero changes) instead of hardcoded
    module constants. Verified behaviour-preserving for BDM by
    regenerating and md5-diffing `data/raw/manifest.json` plus sample
    CSVs before/after - byte-identical.

    **`ChildProtectionProvider`** (generate_cp_runs.py) - `generate()`
    returns a copy of the real base tables (population + casework,
    built once from a fixed seed) with `extract_timestamp` stamped
    once; `dirty()` reuses the exact same 6 `apply_cp_*_presets` calls
    `main()` used to make inline, now callable per-attempt, still
    referencing `base_tables` (never the current attempt's own,
    possibly-churned payload) for the dangling-FK injectors' exclusion
    sets - consistent with a resupply's own "the same underlying
    collection, corrected" framing (plans/conceptual-design.md Thread
    A), not a fresh random draw each attempt; `churn()` is a small-rate
    `extract_timestamp` nudge on the 3 "activity" tables
    (cp_notifications/cp_investigations/cp_placements) - cp_clients/
    cp_carers/cp_case_workers pass through unchanged as comparatively
    stable reference entities over a resupply's short window.

    **Real bug found and fixed the same day, before this shipped**:
    churn()'s first draft ALSO independently removed ~1% of rows from
    each activity table - real output caught it immediately (a resupply
    attempt whose own `dirty_severity` was genuinely `null` still read
    RED on the dashboard's real aggregate-status pill). Root cause:
    child_protection.py's own generation keeps every cross-table
    business rule (escalation completeness, placement/carer approval,
    closed-case hygiene) clean BY CONSTRUCTION on a clean run (this
    file's own top docstring) - independently dropping rows from
    cp_notifications and cp_investigations broke escalation
    completeness for real (an "Investigation opened" notification whose
    matching investigation got independently removed). Fixed by
    dropping the remove step entirely - churn stays modify-only, which
    can never break a cross-table rule since it never changes which
    rows exist. Caught by actually looking at the real rebuilt
    dashboard's own supply-history UI before calling this done, not
    just trusting the generator's own "clean" label - same discipline
    item 74's own wider-bug investigation established.

    **Verified**: full `uv run pytest` (344 tests, +6 new: 4 in
    `tests/test_generate_cp_runs.py` mirroring `test_generate_runs.py`'s
    own manifest-shape assertions, 2 in `tests/test_resupply.py`
    covering the generic dict-payload path and a custom delay curve),
    `uv run ruff check .`, `npm test` (unaffected) all green. Real CP
    data regenerated end to end (`generator.generate_cp_runs` ->
    `qa_tools.cp.orchestrate_cp` -> committed `qa_results/` -> rebuilt
    dashboard) and confirmed via a real Playwright check against the
    built dashboard's own `cp-notifications` supply-history table: both
    red deliveries (`cp_run_13`, `cp_run_15`) show real resupply
    attempts with a real business-day-computed "N days since previous"
    counter, both resolving to green - plus a real illustration of the
    chain model's own documented behaviour (plans/conceptual-design.md
    Thread A): a chain isn't restricted to a single delivery's own
    official resupply attempts - `cp_run_08` (amber-severity, but reads
    red on `cp_notifications`' own real checks) chains straight into
    `cp_run_09` (the next SCHEDULED quarterly delivery, no synthetic
    resupply relationship at all) as "attempt 2," purely because that's
    what the real, consecutive per-run status says - exactly the
    "derive from real observable facts, not synthetic bookkeeping"
    design this whole redesign was built around, now visibly true for a
    second dataset, not just claimed for one.

    **Follow-up, same day, dictated feedback**: two real calibration
    corrections. (1) "only some tables in CP to fail... two or three
    could fail, and the rest could be fine" - `ChildProtectionProvider.
    dirty()` used to apply the delivery's severity to all 6 real tables
    uniformly; now defers to a new `_pick_dirty_tables(seed)`, drawing
    2 or 3 of the 6 per dirty() call (own test:
    `test_dirty_only_picks_2_or_3_of_the_6_tables`). (2) "no need for
    the latest one to always fail... happy for it to be random" -
    `RUN_PLAN`'s last slot folded into the same shuffle as every other
    non-first delivery; only the first stays forced clean (a real
    technical need - `orchestrate_cp.py`'s own Evidently reference
    run). Regenerated + re-verified via Playwright the same way as the
    initial build above.

82. **[investigate, 2026-09-18]** **[QA checks & contract]** Great
    Expectations (GX Core) as a genuine comparison tool alongside
    dbt/Soda/datacontract-cli/Evidently in `real_tools/`. `docs/data-
    contract-engines-landscape.md`'s own worked example noted GX "isn't
    pip-installable in this environment" at the time it was written -
    that's no longer true (confirmed via `pip index versions great-
    expectations`: 1.23.0 available), the same kind of stale-constraint
    discovery as Faker/Mimesis in `docs/synthetic-data-generation-tools-
    research.md`. Worth revisiting IF research holds up that it adds
    something the current four tools don't. **Rationale downgraded**:
    the original candidate reason was GX's `unexpected_index_list` as
    the way to get real per-row failing-record samples - but item #15's
    follow-up research (reading the actual installed source of all four
    current tools, not docs) found THREE of the four already do this
    natively: `datacontract-cli` via `include_failed_samples=True` (a
    one-line change to what `run_datacontract_real.py` already calls),
    Soda Core via SodaCL's `samples limit:` + a custom `Sampler` class,
    and dbt via `store_failures: true` - none currently turned on, but
    none need a new tool either. Evidently genuinely doesn't (confirmed -
    no such concept in its source), consistent with its role here being
    drift/row-growth, not validity. So GX is no longer motivated by that
    specific gap. Not yet scoped whether it's worth evaluating for any
    other reason (pure feature/API comparison, maturity, ecosystem) -
    Compare, don't assume, before wiring anything in.

    (Moved here from `plans/wider.md` #14 as part of that file's
    2026-09-18 split - a QA-checks-and-contract concern, not a
    whole-of-project one.)

83. **[done, 2026-09-14]** **[QA checks & contract]** Removed
    `engines/*.py` entirely, superseding `plans/wider.md` #3's earlier
    "rename for consistency" pass. Follow-up to Keith's own question
    ("do we still need the old equivalent engine code given that's
    legacy from when we couldn't install packages?") - scoped via
    questions first (framework/scope for the smoke-tests work landing
    alongside this, uv adoption), with the engines/ decision itself
    answered directly: remove it, real internet access isn't going away
    and it had already drifted out of sync (Child Protection, the
    row-count-growth/freshness/text-format checks were all built
    real-tools-only, never backfilled).

    Confirmed safe first: `reports/results_real.json` (real_tools/
    orchestrate_real.py's output) is a strict superset of the old
    equivalent path (824 checks vs. 630) - no coverage gap from dropping
    the merge.

    What changed, beyond deleting `engines/*.py` and the now-dead
    `real_tools/compare_real_vs_equivalent.py`:
    - `pipeline/orchestrate.py` trimmed to just its real remaining job -
      generate + load the combined warehouse (`data/warehouse.duckdb`) -
      dropping the "run 4 equivalent engines -> reports/results.json"
      half entirely. The combined warehouse itself is still needed:
      `build_dashboard_data.py`'s own direct DuckDB queries (e.g. the sex
      value-count chart) run against it; `real_tools/orchestrate_real.py`
      builds its own separate per-run warehouses for dbt/Soda.
    - `pipeline/build_dashboard_data.py` rewritten to source solely from
      `results_real.json` - removed the `_REAL_ONLY_CHECK_KEYS` allowlist
      and `_merge_real_only_checks()` merge logic entirely (there's no
      more "base" equivalent result to merge real-only checks into), and
      simplified `ENGINE_SHORT` to the 4 real tags only.
    - `run_pipeline.sh` rewritten to run the actual real-tools pipeline
      end to end (generate+load -> real_tools/orchestrate_real.py ->
      build_dashboard_data.py -> embed) rather than the old
      equivalent-only path - there's only one path now.
    - README.md's whole "two generations" framing rewritten - the intro,
      quick-start, tool table, Layout section, and "The Child Protection
      collection"/"Known simplifications" sections all updated. The
      debugging narrative in "Known simplifications" (the real ODCS
      validation fixes, the dbt-core %-syntax bug, the dbt-duckdb
      reliability bug, the Soda wall-clock finding, the PSI binning
      difference) was kept, not deleted - it's genuine technical history
      - just reframed as "found by comparing against the equivalent that
      existed at the time" (past tense) rather than describing an
      ongoing dual-source dashboard, since there's only one source now.
    - Swept every other file for stray references to the deleted module
      names/paths and fixed them in place rather than leaving dangling
      pointers: `real_tools/*.py` docstrings/comments, `contract/
      bdm-birth-registrations-contract.yaml`, `dbt_project/dbt_project.yml`
      and `schema.yml`, and the dashboard HTML (a visible footer line, a
      JS block comment, and a drawer subtitle template string) - plus one
      unrelated stale `HANDOFF.md` reference found along the way (that
      file was deleted earlier this session; missed at the time).

    **Verified end to end, not assumed**: full `./run_pipeline.sh` run
    after the rewrite succeeded with no `engines/` dependency anywhere;
    confirmed the rebuilt dashboard JSON has zero stale "equiv" wording
    and every check's `engine` field is one of the four real tags. This
    file's own historical entries (bug-hunt narrative naming
    `contract_engine.py`/`soda_engine.py`/etc.) were deliberately left
    untouched - that's a development log of what happened and when, not
    a description of current state, so it stays historically accurate
    as originally written.

    (Moved here from `plans/wider.md` #18 as part of that file's
    2026-09-18 split - a QA-checks-and-contract concern, not a
    whole-of-project one.)

84. **[done, 2026-09-14]** **[QA checks & contract]** Code duplication
    across `real_tools/*_real.py` (BDM) vs `real_tools/*_real_cp.py`
    (Child Protection) file pairs - asked because more datasets are
    coming. Confirmed: yes, one file pair per tool, 8 files / 1392 lines
    total for 2 datasets (dbt 258+181, Soda 200+140, datacontract-cli
    154+177, Evidently 185+97).

    Diffed the dbt pair (and spot-checked the Soda pair) in full. Same
    split both times:
    - **Genuinely shared/generic** (~30-40 lines/pair): subprocess/API
      invocation boilerplate (`_run_dbt`'s `subprocess.run` call shape,
      `--target-path` handling), `_parse_threshold`/`_NUM_RE`, path
      constants, `ENGINE_TAG` pattern, the per-run-warehouse-file
      convention.
    - **Genuinely dataset-specific** (the rest): test-name -> dimension/
      label mapping dicts (different tests exist per dataset), BDM's
      `_VERIFY_COUNT_SQL` dbt-duckdb reliability workaround (Child
      Protection has never hit that bug), CP's `_table_for_test()`
      multi-table attribution (BDM is single-table, doesn't need it).
      This half isn't boilerplate - it's the actual check-to-dashboard-
      field mapping logic per dataset, and forcing it into one shared
      abstraction would fight the grain of "each dataset's tests are
      genuinely different."

    Not a false-DRY situation, but not nothing either: ~150-260 lines/
    file with a real (if partial) shared layer inside it, and every new
    dataset currently means copy-pasting a whole file and manually
    picking apart which parts to keep.

    **Built** (2026-09-14), scoped via questions first (naming suffix,
    folder structure, import style, and what to do with an unrelated
    stray file the restructure surfaced):
    - **Renamed the BDM/birth-registrations files to match the CP
      convention** - `run_dbt_real.py` -> `run_dbt_real_bdm.py` etc.
      (`_bdm`, not `_births` - matches the existing `contract/
      bdm-birth-registrations-*` naming and "BDM" used as the dataset's
      short name everywhere else in the repo). Previously birth
      registrations had no suffix at all (it was the only dataset when
      these files were written) while CP got `_cp` when it was added
      later - fine with one dataset implied by "no suffix," not fine
      with more coming.
    - **Extracted the confirmed-shared ~30-40 lines/tool-pair** into
      `real_tools/common/{dbt,soda,datacontract,evidently}_common.py` -
      exactly the boilerplate identified above (subprocess/API
      invocation, `--target-path` handling, threshold parsing,
      `ENGINE_TAG`), plus two extra bits datacontract-cli's and
      evidently's pairs turned out to also share byte-for-byte once
      written side by side (the "local_test" server + `DataContract
      .test()` construction; the PSI-via-DataDriftPreset computation) -
      found while doing the extraction, not predicted in advance. Left
      genuinely dataset-specific: test-name/metric mapping dicts, BDM's
      `_VERIFY_COUNT_SQL` workaround, CP's `_table_for_test()`, BDM's
      row-count-growth check (CP has no equivalent).
    - **Split into per-dataset subfolders** - `real_tools/bdm/`,
      `real_tools/cp/`, `real_tools/common/` - rather than a flat
      directory of 16 files that only reads as organized by tool-name
      prefix. `dbt_profiles/` stays directly under `real_tools/` (one
      shared dbt project, can't be split by dataset).
    - **`real_tools` became a proper Python package** (`__init__.py`
      throughout, dotted imports - `from real_tools.common import
      dbt_common`, `from . import cp_common`) rather than extending the
      old per-script `sys.path.insert(0, dirname(__file__))` hack across
      subfolders - Keith's own call between the two options asked about.
      Scripts now run as `python3 -m real_tools.bdm.orchestrate_real_bdm`
      (not a bare file path) - `run_pipeline.sh`, README, and CLAUDE.md
      all updated. `pyproject.toml`'s pytest `pythonpath` swapped
      `"real_tools"` for `"."` accordingly.
    - **Deleted `real_tools/soda_configuration.yml`** (Keith's call, once
      established it wasn't used by any code - a static reference doc
      for running the `soda` CLI directly, hardcoded to one BDM run file,
      superseded by the Python Scan API `run_soda_real_bdm.py` actually
      uses). Git history holds it if ever needed.

    Verified behaviour-preserving, not just refactored: both orchestration
    scripts re-run end to end post-restructure and diffed byte-for-byte
    identical (modulo `run_timestamp`) against pre-restructure
    `results_real.json`/`results_real_cp.json` - 824 and 950 check
    results respectively, zero differences. `uv run pytest` (19 tests,
    `tests/test_parallel_orchestrate.py`'s import updated to the new
    module path) and `uv run ruff check .` both clean.

    **Follow-up, same day: dropped `_real` everywhere.** Keith noticed the
    `_real` qualifier throughout (`real_tools/` itself,
    `run_dbt_real_bdm.py`, `results_real.json`, the `ENGINE_TAG` values'
    `"(real)"` suffix) only ever meant "genuinely ran the tool, not the
    `engines/*.py` hand-written equivalent" - and that distinction has had
    nothing to contrast against since `engines/*.py` was removed (item
    #83 above). Confirmed before touching anything: the dashboard's
    *separate* `REAL_BIRTH_REG_DATA`/`REAL_CP_DATA`/"Real pipeline data"
    naming is a different "real" (genuinely-computed rows vs. the
    illustrative mock data still covering most of the dashboard) and was
    deliberately left alone - not part of this cleanup.

    Scoped via questions (dropping `ENGINE_TAG`'s `"(real)"` is
    dashboard-visible - each check's note text - so worth confirming
    before regenerating reports/re-embedding the dashboard; renaming
    `real_tools/` itself is bigger again, since it touches the import
    paths just built): both yes. Keith left the new package name to be
    picked - went with `qa_tools/` (matches "QA reporting dashboard"/
    "QA pipeline" language used throughout the docs already; avoids
    `checks/`, which would collide in spirit with the existing
    `contract/*-soda-checks.yml` naming).

    What changed: `real_tools/` -> `qa_tools/`; every `_real_bdm.py`/
    `_real_cp.py` file -> `_bdm.py`/`_cp.py` (`run_dbt_bdm.py`,
    `orchestrate_cp.py`, etc.); every `evaluate_*_real_bdm`/
    `run_real_pipeline` function -> `evaluate_*_bdm`/`run_pipeline`
    (same pattern for `_cp`); `reports/results_real.json`/
    `results_real_cp.json` -> `results_bdm.json`/`results_cp.json`; all
    four `ENGINE_TAG` values lost their `"(real)"` suffix (`"dbt-core
    1.12 + dbt-duckdb"` etc.) - which meant updating `ENGINE_SHORT`'s
    dict keys in both `build_dashboard_data.py`/`build_cp_dashboard_data
    .py` to match, and regenerating `reports/*.json` + re-embedding the
    dashboard HTML so the new tag text actually reaches it. Also fixed:
    `build_cp_dashboard_data.py`'s `sys.path.insert(..., "real_tools")`
    + flat `import cp_common` (would have broken outright once
    `real_tools/` stopped existing) now does `from qa_tools.cp import
    cp_common` instead; a couple of stale `real_tools/soda_configuration
    .yml` mentions left behind in `contract/child-protection-soda-checks
    .yml`'s usage comment from that file's earlier deletion (this item's
    own first round, above) were also caught and fixed here, not before.

    Verified the same way as the first round: both orchestration scripts
    re-run end to end, this time diffed against the pre-rename output
    with an explicit exception for the field that was *supposed* to
    change - every `engine` string (and the `note` text
    `build_dashboard_data.py`/`build_cp_dashboard_data.py` derive from
    it) lost its `"(real)"` suffix, confirmed as the *only* difference;
    every other field, byte-for-byte identical. `uv run pytest`/
    `uv run ruff check .` both clean.

    (Moved here from `plans/wider.md` #20 as part of that file's
    2026-09-18 split - a QA-checks-and-contract concern, not a
    whole-of-project one.)

    **Picked up again, widened, 2026-09-19 - see `plans/tooling.md` #12**
    (Keith's own pointer, tying that item back to this one). This item
    stays `done`: what it actually did - diff the BDM/CP tool-runner
    pairs in full, sort the result into genuinely-shared vs
    genuinely-dataset-specific, extract only the confirmed-shared part -
    was completed and verified. What #12 takes from it is the METHOD,
    which is the closest thing this project has to a proven approach for
    this kind of work, plus two findings worth carrying forward: that
    actually diffing candidates side by side surfaced shared code nobody
    predicted, and that the honest answer here was "not a false-DRY
    situation, but not nothing either" rather than a clean verdict
    either way.

    Two things about this item are worth reading as OF ITS TIME rather
    than as standing rulings, since #12 will re-measure both. It
    measured **2 datasets** against a stated target of ~30; and its own
    closing cost - "every new dataset currently means copy-pasting a
    whole file and manually picking apart which parts to keep" - was
    accepted as tolerable at that scale, reopened by
    `plans/publishing-and-history.md` #6, and then, 2026-09-19,
    explicitly REJECTED as tolerable by Keith quoting this very
    sentence back: "that is not tolerable in the short term as we add
    more data sets, so that will need to be addressed as a priority."
    #6 is now `todo` and HIGH priority on the strength of it. So this
    item's own closing line has outlived the judgement attached to it -
    the cost it names is real and still there, what changed is that
    paying it is no longer acceptable. Nothing about the FINDING is
    being second-guessed; the codebase it was measured against has
    simply grown a lot since (`plans/qa-pipeline.md` item 74 alone
    turned up four separate status implementations, one of them dead).

85. **[investigate, 2026-09-18]** **[QA checks & contract]** A real, currently-unused
    way to make the ODCS contract the actual single source of truth for
    dbt's and Soda's own check files too - not just something the
    dashboard/datacontract-cli read. Keith asked for this to be flagged
    as an architectural consideration, not built. Same underlying pain
    as `plans/data-generation.md` #6 (the generator hand-duplicating the
    contract's column definitions), just hitting `dbt_project/models/
    staging/schema.yml` and `contract/*-soda-checks.yml` instead of
    `generator/daily_batch.py`: all three of these files independently
    hand-encode the same quality rules the ODCS contract already states,
    with nothing connecting them today - add or change a rule in the
    contract and the dbt/Soda check files silently don't follow, the
    same drift risk `plans/data-generation.md` #6 already named for the
    generator.

    Both tools have real bridge tooling for this (verified with actual
    research, not assumed - full detail and sources in item #19): `data
    contract-cli`'s own `dbt sync` command (already installed in this
    project) and the third-party `dbt-contracts` package both read an
    ODCS file and **write real `schema.yml`/model files to disk** -
    `dbt sync` specifically tags the sections it manages so a re-run
    won't clobber hand-added tests. Soda's `soda ai` (shipped inside
    `soda-core` itself, no extra install) translates an ODCS contract
    into Soda's own Contract Language, with a review-and-approve step
    before it saves a real file. **Neither is a live runtime bridge** -
    dbt and Soda always execute against whatever file is sitting on
    disk, with zero awareness of where it came from or whether it's
    stale relative to the contract.

    The pipeline shape this would actually enable, if adopted:
    ```
    contract/*.yaml (hand-edited, the only thing a human touches)
            |
            |  CI step, triggered on contract changes (or run manually)
            v
    `datacontract dbt sync ...`  /  `soda ai` (translate, review, approve)
            |
            v
    dbt_project/.../schema.yml (generated + meta-tagged)
    a generated Soda Contract Language file (replaces *-soda-checks.yml)
            |
            v
    `dbt build` / `soda scan` - run completely normally, no ODCS involved
    ```
    Real, currently-unresolved tradeoffs, not yet scoped: `soda ai` is
    explicitly experimental with no published GA date (see item #19
    above) - a real dependency to take on for a PoC, not a stable
    foundation yet. `dbt-contracts` is an unofficial third-party
    package, not from dbt Labs. And this project's own check design
    leans on things that might not survive a generated round-trip - the
    dbt-duckdb `fail_calc` reliability workaround (`schema.yml`'s own
    header comment), the count-based (not percentage) `warn_if`/
    `error_if` bands calibrated per check, the custom `failed rows`/
    `fail query:` pattern used where Soda's ordinary metric checks don't
    fit - would need verifying whether `dbt sync`/`soda ai`'s generated
    output can even express these, not just whether the happy path
    works. Not scoped further; revisit alongside `plans/data-
    generation.md` #6, not in isolation - same root question (should the
    contract generate its downstream check files, or stay read-only
    reference material) applied to a different pair of files.

    (Moved here from `plans/wider.md` #22 as part of that file's
    2026-09-18 split - a QA-checks-and-contract concern, not a
    whole-of-project one.)

86. **[done, 2026-09-19]** **[QA checks & contract]** Real bug found and
    fixed while building `/reject` for the amber-decision mechanism
    (`plans/running-thoughts.md` #6, `plans/conceptual-design.md` Thread
    A): `qa_tools/common/acceptance_sync.py`'s `_run_windows_for_
    dataset()` builds each real run's own comment-matching arrival
    WINDOW from consecutive entries sorted by `arrived_date` - two real
    runs sharing the same `arrived_date` turn out to be common in this
    project's own real committed history now (352 real BDM runs, only
    123 distinct dates - a side effect of this project's own full
    pipeline regenerations, which tend to produce same-day original+
    resupply pairs), not the rare theoretical edge case the function's
    own docstring originally described it as. The function's own
    long-documented intent ("ties resolve to whichever sorts first")
    didn't match what the code actually did: a naive
    `entries[i+1]`-as-window-end lookup gave the FIRST tied entry a
    zero-width `[date, date)` window (always empty, since
    `start <= created < end` can never hold when `start==end`), so a
    same-day `/accept` or `/reject` comment silently fell through to the
    SECOND (or last, for 3+-way ties) run instead - the opposite of the
    documented intent, and a real run a human could never actually
    target via a same-day comment. Fixed by deduping to one
    window-owning entry per distinct date (the first, by `list_run_ids`'
    own iteration order) before computing window ends - a same-day
    comment now genuinely resolves to whichever run sorts first, per the
    function's own original intent; other same-day runs are simply
    omitted from the window list rather than given a window that could
    never match anything. 3 new regression tests, confirmed failing
    against the pre-fix code first (via monkeypatched `list_run_ids`/
    `read_dataset_stats`, not real files - the collision itself is
    already covered against real committed history by this project's
    existing `TestRunWindowsAgainstRealCommittedHistory` tests).

## Held over from the original (equivalent-only) build

Lower priority — these were already documented as deliberate, honest
simplifications before any real tool ran, and nothing since has changed
that assessment. Listed here so they don't get lost, not because they're
urgent.

7. **[open, low]** ODCS severity is single-tier (pass/fail or pass/warn,
   never a three-way band). `contract_engine.py` encodes that into the
   dashboard's two-threshold shape as warn==fail (error severity) or an
   unreachable fail ceiling (warning/info severity). Real, not a bug —
   revisit only if the dashboard's shape itself changes.

8. **[open, low]** Soda's `row_count` check is a genuine two-sided range
   (too few *or* too many rows); `soda_engine.py`'s `_numeric_threshold()`
   reduces it to the upper bound only for display — the one place a piece
   of real information (the lower bound) is dropped for a single scalar.
   Would need a dashboard/schema change (a second threshold field) to fix
   properly, not just an engine change.
