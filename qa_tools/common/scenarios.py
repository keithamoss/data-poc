"""The test scenario register, read as data (REQ-GEN-044, REQ-GEN-045).

THE REGISTER IS PROSE, AND THAT IS DELIBERATE. It lives in
plans/supply-model.md because it was written while the model was being
shaped and every entry carries the narrative behind it - the config the
outcome depends on, what the system should do, and what it BREAKS AS if
the rule is got wrong. Keith reviewed it as prose, and that review is
what makes it authoritative. Moving it into YAML would make it
machine-readable and would also make it unreadable, which is the wrong
trade for the thing everything else cites.

So this parses it rather than replacing it. The register stays the one
copy; this is a view of it.

WHAT IT DOES NOT DO: it does not know where any scenario LANDED. That
is the generator's to record (REQ-GEN-044 criterion 7) and this module
deliberately has no way to find out - a map built from the register
alone would say where a scenario was MEANT to go, which is exactly the
hand-maintained map REQ-GEN-045 criterion 2 forbids.

PARSED, NOT TRUSTED. Every entry is required to have an id, a mode and
a title; anything that looks like an entry and is missing one is a
parse failure rather than a silently skipped line, because a register
of 49 scenarios that quietly returns 48 is worse than one that cannot
be read at all.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

REGISTER_PATH = ROOT / "plans" / "supply-model.md"
REGISTER_HEADING = "## Test scenario register"

#: What the register says should happen to a scenario.
INJECT = "INJECT"
UNIT = "unit"
BOTH = "both"
MODES = (INJECT, UNIT, BOTH)

#: `**TS-3a `[INJECT]` Quarterly, prior slot FILLED.**`. Two shapes the
#: register really uses and a naive line-based match gets wrong: the
#: title may WRAP onto the next line before its closing `**`, and the
#: body may begin on the SAME line as the closing `**` (TS-23 is the
#: worked example of the second). So this matches the header as a
#: PREFIX of the whole block rather than as a whole line, and whatever
#: follows is the body.
_ENTRY = re.compile(
    r"\A\*\*(?P<id>TS-[0-9]+[a-z]?)\s+`\[(?P<mode>INJECT|unit|both)\]`\s+(?P<title>.*?)\*\*",
    re.S)
_ENTRY_START = re.compile(r"^\*\*(TS-[0-9]+[a-z]?)\s+`\[")


class RegisterError(RuntimeError):
    """The register could not be read as data."""


@dataclass(frozen=True)
class Scenario:
    """One scenario, as the register states it."""

    id: str
    mode: str
    title: str
    section: str
    config: str | None
    expect: str | None
    breaks_as: str | None
    body: str

    @property
    def is_injected(self) -> bool:
        """Only the INJECT set can have data behind it. A `[unit]`
        scenario has nothing to navigate to, and the map says so
        rather than rendering a dead link."""
        return self.mode == INJECT

    @property
    def sort_key(self) -> tuple:
        number = int(re.match(r"TS-(\d+)", self.id).group(1))
        suffix = self.id[len(f"TS-{number}"):]
        return (number, suffix)


def _flatten(text: str) -> str:
    return " ".join(text.split())


def _field(body: str, label: str) -> str | None:
    """One `**Label**: ...` field, up to the next bolded field or the
    end of the entry."""
    match = re.search(rf"\*\*{label}\*\*:\s*(.*?)(?=\n\*\*[A-Z]|\Z)", body, re.S)
    return _flatten(match.group(1)) if match else None


def _config(body: str) -> str | None:
    match = re.search(r"^\*(Config:.*?)\*\s*$", body, re.S | re.M)
    if match:
        return _flatten(match.group(1))
    # A few entries state the config inside a bolded sentence instead
    # of the italic line - TS-5's "MUST be stated per variant" is the
    # worked example. Reported as absent rather than guessed at.
    return None


def parse_register(path: Path | str | None = None) -> list[Scenario]:
    """Every scenario in the register, in register order.

    Scoped to the register's OWN heading rather than the whole file:
    plans/supply-model.md is a long document and other sections cite
    scenario ids in passing, which a whole-file scan would read as
    entries.
    """
    text = Path(path or REGISTER_PATH).read_text()
    start = text.find(REGISTER_HEADING)
    if start < 0:
        raise RegisterError(
            f"no {REGISTER_HEADING!r} heading in {path or REGISTER_PATH} - "
            f"the register has moved or been renamed")
    end = text.find("\n## ", start + len(REGISTER_HEADING))
    region = text[start:end if end > 0 else len(text)]

    # Split on blank lines so an entry keeps its own body and nothing
    # else's. A section heading resets `section`, which is what gives
    # each scenario the part of the model it belongs to.
    scenarios: list[Scenario] = []
    section = ""
    for block in re.split(r"\n\s*\n", region):
        stripped = block.strip()
        if stripped.startswith("### "):
            section = stripped[4:].strip()
            continue
        if not _ENTRY_START.match(stripped):
            continue
        # AN ENTRY WHOSE TITLE NEVER CLOSES IS A PARSE FAILURE, not a
        # title to be repaired. Appending the missing `**` was the
        # first version and it is the wrong leniency: a malformed
        # header usually means the entry below it has been mangled
        # too, and a register that silently repairs itself is one
        # nobody finds out is broken.
        match = _ENTRY.match(stripped)
        if match is None:
            raise RegisterError(
                f"cannot read this as a scenario entry: {_flatten(stripped)[:120]!r}")
        body = stripped[match.end():]
        scenarios.append(Scenario(
            id=match.group("id"), mode=match.group("mode"),
            title=_flatten(match.group("title")).rstrip("."),
            section=section,
            config=_config(body), expect=_field(body, "Expect"),
            breaks_as=_field(body, "Breaks as"), body=_flatten(body)))

    if not scenarios:
        raise RegisterError("the register parsed to zero scenarios")
    seen = [s.id for s in scenarios]
    duplicates = sorted({i for i in seen if seen.count(i) > 1})
    if duplicates:
        raise RegisterError(f"the register names these scenarios more than once: {duplicates}")
    return scenarios


def injected(path: Path | str | None = None) -> list[Scenario]:
    """Just the ones the register marks for injection."""
    return [s for s in parse_register(path) if s.is_injected]
