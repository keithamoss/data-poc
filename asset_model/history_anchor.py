"""The date a synthetic asset's generated history runs up to - its ANCHOR
(REQ-GEN-404, REQ-GEN-405; signed by Keith 2026-11-14 as speed-anchor v2).

ONE INPUT, RECORDED WITH THE HISTORY (R2). A generation is given its anchor by
its caller - the fixed test anchor unless a person asked for another with
`--anchor` or `--roll-anchor` - and records the date it used, from one value, in
three places, each for a reader the others cannot serve (SR1):

- the generator's bookkeeping, for the generator's own readers (a resume);
- the one-line ANCHOR FILE beside the delivery tree, data/<asset>/history_anchor,
  which this module reads - for offset dates in a synthetic asset's
  configuration (REQ-GEN-406 criterion 3) and `mothman env current`, neither of
  which may open a database or read the bookkeeping (REQ-GEN-043 criterion 7);
- through the bootstrap, the qa schema (qa.history_anchor), which the dashboard
  build reads as a recorded fact (REQ-DASH-407).

INSTALLED PROCESS-WIDE FOR A RUN (REQ-GEN-404 criterion 10): the providers call
get_anchor_date() with no argument about fifteen times, so the anchor is
installed for the span of a generation or a bootstrap, as the configuration pin
is, and handed to every process the run starts through assets.handoff(). Here,
in asset_model/, rather than in the generator, because assets.handoff() may not
import the generator (REQ-TEST-384's imports gate) and the offset resolver here
needs it too. The generator names the same constant (generator/anchor_date.py).
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path

#: THE FIXED TEST ANCHOR (REQ-GEN-405 criterion 1): what the test suite and CI
#: always generate at, and what a bootstrap without --roll-anchor uses (R1). It
#: is the old ANCHOR_DATE, so no pin built on it moves.
FIXED_TEST_ANCHOR = date(2026, 9, 25)

#: The one-line anchor file's name, under data/<asset>/ (SR1).
FILE = "history_anchor"

#: The environments where offsets may resolve to the fixed test anchor when no
#: anchor file exists (REQ-GEN-404 criterion 12): CI's critical half and a
#: fresh checkout have no delivery tree.
FALLBACK_ENVIRONMENTS = frozenset({"test", "ci"})


class AnchorUnknown(RuntimeError):
    """An offset date asked for where no anchor is installed, none is recorded,
    and the environment may not fall back to the fixed test anchor."""


_installed: date | None = None


def install(anchor: date) -> None:
    """Install `anchor` for this process until release()."""
    global _installed
    if not isinstance(anchor, date):
        raise TypeError(f"an anchor is a date, not {anchor!r}")
    _installed = anchor


def release() -> None:
    global _installed
    _installed = None


def installed() -> date | None:
    """The anchor installed in this process, or None - for the synthetic side
    and the hand-off; never for a pipeline module to branch on."""
    return _installed


@contextmanager
def anchored(anchor: date):
    """`anchor` installed for the span of the with-block, the one before it put
    back however the block ends - a generation inside a bootstrap is one
    anchor."""
    before = _installed
    install(anchor)
    try:
        yield anchor
    finally:
        if before is None:
            release()
        else:
            install(before)


def adopt(anchor: date | None) -> None:
    """A started process's half of the hand-off (assets.adopt)."""
    if anchor is None:
        release()
    else:
        install(anchor)


def path() -> Path:
    """The selected asset's anchor file: data/<asset>/history_anchor."""
    from asset_model import assets

    return assets.data_path(FILE)


def parse(text: str, where: str) -> date:
    line = text.strip()
    try:
        return date.fromisoformat(line)
    except ValueError:
        raise ValueError(f"{where} should hold one date, YYYY-MM-DD, and holds {line!r}") from None


def recorded(at: Path | None = None) -> date | None:
    """The anchor recorded in the anchor file beside the delivery tree, or None
    where there is no file. Read whole on every call (REQ-PIPE-254 criterion
    15): it is state beside the tree, not configuration, so never pinned."""
    p = Path(at) if at is not None else path()
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return parse(text, str(p))


def write(anchor: date, at: Path | None = None) -> Path:
    """Write the one-line anchor file - the generator's, with its bookkeeping
    (REQ-GEN-404 criterion 3)."""
    p = Path(at) if at is not None else path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(anchor.isoformat() + "\n", encoding="utf-8")
    return p


def for_offsets() -> date:
    """The anchor an offset date in a synthetic asset's configuration resolves
    against (REQ-GEN-406 criterion 3; REQ-GEN-404 criterion 12): the installed
    one during a generation or a bootstrap, else the anchor file beside the
    delivery tree, else - only where MOTHMAN_ENVIRONMENT is test or ci - the
    fixed test anchor. Refused elsewhere, naming the missing file."""
    if _installed is not None:
        return _installed
    found = recorded()
    if found is not None:
        return found
    if os.environ.get("MOTHMAN_ENVIRONMENT") in FALLBACK_ENVIRONMENTS:
        return FIXED_TEST_ANCHOR
    raise AnchorUnknown(
        f"this asset's configuration writes a date as an offset from its history's anchor, "
        f"and there is no anchor to resolve it against: {path()} does not exist. Generate "
        f"the history first - `mothman pipeline bootstrap` writes it")


def kind(anchor: date) -> str:
    """'fixed' for the fixed test anchor, else 'rolled' - how the closing line,
    `mothman env current` and the cache key tell the two apart."""
    return "fixed" if anchor == FIXED_TEST_ANCHOR else "rolled"
