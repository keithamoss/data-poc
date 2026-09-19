"""
Dev-only tool: run a real command in a real pseudo-terminal, script real
keystrokes into it, and record the whole session as a timestamped
asciinema v2 `.cast` file (plans/tooling.md #1 Phase 6's "Demo" tab -
`dashboard/demos/*.cast`, played back by the static `asciinema-player`
JS widget, no server/asciinema.org account needed). Never imported by
the shipped pipeline/CLI - dev tooling only, same throwaway-tooling
status as scripts/dev/tui_screenshot.py, which this borrows its real
pty-spawn/read loop from.

Unlike tui_screenshot.py's fixed key_delay (fine for quick TUI redraws,
too fragile for a session that also runs a real, several-seconds-long
subprocess mid-flow - the actual dbt-core/Soda Core/datacontract-cli/
Evidently chain a real QA run triggers), this script's own keystroke
script is a list of STEPS, each optionally waiting for a real substring
to appear in the terminal's DECODED output before sending its key. That
makes a recording that spans both instant menu redraws and a real,
variable-duration subprocess actually deterministic (waits for the real
state, not a guessed delay) rather than flaky.

Usage (see dashboard/demos/README.md for the actual recorded script):
    uv run python3 scripts/dev/record_cast.py --out dashboard/demos/qa_wizard.cast \
        --cmd "./mothman" --cols 100 --rows 28 \
        --step 'wait:What would you like to do?' --step 'key:enter' \
        --step 'wait:Which dataset?' --step 'key:enter' \
        ...
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time

import pyte

NAMED_KEYS = {
    "up": "\x1b[A",
    "down": "\x1b[B",
    "right": "\x1b[C",
    "left": "\x1b[D",
    "enter": "\r",
    "space": " ",
    "tab": "\t",
    "escape": "\x1b",
    "ctrl-c": "\x03",
    "backspace": "\x7f",
}

# ESC[6n (Device Status Report / cursor-position-request). A real
# terminal replies ESC[<row>;<col>R with its ACTUAL cursor position - see
# _drain()'s own comment for why this is answered at all, and why the
# answer has to be truthful rather than constant.
_CPR_QUERY = "\x1b[6n"


def parse_steps(raw_steps: list[str]) -> list[dict]:
    """Each --step is one of:

    - "wait:<substring>[:timeout_seconds]" - block until that substring
      appears in the decoded output so far, or raise after
      timeout_seconds (default 10; pass a bigger one for a step that
      triggers a real, slow subprocess).
    - "key:<name or literal text>" - sent immediately, no waiting.
    - "pause:<seconds>" - send nothing and keep recording for that long.

    `pause` exists because a recording of a TUI is watched by a human,
    and a script that answers every prompt the instant it renders reads
    as a machine driving a machine (plans/dashboard.md #13). The first
    qa_wizard.cast gave a viewer a uniform 0.78s to read each menu and
    0.48s to read a dense results table, with zero arrow keys anywhere -
    every choice was just the already-highlighted first option. Real
    hesitation is content here, not dead air, so it is scripted
    explicitly rather than faked with a global delay: pauses genuinely
    differ (a first-time menu earns longer than a familiar y/N), and
    keeping them per-step keeps the recording deterministic, which a
    random jitter would not."""
    steps = []
    for raw in raw_steps:
        kind, _, rest = raw.partition(":")
        if kind == "wait":
            parts = rest.rsplit(":", 1)
            if len(parts) == 2 and parts[1].replace(".", "", 1).isdigit():
                steps.append({"type": "wait", "text": parts[0], "timeout": float(parts[1])})
            else:
                steps.append({"type": "wait", "text": rest, "timeout": 10.0})
        elif kind == "key":
            steps.append({"type": "key", "value": rest})
        elif kind == "pause":
            try:
                seconds = float(rest)
            except ValueError:
                raise ValueError(f"--step {raw!r}: pause needs a number of seconds, got {rest!r}") from None
            if seconds < 0:
                raise ValueError(f"--step {raw!r}: pause cannot be negative")
            steps.append({"type": "pause", "seconds": seconds})
        else:
            raise ValueError(
                f"Unrecognised --step {raw!r} (expected wait:..., key:... or pause:...)")
    return steps


def record(cmd: list[str], steps: list[dict], cols: int, rows: int,
           settle_delay: float, final_idle_timeout: float) -> list[tuple[float, str]]:
    """Spawn cmd in a real pty and run through `steps` in order, recording
    every (elapsed_seconds, decoded_chunk) pair written back - the raw
    material an asciinema v2 file's own event lines are built from.
    Blocks on each "wait" step's own real text appearing (or raises
    TimeoutError - a broken script is a loud failure, not a bad
    recording); a "key" step sends immediately, then pauses
    `settle_delay` so a redrawing TUI has a moment to repaint before the
    next step's own wait (if any) starts checking. After the last step,
    keeps recording until `final_idle_timeout` seconds of real silence,
    then stops (whether or not the process itself has exited)."""
    master_fd, slave_fd = pty.openpty()
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    proc = subprocess.Popen(cmd, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                             env=env, close_fds=True, preexec_fn=os.setsid)
    os.close(slave_fd)

    t0 = time.time()
    events: list[tuple[float, str]] = []
    decoded_so_far = ""
    # A real terminal-emulator buffer, fed every byte the child writes, so
    # the CPR replies below can report the genuine cursor position rather
    # than a constant. Same pyte dependency scripts/dev/tui_screenshot.py
    # already uses to resolve in-place TUI redraws.
    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)

    def _drain(deadline: float | None) -> None:
        nonlocal decoded_so_far
        while True:
            if proc.poll() is not None:
                # Still drain whatever's already buffered before giving up.
                r, _, _ = select.select([master_fd], [], [], 0.05)
                if not r:
                    return
            remaining = None if deadline is None else max(0.0, deadline - time.time())
            r, _, _ = select.select([master_fd], [], [], 0.1 if remaining is None else min(0.1, remaining))
            if master_fd in r:
                try:
                    chunk = os.read(master_fd, 65536)
                except OSError:
                    return
                if not chunk:
                    return
                text = chunk.decode("utf-8", errors="replace")
                events.append((time.time() - t0, text))
                decoded_so_far += text
                stream.feed(text)
                # Answer a real CPR (cursor-position-request, ESC[6n) query
                # the moment it appears - prompt_toolkit/questionary send
                # one on every fresh prompt render to check the real
                # terminal's cursor position, and a real terminal always
                # answers it (ESC[<row>;<col>R back on stdin). Skipping
                # this used to leave the query unanswered, which did two
                # real things wrong: printed a "your terminal doesn't
                # support cursor position requests" warning INTO the
                # recording itself (a real artifact of this synthetic
                # pty, not something a real mothman user in a real
                # terminal would ever see - caught live when the first
                # real recording shipped with it baked in), and left the
                # settle-pause-after-every-wait workaround above as the
                # only thing preventing the timing bug that warning's own
                # fallback delay could otherwise cause. Answering for
                # real, immediately, fixes both at the actual source
                # rather than working around the symptom.
                if _CPR_QUERY in text:
                    # Answer with the REAL cursor position, tracked by
                    # feeding everything through a terminal emulator.
                    # This used to reply a constant ESC[1;1R ("you are at
                    # the top-left"), which silenced the warning but told
                    # prompt_toolkit a lie: it re-rendered every prompt
                    # from row 0 and erased whatever was above, so the
                    # splash screen and every answered line got wiped the
                    # instant the next prompt drew. What a viewer saw was
                    # an unreadable orange flash - questionary's own
                    # "answered" style, colour 214, appearing and being
                    # destroyed in the same frame (plans/dashboard.md
                    # #13's follow-up; Keith spotted it in the published
                    # demo). A real terminal session never behaved that
                    # way; only the recording did.
                    for _ in range(text.count(_CPR_QUERY)):
                        os.write(master_fd,
                                  f"\x1b[{screen.cursor.y + 1};{screen.cursor.x + 1}R".encode())
                continue
            if deadline is not None and time.time() >= deadline:
                return
            if deadline is None:
                return

    for step in steps:
        if step["type"] == "wait":
            deadline = time.time() + step["timeout"]
            while step["text"] not in decoded_so_far:
                if time.time() >= deadline:
                    raise TimeoutError(
                        f"Timed out after {step['timeout']}s waiting for {step['text']!r}. "
                        f"Last output:\n{decoded_so_far[-800:]}")
                _drain(min(time.time() + 0.2, deadline))
            # A freshly-rendered prompt_toolkit prompt probes the real
            # terminal for its cursor position (CPR) before it's actually
            # ready to accept input - our synthetic pty never answers
            # that probe, so prompt_toolkit falls back after its own real
            # internal timeout. A key sent before that fallback resolves
            # can land during the probe window and get silently dropped -
            # reproduced live (a scripted Escape right after "What would
            # you like to do?" first matched never registered; the exact
            # same key worked once this settle pause was added). Waiting
            # here, not just after a key, covers exactly that gap.
            _drain(time.time() + settle_delay)
        elif step["type"] == "key":
            os.write(master_fd, NAMED_KEYS.get(step["value"], step["value"]).encode())
            _drain(time.time() + settle_delay)
        elif step["type"] == "pause":
            # Keep draining rather than sleeping: real output arriving
            # mid-pause still gets recorded with its own true timestamp,
            # and asciinema v2 stores absolute elapsed times per event,
            # so the resulting GAP is exactly what playback renders as
            # the viewer's own thinking time.
            _drain(time.time() + step["seconds"])

    # Keep recording real output until it genuinely goes quiet.
    last_activity = time.time()
    while True:
        before = len(events)
        _drain(time.time() + 0.1)
        if len(events) > before:
            last_activity = time.time()
        elif time.time() - last_activity > final_idle_timeout:
            break
        if proc.poll() is not None and time.time() - last_activity > 0.5:
            break

    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        os.close(master_fd)
    except OSError:
        pass

    return events


def write_cast(path: str, events: list[tuple[float, str]], cols: int, rows: int, title: str) -> None:
    header = {
        "version": 2,
        "width": cols,
        "height": rows,
        "timestamp": int(time.time()),
        "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"},
        "title": title,
    }
    with open(path, "w") as f:
        f.write(json.dumps(header) + "\n")
        for elapsed, text in events:
            f.write(json.dumps([round(elapsed, 6), "o", text]) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, help="Output .cast path.")
    parser.add_argument("--cmd", required=True, help="Command to run, e.g. './mothman'.")
    parser.add_argument("--cols", type=int, default=100)
    parser.add_argument("--rows", type=int, default=28)
    parser.add_argument("--settle-delay", type=float, default=0.4,
                         help="Seconds to let the TUI repaint after a key before the next step's wait starts.")
    parser.add_argument("--final-idle-timeout", type=float, default=2.0,
                         help="Seconds of real silence after the last step before the recording stops.")
    parser.add_argument("--title", default="mothman CLI/TUI demo")
    parser.add_argument("--step", action="append", default=[], required=True,
                         help="wait:<substring>[:timeout_s], key:<name|literal text>, or "
                              "pause:<seconds> - repeatable, applied in order.")
    args = parser.parse_args()

    steps = parse_steps(args.step)
    events = record(args.cmd.split(), steps, args.cols, args.rows, args.settle_delay, args.final_idle_timeout)
    write_cast(args.out, events, args.cols, args.rows, args.title)
    total_duration = events[-1][0] if events else 0.0
    print(f"Wrote {args.out} ({len(events)} events, {total_duration:.1f}s)", file=sys.stderr)


if __name__ == "__main__":
    main()
