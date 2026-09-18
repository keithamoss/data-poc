# Data generation

Synthetic data generation for this PoC - `generator/` (Birth
Registrations, event-flow, daily deliveries) and `synthetic_data_
generator/` (a separate, population-scale, cross-agency-identity-linked
generator, not currently wired into the pipeline - see item #3 below).
Split out of `plans/wider.md` 2026-09-18 (that file had become an
undifferentiated 32-item dump spanning unrelated topics; see `plans/
wider.md`'s own intro for the full account of the split and `plans/
running-thoughts.md` item #10 for the schema this file's own item tags
follow).

Status values: `todo` / `investigate` / `in-progress` / `parked` /
`done` / `superseded`. Every item also carries a Component tag - see
`plans/running-thoughts.md` item #10 for the shared taxonomy this and
`CHANGELOG.md` both use. IDs (`data-generation-N`, referenced elsewhere
as `plans/data-generation.md #N`) are permanent once assigned - never
renumbered or reused, even if an item is later retired, matching `qa_
tools/common/check_lifecycle.py`'s own `check_id` convention.

1. **[done, 2026-09-18]** **[Data generation]** Pull `synthetic-data-generator/` and
   `docs/` into this repo. The sibling repo never existed on GitHub —
   only inside claude.ai chat sessions — so this was a zip merge, not a
   git remote add. Deliberately left out a stale, pre-real-tools
   snapshot of the pipeline files bundled in the same upload. Commit
   `8a1028f`.

2. **[todo, 2026-09-18]** **[Data generation]** Decide the long-term home for
   `synthetic_data_generator/`. It's a subdirectory here for now
   (simplest, since it never had its own GitHub repo); worth revisiting
   once cleanup starts — does it stay merged into this repo, or get
   split out now that we can actually push to GitHub? Note this is now a
   real dependency-in-the-other-direction, not just physical proximity:
   `synthetic_data_generator/` imports `generator.dirty`/`generator.
   names_au`/`generator.presentation` directly (see `plans/publishing-
   and-history.md` #3) - splitting it into a separate repo would need to
   either vendor those three modules back in or make `generator` an
   actual installable dependency, not just delete the sys.path hack that
   used to paper over this.

3. **[todo, 2026-09-14]** **[Data generation]** Birth Registrations and Child
   Protection currently come from two separate, unlinked synthetic
   populations — no cross-agency identity linkage is actually exercised
   in this pipeline, despite the machinery existing.
   `synthetic-data-generator/population.py` builds a shared master
   registry (`person_uid`, households) and `synthetic-data-generator/
   generate.py` + `agency_datasets.py` draw Birth Registrations, Child
   Protection, and School Enrollment all from that *same* population
   (each agency gets its own presented name/ID via `presentation.py`,
   linked underneath by `person_uid`, with an `internal/` linkage
   answer-key file) — real and present, just not what this pipeline
   calls. `generator/daily_batch.py` (what `generator/generate_runs.py`
   actually uses for Birth Registrations) is a deliberately separate
   event-flow generator with no population.py involvement at all — a
   fresh cohort of newborns each day, not a resample of an existing
   population, per its own docstring. `generator/generate_cp_runs.py`
   (Phase 1, Child Protection) does call `population.py`, but generates
   its own standalone population instance, not shared with Birth
   Registrations'. **Follow-up:** re-point Birth Registrations at the
   shared population (`agency_datasets.py`'s own
   `generate_birth_registrations()` already does this — a second,
   genuine implementation that exists but isn't wired into the pipeline)
   so a synthetic person can genuinely show up in both datasets under
   different agency IDs — worth doing once there are enough datasets
   wired into the dashboard (`plans/dashboard.md` #1) that cross-agency
   identity resolution becomes a meaningful thing to demonstrate, not
   before.

   **Scoped, not built (2026-09-14)** - Keith asked for this, then
   stopped short of building once the real shape became clear, to keep
   focus on the pipeline's actual core (QA) rather than get pulled into
   generator work. Filed here so the scoping isn't lost if this comes
   back later:
   - `agency_datasets.py`'s `generate_birth_registrations()` is NOT a
     drop-in replacement for `daily_batch.py` - it emits one row per
     person in a whole-population snapshot in a single call, with no
     concept of daily deliveries, dirty-severity injection, or resupply
     chains (the machinery the actual QA pipeline's "multiple runs over
     time" story depends on). Real linkage means threading a shared
     identity source underneath both generators' *existing* mechanics,
     not swapping generators.
   - Asked how much overlap: **"a meaningful minority (most/all CP
     clients also get a BDM record)"**, not just a handful. This rules
     out relying on coincidental overlap between CP's population (ages
     0-17) and BDM's ~10-day rolling newborn window (statistically
     near-zero chance of a birthdate landing inside it) - it requires a
     **historical backfill** dataset (birth registrations for people
     already in the population, via `generate_birth_registrations()`
     largely as-is) as an *additional* piece alongside BDM's existing
     daily event-flow feed, not a replacement for it.
   - Asked whether the backfill goes through the real dbt/Soda/
     datacontract-cli checks like any other run: **yes, in scope** - not
     treated as exempt archival data.
   - Asked whether the dashboard should visibly surface the linkage:
     **no, separate follow-up** - this item is scoped as the data-model
     linkage only (shared population underneath both generators + the
     historical backfill + a linkage answer-key file, mirroring
     `synthetic-data-generator/generate.py`'s existing `internal/`
     convention), not a dashboard feature.
   - Also surfaced, not yet acted on: `population.py`/`child_protection
     .py`/`agency_datasets.py` each hardcode their own `TODAY = pd
     .Timestamp("2026-09-13")` for age/mortality calculation - separate
     from the rolling-window dates fixed in `plans/qa-pipeline.md`
     #84's freshness-filter follow-up (`generator/anchor_date.py`), but
     would need the same treatment for population-linked birthdates to
     land correctly inside BDM's actual rolling window if this is picked
     back up.
   - Not scoped at all yet: how the historical backfill is exposed
     structurally (a new manifest entry type distinct from daily runs?
     how it interacts with row-count-growth/on-time-arrival checks built
     around the daily-delivery shape), and exactly how many/which
     `has_child_protection_history` children get birthdates placed inside
     the rolling window vs. left at their existing 0-17-year spread.

4. **[todo, 2026-09-18]** **[Data generation]** Document/explain how the
   synthetic data population is generated and how `dirty.py`'s failure
   injection reflects real government data quality issues — Keith wants
   to understand the current approach's realism, not just confirm that
   it runs. Distinct from item #3 above (which is about wiring
   cross-agency linkage into the pipeline) — this is about explaining
   and reviewing the *model* itself: what `population.py`/
   `presentation.py`/`daily_batch.py` actually simulate (household
   structure vs. this repo's deliberately separate event-flow generator,
   ordinary cross-agency name/ID variation, nickname/typo drift) and
   whether `dirty.py`'s presets (null-rate creep, invalid codes,
   near-duplicates, drift, the newer format/cross-record presets) are a
   fair proxy for the kinds of defects real agency data actually has, or
   read as generic "data quality gremlins" a reviewer familiar with real
   WA government data would find unconvincing. Could land as a
   design-note doc, a README section, or a live walkthrough — not yet
   decided.

   **Progress:** did the live walkthrough for `population.py` (format/
   audience/rigor scoped via questions first) — found real, evidence-
   backed gaps: the hand-authored name pools collide heavily at
   population scale (`Charlotte Smith` × 5,499 at 200k people; ~5,000
   genuine full-name+DOB collisions), couple ages are drawn fully
   independently (32% of couples have a >15-year gap), mortality is
   computed but never enforced anywhere downstream, and
   `has_child_protection_history` can structurally never reach an adult
   despite the code's own comment claiming it's lifelong. Not yet walked
   through `agency_datasets.py`/`presentation.py`/`daily_batch.py`/
   `generate_cp_runs.py`/`dirty.py` - pick back up there.

   Also researched (not yet actioned) whether an existing library would
   do this better than hand-rolling it further - see `docs/synthetic-
   data-generation-tools-research.md`. Bottom line: no clean drop-in for
   "Python, Australian, multi-agency," but a real path exists (swap name
   pools for Faker/Mimesis now that pip access isn't the blocker it was
   when they were hand-authored; recalibrate household/age structure
   against real ABS Census DataPack marginals; if the multi-decade
   dimension is ever actually wanted, adopt a real dynamic
   microsimulation engine like `neworder` or LIAM2 rather than faking
   time-evolution in a point-in-time snapshot generator).

   **Also parked for future synth-data work**: day-of-week seasonality.
   Raised while analysing whether the row-count-growth check (`plans/
   qa-pipeline.md` #12) should compare against a run from N calendar
   days ago rather than the immediately preceding run - the real
   motivation for date-matching over ordinal-matching would be filtering
   out day-of-week effects (e.g. registrations naturally dipping on
   weekends), but `daily_batch.py`/`generate_runs.py` don't model any
   seasonality at all today, so the distinction is currently moot. Worth
   reconsidering if/when the generator models realistic weekly (or
   holiday) patterns - which would also mean revisiting the
   row-count-growth check's own thresholds, since a same-day-of-week
   comparison would then behave differently from a previous-run
   comparison in a way it doesn't yet.

5. **[done, 2026-09-14]** **[Data generation]** Resupply-chain
   simulation for Birth Registrations (generator layer only), Keith's
   own real-world practice: a delivery with a RED failing check (never
   amber) gets a resupply request, and the corrected (or still-broken)
   resupply arrives some working days later - "no single fixed resupply
   rate," deliberately. Scoped up front via 2 rounds of questions before
   building: generator/manifest layer only, real
   rows-largely-the-same-plus-organic-churn on resupply (not a fresh
   random draw), a real per-attempt retry chance rather than "one
   resupply always fixes it," Birth Registrations only for now.

   `generator/generate_runs.py` now walks each of its 10 scheduled
   deliveries through a full attempt chain when the first attempt is
   red: a business-day-aware delay (skewed fast - days 1-3 carry ~79% of
   the probability mass, tailing out to day 10), a 60%-per-attempt
   chance the resupply is ALSO red (calibrated so ~13% of red chains
   need 5+ attempts - "sometimes, in a really bad scenario," most
   resolve in 1-2 - matches Keith's own framing), and small-rate organic
   churn between attempts (~2% rows added, ~2% modified, ~1% removed -
   the source system keeps moving between attempts, a resupply isn't a
   time-frozen resend of byte-identical data). Bumped RUN_PLAN from 1
   red delivery to 2 so there'd be two independent chains to compare,
   not one data point.

   `data/raw/manifest.json` gained `delivery_id` (stable across every
   attempt of one logical delivery), `delivery_date` (the originally
   scheduled date), `attempt_number`, `arrived_date` (when this specific
   attempt's file was actually received), `is_resupply`, and
   `supersedes_run_id` - one delivery can now produce several manifest
   entries. Verified end to end: a real 2-attempt chain and a real
   4-attempt chain both generated and resolved correctly, with correct
   business-day arithmetic (every resupply `arrived_date` lands Mon-Fri)
   and correctly-scoped churn (isolated-tested at the designed ~1%/~2%
   rates; the larger add/remove deltas visible between a red delivery's
   own consecutive attempts are the combined effect of churn *and* that
   attempt's own freshly reapplied red-severity defects, not a churn
   bug).

   **Deliberately left untouched at the time**: `real_tools/*.py`, both
   dashboard builders, and the dashboard UI all assumed one manifest
   entry = one calendar day. Checked what that mismatch actually looked
   like rather than guessing: pointed the existing (unmodified)
   equivalent-engine pipeline at the new 15-entry manifest and it did
   NOT crash - it silently treated every attempt as its own independent
   "day," so `run_date`-sorted logic ended up picking whichever attempt
   arrived most recently *across every delivery's chain*, conflating
   separate deliveries' timelines into one sequence instead of
   representing "5+ attempts, same delivery" as what it is. That was the
   concrete, real input for designing what the reporting UI needed -
   since built (real resupply-chain simulation now also covers Child
   Protection, and the dashboard's own supply-history UI derives chains
   from real, observable status - see `plans/conceptual-design.md`
   Thread A for the resolved model and `plans/dashboard.md` for the UI
   itself).

   **Follow-up finding, verified**: revisited the row-count-growth
   check's own "compare against the immediately preceding run" logic
   (`real_tools/run_evidently_real.py`'s `_previous_run_file`, which
   walks `manifest.json` in list/generation order) in light of this
   item's own resupply chains - it had a real ordering problem once
   generation order and arrival order could diverge. Confirmed directly
   against the actual `data/raw/manifest.json`: `run_10_2026-09-10`
   (arrived 2026-09-10) sat at manifest position 15, immediately after
   `run_09_2026-09-09_resupply3` (position 14) - but that resupply
   didn't actually arrive until 2026-09-16, six days AFTER run_10.
   `_previous_run_file` would have compared run_10's row count against a
   delivery that, chronologically, hadn't arrived yet at the time run_10
   was received. Before this item, generation order and arrival order
   were always identical (one entry per calendar day, in sequence), so
   this was structurally impossible - a genuinely new problem this
   feature introduced, not a pre-existing one just now noticed.

6. **[investigate, 2026-09-18]** **[Data generation]** Data generation currently
   duplicates the contract's column definitions rather than reading from
   them - a real pain point Keith flagged. Confirmed by reading the
   code, not assumed: `contract/bdm-birth-registrations-contract.yaml`'s
   `schema.properties` is the actual source of truth for Birth
   Registrations' column names/types/quality rules, but `generator/
   daily_batch.py` builds its output via a hand-written
   `pd.DataFrame({"registration_number": ..., "child_given_names": ...,
   ...})` literal with its own independently hand-typed column names -
   nothing connects the two today. Add, rename, or remove a column in
   the contract and the generator silently drifts out of sync; nothing
   would catch it until a QA check started failing unexpectedly, or
   worse, silently stopped covering a real column at all. Not yet scoped
   how to fix: options range from a thin generator-side loader that
   reads column names/types straight out of the ODCS YAML's
   `schema.properties` at generation time (cheap, doesn't touch what
   actually gets simulated per column, just what the frame is shaped
   like) to something deeper tied into the `docs/synthetic-data-
   generation-tools-research.md` replacement work (a real generator
   library could plausibly take the contract's schema as its literal
   column spec, rather than either side hand-authoring independently).
   Worth scoping properly rather than picking blind - revisit alongside
   this file's own #4/#3 generator work, not in isolation. See also
   `plans/qa-pipeline.md` #85 - the same "contract should generate its
   downstream files, not just describe them" question, applied to dbt's
   and Soda's own check files instead of the generator.

7. **[parked, 2026-09-17]** **[Data generation]** An MVP external-data
   ingestion entry point - a real gap this PoC doesn't have an answer
   for today: every real run's data comes from this repo's own synthetic
   generator (`generator/`/`synthetic_data_generator/`), never from an
   outside source. Keith's own call: resume after `plans/publishing-and-
   history.md`'s Phase 6, same sequencing as `plans/qa-pipeline.md`
   items 66/68. Keith's own framing: not "automate all the data pipes"
   (a real integration project) but a genuine MVP entry point a team
   could use to fit this into their CURRENT workflow - pointing the
   pipeline at a zip file on disk, an S3 bucket, or a plain folder on
   disk, rather than requiring a real upstream integration before this
   tool is usable at all.

   Related to, but narrower and more actionable than, `plans/wider.md`
   #8 (that entry's "how checks output/results get stored in a
   multi-user environment" bullet is already scoped, per its own
   2026-09-16 update - see `plans/publishing-and-history.md`; this is a
   new, separate concern that entry's list didn't cover: how REAL INPUT
   data gets into the pipeline in the first place, not how QA results
   get stored once computed).

   Real complications Keith already flagged, to work through when this
   gets scoped for real (a conversation to have then, not decided here):
   agencies renaming files between deliveries (no stable filename
   convention to key off); some deliveries arriving zipped, others not;
   extra, irrelevant files mixed into the same drop (Word docs,
   README-style cover notes, etc.) that need to be recognized and
   ignored rather than tripping the pipeline. Not scoped further than
   that yet - flagged here so the concern and its known complications
   aren't lost before that conversation happens.

8. **[parked, 2026-09-17]** **[Testing & dev tooling]**
   `synthetic_data_generator/` has zero test coverage - a real gap a
   coverage survey found - but Keith's own call was to leave it out of
   `plans/publishing-and-history.md` Phase 6's scope, since the package
   is also currently entirely unused (not wired into the real BDM/CP
   pipeline at all - see `plans/qa-pipeline.md` #84's own history). His
   own words: "when we come back to it, have a note that we should
   consider adding tests for it." Not scoped further than that - revisit
   alongside whatever eventually wires this package into the real
   pipeline (if it ever does), not before.
