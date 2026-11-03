# Rule 3 audit: is the raw evidence recorded when it happens?

Read-only audit, 2026-10-13 (Perth). Sources: `qa_tools/common/qa_store.py` DDL, every writer
named in the brief, and SELECT-only queries against the freshly bootstrapped `supply`
database (229 runs, 13,070 check results, 300 decisions, 221 verdicts).

Question (Keith): "Rule 3: record the raw evidence when it happens, so any future derived value or
change can use it. Do we have gaps NOW, in the PoC, that we should start capturing?"

Short answer: **yes, eight that matter.** Three of them are HIGH:
- the recorded evidence of a run can be overwritten in place;
- no bytes-level identity is kept for a delivered file;
- nothing records which code or tool versions produced a verdict.

The tool outputs themselves are captured better than expected. The gaps sit around them: identity,
versions, the instant a verdict was judged on, and what a person was shown. One finding runs the
other way, and it needs Keith rather than a fix: the qa schema already holds some supply-row values.

---

## Severity key

- **HIGH**: on a real asset, this would force re-judging or lose history for good.
- **MED**: a plausible future derived value or migration becomes impossible, or has to fall back on
  inference.
- **LOW**: hygiene, or a gap that config already makes recoverable.

---

## Findings, ranked

### H1. Recorded tool evidence is overwritten in place when a run key is reused

- **Stored now:**
  - `qa.check_result`: `record_results()` DELETEs by (run_key, tool, scope, supply_state) and then
    inserts (`qa_store.py:1806-1821`; the docstring says "REPLACES ... so re-running one tool is
    idempotent").
  - `qa.tool_output`: `record_tool_output()` uses `ON CONFLICT ... DO UPDATE SET raw_output`
    (`qa_store.py:1884-1891`).
  - `qa.dataset_stats` and `qa.tables_read` are also upserts, and `asked_check` is delete-then-insert
    (`qa_store.py:1982`).
  - `qa.run`: `record_run()` overwrites `run_timestamp`/`run_instant` on conflict
    (`qa_store.py:1749-1752`).
  - `open_run()` reopens a finished run (`qa_results_writer.py:638`).
  - `cli/debug.py`'s own docstring (lines 14-23) says that `mothman debug run-*` against an
    existing run "OVERWRITES" its recorded result.
- **Missing:** the previous verdicts and raw output, plus any marker that a replacement happened.
  Pipeline re-runs do take fresh keys (`__r1`, `__r2`; 12 `full` and 10 `readers` runs in the db),
  so the ordinary path is fine. But the arrival run key is deterministic (`<table>__<arrival key>`),
  so any re-execution of an arrival run (debug, a manual `bdm qa` on the same arrival, a crash
  retry) silently replaces recorded facts.
- **What it would break:** REQ-PIPE-168 treats verdicts as recorded facts. A promotion decision taken
  on run X's verdicts can later point at a run X whose verdicts are different. Nothing errors, and
  `promoted_status` no longer matches the results it claims to summarise.
- **Severity: HIGH.**
- **Cheapest fix:** make `check_result`/`tool_output`/`dataset_stats` append-only, keyed by an
  attempt number on the run (`run_attempt` int, or a `qa.run_attempt` child). Alternatively, refuse
  a write to a completed run unless a new key is minted. The rest of the schema already follows this
  pattern (`decision`, `filing`, `verdict` are append-only); these tables are the exception.

### H2. No bytes-level identity for a delivered file (checksum, size, storage version)

- **Stored now:** `qa.delivery_file` holds delivery, filename, dataset_id, contested_by, receipt
  text/instant/clock, receipt_sequence, stated original, and `storage_uri`
  (`delivery_log.py:91-200`). `qa.load_outcome` holds `row_count`. For S3, `receipt_of()` reads
  `head_object` but keeps only `LastModified` (`s3_arrival.py:72-80`).
- **Missing:**
  - a content hash (sha256);
  - byte size;
  - S3 `ETag` and `VersionId`, and `ContentLength`;
  - the header line and column count. The file check records the finding "the first line is a header
    naming the columns" but not the header itself (`check_result.extra.finding`).

  No `hashlib`/size call exists anywhere in the arrival path.
- **What it would break:**
  - It can't be shown later which bytes were judged. With `storage_uri = local:<delivery>/<file>`,
    an overwritten S3 key or a re-copied file silently points somewhere else.
  - "This resupply is byte-identical to the last one" (duplicate detection) can't be computed for
    history.
  - A header-drift check (columns renamed or reordered between supplies) can't be computed for
    history.
  - The PoC re-loads an arrival by REPLACING its table (`supply_db.load_csv_into`, docstring), and
    nothing proves the re-load read the same bytes.
- **Privacy:** safe. A hash, a size and column NAMES are not personal data.
- **Severity: HIGH** for a real asset, where the file is the only full-fidelity evidence (see M5).
- **Cheapest fix:** at receipt, add `sha256`, `size_bytes`, `storage_version` (S3 VersionId or ETag)
  and `header text[]` columns to `delivery_file`, written once.

### H3. No code version, and tool versions are never filled in

- **Stored now:**
  - `qa.run.tool_versions jsonb NOT NULL DEFAULT '{}'`, which is **`{}` on all 229 runs**. No caller
    passes it (`record_run` callers: `qa_results_writer.py:582,629`, `asked_for.py:94`).
  - `check_result.engine` is a hard-coded string constant, e.g.
    `ENGINE_TAG = "dbt-core 1.12 + dbt-postgres"` (`dbt_common.py:25`), "Soda Core 3.5" and
    "Evidently 0.7". It is a claim made by code, not a measurement.
  - Incidental versions survive inside raw output: dbt `metadata.dbt_version` 1.12.4 and
    datacontract `datacontractCliVersion` 1.2.0. **Soda and Evidently record no version at all.**
  - No git SHA of mothman is recorded on any run, verdict, filing or decision.
- **What it would break:**
  - Root-causing "status flipped between these two runs": the open dbt nondeterminism (item 38), a
    Soda or Evidently PSI binning change, or a status-rollup code change (item 74's nullable
    thresholds).
  - The schema-bumps analysis already says `promoted_status` and verdict-like values must "name the
    code and config version that computed it". Today no version is available to name.
  - A migration that needs to know "which rows were judged by the old rule" (v26's refile
    reinterpretation) has to guess from dates.
- **Severity: HIGH.** This is cheap, and every later derivation question gets harder without it.
- **Cheapest fix:**
  - In `open_run`, record `{"mothman": <git sha + dirty flag>, "dbt-core", "dbt-postgres",
    "dbt_utils", "soda-core", "datacontract-cli", "evidently", "duckdb", "python"}` from
    `importlib.metadata` into `run.tool_versions`.
  - Add a `code_version` text column on `decision`, `filing`, `verdict` and `hold`.
  - Derive `engine` from the measured version rather than a constant.

### M1. A verdict's inputs omit the receipt instant it was judged on

- **Stored now:** `qa.verdict.inputs` records the full agreement (due_at, late_after, claim window,
  grace, timezone, expected_time) plus a fingerprint (`verdict.py:80-120`). That is good. But
  `judge(dataset_id, slot, received_at, ...)` uses `received_at` and doesn't record it
  (`verdict.py:123-142`).
- **What's missing, and why it matters:** the instant comes from the `qa.supply_receipt` VIEW.
  Version 40 already changed which file's receipt that view prefers (the settled file), so the
  basis of a historical verdict can move without the verdict changing.
- **What it would break:** a REQ-PIPE-173-style backstop ("is this verdict still what its inputs
  say?") can't be re-run for history. It would compare against today's view, not the instant
  actually judged.
- **Severity: MED** (borderline HIGH, since the view has already changed once).
- **Cheapest fix:** add `received_at` (text with its offset), `received_from` and the receipt's
  `(delivery, filename)` to `verdict.inputs`.

### M2. A promotion doesn't record which run's results it stood on

- **Stored now:** `qa.decision` for `promote` holds `promoted_status` (green/amber), the amber
  setting/level/version where relevant, and reason prose (`promotion.py:108-115`). There is no
  `run_key` and no `stands_on`-style link to the results.
- **What it would break:** "show me the check results this promotion was decided on" can only be
  answered by inference: the `supply_current_run` view as at `effective_at`. That view has been
  redefined twice (v31, v32) and is defeated by H1. Re-auditing a promotion after a status-rollup
  change can't be done precisely.
- **Severity: MED.**
- **Cheapest fix:**
  - Add a `decided_on_run` text column (and, for rule promotions, the counts by status of the
    contributing checks, or a hash of their ids and statuses).
  - Record the same on `acknowledge` and `still-failing`. An acknowledgement today says "this was
    fine" without saying which run's ambers it was acknowledging.

### M3. A person's decision doesn't record what they were shown, or where the instruction came from

- **Stored now:** `filing_decisions.Consequences` builds the warning lines and a sha1 `key`. The
  person must quote it back (`filing_decisions.py:195-205, 1051-1058`). `Request.acknowledged`
  carries it, but **neither the lines nor the key is written to `qa.decision`** (no column; grep of
  `decision_log.py` finds nothing). On the GitHub route, `Comment` has body, author and slot_key
  (`filing_from_github.py:79-92`), but the comment id/URL and the verbatim body are not recorded.
  Only the parsed `reason` survives.
- **What it would break:**
  - "Was the person warned this re-file would knock on to 2026-Q3?" can't be answered for history.
    An audit or a dispute on a real asset asks exactly that.
  - A GitHub comment can be edited or deleted, so the authorising instruction disappears.
  - If a consequences rule changes, there's no way to tell which past decisions were taken without
    that warning.
- **Severity: MED** (HIGH if Keith treats the decision log as an audit trail for accountability).
- **Cheapest fix:**
  - Add `shown text[]` (the consequence lines) plus `shown_key` on `decision`.
  - Add `instruction_ref` (comment URL/id or `terminal`) plus `instruction_text` (the verbatim
    comment).
  - This is not personal supply data; it is operator text.

### M4. A check's definition is not pinned to each result

- **Stored now:**
  - `check_result` has `check_id`, `check_name`, `warn_threshold`/`fail_threshold` (two scalars) and
    `engine`.
  - `check_lifecycle.py` already computes a per-check **config hash** (thresholds, values, logic)
    for its CI gate, but the hash is never stored with a result.
  - What does survive, in `tool_output`:
    - dbt `results[].compiled_code` and `unique_id`;
    - the full SodaCL `definition` text and the executed `queries[].sql`;
    - datacontract `checks[].implementation` SQL.

    That is real raw evidence, and it is good.
  - What doesn't survive:
    - (a) the **link** from a `check_result` row to its tool-native id. dbt `unique_id` maps to
      `check_id` only through the manifest's `meta`, and the manifest is deleted with the dbt target
      dir (`orchestrate_bdm.py:318-348`).
    - (b) the two-scalar threshold columns can't hold a band. Soda `row_count` "fail when < 100 when
      > 20000" is stored as fail_threshold=100, and the upper bound is gone from the structured
      columns. 5,445 of 13,070 results have no threshold at all.
    - (c) Evidently stores a metric config, but not the contract or check definition.
- **What it would break:**
  - "Which results were produced under the old accepted-values list?" (a definition-change cut-over
    on the dashboard) needs either a git-history walk by date (config is mutable in git) or text
    matching of compiled SQL.
  - Re-banding history from structured columns is impossible for banded checks.
- **Severity: MED.**
- **Cheapest fix:**
  - Store `config_hash` (from `check_lifecycle`) on every `check_result`. It is one column and the
    hash already exists.
  - Store the tool-native id (`dbt unique_id`, Soda check identity, datacontract check id) in a real
    column.
  - Keep the dbt `manifest.json` node for each executed test (config, meta, depends_on, raw_code)
    in `tool_output` before the target dir is removed. A small subset is enough; don't keep the
    whole manifest.

### M5. Staged supply rows are a lossy derivation of the file, and the file's long-term home is undefined

- **Stored now:** BDM/CP loaders read the CSV with pandas (explicit nulls), re-write it as a scratch
  CSV, then DuckDB `read_csv_auto` **infers types** and the rows are COPYed into PostgreSQL
  (`build_per_run_warehouses.py:118-133`, `supply_db.py:655-700`). Rejected supplies keep their
  rows in `rejected` (7 tables), and superseded ones in `<period>_superseded`. That part is good.
  But:
  - (a) inferred types change the cell text. Leading zeros in an integer-inferred code (e.g. NT
    postcodes "0800") are lost, and date formats are normalised. The inferred column types are not
    recorded in qa.
  - (b) a file refused by the file checks, or one that failed to load, has its table dropped
    (`file_checks.py:472`, the loader's except path). Its only evidence is the file under
    `data/deliveries/` (gitignored and local) or wherever `storage_uri` points.
  - (c) no retention rule or production location exists for delivered files. `storage_uri` is
    `local:` in the PoC.
- **What it would break:** a new check on raw cell text (e.g. "postcode must be 4 characters
  including a leading zero", or "dates must be ISO in the file") can't be evaluated against history
  from staged rows. Neither can re-staging after a loader bug fix if the file isn't kept.
- **Privacy:** the raw file is personal data and must not go into `qa`. The safe options:
  - keep the file in the supply side (an S3 bucket with versioning and a retention policy, which is
    the natural production home);
  - record its hash/size/version in `qa` (H2);
  - record the inferred schema (column name to type) per load in `qa.load_outcome`. Names and types
    are not personal data.
- **Severity: MED** (HIGH if production storage turns out not to retain files).
- **Cheapest fix:** add `columns jsonb` (name, inferred type) to `load_outcome`, and write a
  decision for Keith on file retention: where, how long, and versioned or not.

### M6. Too little distribution is recorded to compute a new drift metric without the rows

- **Stored now:** `qa.dataset_stats.stats` holds row_counts per table, `value_counts` for **one
  column per collection only** (BDM `sex`, CP `concern_type`; `bdm/dataset_stats.py:82,198`),
  invalid-value aggregates for three spec'd columns, and the earliest extract. Evidently
  `tool_output` stores only the PSI/RowCount metric snapshots, not the report's distributions.
  `drift_reference.py` rebuilds the reference from those recorded value counts. That design is
  right, and has been proven bit-identical.
- **What it would break:** "add PSI drift on place_of_birth_suburb / placement_type / risk_rating
  and backfill its trend" has no reference distribution for any earlier supply. Neither does "add a
  numeric drift (date_of_birth age distribution)". It needs rows, which a build may never read and
  which may be gone for superseded or rejected supplies.
- **Privacy:** value counts of closed-set categorical columns and binned histograms of numeric/date
  columns are aggregates, but small cells in CP can be identifying. Apply the existing `suppressed`
  mechanism (small-cell suppression) and exclude `classification: pii` columns.
- **Severity: MED.**
- **Cheapest fix:** in `dataset_stats`, record value counts for **every** closed-value-set column
  the contract declares (`validValues`/`accepted_values`) and a fixed-bin histogram (plus null
  count, min and max) for every date/numeric column. Suppress small cells and skip PII-classified
  columns.

### L1. Supplier timestamps are given an assumed offset with no marker that it was assumed

- `asset_time.record_source_instant()` attaches `SOURCE_TIMESTAMP_OFFSET` to naive supplier values
  (`asset_time.py:325-347`). `dataset_stats.arrival.earliest_extract` then reads e.g.
  `"2023-02-01T01:00:00+00:00"`, as though the supplier stated +00:00. The CSVs are naive
  (`extract_timestamp` = `2023-05-01 07:00:00`).
- **Fix:** store the original text alongside, or add `"offset_assumed": true`.
- **Severity: LOW** (the rows still hold the naive value).

### L2. Our own instants are timestamptz-only

`decision.effective_at`/`recorded_at`, `filing.recorded_at`, `verdict.recorded_at`,
`hold.raised_at`, `period.opened_at`, `census.taken_at`, `owed_run.*_at` and `correction_*.*_at`
store an instant only. This is the v4 loss class. It is LOW because these are our clock, and the
asset timezone is an effective-dated config with frozen past versions, so the local reading is
recoverable. `qa.delivery`, `delivery_file`, `run.run_timestamp` and `load_outcome.recorded_at`
already keep the text with its offset. Only worth fixing where the rendered local time is
legally meaningful (decision `effective_at`).

### L3. Which recognition rule attributed a file isn't recorded

`delivery_file.dataset_id` and `contested_by` are recorded, but not the arrival pattern (or its
version) that matched. If `arrival_patterns` change, "why was this file attributed to cp-carers?"
can't be answered. **Fix:** add `matched_pattern text` on `delivery_file`. **LOW.**

### L4. Defaults that claim a fact, and schemaless jsonb (rule-1 and rule-11 smells)

- **Defaults that claim a fact:**
  - `delivery.filed_by_kind DEFAULT 'automated'` (already in the analysis). The writer also falls
    back to `{"kind": "automated"}` when the delivery doesn't say (`delivery_log.py`, payload
    `filed_by`).
  - `run.scope DEFAULT 'arrival'`.
  - `check_result.supply_state DEFAULT 'agreed'` and `scope DEFAULT <dataset>`.
  - `run.tool_versions DEFAULT '{}'` (honest, but hides H3).
  - `check_result.engine` constants (H3).
- **jsonb with no recorded shape or version:** `dataset_stats.stats`, `hold.reason`,
  `delivery.anomalies`, `correction_applied.summary` and `check_result.extra` (11 different keys
  across tools).
- **Fix:** add a `"shape": n` key inside each jsonb document the PoC authors (not the tools' native
  output), so a future reader knows which writer version produced it.
- **Severity: LOW.**

---

## The finding that runs the other way: supply-row values already in `qa`

This doesn't need more capture. It needs Keith's eyes, because the rule "a build reads recorded QA
results, never supply rows" assumes `qa` holds no supply rows, and it does hold some.

- **`tool_output` (datacontract) `checks[].failed_samples`** is populated on **285 checks**. It
  carries row values for 27 distinct columns, including `registration_number`, `cp_client_id`,
  `date_of_birth`, `postcode`, `suburb`, `sex`, `placement_id` and `notification_id`. The source is
  `include_failed_samples=True` (`datacontract_common.py:134`).
- **`check_result.extra.failing_sample_keys`** holds up to five primary keys per failing check
  (~11k rows across dbt, Soda and datacontract). These are registration numbers (BDM-xxxxxxxxx) and
  client ids.
- **`dataset_stats.check_aggregates`** holds distinct invalid values with counts (invalid DOBs,
  suburbs, postcodes).

These were deliberate (plans/qa-pipeline.md items 15-17 settled sample keys and PII-classified-column
exclusion with Keith on 2026-09-14). But the publisher role is granted SELECT on **all** of `qa`
(`qa_store.py:1649-1652`), so the dashboard build can read identifiers and quasi-identifiers
(DOB + postcode + client id). On a real Child Protection asset that is personal data in the metadata
schema.

Privacy-safe alternatives:
- keep the keys/samples in a supply-side schema (e.g. `qa_samples`, not granted to the publisher);
- or store salted hashes of the keys;
- or strip `failed_samples` from `raw_output` before recording and keep only the counts.

Whatever the decision, the raw-evidence additions proposed below should be checked against the same
rule. None of them copies row values.

---

## Already well captured (the good news)

- **Raw tool output is genuinely kept:**
  - dbt `run_results.json` with `compiled_code` per test;
  - the complete Soda scan results, including each check's SodaCL `definition` text and every
    executed `queries[].sql`;
  - the complete datacontract-cli run, including `implementation` SQL, `dataContractVersion` and
    the CLI version.

  So "what SQL actually ran" is answerable for 3 of 4 tools, for every run (213 each).
- **`verified` records alongside the raw output.** These are the corrected counts from the dbt audit
  re-query and the Soda row_count query, so the known dbt `failures=0` bug doesn't contaminate
  history.
- **Arrival verdicts carry their agreement.** `qa.verdict.inputs` plus `fingerprint` record the
  due/late/claim-window/timezone values that judged them. They are append-only, with corrections
  appended rather than overwritten (213 of 221 have inputs; the other 8 are `unfiled`, correctly
  null).
- **Receipts keep text plus offset plus clock:** `delivery.received_at` text,
  `received_from` (`storage` vs `our-clock`), per-file receipts with `receipt_sequence`, the
  supplier's stated original arrival as text plus instant, and `run.run_timestamp` as text. The v4
  lesson has been applied everywhere it was caught.
- **The inputs of the assignment rule are recorded:** `filing.considered` and `filing.branch`, plus
  `hold.reason.considered` and `unavailable`, with the reason each slot was unavailable.
- **Configuration settings are recorded on the decision, not re-read later:** `amber_setting`,
  `amber_level` and `amber_version`, `replacement_*`, and `promoted_status` "fixed when taken".
  Calendars, participation, timezone, amber and replacement settings are effective-dated and frozen
  once past.
- **What each tool was asked to evaluate:** `asked_tool`/`asked_check`, which deliberately says
  "not recorded" for history.
- **Provenance of re-runs:** `run.scope`, `caused_by_decision`/`caused_by_load`, `qa.owed_run` with
  attempts and failures, and `tables_read` with the supply a period table held when it was read.
- **Supply rows of rejected and superseded supplies are retained** in `rejected` and
  `<period>_superseded`, rather than dropped.
- **Drift references are rebuilt from recorded counts, not from rows.** This was proven
  bit-identical, so the design for M6 already exists. It only needs more columns.
- **Append-only discipline** on `decision`, `filing`, `verdict`, `correction_*` and
  `decision_file`.

---

## Proposed short list to start capturing now (cheapest first, all privacy-safe)

1. **`run.tool_versions` actually filled**, plus the mothman git SHA and dirty flag, from
   `importlib.metadata` in `open_run`. Add `code_version` to decision, filing, verdict and hold.
   (H3; one function, no schema change for the run.)
2. **File identity at receipt:** `sha256`, `size_bytes`, `storage_version` (S3 VersionId/ETag) and
   `header text[]` on `delivery_file`; inferred `columns jsonb` on `load_outcome`. (H2, M5)
3. **Stop overwriting run evidence:** append an attempt (or refuse writes to a completed run key)
   for `check_result`, `tool_output`, `dataset_stats`, `tables_read` and `asked_check`. (H1)
4. **`verdict.inputs` gains the receipt instant (text + clock + file) it judged.** (M1, one dict
   entry)
5. **`config_hash` and tool-native check id on every `check_result`.** Keep the dbt manifest node
   subset for each executed test before the target dir is deleted. (M4)
6. **Promotion/acknowledge decisions record `decided_on_run`.** Person decisions record the
   `shown` consequence lines and key, plus `instruction_ref`/`instruction_text` for GitHub
   comments. (M2, M3)
7. **`dataset_stats` records value counts for every closed-set column and histograms for every
   date/numeric column**, with small-cell suppression and PII exclusion. (M6)
8. **A decision for Keith (not a build):** where delivered files live and for how long in
   production, and whether `failed_samples`, `failing_sample_keys` and invalid-value aggregates
   should stay readable by the publisher role.

Items 1, 2 and 4 are additive columns or values whose NULL honestly means "not recorded at the
time". That is the safe class in the schema-bumps analysis, so they can start today without
touching history.
