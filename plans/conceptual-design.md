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

**Status:** done (2026-09-17) · **Category:** QA checks & contract

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

Applies equally to Child Protection - confirmed for real, not just in
principle, once CP actually got its own resupply simulation
(2026-09-18, plans/qa-pipeline.md item 80/queued in plans/running-
thoughts.md as "CP resupply simulation"): `generator/generate_cp_runs.py`
now drives a real red quarterly delivery through `generator/resupply.py`'s
same generic chain-orchestration engine BDM uses (genericized that same
day to a `dict[str, pd.DataFrame]` payload, since CP's delivery is a
whole collection's worth of tables at once, not one DataFrame), on its
own slower delay curve (a full collection re-extract realistically
takes longer to correct than a single day's file - Keith's own
calibration: "2-4 weeks, mostly 1-2," vs BDM's 1-10 business days). The
dashboard-side model above needed literally zero changes to pick this
up - exactly the "nothing about the model assumes BDM-only" claim this
paragraph made before it was actually exercised by a second dataset,
now verified against real committed CP history (a real chain opens at
`cp_run_13`/closes at its resupply, another at `cp_run_15`/its own
resupply, both visible in the real supply-history UI with a real "N
days since previous" counter).

**Resolved, 2026-09-19 (was: Parked, NOT blocking the above).** How
should a PERSISTENTLY amber dataset be handled? Keith's own words,
thinking out loud, originally ended without landing on an answer: "how
do we handle amber-level data sets... do we need to actually take a
decision to accept that they're amber? Or are we saying amber is a
warning that we have to resolve by changing the checks
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
be recorded, whether it's per-run or a standing decision for a check) -
explicitly deferred at the time, not something the "keep it simple,
amber-or-green closes a chain" rule above needed resolved first.

**Resolution, 2026-09-19 (Keith's own explicit ask, "let's tackle item
six" - running-thoughts.md #6): option 3** - amber requires an explicit
HUMAN decision, per run, accept or reject, without changing the check
definition itself. Scoped via a real `AskUserQuestion` round covering
the three options above plus two follow-up mechanics questions, all
grounded in what `/accept` (built 2026-09-18) had already proven out in
practice rather than decided from scratch: reject mirrors accept
exactly (a real `/reject` GitHub comment, same ticket, same per-run
window-matching, no new infrastructure) and - the smaller, safer
option, Keith's own explicit call - a REJECTED run's pill still stays
amber, same as accept's own "never silently repaint the pill" design;
only the badge differs ("✗ Rejected by `<user>`" vs "✓ Accepted by
`<user>`"). If a single run's window somehow carries both a real
`/accept` and a real `/reject` (someone changes their mind, or two
different people comment differently) - Keith's own explicit call -
whichever comment is MOST RECENT wins, regardless of which command it
was, not "reject always wins" or "accept always wins".

Built the same session: `qa_tools/common/acceptance_sync.py` generalized
from accept-only to `match_decisions()`/`build_decisions()` (both
commands, most-recent-wins conflict resolution); `dashboard/qa-reporting-
dashboard.template.html`'s `const ACCEPTANCES` renamed `const
AMBER_DECISIONS`, `acceptanceBadge()` renamed `amberDecisionBadge()`
(renders either badge kind off a new `decision` field). Found and fixed
a real, separate bug live while adding test coverage against real
current committed history: this project's own full BDM pipeline
regenerations left MOST real runs sharing an `arrived_date` with
another real run (352 real runs, only 123 distinct dates) -
`_run_windows_for_dataset()`'s own long-documented intent ("ties
resolve to whichever sorts first") didn't match what the code actually
did (the FIRST tied entry got a zero-width, structurally unmatchable
window; a same-day comment silently fell through to the SECOND or last
tied entry instead) - fixed to dedupe to one window-owning entry per
distinct date, matching the documented intent for real. Regression
tests added first, confirmed failing against the pre-fix code, then
fixed. 9 new/updated Python tests (`tests/test_acceptance_sync.py`),
3 new real-browser e2e tests (`tests/test_dashboard_e2e.py`'s
`TestAmberDecisionBadge`, verified against real committed amber runs).
Revisit when Keith raises it again if this ever needs a "standing
decision" (not per-run) mode - out of scope for this pass, per the
original design's own "per-run, not standing" call for accept.

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
