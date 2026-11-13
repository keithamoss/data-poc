"""Shared text helpers for this project's own markdown parsers -
`dashboard/plans_md.py` (plans/*.md, the Plans tab) and
`dashboard/changelog_yaml.py` (CHANGELOG.yaml, the Release Notes panel) until that file became structured YAML on 2026-09-20 and stopped needing line-joining at all.

Exists because of one real, live bug they both had (found 2026-09-20).
Both reassembled hard-wrapped markdown with a plain `" ".join(...)`,
which is right for ordinary wrapped prose and wrong for a hyphenated
word split across two source lines:

    A dedicated requirements-
    analysis subagent system

came back as "requirements- analysis" and rendered that way on the
published site - 195 occurrences across 74 of the 137 plans items, and 9
in CHANGELOG.md. Worth recording why it survived so long: the symptom
had been patched once, in the CHANGELOG source text during an unrelated
rename, without the cause being touched - so it simply came back, and
one of the 9 was in an entry written the same night as that "fix".

The fix lives here rather than in both parsers because two copies of
this rule is exactly the drift `plans/tooling.md` #12's DRY pass exists
to stop, and because the tricky half of it is easy to get subtly
different in two places (see `join_wrapped`).
"""
from __future__ import annotations
import re

# A hyphen that is ATTACHED to a word character, at end of line - the
# signature of a word wrapped mid-hyphenation. Deliberately not "any
# trailing hyphen": this project uses " - " as a dash constantly ("a
# real bug - not a design gap"), and a line ending in a standalone
# hyphen is punctuation that must keep its following space.
_WRAPPED_HYPHEN_RE = re.compile(r"\w-$")


def join_wrapped(parts: list[str]) -> str:
    """Join hard-wrapped markdown lines (or words) back into one string,
    inserting a space between them EXCEPT where the preceding part ends
    in a word-attached hyphen, which means the word itself was wrapped.

        join_wrapped(["requirements-", "analysis"]) -> "requirements-analysis"
        join_wrapped(["a real bug -", "not a gap"]) -> "a real bug - not a gap"

    Empty parts are skipped rather than contributing a stray space."""
    out = ""
    for part in parts:
        if not part:
            continue
        if not out:
            out = part
        elif _WRAPPED_HYPHEN_RE.search(out):
            out += part
        else:
            out += " " + part
    return out
