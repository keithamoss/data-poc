"""Supplies nothing can place, counted together (REQ-PIPE-064).

A HOLD IS THE CORRECT OUTPUT OF THE RULE, NOT A DEFECT IN IT. Where a
rule genuinely cannot know, it says so rather than committing silently
- a standing principle in this design rather than a one-off, and it has
now produced three separate requirements in this area alone. Defaulting
a supply nothing can place into a future slot is the forward cascade
again, arriving by the recovery path rather than by the rule.

THEY AGGREGATE, and that is a scale requirement rather than a
presentation choice. At two datasets a banner per held supply is fine;
at the ~30 this is a PoC for it is thirty banners, and a banner per
dataset is exactly how people learn to ignore a whole class of warning.
So this counts and groups, and never returns one element per supply.

RE-PRESENTED EVERY RUN. A hold is a state that persists until somebody
resolves it, not an event reported once into a log nobody re-reads.
Nothing here marks a hold as seen.

WHAT A HOLD COSTS, stated because the blast radius is not zero. The
held supply stays STAGED - staging asserts only that this landed at
this time, which is true wherever it eventually files, so holding costs
nothing and loses nothing there. It is NOT QA'd: the single-table
checks could run without a period, but drift and previous-period
comparison cannot, so partial QA produces a verdict that has to be
thrown away once the slot is known - or worse, a GREEN one sitting in
history against no period at all. Every other dataset in the delivery
is processed normally, but any cross-table check reading a held table
reads RED naming it. Scoped to what actually depends on the held thing.

THIS IS A DEAD END UNTIL SPRINT 12, and saying so is required rather
than optional: the resolution path is a human assigning the supply to
a slot or rejecting it, and that write path belongs with the decision
log. A hold nobody can clear is indistinguishable from a bug, so the
report says which it is.
"""
from __future__ import annotations

from dataclasses import dataclass

from qa_tools.common.assignment import Assignment


@dataclass(frozen=True)
class HeldSupply:
    """One supply the rule declined to place, and why."""

    dataset_id: str
    supply_id: str
    unavailable: tuple[tuple[str, str], ...]

    @classmethod
    def of(cls, decided: Assignment) -> "HeldSupply":
        return cls(dataset_id=decided.dataset_id, supply_id=decided.supply_id,
                    unavailable=decided.unavailable)


@dataclass(frozen=True)
class Holds:
    """Every outstanding hold, as ONE thing rather than a list of
    banners (criterion 8)."""

    supplies: tuple[HeldSupply, ...]

    @property
    def total(self) -> int:
        return len(self.supplies)

    @property
    def datasets(self) -> tuple[str, ...]:
        return tuple(sorted({h.dataset_id for h in self.supplies}))

    @property
    def needs_action(self) -> bool:
        """Criterion 5: a hold is an event NEEDING ACTION, not an
        informational one. The distinction is the whole difference
        between a queue somebody drains and a line in a log."""
        return self.total > 0

    def summary(self) -> str:
        """One line for the whole class, never one per supply."""
        if not self.supplies:
            return "No supply is currently held."
        datasets = self.datasets
        return (f"{self.total} supply/supplies held across "
                f"{len(datasets)} dataset(s) - {', '.join(datasets)}. "
                f"Each needs somebody to assign it to a slot or reject it.")


def holds_in(decisions) -> Holds:
    """The holds among a run's assignments.

    Takes the decisions rather than reading a store, because the
    resolution path that would write one does not exist yet - and a
    function that invented a store now would have to be unpicked when
    it does.
    """
    return Holds(supplies=tuple(HeldSupply.of(d) for d in decisions if d.is_held))
