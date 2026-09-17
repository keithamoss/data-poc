# Real conceptual/design issues

A different kind of memory from the other three `plans/*.md` files -
`qa-pipeline.md` logs real bugs/checks found running the real tools,
`wider.md` tracks the whole PoC's architecture and parked ideas,
`publishing-and-history.md` is scoped narrowly to the publish/history
mechanism. This file is for the deeper kind of question Keith raises
periodically that isn't "here's a bug" or "here's a feature to build" but
"does the thing we're modeling actually correspond to how this works in
the real world" - the kind of tension that needs a real decision, not
just an implementation. Created 2026-09-17 (Phase 7), at Keith's own
explicit request, to park exactly this kind of question rather than lose
it in chat history or force a decision before it's ready.

## Thread A: resupply-chain modeling (2026-09-17)

**The tension.** The original resupply-history UI
(`buildSupplyHistory()` in `dashboard/qa-reporting-dashboard.template.
html`, plans/qa-pipeline.md items 29/71) grouped a dataset's real run
history using synthetic bookkeeping fields the GENERATOR writes for its
own convenience - `delivery_id`/`delivery_date`/`is_resupply`/
`supersedes_run_id` (`generator/generate_runs.py`'s
`_manifest_entries_for_delivery()`). Keith's own critique, prompted by
investigating a real mislabeled-attempt-number bug (item 71): "suppliers
won't actually label a resupply as against the original supply. It will
just appear at a certain time. So I think something you're modeling
about supplies and resupplies doesn't make sense." Trusting
generator-authored "this run IS a resupply of THAT run" metadata models
something that has no real-world counterpart - a real supplier's file
just arrives, with no flag saying what it's a resupply of, or even that
it's a resupply at all.

**The resolved model (built, Phase 7).** Chain membership is now derived
PURELY from two real, computable things, cadence-agnostic (identical
logic for a daily feed and a quarterly one):

1. The ODCS-contract-derived cadence (`pipeline/cadence.py`'s
   `cycle_start()`/the dashboard's own `cycleStartDate()`) - used only to
   anchor where a NEW chain starts, not to decide chain membership run by
   run.
2. Each arrival's own real aggregate quality status - red/amber/green,
   the worst status among every real check across every column for that
   specific run (a new `datasetStatusByRun()` in the dashboard template,
   built from data already embedded in the dashboard JSON - each check's
   own `history[]` entries against its own `warn`/`fail` thresholds, no
   new data pipeline computation needed).

Walking a dataset's real arrivals in chronological (`run_date`) order: a
RED arrival starts (or continues, if the current chain is still open) a
resupply chain. The chain CLOSES on the first AMBER or GREEN arrival
after a RED. "Let's keep it simple - an amber or a green supply can count
as the end of a resupply chain" - Keith's own final call, arrived at out
loud after weighing whether amber should count as a real resolution or
an accepted-but-unresolved state (see Thread A's parked question below,
which is exactly that weighing, deliberately not resolved here). A plain
green (or amber) arrival with no open chain before it is just an
ordinary one-entry group - no resupply language shown, same as today.

This is the same underlying "worst-of every check, across every column"
computation as the separately-requested aggregate status pill shown
against each supply/resupply row (Keith: "I do like the idea of having
an overall pill on each supply, showing whether it's red, amber, or
green... an aggregate of all of the checks for the dataset and all its
columns") - one computation, two UI uses, not two parallel
implementations that could drift.

Deliberately NOT changed as part of this: the generator
(`generator/resupply.py`/`generator/generate_runs.py`) still writes
`is_resupply`/`delivery_id`/`delivery_date`/`supersedes_run_id` into
`manifest.json` - those still describe something real about how the
SYNTHETIC DATA ITSELF was generated (a churned, re-dirtied re-attempt of
the same underlying delivery), which is legitimate generator-internal
bookkeeping. What changed is narrower and more important: the DASHBOARD
no longer trusts or reads any of those fields to decide what counts as a
resupply or which cycle something belongs to - it derives that purely
from real, publicly-observable facts (when did a file arrive, was it
red/amber/green), the same two facts a real production dashboard would
actually have.

Applies equally to Child Protection, which has zero resupply-chain
concept in its generator today (`generator/generate_cp_runs.py` - pure
periodic full-collection snapshots, no resupply simulation at all) - the
new model needs nothing dataset-specific to work there: it would just
never find an open chain to continue, since CP's synthetic runs don't
currently simulate a red-then-refixed sequence. Nothing about the model
assumes BDM-only.

**Parked, NOT blocking the above.** How should a PERSISTENTLY amber
dataset be handled? Keith's own words, thinking out loud, ended without
landing on an answer: "how do we handle amber-level data sets... do we
need to actually take a decision to accept that they're amber? Or are we
saying amber is a warning that we have to resolve by changing the checks
to accept it (become green) or reject it (become red)? Or a human taking
a decision, accept/reject, making it effectively red or green." Three
live options, none chosen yet:

1. Amber is a legitimate steady state - no decision ever required, it's
   just a standing warning.
2. Amber is inherently provisional - it must eventually be resolved by
   changing the CHECK DEFINITION itself, either loosened to accept the
   observed values (amber -> green) or tightened to reject them (amber ->
   red). The data doesn't change; the bar does.
3. Amber requires an explicit HUMAN decision on the DATA - accept it
   (effectively treated as green from then on) or reject it (effectively
   treated as red) - without necessarily changing the check definition
   itself.

This is a real governance question (who owns that decision, where it'd
be recorded, whether it's per-run or a standing decision for a check)
with no scoped answer yet - explicitly deferred, not something the
"keep it simple, amber-or-green closes a chain" rule above needs
resolved first. Revisit when Keith raises it again.

**Related, still open (tracked in `plans/qa-pipeline.md` item 71's own
"related risk" note, not duplicated here in full)**: the SLA tile's
"Latest arrival" pill and the Tier 2 agency-row pill
(`pipeline/build_dashboard_data.py`'s `lastArrival`/`latest_status`)
still pick the single most-recent run by `run_date` with no awareness of
chain position - currently harmless (today's real committed history
happens to end on a non-chained run) but architecturally the same
category-error risk item 69 fixed for the supply-history table. Keith's
own sequencing: pick this up once the chain-derivation redesign above is
done, not before.
