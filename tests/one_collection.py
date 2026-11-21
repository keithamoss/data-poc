"""A test's premise that the selected asset holds ONE collection, stated
rather than read off the real configuration. The daily asset was such an
asset until Mental Health joined it (REQ-QAC-350, 2026-11-18); a test about a
one-collection asset's behaviour reads it with the named collection alone,
through the one function every reader of the registry calls."""
from __future__ import annotations


def only(monkeypatch, collection_id: str) -> None:
    from asset_model import collections

    real = collections.all_collections
    monkeypatch.setattr(collections, "all_collections",
                        lambda *a, **k: [c for c in real(*a, **k) if c.id == collection_id])
