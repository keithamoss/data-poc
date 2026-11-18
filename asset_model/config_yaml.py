"""Configuration YAML, parsed once per process while its content is unchanged
(REQ-PIPE-156, signed by Keith 2026-10-06).

WHY. A profile of a real 12-arrival Child Protection replay found 5,911
`yaml.safe_load` calls - about half the bootstrap - re-reading files that do
not change during a run: the ODCS contract on every slot lookup, the asset
file on every connection, the environments file, the check metadata. Content
-memoised, the same replay took 95s instead of 178s
(REQ-PIPE-156).

KEYED ON THE BYTES, NOT ON MODIFICATION TIME OR SIZE. A test that changes
'14d' to '21d' inside one filesystem clock tick changes neither, and a cache
keyed on them would hand it the old document - silently, in exactly the tests
that exist to check configuration is honoured. Hashing a contract's text
costs microseconds; parsing it costs tens of milliseconds.

EVERY CALLER GETS ITS OWN COPY. Callers mutate what they read (a fixture
editing a loaded document before writing it back, a parser popping keys), and
a shared object would carry one caller's edit into the next. A deep copy of
the largest contract is under a millisecond.

PyYAML's C LOADER where it is installed (Keith chose both): every parse that
does happen is ~9x faster - 13 contract files 218ms -> 24ms, identical
results, measured 2026-10-06. The pure-Python loader where it is not.

BOUNDED and THREAD-SAFE: a run's four tools read configuration from worker
threads, so the cache is behind a lock and holds the most recently used
documents only.

VALUES BUILT FROM A FILE ARE KEYED THE SAME WAY (REQ-PIPE-254, signed by
Keith 2026-10-24). A module that turns a configuration file into something
richer - the hierarchy's Dataset records, the agreement, compiled patterns,
a check-id lookup - keeps what it built in a `Built` store, keyed on the
file's path AND its text as read on this call. So an edited or swapped file
is answered for what it says now, with nothing to clear, and an unchanged one
is answered without being parsed or built again. OUTSIDE A PINNED RUN
(REQ-PIPE-397) the file is READ ON EVERY CALL and never skipped on its
modification time, size or inode (criterion 15, as amended): a same-size edit
inside one clock tick keeps all three. Inside one, a file of the pinned
snapshot is answered from the snapshot - see THE PIN below. Before this, nine
such values sat behind functools.lru_cache, one per process or per path, and
a test that swapped a file had to know every cache to clear
(plans/post-build-review.md #217 is the one it missed). `mothman check`'s
`caches` gate now fails an lru_cache or cache under qa_tools/ or pipeline/
that is not on its allowlist (qa_tools/common/validate_caches.py).
"""
from __future__ import annotations

import copy
import os
import re
import threading
from pathlib import Path
from collections import OrderedDict

import yaml

#: The loader every parse uses - the C one when PyYAML was built with libyaml.
LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

#: How many distinct documents are kept. contract/ is ~220KB of YAML in 13
#: files; a run reads a few dozen distinct documents, small strings included.
MAX_DOCUMENTS = 256

_cache: "OrderedDict[str, object]" = OrderedDict()
_lock = threading.Lock()


# ---- OFFSET DATES (REQ-GEN-406 criterion 3; SA Q1, SETTLED by Keith 2026-11-14) ----
#
# A SYNTHETIC asset's configuration may write a date that frames its generated
# history as an offset from the history's anchor: `!anchor -99` is the date 99
# days before it, and `!anchor "calendar daily version {+0}"` writes one into a
# string. Resolved HERE, at the one parse every reader goes through, to the plain
# 'YYYY-MM-DD' string the file would otherwise hold - so the pipeline, the
# dashboard build and the CLI read a resolved date and none of them computes
# the anchor; the anchor comes from asset_model/history_anchor.py's resolver
# (the installed one, else the anchor file, else - under test and CI only - the
# fixed test anchor). REFUSED on an asset that does not declare `synthetic:
# true`, naming the file and the line (criterion 3): a real deployment's
# agreement is only ever the dates it wrote.
#
# A DOCUMENT USING THE TAG IS CACHED PER ANCHOR: its parse is keyed on the
# anchor as well as the text, so one process generating at two anchors never
# answers one anchor's dates for the other.

ANCHOR_TAG = "!anchor"

_OFFSET = re.compile(r"\{([+-]?\d+)\}")


class OffsetRefused(ValueError):
    """An offset date written in the configuration of an asset that is not
    synthetic."""


_parsing = threading.local()


def _anchor_offset(loader, node):
    from datetime import timedelta

    from asset_model import history_anchor

    where = f"{getattr(_parsing, 'name', None) or 'a configuration file'}, line {node.start_mark.line + 1}"
    if not getattr(_parsing, "checking", False):
        if not _asset_is_synthetic(getattr(_parsing, "name", None)):
            raise OffsetRefused(
                f"{where} writes a date as an offset from the history's anchor "
                f"({ANCHOR_TAG}), and this asset does not declare `synthetic: true` - a real "
                f"asset's configuration writes its dates")
    anchor = history_anchor.for_offsets()
    value = str(loader.construct_scalar(node)).strip()
    try:
        return (anchor + timedelta(days=int(value))).isoformat()
    except ValueError:
        pass
    if not _OFFSET.search(value):
        raise ValueError(f"{where}: {ANCHOR_TAG} takes a number of days, e.g. -7, or a "
                         f"string naming one in braces, e.g. \"version {{+0}}\" - not {value!r}")
    return _OFFSET.sub(lambda m: (anchor + timedelta(days=int(m.group(1)))).isoformat(), value)


#: Whether the selected asset is synthetic, by its data-asset.yaml's text.
_SYNTHETIC: "OrderedDict[str, bool]" = OrderedDict()


#: Which asset folder holds a file, by (file, selected folder, asset folders):
#: paths, not configuration, so remembering them answers nothing stale.
_OWNERS: "OrderedDict[tuple, Path | None]" = OrderedDict()


def _owner_data_asset_yaml(name) -> Path | None:
    """The data-asset.yaml of the asset folder holding the file `name`, where
    it lies in one other than the selected asset's (post-build-review #475)."""
    if not name:
        return None
    from asset_model import assets

    selected = assets.selected_or_none()
    if selected is None:
        return None
    every = assets.every()
    key = (str(name), str(selected.folder), tuple(str(a.folder) for a in every))
    if key in _OWNERS:
        return _OWNERS[key]
    path = Path(name).resolve()
    found = None
    if not path.is_relative_to(selected.folder.resolve()):
        found = next((a.data_asset_yaml for a in every
                      if path.is_relative_to(a.folder.resolve())), None)
    with _lock:
        _OWNERS[key] = found
        while len(_OWNERS) > MAX_DOCUMENTS:
            _OWNERS.popitem(last=False)
    return found


def _asset_is_synthetic(name=None) -> bool:
    """asset_time.declared_synthetic(), remembered by data-asset.yaml's text -
    so the answer is part of an offset-using document's cache key and the
    refusal holds on every load (post-build-review #435). The declaration is
    read with `checking` set: data-asset.yaml may itself write offsets, which
    resolve unchecked there, since the check is what is being answered.

    OF THE ASSET WHOSE FILE IS READ (post-build-review #475): a file in
    another asset's folder - a gate acting for a real asset reading every
    asset's hierarchy - is asked of that asset's own declaration."""
    from asset_model import asset_time

    owner = _owner_data_asset_yaml(name)
    path = owner or asset_time.data_asset_yaml()
    text = read(path)
    found = _SYNTHETIC.get(text)
    if found is None:
        before = getattr(_parsing, "checking", False)
        _parsing.checking = True
        try:
            found = ((parse(text, name=str(path)) or {}).get("synthetic") is True if owner
                     else asset_time.declared_synthetic())
        finally:
            _parsing.checking = before
        with _lock:
            _SYNTHETIC[text] = found
            while len(_SYNTHETIC) > MAX_DOCUMENTS:
                _SYNTHETIC.popitem(last=False)
    return found


class _Loader(LOADER):
    """The safe loader, with the one tag a synthetic asset may write."""


_Loader.add_constructor(ANCHOR_TAG, _anchor_offset)
# ON PyYAML'S OWN SAFE LOADERS TOO (PROVISIONAL (2026-11-16)): a reader that
# parses a configuration file itself - a test copying an asset folder, a tool's
# own safe_load - resolves the tag the same way rather than failing on it. The
# one tag is all that is added, so nothing else safe_load accepts changes.
for _safe in {yaml.SafeLoader, getattr(yaml, "CSafeLoader", yaml.SafeLoader)}:
    _safe.add_constructor(ANCHOR_TAG, _anchor_offset)

#: Whether a text uses the tag, remembered by the text itself (a pinned run
#: hands the same string objects a million times, whose hash is cached).
_USES_ANCHOR: "OrderedDict[str, bool]" = OrderedDict()


def uses_anchor(text) -> bool:
    if not isinstance(text, str):
        return False
    found = _USES_ANCHOR.get(text)
    if found is None:
        found = ANCHOR_TAG in text
        with _lock:
            _USES_ANCHOR[text] = found
            while len(_USES_ANCHOR) > MAX_DOCUMENTS:
                _USES_ANCHOR.popitem(last=False)
    return found


def anchored_key(text, name=None):
    """`text` itself, or - where it uses the tag - `text` with the anchor it
    resolves against, so a cached document or a built value is per anchor.
    `name` is the file's, so another asset's file is keyed on that asset's
    declaration (post-build-review #475)."""
    if not uses_anchor(text):
        return text
    from asset_model import history_anchor

    if getattr(_parsing, "checking", False):
        # The synthetic check's own read: never remembered (parse()).
        return f"checking\0{text}"
    if not _asset_is_synthetic(name):
        # Refused when parsed, so nothing is ever kept under this key - and an
        # offset document kept while the asset was synthetic is not answered.
        return f"real\0{text}"
    return f"{history_anchor.for_offsets().isoformat()}\0{text}"


def _parse_raw(text: str):
    """One real parse - separate so a test can count them."""
    return yaml.load(text, Loader=_Loader)  # noqa: S506 - a SafeLoader, C or Python


def _parse_named(text: str, name: str | None):
    """_parse_raw, with the file's name where an offset date's refusal can say
    it."""
    before = getattr(_parsing, "name", None)
    _parsing.name = name
    try:
        return _parse_raw(text)
    finally:
        _parsing.name = before


def parse(source, *, name: str | None = None, remember: bool = True):
    """A YAML document from text or an open stream, parsed at most once per
    distinct content in this process; the caller's own copy.

    `remember=False` parses without keeping the document - for a large file
    read once by a gate (the 6MB register), which the cache would only hold
    and deep-copy for nothing.

    A SLIP NAMES ITS FILE: PyYAML took the name from the stream it read, and
    reading the text first would leave every error saying `<unicode string>`
    (tests/test_cli_config_unreadable.py) - so the stream's name, or the
    path `load()` was given, goes onto the error's marks."""
    if source is None:
        return None
    if name is None and not isinstance(source, str):
        name = getattr(source, "name", None)
    text = source if isinstance(source, str) else source.read()
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    # PER ANCHOR WHERE THE TEXT WRITES AN OFFSET DATE (REQ-GEN-406).
    key = anchored_key(text, name)
    if remember:
        with _lock:
            if key in _cache:
                _cache.move_to_end(key)
                return copy.deepcopy(_cache[key])
    try:
        parsed = _parse_named(text, name)
    except yaml.MarkedYAMLError as exc:
        if name:
            # A C-loader mark's name is read-only, so each is replaced by the
            # pure-Python equivalent carrying the file's name.
            for attr in ("problem_mark", "context_mark"):
                mark = getattr(exc, attr, None)
                if mark is not None:
                    setattr(exc, attr, yaml.Mark(str(name), mark.index, mark.line,
                                                 mark.column, None, None))
        raise
    if not remember:
        return parsed
    if getattr(_parsing, "checking", False) and uses_anchor(text):
        # RESOLVED UNCHECKED, SO NEVER REMEMBERED (post-build-review #435): this
        # parse is the synthetic check's own read of data-asset.yaml, whose
        # offset dates resolve without asking - the check is what is being
        # answered. Remembered, the next load of the file would be answered
        # from it and an asset that is not synthetic would be refused once.
        return parsed
    with _lock:
        _cache[key] = parsed
        _cache.move_to_end(key)
        while len(_cache) > MAX_DOCUMENTS:
            _cache.popitem(last=False)
    return copy.deepcopy(parsed)


def load(path, *, remember: bool = True) -> object:
    """A configuration file, read fresh and parsed at most once per distinct
    content. A missing file raises as reading it would.

    A DEEP COPY ON EVERY CALL, INSIDE A PIN AS OUTSIDE ONE (REQ-PIPE-397
    criterion 10): callers mutate what they load (a fixture editing a document
    before writing it back, a parser popping keys), so a pinned run answering
    the same text a million times still hands each caller its own copy. Do not
    optimise the copy away because the text is pinned - the text is shared, the
    document must not be."""
    return parse(read(path), name=str(path), remember=remember)


# ---- THE PIN (REQ-PIPE-397) --------------------------------------------------
#
# For the span of a synthetic generation or replay, asset_model/config_pin.py
# installs the asset's configuration as read once at the start, and every
# read() below of a file in that snapshot is answered from it - so load(), every
# Built store and every reader built on them answer from it too, and no real
# pipeline module learns that a pin exists (criterion 4). Outside a pin nothing
# here changes: the file is read whole on every call (REQ-PIPE-254 criterion 15).
#
# KEYED ON THE RESOLVED PATH (the architect's non-blocking point): callers mix
# repository-relative spellings with the asset resolver's, and the suite's
# asset folders link to the real files, so two spellings of one file are one
# entry. An absolute spelling's resolution is remembered for the pin's span -
# nothing in the snapshot moves while it is installed.
#
# PROCESS-WIDE, NOT A CONTEXT VARIABLE, as the clock is: a run's four tools read
# from worker threads.


class _Pin:
    """The texts a pin answers, by resolved path."""

    def __init__(self, texts):
        self.texts = texts
        self.spellings: dict[str, str] = {}

    def text_of(self, path):
        spelled = os.fspath(path)
        key = self.spellings.get(spelled)
        if key is None:
            key = os.path.realpath(spelled)
            if os.path.isabs(spelled):
                self.spellings[spelled] = key
        return self.texts.get(key)


_pin: _Pin | None = None


def pin(texts) -> None:
    """Answer every read of a file in `texts` ({resolved path: text}) from it
    until unpin() - asset_model/config_pin.py's alone to call (REQ-PIPE-397)."""
    global _pin
    _pin = _Pin(texts)


def unpin() -> None:
    """Read every file from disk again."""
    global _pin
    _pin = None


def read(path) -> str:
    """A configuration file's text, read now. A missing or unreadable file
    raises as reading it would - on every call, since nothing is remembered
    about a failure.

    INSIDE A PIN (REQ-PIPE-397) a file of the pinned snapshot is answered from
    it, with no read; a file outside the snapshot - or one that could not be
    read when the snapshot was taken (criterion 9) - is read as it always is."""
    held = _pin
    if held is not None:
        text = held.text_of(path)
        if text is not None:
            return text
    return read_from_disk(path)


def read_from_disk(path) -> str:
    """read(), never answered from a pin - what the pin itself is taken with."""
    # THE OPERATING SYSTEM'S OWN READ, then decoded, at about half
    # read_text's cost, on a path that runs tens of thousands of times in one
    # dashboard build (REQ-PIPE-254 criterion 19). Still the whole content,
    # every call (criterion 15). It answers as read_text(encoding="utf-8")
    # does, which is what tests/test_config_yaml.py's TestReadIsReadText
    # holds it to: newlines translated as text mode translates them, and an
    # error raised while reading (a directory opens and then fails to read)
    # names the path, as open()'s would (post-build-review #282).
    fd = os.open(path, os.O_RDONLY)
    try:
        chunks = []
        while True:
            try:
                chunk = os.read(fd, 1 << 16)
            except OSError as exc:
                if exc.filename is not None:
                    raise
                raise type(exc)(exc.errno, exc.strerror, os.fspath(path)) from None
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(fd)
    text = b"".join(chunks).decode("utf-8")
    if "\r" in text:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


#: How many built values a `Built` store keeps for one file (NFR MEMORY): a
#: long-running process that sees a file edited again and again holds only
#: its most recent versions.
VERSIONS_PER_FILE = 4


class Built:
    """Values built from configuration files, keyed on each file's path and
    current text (REQ-PIPE-254).

    `get(key, text, build)` returns the value built from exactly `text`,
    calling `build()` only when this key has no value for that text - which
    may be any hashable statement of the content a value is built from, as
    arrival_patterns' declared patterns are. The
    caller reads the text ONCE and builds from that one read, so a value can
    never combine two versions of a file (criterion 6), and two threads
    reading during a replacement each get a value built wholly from the
    version they read (criterion 8).

    THE SAME PATTERN AS THE DOCUMENT CACHE ABOVE: the store behind one lock,
    building outside it, so two threads may both build the first value and
    the second write is the same value. A build that raises stores nothing,
    so a corrected file is read on the next call (criterion 9).

    A STORED VALUE IS SHARED between callers, so what a store holds must be
    immutable - frozen records, tuples, MappingProxyType (criterion 7). A
    module whose value is a plain document returns `load()`'s own copy
    instead of using a store.
    """

    def __init__(self, *, versions: int = VERSIONS_PER_FILE, files: int = MAX_DOCUMENTS):
        self._versions = versions
        self._files = files
        self._store: "OrderedDict[object, OrderedDict[object, object]]" = OrderedDict()
        # The version each key was last answered for, as one (text, value)
        # pair: the common case - a file unchanged since the last call - is an
        # equality test of the text just read against it, with no hash of the
        # text and no lock (REQ-PIPE-254 criterion 19). The pair is replaced
        # whole, never edited, so a reader sees one version or the other.
        self._newest: dict[object, tuple[object, object]] = {}
        self._lock = threading.Lock()

    def get(self, key, text, build):
        # A VALUE BUILT FROM A FILE WRITING OFFSET DATES IS PER ANCHOR
        # (REQ-GEN-406): the text is keyed with the anchor it resolves against.
        text = anchored_key(text)
        newest = self._newest.get(key)
        if newest is not None and newest[0] == text:
            return newest[1]
        with self._lock:
            held = self._store.get(key)
            if held is not None and text in held:
                held.move_to_end(text)
                self._store.move_to_end(key)
                self._newest[key] = (text, held[text])
                return held[text]
        value = build()
        with self._lock:
            held = self._store.setdefault(key, OrderedDict())
            self._store.move_to_end(key)
            held[text] = value
            held.move_to_end(text)
            self._newest[key] = (text, value)
            while len(held) > self._versions:
                held.popitem(last=False)
            while len(self._store) > self._files:
                gone, _ = self._store.popitem(last=False)
                self._newest.pop(gone, None)
        return value

    def from_file(self, path, build):
        """The value built from `path` as it reads now: `build(text)` is
        called with the one read this call made, only when it is new."""
        text = read(path)
        return self.get(str(path), text, lambda: build(text))


def clear() -> None:
    """Forget every parsed document - for a test that wants to count parses."""
    with _lock:
        _cache.clear()
