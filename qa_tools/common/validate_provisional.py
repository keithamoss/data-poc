"""`mothman check`'s provisional gate (REQ-TEST-374, Keith 2026-11-01).

A `PROVISIONAL` choice is a builder deciding something on Keith's behalf
while he was away. Post-build-review #292 found one (Pass / Warn / Fail)
that later work had quietly treated as settled, so this gate keeps every
unanswered one in BUILT work in front of him: it WARNS, naming each by
requirement, field and item number, and never fails the build on it.

What counts, tightened after the gate's critic (Keith, 2026-11-01):
- the marker is the upper-case word on its own;
- a QUOTED word - in backticks or single quotes - is a mention, not a marker;
- text inside <<< >>> (an amendment's CURRENT or PROPOSED quote) is ignored;
- an item is ANSWERED only where it says 'SETTLED by Keith' or 'answered by
  Keith' followed by a date. A bare 'answered', 'to be answered by Keith'
  with no date, and 'SIGNED by Keith' do not count.

THE BASELINE. The 188 markers on the register the day this was built were
written once to `provisional-baseline.yaml`, each as requirement id, field
and a fingerprint of the item text, so only NEW markers warn. It only ever
shrinks: an entry whose marker has been answered, or whose item has been
reworded, FAILS the gate until it is taken off (`--prune`), and an entry
present here but absent at the push's base (diff_base) fails as a gain.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from qa_tools.common import diff_base as _diff_base

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTER = "requirements.yaml"
BASELINE = "provisional-baseline.yaml"
WARNING_EXIT_VAR = "MOTHMAN_GATE_WARNING_EXIT"
FIELDS = ("acceptance_criteria", "non_functional_requirements", "decisions")
_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

_AMENDMENT_QUOTE = re.compile(r"<<<.*?>>>", re.S)
_QUOTED_WORD = re.compile(r"`PROVISIONAL`|'PROVISIONAL'")
_MARKER = re.compile(r"\bPROVISIONAL\b")
# The words, then a date. Case-insensitive on purpose: REQ-PIPE-110 d5 is
# answered as "settled by Keith on 2026-10-07".
_ANSWERED = re.compile(
    r"\b(?:SETTLED|answered) by Keith,?\s+(?:on\s+)?\d{4}-\d{2}-\d{2}", re.I)
# A promise or a denial is not an answer, even when a date follows: "to be
# answered", "not yet answered", "not answered", "never answered",
# "un-answered", "has not been answered" - the negation within a word of it.
_NEGATED = re.compile(r"\b(?:not|never|un|yet|be|been)\b[\s-]*(?:\w+\s+)?$", re.I)

_HEADER = """\
# REQ-TEST-374: the `PROVISIONAL` markers already in BUILT requirements when
# the provisional gate was built (2026-11-01), so that only new ones warn.
# SHRINK-ONLY: take an entry off when its item is answered ('SETTLED by Keith
# <date>' or 'answered by Keith <date>') or reworded - `mothman dashboard
# validate-provisional --prune` does exactly that - and never add one; the
# gate fails on a stale entry and on any entry the push's base did not hold.
"""


def is_unanswered_marker(text: str) -> bool:
    """True where `text` carries an unquoted marker and no dated answer."""
    live = _QUOTED_WORD.sub("", _AMENDMENT_QUOTE.sub("", text))
    if not _MARKER.search(live):
        return False
    return not any(not _NEGATED.search(live[max(0, m.start() - 40):m.start()])
                   for m in _ANSWERED.finditer(live))


def fingerprint(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Marker:
    req_id: str
    field: str
    item: int
    fingerprint: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.req_id, self.field, self.fingerprint)


def load_register(root: Path = ROOT) -> dict:
    with open(root / REGISTER, encoding="utf-8") as f:
        return yaml.load(f, Loader=_LOADER) or {}


def scan(register: dict) -> list[Marker]:
    """Every unanswered marker in a built requirement, in register order."""
    found = []
    for req in register.get("requirements") or []:
        if req.get("status") != "built":
            continue
        for field in FIELDS:
            for i, item in enumerate(req.get(field) or [], 1):
                text = item if isinstance(item, str) else yaml.safe_dump(item)
                if is_unanswered_marker(text):
                    found.append(Marker(req["id"], field, i, fingerprint(text)))
    return found


def _entries(doc) -> set[tuple[str, str, str]]:
    return {(e["id"], e["field"], e["fingerprint"])
            for e in ((doc or {}).get("entries") or [])}


def load_baseline(root: Path = ROOT) -> set[tuple[str, str, str]]:
    with open(root / BASELINE, encoding="utf-8") as f:
        return _entries(yaml.load(f, Loader=_LOADER))


def write_baseline(root: Path, entries) -> None:
    keys = sorted({e.key if isinstance(e, Marker) else tuple(e) for e in entries})
    body = yaml.safe_dump({"entries": [
        {"id": i, "field": f, "fingerprint": fp} for i, f, fp in keys]},
        sort_keys=False, width=100)
    (root / BASELINE).write_text(_HEADER + body, encoding="utf-8")


def _baseline_at_base(root: Path) -> set[tuple[str, str, str]] | None:
    """The baseline as the push's base held it, or None where that commit
    is unreadable or did not hold one yet (its first introduction).

    UNREADABLE IS SAID, NOT SWALLOWED (post-build-review #295): a shallow
    checkout cannot reach the push's base, and falling back to HEAD there
    compared the baseline with itself, so a gain committed in the push
    passed in silence. Now the gate prints that the gain check was skipped,
    and why; the stale-entry check still runs."""
    ref = _diff_base.diff_base(root=root)
    if not _diff_base._resolves(ref, root):
        wanted = (os.environ.get(_diff_base.ENV_VAR) or "").strip() or ref
        print(f"provisional: note - gain check skipped: the push's base ({wanted}) cannot be "
              f"read from this checkout (a shallow clone, or a first commit), so whether "
              f"{BASELINE} gained an entry is unchecked here.")
        return None
    shown = subprocess.run(["git", "show", f"{ref}:{BASELINE}"], cwd=root,
                           capture_output=True, text=True)
    if shown.returncode != 0:
        return None
    return _entries(yaml.load(shown.stdout, Loader=_LOADER))


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    root = root or ROOT
    parser = argparse.ArgumentParser(prog="validate-provisional")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write-baseline", action="store_true")
    mode.add_argument("--prune", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    markers = scan(load_register(root))
    live = {m.key for m in markers}
    path = root / BASELINE

    if args.write_baseline:
        if path.exists():
            print(f"{BASELINE} already exists - it is written once and only shrinks; "
                  f"use --prune to take answered entries off.")
            return 1
        write_baseline(root, markers)
        print(f"wrote {BASELINE}: {len(live)} entries on "
              f"{len({m.req_id for m in markers})} built requirements.")
        return 0

    if not path.exists():
        print(f"provisional: {BASELINE} is missing - the gate needs its baseline, and "
              f"warning on every marker instead would bury the new ones.")
        return 1
    baseline = load_baseline(root)

    if args.prune:
        kept = baseline & live
        write_baseline(root, kept)
        print(f"pruned {len(baseline) - len(kept)} entr(y/ies); {len(kept)} remain.")
        return 0

    problems = [f"{rid} {field} {fp} is in {BASELINE} but no longer an unanswered marker "
                f"(answered, reworded or gone) - take it off with --prune, so the "
                f"baseline only shrinks"
                for rid, field, fp in sorted(baseline - live)]
    base = _baseline_at_base(root)
    if base is not None:
        problems += [f"{BASELINE} gained {rid} {field} {fp}, which the push's base did not "
                     f"hold - the baseline only shrinks; answer the choice instead"
                     for rid, field, fp in sorted(baseline - base)]

    new = [m for m in markers if m.key not in baseline]
    for m in new:
        print(f"warning: {m.req_id} {m.field} item {m.item} carries an unanswered "
              f"PROVISIONAL choice - put it to Keith, and once answered write "
              f"'SETTLED by Keith <date>' or 'answered by Keith <date>' in the item.")
    for p in problems:
        print(f"provisional: {p}")
    if problems:
        return 1
    print(f"provisional OK - {len(new)} new unanswered choice(s) in built requirements; "
          f"{len(baseline)} baselined.")
    if new:
        return int(os.environ.get(WARNING_EXIT_VAR) or 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
