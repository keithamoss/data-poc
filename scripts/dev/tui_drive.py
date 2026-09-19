"""
Dev-only tool: a persistent, addressable interactive TUI-driving session
for real post-build CLI/TUI review (`requirements-cli-ux-critic`,
`plans/wider.md` #10's deferred HCI/psychology-grounding work,
2026-09-19). Spawns a real command in a real pty and exposes it over a
local Unix domain socket so an agent can drive it step by step across
multiple separate `Bash` tool calls - env vars and in-process state
don't survive between separate `Bash` invocations, the same reason
`scripts/dev/serve_dashboard_https.py` prints its port to stdout rather
than a shell variable.

Built on the two existing real pty dev tools rather than reinventing
their proven pieces: `tui_screenshot.py`'s `pyte.Screen`/`pyte.Stream`
(a real terminal-emulator buffer that correctly resolves cursor-
movement/erase/overwrite ANSI codes into the actual visible grid, not a
raw scrolling log) and `record_cast.py`'s real CPR (cursor-position-
request, ESC[6n) auto-answering - prompt_toolkit/questionary send one on
every fresh prompt render, and a real terminal always answers it; not
answering it is a real, previously-hit bug (see that script's own
comment) that both delays and can corrupt a synthetic pty session.

Why a real interactive protocol rather than a single scripted run (like
`record_cast.py`'s own fixed `--step` list): a real post-build critic
needs to SEE the actual current screen before deciding its next action -
the same "observe, then act" loop Playwright MCP gives the dashboard
critics - a script written in advance can't do that. A persistent
background session (not a fresh pty per command) is necessary because
`mothman`'s own wizard flows can trigger real, several-seconds-long
subprocess runs (the real dbt-core/Soda Core/datacontract-cli/Evidently
chain) - replaying the whole session from scratch on every single step
would re-trigger that real work repeatedly, both slow and wrong for
anything with real side effects.

Two modes:
    serve   - runs the real pty session in the foreground; background it
              yourself (`... &`) and read its socket path from the first
              stdout line (`SOCKET=<path>`).
    <verb>  - a thin client: connects to an already-running `serve`
              session's socket, sends one command, prints the JSON
              response, exits.

Usage:
    LOGFILE=$(mktemp)
    (uv run python3 scripts/dev/tui_drive.py serve --cmd "./mothman" > "$LOGFILE" 2>&1 &)
    sleep 0.5
    SOCK=$(grep -oP 'SOCKET=\K.*' "$LOGFILE")
    uv run python3 scripts/dev/tui_drive.py screen --socket "$SOCK"
    uv run python3 scripts/dev/tui_drive.py send --socket "$SOCK" down
    uv run python3 scripts/dev/tui_drive.py send --socket "$SOCK" enter
    uv run python3 scripts/dev/tui_drive.py wait --socket "$SOCK" --timeout 15 "Which dataset?"
    uv run python3 scripts/dev/tui_drive.py alive --socket "$SOCK"
    uv run python3 scripts/dev/tui_drive.py close --socket "$SOCK"
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import pty
import select
import socket
import struct
import subprocess
import sys
import tempfile
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

# See record_cast.py's own comment for the real bug this fixes: a
# freshly-rendered prompt_toolkit prompt queries the real terminal's
# cursor position (CPR) before it's ready for input - a real terminal
# always answers it, and not answering can both delay and corrupt the
# session.
_CPR_QUERY = "\x1b[6n"
_CPR_RESPONSE = b"\x1b[1;1R"

_SETTLE_DELAY = 0.35  # seconds to let the TUI repaint after a sent key
_MAX_BUFFER_CHARS = 500_000  # cap the decoded-output buffer for a long session


class TuiSession:
    """Owns the real pty + pyte screen buffer for one spawned command."""

    def __init__(self, cmd: list[str], cols: int, rows: int) -> None:
        self.cols = cols
        self.rows = rows
        self.master_fd, slave_fd = pty.openpty()
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        self.proc = subprocess.Popen(cmd, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                                      env=env, close_fds=True, preexec_fn=os.setsid)
        os.close(slave_fd)
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.Stream(self.screen)
        self.decoded_so_far = ""

    def alive(self) -> bool:
        return self.proc.poll() is None

    def _feed(self, text: str) -> None:
        self.stream.feed(text)
        self.decoded_so_far += text
        if len(self.decoded_so_far) > _MAX_BUFFER_CHARS:
            self.decoded_so_far = self.decoded_so_far[-_MAX_BUFFER_CHARS:]

    def drain(self, deadline: float) -> None:
        """Read and feed whatever's available on the pty until `deadline`
        (a real time.time() value), answering any real CPR probe the
        moment it appears."""
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return
            r, _, _ = select.select([self.master_fd], [], [], min(0.1, remaining))
            if self.master_fd not in r:
                continue
            try:
                chunk = os.read(self.master_fd, 65536)
            except OSError:
                return
            if not chunk:
                return
            text = chunk.decode("utf-8", errors="replace")
            self._feed(text)
            if _CPR_QUERY in text:
                for _ in range(text.count(_CPR_QUERY)):
                    try:
                        os.write(self.master_fd, _CPR_RESPONSE)
                    except OSError:
                        pass

    def send(self, key_or_text: str) -> None:
        payload = NAMED_KEYS.get(key_or_text, key_or_text)
        try:
            os.write(self.master_fd, payload.encode())
        except OSError:
            pass
        self.drain(time.time() + _SETTLE_DELAY)

    def screen_lines(self) -> list[str]:
        self.drain(time.time() + 0.05)
        return list(self.screen.display)

    def wait_for(self, substring: str, timeout: float) -> bool:
        deadline = time.time() + timeout
        while substring not in self.decoded_so_far:
            if time.time() >= deadline:
                return False
            self.drain(min(time.time() + 0.2, deadline))
        return True

    def close(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        try:
            os.close(self.master_fd)
        except OSError:
            pass


def _handle_command(session: TuiSession, line: str) -> dict:
    parts = line.rstrip("\n").split(" ", 1)
    verb = parts[0].upper() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if verb == "SEND":
        session.send(rest)
        return {"ok": True, "alive": session.alive(), "screen": session.screen_lines()}
    if verb == "SCREEN":
        return {"ok": True, "alive": session.alive(), "screen": session.screen_lines()}
    if verb == "ALIVE":
        return {"ok": True, "alive": session.alive()}
    if verb == "WAIT":
        timeout_str, _, substring = rest.partition(" ")
        try:
            timeout = float(timeout_str)
        except ValueError:
            return {"ok": False, "error": f"bad timeout {timeout_str!r}"}
        matched = session.wait_for(substring, timeout)
        return {"ok": True, "matched": matched, "alive": session.alive(),
                "screen": session.screen_lines()}
    if verb == "CLOSE":
        session.close()
        return {"ok": True, "closed": True}
    return {"ok": False, "error": f"unrecognised command {verb!r}"}


def serve(cmd: list[str], cols: int, rows: int) -> int:
    session = TuiSession(cmd, cols, rows)

    sock_path = tempfile.mktemp(prefix="mothman-tui-", suffix=".sock")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(sock_path)
    listener.listen(4)

    print(f"SOCKET={sock_path}")
    print(f"Driving real command {cmd!r} in a {cols}x{rows} pty. "
          f"Use this script's other subcommands with --socket {sock_path} to drive it. "
          f"Send CLOSE (or Ctrl-C here) when done.", file=sys.stderr)
    sys.stdout.flush()
    sys.stderr.flush()

    try:
        while True:
            session.drain(time.time() + 0.05)
            r, _, _ = select.select([listener], [], [], 0.1)
            if listener not in r:
                continue
            conn, _ = listener.accept()
            try:
                buf = b""
                while b"\n" not in buf:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                line = buf.decode("utf-8", errors="replace")
                response = _handle_command(session, line)
                conn.sendall((json.dumps(response) + "\n").encode())
            finally:
                conn.close()
            if line.strip().upper() == "CLOSE":
                break
    except KeyboardInterrupt:
        session.close()
    finally:
        try:
            listener.close()
        except OSError:
            pass
        try:
            os.unlink(sock_path)
        except OSError:
            pass
    return 0


def client(verb: str, socket_path: str, arg: str) -> int:
    line = f"{verb} {arg}".rstrip() + "\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(socket_path)
        s.sendall(line.encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    print(buf.decode("utf-8", errors="replace").strip())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    p_serve = sub.add_parser("serve", help="Spawn the real session (run in background).")
    p_serve.add_argument("--cmd", required=True, help="Command to run, e.g. './mothman'.")
    p_serve.add_argument("--cols", type=int, default=100)
    p_serve.add_argument("--rows", type=int, default=30)

    for verb in ("screen", "alive", "close"):
        p = sub.add_parser(verb)
        p.add_argument("--socket", required=True)

    p_send = sub.add_parser("send")
    p_send.add_argument("--socket", required=True)
    p_send.add_argument("keys", nargs=argparse.REMAINDER,
                         help="A named key (up/down/enter/...) or literal text to type.")

    p_wait = sub.add_parser("wait")
    p_wait.add_argument("--socket", required=True)
    p_wait.add_argument("--timeout", type=float, default=10.0)
    p_wait.add_argument("substring", nargs=argparse.REMAINDER)

    args = parser.parse_args()

    if args.mode == "serve":
        return serve(args.cmd.split(), args.cols, args.rows)
    if args.mode == "send":
        return client("SEND", args.socket, " ".join(args.keys))
    if args.mode == "wait":
        return client("WAIT", args.socket, f"{args.timeout} {' '.join(args.substring)}")
    return client(args.mode.upper(), args.socket, "")


if __name__ == "__main__":
    sys.exit(main())
