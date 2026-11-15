"""datacontract-cli's library call in a long-lived process of its own, one per
pipeline process (REQ-PIPE-431), so it runs beside Soda Core and Evidently in
the foreground and dbt in its worker rather than after them.

ONLY THE LIBRARY CALL MOVES (criteria 1 and 2): this runs
datacontract_common.run_against_warehouse - DataContract.test() over the run's
view schema - and nothing else. Asking, filtering, left-out notes and
recording stay in run_datacontract.evaluate, in the run's own process, so the
records carry that process's replay clock and staged agreement, the left-out
comparison holds and a re-check trial keeps its scope. NOTHING THAT RECORDS
RUNS HERE.

A PROCESS, NOT A THREAD: datacontract-cli, Soda Core and Evidently were never
written to share an interpreter concurrently, and Soda reloads .env into
os.environ (plans/tooling.md #26), which cannot reach a process of its own.

The start, lock, request and restart code is dbt's worker's, shared through
tool_worker rather than copied. Credentials travel as each request's
environment over the authenticated connection, never on a command line
(criterion 3).

WHERE TOOLS_CONCURRENTLY IS OFF (`--sequential`, criterion 8) the call runs
here, in this process, as it always did.
"""
from __future__ import annotations

import atexit
import os
import pickle
import sys
from types import SimpleNamespace

from qa_tools.common import tool_worker

#: The one datacontract-cli worker of this process.
_WORKER = tool_worker.Worker("datacontract-cli")


class DatacontractWorkerFailed(RuntimeError):
    """datacontract-cli's worker died on a run's request, or could not be
    started (criterion 6) - a tool error about this machine, never about the
    supply's data."""


_STOPPED = (
    "datacontract-cli could not finish checking this run: its worker process stopped "
    "mid-run ({cause}). The supply's data was not the cause. The run's other tools' "
    "results are recorded but do not stand on their own - the run is not finished, so "
    "the supply is not checked. The next run starts a new worker, so a re-run should "
    "go through.")
_DID_NOT_START = (
    "datacontract-cli could not check this run: its worker process did not start "
    "({cause}). The supply's data was not the cause. The run's other tools' results are "
    "recorded but do not stand on their own - the run is not finished, so the supply is "
    "not checked. The next run will fail the same way until the worker can start: check "
    "that `uv run python -m qa_tools.common.datacontract_worker` can import "
    "datacontract-cli in this environment, and that the machine has memory and "
    "processes to spare.")


def _start():
    from qa_tools.common import supply_db

    return tool_worker.spawn("qa_tools.common.datacontract_worker", [str(supply_db.ROOT)],
                             "datacontract-cli", cwd=str(supply_db.ROOT))


def run_against_warehouse(contract_path: str, schema: str, **options):
    """datacontract_common.run_against_warehouse, in this process's worker
    while a run's tools overlap - its result as a Run-like value: `checks`
    (each with type, name, model, field, dimension, diagnostics,
    qualityDefinition, failedSamples and result.value) and model_dump(), the
    raw output recorded as before. In this process when they do not."""
    from asset_model import assets
    from qa_tools.common import datacontract_common, parallel_orchestrate

    if not parallel_orchestrate.TOOLS_CONCURRENTLY:
        return datacontract_common.run_against_warehouse(contract_path, schema, **options)
    from qa_tools.common import supply_db

    handoff = assets.handoff()
    message = (dict(os.environ), handoff, str(contract_path), schema, dict(options))
    try:
        # ONE ASSET AND ONE DATABASE PER WORKER, as per process (supply_db's
        # OneAssetPerProcess): a caller that moves to another restarts it.
        ok, payload = _WORKER.request(message, start=lambda: _start(),
                                      key=(handoff, supply_db.supply_db_dsn()))
    except tool_worker.WorkerDidNotStart as exc:
        raise DatacontractWorkerFailed(_DID_NOT_START.format(cause=exc)) from exc
    except tool_worker.WorkerLost as exc:
        raise DatacontractWorkerFailed(_STOPPED.format(cause=exc)) from exc
    if not ok:
        raise payload
    return _Run(payload)


class _Run:
    """What the worker hands back, shaped as evaluate reads a Run."""

    def __init__(self, payload: dict):
        self._raw = payload["raw"]
        self.checks = [SimpleNamespace(**{**c, "result": SimpleNamespace(value=c["result"])})
                       for c in payload["checks"]]

    def model_dump(self) -> dict:
        return self._raw


#: The attributes of each check evaluate and failing_sample_keys read.
_CHECK_FIELDS = ("type", "name", "model", "field", "dimension", "diagnostics",
                 "qualityDefinition", "failedSamples", "reason")


def _picklable(run) -> dict:
    """The run as plain values: each check's fields, its samples as the tool
    gave them (keys keep their own types), and the raw output exactly as it
    is recorded (json.dumps with default=str, as qa_store writes it)."""
    import json

    checks = []
    for c in run.checks:
        result = getattr(c.result, "value", c.result)
        checks.append({**{f: getattr(c, f, None) for f in _CHECK_FIELDS}, "result": result})
    return {"checks": checks, "raw": json.loads(json.dumps(run.model_dump(), default=str))}


def _serve(conn, root: str) -> None:
    """The worker's loop: one library call per request until told to stop."""
    os.chdir(root)
    from asset_model import assets
    from qa_tools.common import datacontract_common

    adopted = None
    while True:
        try:
            msg = conn.recv()
        except EOFError:
            return
        if msg is None:
            return
        env, handoff, contract_path, schema, options = msg
        # THE CALLER'S ENVIRONMENT AND ASSET FOR THIS RUN.
        os.environ.clear()
        os.environ.update(env)
        try:
            if handoff != adopted:
                assets.adopt(*handoff)
                adopted = handoff
            reply = (True, _picklable(datacontract_common.run_against_warehouse(
                contract_path, schema, **options)))
        except Exception as exc:  # noqa: BLE001 - handed back and raised there
            try:
                pickle.dumps(exc)
            except Exception:  # noqa: BLE001 - an exception that cannot travel
                exc = RuntimeError(f"{type(exc).__name__}: {exc}")
            reply = (False, exc)
        conn.send(reply)


def stop() -> None:
    """End this process's datacontract-cli worker."""
    _WORKER.stop()


atexit.register(stop)


def _main(argv: list[str]) -> None:
    host, port, root = argv
    with tool_worker.connect_back(host, port) as conn:
        _serve(conn, root)


if __name__ == "__main__":
    _main(sys.argv[1:])
