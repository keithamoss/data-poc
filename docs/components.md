# Components

The real, 7-part taxonomy this whole project tags things with -
`CHANGELOG.md` entries, `plans/*.md` items, and (2026-09-19,
`plans/wider.md` #10) `requirements.yaml`'s own id scheme
(`REQ-<CODE>-NNN`). Written up in its own file at Keith's own explicit
request, 2026-09-19: it existed informally as a set of tags before this,
but nothing spelled out what each one actually covers, what its short
code is, or where its real boundaries sit against its neighbours - this
file is that single reference, for humans and for the requirements-
analysis agents alike (`requirements-scoper` especially needs this to
pick the right code when drafting a new requirement's id).

**The single source of truth for the CODE itself** (the exact string,
used in real ids and validated by CI) is
`qa_tools/common/validate_requirements.py`'s own `_COMPONENT_CODES`
dict - if this file and that dict ever disagree, the dict wins; fix this
file to match it, not the other way round. This file exists to carry
everything the dict doesn't: the real scope, the real file/directory
ownership, and the real in/out-of-scope boundary against each
neighbouring component.

A requirement, a `plans/*.md` item, or a `CHANGELOG.md` entry can
legitimately touch more than one component (most real features do) -
`plans/*.md`/`CHANGELOG.md` tag with as many as genuinely apply, but a
requirement's own `id` can only carry one code, so `requirements-scoper`
has to make a single best-fit call (see each requirement's own judgement
call precedent in `requirements.yaml`'s 22 pre-2026-09-19 entries,
migrated 2026-09-19 - `plans/wider.md` #10 has the full migration note).
When something genuinely straddles two components, pick whichever one
the requirement's own PRIMARY user-facing outcome belongs to, not
whichever file happens to need editing.

---

## `GEN` — Data generation

**What it is:** synthetic data generation standing in for what would be
real production data in an actual deployment - both the real, wired-in
generator and the separate, exploratory population-scale one.

**Owns:** `generator/` (Birth Registrations - `daily_batch.py`,
`generate_runs.py`, `resupply.py`, `dirty.py`, `names_au.py`,
`presentation.py` - plus Child Protection's own run generation),
`synthetic_data_generator/` (the separate, population-scale,
cross-agency-identity-linked generator, `mothman population`, Tier 4/
exploratory, not currently wired into the real pipeline).

**In scope:** producing seeded, reproducible synthetic data; dirty-data
injection (nulls, FK dangling, format drift); resupply/cadence
simulation (a late or corrected delivery arriving after an initial
failure); anything about *how the fake data itself gets made*.

**Out of scope:** what counts as a passing/failing check against that
data (`QAC`), how a generated run's results get stored or published
(`PIPE`), how any of it gets displayed (`DASH`).

---

## `QAC` — QA checks & contract

**What it is:** the real quality/schema rules themselves and the four
real tools that evaluate them - the actual substance of "is this data
good."

**Owns:** `contract/` (the real ODCS contract + SodaCL checks -
`data-asset.yaml`, `people.yaml`'s own role definitions aside),
`dbt_project/`, `qa_tools/bdm/` and `qa_tools/cp/` (the real dbt-core/
Soda Core/datacontract-cli/Evidently AI run + evaluate logic and each
one's own `dataset_stats.py`), `qa_tools/common/check_lifecycle.py`
and `validate_check_lifecycle.py` (check definition/retirement rules),
`qa_tools/common/dataset_status.py` and the resupply-chain-identification
logic it implements (`plans/conceptual-design.md`'s own real decisions
on this).

**In scope:** check definitions and their lifecycle metadata (`check_id`/
`introduced_date`/`changelog`); what red/amber/green actually means for
a column/dataset; cross-tool result reconciliation; the resupply-chain
model (a real QA-status concept, not a display concept).

**Out of scope:** how a run's raw output gets committed/persisted
(`PIPE`), how results render in the UI (`DASH`), what happens once a
human acts on a bad result - a ticket, an accept/reject decision
(`GHUB`).

---

## `PIPE` — Pipeline & publishing

**What it is:** orchestration, the permanent committed QA history, and
the CI-gated publish path - the plumbing between "a check ran" and "the
public dashboard reflects it."

**Owns:** `pipeline/` (`orchestrate.py`'s warehouse build,
`build_dashboard_data.py`/`build_cp_dashboard_data.py`), `qa_tools/
common/qa_results_writer.py`/`qa_results_reader.py`/`git_identity.py`/
`changelog.py`/`cadence.py`/`parallel_orchestrate.py`, `qa_tools/bdm/
build_results_from_history.py`/`orchestrate_bdm.py` and their Child
Protection equivalents, `.github/workflows/deploy-pages.yml`, `aws/`
(the event-driven MVP design, real code + doc, not yet the live
pipeline).

**In scope:** how a real run's raw output gets committed to
`qa_results/` and rebuilt from it later with no live tool re-run; the
CI-gated, no-manual-publish path; the cadence-aware "as of" offset
mechanism itself (the underlying computation, not the date-picker UI);
on-demand/event-driven triggering.

**Out of scope:** the check definitions being run (`QAC`), how any of
this gets displayed (`DASH`), the actual generation of the data being
piped through (`GEN`).

---

## `DASH` — Dashboard UI

**What it is:** the single-file static reporting dashboard itself -
everything about how a person actually sees and navigates this data
asset's QA state.

**Owns:** `dashboard/qa-reporting-dashboard.template.html` (the real,
hand-authored UI - every panel: current status/drill-down, Requirements,
Activity, Changelog release notes, Plans, Demo, Snapshots, Leaderboard,
dark mode, the as-of date picker's own UI), `dashboard/requirements_yaml.py`/
`changelog_md.py`/`plans_md.py` (thin parsers feeding the template, no
computation of their own), `dashboard/embed_dashboard_data.py`/
`check_dashboard_renders.py`/`snapshot_dashboard.py`, `dashboard/vendor/`,
`dashboard/fonts/`, `dashboard/demos/`, `dashboard/snapshots/`.

**In scope:** visual presentation, layout, interaction, navigation,
consistency of UI patterns, rendering data that another component
already computed.

**Out of scope:** computing the data being rendered (whichever component
actually owns that concept - `QAC`/`PIPE`/`GHUB`/`GEN`/`DOCS` depending
on what it is); `DASH` only ever consumes.

---

## `GHUB` — GitHub workflow & people

**What it is:** turning a QA result into real, tracked human work -
tickets, ownership, and recorded governance decisions - plus the config
of who's actually involved.

**Owns:** `qa_tools/common/ticket_sync.py`/`ticket_status.py`/
`github_links.py`/`people.py`/`acceptance_sync.py`/`leaderboard.py`,
`contract/people.yaml`, `.github/workflows/ticket-sync.yml`.

**In scope:** opening/updating/commenting on real GitHub Issues for QA
events; routing a ticket to the right person; the real `/accept`/
`/reject` amber-governance decision workflow (a GitHub-comment-driven
mechanism, even though its *result* is displayed on the dashboard);
who's assigned to what.

**Out of scope:** the underlying QA status that triggers a ticket
(`QAC`), rendering any of this in the UI (`DASH`).

---

## `TEST` — Testing & dev tooling

**What it is:** how this repo actually gets run, developed, and
verified - not the product itself, the tooling around building it.

**Owns:** `cli/` (the whole `mothman` CLI/TUI shell - `app.py`/
`common.py`/`banner.py`, and each Tier's own command group file, even
though a given subcommand's own underlying work may belong to a
different component - e.g. `mothman dashboard embed` wraps `DASH` work,
but the CLI mechanism itself is `TEST`), `tests/`, `tests-js/`,
`scripts/dev/` (dev-only, throwaway-adjacent helpers - `record_cast.py`,
`tui_screenshot.py`), `.github/workflows/test.yml`, `pyproject.toml`'s
test/lint/coverage config.

**In scope:** the test suites themselves, CI test workflow, dev-only
scripts that help build/verify the product, coverage enforcement,
`ruff`/`pre-commit` config.

**Out of scope:** the product features under test (whichever component
they actually belong to) - a new test for a `QAC` check is still `QAC`
work with test coverage, not automatically `TEST`; this code is
`TEST`-tagged when the THING BEING BUILT is the tooling/testing
infrastructure itself (e.g. adding `pytest-xdist`, a new CLI command
group, a new dev screenshot helper).

---

## `DOCS` — Docs & process

**What it is:** this project's own planning memory, conventions, and
documentation - the working process, not the product it's building.

**Owns:** `plans/*.md`, `CLAUDE.md`, `README.md`, `docs/` (this file
included), `CHANGELOG.md`, `requirements.yaml`'s own schema/tooling
(as opposed to an individual requirement's *content*, which is tagged by
whatever product area that requirement is actually about - see
`REQ-DOCS-014`, "a live requirements register," for the one legitimately
self-referential case: the register's own existence is a `DOCS` concern).

**In scope:** process/convention decisions, planning and requirements
infrastructure, research docs, this project's own real design history.

**Out of scope:** product features (whichever component they belong to).

---

## Not owned by any one component

`data/`, `data/raw/`, `data/cp_raw/`, `reports/*.json` - gitignored,
fully regenerated artifacts, not source of truth for anything and not
conceptually "owned" the way a real, committed directory is. `qa_results/`
IS owned (by `PIPE` - the committed publishing/history architecture),
despite also being data, because it's the real, permanent source of
truth `PIPE`'s own design exists to protect.
