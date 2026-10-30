"""Run inside a copy built by tests/thirty_linked_datasets.py (REQ-TEST-339):
generate the six fake collections, then replay them as ONE receipt-ordered
stream through cli.pipeline._run_stream - the function `mothman pipeline run`
calls for collections sharing a calendar - against the database
MOTHMAN_SUPPLY_DSN names.

THE ONE THING ADDED is a stopwatch: orchestrate.run_one, which the stream's
per-arrival steps look up at call time, is wrapped to record how long each
QA run took (criterion 4). The run itself is unchanged. The timings are
written to the path given as the only argument.

Invoked as `python tests/thirty_linked_run.py <out.json>` with the copy as
the working directory, so every import resolves to the copy's own files.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))


def main(out: str) -> None:
    from cli import pipeline
    from qa_tools import collections
    from qa_tools.tools import orchestrate

    import thirty_linked_datasets as fixture

    timings: list[dict] = []
    real = orchestrate.run_one

    def timed(collection_id, entry, *args, **kwargs):
        start = time.perf_counter()
        try:
            return real(collection_id, entry, *args, **kwargs)
        finally:
            timings.append({"collection": collection_id, "run_id": entry["run_id"],
                            "seconds": round(time.perf_counter() - start, 2)})

    orchestrate.run_one = timed
    ids = [c["id"] for c in fixture.sources()] + [fixture.PRODUCT["collection"]]
    start = time.perf_counter()
    try:
        pipeline._run_stream([collections.by_id(i) for i in ids], sequential=False)
    finally:
        Path(out).write_text(json.dumps({"runs": timings,
                                         "stream_seconds": round(time.perf_counter() - start, 1)}))


if __name__ == "__main__":
    sys.path.insert(1, str(Path(__file__).resolve().parent))
    main(sys.argv[1])
