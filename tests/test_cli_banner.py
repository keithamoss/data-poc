"""Tests for cli/banner.py - the mothman TUI splash screen. Real
regression coverage for a genuine visual bug this refactor could easily
introduce silently: rich.text.Text.append() calls building the moth up
from separately-styled spans must still reproduce the EXACT original
ASCII art byte-for-byte (this project's own real incident, plans/
tooling.md #1: a literal backslash next to a rich markup tag once
already broke this art once), plus the real ask that started this
refactor (2026-09-19, Keith's own): the eyes render in a distinct red,
not the body's cyan."""
from __future__ import annotations

from cli.banner import _moth_text


def test_moth_plain_text_matches_the_original_ascii_art_exactly():
    expected = (
        "\n"
        "       \\\\           //\n"
        "        \\\\.        .//\n"
        "    .----\\\\\\      ///----.\n"
        "   (      \\\\\\    ///      )\n"
        "    \\      \\\\\\  ///      /\n"
        "     \\      \\\\\\///      /\n"
        "      '.     )||(     .'\n"
        "        '--. |  | .--'\n"
        "            \\O  O/\n"
        "             \\/\\/"
    )
    assert _moth_text().plain == expected


def test_moth_eyes_are_styled_red_distinct_from_the_cyan_body():
    text = _moth_text()
    styles_by_offset = {}
    for span in text.spans:
        for offset in range(span.start, span.end):
            styles_by_offset[offset] = str(span.style)

    eyes_line_start = text.plain.index("\\O  O/")
    first_eye_offset = eyes_line_start + 1  # skip the leading backslash
    second_eye_offset = eyes_line_start + 4  # "\O  O/" -> O at +1, O at +4

    assert text.plain[first_eye_offset] == "O"
    assert text.plain[second_eye_offset] == "O"
    assert "red" in styles_by_offset[first_eye_offset]
    assert "red" in styles_by_offset[second_eye_offset]

    body_offset = text.plain.index("(") + 1  # a body character, not an eye
    assert "cyan" in styles_by_offset[body_offset]
    assert "red" not in styles_by_offset[body_offset]
