"""dbt in a long-lived process of its own, one per pipeline process
(REQ-PIPE-157, Keith 2026-10-06: "stay in v1 and do the change").

WHY. A run's dbt took ~8s, of which ~1.6s was starting Python and importing
dbt and ~2.5s re-reading the whole project - a full parse every run, because
the schema names changed every run and the partial-parse file lived in each
run's own target directory (parser/manifest.py's state check hashes the
profile's connection_info, `schema` included). Measured with this worker: a
first run ~6s, then ~3.8s a run on one thread.

HOW, using only dbt's documented API - nothing pinned. `dbtRunner().invoke()`
WITHOUT an injected manifest (supported in v1 and v2; injection is what v2
drops), stable schema names for the life of the process so the partial parse
stays valid, and dbt's own `--partial-parse-file-path` pointing at one file
kept here.

A PROCESS, NOT A THREAD IN OURS: dbt does not support concurrent invocations
in one interpreter (docs.getdbt.com/reference/programmatic-invocations), and
it runs beside Soda Core, datacontract-cli and Evidently - which run in ours,
and Soda reloads .env into os.environ (plans/tooling.md #26). Spawned, not
forked, for the reason bootstrap._run_concurrently gives.

ONE REQUEST AT A TIME, behind a lock: runs within a process are sequential,
and the stable schemas are this process's alone. The start, lock, request
and restart code is tool_worker's, which datacontract-cli's worker shares
(REQ-PIPE-431).
"""
from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

from qa_tools.common import tool_worker

#: This process's one dbt worker: (process, connection, partial-parse
#: directory, dbt threads) once started. Its start, lock, request and restart
#: code is tool_worker's, shared with datacontract-cli's worker (REQ-PIPE-431).
_WORKER = tool_worker.Worker(
    "dbt", on_stop=lambda state: shutil.rmtree(state[2], ignore_errors=True))

#: The dbt worker died mid-request (the next request starts another), or did
#: not start.
WorkerLost = tool_worker.WorkerLost


def __getattr__(name: str):
    # `_worker` - the running worker's state, or None - as it was before the
    # shared helper held it.
    if name == "_worker":
        return _WORKER.state
    raise AttributeError(name)


def _serve(conn, root: str, pp_dir: str, threads: int = 1) -> None:
    """The worker's loop: one dbt invocation per request until told to stop,
    every one at the `threads` this worker was started with (REQ-PIPE-432
    criterion 2): one value for the worker's life."""
    os.chdir(root)
    from dbt.cli.main import dbtRunner

    pp = os.path.join(pp_dir, "partial_parse.msgpack")
    while True:
        try:
            msg = conn.recv()
        except EOFError:
            return
        if msg is None:
            return
        args, env, target_path = msg
        # THE CALLER'S ENVIRONMENT FOR THIS RUN: dbt reads its profile's
        # env_var()s afresh on every invoke.
        os.environ.clear()
        os.environ.update(env)
        args = [*args, "--threads", str(threads)]
        if os.path.exists(pp):
            args = [*args, "--partial-parse-file-path", pp]
        os.makedirs(target_path, exist_ok=True)
        # ONLY A PARSE THIS INVOKE WROTE IS KEPT. dbt writes none when it
        # skips parsing, so one an earlier process left in this run's target
        # would otherwise be copied over the kept parse below - and, with no
        # kept parse yet, read in its place (2026-10-12: another worker's
        # schema, so "profile has changed" and a full parse every run).
        fresh = os.path.join(target_path, "partial_parse.msgpack")
        try:
            os.remove(fresh)
        except FileNotFoundError:
            pass
        log_path = os.path.join(target_path, "dbt_worker.log")
        # WHAT dbt SAID, kept for the refusal message as a subprocess's
        # captured output was - written at the file-descriptor level, which
        # is where dbt's own logger writes.
        sys.stdout.flush()
        sys.stderr.flush()
        saved = os.dup(1), os.dup(2)
        with open(log_path, "w") as log:
            os.dup2(log.fileno(), 1)
            os.dup2(log.fileno(), 2)
            try:
                result = dbtRunner().invoke(args)
                ok = bool(result.success)
                said = repr(result.exception) if result.exception else ""
            except BaseException as exc:  # noqa: BLE001 - reported, never swallowed
                ok, said = False, repr(exc)
            finally:
                sys.stdout.flush()
                sys.stderr.flush()
                os.dup2(saved[0], 1)
                os.dup2(saved[1], 2)
                os.close(saved[0])
                os.close(saved[1])
        # THE PARTIAL PARSE CARRIES TO THE NEXT RUN: dbt writes it into the
        # target path, and this keeps a copy where the next invoke reads it.
        if os.path.exists(fresh):
            shutil.copyfile(fresh, pp)
        with open(log_path) as f:
            conn.send((ok, said, f.read()))


def _start(threads: int):
    """Launch the worker (tool_worker.spawn) with a partial-parse folder of
    its own, removed again if it does not start."""
    from qa_tools.common import supply_db

    pp_dir = tempfile.mkdtemp(prefix="mothman-dbt-parse-")
    try:
        proc, conn = tool_worker.spawn(
            "qa_tools.common.dbt_worker", [str(supply_db.ROOT), pp_dir, str(threads)],
            "dbt", cwd=str(supply_db.ROOT))
    except BaseException:
        # Either way the process and its directory go (#131 D4).
        shutil.rmtree(pp_dir, ignore_errors=True)
        raise
    return proc, conn, pp_dir, threads


def invoke(args: list[str], env: dict, target_path: str) -> SimpleNamespace:
    """Run one dbt command in this process's worker; a result shaped like a
    finished subprocess's (returncode, stdout, stderr) for
    dbt_common._refuse_a_build_that_did_not_run."""
    from qa_tools.common import dbt_common

    # REFUSED BEFORE dbt IS STARTED (REQ-PIPE-432 criterion 3).
    threads = dbt_common.dbt_threads()
    # ONE VALUE PER WORKER'S LIFE (criterion 2): the threads are the worker's
    # key, so a changed setting gets a new worker, never a different value in
    # the old one.
    ok, said, log = _WORKER.request((list(args), dict(env), str(target_path)),
                                    start=lambda: _start(threads), key=threads)
    return SimpleNamespace(returncode=0 if ok else 1, stdout=log, stderr=said)


def stop() -> None:
    """End this process's worker and remove its partial-parse file - at exit,
    and for a caller that must hold nothing once it finishes (REQ-PIPE-157's
    disk NFR)."""
    _WORKER.stop()


atexit.register(stop)


def _main(argv: list[str]) -> None:
    host, port, root, pp_dir, threads = argv
    with tool_worker.connect_back(host, port) as conn:
        _serve(conn, root, pp_dir, int(threads))


if __name__ == "__main__":
    _main(sys.argv[1:])
