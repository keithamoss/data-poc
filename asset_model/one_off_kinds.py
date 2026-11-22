"""The kind plug-ins: what each kind of one-off brings that the shared
one-off layer does not (REQ-PIPE-446 criterion 2).

ONE REGISTRY, FILLED BY THE KINDS THEMSELVES. A kind folder under one-offs/
is served only by a plug-in registered here in code - the reader for its
package, its generator, its check layers and its display words (its name in
the singular and plural, 'extraction' / 'extractions', and its own check
layer's, 'Recipe check'). A kind folder with no plug-in fails `mothman
check`, naming the folder. Nothing here names a kind: each kind's module
registers itself, and every module in the `one_off_kinds` package beside
this one is imported when the registry is first asked, so a new kind is a
new file there and nothing else.

THE FIRST KIND, THE EXTRACTION, IS REQ-PIPE-439's AND REQ-PIPE-440's - its
recipe reader and its generated folder - and is not built here.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Callable, Mapping


@dataclass(frozen=True)
class Kind:
    """One kind of one-off."""

    #: Its folder's name under one-offs/.
    name: str
    #: Its display words - never its folder name, on any page or line.
    singular: str
    plural: str
    #: The name of its own check layer, e.g. 'Recipe check'.
    layer: str
    #: Reads the package a one-off of this kind is opened from.
    reader: Callable | None = None
    #: Generates a one-off folder from what the reader read.
    generator: Callable | None = None
    #: Its check layers, beside the shared default layer.
    check_layers: tuple = ()
    #: {gate label: applies?} for every per-asset gate of `mothman check`
    #: (REQ-PIPE-448 criterion 1) - declared, never defaulted.
    gates: Mapping[str, bool] = field(default_factory=dict)


_REGISTRY: dict[str, Kind] = {}
_DISCOVERED = False


def register(kind: Kind) -> Kind:
    """Register a kind - from its own module. Registering one name twice with
    a different plug-in is refused rather than replaced."""
    held = _REGISTRY.get(kind.name)
    if held is not None and held != kind:
        raise ValueError(f"one-off kind {kind.name!r} is registered twice")
    _REGISTRY[kind.name] = kind
    return kind


def unregister(name: str) -> None:
    """For the suite, which registers a test kind for one test."""
    _REGISTRY.pop(name, None)


def _discover() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True
    try:
        package = importlib.import_module("asset_model.kinds")
    except ModuleNotFoundError:
        return
    for info in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"asset_model.kinds.{info.name}")


def get(name: str) -> Kind | None:
    _discover()
    return _REGISTRY.get(name)


def registered() -> list[Kind]:
    _discover()
    return [_REGISTRY[n] for n in sorted(_REGISTRY)]
