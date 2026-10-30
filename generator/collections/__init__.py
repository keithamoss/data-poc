"""The generator's provider registry (REQ-GEN-246): which collections have a
synthetic generator, and the provider each one's rows, seeds and period plan
are reached through.

ONE DRIVER, A PROVIDER PER COLLECTION. generator/driver.py owns the slot
loop, the bookkeeping, delivery and receipt writing and injection placement;
a provider at generator/collections/<id>.py owns only what genuinely differs
- how its rows are made, its seed schedule and its period plan. A provider
is its own module, separate from the collection's QA adapter in
qa_tools/collections/: a real deployment's collections have no synthetic
generator, and an adapter that carried one would import generator code into
every real deployment (the requirement's decision 4).

CHOSEN BY CONFIGURATION, NEVER IMPORTED FROM IT: a collection's id picks
which module of this package loads, exactly as qa_tools/collections does
for adapters, and only an id the hierarchy declares may.

CHEAP TO READ: every provider module is importable without pandas or numpy
(criterion 7), so asking what a provider declares - its seed ranges, whether
it supports a target trial - costs no tool import.
"""
from __future__ import annotations

import importlib

from generator.collections.base import NoProviderError, Provider  # noqa: F401 - re-exported


def provider(collection_id: str) -> Provider:
    """The provider for `collection_id`, or NoProviderError naming it.

    The id is the registry's own (qa_tools.collections.by_id), so an
    undeclared collection is refused there by name; a declared one with no
    provider module is refused here by name - never generated with another
    collection's behaviour."""
    from qa_tools import collections

    coll = collections.by_id(collection_id)
    if not collections.ID_PATTERN.fullmatch(coll.id):
        raise NoProviderError(f"collection id {coll.id!r} is not a hierarchy id, so it cannot "
                              f"name a generator provider")
    try:
        module = importlib.import_module(f"generator.collections.{coll.module_name}")
    except ModuleNotFoundError as exc:
        if exc.name != f"generator.collections.{coll.module_name}":
            raise
        raise NoProviderError(
            f"collection {collection_id!r} has no synthetic generator: no provider module "
            f"generator/collections/{coll.module_name}.py") from None
    return module.PROVIDER


def for_dataset(dataset_id: str) -> Provider:
    """The provider of the collection `dataset_id` belongs to - refused by
    name when the hierarchy does not declare the dataset, or its collection
    has no provider."""
    from qa_tools.common import hierarchy

    try:
        collection_id = hierarchy.dataset(dataset_id).collection_id
    except KeyError:
        raise NoProviderError(f"dataset {dataset_id!r} is not declared in the hierarchy, so no "
                              f"generator provider makes it") from None
    return provider(collection_id)


def providers() -> list[Provider]:
    """Every declared collection's provider, in hierarchy order - the
    collections without one are simply not generated."""
    from qa_tools import collections

    out = []
    for coll in collections.all_collections():
        try:
            out.append(provider(coll.id))
        except NoProviderError:
            continue
    return out


def order_problems(found: list[Provider] | None = None,
                   only: str | None = None) -> list[str]:
    """Every provider whose declared dependency (Provider.depends_on) has no
    provider or generates after it in hierarchy order - the order every
    generation runs in (REQ-GEN-334 criterion 6) - naming both. `only`: that
    collection's provider alone."""
    found = providers() if found is None else found
    order = {p.collection_id: i for i, p in enumerate(found)}
    problems = []
    for i, p in enumerate(found):
        if only is not None and p.collection_id != only:
            continue
        for dep in p.depends_on:
            if dep not in order:
                problems.append(
                    f"{p.collection_id}'s provider depends on {dep}, which has no generator "
                    f"provider, so the supplies it reads would not exist")
            elif order[dep] > i:
                problems.append(
                    f"{p.collection_id}'s provider depends on {dep}, which generates after "
                    f"it in hierarchy order, so it would read a history not yet generated - "
                    f"declare {p.collection_id} after {dep}")
    return problems


def seed_range_problems(found: list[Provider] | None = None) -> list[str]:
    """Every pair of providers whose declared seed ranges overlap, naming
    both (criterion 3) - what makes REQ-GEN-232's disjoint Emergency
    Department seeds a check rather than a promise."""
    found = providers() if found is None else found
    problems = []
    for i, a in enumerate(found):
        for b in found[i + 1:]:
            for lo_a, hi_a in a.seed_ranges:
                for lo_b, hi_b in b.seed_ranges:
                    if lo_a < hi_b and lo_b < hi_a:
                        problems.append(
                            f"the seed ranges of {a.collection_id} [{lo_a}, {hi_a}) and "
                            f"{b.collection_id} [{lo_b}, {hi_b}) overlap - two collections "
                            f"drawing the same seeds would draw the same rows")
    return problems
