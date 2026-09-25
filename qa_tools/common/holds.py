"""A supply nobody may choose for you (REQ-PIPE-059).

WHEN TWO FILES IN ONE DELIVERY ARE BOTH THE SAME DATASET, that dataset's
supply is HELD. Not merged, not resolved by picking one - held, and left
for a person.

WHY NOT JUST PICK ONE. Every rule for picking is a guess dressed as a
policy, and each fails silently: take the newest and you drop the one a
supplier will later say they sent; take the largest and you drop a
correction; take the lexically last and you have picked by alphabet.
Merging is worse than any of them - a supply is one table VERSION, and
concatenating two manufactures a supply that never arrived, which is the
same category of untruth as recording a missed delivery as met.

WHAT WAS ALREADY TRUE, and what this changes. Arrival.path_for() has
always refused when a dataset matched several files, its own docstring
saying that taking the first would silently drop a supplier's second.
That refusal was an EXCEPTION, which took the whole run with it. This
turns it into a handled operational state: the dataset is held, and
every other dataset in the same delivery is processed exactly as usual.

A HELD SUPPLY IS STILL STAGED, AND IS NOT QA'd (Keith, 2026-09-24, and
the reasoning is sharper than the options it settles). Both files load,
so the material to resolve the hold with is there. No view resolves the
logical name, because REQ-PIPE-068 refuses to choose between candidates
either - so nothing can read it, which is how "not QA'd" is enforced by
the mechanism rather than by remembering. The single-table checks COULD
run without a period, but drift and previous-period comparison cannot,
so partial QA produces a verdict that has to be thrown away once the
slot is known - and worse, possibly a GREEN one sitting in history
against no period at all.

THE BLAST RADIUS IS NOT ZERO, and saying so is the point. Any
cross-table check reading a held table reads RED naming it, which for
cp_clients is real rather than hypothetical: cp_notifications,
cp_investigations and cp_placements all carry a referential check
against it. Holding one table reddens checks on others - scoped to what
actually depends on the held thing, rather than either nothing or
everything.

IT HOLDS EVERY TIME, including the legitimate split extract (Keith,
2026-09-24, knowing the cost). A supplier who routinely splits one table
generates a hold per period, per dataset, indefinitely. He chose that
because a proper splitting mechanism is the real answer and a hold is
the honest placeholder until one exists - see plans/running-thoughts.md
 #39 for splitting and #40 for deltas, the second of which contradicts
this requirement's own foundation rather than extending it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hold:
    """One dataset's supply, in one delivery, that cannot be chosen.

    Carries every file that matched, because the question a person
    opens this with is "what could it not choose between" - a count
    answers nothing and the delivery name alone sends them to a
    directory listing.
    """

    delivery_name: str
    dataset_id: str
    files: tuple[str, ...]

    def describe(self) -> str:
        return (f"delivery {self.delivery_name!r}: {len(self.files)} files are all "
                f"{self.dataset_id} ({', '.join(self.files)}), so that dataset's supply "
                f"is HELD - it is staged but not checked, and nothing will choose "
                f"between them. Every other dataset in this delivery is processed as "
                f"usual.")


def holds_in(recognition) -> tuple[Hold, ...]:
    """Every dataset in one delivery that matched more than one file.

    Also what catches a CATCH-UP DELIVERY carrying two periods of the
    same table - August's and November's cp_clients are two files
    matching one dataset's pattern, so nothing has to read a declared
    period and no separate mechanism is needed. The residual case,
    different tables landing in different periods, is a promotion gate
    in sprint 11.
    """
    return tuple(
        Hold(delivery_name=recognition.delivery_name, dataset_id=dataset_id,
             files=tuple(sorted(names)))
        for dataset_id, names in sorted(recognition.by_dataset.items())
        if len(names) > 1)


def held_datasets(recognition) -> frozenset[str]:
    """Just the ids, for the many callers that only need to skip them."""
    return frozenset(h.dataset_id for h in holds_in(recognition))
