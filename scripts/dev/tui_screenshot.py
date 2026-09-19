"""
Dev-only tool: run a real command inside a real pseudo-terminal, feed it
scripted keystrokes, and render the resulting on-screen terminal state
(not a raw scrolling log - a real terminal-emulator buffer, via pyte) to a
PNG screenshot. Built 2026-09-19 as prep for the mothman CLI work (plans/
wider.md #7) so Keith can see real, actual TUI/CLI output in chat as it's
built, rather than descriptions of it. Never imported by the shipped
pipeline/CLI - dev tooling only, not covered by pytest-cov's threshold.

Why pyte and not a plain ANSI-to-HTML text converter: questionary/rich
redraw in place using cursor-movement and erase ANSI codes (they don't
just print new lines), so the raw byte stream on its own doesn't represent
what a human would actually see on screen at any given moment - only a
real terminal-emulator buffer (pyte.Screen) resolves cursor movement/
erase/overwrite into the final grid of visible cells.

Usage:
    uv run python3 scripts/dev/tui_screenshot.py --out shot.png -- <cmd...>
    uv run python3 scripts/dev/tui_screenshot.py --out shot.png --keys "down,down,enter" -- <cmd...>

--keys is a comma-separated list of either literal text to type, or one of
the named keys below (arrow/enter/etc.), sent in order with a short pause
between each so a redrawing TUI (prompt_toolkit-based, e.g. questionary)
has time to repaint before the next key lands.
"""
from __future__ import annotations

import argparse
import fcntl
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

# pyte's named ANSI colors -> real hex, for a dark terminal background.
# Matches a fairly standard xterm-256color palette closely enough for a
# demo screenshot - not trying to be a byte-perfect terminal emulator.
_PALETTE = {
    "black": "#1e1e1e", "red": "#e06c75", "green": "#98c379", "brown": "#d19a66",
    "blue": "#61afef", "magenta": "#c678dd", "cyan": "#56b6c2", "white": "#dcdfe4",
    "brightblack": "#5c6370", "brightred": "#e06c75", "brightgreen": "#98c379",
    "brightbrown": "#e5c07b", "brightblue": "#61afef", "brightmagenta": "#c678dd",
    "brightcyan": "#56b6c2", "brightwhite": "#ffffff",
    "default": None,
}


def _color_to_hex(color: str | None, is_fg: bool) -> str | None:
    if not color or color == "default":
        return None
    if color in _PALETTE:
        return _PALETTE[color]
    # pyte represents 256-color/truecolor as a literal hex string already.
    if len(color) == 6:
        try:
            int(color, 16)
            return f"#{color}"
        except ValueError:
            return None
    return None


def run_in_pty(cmd: list[str], keys: list[str], cols: int, rows: int,
                key_delay: float, idle_timeout: float) -> bytes:
    """Spawn cmd in a real pty, send `keys` with a pause between each, and
    capture every byte written back until the process exits or goes quiet
    for `idle_timeout` seconds past the last scripted key."""
    master_fd, slave_fd = pty.openpty()
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    proc = subprocess.Popen(cmd, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                             env=env, close_fds=True, preexec_fn=os.setsid)
    os.close(slave_fd)

    output = b""
    pending_keys = list(keys)
    last_activity = time.time()

    while True:
        if proc.poll() is not None:
            # Drain whatever's left, then stop.
            try:
                while True:
                    r, _, _ = select.select([master_fd], [], [], 0.05)
                    if not r:
                        break
                    chunk = os.read(master_fd, 65536)
                    if not chunk:
                        break
                    output += chunk
            except OSError:
                pass
            break

        r, _, _ = select.select([master_fd], [], [], 0.1)
        if master_fd in r:
            try:
                chunk = os.read(master_fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
            last_activity = time.time()
        elif pending_keys:
            key = pending_keys.pop(0)
            os.write(master_fd, NAMED_KEYS.get(key, key).encode())
            last_activity = time.time()
            time.sleep(key_delay)
        elif time.time() - last_activity > idle_timeout:
            proc.kill()
            break

    try:
        os.close(master_fd)
    except OSError:
        pass
    return output


def render_html(raw: bytes, cols: int, rows: int) -> str:
    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)
    stream.feed(raw.decode("utf-8", errors="replace"))

    lines_html = []
    for line_no in range(rows):
        line = screen.buffer[line_no]
        spans = []
        for col_no in range(cols):
            char = line[col_no]
            text = char.data or " "
            if text == "\x00":
                text = " "
            text = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            fg = _color_to_hex(char.fg, is_fg=True)
            bg = _color_to_hex(char.bg, is_fg=False)
            if char.reverse:
                fg, bg = bg, fg
            style_parts = []
            if fg:
                style_parts.append(f"color:{fg}")
            if bg:
                style_parts.append(f"background-color:{bg}")
            if char.bold:
                style_parts.append("font-weight:bold")
            if char.italics:
                style_parts.append("font-style:italic")
            if char.underscore:
                style_parts.append("text-decoration:underline")
            style = ";".join(style_parts)
            spans.append(f'<span style="{style}">{text}</span>' if style else text)
        lines_html.append("".join(spans))

    body = "\n".join(lines_html)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  body {{ background:#1e1e1e; margin:0; padding:16px; }}
  pre {{ font-family:'DejaVu Sans Mono','Menlo','Consolas',monospace; font-size:15px;
         line-height:1.35; color:#dcdfe4; white-space:pre; margin:0; }}
</style></head><body><pre>{body}</pre></body></html>"""


def screenshot_html(html_path: str, png_path: str, cols: int, rows: int) -> None:
    from playwright.sync_api import sync_playwright

    width = cols * 9 + 32
    height = int(rows * 20.25) + 32
    # This sandbox's pre-installed browser build can lag the pinned
    # playwright package version (chromium_headless_shell-1194 vs. the
    # 1234 the package wants) - point at the real installed chrome binary
    # directly rather than trying to download a matching one.
    chrome_path = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_path if os.path.exists(chrome_path) else None)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(f"file://{os.path.abspath(html_path)}")
        page.screenshot(path=png_path)
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Output PNG path.")
    parser.add_argument("--keys", default="", help="Comma-separated scripted keystrokes.")
    parser.add_argument("--cols", type=int, default=100)
    parser.add_argument("--rows", type=int, default=30)
    parser.add_argument("--key-delay", type=float, default=0.35,
                         help="Seconds to wait after each scripted key for the TUI to repaint.")
    parser.add_argument("--idle-timeout", type=float, default=2.0,
                         help="Seconds of no output after the last key before capture ends.")
    parser.add_argument("cmd", nargs=argparse.REMAINDER, help="-- <command to run>")
    args = parser.parse_args()

    cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd
    if not cmd:
        parser.error("no command given - pass it after --")

    keys = [k for k in args.keys.split(",") if k] if args.keys else []

    raw = run_in_pty(cmd, keys, args.cols, args.rows, args.key_delay, args.idle_timeout)
    html = render_html(raw, args.cols, args.rows)

    html_path = args.out.rsplit(".", 1)[0] + ".html"
    with open(html_path, "w") as f:
        f.write(html)

    screenshot_html(html_path, args.out, args.cols, args.rows)
    print(f"Wrote {args.out} (and {html_path})", file=sys.stderr)


if __name__ == "__main__":
    main()
