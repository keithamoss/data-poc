"""Move the committed qa_results/ tree into the database, once.

WHY THIS EXISTS AND WHY IT IS THROWAWAY. `qa_results/` held every check
this pipeline ever ran, as committed JSON, and that made the repository
hold STATE as well as configuration - which Keith settled against on
2026-09-27: "the repository only contains configuration, not actual
state, no state at all." REQ-PIPE-089 moves it into `qa.check_result` and
its siblings. This module is the one-way door between the two.

IT IS NOT A DUAL-WRITE AND MUST NEVER BECOME ONE. Two sources of the same
truth is the failure REQ-PIPE-089 criterion 11 forbids by name: they
drift, and nothing says which wins. The tree is read once and deleted in
the same change.

ANYTHING IT CANNOT MIGRATE IS A LOUD FAILURE, not a skip. A silent skip
here loses history permanently - the whole point of the tree was that it
was durable - so an unreadable file, an unrecognised scope or a record
without a check_id stops the migration with the path in the message.

THE TREE'S OWN SHAPE, which this has to know because the path carries
facts the file does not:

  <agency>/<collection>/<dataset>/<run>/<tool>.json   a dataset's own
                                                      verified records
  <agency>/<collection>/_cross-table/<run>/<tool>.json  records spanning
                                                      datasets (REQ-QAC-037)
  <agency>/<collection>/_raw/<run>/<tool>.json        the one unmodified
                                                      raw_output per tool,
                                                      plus the dataset_stats
                                                      and tables_read
                                                      pseudo-tools

`tool` and `scope` and `dataset_id` come from the PATH; a verified record
carries neither tool nor scope, which is exactly why reading the tree
needed a convention in the first place.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qa_tools.common import qa_store, supply_db

#: Reserved scope directories - a leading underscore is already refused
#: for any real agency, collection or dataset id, which is what makes
#: these unambiguous rather than a name clash waiting to happen.
CROSS_TABLE_DIR = "_cross-table"
RAW_DIR = "_raw"

#: Pseudo-tools: they describe a RUN rather than a dataset, and they live
#: under _raw for that reason. dataset_stats becomes qa.dataset_stats;
#: tables_read rides inside it, because it is read whole for audit and
#: normalising it would buy a migration and no query.
DATASET_STATS_TOOL = "dataset_stats"
TABLES_READ_TOOL = "tables_read"


class MigrationError(RuntimeError):
    """Raised where continuing would lose history."""


def migrate_tree(conn: supply_db.SupplyConnection, tree: Path, *,
                 environment: str) -> dict[str, int]:
    """Read a whole qa_results/ tree into the database. Returns counts.

    Ordered deliberately: every RUN is registered before any result
    references it, because qa.check_result has a real foreign key and a
    result arriving first would fail on it - which is the FK doing its
    job rather than an inconvenience.
    """
    if not tree.is_dir():
        raise MigrationError(f"no qa_results tree at {tree}")

    qa_store.ensure_schema(conn)
    counts = {"runs": 0, "results": 0, "raw": 0, "stats": 0}

    # Pass one: every run, from wherever it is mentioned. A run appears in
    # several scopes, so this is a set rather than a walk order.
    runs: dict[tuple[str, str, str], dict[str, Any]] = {}
    for path in sorted(tree.rglob("*.json")):
        agency, collection, scope_dir, run_id, tool = _parse(path, tree)
        doc = _load(path)
        key = (agency, collection, run_id)
        entry = runs.setdefault(key, {"run_timestamp": None, "run_by": None})
        entry["run_timestamp"] = entry["run_timestamp"] or doc.get("run_timestamp")
        entry["run_by"] = entry["run_by"] or doc.get("run_by")

    for (agency, collection, run_id), entry in sorted(runs.items()):
        if not entry["run_timestamp"]:
            raise MigrationError(
                f"run {run_id} ({agency}/{collection}) has no run_timestamp in any "
                f"of its files - refusing to invent one")
        qa_store.record_run(
            conn, run_key=run_id, agency_id=agency, collection_id=collection,
            run_timestamp=entry["run_timestamp"],
            # A run written before run_by existed genuinely has none, and
            # saying so is better than attributing it to somebody.
            run_by=entry["run_by"] or "unrecorded",
            environment=environment)
        counts["runs"] += 1

    # Pass two: the contents.
    for path in sorted(tree.rglob("*.json")):
        agency, collection, scope_dir, run_id, tool = _parse(path, tree)
        doc = _load(path)

        if scope_dir == RAW_DIR:
            if tool == DATASET_STATS_TOOL:
                counts["stats"] += _migrate_stats(conn, run_id, doc)
                continue
            if tool == TABLES_READ_TOOL:
                # Rides in the stats document rather than earning a table.
                qa_store.record_tool_output(conn, run_id, TABLES_READ_TOOL,
                                            doc.get("raw_output"))
                counts["raw"] += 1
                continue
            qa_store.record_tool_output(conn, run_id, tool, doc.get("raw_output"))
            counts["raw"] += 1
            continue

        scope = "cross_table" if scope_dir == CROSS_TABLE_DIR else "dataset"
        dataset_id = None if scope == "cross_table" else scope_dir
        records = doc.get("verified") or []
        for record in records:
            if not record.get("check_id"):
                raise MigrationError(f"{path}: a verified record has no check_id")
        counts["results"] += _append_results(conn, run_id, tool, scope, dataset_id, records)

    return counts


def _append_results(conn, run_id: str, tool: str, scope: str,
                    dataset_id: str | None, records: list[dict]) -> int:
    """Insert one file's records.

    APPENDS rather than replacing, unlike qa_store.record_results(), and
    the difference matters here: one run's dataset scope is spread across
    several FILES (one per tool), so replacing per call would leave only
    the last tool's results. The scope is cleared once, by the caller of
    the whole migration, not per file.
    """
    prepared = []
    for record in records:
        row = dict(record)
        row["tool"] = tool
        row["scope"] = scope
        if dataset_id is not None:
            row.setdefault("dataset_id", dataset_id)
        prepared.append(row)
    return _insert(conn, run_id, prepared)


def _insert(conn, run_key: str, records: list[dict]) -> int:
    columns = qa_store._RESULT_COLUMNS
    placeholders = ", ".join(["?"] * (len(columns) + 2))
    for record in records:
        extra = {k: v for k, v in record.items()
                 if k not in columns and k not in ("run_id", "run_timestamp")}
        conn.execute(
            f'INSERT INTO "{qa_store.SCHEMA}".check_result '
            f'(run_key, {", ".join(columns)}, extra) VALUES ({placeholders})',
            [run_key, *[record.get(c) for c in columns], json.dumps(extra, default=str)])
    return len(records)


def _migrate_stats(conn, run_id: str, doc: dict) -> int:
    """dataset_stats holds one payload per dataset for the run."""
    payload = doc.get("raw_output") or {}
    written = 0
    if isinstance(payload, dict) and payload:
        for dataset_id, stats in payload.items():
            if not isinstance(stats, dict):
                continue
            qa_store.record_dataset_stats(conn, run_id, dataset_id, stats)
            written += 1
    if not written:
        # Still record it, keyed to the run, rather than dropping a
        # payload whose shape this does not recognise.
        qa_store.record_tool_output(conn, run_id, DATASET_STATS_TOOL, payload)
    return written


def _parse(path: Path, tree: Path) -> tuple[str, str, str, str, str]:
    rel = path.relative_to(tree).parts
    if len(rel) != 5:
        raise MigrationError(
            f"{path} is {len(rel)} levels deep under {tree}, expected 5 "
            f"(<agency>/<collection>/<scope>/<run>/<tool>.json)")
    agency, collection, scope_dir, run_id, filename = rel
    return agency, collection, scope_dir, run_id, Path(filename).stem


def _load(path: Path) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(f"{path}: {type(exc).__name__}: {exc}") from exc
