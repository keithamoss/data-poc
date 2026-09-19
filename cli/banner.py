"""The mothman TUI's splash screen (plans/tooling.md #1, Keith's own fun
ask): a pyfiglet block-letter wordmark plus a small hand-drawn ASCII moth,
shown once before the main menu on a bare `mothman` launch. Iterated
visually via scripts/dev/tui_screenshot.py's real screenshot pipeline
before landing here, not guessed blind - including one real bug caught
that way: a literal backslash immediately before a `[red]...[/red]` rich
markup tag gets parsed as an escaped literal `[` (rich markup syntax),
leaving the matching `[/red]` with no open tag to close.

The moth's own eyes are styled red separately from the rest (a real
"glowing red eyes" ask, 2026-09-19, Keith's own - the original design
text in plans/tooling.md already said "glowing red eyes" but the actual
code had never done more than print the whole moth in one flat cyan,
this closes that real gap). Built as a `rich.text.Text` with each eye
appended as its own separately-styled span, not a markup string - the
same backslash-escaping trap the docstring above already warns about
would apply just as much to a `[red]O[/red]` markup string embedded
next to this many literal backslashes, so this sidesteps markup parsing
entirely rather than trying to escape around it."""
from __future__ import annotations

import pyfiglet
from rich.console import Console
from rich.text import Text

_MOTH_BODY_LINES = [
    r"       \\           //",
    r"        \\.        .//",
    r"    .----\\\      ///----.",
    r"   (      \\\    ///      )",
    r"    \      \\\  ///      /",
    r"     \      \\\///      /",
    r"      '.     )||(     .'",
    r"        '--. |  | .--'",
]
_MOTH_EYES_PREFIX = "            \\"
_MOTH_EYE = "O"
_MOTH_EYES_GAP = "  "
_MOTH_EYES_SUFFIX = "/"
_MOTH_TAIL_LINE = r"             \/\/"


def _moth_text() -> Text:
    text = Text()
    text.append("\n")
    for line in _MOTH_BODY_LINES:
        text.append(line + "\n", style="cyan")
    text.append(_MOTH_EYES_PREFIX, style="cyan")
    text.append(_MOTH_EYE, style="bold red")
    text.append(_MOTH_EYES_GAP, style="cyan")
    text.append(_MOTH_EYE, style="bold red")
    text.append(_MOTH_EYES_SUFFIX + "\n", style="cyan")
    text.append(_MOTH_TAIL_LINE, style="cyan")
    return text


def print_banner(console: Console | None = None) -> None:
    console = console or Console()
    console.print(_moth_text(), highlight=False)
    console.print(pyfiglet.figlet_format("MOTHMAN", font="slant"), style="bold magenta", highlight=False)
    console.print("Quality Assurance for a multi-agency data asset", style="dim")
    console.print()
