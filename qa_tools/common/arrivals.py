"""Arrivals built from the DELIVERY RECORDS in the database rather than the
tree (REQ-PIPE-152 criterion 6) - the half of arrival recognition that reads
qa.delivery and qa.delivery_file, and an S3 object a handler recorded with no
directory anywhere.

TREE RECOGNITION IS asset_model/arrivals.py (REQ-PIPE-380 criterion 2, QB
SETTLED by Keith 2026-11-14): recognising a delivery on disk, the arrivals
it makes and what could not be placed read configuration and the delivery
tree, which the generator checks its placements against. This half stays in
the real pipeline because it opens the database, which asset_model/ never
does.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from asset_model import asset_time, delivery, hierarchy
from asset_model.arrivals import Arrival


def arrivals_from_records(collection_id: str, deliveries_dir: Path | None = None,
                          conn=None) -> list[Arrival]:
    """Every arrival for one collection, built from the DELIVERY RECORDS
    rather than the tree, OLDEST FIRST (REQ-PIPE-152 criterion 6; Keith,
    2026-10-06: the pass builds every arrival from the database).

    THE SAME ARRIVALS arrivals_for() recognises from disk, by construction:
    one per dataset per delivery, its receipt the earliest of that dataset's
    files, the run id the staged table's spelling, the same order, the same
    renumbering - pinned against arrivals_for() over the whole deployment by
    tests/test_arrivals_from_records.py. What it adds is that an object a
    handler recorded straight from S3, with no directory anywhere, is an
    arrival like any other.

    A LOCAL DELIVERY WHOSE DIRECTORY IS GONE IS NOT AN ARRIVAL. Its files are
    named relative to the deliveries tree, so a record the tree no longer
    holds - a test's, or one deleted by hand - would be an arrival whose
    files cannot be read. That is the orphan the tree once left in qa.run
    (CLAUDE.md, 2026-09-28); here it is simply not offered. An S3 delivery
    has no directory and is always offered.
    """
    from datetime import datetime as _dt

    from qa_tools.common import delivery_log, qa_store, s3_arrival

    hierarchy.datasets_in_collection(collection_id)  # raises if unknown
    root = Path(deliveries_dir or delivery.default_deliveries_dir())
    with delivery_log._db(conn) as db:
        rows = db.execute(
            f'SELECT d.name, d.anomalies, f.filename, f.dataset_id, f.contested_by, '
            f'f.received_at, f.receipt_sequence, f.storage_uri '
            f'FROM "{qa_store.SCHEMA}".delivery d '
            f'JOIN "{qa_store.SCHEMA}".delivery_file f ON f.delivery = d.name '
            f"ORDER BY d.name, f.filename").fetchall()
    by_delivery: dict[str, list] = {}
    anomalies: dict[str, tuple[str, ...]] = {}
    for name, anomaly, *rest in rows:
        by_delivery.setdefault(name, []).append(rest)
        anomalies[name] = tuple(anomaly or ())
    out: list[Arrival] = []
    for name, files in by_delivery.items():
        uris = {filename: uri for filename, _, _, _, _, uri in files}
        remote = any((uri or "").startswith(s3_arrival.S3_SCHEME) for uri in uris.values())
        if not remote and not (root / name).is_dir():
            continue
        unmatched = tuple(sorted(f for f, ds, contested, *_ in files
                                 if ds is None and not contested))
        datasets: dict[str, list] = {}
        for filename, dataset_id, _, received_at, sequence, _ in files:
            if dataset_id and hierarchy.dataset(dataset_id).collection_id == collection_id:
                datasets.setdefault(dataset_id, []).append(
                    (filename, _dt.fromisoformat(received_at), int(sequence)))
        for dataset_id in sorted(datasets):
            entries = datasets[dataset_id]
            names = tuple(sorted(f for f, _, _ in entries))
            received_at, sequence = min((at, seq) for _, at, seq in entries)
            table = hierarchy.dataset(dataset_id).table
            out.append(Arrival(
                run_id=f"{table}__{asset_time.arrival_key(received_at)}",
                run_index=len(out) + 1, collection_id=collection_id,
                delivery_name=name, path=root / name,
                received_at=received_at, sequence=sequence,
                files_by_dataset={dataset_id: names}, unmatched=unmatched,
                anomalies=anomalies[name],
                sources=tuple((f, uris[f]) for f in names if remote)))
    out.sort(key=lambda a: (a.received_at, a.sequence, a.run_id))
    return [dataclasses.replace(a, run_index=i) for i, a in enumerate(out, start=1)]
