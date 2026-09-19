"""The mothman TUI's splash screen (plans/tooling.md #1, Keith's own fun
ask): a pyfiglet block-letter wordmark plus a small hand-drawn ASCII moth,
shown once before the main menu on a bare `mothman` launch. Iterated
visually via scripts/dev/tui_screenshot.py's real screenshot pipeline
before landing here, not guessed blind - including one real bug caught
that way: a literal backslash immediately before a `[red]...[/red]` rich
markup tag gets parsed as an escaped literal `[` (rich markup syntax),
leaving the matching `[/red]` with no open tag to close - printed with
markup=False here for exactly that reason, real ASCII art is full of
backslashes."""
from __future__ import annotations

import pyfiglet
from rich.console import Console

_MOTH = r"""
       \\           //
        \\.        .//
    .----\\\      ///----.
   (      \\\    ///      )
    \      \\\  ///      /
     \      \\\///      /
      '.     )||(     .'
        '--. |  | .--'
            \O  O/
             \/\/
"""


def print_banner(console: Console | None = None) -> None:
    console = console or Console()
    console.print(_MOTH, style="cyan", markup=False, highlight=False)
    console.print(pyfiglet.figlet_format("MOTHMAN", font="slant"), style="bold magenta", highlight=False)
    console.print("Quality Assurance for a multi-agency data asset", style="dim")
    console.print()
