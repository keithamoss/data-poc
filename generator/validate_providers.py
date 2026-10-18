"""`mothman check`'s providers gate (REQ-GEN-246 criterion 3): no two
generator providers' declared seed ranges overlap, and every seed each one
derives lies inside its own (criterion 2, checked here as well as before
each generation, so a bad schedule fails at review rather than at the
first regeneration).

Two collections drawing the same seeds would draw the same rows - a
duplicated history that reads as a real one. A range declared once and
checked mechanically is what makes REQ-GEN-232's disjoint Emergency
Department seeds a check rather than a promise.

READS DECLARATIONS ONLY: no provider module imports pandas or numpy at
module level (criterion 7), so this gate costs no tool import.
"""
from __future__ import annotations

import sys


def problems() -> list[str]:
    from generator import collections

    found = collections.providers()
    out = collections.seed_range_problems(found)
    for provider in found:
        try:
            provider.check_seeds()
        except collections.base.SeedOutOfRange as exc:
            out.append(str(exc))
    return out


def main() -> int:
    from generator import collections

    found = problems()
    if found:
        for p in found:
            print(f"providers: {p}", file=sys.stderr)
        return 1
    print(f"providers OK - {len(collections.providers())} generator provider(s), seed ranges "
          f"disjoint and every derived seed inside its own")
    return 0


if __name__ == "__main__":
    sys.exit(main())
