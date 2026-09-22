"""Gate: every dataset contract agrees with the one hierarchy
(REQ-QAC-039).

WHY THIS EXISTS AT ALL. Stating the tree once in
`contract/data-asset.yaml` fixes the twelve Python files that used to
carry it, but the dataset contracts carry their own `id`, `name` and
`domain` - and on 2026-09-23 all of them had drifted. BDM declared
`id: bdm-birth-registrations` against the `birth-registrations` every
check_id and every qa_results/ path already used. CP declared
`domain: child-and-family-safety`, which matched neither its collection
(`child-protection`) nor its agency. Nothing read those fields, so
nothing noticed, for however long they had been wrong.

Correcting them without a gate would just reset the clock. The whole
point of this requirement is that the hierarchy is stated once and
everything else is held to it, and a copy nobody checks is a copy that
drifts - which is the argument the twelve Python files had already
proved.

THE RULE, and it is deliberately narrow:
- `domain` names the AGENCY that owns the contract.
- `id` names what the contract DESCRIBES - a dataset for a
  dataset-scoped contract, a collection for a collection-scoped one.
- `name` is that same thing's display name from the hierarchy.

Keith's call, 2026-09-23, choosing consistency of MEANING over
minimising the diff. The alternative - `domain` names the collection -
left Child Protection's contract saying `id: child-protection` and
`domain: child-protection`, one field restating another, which is
exactly the kind of oddity a later reader 'fixes' without knowing why
it was that way.

WHAT IT DOES NOT CHECK. The contract's schema, its quality rules, its
check definitions - those are `validate_check_lifecycle.py`'s and the
real tools' business. This gate answers one question: does this
contract agree with the tree about where it sits.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from qa_tools.common import hierarchy

CONTRACT_DIR = Path(__file__).resolve().parent.parent.parent / "contract"

# The dataset contracts, and what each one describes. A contract scoped
# to a COLLECTION names that collection; one scoped to a DATASET names
# that dataset. Listed rather than inferred from the filename, because
# a filename is not a declaration and this gate exists precisely to
# stop things being assumed.
CONTRACTS: tuple[tuple[str, str], ...] = (
    ("bdm-birth-registrations-contract.yaml", "birth-registrations"),
    ("child-protection-contract.yaml", "child-protection"),
)


def _describes(name: str) -> tuple[str, str, str]:
    """(expected_id, expected_name, expected_domain) for what a contract
    describes - resolving it as a dataset first, then as a collection."""
    try:
        entry = hierarchy.dataset(name)
        return (entry.dataset_id, entry.dataset_name, entry.agency_id)
    except hierarchy.UnknownDatasetError:
        pass
    members = hierarchy.datasets_in_collection(name)  # raises if neither
    first = members[0]
    return (first.collection_id, first.collection_name, first.agency_id)


def validate() -> list[str]:
    errors: list[str] = []
    for filename, describes in CONTRACTS:
        path = CONTRACT_DIR / filename
        if not path.exists():
            errors.append(f"{filename}: no such contract")
            continue

        with open(path) as f:
            doc = yaml.safe_load(f) or {}

        try:
            expected_id, expected_name, expected_domain = _describes(describes)
        except hierarchy.UnknownDatasetError as exc:
            errors.append(f"{filename}: describes {describes!r}, which the hierarchy does not define - {exc}")
            continue

        for field, expected in (("id", expected_id), ("name", expected_name), ("domain", expected_domain)):
            actual = doc.get(field)
            if actual != expected:
                errors.append(
                    f"{filename}: {field} is {actual!r}, but the hierarchy says {expected!r}. "
                    f"Fix the contract, or fix contract/data-asset.yaml if the hierarchy is wrong - "
                    f"not both independently."
                )
    return errors


def main() -> int:
    """Exit code, not sys.exit - matching the other validate_* gates, so
    cli/ can wrap it in a ClickException the same way."""
    errors = validate()
    if errors:
        print(f"hierarchy validation FAILED ({len(errors)} error(s)):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    datasets = hierarchy.all_datasets()
    collections = {d.collection_id for d in datasets}
    agencies = {d.agency_id for d in datasets}
    print(
        f"hierarchy validation OK - {len(agencies)} agenc(ies), {len(collections)} collection(s), "
        f"{len(datasets)} dataset(s), {len(CONTRACTS)} contract(s) in agreement."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
