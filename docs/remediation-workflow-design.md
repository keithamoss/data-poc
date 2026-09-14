# Remediation workflow design — investigating and fixing bad data

Grew out of `plans/qa-pipeline.md` #15 ("genuine per-row failing-record
samples"): once it became clear three of the four real tools already
wired into this pipeline can surface real failing rows cheaply (see that
item for the tool-capability research), the actual open question turned
out not to be technical at all. It was a product-scope one — **should the
QA reporting dashboard be the thing that stores/displays row-level bad
data and lets someone act on it, or does that belong somewhere else
entirely?** — the same split `docs/quarantine_sex_column.py` already
draws between "flag it" (report a check failed) and "act on it" (decide
what happens to the specific bad rows).

Settled via several rounds of questions with Keith (2026-09-14), working
through the actual shape of the idea rather than jumping to a solution.
Moved to its own file because it turned out to be a genuinely standalone,
self-contained design — a real case-management/workflow capability,
architecturally distinct from the QA reporting dashboard, not a dashboard
feature.

**Scope for this PoC specifically: design the seam/handoff point only, do
not build this.** The platform choice — Jira Service Management already
exists at the agency, but Microsoft-stack tooling (Planner/Power
Automate/SharePoint/Teams etc.) is preferred to avoid extra licensing — is
a deliberately separate, later conversation, not decided here.

## Why this needs to exist at all

Today's real process — a person manually reviews output, then emails or
calls the provider directly — works at current scale but won't survive
the move to daily refreshes. Some of this needs to hand off directly to
providers while the team keeps oversight, rather than reviewing every
single issue by hand.

## Ticket model

- **Creation is universal**: every issue automatically becomes a ticket,
  no gatekeeping — *except* a check marked "known, expected to stay amber
  long-term" doesn't spin up a repeat ticket for persisting as expected
  (a flip to red, or to green, still surfaces as a notification either
  way).
- **Granularity: one ticket per column.** If several checks on the same
  column fail at once, that's one ticket, not several — a provider would
  want to address them together.
- **Scope: one unified ticket queue across every dataset/agency**,
  filterable per audience, not separate queues per dataset or agency.
- **Recurrence: a fresh occurrence of a previously-closed issue creates a
  NEW ticket, cross-referenced to the prior one** — not a reopen. Keeps
  each incident's resolution-time measurement clean and separately
  trackable (matters for the SLA-reporting ambition below), at the cost
  of not having one continuous record per check over its whole history.

## Assignment — the real decision point, not ticket creation

- **Automatic default per check/column** (e.g. schema/structural breaks
  default straight to the provider — clear-cut, major; subtler things
  like null-rate creep default to the team first), human-overridable.
- A provider-assigned ticket still notifies the team — assignment isn't
  "the team goes dark," it's the trigger for the team's own watch/FYI so
  they can step in if needed.
- **Ownership can be joint** — team and provider both actively engaged on
  one ticket at once, not necessarily a strict handoff.

## Escalation and suppression

Two distinct mechanisms, easy to conflate with each other:

- **Escalation**: the same check failing 6+ times in a row is a real
  supply-relationship signal, not routine noise — it bumps the ticket's
  severity so it can't get lost.
- **Suppression**: a check marked "known, expected to stay amber
  long-term" is exempt from BOTH repeat-ticket creation AND the
  6-in-a-row escalation rule — trusting the deliberate "this is accepted
  for now" call rather than re-litigating it via a stretch-length
  trigger.

## Automatic pipeline updates

The underlying principle, named directly by Keith: **tickets should get a
status update from the pipeline automatically anytime something happens
that affects that check or column** — a resupply arriving (whether it
fixes the issue or not), a quarantine release, any status touch, even
non-transitions ("still red, no change" still posts, since it's evidence
of activity/attempts for the timeline and SLA tracking).

This maps closely onto infrastructure this repo already has:
`generator/resupply.py`'s `run_delivery_chain` already yields exactly
this kind of event sequence (severity/arrival date per attempt) for Birth
Registrations' resupply chains — a real ticketing integration would
consume much the same shape of event stream this generator already
produces, not something wholly new.

**Closing always requires a human — no auto-close, full stop.** (This
superseded an earlier "maybe auto-close for minor issues" idea raised
partway through the discussion — worth knowing the thinking evolved here,
in case it resurfaces.)

## Quarantine and release

Extends `docs/quarantine_sex_column.py`'s existing split-and-hold demo
with a release step that doesn't exist there yet:

- Rows failing a quarantine-configured check are held in a dead-letter
  queue, per check.
- **Only the internal team can execute a release** back into the
  dataset — providers can be part of the decision, never the executor.
- Any required second-level sign-off (for higher-stakes releases) is a
  process convention configured inside the ticketing tool itself, not a
  separate technical permission system.
- The release auto-posts to the ticket, per the automatic-updates
  principle above.

## Time-tracking / SLA reporting

Captured from the start, internal-only reporting for now, but
deliberately designed so it could become a real, shared SLA metric with
providers later (e.g. "BDM average resolution time: 4.2 days") — worth
capturing cleanly from day one even before it's shared anywhere.

## Audiences and access

Three distinct roles:

1. **Data engineers** — full detail, full workflow tools.
2. **Their managers** — an oversight/rollup view.
3. **External data providers** (BDM etc.) — restricted to what they need
   to act (e.g. primary keys of bad rows, not full row content).

**Still genuinely open**: the external access *mechanism* — an
authenticated portal, email-threaded notification with no login, or some
hybrid. Not really an either/or in practice (most real platforms support
both at once); the real open variable is how much back-and-forth a
typical resupply conversation actually needs. Left for the
project-context walkthrough (`plans/wider.md` #16) to settle, since it's
a real-world-process question rather than a technical one.

## What's NOT decided here

- The platform (Jira Service Management vs. Microsoft-stack tooling) —
  explicitly deferred.
- The external access mechanism — see above, tied to real workflow depth
  not yet known.
- Anything about actually building this — this PoC's job is the seam,
  not the system.
