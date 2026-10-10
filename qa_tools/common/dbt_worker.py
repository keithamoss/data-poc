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
and the stable schemas are this process's alone.
"""
from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace

_lock = threading.Lock()
_worker = None  # (process, connection, partial-parse directory)


class WorkerLost(RuntimeError):
    """The dbt worker process died mid-request; the next request starts another."""


def _serve(conn, root: str, pp_dir: str) -> None:
    """The worker's loop: one dbt invocation per request until told to stop."""
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
        if os.path.exists(pp):
            args = [*args, "--partial-parse-file-path", pp]
        os.makedirs(target_path, exist_ok=True)
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
        fresh = os.path.join(target_path, "partial_parse.msgpack")
        if os.path.exists(fresh):
            shutil.copyfile(fresh, pp)
        with open(log_path) as f:
            conn.send((ok, said, f.read()))


def _start():
    """Launch the worker as ITS OWN MODULE (`python -m`), connected back over
    an authenticated local socket. Not multiprocessing's spawn: that
    re-imports the parent's __main__ in the child, so any caller script
    without a main guard ran itself again inside the worker (found timing
    the 12-arrival replay, whose script has none)."""
    import secrets
    import subprocess
    from multiprocessing.connection import Listener

    from qa_tools.common import supply_db

    key = secrets.token_bytes(32)
    pp_dir = tempfile.mkdtemp(prefix="mothman-dbt-parse-")
    with Listener(("127.0.0.1", 0), authkey=key) as listener:
        host, port = listener.address
        proc = subprocess.Popen(
            [sys.executable, "-m", "qa_tools.common.dbt_worker", host, str(port),
             str(supply_db.ROOT), pp_dir],
            cwd=str(supply_db.ROOT), stdin=subprocess.PIPE,
            env={**os.environ, _KEY_ENV: key.hex()})
        # The key went through the environment, never the command line, which
        # any user on the machine can read.
        # NEVER WAIT FOREVER for a worker that failed to start: the accept is
        # bounded where the platform's listener allows it, and a worker that
        # exited instead of connecting is reported rather than waited on.
        sock = getattr(getattr(listener, "_listener", None), "_socket", None)
        if sock is not None:
            sock.settimeout(60)
        from multiprocessing import AuthenticationError

        try:
            conn = listener.accept()
        except (OSError, AuthenticationError) as exc:
            # A STRAY LOCAL CONNECTION FAILS AUTHENTICATION rather than
            # timing out; either way the process and its directory go
            # (#131 D4).
            proc.kill()
            shutil.rmtree(pp_dir, ignore_errors=True)
            raise WorkerLost(f"the dbt worker did not start (exit {proc.poll()})") from exc
    return proc, conn, pp_dir


#: Carries the socket's key to the worker - out of the process list.
_KEY_ENV = "MOTHMAN_DBT_WORKER_KEY"


def invoke(args: list[str], env: dict, target_path: str) -> SimpleNamespace:
    """Run one dbt command in this process's worker; a result shaped like a
    finished subprocess's (returncode, stdout, stderr) for
    dbt_common._refuse_a_build_that_did_not_run."""
    global _worker
    with _lock:
        if _worker is not None and _worker[0].poll() is not None:
            # DIED WHILE IDLE: let go of its connection and parse directory
            # before starting another (#131 D4 - they leaked).
            stop()
        if _worker is None:
            _worker = _start()
        proc, conn, _pp = _worker
        try:
            conn.send((list(args), dict(env), str(target_path)))
            ok, said, log = conn.recv()
        except (EOFError, BrokenPipeError, ConnectionResetError, OSError) as exc:
            stop()
            raise WorkerLost(f"the dbt worker process stopped mid-run ({type(exc).__name__})"
                             ) from exc
    return SimpleNamespace(returncode=0 if ok else 1, stdout=log, stderr=said)


def stop() -> None:
    """End this process's worker and remove its partial-parse file - at exit,
    and for a caller that must hold nothing once it finishes (REQ-PIPE-157's
    disk NFR)."""
    global _worker
    if _worker is None:
        return
    proc, conn, pp_dir = _worker
    _worker = None
    try:
        conn.send(None)
    except (BrokenPipeError, OSError):
        pass
    try:
        proc.wait(timeout=10)
    except Exception:  # noqa: BLE001 - a worker that will not stop is killed
        proc.kill()
        proc.wait(timeout=5)
    conn.close()
    shutil.rmtree(pp_dir, ignore_errors=True)


atexit.register(stop)


def _main(argv: list[str]) -> None:
    from multiprocessing.connection import Client

    host, port, root, pp_dir = argv
    key = bytes.fromhex(os.environ.pop(_KEY_ENV))
    with Client((host, int(port)), authkey=key) as conn:
        _serve(conn, root, pp_dir)


if __name__ == "__main__":
    _main(sys.argv[1:])
