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

## Known dead patch

The real check chain takes ~13.5s and the CLI prints **nothing** while
it runs (`cli/bdm.py` prints one "Running the real ... chain for ..."
line, then calls `run_check()` silently), so both the recording and a
real terminal session sit frozen for that whole stretch. That's a real
CLI gap rather than a recording artifact — logged as
`plans/tooling.md` #13.
