"""
File-arrival pattern matching for the AWS event-driven MVP (plans/running-
thoughts.md #5 Thread B / docs/aws-event-driven-mvp-design.md): given a raw
S3 object key, decide which dataset/table it is and how to get at its data,
covering the three real arrival shapes Keith flagged when this was first
scoped - a single file, one of several files landing under a shared
folder, or a zip archive that needs extracting first.

Pure logic, no AWS import at all - deliberately, so it's testable with
zero mocking. Proposed as a real `arrivalPattern` ODCS contract
`customProperties` extension (see the design doc's own top-of-file flagged
decision for why it isn't wired into the real production contract YAML
files yet) - this module takes a plain list of pattern-spec dicts shaped
exactly like that proposed YAML, from wherever the caller gets them (today,
a hardcoded list in each Lambda handler module).
"""
from __future__ import annotations
import re
import zipfile
from dataclasses import dataclass, field


class ArrivalPatternError(Exception):
    """Raised for a malformed pattern spec (unknown type, missing
    keyPattern) - a config bug, not a "no match" outcome."""


@dataclass
class ArrivalMatch:
    dataset_id: str
    pattern_type: str
    groups: dict[str, str] = field(default_factory=dict)
    # nested_folder only - which table/file role this specific key matched.
    table: str | None = None
    # zip_archive only - {member filename inside the zip: table name}.
    extract_map: dict[str, str] | None = None


_GROUP_RE = re.compile(r"\{(\w+)\}")


def _pattern_to_regex(key_pattern: str) -> re.Pattern:
    """Turns a keyPattern like "raw/bdm/birth_registrations_{date}.csv"
    into a real compiled regex with named capture groups - {date}/{run_id}/
    {table} become (?P<date>...) etc, anything else is matched literally
    (re.escape'd first, so a literal "." in a real key pattern doesn't
    accidentally become a regex wildcard)."""
    parts = []
    pos = 0
    for m in _GROUP_RE.finditer(key_pattern):
        parts.append(re.escape(key_pattern[pos:m.start()]))
        parts.append(f"(?P<{m.group(1)}>[^/]+)")
        pos = m.end()
    parts.append(re.escape(key_pattern[pos:]))
    return re.compile("^" + "".join(parts) + "$")


def match_arrival(key: str, patterns: list[dict]) -> ArrivalMatch | None:
    """Tries each pattern in order, returns the first match or None if
    nothing matches - an unmatched key is a real, expected occurrence (a
    stray file, a different team's object in a shared bucket), never
    raised as an error. A malformed PATTERN (not a malformed key) still
    raises ArrivalPatternError - that's a config bug worth failing loudly
    on, unlike a key that simply doesn't match anything."""
    for pattern in patterns:
        pattern_type = pattern.get("type")
        key_pattern = pattern.get("keyPattern")
        if not key_pattern or pattern_type not in ("single_file", "nested_folder", "zip_archive"):
            raise ArrivalPatternError(f"malformed arrival pattern (needs type + keyPattern): {pattern!r}")

        regex = _pattern_to_regex(key_pattern)
        found = regex.match(key)
        if not found:
            continue

        groups = found.groupdict()
        if pattern_type == "single_file":
            return ArrivalMatch(dataset_id=pattern["dataset_id"], pattern_type=pattern_type, groups=groups)
        if pattern_type == "nested_folder":
            return ArrivalMatch(dataset_id=pattern["dataset_id"], pattern_type=pattern_type, groups=groups,
                                 table=pattern.get("extractTo"))
        # zip_archive
        return ArrivalMatch(dataset_id=pattern["dataset_id"], pattern_type=pattern_type, groups=groups,
                             extract_map=dict(pattern.get("extractTo") or {}))

    return None


def extract_zip_members(zip_path: str, extract_map: dict[str, str], dest_dir: str) -> dict[str, str]:
    """zip_archive support: extracts each member named in extract_map (the
    proposed arrivalPattern's own {filename-inside-zip: table} shape) into
    dest_dir, returns {table: extracted file path}. Written but not
    exercised by either real dataset today (neither BDM nor CP actually
    arrives zipped) - see the design doc's own note on why this exists
    anyway, covered by a real fixture zip in tests/test_file_arrival.py
    rather than a real production path."""
    extracted = {}
    with zipfile.ZipFile(zip_path) as zf:
        for member, table in extract_map.items():
            dest_path = zf.extract(member, dest_dir)
            extracted[table] = dest_path
    return extracted
