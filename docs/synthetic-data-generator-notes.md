# Synthetic data generator — design notes

A companion tool to this project's data-contract/QA-pipeline work: generates
population-scale, referentially-consistent fake data for internal testing,
built around four decisions made up front (see the "Synthetic data
generation" thread of this project's chat history for the full reasoning):

| Decision | Answer |
|---|---|
| First build target | A cross-agency identity scenario: **Child Protection Casework** |
| Identity linkage | A **shared synthetic population registry** every agency draws from |
| Target scale | **Several million+** (validated at 2.95M — WA's approximate real population) |
| Bad data | **Configurable failure injection**, tied to the checks already defined for this project |

The runnable code (a small git repo: `population.py`, `presentation.py`,
`child_protection.py`, `agency_datasets.py`, `dirty.py`, `generate.py`,
`reference/names_au.py`, plus a pre-generated sample) was delivered to the
user directly as `synthetic-data-generator.zip` — it isn't stored in this
project's docs (too large / not text), so if a future session needs the
actual source, ask the user to re-attach it rather than assuming it's
retrievable from here.

## Architecture

**`population.py`** — the master registry: one row per synthetic person
(`person_uid`, household, age, sex, name, one shared household address,
mortality, and a `has_child_protection_history` flag at ~2.2% of
children). Fully vectorized numpy/pandas — no per-person or per-household
Python loop — which is what makes population-scale generation fast (2.95M
people in ~17s). Household composition comes from 7 weighted templates
(single adult, couple, single-parent+N-children, couple+N-children) rather
than independent per-person sampling, so households/families are coherent.

**`presentation.py`** — projects one master identity into an
agency-specific "view": nickname substitution (~12%), an occasional
transcription-style typo (~3.5%), and a stable but agency-own reference
number (e.g. `BDM-######### `/ `CPS-#########` / `EDU-#########`, via a
seeded hash of `person_uid`). This is what makes the same fake person look
*slightly* different at each agency — deliberately separate from
`dirty.py`'s failure injection, since this models expected, healthy
cross-system variation, not a QA defect.

**`child_protection.py`** — the Child Protection Casework collection: 6
related tables with real FKs — `cp_clients` → `cp_notifications` →
`cp_investigations`, and `cp_clients` → `cp_placements` → `cp_carers`, plus
a small `cp_case_workers` staff pool. Categorical columns
(`concern_type`, `risk_rating`, `placement_type`, `source_type`) are closed
value sets — the same kind of column the QA pipeline's traffic-light
checks are built to watch.

**`agency_datasets.py`** — two more agencies' views of the same people:
`birth_registrations` for the *whole* population (same column shape as
`bdm-birth-registrations-contract.yaml`) and a lightweight
`school_enrollment` extract for the CP-flagged children — giving the
literal "one person, three agencies" demonstration the brief asked for.

**`dirty.py`** — generic failure-injection primitives (`inject_nulls`,
`inject_invalid_values`, `inject_missing_expected_value`,
`inject_duplicate_rows`, `inject_drift_batch`) plus two ready-made
presets tied to exact thresholds already defined elsewhere in this
project: `sex` invalid-code injection and `place_of_birth_facility`
null-creep match `bdm-birth-registrations-soda-checks.yml`'s warn/fail
lines exactly (0.8%/2.8% vs warn>0%/fail>2%; 20%/40% vs warn>15%/fail>35%);
`concern_type` gets unknown-code injection (`Unspecified`, `Pending
classification`, `Code 9`) — the "a new, unexpected value appeared in a
fixed value set" scenario from earlier in this project — plus
near-duplicate notification rows for uniqueness-check testing.

## Scale validation (measured, not estimated)

Ran end-to-end at 2,950,000 people (WA's approximate real population), one
core, no external services: population registry 16.8s, Child Protection
collection (6 tables) 0.2s, birth_registrations (2.95M rows) +
school_enrollment 25.1s, `--dirty amber` injection 1.8s — **~70s total,
~645MB CSV output**. Referential integrity (every FK across all 6 CP
tables) and the injected failure rates were verified against the output,
not assumed.

The Child Protection tables stay small regardless of population size (they
scale with the ~2.2% flagged-child rate, not the population) — the cost of
scaling up is almost entirely the two full-population tables.

**Output is CSV, not Parquet** (the contract's planned delivery format) —
`pyarrow` isn't pip-installable in this environment; `generate.py`'s
`.to_csv(...)` calls are a drop-in swap for `.to_parquet(...)` once it is.

## Output layout

`<outdir>/public/` — agency-shaped tables only, no cross-agency join keys
(what a real downstream consumer would get). `<outdir>/internal/` —
`population_master.csv` (ground truth) and `linkage_answer_key.csv`
(`person_uid` → every agency's own ID, for the people who appear in all
three agencies) — an answer key for validating entity-resolution logic or
the generator itself, never to be distributed alongside `public/` as if it
were more test data.

## Known simplifications

Adult age and "has children" are only loosely correlated; everyone in a
household shares one address (placements override this for CP-flagged
children only); mortality is an age-band curve, not an actuarial table;
`registering_parent_*_name` is populated only for people currently in the
"child" household role (adults' own parents aren't modelled);
`is_multiple_birth` doesn't actually pair twins; case workers/carers are a
separate pool, not drawn from the general population.

## Open thread

Pipeline-run tracking (the other item raised alongside synthetic data
generation) is still on the agenda and hasn't been scoped or built yet.
