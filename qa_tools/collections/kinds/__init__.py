"""Each one-off kind's ONE SHARED ADAPTER (REQ-PIPE-440 criterion 4,
REQ-PIPE-448 criterion 4): a one-off carries no adapter module of its own, so
every collection of a one-off of kind <kind> is served by
qa_tools/collections/kinds/<kind>.py's `adapter_for(collection)`.

Found by the kind's folder name, which assets.Asset.kind reads from where the
folder is - never named in code, as the enduring assets' adapters are never
named (REQ-PIPE-342 criterion 5)."""
from __future__ import annotations

import importlib
from types import SimpleNamespace


class NoSharedAdapter(LookupError):
    """A kind with no shared adapter module."""


def module_for(kind: str):
    from asset_model.collections import ID_PATTERN

    if not ID_PATTERN.fullmatch(kind):
        raise NoSharedAdapter(f"one-off kind {kind!r} is not a hierarchy id")
    try:
        return importlib.import_module(f"qa_tools.collections.kinds.{kind.replace('-', '_')}")
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("qa_tools.collections.kinds."):
            raise NoSharedAdapter(f"one-off kind {kind!r} has no shared adapter - "
                                  f"qa_tools/collections/kinds/{kind.replace('-', '_')}.py "
                                  f"does not exist") from None
        raise


def adapter_module(kind: str, collection):
    """What qa_tools.collections.adapter_module() returns for a one-off's
    collection: its ADAPTER, from the kind's shared module, and that module's
    file."""
    module = module_for(kind)
    return SimpleNamespace(ADAPTER=module.adapter_for(collection), __file__=module.__file__)
