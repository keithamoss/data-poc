"""A check's definition fingerprint - the ONE writer (REQ-QAC-176).

What every recorded check result carries (qa.check_result.definition_fingerprint)
and what the changelog gate compares (CheckMetadata.config_hash): the same
function, never a second gate-only or store-only hash. A fix to a check moves
its fingerprint, so the bulk re-check (REQ-PIPE-177) can say exactly which
supplies were judged under an old definition, with no date anyone typed.

THE STEPS, for a check's settings as its tool's parser hands them over
(check_lifecycle - the settings each parser hashes, REQ-QAC-223's widened
scope with its project dbt SQL):

  1. NORMALISE (criterion 7): a date becomes its ISO string, the rule
     check_lifecycle._as_written applies to Evidently's files, for every
     tool; any value of a type this does not know - an unquoted timestamp
     included - is REFUSED, naming the check and the setting's path, rather
     than coerced as json.dumps(default=str) used to.
  2. DROP FROZEN DEFAULTS (criteria 8 to 10): a setting equal to its frozen
     default (frozen_defaults.FROZEN_DEFAULTS), by type and value, is left
     out - recursing into maps only, comparing lists whole, and dropping a
     map the dropping leaves empty. Null equals a default only where the
     table says null.
  3. SERIALISE as RFC 8785 canonical JSON (criterion 20), and
  4. WRITE 'v1:' and the full 64-hex SHA-256 (criterion 21).

EVERY SCHEME IS KEPT (criterion 12). A stored fingerprint names its scheme,
and is compared with the check's current settings fingerprinted under THAT
scheme (`fingerprint_under`), so a new scheme alone moves nothing. A scheme
is kept while any recorded result carries it; there is one today.

LOCATION-INDEPENDENT (NFR): nothing here sees a file path - a dbt definition
is labelled by file name inside its text, and REQ-QAC-241's moves kept every
hash, which the golden test (tests/test_check_fingerprint.py) keeps true.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
from typing import Any, Iterable, Mapping

import rfc8785

#: The scheme every new fingerprint is written under.
CURRENT_SCHEME = "v1"

#: Every scheme a stored fingerprint may carry, oldest first.
SCHEMES = ("v1",)


class UnhashableSetting(ValueError):
    """A check's settings hold a value of a type the writer does not know
    (criterion 7) - refused, never coerced."""


class UnknownScheme(ValueError):
    """A stored fingerprint names a scheme this checkout does not keep."""


class NoFingerprint(LookupError):
    """A result was offered for a check id the fingerprints map does not
    hold (criterion 14)."""


def normalise(value: Any, *, check_id: str = "?", path: tuple = ()) -> Any:
    """`value` with every date as its ISO string; raises UnhashableSetting
    for anything that is not a map with string keys, a list, a string, an
    integer, a float, a boolean, null or a plain date."""
    where = ".".join(str(p) for p in path) or "(top)"
    if isinstance(value, _dt.datetime):
        raise UnhashableSetting(
            f"{check_id}: setting {where} is the timestamp {value!r}, which cannot be "
            "hashed as written - quote it (REQ-QAC-176 criterion 7)")
    if isinstance(value, _dt.date):
        return value.isoformat()
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise UnhashableSetting(f"{check_id}: setting {where} is {value!r}, which has "
                                    "no JSON form (REQ-QAC-176 criterion 7)")
        return value
    if isinstance(value, Mapping):
        out = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise UnhashableSetting(
                    f"{check_id}: setting {where} has the key {k!r}, which is not a string "
                    "(REQ-QAC-176 criterion 7)")
            out[k] = normalise(v, check_id=check_id, path=(*path, k))
        return out
    if isinstance(value, (list, tuple)):
        return [normalise(v, check_id=check_id, path=(*path, i)) for i, v in enumerate(value)]
    raise UnhashableSetting(
        f"{check_id}: setting {where} is a {type(value).__name__} ({value!r}), a type the "
        "fingerprint does not know - refused rather than coerced (REQ-QAC-176 criterion 7)")


def same(a: Any, b: Any) -> bool:
    """Equal by type AND value, all the way down: True is not 1, 1 is not 1.0."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def defaults_for(tool: str, kind: str | None, scheme: str,
                 table: Iterable[Mapping] | None = None) -> dict[tuple, Any]:
    """{setting path: frozen value} for one tool and check kind under
    `scheme` - every entry introduced at or before it, a later entry for the
    same path replacing an earlier one (criterion 10)."""
    from qa_tools.common import frozen_defaults

    rank = {s: i for i, s in enumerate(SCHEMES)}
    if scheme not in rank:
        raise UnknownScheme(f"fingerprint scheme {scheme!r} is not one this checkout keeps "
                            f"({', '.join(SCHEMES)})")
    out: dict[tuple, Any] = {}
    for entry in frozen_defaults.FROZEN_DEFAULTS if table is None else table:
        if entry["tool"] != tool or rank.get(entry["scheme"], len(SCHEMES)) > rank[scheme]:
            continue
        if entry.get("kind") is not None and entry["kind"] != kind:
            continue
        out[tuple(entry["path"])] = entry["value"]
    return out


def drop_defaults(settings: dict, defaults: Mapping[tuple, Any], path: tuple = ()) -> dict:
    """`settings` less every setting equal to its frozen default (criterion
    9): into maps only, lists compared whole, a map left empty by the
    dropping dropped too."""
    out = {}
    for key, value in settings.items():
        here = (*path, key)
        if here in defaults and same(value, defaults[here]):
            continue
        if isinstance(value, dict) and value:
            kept = drop_defaults(value, defaults, here)
            if not kept:
                continue
            value = kept
        out[key] = value
    return out


def canonical(settings: Mapping) -> bytes:
    """RFC 8785 canonical JSON (criterion 20)."""
    return rfc8785.dumps(settings)


def fingerprint_under(scheme: str, tool: str, kind: str | None, settings: Mapping, *,
                      check_id: str = "?", table: Iterable[Mapping] | None = None) -> str:
    """The fingerprint of `settings` under `scheme` - '<scheme>:' and the
    64-hex SHA-256 of the canonical JSON of the settings, normalised and
    less their frozen defaults."""
    if scheme != "v1":
        raise UnknownScheme(f"fingerprint scheme {scheme!r} is not one this checkout keeps "
                            f"({', '.join(SCHEMES)})")
    normal = normalise(dict(settings), check_id=check_id)
    kept = drop_defaults(normal, defaults_for(tool, kind, scheme, table))
    return f"{scheme}:{hashlib.sha256(canonical(kept)).hexdigest()}"


def fingerprint(tool: str, kind: str | None, settings: Mapping, *, check_id: str = "?",
                table: Iterable[Mapping] | None = None) -> str:
    """The fingerprint written today (CURRENT_SCHEME)."""
    return fingerprint_under(CURRENT_SCHEME, tool, kind, settings, check_id=check_id,
                             table=table)


def scheme_of(stored: str) -> str:
    scheme, sep, digest = (stored or "").partition(":")
    if not sep or len(digest) != 64:
        raise UnknownScheme(f"{stored!r} is not a stored definition fingerprint")
    return scheme


def differs(stored: str, check) -> bool:
    """Whether a stored fingerprint differs from `check`'s current
    definition, fingerprinted under the stored one's own scheme (criterion
    12). `check` is a CheckMetadata, whose hashed_settings are kept outside
    the hash for exactly this."""
    return stored != fingerprint_under(scheme_of(stored), check.tool, check.check_kind,
                                       check.hashed_settings, check_id=check.check_id)


def current_by_scheme(checks: Iterable) -> dict[str, dict[str, str]]:
    """{scheme: {check id: fingerprint}} for every kept scheme - what a
    selection compares a stored fingerprint against, whatever scheme it
    carries."""
    checks = list(checks)
    return {s: {c.check_id: fingerprint_under(s, c.tool, c.check_kind, c.hashed_settings,
                                              check_id=c.check_id) for c in checks}
            for s in SCHEMES}


def stamp(fingerprints: Mapping[str, str], check_id: str | None, *, run_key: str) -> str:
    """The fingerprint to record with a result about `check_id`, or
    NoFingerprint (criterion 14)."""
    found = fingerprints.get(check_id) if check_id else None
    if not found:
        raise NoFingerprint(
            f"run {run_key!r}: no definition fingerprint for check {check_id!r} - refusing to "
            "record a result whose check definition cannot be named (REQ-QAC-176 criterion 14)")
    return found
