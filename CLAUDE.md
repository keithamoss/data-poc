# Orientation for a new session

Read this first, then `plans/wider.md` and `plans/qa-pipeline.md` in full
before doing anything else. This project is worked across many separate
chat sessions over a period of weeks - those two files are the actual
persistent memory of the project, not this chat history. They're kept
current as work happens: design decisions, the questions that were asked
to scope them, what was verified and how, and what's still open. Don't
re-derive a decision that's already recorded there, and don't re-propose
something already logged as `[investigate]`/`[todo]` without checking if
it's already scoped.

- `plans/wider.md` - the whole PoC: what exists and where, open
  architectural questions, parked thoughts for later.
- `plans/qa-pipeline.md` - specifically the birth-registrations QA
  pipeline: real bugs found running the real tools, check design,
  dashboard follow-ups.
- `plans/performance.md` - narrowly the real-tool orchestration scripts'
  runtime.

## Who this is for

Keith, Director of Data Technology at a Western Australian government
agency, working this as a proof-of-concept over **weeks**, not months -
don't assume a long timeline or plan around one. He gives feedback by
voice dictation fairly often; when a message reads oddly (garbled words,
self-contradicting mid-sentence), it's very likely a transcription
artifact, not a genuine ambiguity - read for intent rather than asking
him to repeat himself, unless the fork it implies is actually consequential.

## What this repo is

An end-to-end QA/data-pipeline PoC for a multi-agency government data
asset, built around one real feed (BDM Birth Registrations) plus a Child
Protection collection, both backed by synthetic data. `README.md` is the
detailed technical entry point (what's real vs. "equivalent", how to run
it); `HANDOFF.md` documents a since-completed session-to-session
transition (claude.ai, no internet -> Claude Code, real internet) - read
it for history, not for current state.

Rough layout:

| Path | What |
|---|---|
| `contract/` | Real ODCS contract + SodaCL check YAML - the actual source of truth for schema/quality rules |
| `generator/` | Synthetic data generation (`daily_batch.py`, `generate_runs.py`, `resupply.py`, `dirty.py`) - Birth Registrations only; deliberately separate from `synthetic-data-generator/`'s population-scale generator |
| `synthetic-data-generator/` | A separate, population-scale (millions), cross-agency-identity-linked synthetic data generator - not currently wired into the pipeline (see `plans/wider.md`) |
| `pipeline/` | Loads generated CSVs into DuckDB, builds dashboard JSON |
| `engines/` | Hand-written Python/DuckDB stand-ins for dbt/Soda/datacontract-cli/Evidently, from before real tool access existed - kept as documented fallback, not the current path |
| `real_tools/` | The actual dbt-core/Soda Core/datacontract-cli/Evidently runs - this is what's live today |
| `dashboard/qa-reporting-dashboard.html` | The single-file static dashboard, published via GitHub Pages on every push that touches `dashboard/` |
| `docs/` | Research and design-note docs - `data-contract-engines-landscape.md` (tooling survey), `synthetic-data-generation-tools-research.md`, `synthetic-data-generator-notes.md` |
| `plans/` | Living project memory - see above |

## Conventions worth knowing before touching anything

- `data/raw/`, `data/warehouse.duckdb`, `reports/*.json` etc. are
  gitignored and fully regenerated - never hand-edit or try to commit
  them. Regenerate via `./run_pipeline.sh` (equivalent engines) or
  `python3 real_tools/orchestrate_real.py` (real tools).
- Everything is seeded - regenerating reproduces the same output, so a
  diff against previous output is a real correctness check, not noise
  (used repeatedly to verify refactors are behaviour-preserving).
- The repo is public (Keith's own call, synthetic data only) - GitHub
  Pages hosting depends on that; see `plans/wider.md` #5 for the
  parked note about what happens if/when it goes private again.
- When a design decision has real forks (not just implementation
  detail), scope it with Keith via a couple of rounds of clarifying
  questions before building - this has been the working pattern all
  along, not a one-off. Bias toward proceeding once the real forks are
  resolved; don't re-ask what's already been answered.
- Commit and push to whatever branch the session was told to develop
  on; don't create a PR unless explicitly asked.
