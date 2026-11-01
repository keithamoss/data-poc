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


from pathlib import Path

PACKAGE = Path(__file__).resolve().parent / "collections"


def declaration_problems() -> list[str]:
    """What a provider declares that only a new collection would trip over
    (post-build-review #232): a provider filed under another collection's
    module, a dataset its collection does not own, a target trial on a
    multi-table collection (the trial tries one table's targets, and only a
    one-table collection's commands can run it), a lever set nothing knows,
    or one lever set declared by two collections (each set reads one
    dataset's rules)."""
    from generator import collections
    from generator.collections.base import CLIENT_POSTCODES, NULL_RATE
    from qa_tools import collections as registry

    out: list[str] = []
    levers: dict[str, str] = {}
    for coll in registry.all_collections():
        try:
            provider = collections.provider(coll.id)
        except collections.NoProviderError:
            continue
        where = f"generator/collections/{coll.module_name}.py"
        if provider.collection_id != coll.id:
            out.append(f"{where} names collection {provider.collection_id!r}, not {coll.id!r}")
            continue
        owned = [d.dataset_id for d in coll.datasets]
        for field in ("dataset_id", "amber_dataset"):
            value = getattr(provider, field)
            if value is not None and value not in owned:
                out.append(f"{where}'s {field}: dataset {value!r} is not one of {coll.id}'s "
                           f"({', '.join(owned)})")
        # A TRIAL OF A COLLECTION OF SEVERAL DATASETS IS NO LONGER REFUSED
        # (REQ-GEN-298 criterion 10): each tried supply names its own dataset
        # and file, and is tried against its own table. What a trial still
        # needs is somewhere each supply's verdict is compared.
        if provider.target_trial and not provider.target_datasets:
            out.append(f"{coll.id} declares a target trial and no target_datasets - a trial "
                       f"compares each supply in its own dataset, so it must name them")
        if provider.target_levers is not None:
            if provider.target_levers not in (NULL_RATE, CLIENT_POSTCODES):
                out.append(f"{where} declares lever set {provider.target_levers!r}, which "
                           f"generator/targeting.py does not know")
            elif provider.target_levers in levers:
                out.append(f"lever set {provider.target_levers!r} is declared by both "
                           f"{levers[provider.target_levers]} and {coll.id} - each set reads "
                           f"one dataset's rules")
            else:
                levers[provider.target_levers] = coll.id
    return out


def orphan_problems(package: Path = PACKAGE) -> list[str]:
    """A provider module naming no declared collection - a misspelt one would
    otherwise leave its collection silently ungenerated."""
    from qa_tools import collections as registry

    declared = {c.module_name for c in registry.all_collections()}
    return [f"generator/collections/{p.stem}.py names no declared collection"
            for p in sorted(package.glob("*.py"))
            if p.stem not in ("__init__", "base") and p.stem not in declared]


def problems() -> list[str]:
    from generator import collections

    found = collections.providers()
    out = collections.seed_range_problems(found) + collections.order_problems(found)
    for provider in found:
        try:
            provider.check_seeds()
        except collections.base.SeedOutOfRange as exc:
            out.append(str(exc))
    from generator import synthetic_inputs

    # REQ-QAC-294 criterion 3: the generator-only placing configuration agrees
    # with the contracts it names.
    return out + declaration_problems() + orphan_problems() + synthetic_inputs.problems()


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
