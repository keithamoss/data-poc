# Demo recordings

`qa_wizard.cast` is a real asciinema v2 recording of the actual `mothman`
CLI/TUI — a real pty, real keystrokes, real output, including the real
dbt-core/Soda Core/datacontract-cli/Evidently chain genuinely executing.
Not a mockup and not sped up. `dashboard/embed_dashboard_data.py` embeds
its raw text into the dashboard template's `const DEMO_CAST`, and the
Demo tab plays it back with the vendored `asciinema-player`
(`dashboard/vendor/`). See `plans/tooling.md` #1 Phase 6 for how that
tab was built.

## The recorded script

This file exists because `scripts/dev/record_cast.py`'s own docstring
pointed at it for "the actual recorded script" and it had never been
written — so the exact `--step` sequence behind the committed `.cast`
was not recorded anywhere, and the only way to know what produced it was
to decode the recording. Keep this in sync when re-recording.

Regenerate (needs real BDM synthetic data on disk first — a fresh clone
has none, since `data/` is gitignored):

```bash
uv run mothman bdm generate-synthetic-data --yes

uv run python3 scripts/dev/record_cast.py \
  --out dashboard/demos/qa_wizard.cast \
  --cmd "./mothman" --cols 100 --rows 28 \
  --title "mothman: Quality Assurance wizard (Birth Registrations)" \
  --step 'wait:Quality Assurance for a multi-agency data asset' \
  --step 'pause:1.4' \
  --step 'wait:What would you like to do?' \
  --step 'pause:1.9' \
  --step 'key:down' --step 'pause:0.5' \
  --step 'key:down' --step 'pause:0.8' \
  --step 'key:up'   --step 'pause:0.35' \
  --step 'key:up'   --step 'pause:0.9' \
  --step 'key:enter' \
  --step 'wait:Which dataset?' \
  --step 'pause:1.4' \
  --step 'key:down' --step 'pause:0.9' \
  --step 'key:up'   --step 'pause:0.7' \
  --step 'key:enter' \
  --step 'wait:Which source?' \
  --step 'pause:1.6' \
  --step 'key:down' --step 'pause:0.45' \
  --step 'key:down' --step 'pause:1.0' \
  --step 'key:up'   --step 'pause:0.4' \
  --step 'key:up'   --step 'pause:0.8' \
  --step 'key:enter' \
  --step 'wait:Pick a run to check:' \
  --step 'pause:1.7' \
  --step 'key:down' --step 'pause:0.3' \
  --step 'key:down' --step 'pause:0.3' \
  --step 'key:down' --step 'pause:0.9' \
  --step 'key:up'   --step 'pause:0.25' \
  --step 'key:up'   --step 'pause:0.25' \
  --step 'key:up'   --step 'pause:1.1' \
  --step 'key:enter' \
  --step 'wait:Promote this run:90' \
  --step 'pause:5.5' \
  --step 'key:n' \
  --step 'wait:What would you like to do?:15' \
  --step 'pause:1.6'
```

Then re-embed so the built dashboard picks it up:

```bash
uv run mothman dashboard embed
```

## Why the script looks like that

The pauses and the arrow keys are the point, not padding
(`plans/dashboard.md` #13). The first version of this recording had
neither, and read as a machine driving a machine: a uniform **0.78s** to
read every menu, **0.48s** to read a dense results table, and **zero
arrow keys anywhere** — every choice was just the already-highlighted
first option, taken the instant it appeared.

Two rounds of slowing the player down (`speed: 0.5`, then `0.4`) didn't
fix it, because a global multiplier can't fix a distribution problem: it
stretched the ~13.5s tool-chain dead patch by exactly as much as the
reading time. So the hesitation is baked into the recording instead,
where it can vary:

- **Longer on first sight of a menu** (~1.4–1.9s) than on a familiar
  y/N. A first-time viewer is reading options they've never seen.
- **Real scanning, then correction.** The highlight moves down past the
  other options and comes back up to the target. Equal numbers of
  `down` and `up` always land back on the first item, whether the menu
  wraps or clamps at the ends, so this is safe for any menu length.
- **~5.5s on the report**, the densest screen in the whole flow and the
  one a viewer most wants to actually read.

Pauses are explicit per-step rather than a global delay or random
jitter, which keeps the recording deterministic — re-running this script
produces the same rhythm every time.

With that in the `.cast`, playback is honest at `speed: 1` (see the
player config in `dashboard/qa-reporting-dashboard.template.html`).
Total runtime is ~48s, about the same as the old recording's effective
playback at 0.4 — the time is simply spent where a viewer needs it now.

## The chain now shows progress

The real check chain takes ~13.5s, and the CLI used to print **nothing**
for that whole stretch — so both the recording and a real terminal
session sat frozen on one line. That was a real gap in the CLI rather
than a recording artifact, and it's fixed at the source
(`plans/tooling.md` #13): the chain now reports each of its real steps
(the 4 tools plus the dataset-stats computation) and `cli/common.py`'s
`chain_progress()` renders a spinner, the current tool's name, a bar,
the step count and elapsed time.

In this recording that stretch went from **~0 terminal events and a
13.5s frozen gap** to **133 events with a largest gap of 1.5s**. It's
worth knowing when re-recording that this is why the `.cast` is ~68KB
rather than ~26KB: the spinner redraws are real frames. Still plain
text, still small enough that HTTP-level gzip covers it.

Re-recording against a CLI *without* that progress reporting would
silently reintroduce the frozen patch — if that ever shows up again,
check the CLI first, not the pacing script.

## The recorder answers cursor queries truthfully

`prompt_toolkit` sends a CPR (cursor-position-request, `ESC[6n`) on
every fresh prompt render, and a real terminal answers with where the
cursor genuinely is. `record_cast.py` used to answer a constant
`ESC[1;1R` — "top-left" — which silenced the "your terminal doesn't
support cursor position requests" warning but told `prompt_toolkit`
something untrue: it re-rendered every prompt from row 0 and erased
the splash screen and the whole trail of answered lines above it. What
a viewer saw was an unreadable orange flash (`questionary`'s "answered"
style, 256-colour 214) appearing and being destroyed in the same frame.
See `plans/dashboard.md` #13's follow-up.

The recorder now feeds everything the child writes through a real
`pyte` terminal emulator and answers each CPR with that screen's actual
cursor position. A correct recording is easy to spot when replayed: the
splash screen stays up, and the answered choices accumulate under it:

```
 18| Quality Assurance for a multi-agency data asset
 20| ? What would you like to do? Quality Assurance - run the real check chain…
 22| ? Which dataset? Birth Registrations
 23| ? Which source? (Use arrow keys)
```

If a re-recording ever shows only the current prompt with nothing above
it, that's this bug back, not a CLI change.

## What the recording deliberately doesn't show

The script answers **no** at the Promote prompt. Saying yes would write
a real run into the permanent, committed `qa_results/` history as a side
effect of making a video — so the promote success panel
(`cli/common.report_promoted()`, `plans/tooling.md` #14) isn't in the
demo. That's a deliberate omission, not a gap to fix by flipping the
answer.
