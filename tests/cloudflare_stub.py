"""Stand-ins for Cloudflare, so the publish is driven with no account, token
or network (REQ-PIPE-255 criterion 30, REQ-PIPE-257 criterion 13).

A STUB WRANGLER first on PATH records each call's arguments and environment
to a JSON-lines log and answers as wrangler does. AN HTTP STUB on localhost
answers one way per path - the sign-in redirect, an open 200 dashboard, a
redirect elsewhere and a 404 - and a closed port stands for a refused
connection. `route` points the publish's checks of *.pages.dev at it.
"""
from __future__ import annotations

import http.server
import json
import os
import socket
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

PINNED = json.loads((Path(__file__).resolve().parents[1] / "package.json").read_text())[
    "devDependencies"]["wrangler"]
SIGNIN_DOMAIN = "team.cloudflareaccess.com"
TOKEN = "cf-test-token-0123456789abcdef"

_SCRIPT = '''#!{python}
import json, os, sys
log = {log!r}
with open(log, "a") as f:
    f.write(json.dumps({{"argv": sys.argv[1:], "env": {{k: os.environ.get(k) for k in
        ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "WRANGLER_SEND_METRICS")}}}}) + "\\n")
args = sys.argv[1:]
if args == ["--version"]:
    print({version!r}); sys.exit(0)
if args[:2] == ["pages", "deploy"]:
    if {fail!r}:
        print("Upload failed: authentication error for token " + os.environ.get("CLOUDFLARE_API_TOKEN", ""),
              file=sys.stderr)
        sys.exit(1)
    project = args[args.index("--project-name") + 1]
    print("Uploading... (3/3)")
    print(f"Deployment complete! Take a peek over at https://abc123.{{project}}.pages.dev")
    sys.exit(0)
if args[:3] == ["pages", "deployment", "list"]:
    project = args[args.index("--project-name") + 1]
    print(json.dumps([{{"Id": "abc123", "Deployment": f"https://abc123.{{project}}.pages.dev"}}]))
    sys.exit(0)
print("unexpected wrangler call", args, file=sys.stderr); sys.exit(2)
'''


def stub_wrangler(tmp_path: Path, monkeypatch, *, version: str = PINNED, fail: bool = False) -> Path:
    """A stub wrangler first on PATH, with the credentials set; returns its log."""
    bin_dir = tmp_path / "stub-bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "wrangler-calls.jsonl"
    script = bin_dir / "wrangler"
    script.write_text(_SCRIPT.format(python=sys.executable, log=str(log), version=version, fail=fail))
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-123")
    return log


def calls(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - the stdlib's name
        if self.path.startswith("/signin"):
            self.send_response(302)
            self.send_header("Location", f"https://{SIGNIN_DOMAIN}/cdn-cgi/access/login/x")
        elif self.path.startswith("/open"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
        elif self.path.startswith("/elsewhere"):
            self.send_response(302)
            self.send_header("Location", "https://example.org/somewhere")
        else:
            self.send_response(404)
        self.end_headers()
        if self.path.startswith("/open"):
            self.wfile.write(b"<html>the dashboard</html>")

    def log_message(self, *a):
        pass


@contextmanager
def access_stub():
    """(base_url, refused_url): the HTTP stub, and an address nothing listens on."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    refused = f"http://127.0.0.1:{probe.getsockname()[1]}/"
    probe.close()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", refused
    finally:
        server.shutdown()


def route(monkeypatch, base: str, *, production: str = "signin", deployment: str = "signin") -> None:
    """Point the publish's checks of the production host and of a deployment's
    own host at the stub, answering as `production` and `deployment` say."""
    from dashboard import access_check

    real = access_check.check

    def routed(url, domain, timeout=15.0):
        from urllib.parse import urlsplit

        host = urlsplit(url).hostname or ""
        kind = deployment if host.count(".") > 2 else production
        return real(f"{base}/{kind}", domain, timeout)
    monkeypatch.setattr(access_check, "check", routed)
