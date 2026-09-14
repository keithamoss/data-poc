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
it, including the project's origin in a claude.ai session with no
internet access, later picked up by a Claude Code session with real
access to actually run the tools).

Rough layout:

| Path | What |
|---|---|
| `contract/` | Real ODCS contract + SodaCL check YAML - the actual source of truth for schema/quality rules |
| `generator/` | Synthetic data generation (`daily_batch.py`, `generate_runs.py`, `resupply.py`, `dirty.py`) - Birth Registrations only; deliberately separate from `synthetic-data-generator/`'s population-scale generator |
| `synthetic-data-generator/` | A separate, population-scale (millions), cross-agency-identity-linked synthetic data generator - not currently wired into the pipeline (see `plans/wider.md`) |
| `pipeline/` | `orchestrate.py` generates + loads the combined DuckDB warehouse; `build_dashboard_data.py`/`build_cp_dashboard_data.py` reshape real-tool results into dashboard JSON |
| `qa_tools/` | The actual dbt-core/Soda Core/datacontract-cli/Evidently runs - the only pipeline path now (no more "_real" suffix on any of this - see `plans/wider.md` action 20's follow-up for why it dropped, once `engines/` was gone there was nothing left to distinguish it from). A proper Python package: `bdm/` and `cp/` (one per dataset, run as `python3 -m qa_tools.bdm.orchestrate_bdm` / `qa_tools.cp.orchestrate_cp`) plus `common/` (tool-generic subprocess/API invocation shared between them). (An earlier `engines/` directory of hand-written Python/DuckDB stand-ins, from before real tool access existed, was removed once it had drifted out of sync - see `plans/wider.md` action 18. Git history holds it if ever needed.) |
| `dashboard/qa-reporting-dashboard.html` | The single-file static dashboard, published via GitHub Pages on every push that touches `dashboard/` |
| `docs/` | Research and design-note docs - `data-contract-engines-landscape.md` (tooling survey), `synthetic-data-generation-tools-research.md`, `synthetic-data-generator-notes.md`, `remediation-workflow-design.md` (the bad-data ticketing/case-management design - deliberately out of this PoC's build scope, seam only) |
| `plans/` | Living project memory - see above |

## Conventions worth knowing before touching anything

- `data/raw/`, `data/warehouse.duckdb`, `reports/*.json` etc. are
  gitignored and fully regenerated - never hand-edit or try to commit
  them. Regenerate via `./run_pipeline.sh` (the whole pipeline end to
  end, ~45s) or `python3 -m qa_tools.bdm.orchestrate_bdm` (just
  the real-tool check runs, if `data/raw/`/`data/warehouse.duckdb`
  already exist; `python3 -m qa_tools.cp.orchestrate_cp` for
  Child Protection - not part of `run_pipeline.sh`, run separately).
  `qa_tools` is a proper Python package (`-m` invocation, not a bare
  script path) - both orchestration scripts run their manifest's runs in
  parallel by default (`qa_tools/common/parallel_orchestrate.py`) -
  add `--sequential` if debugging one specific run, since parallel
  workers interleave their print output and stack traces.
- Everything is seeded - regenerating reproduces the same output, so a
  diff against previous output is a real correctness check, not noise
  (used repeatedly to verify refactors are behaviour-preserving).
- Dependencies are managed with `uv` (`pyproject.toml` + `uv.lock`) -
  `uv sync --dev` installs everything including dev tooling. Run
  `uv run pytest` (fast smoke tests - generator layer runs the real
  seeded generator, dashboard-builder layer uses fixtures, no slow
  real-tool run needed) and `uv run ruff check .` (a deliberately lean
  rule set - real bugs only, not style) before considering a change
  done. `pre-commit install` wires ruff into `git commit` automatically.
  Not needed yet, but flagged: once the suite runs long enough that
  wall-clock time actually matters (currently ~3s for 13 tests - `pytest-
  xdist` would add more overhead than it saves), switch to `pytest-xdist`
  for parallel test execution rather than just tolerating a slower suite.
- **Whenever an actual bug is found** (not a design gap, not a missing
  feature - a case where the code produces a genuinely wrong result),
  add a test to `tests/` that reproduces it and fails against the
  current (buggy) code first, confirm it actually fails, then fix the
  bug and confirm the same test now passes. Applies repo-wide, not just
  to files `tests/` currently covers - a bug outside that scope still
  gets a new test alongside the fix, not just a fix. Don't retrofit this
  onto bugs already fixed earlier in this project's history; it's a
  going-forward convention.
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
