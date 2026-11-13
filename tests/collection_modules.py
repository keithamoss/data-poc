"""THE ONE TEST HELPER FOR ADAPTER AND PROVIDER MODULES (REQ-PIPE-369
criterion 5): a test reaches an adapter or provider module the way the
pipeline does - loaded by path from the selected asset's folder - and never
imports one by package name. A test that patches a provider's attribute
therefore patches the module the driver actually runs.

`install` puts a fake in the place the by-path lookup would find it, for a
test that adds a collection of its own; monkeypatch takes it out again.
"""
from __future__ import annotations

import sys

from qa_tools.common import assets


def adapter_module(collection_id: str):
    """The collection's adapter module, by the registry's own lookup."""
    from qa_tools import collections

    return collections.adapter_module(collection_id)


def provider_module(collection_id: str):
    """The collection's generator provider module, by the registry's own
    lookup."""
    from generator import collections

    return collections.provider_module(collection_id)


def name(kind: str, module: str) -> str:
    """Where a `kind` ("adapter" or "provider") module named `module` is
    registered for the selected asset."""
    return assets.module_name(kind, module)


def install(monkeypatch, kind: str, module: str, fake) -> None:
    """Make `fake` the selected asset's `kind` module `module`, as if its file
    existed - registered under the by-path name, with that file as its
    __file__ - until the test ends."""
    fake.__file__ = str(assets.module_file(kind, module))
    monkeypatch.setitem(sys.modules, name(kind, module), fake)


def installed(kind: str, module: str):
    """The module `install` put in place."""
    return sys.modules[name(kind, module)]


def uninstall(monkeypatch, kind: str, module: str) -> None:
    """Take an installed fake out again for the rest of the test - so the
    lookup finds no file, as for a collection with no adapter."""
    monkeypatch.delitem(sys.modules, name(kind, module))
