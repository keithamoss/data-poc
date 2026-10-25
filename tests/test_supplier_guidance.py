"""REQ-DOCS-274: supplier guidance to send a delivery's files as one zip.

The document IS the deliverable here, so these read it - the one case
CLAUDE.md's test rule 1 allows reading text for: there is no behaviour to
drive. What they guard is that the guidance exists where the two docs that
point at it say it does, that every link it makes resolves, and that it
still says the three things its criteria require."""
from __future__ import annotations

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
GUIDANCE = DOCS / "supplier-guidance.md"


def _text() -> str:
    text = GUIDANCE.read_text()
    assert text.strip(), "the guidance is empty"
    return text


def _anchor(heading: str) -> str:
    return re.sub(r"[^a-z0-9 -]", "", heading.lower()).replace(" ", "-")


def test_both_docs_that_point_at_it_link_to_it():
    for name in ("delivery-format.md", "aws-event-driven-mvp-design.md"):
        assert "(supplier-guidance.md)" in (DOCS / name).read_text(), name


def test_every_link_it_makes_resolves():
    links = re.findall(r"\]\(([^)]+)\)", _text())
    assert links, "the guidance links nowhere"
    for link in links:
        target, _, anchor = link.partition("#")
        path = DOCS / target
        assert path.exists(), link
        if anchor:
            headings = [_anchor(h) for h in re.findall(r"^#+ (.+)$", path.read_text(), re.M)]
            assert anchor in headings, link


def test_it_says_one_zip_on_both_paths_and_why():
    text = _text().lower()
    assert "one zip" in text
    assert "delivery directory" in text and "cloud upload path" in text
    assert "checked as they arrive" in text and "reads **red**" in text


def test_it_says_the_red_clears_by_itself_and_a_zip_avoids_it():
    text = _text().lower()
    assert "clears by itself" in text
    assert "a zip avoids it" in text


def test_a_package_is_files_arriving_at_one_instant_and_nothing_else():
    text = _text().lower()
    assert "arrive at the same instant" in text
    assert "manifest" not in text and "end marker" not in text
