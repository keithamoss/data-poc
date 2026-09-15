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

1. **[workaround shipped, high]** dbt-duckdb reliability bug. dbt-core's
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
   against `duckdb-labs/dbt-duckdb`; `plans/wider.md` #3/#4 (CI, Postgres)
   might also shed light on this without extra effort.

2. **[open, medium]** `soda-core-duckdb`'s `duckdb<1.1.0` pin isn't a
   compatibility ceiling — it pins to a DuckDB version with a published
   CVE (GHSA-w2gf-jxc9-pf2q), patched in 1.1.0. Confirmed via upstream
   issue `sodadata/soda-core#2295`. Currently ignored (we run on 1.5.5,
   verified working end to end — see `pyproject.toml`'s `[tool.uv]`
   comments). **Follow-up:** there's a newer `soda-duckdb` V4 package
   (`sodadata/soda-core/soda-duckdb`) that's actively maintained — worth
   checking whether it's the intended replacement and whether
   `run_soda_bdm.py`'s `Scan` API still exists there before migrating.

3. **[done]** Soda's `[recent]` scoped check (`filter ... where:
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

4. **[moot - `engines/*.py` removed]** Evidently's PSI and the equivalent
   engine's PSI used to genuinely differ (0.144 vs 0.179 on the red run)
   because Evidently bins by every distinct observed value while
   `evidently_engine.py` collapsed everything outside {M,F,X} into one
   `_other` bucket. Both were valid; documented, never reconciled - moot
   now that `engines/*.py` (including `evidently_engine.py`) was removed
   entirely (see `plans/wider.md` action 18) and there's no more
   equivalent to reconcile against. Left here as historical record, not
   an active item.

5. **[moot - `engines/*.py` removed]** `engines/contract_engine.py`'s
   `type: sql` rule handling (added when the contract was rewritten to
   real ODCS vocabulary) used a temp-view + string-replace to scope each
   SQL rule to one run's rows - worked, but was fragile, equivalent-only
   tech debt. Moot now that the file itself is gone (see `plans/wider.md`
   action 18). Left here as historical record, not an active item.

6. **[open, low]** The two-step `pip install` requirement is only half
   fixed: `uv sync --dev` now resolves everything in one step
   (`pyproject.toml`'s `[tool.uv] override-dependencies`, see action 19 in
   `plans/wider.md`), but a plain `pip install .` still needs the old
   two-step dance (`pip` has no equivalent override mechanism) - see
   README's install note. Worth a periodic recheck as
   `dbt-duckdb`/`soda-core-duckdb`/`datacontract-cli` release new
   versions; this could resolve cleanly on its own, or break differently.

9. **[done, medium]** Two of the three Child Protection cross-table
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
   regenerated; `plans/wider.md` #2's row-count calibration in the
   contract was rechecked and didn't need changes (row counts are
   unaffected by the fix, only which values land in `carer_id`/
   `case_status`/`end_date`).

10. **[done, medium]** Dashboard check display was hard for a human reader
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

11. **[done, medium]** Birth Registrations' QA coverage was thin outside
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

12. **[done, medium]** Two more checks Keith asked for directly: a
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

13. **[investigate]** Look more closely at what Evidently AI is actually
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

14. **[done, medium]** Dashboard follow-ups from actually using it: a real
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

15. **[investigate]** Genuine per-row failing-record samples, revisited.
    Item 14 above honestly noted that no real tool currently wired into
    this pipeline (dbt, Soda, datacontract-cli, Evidently) captures which
    SPECIFIC rows failed a check - only aggregate counts
    (`row_count_total`/`row_count_invalid`). `docs/quarantine_sex_column.py`
    already identifies the real mechanism for this: Great Expectations'
    `unexpected_index_list` (or a Pandera boolean mask) gives real
    row-level output, but GX isn't currently one of this pipeline's wired
    tools. See `plans/wider.md` #14 - worth pursuing together: if GX gets
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
    This meaningfully changes GX's case in `plans/wider.md` #14 - GX's
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

16. **[done]** Should the dashboard explain *why* checks on the
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

17. **[done, one open follow-up]** Aggregate failing-value shapes ("shape 2"), the
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
      `sys.path` manipulation anywhere - see `plans/wider.md`'s
      package-layout entry (action 21) for the full change, including a
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

18. **[investigate]** Explicit, non-magic null handling in every CSV
    read/write this pipeline does - a spike Keith asked for after item
    17's `"N/A"` bug. Right now every CSV read (`pd.read_csv(...)`,
    DuckDB's `read_csv_auto(...)`) relies on each library's own default
    list of "these specific strings mean null" - pandas' includes `""`,
    `"N/A"`, `"NA"`, `"NULL"`, `"NaN"`, `"None"`, `"n/a"`, `"nan"`,
    `"null"`, and several numeric-looking variants; DuckDB's own default
    list is separate and not necessarily identical. Nobody in this
    codebase chose that vocabulary - it's just whatever each library
    ships with, and item 17's bug is exactly what "silent library magic"
    costs when it collides with a real value. Goal: audit every
    `pd.read_csv`/`read_csv_auto` call site in `generator/`, `pipeline/`,
    `qa_tools/` and make null detection fully explicit - `pd.read_csv(...,
    keep_default_na=False, na_values=[""])` and DuckDB's
    `read_csv_auto(..., nullstr='')` - so an empty field is the ONLY
    thing that ever becomes NULL, and any other text (including "N/A")
    is always kept as the literal string it is. Needs checking against
    every EXISTING null-rate check too, not just re-verifying item 17's
    fix still holds - e.g. `place_of_birth_facility`'s null-rate check
    presumably relies on a genuinely empty CSV field becoming NULL today;
    confirm that still works identically once default sniffing is turned
    off everywhere, not just that "N/A" stops being swallowed. Also
    covers the write side (`to_csv()`'s own default for how a NaN gets
    written back out) for the same write-then-read round trip item 17's
    bug happened in.

19. **[investigate]** What dbt-core/Soda Core natively offer for "inspect
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
      datacontract-cli, their native caps (100 and 5 rows respectively)
      mean neither gives a true, exhaustive aggregate - some additional
      mechanism was genuinely needed for those two regardless.
    Not yet acted on - a real finding to keep in mind if `aggregate_
    values.py` (or a future dbt-specific optimization) gets revisited,
    not an immediate to-do.

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
