"""Configuration YAML, parsed once per process while its content is unchanged
(REQ-PIPE-156, signed by Keith 2026-10-06).

WHY. A profile of a real 12-arrival Child Protection replay found 5,911
`yaml.safe_load` calls - about half the bootstrap - re-reading files that do
not change during a run: the ODCS contract on every slot lookup, the asset
file on every connection, the environments file, the check metadata. Content
-memoised, the same replay took 95s instead of 178s
(plans/running-thoughts.md #65).

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
"""
from __future__ import annotations

import copy
import threading
from collections import OrderedDict
from pathlib import Path

import yaml

#: The loader every parse uses - the C one when PyYAML was built with libyaml.
LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

#: How many distinct documents are kept. contract/ is ~220KB of YAML in 13
#: files; a run reads a few dozen distinct documents, small strings included.
MAX_DOCUMENTS = 256

_cache: "OrderedDict[str, object]" = OrderedDict()
_lock = threading.Lock()


def _parse_raw(text: str):
    """One real parse - separate so a test can count them."""
    return yaml.load(text, Loader=LOADER)  # noqa: S506 - a SafeLoader, C or Python


def parse(source, *, name: str | None = None):
    """A YAML document from text or an open stream, parsed at most once per
    distinct content in this process; the caller's own copy.

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
    with _lock:
        if text in _cache:
            _cache.move_to_end(text)
            return copy.deepcopy(_cache[text])
    try:
        parsed = _parse_raw(text)
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
    with _lock:
        _cache[text] = parsed
        _cache.move_to_end(text)
        while len(_cache) > MAX_DOCUMENTS:
            _cache.popitem(last=False)
    return copy.deepcopy(parsed)


def load(path) -> object:
    """A configuration file, read fresh and parsed at most once per distinct
    content. A missing file raises as reading it would."""
    return parse(Path(path).read_text(encoding="utf-8"), name=str(path))


def clear() -> None:
    """Forget every parsed document - for a test that wants to count parses."""
    with _lock:
        _cache.clear()
