"""The values derived from an agreement, worked out once (REQ-PIPE-400, signed
by Keith 2026-11-14 as speed-anchor v2).

WHY. A generation and a replay ask the same schedule questions inside their
loops - every dataset's slots, its periods, a calendar's periods, a dataset's
standing on a date - and each answer was worked out again every time:
post-build-review #318 counted 1.5 million Agreement.standing_on calls in one
generation. Keith's S1 (2026-11-14): 'with slots and periods derived from it
worked out once'.

KEYED ON THE AGREEMENT USED AND THE ZONES IN FORCE (the architect's B3). Each
of the four takes `agreement=`, so the key is the Agreement each call actually
uses - the one passed, or schedule.agreement_to_read()'s answer - never
agreement.current() looked up again. And a staged correction
(correction_trial.configured) swaps asset_time.timezone_versions as well as the
agreement, and slots resolve zones through the former, so the key holds both:
a value worked out under one calendar or one set of zones never answers a call
made under another.

CORRECT WITHOUT A PIN. An Agreement is a frozen dataclass of MappingProxyType
fields and cannot be hashed, but config_yaml.Built hands back the same instance
for the same text, so an IDENTITY key is content-keyed by construction. The
memo holds a strong reference to every agreement and zones value it keys on,
so an object id is never reused while it is remembered, and it keeps only the
most recent few, so a long-running unpinned process - a dashboard build - does
not grow without limit.

WHAT IT HANDS BACK is immutable or the caller's own copy (REQ-PIPE-254
criterion 7): a list is copied on every call, its elements being frozen
records. Not functools.lru_cache or cache (REQ-PIPE-254 criterion 16): those
key on hashable arguments and hold no agreement still.
"""
from __future__ import annotations

import threading
from collections import OrderedDict

from asset_model import asset_time

#: How many (agreement, zones) pairs are remembered: the committed one and a
#: few staged corrections' (a replay stages one per arrival it re-reads).
AGREEMENTS = 16


class Memo:
    """Values worked out per (agreement, zones) pair, then per argument set."""

    def __init__(self, agreements: int = AGREEMENTS):
        self._limit = agreements
        # (id(agreement), id(zones)) -> (agreement, zones, {key: value})
        self._held: "OrderedDict[tuple[int, int], tuple[object, object, dict]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, agreement, key: tuple, compute):
        """The value `compute()` works out for `key` under `agreement` and the
        zones in force now - worked out at most once per pair and key. A
        computation that raises stores nothing."""
        zones = asset_time.timezone_versions()
        pair = (id(agreement), id(zones))
        with self._lock:
            held = self._held.get(pair)
            if held is not None and held[0] is agreement and held[1] is zones:
                self._held.move_to_end(pair)
                values = held[2]
                if key in values:
                    return values[key]
        value = compute()
        with self._lock:
            held = self._held.get(pair)
            if held is None or held[0] is not agreement or held[1] is not zones:
                held = self._held[pair] = (agreement, zones, {})
            held[2][key] = value
            self._held.move_to_end(pair)
            while len(self._held) > self._limit:
                self._held.popitem(last=False)
        return value

    def __len__(self) -> int:
        """How many (agreement, zones) pairs it holds."""
        return len(self._held)

    def clear(self) -> None:
        with self._lock:
            self._held.clear()


#: The one memo the four functions share (NFR MAINTAINABILITY: one memo, in
#: asset_model/, rather than a cache per function).
MEMO = Memo()


def remembered(agreement, function: str, args: tuple, compute):
    """`compute()`'s value for `function(*args)` under `agreement`, worked out
    once; a list comes back as the caller's own copy."""
    value = MEMO.get(agreement, (function, *args), compute)
    return list(value) if isinstance(value, list) else value
