# Python-Based Data Contract Engines — Landscape Survey

*Scope: open-source, self-hostable tools only. Written for a greenfield stack (no orchestrator/warehouse locked in yet), in the context of a PoC for end-to-end pipelines operating population-scale, multi-agency government data.*

## The one distinction that matters most

Across this landscape, tools split cleanly into two groups, and it's easy to buy the wrong one:

- **Documentation-only tools**: they let you write down a contract (schema, quality rules, SLAs) in a structured format, but something else has to actually run the check. Publishing a contract here is "an honor system with a search interface" — useful for governance and discoverability, but nothing stops bad data from flowing if no one wires up the check.
- **Runtime enforcers**: something concrete happens on violation — a CI job fails, a build breaks, a record gets routed to a dead-letter queue, a pipeline halts — independent of whether the producer remembered to comply.

For a multi-agency government context, this distinction matters more than usual: contracts here are effectively the technical expression of a data-sharing agreement between agencies, and a data-sharing agreement that nobody enforces isn't worth much. The shortlist below is organized around this split.

## Category A — Contract-standard / definition layer

### datacontract-cli (Data Contract CLI)
- **License**: MIT. Python CLI + library.
- **Standard**: implements the **Open Data Contract Standard (ODCS)**, governed by **Bitol**, a Linux Foundation AI & Data project (Apache 2.0, Technical Steering Committee). Also backward-compatible with the older Data Contract Specification.
- **What it does**: contracts are written as YAML covering schema, data types, quality rules, SLAs, ownership/stakeholders, and governance metadata (security classification, pricing, etc.) — exactly the shape of metadata a cross-agency data-sharing agreement needs. The CLI then:
  - **Lints** contracts against the ODCS JSON Schema
  - **Tests** real data against the contract by generating and running checks via other engines — it compiles ODCS into dbt tests, SodaCL checks, or Great Expectations suites
  - **Imports/exports** 25+ formats (SQL DDL, dbt, Avro, JSON Schema, Protobuf) and connects to 15+ data sources (Snowflake, BigQuery, Databricks, Postgres, MySQL, SQL Server, etc.)
- **Enforcement model**: genuine — because it drives a real validation engine underneath and is typically run as a CI gate, a violating dataset fails the build before it reaches consumers.
- **Best fit**: the contract *definition and standard* layer — the artifact that agencies actually sign off on — paired with a validation engine to execute it.

### dbt model contracts
- **License**: dbt Core is open source (Apache 2.0); contracts work in both dbt Core and dbt Cloud.
- **What it enforces**: column names, data types, and (platform-dependent) constraints (`not_null`, `unique`, `primary_key`, `foreign_key`, `check`) on a model's output shape — not the data's content.
- **Mechanics**: declared via `contract: enforced: true` in YAML; dbt runs a pre-flight check before build, and the model **fails to build** if the query doesn't match — including on breaking changes (dropped/renamed columns, changed types).
- **Limitations**: SQL models only (no Python models), no support for `ephemeral`/custom materializations, sources, seeds or snapshots; constraint enforcement varies a lot by warehouse (many only actually enforce `not_null`).
- **Best fit**: strong, real enforcement if the pipeline is dbt-centric — but it's a shape/schema contract only, not a general quality or SLA contract, and it only guards the transformation layer, not ingestion.

## Category B — Validation / quality engines (what actually executes the checks)

### Great Expectations — GX Core
- **License**: open source (Apache 2.0), self-hosted; GX Cloud is a separate commercial offering.
- **Model**: "Expectations" (assertions about data, from a large pre-built gallery) grouped into Suites, run via Checkpoints against Data Sources/Assets, producing human-readable Data Docs.
- **Fit**: the most mature and widest-adopted Python data-quality framework; good expectation coverage, good CI integration, works well as the enforcement engine behind an ODCS contract.

### Soda Core (Soda v3)
- **License**: open source library + CLI; Soda Library/Soda Cloud (cloud connectivity, advanced features) is the paid tier.
- **Model**: checks defined in **SodaCL**, a declarative check language that compiles to SQL, run against 18+ data sources.
- **Fit**: lighter-weight than GX for warehouse-side SQL checks; also a common compile target for datacontract-cli.

### Pandera
- **License**: MIT, maintained with support from Union.ai.
- **Model**: dataframe schema validation with two APIs — object-based (`DataFrameSchema`) and class-based/pydantic-style (`DataFrameModel`). Runs in-process, decorator-friendly.
- **Backends**: pandas (primary), Polars, PySpark, Dask, Modin, Ibis, PyArrow, GeoPandas (via a Narwhals-powered layer).
- **Fit**: best when contracts need to be enforced *inside application/pipeline code* (e.g., a Python transform step) rather than against a warehouse table — complements GX/Soda rather than replacing them.

### PyDeequ (AWS Labs)
- **License**: Apache 2.0. Python API over the JVM library **Deequ**.
- **Model**: "unit tests for data" on top of Apache Spark — constraint suggestion, anomaly detection, incremental metrics computation at scale.
- **Fit**: relevant only if the pipeline is Spark-based; heavier operationally (JVM dependency) than the others, but built for genuinely large (population-scale) datasets.

### Frictionless Framework
- **License**: MIT.
- **Model**: describe/extract/validate/transform tabular data against the **Frictionless Data** standards (Data Package, Table Schema). Broad format/scheme support (CSV, XLS, JSON, SQL, HTTP/FTP/S3), low memory footprint.
- **Fit**: less focused on "contracts between teams" and more a general tabular-data toolkit; worth knowing about but not a strong fit as the primary contract engine here.

## Category C — Governance/catalog layers (observe, not enforce)

### DataHub (OSS)
- **License**: Apache 2.0 (DataHub Core); DataHub Cloud/Acryl Observe is the commercial layer.
- **Contracts**: YAML-defined, assertion-based, tied to catalogued assets; can ingest ODCS directly.
- **Reality check**: self-hosted DataHub **stores and displays** contract compliance — it does not run the checks itself. You still need an external engine (GX, Soda, dbt tests) to produce the assertion results it displays. Good for cross-agency visibility/catalog, not enforcement.

### OpenMetadata
- **License**: Apache 2.0.
- **Contracts**: as of 1.9+, can run **scheduled validations and schema checks as part of the catalog itself** — one of the few catalog tools that crosses from documentation into actual enforcement, per third-party analysis.
- **Fit**: worth a closer look if a shared, multi-agency data catalog is part of the PoC's scope (it likely should be, given "population-scale, multi-agency" framing) — it can double as both the catalog and a validation runner.

## Comparison table

| Tool | License | Layer | Enforces at runtime? | Backend / scale | Maturity |
|---|---|---|---|---|---|
| datacontract-cli | MIT | Contract definition (ODCS) | Yes, via compiled checks + CI gate | Warehouse/DB agnostic (15+ sources) | Growing, active |
| dbt model contracts | Apache 2.0 | Contract definition (schema shape) | Yes, build fails on violation | SQL models only | Mature (dbt-native) |
| Great Expectations (GX Core) | Apache 2.0 | Validation engine | Yes | Pandas/SQL/Spark data sources | Mature, widest adoption |
| Soda Core | Open core | Validation engine | Yes | 18+ SQL data sources | Mature |
| Pandera | MIT | Validation engine (in-process) | Yes | pandas/Polars/PySpark/Dask/etc. | Mature |
| PyDeequ | Apache 2.0 | Validation engine | Yes | Spark only | Mature, ops-heavy (JVM) |
| Frictionless | MIT | Tabular data toolkit | Yes (local) | CSV/JSON/SQL/etc. | Active, narrower scope |
| DataHub (self-hosted) | Apache 2.0 | Catalog/governance | No — observation only | N/A | Mature catalog, immature enforcement |
| OpenMetadata | Apache 2.0 | Catalog/governance | Partial (1.9+) | N/A | Mature catalog, newer enforcement |

## Recommendation for the PoC

Given a greenfield, self-hostable, OSS-only constraint, a workable composition rather than a single tool:

1. **Contract definition layer: ODCS via datacontract-cli.** It's the closest thing to a real open standard for this problem, it's built specifically around the producer/consumer/governance metadata shape a multi-agency data-sharing agreement needs (ownership, classification, SLAs), and it's designed to *drive* enforcement rather than just describe it.
2. **Enforcement layer: Great Expectations (or Soda Core) as the executing engine**, invoked by datacontract-cli's test command and run as a CI/pipeline gate — this is what turns a YAML promise into something that actually blocks bad data. Add Pandera at the in-process/application layer if transforms are written as Python rather than SQL.
3. **If the transform layer ends up dbt-centric**, layer dbt model contracts on top for the transformation boundary specifically — cheap to adopt, genuinely enforced, but not a substitute for #1/#2 since it only covers shape, not quality/SLA.
4. **Catalog/visibility layer (second phase, not needed for the PoC's first cut): OpenMetadata** over DataHub, specifically because of its move toward native enforcement rather than pure observation — likely relevant once multiple agencies need a shared place to see contract status, not just engineering.

This composition keeps every layer independently open-source and self-hostable, doesn't lock in an orchestrator or warehouse, and treats "enforcement" as a first-class requirement rather than an assumption — which seems like the right posture before this becomes something agencies actually rely on.

*Scope note: a shared multi-agency catalog (the OpenMetadata/DataHub layer above) is explicitly out of scope for the PoC's first cut — a later-phase concern once contract definition and enforcement are proven out.*

## Worked example: BDM birth registrations

The rest of this report has been tool-first. This section is data-first: one real feed, run through the recommended stack, to check the recommendation actually holds up against a case we know.

### The feed, as it exists today

The Registry of Births, Deaths and Marriages (BDM) supplies birth registration records to the central multi-agency data asset, which downstream agencies use for identity and eligibility matching. Today that supply is:

- **Format**: CSV, dumped in full or incrementally
- **Transport**: a file drop into an S3 bucket — no direct source connection
- **Planned**: a move to Parquet, and eventually pulling directly from source (BDM's source systems are Postgres/MySQL/SQL Server/Snowflake-shaped, so a direct connection is realistic once BDM can support it)

None of this is currently backed by a contract — the central asset just reads whatever lands in the bucket.

### Failure modes this needs to catch

These are the recurring, named problems with this kind of feed, not hypothetical ones:

| Failure mode | Caught by | How |
|---|---|---|
| **Data drift** (a file silently doubled, truncated, or otherwise structurally "fine" but wrong) | Row-count sanity band, at the CI gate | A schema check alone passes a duplicated file — only a volume/quality rule catches it |
| **Null rate creeping up** | Per-column completeness thresholds | Each field gets a threshold matched to what's *actually* normal for it (a birth record with no facility name is normal; one with no date of birth is not) — a single blanket "not null" rule can't express that distinction |
| **Column renamed** | Required-field + schema checks | A rename looks like "a required column vanished" to the contract — the same mechanism dbt model contracts use, just applied earlier, at ingestion rather than only at the transform layer |
| **Type changes** | `logicalType`/`physicalType` + validity rules per column | E.g. a date arriving as a timestamp-with-timezone, or an ID field's format changing upstream — the regex/date-range rules below are written specifically to catch this rather than a generic "is it a string" check |

### The contract

A full ODCS contract for this feed is in [`bdm-birth-registrations-contract.yaml`](bdm-birth-registrations-contract.yaml) (sent alongside this report). Highlights:

- **Schema**: 13 columns, matching a plausible BDM birth-registration extract (registration number, child name, DOB, sex, place of birth, registering parent(s), multiple-birth flag, source/extract metadata).
- **Completeness rules tuned per column**, not blanket — `registration_number` and `date_of_birth` must be 100% populated (`mustBe: 0` on the null check); `registering_parent_2_name` tolerates up to 30% null, because single-parent registrations are legitimately common and treating that as an error would just train everyone to ignore the alerts.
- **A regex on `registration_number`** (`^BDM-[0-9]{9}$`) — this is the concrete defence against an upstream ID-format change reaching consumers as silent garbage instead of a loud, specific failure.
- **A row-count sanity band** (500–20,000/day) at the table level — the one rule in the contract that exists purely to catch data drift a schema check is structurally blind to.
- **SLA properties** for delivery frequency (daily) and latency (24h) — turning "it usually arrives by morning" into something a contract can actually assert.
- **`customProperties`** flagging the current CSV format, the planned Parquet move, and the eventual direct-source candidates — so the format migration is a tracked, versioned change to the contract rather than a hopeful swap nobody wrote down.

It hasn't been run through `datacontract-cli lint` in this environment — pip isn't reachable here (see the tts-repo README from earlier in this thread for why) — so treat it as a structurally-faithful draft to lint yourself once you have datacontract-cli installed, not a verified-passing contract.

### What actually happens on a violation

This is illustrative, not a captured run (same pip constraint), but it's what `datacontract-cli test` is built to produce when, say, BDM's source system renames `date_of_birth` to `dob` without warning:

```
$ datacontract test bdm-birth-registrations-contract.yaml

Testing birth_registrations...
  ✗ required column 'date_of_birth' not found in source
  ✗ quality rule 'validDateRange' skipped: column missing
  ✓ registration_number: nullCheck passed (0.0% null)
  ✓ registration_number: regexPattern passed
  ...

1 of 14 checks failed. Contract violated.
```

That failure happens at the CI gate, before the renamed column reaches the central asset — which is the entire point of choosing an enforcing stack over a documentation-only one back in the first section of this report.

### Traffic-light thresholds, and quarantine vs. block

A flat pass/fail per check isn't quite enough in practice: a check should often distinguish "this is worth flagging" (amber) from "this is bad enough to act on" (red), and separately, what happens on red shouldn't always be the same — sometimes the right move is to hold back the specific bad rows and let everything else through, sometimes it's to stop the whole run. Both turned out to be real capabilities already sitting in the recommended stack, not something requiring a new tool — but neither is a single checkbox, and they don't live in the same place.

**Two-tier (warn/fail) thresholds.** ODCS itself only has one operator plus a flat `severity` label per rule — no built-in second threshold. Great Expectations is the same: `mostly` is a single threshold per Expectation. Soda Core and dbt tests both do support this natively, though:

- **Soda Core** (`bdm-birth-registrations-soda-checks.yml`, sent alongside this): a check gets separate `warn:`/`fail:` blocks, e.g. `sex`'s invalid-value rate warns above 0% and fails above 2%. The same file also shows the third threshold shape you asked about — "proportion of records *since a certain date*" — using a SodaCL `filter` to scope a check to only the last 24 hours, so a fresh drift is caught fast instead of being diluted by months of clean history in the same table.
- **dbt tests** get the same two-tier behavior via `severity` plus `warn_if`/`error_if`.

Net effect: red/amber/green thresholds live at the Soda/dbt level, with the ODCS contract documenting the intent (as it already does via `severity: warning` vs `severity: error` on separate rule objects) rather than being the literal enforcement mechanism for the two-tier logic.

**Quarantine vs. block, on red.** This isn't a setting — it's a question of *where in the pipeline the check runs*:

- **Block the run** is just the existing CI-gate pattern: a check fails, `datacontract-cli test`/a GX Checkpoint/`dbt build` exits non-zero, nothing downstream gets promoted. Already covered above.
- **Quarantine** — valid rows proceed, invalid rows get routed to a dead-letter table instead — only works if the check runs *before* the load, at the row level. `quarantine_sex_column.py` (sent alongside this) demonstrates this against `sex`: it splits an incoming batch into valid/invalid subsets, applies the same red/amber/green logic as the Soda file, and shows both `on_fail` policies side by side — quarantine-and-continue vs. abort-and-load-nothing — as a per-check, configurable choice rather than a global one.

Worth being precise about a common misconception here: dbt's `store_failures` looks like quarantine but isn't — dbt tests run *after* the model has already built, so it copies failing rows to an audit table for visibility while those same rows are still sitting in the real table too. Genuine pre-load quarantine needs row-level output from something running before the write — Great Expectations' `unexpected_index_list` (or a Pandera boolean mask) is what that script is built on; the script itself uses a plain pandas mask (fully tested, since GX isn't pip-installable in this environment) with the equivalent GX 1.x call shown as commented reference code at the bottom, not executed here.

### Why this doesn't change the recommendation

Running this feed through the stack didn't surface a reason to pick differently — if anything it sharpens the case for datacontract-cli + Great Expectations/Soda specifically: the completeness thresholds, regex validity check, and row-count band above are all things a file-drop pipeline needs on day one, and all things a documentation-only catalog (DataHub, OpenMetadata's older versions) would have left as an unenforced honor system.

## QA reporting layers

The checks above (Soda/GX/dbt) all produce the same kind of thing at the end of a run: a pass/fail (or red/amber/green) result per check, per column, per dataset. What's been missing so far is what happens to that result *after* the run — who sees it, at what altitude, and how far back they can look. That's a reporting layer on top of the QA pipeline, not a new QA engine, and it's worth designing deliberately because the three audiences who need it want genuinely different things from the same underlying results.

### Three tiers, three audiences

| Tier | Rolls up to | Audience | What they see |
|---|---|---|---|
| **Executive** | Agency | Executives, managers, directors | A single traffic-light status per agency — a "10,000-foot view" with none of the underlying detail |
| **Agency** | Data collection → dataset | Internal data teams *and* the agency's own data providers | Every data collection in the agency, each broken out into its datasets, each with a current status — framed as a real-time report, since data providers use this to check their own feed's standing |
| **Dataset** | Column | The individual data provider for that dataset (often one of several within an agency) | Full detail: SLA/arrival status, a dataset-level and column-level status summary, and a drill-down into every column's checks, current-vs-previous comparison, and complete run history |

The hierarchy is **Agency → Data Collection → Dataset → Column**, and it's strictly nested — every dataset belongs to exactly one collection, every collection to exactly one agency, matching how BDM's birth registrations feed sits under Registry Services' "Civil Registration" collection alongside death and marriage registrations.

### Rollup rule: worst-of

Each tier's status is the worst status among its children — any red anywhere below makes the parent red; failing that, any amber makes the parent amber; only when every child is green is the parent green. Concretely, for the birth registrations worked example: if `sex` and `place_of_birth_facility` are amber and the other eleven columns are green, the *dataset* is amber; if that's the worst thing happening anywhere in Registry Services' Civil Registration collection, the *collection* is amber, and so is the *agency*.

Worst-of is the only rollup rule that can't hide a real problem behind an average. An averaged or majority-vote rollup would let one red column disappear into a sea of green ones at the executive tier — exactly the silent-failure pattern this whole reporting layer exists to prevent. The tradeoff is that a large agency with many datasets will spend a lot of its calendar year showing amber or red at the top tier, simply because *something* is usually mid-incident somewhere underneath it; that's accurate, not noisy, but it does mean the executive tier needs to answer "what, specifically, is red?" in one click, not force a director to go hunting for it. The mockup below does that by making every tile a link straight down to the thing causing its color.

### The check-result record

Every tier above, plus the current-vs-previous comparison and the full historical trend, all read from the same shape of record — one per check, per run:

```
{
  agency_id, collection_id, dataset_id, column_name,   // where this result sits in the hierarchy
  check_name, dimension,                                // e.g. "Valid values (M, F, X)", "Validity"
  run_id, run_timestamp,                                 // which QA run this belongs to
  metric_value, unit,                                    // e.g. 0.82, "%"
  warn_threshold, fail_threshold,                        // the configured traffic-light thresholds
  status,                                                // green | amber | red, derived from the two lines above
  on_fail_action,                                        // "quarantine" | "block_run" (see previous section)
  row_count_total, row_count_invalid                     // enough to reconstruct "62 of 7,604 rows"
}
```

Everything the three tiers need falls out of this one record shape:

- **Rollups** (dataset/collection/agency status) are a `GROUP BY` + worst-of aggregation over the latest `run_id` per dataset — no separate rollup table to keep in sync, just a view over the same rows.
- **Current-vs-previous** is a self-join on the same `column_name`, comparing the two most recent `run_id`s.
- **Full historical trend** ("has this column been rock-solid or battling a lot") is every row for that `column_name` + `check_name`, ordered by `run_timestamp` — kept at full per-run granularity rather than rolled up into weekly/monthly aggregates, so a short-lived incident (like the six-day spike on `sex` in the worked example) stays visible as itself rather than getting smoothed into a monthly average that would hide it.
- **SLA/arrival status** is a sibling record at the dataset+run grain (arrived-by timestamp vs. the contract's `slaProperties`), not a column-level check — it answers "did the file show up," which is a precondition for every check below it even running.

This is also why the "traffic-light thresholds" section above matters to reporting, not just to enforcement: `warn_threshold`/`fail_threshold` need to travel with the result, not just live in the Soda/dbt config, because the dataset-tier drill-down has to show *why* a check is amber (current value vs. both thresholds), not just that it is.

### Companion artifact

An interactive mockup of all three tiers — built against this exact worked example (BDM Birth Registrations, all 13 contract columns, the `sex` and `place_of_birth_facility` traffic-light checks from the Soda file above) plus lighter synthetic data for four other agencies so the executive and agency tiers feel populated — was built alongside this report. It demonstrates the drill-down Executive → Agency → Dataset → Column, the worst-of rollup in practice (Registry Services sits amber because of `sex`/`place_of_birth_facility`; Transportation sits red because of a forced incident on `endorsement_codes`), the current-vs-previous comparison, and a full run-by-run trend chart (120 daily runs) per column, including a "view as table" fallback for the same data.

## Sources

- [What is Data Contract CLI?](https://docs.datacontract.com/)
- [Open Data Contract Standard | Data Contract CLI](https://docs.datacontract.com/open-data-contract-standard)
- [Bitol](https://bitol.io/)
- [PayPal data-contract-template](https://github.com/paypal/data-contract-template/)
- [GX Core overview | Great Expectations](https://docs.greatexpectations.io/docs/core/introduction/gx_overview/)
- [Soda Core (v3) | Documentation](https://docs.soda.io/soda-documentation/soda-v3/overview-main)
- [pandera documentation](https://pandera.readthedocs.io/)
- [PyDeequ · PyPI](https://pypi.org/project/pydeequ/)
- [GitHub - awslabs/deequ](https://github.com/awslabs/deequ)
- [Model contracts | dbt Developer Hub](https://docs.getdbt.com/docs/mesh/govern/model-contracts)
- [GitHub - frictionlessdata/frictionless-py](https://github.com/frictionlessdata/frictionless-py)
- [Most Data Contract Tools Don't Enforce Contracts: Here's What Does](https://zircote.com/blog/2026/04/most-data-contract-tools-dont-enforce-contracts/)
- [DataHub Data Contracts: A Quick Primer for 2026](https://atlan.com/datahub-data-contracts/)
- [Open Data Contract Standard | DataHub](https://docs.datahub.com/docs/generated/ingestion/sources/odcs)
