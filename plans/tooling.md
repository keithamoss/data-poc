# Testing & dev tooling

Real developer/testing tooling for this PoC that doesn't belong to any
one dataset or pipeline stage - the unified `mothman` CLI/TUI design (the
single item that outgrew `plans/wider.md` and justified this file, see
that file's own item #7 for the pointer) and the throwaway dev-only
scripts built to support building it. Split out of `plans/wider.md`
2026-09-19 (Keith's own explicit ask, once that one item had grown far
larger than anything else in that file) - see `plans/wider.md`'s own
intro for the account of its earlier, larger 2026-09-18 split into
`plans/dashboard.md`/`plans/data-generation.md`, which this mirrors at
smaller scale.

Status values: `todo` / `investigate` / `in-progress` / `parked` /
`done` / `superseded`. Every item also carries a Component tag - see
`plans/running-thoughts.md` item #10 for the shared taxonomy this and
`CHANGELOG.md` both use. IDs (`tooling-N`, referenced elsewhere as
`plans/tooling.md #N`) are permanent once assigned - never renumbered or
reused, even if an item is later retired, matching `qa_tools/common/
check_lifecycle.py`'s own `check_id` convention (same rule `plans/
wider.md`/`plans/dashboard.md`/etc. already state for their own items).

1. **[in-progress, 2026-09-19]** **[Testing & dev tooling]** A real,
   unified CLI for running this whole PoC - Keith's own framing, this
   session: "my goal is a human only uses the click CLI and not
   scripts." Superseded from the original `[parked, 2026-09-18]` scoping
   below (kept for the original motivation/friction account) by a long,
   multi-round design conversation the same day Thread A (the two
   on-demand `qa_tools/bdm/check_file.py` / `qa_tools/cp/check_delivery.py`
   Click CLIs, `plans/running-thoughts.md` #5) shipped - this item is the
   generalization of that same idea to every other entry point in the
   repo, reusing the already-decided `mothman` console-script name
   (`plans/wider.md` #5, the project-rename decision). **Not yet built**
   - Keith's own explicit standing instruction, still in force: "don't
   begin building until I give permission." What follows is the real,
   scoped design, ready to build once he gives the word; the two things
   actually built so far (dev screenshot tooling, this writeup itself)
   are called out separately at the end since neither counts as
   "beginning" the CLI.

   **Core shape, confirmed:**
   - Organized by dataset (bdm/cp) under a real interactive TUI - not
     just rich-formatted output, real arrow-key menus, confirmed
     feasible via `click`+`rich`/`rich-click` (already transitively
     present via dbt-core) plus a new `questionary` dependency for the
     menus themselves (built on `prompt_toolkit`).
   - Bare `mothman` (no args) always launches the interactive menu -
     the only entry point a human needs to remember.
   - Every command is BOTH flag-invocable AND TUI-navigable - no
     CLI-only/TUI-only split. (Earlier drafts this session proposed
     splitting "human TUI flows" from "flag-only Tier 2/3 commands";
     Keith's own correction: "just put everything in the TUI.")
   - Three-tier colour coding across every command/menu entry (Keith's
     own explicit ask - "make sure you use colors as well"): **Tier 1**
     (human, day-to-day) = green, **Tier 2** (machine/CI-only
     automation) = blue, **Tier 3** (developer debugging) =
     yellow/amber. **Tier 4** (see Population Data below) is its own,
     separately-flagged exploratory bucket. Every command/menu entry
     also gets a real 1-2 sentence description, not just a name.
   - A splash screen on TUI launch (Keith's own fun ask): a big
     `pyfiglet` block-letter "MOTHMAN" wordmark plus a hand-drawn ASCII
     moth (glowing red eyes, rendered in colour via `rich`), living in a
     new `cli/banner.py`, shown once before the main menu.
   - **"Promote"** replaces the earlier working term "commit" (rejected
     - collides with git). Promoting writes a run into the real,
     permanent `qa_results/` git history. It does **not** itself run any
     git command - the human still stages/commits/pushes separately,
     which is what already triggers CI's existing `deploy-pages.yml`
     rebuild-and-publish. No separate "publish" step - Keith: "let's
     just rely on the current thing where the git commit triggers CI
     rebuild."
   - After a run, the TUI offers to rebuild the dashboard and then
     either open the rebuilt HTML directly in the browser
     (`click.launch()`) or just prints the confirmation/path, operator's
     choice.

   **The Quality Assurance flow** (the flagship guided wizard): agency ->
   dataset -> (Child Protection only: full delivery vs. a single table,
   for partial resupplies - see the single-table design below) -> source
   mode [**Synthetic** / **Local files** / **S3**] -> browse/pick ->
   confirm the suggested dataset mapping -> run the real check chain ->
   rich-rendered report -> Promote? -> rebuild dashboard -> open in
   browser?. Three source modes are real, distinct entry points onto the
   same flow (Keith: "there's, there's three ways to run QA for a given
   data set"), not one mode with options:
   - **Synthetic** - pick an existing generated run, or generate a new
     one on the spot if none exists yet, then check it. Reference/
     baseline file for Evidently drift defaults to the last **Promoted**
     run in `qa_results/` history for that dataset (asks instead if
     nothing's been promoted yet).
   - **Local files** - a configured default root per dataset, browsed
     via `questionary.path()` (ready-made tab-completion browsing, no
     hand-built file picker needed). This is also where Thread A's two
     existing CLIs retire to: "humans will be using the browsable local
     files point, so they're never going to touch [check_file.py]
     directly" - their real logic (the dbt/Soda/datacontract-cli/
     Evidently chain against an already-downloaded file/folder) folds
     into this mode rather than staying as separate standalone commands.
   - **S3** - real `boto3` against real config, verified only via
     mocks (no real AWS access in this sandbox -
     `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` are literal
     `"proxy-injected"` here, same as Thread B). S3 location config
     lives as new `s3Source`/`localSource`/`arrivalPattern`
     `customProperties` entries on each dataset's own real ODCS contract
     YAML (a top-level `customProperties:` block already exists there,
     e.g. `currentDeliveryFormat`/`piiClassification` in
     `contract/bdm-birth-registrations-contract.yaml`).

   **Single-table Child Protection QA (design confirmed, not yet
   built)**: CP's real dbt models need all 6 tables present (`ref()`/
   `source()`), so a single-table check can't just run a reduced set -
   it automatically pulls the most recent **Promoted** state of the
   other 5 tables, builds a combined warehouse, and runs the full check
   suite including the cross-table checks. Grounded in real precedent
   already in this codebase: `generator/resupply.py` already models "a
   resupply might only touch a subset of tables, the rest carry forward
   unchanged" - this reuses that same idea for a human-driven partial
   delivery instead of a synthetic one.

   **Generate/Regenerate synthetic data** - its own Tier 1 top-level
   command group, wrapping the real, unmodified
   `generator.generate_runs`/`generator.generate_cp_runs` - including
   their existing resupply-chain and dirty-severity-preset simulation,
   confirmed NOT to be stripped down for this ("that should also include
   the... resupply stuff where it kind of has broken resupplies and so
   forth"). Confirmed (by reading `pipeline/orchestrate.py`) that
   `prepare_warehouse(regenerate=True)` already fuses "generate" and
   "build the combined warehouse" into one function - so this is one
   command, not two, correcting an earlier draft of this design that had
   wrongly split them. **Naming resolved, 2026-09-19**: an earlier
   session had settled on a shorter alternative to bare "generate" (to
   avoid reading as dev-only, since operators mostly run this against
   real-shaped data day to day) but the exact string was lost to context
   compaction; re-asked directly, and Keith's answer was to keep the
   full, self-explanatory phrase rather than a single-word rename - the
   command/menu label is **"Generate synthetic data"** (e.g.
   `mothman bdm generate-synthetic-data` / `mothman cp
   generate-synthetic-data` as the flag-invocable form), not a cute
   one-word verb. Explicitly saying "synthetic data" in the name is
   itself what avoids the dev-only-sounding ambiguity a bare "generate"
   had.

   **Tier 4 - Population Data**: `synthetic_data_generator/` (the
   separate, population-scale, cross-agency-identity-linked generator,
   not currently wired into the pipeline) gets its own top-level CLI
   entry point too, explicitly flagged exploratory in its own
   description - Keith wants to revisit and collapse it down to a single
   generator eventually, but happy to expose today's version in the
   meantime rather than hide it.

   **Debug group (Tier 3)**: `qa_tools/common/changelog.py` and similar
   internal/diagnostic modules that a human would otherwise have no way
   to run by hand - Keith: "if it wasn't in the CLI, how would a human
   debug it?" - live under a `mothman debug ...` subcommand group rather
   than being left out of the CLI entirely.

   **Full-pipeline run** stays a real command but Tier 2, not
   human-facing - "that's more there for like integration tests and for
   yourself and not there for the humans." Exact shape (a
   `mothman pipeline run` replacing `run_pipeline.sh` outright, vs.
   something narrower) still open - "I'm open to how we do that."

   **Trogon** (`Textualize/trogon`, auto-generates a Textual TUI from a
   Click app's own introspection) - researched, not adopted for the core
   guided flows: a good fit only for flag-heavy, non-branching commands,
   a poor fit for the Quality Assurance wizard's real conditional
   branching. Flagged as an optional future bonus (a `mothman tui`
   fallback) rather than anything in the phase plan below.

   **`questionary` chosen over alternatives on real, sourced project-
   health grounds** (Keith's own explicit due-diligence ask before
   committing to a new dependency): `PyInquirer` is effectively dead,
   built on the unmaintained `blessed`; `InquirerPy`'s last real commit
   was ~May 2022, last release (0.3.3) February 2023 - 3.5+ years stale
   as of this project's own "today," with a community fork existing
   because of that upstream inactivity; `questionary` is actively
   maintained (v2.1.0, updated ~1 month before this check, two named
   maintainers, live CI/dependabot activity). `questionary.path()` is
   also directly reusable for the Local-files source mode's browsing UI,
   rather than needing a hand-built file picker.

   **TUI design considerations, from real online research (2026-09-19,
   Keith's own explicit "one last check before we proceed" ask) - 5
   concrete additions to the Phase 1 design, sourced rather than
   guessed:**
   - **Non-TTY guard.** `questionary`/`prompt_toolkit` can crash outright
     in a non-terminal context (a script, some CI runners, an IDE
     console) rather than degrading gracefully. Every TUI entry point
     must check `sys.stdin.isatty()` before calling into `questionary`
     and fail with a clear message pointing at the equivalent
     flag-based invocation, not a stack trace - the wizard/flags duality
     already designed (every command both flag-invocable and
     TUI-navigable) only actually holds together with this guard in
     place.
   - **Never encode meaning in colour alone.** Every Tier
     (green/blue/amber) and status indicator needs a real text label
     alongside its colour, not colour as the only signal - real practice
     from GitHub CLI's own accessibility work. Respecting
     `NO_COLOR`/`FORCE_COLOR`/`CLICOLOR` env vars is `rich-click`'s
     already-default behaviour - explicitly don't override that default.
   - **Confirm-by-default on writes, with a bypass.** **Promote** (writes
     real, permanent `qa_results/` history) and **Generate/Regenerate
     synthetic data** (can overwrite local generated data) should both
     default to an explicit `[y/N]` confirmation (no as the safe
     default), with a `--yes` flag to bypass it for repeatable/scripted
     use - not removing the prompt, bypassing it. Worth a `--dry-run` on
     Promote specifically, showing what would be written without writing
     it, given how permanent that write is meant to be.
   - **Back-navigation gap in the QA wizard - a real, previously
     undesigned hole.** `questionary` prompts have no native "go back a
     step" support, and the agency -> dataset -> source-mode -> ...
     chain as designed has no way to back up if the operator picks
     wrong partway through. Fix: inject a "<- Back" choice into every
     `select()` menu in the chain, decided now rather than retrofitted
     after Phase 1 ships.
   - **Default output stays human-readable; raw/developer detail is
     opt-in.** Standard CLI guidance (clig.dev): don't show
     developer-only output by default. Applies to the Tier 3 debug
     commands and to the QA flow's own report - the default report stays
     the rich-rendered summary already designed, with raw dbt/Soda/
     datacontract-cli/Evidently tool output behind an explicit
     `--verbose`/`-v`.

   (Two other things researched came back as confirmation of what was
   already designed, not new work: the wizard/flags duality itself is a
   real, named pattern - "wizards and flags aren't opposites... the
   wizard is the flags with training wheels" - and the planned
   spinner-under-10s / step-progress-bar-otherwise split for `rich.
   progress.Progress` already matches real progress-indicator UX
   guidance.)

   **Build order (revised 2026-09-19 to fold in what Generate/Synthetic
   and single-table CP QA need to already exist):**
   1. **Phase 1** - `cli/` package scaffold; `mothman` console-script
      entry (`[project.scripts]`); add `questionary`/`pyfiglet` as real
      dependencies, promote `rich`/`rich-click` from transitive to
      direct; the splash screen; three-tier colour coding; the
      Quality Assurance flow against **Synthetic** source mode only;
      the Generate/Regenerate synthetic data command (needed by that
      same flow's "offer to generate if missing" step, so it can't ship
      later than Phase 1); Promote + dashboard rebuild + open-in-browser.
   2. **Phase 2** - Local-files QA source mode (`questionary.path()`);
      retire `qa_tools/bdm/check_file.py`/`qa_tools/cp/check_delivery.py`
      as standalone CLI entry points, folding their logic in here.
   3. **Phase 3** - S3 QA source mode (real `boto3`, mocked-only
      verification) + the new `s3Source`/`localSource`/`arrivalPattern`
      contract `customProperties`.
   4. **Phase 3.5** - single-table Child Protection QA (auto-pull last-
      Promoted state of the other 5 tables, full check suite) - depends
      on Phases 1-3's QA flow already existing to extend.
   5. **Phase 4** - reorg the remaining scripts into the CLI tree.
      **Real enumeration (2026-09-19), replacing an earlier vague "~20"
      estimate lost to context compaction** - every real script entry
      point in the repo (`grep -rl '__name__ == "__main__"'` across
      `qa_tools/`, `pipeline/`, `generator/`, `dashboard/`, `aws/`,
      `synthetic_data_generator/`), re-derived from the actual codebase
      rather than from memory, minus the 6 already named in Phases 1-3
      (`check_file.py`/`check_delivery.py`, `generate_runs.py`/
      `generate_cp_runs.py`, `orchestrate_bdm.py`/`orchestrate_cp.py`):
      25 remain. Grouped by real role, not just left as a flat list:
      - **Dashboard rebuild chain (Tier 2)**: `pipeline/
        build_dashboard_data.py`, `pipeline/build_cp_dashboard_data.py`,
        `qa_tools/bdm/build_results_from_history.py`, `qa_tools/cp/
        build_results_from_history.py`, `dashboard/
        embed_dashboard_data.py`, `dashboard/check_dashboard_renders.py`,
        `dashboard/snapshot_dashboard.py` (opt-in) - likely one
        `mothman dashboard rebuild` command wrapping the whole chain,
        not 7 separate ones.
      - **GitHub workflow/people automation (Tier 2)**: `qa_tools/
        common/ticket_sync.py`, `qa_tools/common/acceptance_sync.py`,
        `qa_tools/common/leaderboard.py`.
      - **CI validation gates (Tier 2)**: `qa_tools/common/
        validate_check_lifecycle.py`, `qa_tools/common/
        validate_requirements.py`.
      - **Per-tool debug runners (Tier 3, the real answer to "if it
        wasn't in the CLI, how would a human debug it")**: the 8
        individual `run_{dbt,soda,datacontract,evidently}_{bdm,cp}.py`
        modules (run one real tool in isolation against a run already on
        disk) plus `qa_tools/common/changelog.py` (already named),
        `qa_tools/bdm/build_per_run_warehouses.py`, `qa_tools/cp/
        build_cp_warehouses.py`, and `pipeline/load.py` - all under the
        `mothman debug` group.
      Rewrite the 3 GitHub Actions workflows to call `mothman`
      subcommands; retire `run_pipeline.sh`.
   6. **Phase 5** - Tier 4 Population Data command
      (`synthetic_data_generator/`), flagged exploratory.
   7. **Phase 6 (new, 2026-09-19)** - a recorded CLI/TUI demo embedded in
      the dashboard as a genuinely new top-level "Demo" tab (Keith's own
      call today - a new tab, not a small panel folded into an existing
      one; built after the core CLI exists and there's something real
      worth recording, not before). Real GitHub Pages hosting is static
      only - no backend to run a real interactive terminal behind a
      websocket - so this is a **recording**, not live interactivity:
      script real, deterministic keystrokes into the actual `mothman`
      CLI (same pty-capture technique as the dev screenshot tooling
      below), capture to an asciinema-format `.cast` file (plain
      timestamped JSON, no video encoding), and replay it with the
      static/offline-capable `asciinema-player` JS widget (no server, no
      asciinema.org account). A real recording of real CLI behaviour,
      not a mockup. New committed asset directory, analogous to the
      existing `dashboard/snapshots/*.html.gz` pattern (e.g.
      `dashboard/demos/*.cast`).

   **Already built, ahead of Phase 1 (approved by Keith as prep, not
   counted as "beginning" the CLI itself - it's throwaway dev tooling,
   never imported by the shipped pipeline/CLI)**: `scripts/dev/
   tui_screenshot.py` - spawns a real command in a real pseudo-terminal
   (stdlib `pty`), scripts fake keystrokes into it, and resolves the
   captured raw ANSI byte stream through a real terminal-emulator buffer
   (`pyte`, new dev-only dependency) into the actual on-screen character
   grid - necessary because `questionary`/`rich` redraw in place via
   cursor-movement/erase codes, so the raw byte stream alone isn't what a
   human would actually see. Renders that grid to HTML and screenshots it
   via this sandbox's pre-installed headless Chromium (pinned to its
   actual installed build, `chromium-1194`, via an explicit
   `executable_path`, since it lags the `playwright` package's own
   expected version here). Verified end to end against a small real
   `rich` demo (`scripts/dev/demo_rich_sample.py`) - a real screenshot
   was sent to Keith directly in chat. Will be reused through Phase 1+
   to show real TUI/CLI visuals as they're built, not just described.

   **Original scoping, 2026-09-18 (superseded by the above, kept for
   history):** A real CLI for running this PoC, built on Python's
   `click` library - Keith's own framing: "the goal is to give humans a
   user-friendly tool to use to run this PoC on real and fake data."
   Today's actual entry points, confirmed against `README.md`: BDM has
   one (`./run_pipeline.sh`, a plain shell script wrapping 4
   `uv run python3 -m ...` calls), but Child Protection has no wrapper at
   all - generating + running + building dashboard data for CP is 3
   separate, manually-typed commands, each needing the right module path
   remembered and run in the right order. Real friction for anyone other
   than whoever's been living in this repo daily.
