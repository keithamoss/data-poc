"""
Dev-only tool: serve the real, already-built dashboard
(`dashboard/qa-reporting-dashboard.html`) over local HTTPS, with a real
throwaway self-signed certificate. Built 2026-09-19 for the
requirements-analysis agents' own post-build UX/visual critique pass
(`delivery-critic`/`delivery-dashboard-ux-critic`/
`delivery-dashboard-visual-critic`, `plans/wider.md` #10) - Keith's own
explicit call, after a real bug was found: the project's Playwright MCP
server (`.mcp.json`) blocks the `file://` protocol outright by default,
so those agents could never actually open
`file:///.../dashboard/qa-reporting-dashboard.html` the way their own
earlier instructions described. Rather than loosen the MCP server's own
file-access restriction (`--allow-unrestricted-file-access`, which grants
`file://` access to the whole filesystem, not just this repo - broader
than this project actually needs), Keith chose serving it instead -
and asked specifically for HTTPS, not plain HTTP, so the review happens
over a transport closer to the real published site
(GitHub Pages, always HTTPS) than a bare local HTTP server would be.

Real mechanism, verified end to end before this was written into any
agent's own instructions (2026-09-19): a real ephemeral self-signed
certificate via `openssl req -x509` (1-day validity, no passphrase -
this is a throwaway local dev cert, never committed, regenerated every
run), wrapping Python's stdlib `http.server` in a real `ssl.SSLContext`.
The Playwright MCP server's own `--ignore-https-errors` flag (already
added to `.mcp.json`) is what lets a real headless browser accept this
self-signed cert without failing TLS verification - the same real
`ignore_https_errors` Playwright context option this project's own ad
hoc reviewer scripts already use elsewhere, just supplied to the MCP
server at launch instead of per-script.

Usage:
    uv run python3 scripts/dev/serve_dashboard_https.py [--port PORT]

Defaults to an OS-assigned ephemeral port (`--port 0`, the default) so
two invocations never collide - the actual port is printed to stdout as
the very first line, in the form `PORT=<n>`, so a caller (an agent
running this via Bash) can read it back without guessing. Pass an
explicit `--port` only for a one-off manual run where a fixed, memorable
port is more convenient than reading it back.

Real gap this fixes (2026-09-19, Keith's own explicit follow-up after
approving the HTTPS-serving mechanism itself): the original version
always bound a fixed default port (8743) - fine for one agent at a time,
but `delivery-critic`/`delivery-dashboard-ux-critic`/
`delivery-dashboard-visual-critic` can in principle run concurrently (nothing
stops a caller invoking more than one in parallel), and a second
`serve_dashboard_https.py` on the same fixed port would fail outright
with "address already in use" rather than degrade gracefully.

Runs in the foreground - background it yourself (`... &` in Bash) and
stop it (`kill %1`, or `pkill -f serve_dashboard_https`) once the real
Playwright MCP review pass is done; this is a throwaway dev server, not
a real, committed service.
"""
from __future__ import annotations

import argparse
import http.server
import shutil
import ssl
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = ROOT / "dashboard"
BUILT_FILE = DASHBOARD_DIR / "qa-reporting-dashboard.html"


def _generate_self_signed_cert(cert_dir: Path) -> tuple[Path, Path]:
    """A real, throwaway self-signed cert for `localhost` - 1-day
    validity, no passphrase (`-nodes`), never committed. Requires a real
    `openssl` binary (present on every environment this project has
    actually run on so far - not a new dependency)."""
    if shutil.which("openssl") is None:
        sys.exit("openssl not found - required to generate a throwaway local HTTPS cert.")
    key_path = cert_dir / "key.pem"
    cert_path = cert_dir / "cert.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key_path), "-out", str(cert_path),
            "-days", "1", "-nodes", "-subj", "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )
    return cert_path, key_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port", type=int, default=0,
        help="Port to bind. Default 0 = let the OS assign a free ephemeral "
             "port (so parallel runs never collide) - the actual port is "
             "printed as `PORT=<n>` on the first stdout line.",
    )
    args = parser.parse_args()

    if not BUILT_FILE.exists():
        sys.exit(
            f"{BUILT_FILE} doesn't exist yet - run `uv run mothman dashboard rebuild` "
            f"(or the individual build-data/embed steps) first."
        )

    with tempfile.TemporaryDirectory(prefix="dashboard-https-cert-") as tmp:
        cert_path, key_path = _generate_self_signed_cert(Path(tmp))

        handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(  # noqa: E731
            *a, directory=str(DASHBOARD_DIR), **kw
        )
        server = http.server.HTTPServer(("localhost", args.port), handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
        server.socket = ctx.wrap_socket(server.socket, server_side=True)

        bound_port = server.server_address[1]
        print(f"PORT={bound_port}")
        print(f"Serving {DASHBOARD_DIR} over HTTPS at "
              f"https://localhost:{bound_port}/qa-reporting-dashboard.html "
              f"(self-signed cert - the Playwright MCP server's own "
              f"--ignore-https-errors flag is what makes this real browser "
              f"navigation actually work). Ctrl-C to stop.")
        sys.stdout.flush()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
