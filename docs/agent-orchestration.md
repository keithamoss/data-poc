# Orchestrating the `delivery-*` subagents

How the main session (this one, or any future one) should actually run
the `delivery-*` requirements-analysis pipeline - the real sequence,
what each stage needs as input, what runs in parallel vs. not, and how
Keith can invoke it. Written 2026-09-19 at Keith's own explicit ask,
right after the `requirements-*` → `delivery-*` rename, so the renamed
roster doesn't just sit there unexplained.

## The roster

| Agent | Phase | Surface | What it checks |
|---|---|---|---|
| `delivery-scoper` | Pre-build | Any | Turns a raw idea into structured requirements (EARS acceptance criteria + a `plans/*.md`-style entry), coaching Keith through NFRs he wouldn't otherwise think to specify |
| `delivery-architect` | Pre-build | Any | Technical fit - duplication/overlap, `mothman` command-group fit, which real components it touches, security/code-quality considerations, an optional lightweight architecture note |
| `delivery-dashboard-ux` | Pre-build | Dashboard | UX fit against existing dashboard patterns, workflow/information-architecture fit, SPA/URL design fit, HCI/psychology grounding (`docs/hci-ux-psychology.md`) |
| `delivery-cli-ux` | Pre-build | CLI/TUI | The same UX-fit job as `delivery-dashboard-ux`, for `mothman`'s own wizard + plain CLI usage instead |
| `delivery-critic` | Post-build | Any | Functional/code-level check against the requirement's own acceptance criteria, `delivery-architect`'s expectations, and real test coverage. Does NOT check UX/visual polish |
| `delivery-dashboard-ux-critic` | Post-build | Dashboard | Real, persona-driven UX/workflow critique of the finished dashboard, via a real browser (Playwright MCP) |
| `delivery-dashboard-visual-critic` | Post-build | Dashboard | Real visual-polish critique (spacing, overflow, dark mode, interaction states) of the finished dashboard, via the same real browser |
| `delivery-cli-ux-critic` | Post-build | CLI/TUI | Real UX critique of the finished `mothman` command, via a real pty session (`scripts/dev/tui_drive.py`) |

## The real sequence

```
                    delivery-scoper
                    (Keith's raw idea -> structured requirement)
                            |
              +-------------+-------------+
              |                           |
      delivery-architect      delivery-dashboard-ux  OR  delivery-cli-ux
      (always runs)           (whichever surface the requirement touches -
                                neither, if it's not UI-facing at all)

              \_____________  _____________/
                            \/
              Keith reviews both notes, confirms the approach
                            |
                    [ the actual build happens -
                      the main session does this directly,
                      no agent does the building itself ]
                            |
                    delivery-critic
                    (always runs - functional/acceptance-criteria check)
                            |
              +-------------+-------------+
              |                           |
   dashboard-facing?              CLI/TUI-facing?
              |                           |
   delivery-dashboard-ux-critic   delivery-cli-ux-critic
   THEN (not parallel - see below)
   delivery-dashboard-visual-critic
```

**Pre-build parallelism**: `delivery-architect` and the relevant UX
reviewer (`delivery-dashboard-ux` or `delivery-cli-ux`) both only need
`delivery-scoper`'s own draft as input, not each other's output - safe
to run them at the same time.

**Post-build parallelism - one real, hard-won constraint**:
`delivery-dashboard-ux-critic` and `delivery-dashboard-visual-critic`
both drive the SAME shared Playwright MCP browser server. Run them
sequentially, not concurrently - `claude/playwright-mcp-verify-b2t4nb`
deliberately avoided running them in parallel for exactly this reason
("so the two don't contend for the same MCP browser," `plans/wider.md`
#10's own verification write-up). `delivery-critic` (its own Playwright
MCP session, but a functional check, not UX) and `delivery-cli-ux-critic`
(a completely separate mechanism, a real pty via `tui_drive.py`, not
Playwright at all) don't share that constraint - either can run
alongside the dashboard critic pair without contention.

## What each stage actually needs

- **`delivery-scoper`** needs: Keith's own raw idea, in whatever form he
  gives it (a few sentences, a dictated stream of thought). Nothing else
  - it does its own reading of `docs/components.md`/existing
  `requirements.yaml` entries to check for a duplicate id.
- **`delivery-architect`** / **`delivery-dashboard-ux`** / **`delivery-
  cli-ux`** need: `delivery-scoper`'s own drafted requirement(s) -
  nothing about HOW Keith or the main session thinks it should be built,
  only the requirement itself (implementation reasoning at this stage
  would bias the pre-build check).
- **`delivery-critic`** needs: the requirement's own EARS acceptance
  criteria, `delivery-architect`'s own expectations note, and the
  finished, already-built result. Deliberately NOT given the scoper's or
  the builder's own reasoning - same "don't teach to the test" isolation
  `delivery-critic.md`'s own docstring explains.
- **`delivery-dashboard-ux-critic`** / **`delivery-dashboard-visual-
  critic`** / **`delivery-cli-ux-critic`** need: the finished, built
  result (already on disk/already runnable), and optionally the matching
  pre-build UX note (`delivery-dashboard-ux`'s or `delivery-cli-ux`'s
  own) to check for drift from what was agreed - not required, but a
  real standard to check against when available.

## When the full pipeline is (and isn't) the right call

This is for a genuinely new, not-yet-scoped feature or requirement -
not every change. A small, well-understood fix, a doc correction, a
dev-tooling hardening pass, or anything this session would normally just
do directly after a quick scoping conversation with Keith doesn't need
`delivery-scoper` at all (most of this session's own work today -
the SPA guide, the HCI/psychology grounding, the port-collision fix -
happened this way, not through the formal pipeline). Reach for the
pipeline when the idea is big/ambiguous enough to need real EARS
acceptance criteria and a dedicated pre-build sanity check before
committing engineering time to it.

## How Keith can instruct this

Plain language is the normal path - describe the idea or the thing to
review, and the main session picks the right agent(s) and sequence from
this doc rather than needing exact agent names memorized. Concretely:

- **"I've got an idea: ..."** / **"let's scope something new"** → starts
  at `delivery-scoper`, then the main session runs `delivery-architect` +
  the relevant UX reviewer once the draft exists, and brings both notes
  back before anything gets built.
- **"review what we just built"** / **"check that's actually right"**
  → `delivery-critic`, plus the relevant post-build UX critic(s) for
  whatever surface changed - the main session infers which from what
  was actually touched, same as picking the pre-build reviewer.
- **Naming an agent directly** (e.g. "run delivery-architect on this
  specific question," "just get the visual critic to look at the
  Requirements panel") always works too, and is the right move to skip
  straight to one stage - a standalone, zero-hints run (no other
  agent's notes handed in) when testing whether an agent independently
  finds something, the same pattern used to first validate
  `delivery-dashboard-ux-critic` against the real mobile-overflow bug.
- **A specific model for one run** - Claude Code's own real spawn-time
  override (`CLAUDE.md`'s own standing reminder) works here too: "run
  delivery-critic with Opus" or "use a cheaper model for this one" both
  take precedence over an agent file's own default `model:` for that
  one invocation.

If a request doesn't cleanly map to one stage or surface, the main
session should ask rather than guess which agent(s) to run - same "ask,
don't assume" standard every agent here already holds itself to.
