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

IT ALSO CHECKS `arrivalPattern`, added 2026-09-23 (REQ-GEN-043) after
that block turned out to have drifted in exactly the way this gate
exists to catch - and to have survived REQ-QAC-039's own sweep the same
morning, because nothing looked INSIDE a customProperty's value.

What it had: BDM declared `dataset_id: bdm-birth-registrations`, an id
corrected hours earlier and belonging to nothing; all six CP patterns
declared `child-protection-casework`, which was both stale AND the
COLLECTION rather than the per-file dataset. Since a file's own dataset
has to be derivable from its filename through that dataset's
configured pattern, a pattern naming a dataset that does not exist
cannot derive anything.

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

def contracts() -> tuple[tuple[str, str], ...]:
    """(filename, what it describes) for every contract the hierarchy
    names. A contract scoped to a COLLECTION describes that collection;
    one scoped to a DATASET describes that dataset.

    DERIVED, not maintained (post-build-review #36). This was a
    hand-written tuple restating a relation the hierarchy already
    holds - every dataset declares its own `contract:` - so a third
    collection meant editing two places, and forgetting the second one
    failed SILENTLY: the new contract simply never got checked, by the
    gate whose whole job is noticing that a contract and the tree
    disagree.

    The comment this replaces said the list was written out rather than
    "inferred from the filename, because a filename is not a
    declaration". That reasoning holds and is not what changed: nothing
    here reads a filename to decide anything. It reads the hierarchy's
    own declarations, which is the opposite of assuming.

    Which one a contract describes falls out of how many datasets name
    it: shared by several means it describes what they have in common,
    which is their collection; named by exactly one means it describes
    that dataset.
    """
    by_file: dict[str, list] = {}
    for entry in hierarchy.all_datasets():
        by_file.setdefault(entry.contract, []).append(entry)
    out = []
    for filename, entries in sorted(by_file.items()):
        describes = (entries[0].dataset_id if len(entries) == 1
                     else entries[0].collection_id)
        out.append((filename, describes))
    return tuple(out)


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


def _arrival_pattern_errors(filename: str, doc: dict) -> list[str]:
    """Every arrivalPattern entry naming a dataset the hierarchy does
    not define.

    A contract with no arrivalPattern is fine - not every dataset has
    one yet - but a pattern that HAS one must name something real.
    """
    errors: list[str] = []
    entry = next((p for p in (doc.get("customProperties") or [])
                  if p.get("property") == "arrivalPattern"), None)
    if entry is None:
        return errors
    known = {d.dataset_id for d in hierarchy.all_datasets()}
    for pattern in entry.get("value") or []:
        dataset_id = pattern.get("dataset_id")
        if dataset_id not in known:
            errors.append(
                f"{filename}: arrivalPattern {pattern.get('keyPattern')!r} names dataset "
                f"{dataset_id!r}, which the hierarchy does not define. A file's own dataset is "
                f"derivable from its name only through this pattern, so one naming a dataset "
                f"that does not exist derives nothing. Known: {', '.join(sorted(known))}")
    return errors


def validate() -> list[str]:
    errors: list[str] = []
    named = contracts()
    # A CONTRACT NOTHING NAMES is the one thing deriving the list could
    # have lost - and it was never checked before either, because
    # nobody had added it to the hand-written tuple. So this is
    # coverage that list did not have (post-build-review #36).
    if CONTRACT_DIR.exists():
        known = {filename for filename, _ in named}
        for path in sorted(CONTRACT_DIR.glob("*-contract.yaml")):
            if path.name not in known:
                errors.append(
                    f"{path.name}: no dataset in contract/data-asset.yaml names this "
                    f"contract, so nothing checks it. Point a dataset at it, or remove it.")
    for filename, describes in named:
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
        errors.extend(_arrival_pattern_errors(filename, doc))
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
        f"{len(datasets)} dataset(s), {len(contracts())} contract(s) in agreement."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
