# Project context, for the requirements-analysis agents

A condensed orientation written specifically for the three requirements-
analysis subagents (`plans/wider.md` #10 - the scoper, the reviewer, and
the QA-checker on top of them) to read before doing any real work. It
exists because none of the three starts with any memory of this project
- they only know what's in their own prompt plus whatever they read.
`CLAUDE.md` and `plans/*.md` remain the real, authoritative, and far more
detailed record; this document is a first-read summary, not a
replacement, and should be kept short enough that an agent actually reads
all of it before diving into the rest.

**Drafted 2026-09-19 from what was already documented in `CLAUDE.md`/
`README.md` - Keith's own explicit call was to review and correct this
rather than dictate it from scratch, so treat anything here as a
first-pass draft until he's confirmed it.**

## What this is

A proof-of-concept "data asset QA register" - a live reporting dashboard
and the real pipeline behind it - for a multi-agency government data
asset. It's built around one real feed (BDM Birth Registrations) plus a
Child Protection collection (6 tables, cross-table checks), both backed
by synthetic data standing in for what would be real production data in
an actual deployment. Codenamed "Mothman" (a legend remembered for
showing up before a disaster - the point of a QA pipeline).

## Why it exists

The underlying problem: a government agency handling data that spans
multiple other agencies (birth registrations, child protection records,
etc.) needs real, ongoing visibility into that data's quality - not a
one-off audit, but a standing register that shows, dataset by dataset,
whether the data currently arriving is trustworthy, and a real history
of how that's changed over time. This PoC exists to demonstrate that
such a register can be driven by genuinely automated checks (four real,
independent tools - dbt-core, Soda Core, datacontract-cli, Evidently AI
- run against real data on a real cadence) rather than a hand-maintained
spreadsheet or a mocked-up dashboard with fabricated numbers.

## Who this is for

**The person actually evaluating this PoC today**: Keith, Director of
Data Technology at a Western Australian government agency. He is both
the project's sponsor and its most active real user right now - he
reviews the live dashboard, gives feedback by voice dictation, and makes
the real design calls this project's `plans/*.md` files record.

**Who this models being for, in a real (non-PoC) deployment**: data
stewards who'd use the dashboard day-to-day to see whether their
dataset's current status is trustworthy; the agencies who actually own
each real dataset (e.g. Registry Services for Birth Registrations, the
Department for Child Protection and Family Support for the Child
Protection collection) as accountable parties; and whoever maintains the
pipeline itself (the QA checks, the contract, the ingestion). None of
these are real named people yet in this PoC - `contract/people.yaml` has
Keith's own real identity plus fictional Monty-Python-named placeholders
standing in for colleagues not yet named for real.

## Current state and maturity

**A proof-of-concept being built over weeks, not months** - not
production software, and not staffed like one. Most of it is built and
real (see "What's real vs illustrative" below), but scope is
deliberately narrow: two real datasets/collections wired to genuinely
computed checks, everything else on the dashboard illustrative. Treat
"is this a PoC-appropriate scope" as a real, standing question when
scoping new ideas - not everything a production system would eventually
need is in scope now.

## What's real vs illustrative

This matters a lot for the requirements-reviewer agent specifically:
**only some of what the dashboard shows is backed by real computation.**
Registry Services → Civil Registration → Birth Registrations, and the
Department for Child Protection and Family Support → Child Protection
collection (6 tables), are wired to real output - every number traces
back through this repo's actual dbt-core/Soda Core/datacontract-cli/
Evidently AI runs against real generated CSVs, never hand-typed or
fabricated. Every other dataset on the dashboard page is the same
illustrative, browser-fabricated mock data it always was, clearly
labeled as such in the page's own footer. When reviewing "was this
requirement actually built," check which category the relevant
dataset/feature falls into - a real UI element rendering real-looking
mock data is a different thing from the same UI element wired to a real
computed check, and the two can look identical without being verified
the same way.

## Rough architecture (high level - see `CLAUDE.md`'s own layout table
for the full, current, authoritative breakdown)

| Piece | What it does |
|---|---|
| `contract/` | The real ODCS contract + SodaCL checks - the actual source of truth for schema/quality rules. |
| `generator/`, `synthetic_data_generator/` | Synthetic data generation standing in for real production data. |
| `qa_tools/` | The real dbt-core/Soda Core/datacontract-cli/Evidently runs - the only pipeline path. |
| `qa_results/` | The permanent, committed history of every real QA run - never regenerated away. |
| `dashboard/` | The single-file static reporting dashboard, built from a real hand-authored template plus real embedded data. |
| `plans/*.md` | This project's own living design memory - real decisions, real open questions, real status per item. |
| `requirements.yaml` | The live, structured requirements register (MoSCoW, acceptance criteria, real CI-enforced test linkage) - this is what the requirements-scoper/reviewer agents write into. |
| `mothman` (`cli/`) | The one and only programmatic entry point to every script in this repo - nothing outside it should be invoked directly. |

## Conventions worth carrying into any BA-style work

- **`mothman` is the only sanctioned way to run anything in this repo** -
  never invoke a script directly.
- **CI never touches live or synthetic data** - any check that needs a
  live connection runs once, at real pipeline-run time, never deferred
  to a later read.
- **A real bug found gets a regression test, confirmed failing before
  the fix** - the same standard a requirements-reviewer agent should
  hold newly-reviewed work to.
- **Real design forks get scoped with Keith via clarifying questions
  before building** - the requirements-scoper agent's own "ask, don't
  guess" behaviour is this same convention, generalized.
- **`plans/*.md` is the project's real memory, not this chat history** -
  a scoper agent proposing a new idea should check there first for
  whether it's already been scoped, parked, or decided against.
