"""Which effective-dated version is in force on a date - ONE implementation
(REQ-PIPE-113 NFR 2).

Participation versions, calendar versions and timezone versions all answer
the same question, and three hand-written answers to "in force on" would
eventually disagree - REQ-PIPE-123 rejected a copy of the amber module for
exactly that reason. Each caller still decides what "nothing in force yet"
means for it (a dataset not yet owing, a calendar falling back to its first
version, a timezone failing loudly); this module only finds the version.

BY BISECTION, never by walking the list (NFR 3): a daily calendar at thirty
datasets asks this once per slot, and `bisect` with `key=` reads O(log n)
versions without building a list of their dates first.
"""
from __future__ import annotations

import bisect
from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


def _effective_from(version) -> object:
    return version.effective_from


def index_on(versions: Sequence[T], on, key: Callable[[T], object] = _effective_from) -> int | None:
    """The index of the last version whose `key` is on or before `on`, or
    None where every version starts after it. `versions` must be in
    ascending `key` order - every loader here sorts them on reading."""
    i = bisect.bisect_right(versions, on, key=key) - 1
    return i if i >= 0 else None


def version_on(versions: Sequence[T], on, key: Callable[[T], object] = _effective_from) -> T | None:
    """The version in force on `on`, or None where none has begun."""
    i = index_on(versions, on, key)
    return None if i is None else versions[i]
