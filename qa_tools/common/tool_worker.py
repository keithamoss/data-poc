"""A QA tool in a long-lived process of its own, one per pipeline process - the
start, lock, request and restart code dbt's worker (dbt_worker, REQ-PIPE-157)
and datacontract-cli's (datacontract_worker, REQ-PIPE-431) share, rather than
each keeping a copy (REQ-PIPE-431 criterion 1 and its MAINTAINABILITY NFR).

STARTED AS ITS OWN MODULE (`python -m`), connected back over an authenticated
local socket. Not multiprocessing's spawn: that re-imports the parent's
__main__ in the child, so any caller script without a main guard ran itself
again inside the worker (found timing the 12-arrival replay, whose script has
none). Not forked, for the reason bootstrap._run_concurrently gives.

THE SOCKET'S KEY GOES THROUGH THE ENVIRONMENT, never the command line, which
any user on the machine can read; so do the database credentials, which each
request carries in its own environment over that authenticated connection.

ONE REQUEST AT A TIME, behind a lock: a worker serves one run's call, and a
caller that sends another waits for it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from typing import Callable

#: Carries the socket's key to the worker - out of the process list.
KEY_ENV = "MOTHMAN_TOOL_WORKER_KEY"

#: How long a starting worker has to connect back before it is given up on.
START_TIMEOUT_S = 60


class WorkerLost(RuntimeError):
    """A worker process died mid-request; the next request starts another."""


class WorkerDidNotStart(WorkerLost):
    """A worker process exited, or never connected back, when it was started."""


def spawn(module: str, argv: list[str], label: str, *, cwd: str):
    """Start `python -m module *argv host port` and return (process,
    connection) once it has connected back; WorkerDidNotStart, with nothing
    left running, when it does not."""
    import secrets
    from multiprocessing import AuthenticationError
    from multiprocessing.connection import Listener

    key = secrets.token_bytes(32)
    with Listener(("127.0.0.1", 0), authkey=key) as listener:
        host, port = listener.address
        proc = subprocess.Popen([sys.executable, "-m", module, host, str(port), *argv],
                                cwd=cwd, stdin=subprocess.PIPE,
                                env={**os.environ, KEY_ENV: key.hex()})
        # NEVER WAIT FOREVER for a worker that failed to start: the accept is
        # bounded where the platform's listener allows it, and a worker that
        # exited instead of connecting is reported rather than waited on.
        sock = getattr(getattr(listener, "_listener", None), "_socket", None)
        if sock is not None:
            sock.settimeout(START_TIMEOUT_S)
        try:
            conn = listener.accept()
        except (OSError, AuthenticationError) as exc:
            # A STRAY LOCAL CONNECTION FAILS AUTHENTICATION rather than timing
            # out; either way the process goes (#131 D4).
            proc.kill()
            proc.wait()
            raise WorkerDidNotStart(
                f"the {label} worker did not start (exit {proc.poll()})") from exc
    return proc, conn


def connect_back(host: str, port: str):
    """The worker's side of spawn(): its connection to the process that
    started it, authenticated with the key it was handed."""
    from multiprocessing.connection import Client

    key = bytes.fromhex(os.environ.pop(KEY_ENV))
    return Client((host, int(port)), authkey=key)


class Worker:
    """One long-lived worker process for this process: started on first use,
    reused, restarted when it has died or when the `key` it was started for
    changes, and stopped at exit.

    `state` is whatever `start` returned - (process, connection, *extra) -
    and `on_stop(state)` lets go of the extra (dbt's partial-parse folder)."""

    def __init__(self, label: str, *, on_stop: Callable | None = None):
        self.label = label
        self._on_stop = on_stop
        # REENTRANT: a request that finds its worker dead stops it while it
        # holds the lock.
        self._lock = threading.RLock()
        self.state = None
        self._key = None

    def request(self, message, *, start: Callable[[], tuple], key=None):
        """Send one request and return the reply; WorkerLost when the worker
        dies on it, WorkerDidNotStart when it cannot be started."""
        with self._lock:
            if self.state is not None and (self.state[0].poll() is not None
                                           or self._key != key):
                # DIED WHILE IDLE, or started for something else: let go of
                # it before starting another (#131 D4 - they leaked).
                self.stop()
            if self.state is None:
                self.state, self._key = start(), key
            conn = self.state[1]
            try:
                conn.send(message)
                return conn.recv()
            except (EOFError, BrokenPipeError, ConnectionResetError, OSError) as exc:
                self.stop()
                raise WorkerLost(f"the {self.label} worker process stopped mid-run "
                                 f"({type(exc).__name__})") from exc

    def stop(self) -> None:
        """End the worker - at exit, and for a caller that must hold nothing
        once it finishes."""
        with self._lock:
            state, self.state = self.state, None
            if state is None:
                return
            proc, conn = state[0], state[1]
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
            if self._on_stop is not None:
                self._on_stop(state)
