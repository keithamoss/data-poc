# Changelog

What changed about this PoC itself over time - new features, fixes, and
architectural decisions as they shipped. This is a curated summary of
the project's real git history, not a mechanical commit dump; see
`git log` for the full, unabridged record.

This is deliberately a different feed from two others already in the
dashboard: the header's "Recent activity" panel (who ran/published QA
against which dataset, when - drawn from `qa_results/` history) and a
check's own changelog inside its detail panel (that one check's
definition-change history). This page is about the tool itself.

Dates are real calendar dates this project has run on, not a synthetic
generation window - real Perth (AWST, UTC+8) calendar dates specifically,
since that's the timezone this project is actually worked in, not this
tool's own server-side UTC clock. Each entry also carries the real time
(same AWST clock) it actually shipped at, taken straight from its own
git commit history - entries within a date/category are sorted newest
first.

Each entry leads with a short, bold headline and one or more component
tags (the same 7-part taxonomy `plans/*.md` items use) - shown in the
dashboard's own Release Notes panel with a matching icon per component.
The text stays real and technical (module names, real numbers), just
edited for a punchier, friendlier read than a bare commit log.

## 2026-09-19

### Fixed
- **6:04pm** — **Playwright MCP Confirmed Working; the Real file:// Fix Is Local HTTPS** **[Docs & process]** **[Testing & dev tooling]**
  A fresh session confirmed the Playwright MCP server genuinely
  connects and works end to end (real process, real tool calls, real
  responses - `plans/wider.md` #10 has the full 3-way verification) -
  found along the way that the server blocks the `file://` protocol
  outright, so `requirements-reviewer`/`requirements-ux-critic`/
  `requirements-visual-critic` could never actually open the dashboard
  they're meant to review. Keith's own call: serve it locally over
  HTTPS rather than allow `file://` at the server (which would've
  granted access to the whole filesystem, not just this repo) or fall
  back to plain HTTP. New `scripts/dev/serve_dashboard_https.py` (a
  real throwaway self-signed cert + Python's stdlib `http.server`
  wrapped in TLS, verified end to end before being written into any
  agent's instructions) plus `.mcp.json`'s new `--ignore-https-errors`
  flag. All 3 agents now explicitly forbidden from navigating to
  `file://` URLs, pointed at the new script instead.

### Changed
- **5:50pm** — **Defense-in-Depth: permissionMode: plan on the 3 Pure-Advisory Agents** **[Docs & process]** **[Testing & dev tooling]**
  Keith's own ask: "defense in depth is important." Added the real,
  harness-enforced `permissionMode: plan` field to
  `requirements-scoper`/`requirements-architect`/`requirements-ux` -
  the 3 agents that never use `Bash` at all, so it's unambiguously safe
  (pure defense-in-depth, no functional change). Deliberately NOT
  applied to the other 3 (which need `Bash` for `mothman dashboard
  rebuild`) - real doc ambiguity found between 2 separate research
  passes on what `plan` mode actually does to Bash execution, flagged
  rather than guessed at. Also recorded 2 more standing conventions:
  a periodic check of the combined agent description-field token
  budget (checked today: ~1,100 tokens, nowhere near the real
  15,000-token warning threshold), and Claude Code's real spawn-time
  model-override capability, worth proactively suggesting rather than
  only used if remembered.

### Fixed
- **5:43pm** — **requirements-reviewer's Stale Playwright Instructions; a Real MCP Timing Gap Found** **[Docs & process]** **[Testing & dev tooling]**
  `requirements-reviewer` still described the pre-split ad hoc
  Bash+throwaway-script Playwright mechanism and had never been granted
  `mcp__playwright` at all - fixed to match `requirements-ux-critic`/
  `requirements-visual-critic`. `skills:` wired in selectively per
  agent, not blanket - `requirements-ux-critic` gets
  `web-design-guidelines` only, `requirements-visual-critic` gets both,
  `requirements-ux` gets neither (real reasoning in `plans/wider.md`
  #10). Re-testing the fix (spawning a real diagnostic subagent, not
  trusting the docs) found a much bigger thing: this session's own
  Playwright MCP server has never actually connected, because `ps aux`
  on the real running `claude` process shows a fixed `--mcp-config`
  file from before `.mcp.json` existed in this repo - a real,
  documented, one-time-at-session-start mechanism (confirmed against
  Claude Code's own cloud-environments docs), not a bug in what was
  built. The fix is correct and committed, but genuinely unverified
  from inside this session - needs confirming in a fresh session.

### Added
- **5:26pm** — **Two Real Claude Skills: frontend-design and web-design-guidelines** **[Docs & process]** **[Testing & dev tooling]**
  A genuinely different mechanism from the `requirements-*` subagents -
  Claude Skills, progressive-disclosure capability packages that
  activate contextually rather than separate-context-window delegates.
  Keith found a real Snyk article himself ("Top 8 Claude Skills for
  UI/UX Engineers"), picked 4 of its 8 real skills to bring in.
  2 are installed now: Anthropic's own `frontend-design` (vendored
  verbatim, byte-identical to upstream, confirmed via a real `diff` -
  pushes Claude away from generic "AI slop" aesthetics) and a real,
  adapted `web-design-guidelines` (Vercel's own 17-section UI-review
  ruleset, vendored offline per Keith's own explicit call rather than
  the upstream skill's live `WebFetch` on every run - same rationale as
  `dashboard/vendor/`'s own vendored assets). Both read directly from
  their real sources and reviewed before installing, not installed on
  the article's word alone. The other 2 (`UI/UX Pro Max`, `AccessLint`)
  are still pending - both bundle real executable code, mid-review when
  Keith asked to pause; nothing from that review was installed, and
  everything downloaded during it was deleted per his own ask.

### Changed
- **5:15pm** — **UX/Visual Critics Refined Against the Real cfisch3r/estimate Prompts** **[Docs & process]** **[Testing & dev tooling]**
  Keith asked directly whether `requirements-ux-critic`/
  `requirements-visual-critic` were copies of `cfisch3r/estimate`'s own
  real prompts - dug up the real raw files (after a first, HTML-page-
  based fetch gave contradictory results, flagged in `CLAUDE.md` as
  unreliable) and adopted 3 of the 5 real differences found: both
  agents' `tools:` frontmatter simplified from an explicit 12-15-tool
  list down to a single `mcp__playwright` whole-server grant;
  `requirements-visual-critic` now reads the dashboard's own real
  `:root{}` colour/radius custom properties before critiquing, instead
  of judging against generic best practice; added the "squint test"
  visual-hierarchy check. Kept `opus` (not `sonnet`) and kept relying on
  `docs/project-context-for-agents.md`'s general personas rather than
  structured per-review inputs - both Keith's own explicit calls. A
  third, unexplored agent in that repo, `doc-quality.md`, is parked as
  `plans/tooling.md` #4.

### Added
- **5:05pm** — **A Real Playwright MCP Server, and the UX/Visual Critique Split** **[Docs & process]** **[Testing & dev tooling]**
  A standalone, zero-hints test of `requirements-reviewer`'s post-build
  UX pass - pointed at the real built Requirements panel on a real
  mobile viewport with no mention of what to look for - found the real
  mobile overflow bug Keith had reported (and much more: it's actually a
  horizontal-pan bug, confirmed via real touch-event dispatch, with a
  real traced root cause at two specific template lines - full findings
  in `plans/dashboard.md` #12). Real, working evidence the isolated
  "read your own instructions, go in cold" design produces genuine
  findings. Off the back of that, Keith asked to adopt `cfisch3r/
  estimate`'s own `design-critic-ux`/`design-critic-visual` split for
  real: a new `.mcp.json` wires up a real Playwright MCP server
  (`@playwright/mcp@0.0.82`, pinned, pointed at this sandbox's own
  pre-installed Chromium, smoke-tested end to end), and the post-build
  UX pass is pulled entirely out of `requirements-reviewer` into 2 new
  dedicated agents - `requirements-ux-critic` (workflow/navigation) and
  `requirements-visual-critic` (spacing/overflow/dark-mode/interaction
  states) - each with its own real, considered subset of Playwright
  MCP's tool surface. `requirements-reviewer` itself goes back to purely
  functional/code-quality/security/coverage checks.

- **4:52pm** — **A Real CI Test Keeps the Component Taxonomy From Drifting** **[Docs & process]** **[Testing & dev tooling]**
  Keith's own question: now that the same 7-part
  component taxonomy shows up in 3 real places (`docs/components.md`,
  the dashboard template's own `COMPONENT_ICON`/`PLANS_ALL_COMPONENTS`
  consts, and `qa_tools/common/validate_requirements.py`'s
  `_COMPONENT_CODES`), how do we stop them drifting apart? A new
  `tests/test_component_taxonomy_consistency.py` fails CI if any of the
  3 ever disagree - verified with a real, deliberately-introduced typo
  first (confirmed failing), then reverted.

### Changed
- **4:49pm** — **requirements-scoper Now Actively Coaches Non-Functional Requirements** **[Docs & process]**
  Keith's own words: "I feel like I'm not good at doing non-functional
  requirements... I'd like it to prompt me from different angles." The
  single generic non-functional-requirements question was replaced with
  10 real, concrete angles - adapted from the real ISO/IEC 25010
  software-quality-characteristics taxonomy, but each one translated
  into a question grounded in this project's own actual domain rather
  than left abstract (performance, scalability, reliability, security,
  privacy/data sensitivity, compatibility/portability, maintainability,
  observability/auditability, compliance/retention, cost - e.g. privacy
  asks "would this requirement's own assumptions still hold if this were
  ever pointed at real production Birth Registrations/Child Protection
  data," not a generic "any privacy concerns?"). The agent judges which
  angles are plausibly relevant per requirement and asks about those via
  batched `AskUserQuestion` calls, not a mechanical 10-question
  interrogation every time.

### Added
- **4:44pm** — **A Real Reference Doc For This Project's Own Component Taxonomy** **[Docs & process]**
  `docs/components.md` - Keith's own ask: the 7-part component
  taxonomy `plans/*.md`/`CHANGELOG.md`/`requirements.yaml`'s own ids
  already tag things with had never been written up in one place with
  real names, codes, scope, and file/directory ownership. Now it is:
  one section per component (`GEN`/`QAC`/`PIPE`/`DASH`/`GHUB`/`TEST`/
  `DOCS`), each with what it owns, what's in scope, and - just as
  important - what's explicitly out of scope against its neighbours
  (e.g. `QAC` owns check definitions and what red/amber/green means;
  `PIPE` owns how a run gets committed/published; `DASH` only ever
  renders what another component already computed). Wired into the
  requirements-analysis agents that actually need it:
  `requirements-scoper` reads it to pick a new requirement's id code,
  `requirements-architect` reads it for its own cross-component
  blast-radius check, and `docs/project-context-for-agents.md` now
  points to it.

### Changed
- **4:38pm** — **Requirements Register: Component-Coded IDs, Written Dates, Scoper Now Asks About NFRs** **[Docs & process]**
  Three more real refinements to the requirements
  register (`requirements.yaml`) and `requirements-scoper`, Keith's own
  follow-up asks before the agent system's first real run. Every id is
  now `REQ-<CODE>-NNN`, where `<CODE>` is a real 3-4 letter code
  (`GEN`/`QAC`/`PIPE`/`DASH`/`GHUB`/`TEST`/`DOCS`) for the same 7-part
  component taxonomy `plans/*.md`/this changelog already tag things
  with - `qa_tools/common/validate_requirements.py`'s own
  `_COMPONENT_CODES` is the single source of truth. Keith's explicit
  follow-up call: drop the old bare `REQ-NNN` shape entirely rather than
  grandfather it, so all 22 real, pre-existing entries were migrated the
  same day, each keeping its own original number and picking up
  whichever real component best matches it (checked against how the
  equivalent feature is actually tagged elsewhere in this changelog).
  A new optional `date_written` field (real `YYYY-MM-DD`) gives the
  register a real chronological trail, rendered next to each
  requirement's title in the dashboard's own Requirements panel.
  `requirements-scoper.md` now has a real second, explicit step for
  non-functional requirements - proposing its own from this project's
  standing conventions, as before, but now also genuinely asking Keith
  (via `AskUserQuestion`) whether there's anything else only he'd know
  to raise, rather than relying on its own read of the codebase alone.
- **4:27pm** — **Requirements-Analysis Agents: Real Polish Bar, Real Role Depth, Post-Build UX Pass**
  **[Docs & process]** Three real refinements to the same-day agent
  system below, before its first real run - Keith held off running it to
  give more input first. A real, named polish standard now lives in
  `requirements-ux.md`/`requirements-reviewer.md`: Keith's own words,
  dashboard UX polished "to the level that Apple goes for their
  products... a UX where you don't even realize it's polished because of
  everything else." `docs/project-context-for-agents.md` gained real
  role depth (not just labels) - the data steward's real frustration
  point (noise before reaching what matters), the accountable data
  owner's real concern (trend/defensibility), the pipeline maintainer's
  opposite need (wants the raw detail the steward doesn't) - a real
  tension the same dashboard has to serve both sides of. And the
  "banked for later" post-build UX pass got pulled forward into
  `requirements-reviewer` now: a real, separate visual-QA pass for
  dashboard-facing requirements, a busy/moderately-attentive persona,
  real screenshots as evidence, checked against the same Apple-level
  bar.
- **4:23pm** — **A Requirements-Analysis Agent System, Built With Keith As A Joint Design** **[Docs &
  process]** Four new real Claude Code subagents (`.claude/agents/*.md`):
  `requirements-scoper` (turns a raw idea into small, self-contained
  EARS-format requirements plus a draft `plans/*.md` entry, asking as
  many rounds of clarifying questions as it takes), `requirements-
  architect` (a deliberately "simple" pre-build check - duplication/
  overlap against the real codebase, fit within `mothman`'s command
  structure, cross-component blast radius, security, code-quality
  expectations for the builder), `requirements-ux` (dashboard-only
  consistency/workflow-fit review, advisory, alongside the architect),
  and `requirements-reviewer` (a merged reviewer+QA role checking
  finished work against both the requirement and the architect's
  quality bar - reads code, drives a real headless Playwright browser
  via `Bash`, checks real test coverage, strictly read-only, reports
  back rather than editing anything itself).
  Built on real research, not assumed: Claude Code's own published
  sub-agent guidance and Anthropic's multi-agent architecture patterns,
  plus real-world precedent (`zhsama/claude-sub-agent`'s 5-stage spec
  pipeline validated the overall shape and independently confirmed EARS
  as a real convention; `www.codecentric.de`'s "Don't Let Your AI
  Cheat" post supplied the real isolation mechanism and three concrete
  reviewer-prompt instructions now built directly into
  `requirements-reviewer.md`). Where this design deliberately diverges
  from that precedent (forced human approval in the loop, a strictly
  read-only reviewer, no task-planner stage given how small this
  project keeps its own tasks) was each a real Keith decision, not a
  default.
  Also: a new `docs/project-context-for-agents.md` (drafted from
  existing `CLAUDE.md`/`README.md` content, for Keith to correct rather
  than dictated from scratch) these four agents read first, and 5 new
  optional `requirements.yaml` fields (`source`/
  `non_functional_requirements`/`dependencies`/`open_questions`/
  `evidence`) with real CI enforcement, including a genuine
  dangling-reference check on `dependencies` - found and fixed a real
  bug live while validating: the parser's own `source: ""` default was
  tripping the new validator check, failing all 22 real committed
  requirements at once. Regression test added, confirmed failing
  against the pre-fix code first.
  Not yet exercised end-to-end on a real feature - see `plans/wider.md`
  #10 for the full design write-up.

### Changed
- **3:17pm** — **Mothman's Eyes Now Actually Blink** **[Testing & dev tooling]** Keith noticed the CLI/TUI
  splash banner's "glowing red eyes" were a static colour, not actually
  pulsing, and asked directly whether they blink for real - they
  didn't. Confirmed `rich` (already a direct dependency) genuinely
  supports a real `blink` style attribute, mapping to the real ANSI SGR
  blink escape code (verified in the actual rendered output, not just
  Rich's own API) - added it to both eye spans. Whether it actually
  renders as a blink depends on the terminal emulator, same as any real
  ANSI blink code; most modern ones support it.
- **2:49pm** — **Demo Tab: 25% Slower Again** **[Dashboard]** Keith's own follow-up after reloading the
  real published page: `speed: 0.5` (the earlier half-speed fix) still
  read too fast. Another 25% slower on top of that (`speed: 0.4` -
  speed is an inverse multiplier, so `0.5 / 1.25 = 0.4`).

### Added
- **3:09pm** — **Amber Supplies Can Now Be Rejected, Not Just Accepted** **[Dashboard]** **[QA checks &
  contract]** Resolves a real governance question `plans/conceptual-
  design.md` Thread A had left deliberately parked: should a
  persistently-amber dataset ever need a human DECISION, or is amber
  just a standing warning? Keith's own call, scoped via a real
  `AskUserQuestion` round: yes - an explicit per-run human decision,
  accept or reject. Reject mirrors `/accept` exactly (a real `/reject`
  comment on the same GitHub ticket, same per-run window-matching, no
  new infrastructure) and - the smaller, safer option - a rejected
  run's pill still stays amber, same as accept's own "never silently
  repaint the pill" design; only the badge differs ("✗ Rejected by
  `<user>`" vs "✓ Accepted by `<user>`"). If a run's window somehow
  carries both a real `/accept` and a real `/reject`, whichever comment
  is most recent wins, regardless of which command it was.
  `qa_tools/common/acceptance_sync.py` generalized from accept-only to
  `match_decisions()`/`build_decisions()`; the dashboard's own
  `ACCEPTANCES` const renamed `AMBER_DECISIONS`. Found and fixed a
  real, separate bug live while adding test coverage against real
  current committed history: most of today's real runs share an
  `arrived_date` with another real run (352 real BDM runs, only 123
  distinct dates), and the window-matching logic's own documented
  intent ("ties resolve to whichever sorts first") turned out not to
  match what the code actually did - the first tied run got a
  zero-width, structurally unmatchable window, so a same-day comment
  silently resolved to the wrong run. Fixed to match the documented
  intent for real. 12 new/updated Python tests (3 of them regression
  tests for the window bug, confirmed failing against the pre-fix code
  first), 3 new real-browser e2e tests, verified with a real Playwright
  screenshot of both badge kinds rendering correctly side by side.
- **2:44pm** — **Leaderboard Now Shows Everyone, Not Just Ticket-Closers** **[Dashboard]** **[QA checks &
  contract]** Keith caught it live on the real published page: the
  Leaderboard panel showed nobody at all, despite real people already
  being in `contract/people.yaml` - correct at the time (nobody had
  closed a real GitHub QA ticket yet, and `build_leaderboard()` only
  ever showed people with an actual streak), but not what he wanted to
  see. Every real person currently assigned to a dataset
  (`qa_tools.common.people.assignees_for()`, the same roster the
  dashboard's "Owned by" badge already uses) now appears for that
  dataset at `streak=0` when they have no clean-resolution streak yet,
  rather than the whole panel silently degrading to empty; a real
  streak holder no longer assigned to a dataset still appears too (a
  real earned streak isn't erased by a later org-chart change). Found
  and fixed a real duplicate-row bug live while verifying this via a
  real Playwright screenshot of the built panel: Keith himself holds
  two real roles on Registry Services (`qa` and `manager`), and
  `assignees_for()` returns one raw record per role, so without
  deduping he showed up as both "#1" and "#2" for the same dataset.
  6 new tests (`qa_tools/common/leaderboard.py`'s own
  `build_leaderboard()`, now also parameterized on the real
  `DATASET_AGENCY` mapping), one of them a regression test for the
  duplicate-role bug, confirmed failing against the pre-fix code first.
- **2:33pm** — **Plans Tab: Filters Now Persist In The URL** **[Dashboard]** The Plans tab's search box and
  status/component/file filter chips now round-trip through
  `location.search` (`q=`/`status=`/`component=`/`file=`, comma-joined
  for multi-select), written via `history.replaceState` on every real
  filter mutation so rapid chip clicks don't spam browser history - a
  filtered Plans URL can now be bookmarked, shared, or linked to
  directly and lands back in the same filtered state. Status/component
  chips were also restyled to use the exact same `.pill` markup and
  colour classes real plan-item chips already use (green for Done, the
  per-component tag colour, etc.) instead of their own separate flat
  style, so the filter bar now visually matches what it's filtering.
  Found a real jsdom test-harness gotcha while writing coverage for
  this: stubbing `matchMedia` *after* `new JSDOM()` construction is too
  late for a URL that already restores filter state on load - the
  page's own top-level script calls `currentTheme()` (which touches
  `matchMedia`) before reaching later top-level `const` declarations
  like `SIDE_PANELS`, so a late stub lets that call throw and silently
  aborts the script partway through, leaving those later consts
  permanently in their TDZ even though the (hoisted) functions
  referencing them stay callable - surfaces as a confusing "Cannot
  access 'SIDE_PANELS' before initialization" that looks URL-shape-
  specific but isn't. Fixed by using jsdom's `beforeParse` hook, matching
  `tests-js/support/loadDashboard.js`'s own established pattern. 11 new
  tests.

### Fixed
- **2:33pm** — **Drawer Close Icon Wasn't Vertically Centered** **[Dashboard]** The circular "×" close button on
  every side panel/drawer was missing flexbox centering, leaving the
  icon visibly offset within its circle. Confirmed with a real Playwright
  screenshot before and after.
- **2:00pm** — **Real Terminal Warning Text Baked Into The Demo Recording** **[Dashboard]** **[Testing & dev
  tooling]** Keith caught it: the published Demo tab recording had a
  literal "WARNING: your terminal doesn't support cursor position
  requests (CPR)." printed right into the captured output - a real
  artifact of the recording environment (the synthetic pty never
  answered prompt_toolkit's real cursor-position-request probe), not
  something a real `mothman` user in a real terminal would ever see.
  Fixed at the actual source - `scripts/dev/record_cast.py`'s pty loop
  now answers that probe for real, immediately, exactly like any real
  terminal emulator would - and re-recorded `dashboard/demos/
  qa_wizard.cast` with the fix, confirmed clean (0 occurrences, was 1)
  via a real Playwright screenshot of the Demo tab mid-playback.

### Added
- **1:57pm** — **Demo Tab Polish: Half-Speed Playback, Glowing Red Moth Eyes** **[Dashboard]** **[Testing & dev
  tooling]** Two small follow-ups from actually watching the real Demo
  tab recording: playback now runs at half speed (the real recorded
  pace read too fast to follow on first watch), and the TUI splash
  screen's ASCII moth finally gets the glowing red eyes its own
  original design text always described but the code never actually
  rendered - built with `rich.text.Text` spans rather than a markup
  string, since a literal backslash next to a `[red]...[/red]` tag
  breaks rich's parser and this art is full of backslashes.
- **1:49pm** — **A Real Recorded Demo, Right In The Dashboard** **[Dashboard]** A genuinely new top-level "Demo"
  tab, playing back a real recording of the actual `mothman` CLI/TUI (the
  Quality Assurance wizard - splash screen, menu navigation, the real
  4-tool check chain actually running, the real report, declining to
  Promote) - not a mockup, a real pseudo-terminal session captured with a
  new `scripts/dev/record_cast.py` dev tool. Playback via a vendored,
  self-hosted `asciinema-player` (no CDN dependency, works offline).
  Found and fixed two real bugs along the way: a timing gap in the
  recording tool itself (prompt_toolkit's own real cursor-position-probe
  delay could silently drop a scripted key), and a genuinely separate,
  previously-latent one in the site build - `dashboard/fonts/` had
  silently never been copied into the deployed `_site/`, so the live
  published dashboard had quietly been falling back to system fonts
  instead of its real self-hosted ones this whole time, invisible
  because a missing font file just degrades rather than erroring. Both
  `fonts/` and the new `vendor/` directory are now correctly deployed.
- **1:23pm** — **mothman CLI Phase 5: Population Data Command** **[Testing & dev tooling]** `mothman population`
  (Tier 4, explicitly exploratory) wraps `synthetic_data_generator/`'s
  own real argparse CLI - a population-scale (up to millions),
  cross-agency-identity-linked synthetic dataset spanning 3 fictional
  agencies (Registry Services/BDM, Child & Family Safety, Education),
  still genuinely NOT wired into the real BDM/CP QA pipeline. Found and
  fixed a real, genuine bug live while smoke-testing `--dirty amber` for
  the first time: `synthetic_data_generator/generate.py`'s `build()`
  was calling `apply_cp_notifications_presets()` with a stale 3-arg
  signature that had drifted out of sync with the real function
  (`generator/dirty.py` had since grown `clients_df`/`workers_df`
  params for dangling-FK injection, updated in `generator/
  generate_cp_runs.py`'s own call site but never in this unwired
  sibling) - exactly the kind of drift a previously-parked item had
  already flagged as a risk. Fixed and covered by a real regression
  test, confirmed failing against the pre-fix code first with the exact
  real `TypeError`. 6 new tests, real small-population smoke tests
  (including a cross-agency identity resolution check - the same
  synthetic person's name/DOB matching across all 3 agencies' own ID
  schemes), `uv run pytest`/`ruff check .` both clean.
- **1:13pm** — **mothman CLI Phase 4: Reorganized Every Remaining Script Into the CLI** **[Testing & dev tooling]**
  `mothman dashboard`/`mothman github`/`mothman debug`/`mothman pipeline` -
  4 new command groups replacing the last ~24 bare script entry points
  (the dashboard rebuild chain, GitHub ticket/acceptance/leaderboard
  sync, 8 retired per-tool debug scripts folded into 4 dataset-
  parameterized `debug run-*` commands, and the full real-tool batch
  pipeline). Rewrote both GitHub Actions workflows that used to call
  bare `python3 -m` invocations, and retired `run_pipeline.sh` in favour
  of `mothman pipeline run`. Found and fixed two real gaps along the
  way: `orchestrate_bdm.py`'s/`orchestrate_cp.py`'s own full-manifest
  batch functions had never actually been wrapped by any earlier phase
  despite the plan claiming otherwise (only single-run mode was); and
  `uv sync` had been silently failing to install the real `mothman`
  console script this whole project's history (`pyproject.toml` was
  missing a real `[build-system]`) - every `mothman` invocation before
  today's fix was quietly falling through to a `python3 -m cli.app`
  fallback instead. 35 new tests, full local suite + lint + JS tests all
  clean, and a repo-wide sweep confirms no bare `qa_tools`/`pipeline`/
  `generator`/`dashboard` invocation is reachable from outside
  `mothman`'s own implementation any more.
- **12:45pm** — **mothman CLI Phase 3.5: Single-Table Child Protection QA** **[Testing & dev tooling]** `mothman cp
  qa --table <table> --file <csv>` / `--s3-key <key>` - check a real
  partial resupply (one table re-sent after a fix) without needing the
  whole 6-table delivery on hand. The other 5 tables auto-pull from the
  last Promoted CP run's own local data, which doubles as the Evidently
  drift baseline too - no separate reference flag needed. Verified with
  a real end-to-end smoke test against real local data, deliberately
  mismatched across two different runs' tables: a real 177-check run
  (120 pass/7 warn/50 fail-or-error) confirming both that the combined
  warehouse genuinely builds and that a real cross-run mismatch produces
  real cross-table referential-integrity failures rather than silently
  passing - exactly the scenario this feature exists to catch.
- **12:32pm** — **mothman CLI Phase 3: S3 QA Source Mode** **[Testing & dev tooling]** `mothman bdm qa --s3-key
  <key> --s3-reference-key <key>` and `mothman cp qa --s3-delivery
  <prefix> --s3-reference-delivery <prefix>` - browse the real raw-data
  landing bucket directly and run the same real dbt-core/Soda Core/
  datacontract-cli/Evidently chain against whatever's there, before
  you've even pulled it down yourself. Real `boto3`, verified only via a
  mocked client (no real AWS access in this sandbox) - S3 mode is
  "download, then Local files mode" internally, reusing Phase 2's own
  check-running logic rather than a third parallel code path. A real,
  previously-flagged fork got resolved along the way, not silently:
  `docs/aws-event-driven-mvp-design.md` had proposed a real
  `arrivalPattern` ODCS contract extension overnight but deliberately
  kept it OUT of the real contract files - unverified that it wouldn't
  break real dbt/Soda/datacontract-cli parsing. Flagged to Keith before
  touching the real contract; his call was to verify then wire it all
  in now that real tool access exists - confirmed via a real
  `DataContract(...).lint()` pass, the real datacontract-cli
  integration suite, and the real `validate_check_lifecycle` CI gate,
  all clean, before landing `s3Source`/`localSource`/`arrivalPattern`
  in both real `contract/*.yaml` files.
- **11:47am** — **Checks Categorisation (Grouped by Data-Quality Dimension)** **[Dashboard UI]** Every check in
  the column drawer now groups into a collapsible section by data-quality
  category (Completeness/Uniqueness/Conformity/Consistency/Timeliness),
  Keith's own ask. Reused the ODCS contract's own already-existing,
  human-authored `dimension:` vocabulary rather than inventing a rival
  one - a real discovery made while scoping this: all 89 real
  datacontract-cli checks and every real check result across all 8
  `run_*.py` modules already carried a matching `dimension` value.
  Found and fixed a real pre-existing inconsistency alongside this:
  dbt's/Soda's own dimension dicts used `"validity"` where the contract
  already correctly said `"conformity"` for the same checks - normalized
  everywhere and backfilled into 370 already-committed `qa_results/`
  history files (2,838 records, `verified` only, `raw_output` untouched).
  `qa_tools/common/check_lifecycle.py` gained a real, validated `category`
  field on every check's own definition (165 new `category:` lines
  across dbt/Soda YAML, contract reused its native `dimension:` field
  directly) - verified with zero mismatches against real committed
  results. A real bug caught and fixed along the way: grouping reorders
  the check list, which broke the column drawer's old DOM-order-based
  click handler - fixed via a `data-idx` attribute that travels with
  each check through grouping. 5 new Vitest tests, verified with a real
  Playwright pass against the real built dashboard (zero console
  errors). `uv run pytest` (511 passing) and `npm test` (104 passing)
  both clean.
- **11:21am** — **mothman CLI Phase 2: Local Files QA Source Mode** **[Testing & dev tooling]** `mothman bdm qa
  --file <csv> --reference-file <csv>` and `mothman cp qa --folder <dir>
  --reference-folder <dir>` - run the real check chain against a file/
  delivery you've already downloaded, not tied to any synthetic
  manifest, both flag-invocable and TUI-navigable (a real "Which
  source?" picker now precedes the run picker in both datasets' QA
  flows). The two standalone CLIs this replaces,
  `qa_tools/bdm/check_file.py`/`qa_tools/cp/check_delivery.py`, are
  **deleted** - their logic folded verbatim into `cli/bdm.py`/`cli/cp.py`
  (mothman is the only entry point now). Two real bugs caught proactively
  before they could bite (the same manifest-clobbering bug class Phase 1
  found live): local-file checks can clobber the real batch manifest the
  same way Phase 1's bug did, fixed by extracting a shared
  `_run_single_preserving_manifest()` helper; and a real ordering bug
  where calling the timestamp-embedding `run_id_from_path()` twice for
  the same check would silently produce two different run_ids. Verified
  against real local data outside any manifest (a real BDM CSV, 79
  checks; a real CP 6-table delivery, 177 checks), with the real batch
  manifests confirmed untouched afterward. `uv run pytest`/`ruff` clean
  (511 passing).
- **11:08am** — **mothman CLI Phase 1 Complete: Child Protection QA** **[Testing & dev tooling]** `cli/cp.py` -
  `mothman cp generate-synthetic-data` and `mothman cp qa
  [--run-id/--reference-run-id/--commit]`, the Child Protection
  counterpart to the Birth Registrations commands below, on the same
  wizard/flags duality. Adapted for CP's real shape: a 6-table-per-run
  collection rather than one CSV, so `run_check()` loads both the target
  and reference run's 6 tables into their own per-run warehouses (via
  `build_cp_warehouses.add_table_to_run()`) before calling
  `orchestrate_cp.run_single()` - the same pattern `qa_tools/cp/
  check_delivery.py`'s own `_load_delivery()` already established for
  local-folder CP checks, reused here against an existing Synthetic
  manifest run instead of an arbitrary folder. `cli/app.py`'s TUI main
  menu now offers a real Birth Registrations/Child Protection dataset
  picker on both the QA and generate-synthetic-data flows. Verified
  against the real dbt-core/Soda Core/datacontract-cli/Evidently chain
  (177 real checks, 0 fail, against real existing local data) and via a
  real pty screenshot of the new TUI dataset picker. `plans/tooling.md`
  #1's Phase 1 is now fully done.
- **11:00am** — **mothman CLI Phase 1: TUI Shell + Birth Registrations QA** **[Testing & dev tooling]** The
  real start of the unified `mothman` CLI/TUI (`plans/tooling.md` #1),
  built on Keith's own explicit go-ahead. `cli/app.py` (the root
  `mothman` Click group, bare-invocation TUI main menu with a real
  pyfiglet/ASCII-moth splash screen), `cli/common.py` (the non-TTY
  guard, confirm-by-default+`--yes`, back-navigation-aware menus, the
  tmp-dir-first Promote pattern), and `cli/bdm.py` (`generate-synthetic-
  data` and `qa [--run-id/--reference-run-id/--commit]`, both real,
  flag-invocable AND TUI-navigable from one implementation). Verified
  against the real dbt-core/Soda Core/datacontract-cli/Evidently chain,
  not mocked, and the real arrow-key TUI navigation confirmed via a real
  pty screenshot. A thin `./mothman` wrapper script gives a real command
  today without needing this repo properly packaged (a bigger, separate
  lift than Phase 1 needs - `[project.scripts]` is declared in
  `pyproject.toml` for when that happens). `questionary`/`pyfiglet`
  added as real dependencies; `rich`/`rich-click` promoted from
  transitive to direct. A real bug found and fixed along the way: a
  manual smoke test actually corrupted the real, local `data/raw/
  manifest.json` from 176 entries down to 1 -
  `orchestrate_bdm.run_single()`'s own manifest-overwriting side effect
  (correct for its real AWS Lambda use case, a real collision against
  an existing full batch manifest) - fixed in `cli/bdm.py`'s own
  `run_check()`, regression-tested. Child Protection's own `mothman cp`
  commands are still open.
- **10:35am** — **Clickable Header Logo + Mothman SVG Mark** **[Dashboard UI]** Clicking the header logo/
  wordmark now returns to the homepage, matching the existing header nav
  buttons' own pattern - the wordmark is a real `<button>` now (keyboard/
  focus-visible accessible), not a plain, inert div. Also replaced the
  plain "DA" text badge with a small, friendly Mothman SVG mark - rounded
  wings, simple antennae, two eyes cut through via `fill-rule="evenodd"`
  so they show the badge's own accent gradient rather than needing a
  second hardcoded colour. Drawn in `currentColor`, so it automatically
  gets the same light/dark theme contrast the text badge already relied
  on. Iterated visually via real Playwright screenshots (both themes, at
  the actual 38px production size) before embedding, rather than
  guessing SVG path coordinates blind.

### Fixed
- **10:31am** — **Numbered Lists In Plans Tab** **[Dashboard UI]** Real bug, found from Keith's own
  dashboard report: expanding an item card (e.g. `plans/tooling.md`
  #1's own "Build order" phase list) word-joined every numbered list
  line into one illegible run-on paragraph - `dashboard/plans_md.py`'s
  parser only recognised `-`/`*` bullets as list-item boundaries, never
  `1. `/`2. ` ordered markers. Fixed on both sides: the parser now
  preserves numbered lines as their own list items, and the JS renderer
  (`renderPlansMarkdown`) renders an all-numbered block as a real
  `<ol>`, with a mixed block (a numbered phase with its own nested
  bullet sub-items) safely falling back to `<ul>` rather than losing
  structure again. Regression tests added on both sides, confirmed
  failing against the buggy code first.

### Added
- **9:59am** — **TUI/CLI Screenshot Capture Tooling** **[Testing & dev tooling]** A real dev-only helper
  (`scripts/dev/tui_screenshot.py`) for showing actual rendered CLI/TUI
  output during development, ahead of the mothman CLI build itself
  (still gated on Keith's own explicit go-ahead - see `plans/wider.md`
  #7's rewrite below). Spawns a real command in a real pseudo-terminal
  (stdlib `pty`), scripts keystrokes into it, and resolves the raw ANSI
  byte stream through a real terminal-emulator buffer (`pyte`, new
  dev-only dependency) into the actual on-screen character grid -
  necessary because `questionary`/`rich`-style TUIs redraw in place via
  cursor-movement/erase codes, so the raw byte stream alone isn't what a
  human would actually see on screen. Renders that grid to HTML and
  screenshots it via this sandbox's pre-installed headless Chromium
  (pinned to its actual installed `chromium-1194` build via an explicit
  `executable_path`, since it lags the `playwright` package's own
  expected version here). Verified end to end against a small real
  `rich` demo script; never imported by the shipped pipeline/CLI.

### Changed
- **8:22am** — **On-Demand Checks Rebuilt With Click** **[Pipeline & publishing]** **[Testing & dev tooling]** The two on-demand check CLIs added
  minutes earlier switched from argparse to real Click commands (Keith's
  own explicit ask). Real, immediate benefit: `click.Path(exists=True)`
  now rejects a typo'd file/folder path before any real QA tool ever
  runs, rather than failing partway through a real dbt/Soda run. `click`
  added as a real, direct dependency (previously only present
  transitively). Tests now drive both CLIs through `click.testing.
  CliRunner`, Click's own standard test harness.

### Added
- **8:16am** — **On-Demand File Checks** **[Pipeline & publishing]** **[Docs & process]** Two new CLIs (`qa_tools/bdm/check_file.py`/
  `qa_tools/cp/check_delivery.py`) for real, ad hoc QA checks against a
  file or delivery you've already pulled down yourself - Thread A of
  the staff-adoption item, scoped with Keith this morning: staff already
  download data from S3/local storage manually and are CLI-comfortable,
  so this fits that existing motion (`uv run python3 -m
  qa_tools.bdm.check_file <csv> --reference-csv <known-good.csv>`)
  rather than replacing it. Reuses the exact same single-arrival
  orchestration entry points built for last night's AWS MVP design
  (`orchestrate_bdm.run_single()`/`orchestrate_cp.run_single()`), run
  locally instead of from an S3 event. Defaults to a throwaway,
  local-only check - nothing touches the real, permanent `qa_results/`
  history unless `--commit` is passed. A real bug found and fixed while
  testing this: a Python default-argument-value gotcha (bound once at
  import time) meant a couple of calls could silently ignore a
  redirected output directory and write into this repo's own real,
  gitignored data folders instead of a test's tmp dir - caught,
  cleaned up, and fixed at the source.
- **12:30am** — **AWS Event-Driven MVP Design** **[Pipeline & publishing]** **[Docs & process]** A real design doc plus real, unit-tested code for
  triggering this pipeline automatically from S3 file arrivals instead
  of a manually-kicked-off local script (`docs/aws-event-driven-mvp-
  design.md`) - built overnight per Keith's own explicit instruction,
  for his morning review, not yet deployed (no real AWS access exists
  in this environment). Covers file-arrival pattern matching for
  individually-arriving, nested-folder, and zip-archive files; Child
  Protection's explicit-completion-signal design for waiting on all 6
  tables before running cross-table checks; new single-arrival
  orchestration entry points (`orchestrate_bdm.run_single()`/
  `orchestrate_cp.run_single()`) that reuse the existing 4-real-tool
  evaluation logic unchanged; and a clearly-flagged recommendation (not
  a silent decision) on how a Lambda-produced result reaches the
  committed `qa_results/` git history without Lambda ever holding
  git-write credentials. Two real architectural gaps surfaced and got
  fixed while writing the integration tests against the real local dbt/
  Soda/datacontract-cli/Evidently chain - see the design doc's own "Two
  more real gaps found while actually building this" section. AWS CDK
  (Python) infra and both Lambda handlers are real, reviewed code,
  written correctly per their respective documented APIs but genuinely
  unverified - never `cdk synth`'d, never invoked by a real S3 event.

## 2026-09-18

### Added
- **11:44pm** — **Parallel Test Runs** **[Testing & dev tooling]** `pytest-xdist` adopted for a real, measured ~2x faster full local test
  run (`uv run pytest -n auto` - ~59s vs ~122s serial on a 4-core
  machine), not just installed on faith. Found and fixed a real bug
  along the way: two dbt-based integration tests shared a literal run
  id that mapped to dbt's own shared `dbt_project/target/` output
  directory - safe only because tests ran one at a time before, and a
  genuine collision once run in parallel (reproduced directly, not
  assumed). Fixed by co-locating each run's dbt scratch output with its
  own DuckDB file instead of a fixed, repo-shared path - a small
  production improvement in its own right, not just a test workaround.
  Plain `uv run pytest` stays serial by default for easier single-test
  debugging.
- **11:25pm** — **Plans Tab** **[Dashboard UI]** **[Docs & process]** A real "Plans" page inside the dashboard - browse, search, and filter this
  project's own `plans/*.md` planning memory (status/component tags on
  every item and Thread) without leaving the live site. A genuinely new
  top-level page, not another header side-panel - the real content
  volume (124 entries) needed room a cramped drawer couldn't give it.
  Every plan-file item and Thread/Phase section now carries a closed
  status and the same component taxonomy `CHANGELOG.md` entries do,
  fixing 17 items that had quietly slipped through an earlier retrofit
  pass with no real date.
- **11:07pm** — **Friendlier Release Notes** **[Dashboard UI]** **[Docs & process]** Every entry on this page now leads with a bold headline, an icon, and
  the real component(s) it touches - not just a wall of technical
  prose. All 46 prior entries retrofitted to the new format (a full
  rewrite, not forward-only), same as the `plans/*.md` status/component
  tagging done earlier tonight - one consistent tagging scheme across
  both of this project's history feeds.
- **9:12pm** — **Leaderboard Launch** **[Dashboard UI]** **[GitHub workflow & people]** A real leaderboard: whoever's kept a dataset out of the red the
  longest, per dataset, gets a real streak count (amber doesn't break
  it, only a real red run does). Shows real people by name once added
  to `contract/people.yaml` - a bare email is never shown on this
  public page.
- **8:51pm** — **Dataset Ownership** **[GitHub workflow & people]** A real people/roles config: GitHub tickets now get assigned to
  whoever's actually responsible for that dataset (or its whole
  agency, as a fallback) once real people are added, and the dashboard
  shows an "Owned by" badge on the agency/dataset pages. Ships with no
  real people in it yet - a config for Keith to fill in, not guessed.
- **8:39pm** — **Amber Acceptance** **[GitHub workflow & people]** A real way to accept an amber supply: commenting `/accept` on that
  dataset's own GitHub QA ticket now records a real acknowledgment
  against the exact supply that was current at the time - no ID to
  type or copy. The supply itself stays amber (accepting never
  silently reads as green); a small badge shows who accepted it,
  linking to the real comment. An amber-only dataset now gets a real
  ticket too, not just a red one. Publishes within roughly a minute or
  two of the comment, not the next unrelated push.
- **8:11pm** — **GitHub Deep Links** **[GitHub workflow & people]** **[Dashboard UI]** Real deep links from the dashboard back into GitHub: clicking a check
  now opens its actual source (the real dbt test/Soda check/datacontract
  rule/Evidently preset that defines it, at the exact line), and clicking
  a dataset or agency opens its real QA code folder - both pinned to the
  exact commit the dashboard was built from, so a link always shows
  exactly what was true when that page was published.
- **8:00pm** — **Readable URLs** **[Dashboard UI]** Human-readable dashboard URLs: the address bar now shows a real path
  (`#/agency/.../dataset/.../column/.../check/...`) instead of an opaque
  block of URL-encoded JSON - every drill-down level, the 4 header side
  panels, and the check-comparison picker are all genuinely shareable
  links now, not just the top-level page.
- **6:52pm** — **CP Resupply Sim** **[Data generation]** Real resupply-chain simulation for Child Protection: a red quarterly
  delivery now gets a real, later resupply attempt (a genuinely slower
  turnaround than Birth Registrations' own daily-feed curve - a full
  collection re-extract realistically takes longer to correct), the
  same chain-orchestration engine Birth Registrations already uses,
  generalized to a whole delivery's worth of tables at once rather than
  a single file. Visible in the live dashboard's supply-history view
  with no changes to that view at all - it already derived chains
  purely from real, observable status, dataset-agnostic by design.
- **1:02pm** — **Timestamped Notes** **[Docs & process]** A real timestamp against every entry on this page (real AWST
  git-commit time, never fabricated), sorted newest-first within each
  date's own category - also shown in the dashboard's own Release
  Notes panel, not just this markdown file.
- **12:24pm** — **Ticketing MVP** **[GitHub workflow & people]** A GitHub Issues ticketing MVP: a new, separate write-permitted
  workflow that opens a real GitHub Issue per real dataset (birth
  registrations, and each of Child Protection's six real tables
  separately) the moment that dataset's worst-of-every-check status
  goes red, and keeps commenting with its live status on every
  subsequent run - still red, or resolved - without ever auto-closing
  the ticket, since closing stays a human decision. Runs automatically
  on every relevant push - confirmed live: all seven real tickets
  opened for real once turned on, each reflecting a genuine finding
  (a real sibling-record mismatch for Birth Registrations, a real
  dirty synthetic delivery for Child Protection's six tables), not a
  false alarm.
- **11:23am** — **Ticket Badge** **[GitHub workflow & people]** **[Dashboard UI]** A small badge on each dataset's own tile linking straight to its
  real, currently-open GitHub Issue (when one exists) - embedded at
  dashboard build time from a real, read-only GitHub API call, same
  treatment every other embedded feed on the page already gets.
- **8:15am** — **Requirements Register** **[Docs & process]** **[Testing & dev tooling]** A live requirements register: real user stories with MoSCoW priority
  and implementation status, each one's completion backed by a real,
  CI-enforced link to the test that actually verifies it - a claimed
  "built" requirement with no real test behind it now fails CI, not
  just a documentation exercise.
- **7:45am** — **Supply Status Rollup** **[Dashboard UI]** A real aggregate red/amber/green status shown against every entry in
  a dataset's supply history - the worst status among every check
  across every column for that specific delivery - and a genuine "N
  days since the previous supply" counter on resupply attempts.
- **12:58am** — **Test Coverage Push** **[Testing & dev tooling]** Full integration test coverage against all four real QA tools, a unit
  test suite for the dashboard's own inline JavaScript, and real-browser
  end-to-end tests (as-of date picking, supply-history drill-down, dark
  mode) - plus a measured code-coverage floor now enforced on every
  push, not just a speed-focused smoke-test suite.

### Fixed
- **7:37pm** — **Test Isolation Fix** **[Testing & dev tooling]** The BDM/CP generator test suites shared their output directory with real
  production data: running `tests/test_generate_runs.py`/`tests/
  test_generate_cp_runs.py` wrote straight into `data/raw/`/`data/
  cp_raw/`, the same directories `./run_pipeline.sh` and the real
  orchestrators read from and write to - harmless in outcome (generation
  is fully deterministic) but a real coupling between test execution and
  production state that shouldn't have existed. Both test files now
  point the generator at an isolated temp directory for the duration of
  the run.
- **7:22pm** — **Changelog Speedup** **[Pipeline & publishing]** A real git-history-walking performance bug: building the "who
  published QA results, when" changelog feed used to spawn one real
  `git show` subprocess per commit that ever touched a dataset's
  `qa_results/` history, diffing that commit's entire changed tree -
  cost that grew with real repo history, measured at several seconds
  and a real, noticeable chunk of the test suite's own runtime once
  enough of that history had built up. Down to a fraction of a second.
- **12:24pm** — **Ticket Labels Fix** **[GitHub workflow & people]** The GitHub Issues ticketing MVP's very first live run: opening a
  ticket needs its labels to already exist on the repo, which neither
  did yet - now created automatically the first time they're needed.
- **12:16pm** — **Threshold Bugs Fixed** **[QA checks & contract]** Two real threshold-encoding bugs behind the dashboard's red/amber/
  green status: a check with no fail threshold configured used to
  silently read as failing almost every run (a missing threshold
  defaulted to zero rather than "can't fail"), and a handful of real
  contract rules with a genuine non-zero tolerance had that real
  threshold discarded entirely.
- **12:16pm** — **Arrival Stats Fix** **[Pipeline & publishing]** A local build failure: re-running the real check tools without first
  refreshing the combined warehouse left one column's arrival stats
  looking up a run that wasn't there yet.
- **6:28am** — **CI Health Fixes** **[Testing & dev tooling]** Two real continuous-integration failures that had gone unnoticed for
  hours: GitHub's own runner resolving a newer Python version than this
  project had ever been tested against, and a missing one-time setup
  step for one of the real check tools.
- **6:12am** — **Resupply Grouping Fix** **[Dashboard UI]** A resupply-history grouping bug: a resupply landing weeks late used
  to get lumped in with an unrelated delivery that merely happened to
  arrive on the same calendar day.

### Changed
- **9:37pm** — **Leaderboard Redesign** **[Dashboard UI]** **[GitHub workflow & people]** Redesigned the leaderboard to celebrate resolving a dataset from red
  back to green, not just running QA on it - a real person's own streak
  of GitHub QA tickets closed in a row without being reopened, tracked
  via a real GitHub API call rather than committed QA-run history. The
  earlier "current not-red run streak" design (shipped 9:12pm the same
  day) had nothing left to credit once QA running itself becomes
  automated, since closing a ticket stays the one action in this system
  that's always a human decision.
- **7:08pm** — **CP Sim Calibration** **[Data generation]** Child Protection's resupply simulation, calibrated further: a dirty
  delivery now only fails 2-3 of its 6 real tables, not all of them,
  and the most recent delivery is no longer forced red - both random,
  same as every other delivery.
- **12:01pm** — **YAML Safety Net** **[Testing & dev tooling]** A real YAML syntax mistake in a hand-edited contract file went
  uncaught until the next tool run parsed it - a real `check-yaml`
  pre-commit check now catches this class of mistake at commit time.
- **7:45am** — **Resupply Chain Rework** **[QA checks & contract]** How a resupply chain gets identified: no longer inferred from
  internal bookkeeping about which delivery a resupply was "for," but
  derived purely from a delivery's real cadence-aware timing and each
  arrival's own real pass/fail outcome - closer to what could actually
  be observed from a real production feed, where a resupply never
  arrives labelled as such.

## 2026-09-17

### Added
- **8:23pm** — **Stale-Safe Drilldown** **[Dashboard UI]** Child Protection's dataset detail page now stays fully drillable even
  when its most recent supply falls outside the "as of" staleness
  window: real historical columns, checks, and trend charts stay
  browsable, just without misleading current-status colors.
- **7:33pm** — **Sparklines Everywhere** **[Dashboard UI]** Sparklines on the Tier 2 (agency dataset list) and Tier 3 (column
  grid) views, not just the Executive tier - then redesigned to show
  each tier's own aggregate failing-check RATE over time (not one
  arbitrarily-picked check's raw value, and not a raw count, which
  would stop being comparable the moment a check gets added or retired
  mid-history).
- **5:54pm** — **Trend Chart Markers** **[Dashboard UI]** Trend-chart gap and marker rework: a real visual split (with a small
  double-tick glyph) where a check's definition changed in a breaking
  way; a subtler marker where it changed non-breaking; a separate
  dashed connector for a run a check has no result for, distinct from
  either kind of definition change.
- **4:38pm** — **Dark Mode** **[Dashboard UI]** A dark mode toggle.
- **3:28pm** — **Check History Panel** **[Dashboard UI]** Changelog and plain-English description sections inside each check's
  own detail panel, alongside its existing trend chart and comparison
  view.
- **1:40pm** — **Retired Checks Toggle** **[Dashboard UI]** **[QA checks & contract]** A retired-checks toggle in the current-status view: a check that's
  been formally retired stays fully visible in its column's check list,
  behind a toggle, without ever being able to turn that column's status
  amber or red again.
- **9:14am** — **Activity Feed** **[Dashboard UI]** The Executive-tier "Recent activity" panel - a feed of who published
  QA results for which dataset, and when.
- **7:42am** — **As-Of Date Picker** **[Pipeline & publishing]** **[Dashboard UI]** The cadence-aware "as of" date picker: pick any date and see the
  data asset exactly as it stood then, with a staleness tolerance so
  an overdue dataset reads as "no data" rather than silently showing
  old data as current.

### Fixed
- **8:00pm** — **Freshness Check Fix** **[QA checks & contract]** The three `date_of_birth` freshness checks (dbt, Soda, datacontract-
  cli) that read permanently red - they were comparing against the real
  wall-clock date, which drifted further from this fixture's dates
  every day since it was last regenerated. Re-anchored to each run's
  own date instead, paired with a new occasional-staleness defect so
  the checks have something real to catch either way.
- **7:13pm** — **Snapshot Picker Fix** **[Dashboard UI]** The live dashboard's "past snapshots" picker, which had never
  actually shown a real snapshot on the published site - the archived
  snapshot files were there, the picker's own list of them just never
  made it into the deployed page.

### Changed
- **6:44pm** — **CP Cadence Re-Anchor** **[Data generation]** Child Protection's quarterly delivery cadence re-anchored to
  February/May/August/November.

## 2026-09-16

### Added
- **9:44pm** — **Publishing Architecture** **[Pipeline & publishing]** The whole publishing/history architecture this PoC now runs on: every
  real QA run's raw tool output committed to `qa_results/` as a
  permanent record; the dashboard rebuilt purely from that committed
  history, with no live database access required; a CI-gated publish
  pipeline (build, validate, deploy) with no manual local-publish path;
  and a permanent, globally-unique ID for every real check, so a
  check's history survives even once its definition changes or it's
  formally retired.
- **8:39am** — **Time-Travel Snapshots** **[Dashboard UI]** "Time travel" dashboard snapshots - a full, self-contained, gzip-
  archived copy of the dashboard taken at a point in time, openable
  years later with nothing but a browser - plus a picker panel, built
  into the live dashboard, for browsing past snapshots.
- **7:33am** — **Run Comparison View** **[Dashboard UI]** A status pill, a run-picker, and a real side-by-side run comparison
  added to the check-detail panel.

## 2026-09-15

### Added
- **9:10pm** — **Full Check Triplication** **[QA checks & contract]** Full triplication of the check battery: every check that a
  supporting tool can express, implemented in that tool - not just one
  or two illustrative examples per dimension.

### Fixed
- **10:22pm** — **dbt Failure-Count Bug** **[QA checks & contract]** A real dbt-core bug found running this project's own checks for
  real: a test whose true failure count was nonzero but under every
  configured threshold was silently reporting zero failures. Worked
  around by re-deriving the true count from dbt's own audit table
  instead of trusting its summary field.

## 2026-09-14

### Added
- **11:21pm** — **Failing Sample IDs** **[Dashboard UI]** **[QA checks & contract]** Real per-row failing sample identifiers (never full row content) in
  the check-detail panel, so a failing check shows which specific
  records tripped it.
- **9:04pm** — **Test Tooling Setup** **[Testing & dev tooling]** `uv`, `ruff`, and a real `pytest` smoke-test suite.
- **7:44am** — **Resupply Simulation** **[Data generation]** Resupply-chain simulation: a delivery with a real red failing check
  gets a simulated resupply request and a later, possibly-still-broken
  resupply attempt - matching how this actually plays out in practice.

### Changed
- **8:50pm** — **Real Tools Only** **[QA checks & contract]** Removed the four hand-written "equivalent" check engines entirely -
  built early on to demonstrate the pipeline before real tool access
  existed, now fully superseded by the real tools they stood in for.

## 2026-09-13

### Added
- **9:19pm** — **Child Protection Added** **[QA checks & contract]** **[Data generation]** Child Protection added as a second real dataset collection, alongside
  Birth Registrations, complete with its own cross-table business-rule
  checks.
- **8:06pm** — **Dashboard Goes Live** **[Pipeline & publishing]** The dashboard published live to GitHub Pages.
- **6:16pm** — **Project Kickoff** **[QA checks & contract]** Real dbt-core, Soda Core, datacontract-cli, and
  Evidently AI wired in, in place of this project's original
  hand-written stand-ins (built during an earlier session with no
  package-registry access).
