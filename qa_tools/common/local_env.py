"""Read a developer's own `.env`, so nobody has to remember four exports.

WHY NOT `uv run --env-file`, which would need no code at all: it works
(verified - `uv 0.8.17` reads the file with that flag, and honours
`UV_ENV_FILE`), but it is CLI-only. `env-file` is NOT a `[tool.uv]` or
`uv.toml` setting - uv rejects the key outright - so there is no way to
turn it on once for the repository. Every developer would have to
remember the flag on every command, or export `UV_ENV_FILE` first,
which is the same problem one level down.

So it is loaded here instead, from the two places anything really
starts: `cli/app.py` (every `mothman` command, which this project's own
rules make the only programmatic entry point) and `tests/conftest.py`.

NEVER OVERRIDES SOMETHING ALREADY SET, and that is the load-bearing
property rather than politeness. CI supplies `MOTHMAN_TEST_DSN` through
the workflow; a `.env` that clobbered it would point the CI run at a
database that does not exist there, and the failure would look like a
code fault. Same for a developer who exports a variable deliberately to
try something - the explicit thing they just typed wins over a file
they wrote last month.

THE FILE IS GITIGNORED because it holds a DSN, a DSN holds a password,
and this repository is public. `.env.example` is the committed half:
it names every variable and explains it, with no real value in it.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"

_loaded = False


def load_local_env(path: Path | str | None = None, force: bool = False) -> list[str]:
    """Load `.env` into the environment. Returns the names it SET.

    Idempotent - called from both entry points, and one process can be
    both (`mothman check` runs pytest). Names already present in the
    environment are left alone and are not in the returned list, so a
    caller can say what it actually changed rather than what the file
    happened to contain.
    """
    global _loaded
    if _loaded and not force:
        return []

    target = Path(path) if path else ENV_PATH
    _loaded = True
    if not target.exists():
        return []

    try:
        from dotenv import dotenv_values
    except ImportError:  # pragma: no cover - declared in pyproject
        return []

    applied = []
    for name, value in dotenv_values(target).items():
        if value is None or name in os.environ:
            continue
        os.environ[name] = value
        applied.append(name)
    return applied
