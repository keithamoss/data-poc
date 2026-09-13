# Synthetic Data Generator

Generates realistic, referentially-consistent fake population data for
internal testing of the multi-agency data asset PoC - population-scale,
multiple related tables within a collection, and the same fake person
showing up (consistently, but not identically) across several agencies'
own datasets.

Built to answer four things decided up front:

| Decision | Answer |
|---|---|
| First build target | A cross-agency identity scenario: **Child Protection Casework** |
| Identity linkage | A **shared synthetic population registry** every agency draws from |
| Target scale | **Several million+** (validated at 2.95M - WA's approximate real population) |
| Bad data | **Configurable failure injection**, tied to the checks already defined elsewhere in this project |

No pip/network access was available while building this (see the rest of
this project's notes on that), so it's pure pandas + numpy - no Faker, no
DuckDB/Polars, no pyarrow. That turned out fine: hand-rolled, fully
vectorized generation is actually *faster* than Faker-style per-row calls
at this scale, and the reference name/suburb pools (`reference/names_au.py`)
are more controllable than a generic library's defaults. Swap in Parquet
output once pyarrow is available in your real environment - see "Output
format" below.

## Architecture

```
reference/names_au.py     given names, family names, WA suburbs/postcodes,
                           street components - all weighted so the output
                           has a realistic name/place-frequency curve
                           instead of every value being equally likely.

population.py              the master registry: one row per synthetic
                           person, with a stable person_uid, households
                           (built from weighted household-composition
                           templates), ages, sex, names, one shared
                           address per household, mortality, and a
                           has_child_protection_history flag.

presentation.py            projects one master record into an
                           agency-specific "view" - nicknames, occasional
                           transcription-style typos, and a stable but
                           agency-own reference number - so the SAME
                           person looks slightly different at each agency,
                           which is what real government data looks like.

child_protection.py        the Child Protection Casework collection: 6
                           related tables (clients, notifications,
                           investigations, placements, carers, case
                           workers) with real foreign keys between them,
                           drawn from the master registry's flagged
                           subset.

agency_datasets.py         two more agencies' views of the same people:
                           birth_registrations (the WHOLE population, in
                           the same column shape as this project's
                           bdm-birth-registrations-contract.yaml) and a
                           lightweight school_enrollment extract for the
                           CP-flagged children.

dirty.py                   configurable failure injection - nulls,
                           invalid/unknown categorical values, near-
                           duplicate rows, step-change drift - plus
                           ready-made presets tied to the exact warn/fail
                           thresholds in bdm-birth-registrations-soda-
                           checks.yml, so a QA run against dirtied output
                           lands in the band you asked for.

generate.py                 CLI entrypoint - wires all of the above
                           together and writes CSVs.
```

## Quick start

```
python3 generate.py --population 200000 --outdir output/demo
python3 generate.py --population 2950000 --outdir output/full_scale --dirty amber
```

`output/sample/` in this repo is a pre-generated 60,000-person run
(`--dirty amber`) so you can look at real rows without running anything.

## Scale

Validated end-to-end at **2,950,000 people** (Western Australia's
approximate real population) on a single core, no external services:

| Stage | Time |
|---|---|
| Population registry (households, ages, names, mortality, CP flag) | 16.8s |
| Child Protection collection (6 tables, ~22k flagged clients) | 0.2s |
| birth_registrations (2.95M rows) + school_enrollment | 25.1s |
| `--dirty amber` failure injection | 1.8s |
| **Total** | **~70s**, ~645MB of CSV output |

The Child Protection tables stay small regardless of population size (they
scale with the ~2.2% flagged-child rate, not the population), so the cost
of scaling up is almost entirely the two full-population tables
(`population_master` and `birth_registrations`).

**Getting to this speed mattered more than it might look**: the first
version of both the population-registry and the birth-registration
parent-lookup step used `DataFrame.groupby(...).transform(lambda ...)` /
`groupby(...).__iter__()` - i.e. a Python callback invoked once per
household. That's the single most common way pandas code silently becomes
O(n) in Python instead of O(n) in C, and it was costing 19s at 200,000
people alone (would have been several minutes at 3M). Replaced with
`.groupby().cumcount()` / `.transform('max')` (compiled aggregations) plus
vectorized `.map()` - see the comments in `population.py` and
`agency_datasets.py` if you extend this and hit the same wall.

**If you need tens of millions of rows** (e.g. a many-events-per-person
table this repo doesn't build yet, like health service contacts), don't
hold one big DataFrame in memory - generate in chunks and append to disk.
`generate.py` doesn't need this at population scale (2.95M people fits
comfortably in ~1.4GB of RAM), but a table with, say, 20 events/person
would; the vectorized generation functions here all take a `seed` and
return one chunk's DataFrame, so the pattern is: loop over row-count
chunks, generate each with a different seed, `.to_csv(..., mode="a",
header=(i==0))` and discard the chunk before generating the next.

## Output format

Everything here writes CSV. The project's actual delivery format is
planned to move to Parquet (see `bdm-birth-registrations-contract.yaml`'s
`customProperties`) - this repo doesn't do that only because `pyarrow`
isn't installable in the environment it was built in (no PyPI access).
Once it is: `df.to_parquet(path, index=False)` is a drop-in replacement
for every `.to_csv(path, index=False)` call in `generate.py`.

## Output layout: public/ vs internal/

```
<outdir>/public/      what a real downstream QA/test consumer receives -
                       agency-shaped tables only. No table has another
                       agency's ID or the master person_uid in it - only
                       its own agency-minted reference number.

<outdir>/internal/    population_master.csv (the ground-truth registry)
                       and linkage_answer_key.csv (person_uid -> every
                       agency's own ID for that person, for the ~22k
                       people who appear in all three agencies).
```

**Never hand out `internal/` alongside `public/` as if it were more test
data** - it's the answer key. Its actual use is validating your own
entity-resolution/matching logic (or this generator itself) against known
ground truth, not something a QA pipeline or a data-provider test exercise
should ever see.

## The three-agency example, concretely

Every person in `cp_clients` (Child & Family Safety) also has a row in
`birth_registrations` (Registry Services) and `school_enrollment`
(Education) - same underlying person, three agency-specific IDs, three
independently-presented name spellings:

```
person_uid 943378 (internal only, never published):
  Registry Services / BDM  -> BDM-606711178: "Charlotte Smith"
  Child & Family Safety    -> CPS-714543758: "Charlotte Smith"
  Education                -> EDU-988038687: "Charlotte Smith"
```

(names/spellings match here more often than not - `presentation.py`'s
nickname/typo rates are deliberately modest, ~12%/3.5%, because that's
what makes the *mismatches* meaningful when they do occur; run
`generate.py` with `--demo-examples 10` to see cases where they differ.)

## `--dirty {amber,red}`

Applies two presets:

- **birth_registrations**: `sex` gets invalid codes (`U`/`O`/`9`) injected
  at 0.8% (amber) or 2.8% (red) - lands either side of the
  `bdm-birth-registrations-soda-checks.yml` fail line (>2%).
  `place_of_birth_facility`'s null rate is pushed to 20% (amber) or 40%
  (red) against that same file's warn/fail lines (15%/35%).
- **cp_notifications**: `concern_type` gets unknown codes (`Unspecified`,
  `Pending classification`, `Code 9`) injected - the "a new, unexpected
  value has appeared in a fixed value set" scenario discussed earlier for
  this project - plus near-duplicate notification rows (a dropped
  character in `notification_id`), for exercising uniqueness checks.

`dirty.py`'s functions (`inject_nulls`, `inject_invalid_values`,
`inject_missing_expected_value`, `inject_duplicate_rows`,
`inject_drift_batch`) are generic - reach for them directly to build a
scenario the two presets don't cover (e.g. `inject_missing_expected_value`
models an expected value *disappearing* rather than a new one appearing).

## Known simplifications

Documented rather than engineered around, since this is illustrative test
data, not a demographic simulation:

- Adult age and "has children" are only loosely correlated - a small share
  of parent/child age gaps will be tighter than 18 years.
- Everyone in a household shares one current address. Placement addresses
  in `cp_placements` override this for children in out-of-home care;
  nothing else models address history over time yet.
- Mortality is an age-band probability curve, not an actuarial life table.
- `registering_parent_1/2_name` in `birth_registrations` is only populated
  for people whose *current* household role is "child" - adults' own
  parents aren't modelled, so their own birth record's parent fields are
  blank. (This is arguably realistic: a lot of real historical
  civil-registration data has sparse parent fields too.)
- `is_multiple_birth` is an independent per-person flag, not actually
  paired twins/triplets sharing a birth date.
- Case workers and carers are generated as their own small pools, not
  drawn from the master population registry (they're professionals/
  approved carers, not "the general public" in this model).

## Requirements

Python 3.9+, `pandas`, `numpy`. Nothing else.
