# Birth-registrations QA pipeline plan

Open items from wiring up the real dbt-core/Soda Core/datacontract-cli/
Evidently tools (`real_tools/*.py`) against this pipeline. Everything here
is either a genuine bug found by actually running the real tools, or a
documented equivalent-vs-real-tool disagreement worth a second look.
Scoped to this repo's `contract/`/`dbt_project/`/`engines/`/`real_tools/`
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
   `real_tools/run_dbt_real.py`. **Follow-up:** build a minimal standalone
   repro (no dbt project, just the SQL pattern) and file it upstream
   against `duckdb-labs/dbt-duckdb`; `plans/wider.md` #3/#4 (CI, Postgres)
   might also shed light on this without extra effort.

2. **[open, medium]** `soda-core-duckdb`'s `duckdb<1.1.0` pin isn't a
   compatibility ceiling — it pins to a DuckDB version with a published
   CVE (GHSA-w2gf-jxc9-pf2q), patched in 1.1.0. Confirmed via upstream
   issue `sodadata/soda-core#2295`. Currently ignored (we run on 1.5.5,
   verified working end to end — see `requirements-real.txt`'s comments).
   **Follow-up:** there's a newer `soda-duckdb` V4 package
   (`sodadata/soda-core/soda-duckdb`) that's actively maintained — worth
   checking whether it's the intended replacement and whether
   `run_soda_real.py`'s `Scan` API still exists there before migrating.

3. **[open, low]** Soda's `[recent]` scoped check (`filter ... where:
   extract_timestamp >= CURRENT_DATE - 1`) never gets meaningfully
   exercised against real Soda Core — it uses the actual wall-clock date,
   and this fixture's synthetic runs are all in the past by the time
   anyone actually runs it, so the scope always resolves to 0 rows.
   Documented as a real, honest finding (README's known-disagreements
   section), not fixed. **Follow-up:** regenerate the synthetic runs on a
   rolling window near "today" instead of a fixed Sept 2026 range, so the
   scoped check has real data to filter — would also un-stale the fixture
   generally.

4. **[open, low]** Evidently's PSI and the equivalent engine's PSI
   genuinely differ (0.144 vs 0.179 on the red run) because Evidently bins
   by every distinct observed value while `drift_engine.py` collapses
   everything outside {M,F,X} into one `_other` bucket. Both valid;
   documented, not reconciled. **Follow-up:** decide whether to make the
   equivalent's PSI bin per-distinct-value too (closer fidelity to
   Evidently, more equivalent-engine complexity) or leave it as a
   deliberate simplification — either is defensible, just needs a call.

5. **[open, low]** `engines/contract_engine.py`'s `type: sql` rule handling
   (added when the contract was rewritten to real ODCS vocabulary) uses a
   temp-view + string-replace to scope each SQL rule to one run's rows.
   Works, but is fragile — equivalent-only tech debt, not a real-tool
   issue.

6. **[open, low]** The two-step `pip install` requirement
   (`requirements-real.txt` then separately `pip install
   'datacontract-cli[duckdb]'`) is brittle — a single combined install is
   a hard resolver failure today. Worth a periodic recheck as
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
    plus one for Child Protection (`real_tools/run_evidently_real_cp.py`,
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
    **Separate, still-open question, explicitly Keith's own**: even
    though the capability is cheap, should the QA reporting dashboard be
    the thing that stores/displays actual row-level data (even synthetic
    government data), or does that belong in a separate remediation/
    quarantine surface the dashboard only links out to? Same split
    `docs/quarantine_sex_column.py` already draws between "flag it" and
    "act on it" - not answerable from the code, a real product-scope
    call. Suggested next step if pursued: prototype with datacontract-cli
    alone (cheapest, one flag) to see what it actually looks like on the
    dashboard before deciding whether it belongs there long-term.

    **Product-scope discussion, settled (2026-09-14) - several rounds of
    questions with Keith working through the actual shape.** Answers the
    "does this belong in the dashboard" question above: it doesn't - it's
    a genuine case-management/workflow capability, architecturally
    distinct from the QA reporting dashboard. This PoC's scope is to
    design the seam/handoff point, not build the thing itself; the choice
    of platform (Jira Service Management already exists at the agency,
    but Microsoft-stack tooling - Planner/Power Automate/SharePoint etc -
    is preferred to avoid extra licensing) is a deliberately separate,
    later conversation.

    Motivation: today's process (manual review, then a direct email/call
    to the provider) works at current scale but won't survive the move to
    daily refreshes - some of this needs to hand off directly to
    providers while the team keeps oversight, rather than reviewing
    everything by hand.

    Ticket model:
    - Every issue automatically becomes a ticket - no gatekeeping on
      creation - except a check marked "known, expected to stay amber
      long-term" doesn't spin up a repeat ticket for persisting as
      expected (a flip to red, or to green, still surfaces as a
      notification).
    - **Granularity: one ticket per column** - if several checks on the
      same column fail at once, that's one ticket, not several.
    - **Scope: one unified ticket queue across every dataset/agency**,
      filterable per audience - not separate queues per dataset.
    - **Recurrence: a fresh occurrence of a previously-closed issue
      creates a NEW ticket, cross-referenced to the prior one** - not a
      reopen. Keeps each incident's resolution-time measurement clean and
      separately trackable (matters for the SLA-reporting ambition
      below), at the cost of not having one continuous record per check.

    Assignment (the real decision point, not ticket creation):
    - Automatic default per check/column (e.g. schema/structural breaks
      default straight to the provider - clear-cut, major; subtler
      things like null-rate creep default to the team first),
      human-overridable.
    - A provider-assigned ticket still notifies the team - assignment
      isn't "the team goes dark," it's the trigger for the team's own
      watch/FYI so they can step in if needed.
    - Ownership can be joint - team and provider both actively engaged on
      one ticket at once, not necessarily a strict handoff.

    Escalation and suppression (two distinct mechanisms, easy to conflate):
    - **Escalation**: the same check failing 6+ times in a row is a
      supply-relationship signal, not routine noise - bumps the ticket's
      severity so it can't get lost.
    - **Suppression**: a check marked "known, expected to stay amber
      long-term" is exempt from both repeat-ticket creation AND the
      6-in-a-row escalation rule - trusting the deliberate "this is
      accepted for now" call rather than re-litigating it via a
      stretch-length trigger.

    Automatic pipeline updates - the underlying principle Keith named
    directly: **tickets should get a status update from the pipeline
    automatically anytime something happens that affects that check or
    column** - a resupply arriving (whether it fixes the issue or not), a
    quarantine release, any status touch, even non-transitions ("still
    red, no change" still posts). This maps closely onto infrastructure
    this repo already has: `generator/resupply.py`'s `run_delivery_chain`
    already yields exactly this kind of event sequence (severity/arrival
    date per attempt) for Birth Registrations' resupply chains - a real
    ticketing integration would consume much the same shape of event
    stream this generator already produces, not something wholly new.
    **Closing always requires a human - no auto-close, full stop**
    (superseded an earlier "maybe auto-close for minor issues" idea from
    partway through this discussion).

    Quarantine/release - extends `docs/quarantine_sex_column.py`'s
    existing split-and-hold demo with a release step that doesn't exist
    there yet: rows held in a dead-letter queue per check; only the
    internal team can execute a release back into the dataset (providers
    can be part of the decision, never the executor); any required
    second-level sign-off is a process convention inside the ticketing
    tool itself, not a separate technical permission system; the release
    auto-posts to the ticket per the principle above.

    Time-tracking: captured from the start, internal-only reporting for
    now, but deliberately designed so it could become a real, shared SLA
    metric with providers later (e.g. "BDM average resolution time: 4.2
    days") - worth capturing cleanly even before it's shared anywhere.

    Audiences and access (one point still genuinely open): three
    distinct roles - data engineers (full detail + workflow tools), their
    managers (an oversight/rollup view), and external data providers
    (restricted to what they need to act - e.g. primary keys of bad rows,
    not full row content). The external access *mechanism* (an
    authenticated portal, email-threaded notification with no login, or
    some hybrid) is still open - not really an either/or in practice
    (most real platforms support both at once), and the real open
    variable is how much back-and-forth a typical resupply conversation
    actually needs. Left for the project-context walkthrough
    (`plans/wider.md` #16) to settle, per Keith's own call.

16. **[investigate]** Should the dashboard explain *why* checks on the
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
    workaround needed. Given two-tier is a must-have, this is real signal
    against datacontract-cli being one of the eventual 1-2 tools *unless*
    doubling up quality rules is an acceptable convention - worth
    weighing when it's time to actually narrow down.

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
