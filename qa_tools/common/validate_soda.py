"""The configuration-time gate over this project's SodaCL files (the
road-testing sweep's #7, Keith 2026-10-06).

TWO KINDS OF CHECK ARE REFUSED HERE, before any run:
- one Soda Core cannot parse - it logs an error and runs the rest, and the
  check never reports;
- one that needs Soda Cloud to evaluate - change-over-time and anomaly
  checks. They PARSE cleanly, so only knowing the kind catches them; at run
  time Soda Core logs that it must connect to Soda Cloud, leaves the check
  out of its results, and the run carries on (verified 2026-09-24 against
  soda-core 3.5.6; REQ-QAC-108's decisions carry the experiment).

A THIRD, REQ-PIPE-341 criterion 5: a `failed rows` check whose fail query
does not select every column of its table's failing-sample key (the
collection adapter's `sample_key`). With a several-column key such a query
records nothing - post-build-review #291's shape, Linkage Keys' referential
samples recorded empty - so it is refused here, naming the check and the
missing columns. A `fail condition` selects the whole row; a check whose
failure judges the whole table and names no row declares `names_no_row: true`
and is not held to the key. A failed-rows check on a table that declares no
key is WARNED of, never silently skipped (decisions 2026-11-01).

The run-time half is soda_common.unreported_checks(): whatever this gate
cannot foresee still comes out red, "could not be evaluated", never absent.
Retired check files are not run, so they are not checked.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Check kinds Soda Core cannot evaluate without Soda Cloud.
_CLOUD_ONLY = ("change ", "anomaly score", "anomaly detection")


def check_files() -> list[str]:
    """Every collection's live Soda checks file, found by convention through
    the registry (REQ-QAC-241) - a glob of contract/ itself found none once
    they moved under contract/<agency-id>/ (post-build-review #273)."""
    from qa_tools.common import soda_common

    return sorted(soda_common.soda_check_files())


def declared_sample_keys() -> dict[tuple[str, str], list[str]]:
    """Every table's failing-sample key, by (collection, table) - two
    collections may name a table alike, and each file is held to its own
    collection's key, never another's."""
    from qa_tools import collections

    return {(c.id, table): cols for c in collections.all_collections()
            for table, cols in collections.adapter(c).sample_key.items()}


def _collection_of_files() -> dict[str, str]:
    """Each registered collection's live Soda file, by path, to its id."""
    from qa_tools import collections

    return {_resolved(c.check_file("soda")): c.id for c in collections.all_collections()}


def _resolved(path) -> str:
    path = str(path)
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(ROOT, path))


def _keys_for(path, keys: dict, collection_of: dict) -> dict[str, list[str]]:
    """The {table: key} one file is held to: its own collection's, or - for a
    map keyed by bare table name, as a caller may pass for one file - that."""
    if not any(isinstance(k, tuple) for k in keys):
        return keys
    cid = collection_of.get(str(path)) or collection_of.get(_resolved(path))
    return {table: cols for (c, table), cols in keys.items() if c == cid}


def _selected(query: str) -> set[str] | None:
    """The output column names of a fail query's outermost SELECT, or None
    where it selects `*` (every column). Unparseable SQL is Soda's to refuse."""
    import sqlglot
    from sqlglot import exp

    tree = sqlglot.parse_one(query, read="postgres")
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    names: set[str] = set()
    for e in select.expressions:
        if isinstance(e, exp.Star) or (isinstance(e, exp.Column) and isinstance(e.this, exp.Star)):
            return None
        names.add(e.alias_or_name)
    return names


def _failed_rows_checks(doc: dict):
    """(table, check name, fail query or None, names_no_row) for every
    `failed rows` check in one parsed checks file."""
    from qa_tools.common import sample_keys

    for key, checks in doc.items():
        if not (isinstance(key, str) and key.startswith("checks for ")):
            continue
        table = key.removeprefix("checks for ").split("[")[0].strip()
        for item in checks or ():
            if not isinstance(item, dict) or "failed rows" not in item:
                continue
            spec = item["failed rows"] or {}
            attrs = spec.get("attributes") or {}
            yield (table, spec.get("name") or attrs.get("check_id"), spec.get("fail query"),
                   sample_keys.names_no_row(attrs.get("names_no_row")))


def _key_findings(paths, keys, collection_of=None) -> tuple[list[str], list[str]]:
    import yaml

    found, warned = [], []
    collection_of = _collection_of_files() if collection_of is None else collection_of
    for path in paths:
        name = os.path.basename(str(path))
        file_keys = _keys_for(path, keys, collection_of)
        with open(path) as f:
            doc = yaml.safe_load(f) or {}
        for table, check, query, no_row in _failed_rows_checks(doc):
            if no_row:
                continue
            key = file_keys.get(table)
            if not key:
                warned.append(f"{name}: failed-rows check {check!r} is on table {table!r}, "
                              f"which declares no failing-sample key, so its samples cannot be "
                              f"checked (REQ-PIPE-341)")
                continue
            if query is None:
                continue
            selected = _selected(query)
            missing = [c for c in key if selected is not None and c not in selected]
            if missing:
                found.append(f"{name}: failed-rows check {check!r} on {table!r} does not select "
                             f"its sample key - missing {', '.join(missing)} (key: "
                             f"{', '.join(key)}); select them, or declare names_no_row: true if "
                             f"its failure names no row (REQ-PIPE-341 criterion 5)")
    return found, warned


def warnings(paths=None, sample_keys=None, collection_of=None) -> list[str]:
    """What the gate warns of without failing: a failed-rows check on a table
    with no declared key."""
    keys = declared_sample_keys() if sample_keys is None else sample_keys
    return _key_findings(paths or check_files(), keys, collection_of)[1]


def problems(paths=None, sample_keys=None, collection_of=None) -> list[str]:
    import yaml
    from soda.scan import Scan

    found: list[str] = []
    for path in paths or check_files():
        name = os.path.basename(str(path))
        scan = Scan()
        scan.set_data_source_name("config-check")
        scan.add_sodacl_yaml_file(str(path))
        for log in scan.get_error_logs():
            found.append(f"{name}: Soda Core cannot parse it - {' '.join(str(log.message).split())}")
        with open(path) as f:
            doc = yaml.safe_load(f) or {}
        for key, checks in doc.items():
            if not (isinstance(key, str) and key.startswith("checks for ")):
                continue
            for item in checks or ():
                line = next(iter(item)) if isinstance(item, dict) else str(item)
                if line.strip().lower().startswith(_CLOUD_ONLY):
                    found.append(f"{name}: '{line}' needs Soda Cloud to evaluate, which this "
                                 f"project does not use - compute it ourselves, as the volume "
                                 f"check does (REQ-QAC-108)")
    keys = declared_sample_keys() if sample_keys is None else sample_keys
    found += _key_findings(paths or check_files(), keys, collection_of)[0]
    return found


def main() -> int:
    for line in warnings():
        print(f"WARNING: {line}")
    found = problems()
    for line in found:
        print(f"ERROR: {line}")
    if found:
        return 1
    print(f"Soda check files OK - {len(check_files())} file(s), every check runnable here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
