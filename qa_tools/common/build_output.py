"""Where a dashboard build writes (REQ-TEST-281).

A build has two outputs: the `reports/` files (each collection's results file
and its dashboard file) and the built page with its data files. Both go to the
real tree by default - `reports/` and `dashboard/qa-reporting-dashboard.html`.

`mothman dashboard rebuild-results|build-data|embed|rebuild --out-dir DIR`
sends the whole build somewhere else instead: `DIR/reports/` for the reports,
`DIR/qa-reporting-dashboard.html` for the page, `DIR/data/` for its data files,
and `DIR/fonts/`, `DIR/vendor/` copied in beside it so the page renders from
DIR exactly as it does from `dashboard/`. A DIR is self-contained in both
directions: each step of the chain READS the reports the step before it wrote
there, never the real tree's.

WHY IT EXISTS: the browser tests build the dashboard once per test worker, and
two builds sharing a file is the race `--dist loadfile` used to be the only
thing preventing (plans/tooling.md #10, race 2). One directory per build means
no two builds share a file, by construction rather than by ordering.

THE OPTION IS CARRIED IN AN ENVIRONMENT VARIABLE, `MOTHMAN_DASHBOARD_OUT`,
read at call time - so the three steps of the chain, which are separate
commands and often separate processes, agree on it without each module
growing its own parameter. The command-line option is the interface; the
variable is how it travels.
"""
from __future__ import annotations

import os

#: The variable `--out-dir` sets. Unset (the default), a build writes the real tree.
OUT_DIR_ENV = "MOTHMAN_DASHBOARD_OUT"

#: The built page's file name, in the real tree and in an out dir alike.
PAGE_NAME = "qa-reporting-dashboard.html"


def out_dir() -> str | None:
    """The build's own directory when one was given, else None (the real tree)."""
    value = os.environ.get(OUT_DIR_ENV)
    return os.path.abspath(value) if value else None


def use(directory) -> str:
    """Send this process's builds, and its children's, to `directory`."""
    path = os.path.abspath(os.fspath(directory))
    os.makedirs(path, exist_ok=True)
    os.environ[OUT_DIR_ENV] = path
    return path


def reports_dir(default: str) -> str:
    """Where the results and dashboard files are written and read: the build's
    own `reports/` under `--out-dir`, else `default` - the caller's own
    constant, so a test redirecting that constant still redirects it."""
    out = out_dir()
    return os.path.join(out, "reports") if out else default
