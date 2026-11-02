"""The CLI's collection groups for the asset a test acts for (the asset split).

`mothman` builds the selected asset's collection groups once, at import
(REQ-PIPE-363 criterion 2) - one process, one asset. The suite is one process
running tests of both assets, so when the asset a test selects is not the one
cli.app was built for, its groups are rebuilt IN PLACE on the same `cli`
object: every module that did `from cli.app import cli` keeps a reference that
answers for the selected asset. Test-only; nothing that ships rebuilds them.
"""
from __future__ import annotations

import sys


def rebuild_for_selected() -> None:
    app = sys.modules.get("cli.app")
    if app is None:
        return
    from cli import collection_cli
    from qa_tools import collections as registry
    from qa_tools.common import assets

    asset = assets.selected_or_none()
    built_for = app._ASSET.name if app._ASSET is not None else None
    wanted = asset.name if asset is not None else None
    if built_for == wanted:
        return
    for name in list(app._COLLECTION_NAMES):
        app.cli.commands.pop(name, None)
    app._ASSET = asset
    app._COLLECTIONS = registry.all_collections() if asset is not None else []
    app._GROUPS = [collection_cli.make_group(c) for c in app._COLLECTIONS]
    for group in app._GROUPS:
        app.cli.add_command(group)
    app._COLLECTION_NAMES[:] = [g.name for g in app._GROUPS]
    for panel in getattr(app.cli, "panels", None) or []:
        if getattr(panel, "name", None) == "Collections":
            panel.commands = list(app._COLLECTION_NAMES)


class LazyCollectionCli:
    """A collection's command object (cli.collection_cli.of), looked up when
    it is used rather than when a module is imported - so a module naming
    both assets' collections imports under either, and each test reaches its
    own asset's. Attribute writes go to the real object, so monkeypatch.setattr
    and its undo act on it."""

    def __init__(self, short: str):
        object.__setattr__(self, "_short", short)

    def _real(self):
        from cli.collection_cli import of

        return of(object.__getattribute__(self, "_short"))

    def __getattr__(self, name):
        return getattr(self._real(), name)

    def __setattr__(self, name, value):
        setattr(self._real(), name, value)

    def __delattr__(self, name):
        delattr(self._real(), name)
