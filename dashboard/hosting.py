"""Publishing the built dashboard to its asset's Cloudflare Pages project
(REQ-PIPE-255; one project per asset, REQ-PIPE-354).

WRANGLER IS THE TRANSPORT, pinned exactly in package.json (criterion 4). It is
found on PATH first and then in this repository's node_modules/.bin - so a
test can put a stub first on PATH (criterion 30) - and whichever is found must
report the pinned version, or the publish is refused: an unpinned wrangler is
never run.

THE TOKEN NEVER REACHES A COMMAND LINE (criterion 10). It travels to wrangler
in the child's environment only, and anything wrangler prints or raises is
passed through redact() first (criterion 11).

Nothing here reads the database: the site is built before this module is
reached, from recorded results only (criterion 19).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN_ENV = "CLOUDFLARE_API_TOKEN"
ACCOUNT_ENV = "CLOUDFLARE_ACCOUNT_ID"
MIB = 1024 * 1024
#: Cloudflare Pages serves no file over 25 MiB (criterion 13); a file past
#: 20 MiB is warned about at every build and publish (criteria 14 and 26).
LIMIT_BYTES = 25 * MIB
WARN_BYTES = 20 * MIB
REDACTED = "<redacted CLOUDFLARE_API_TOKEN>"
#: The one-time setup that installs the pinned wrangler (criterion 5).
SETUP = "npm ci"


class PublishRefused(RuntimeError):
    """A publish refused before anything is built, written or uploaded."""


@dataclass(frozen=True)
class Hosting:
    pages_project: str
    production_branch: str
    address: str
    access_domain: str

    @property
    def production_host(self) -> str:
        return f"{self.pages_project}.pages.dev"


def hosting() -> Hosting | None:
    """The selected asset's hosting, from its data-asset.yaml (criterion 8),
    or None where it declares none."""
    from asset_model import assets, config_yaml

    doc = config_yaml.load(assets.selected().data_asset_yaml) or {}
    found = doc.get("hosting")
    if not found:
        return None
    return Hosting(**{k: str(found[k]) for k in ("pages_project", "production_branch",
                                                  "address", "access_domain")})


def pinned_version() -> str:
    """wrangler's version as package.json pins it - exactly (criterion 4)."""
    pins = json.loads((ROOT / "package.json").read_text()).get("devDependencies", {})
    version = pins.get("wrangler")
    if not version or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise PublishRefused(f"package.json must pin wrangler to an exact version; it says {version!r}.")
    return version


def find_wrangler() -> str:
    """Where wrangler is, refused when it is not installed (criterion 5) -
    WITHOUT RUNNING IT, so the refusal before a build costs nothing and an
    unchanged publish invokes wrangler zero times (criterion 30)."""
    search = os.pathsep.join([os.environ.get("PATH", ""), str(ROOT / "node_modules" / ".bin")])
    found = shutil.which("wrangler", path=search)
    if not found:
        raise PublishRefused(f"wrangler is not installed here. Run `{SETUP}` once in the repository, "
                             f"which installs the version package.json pins, then publish again.")
    return found


def wrangler() -> str:
    """The wrangler to run, refused unless it is the pinned version
    (criterion 4) - asked just before it is used, never earlier."""
    found = find_wrangler()
    want = pinned_version()
    got = subprocess.run([found, "--version"], capture_output=True, text=True,
                         env=_child_env(with_credentials=False)).stdout
    if want not in got:
        raise PublishRefused(f"{found} is wrangler {got.strip() or 'of an unknown version'}, not the "
                             f"{want} package.json pins. Run `{SETUP}`, then publish again.")
    return found


def missing_credentials() -> list[str]:
    """Each credential variable unset or empty (criteria 6 and 7)."""
    return [name for name in (TOKEN_ENV, ACCOUNT_ENV) if not os.environ.get(name, "").strip()]


def credentials_refusal() -> str | None:
    """Criterion 7, in the plain shape of the unset MOTHMAN_ENVIRONMENT
    refusal: what is missing, and where it is set."""
    missing = missing_credentials()
    if not missing:
        return None
    return (f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not set. A publish "
            f"uploads to Cloudflare with an API token and an account id, read from the environment "
            f"and never from a file; docs/dashboard-hosting.md says how to create the token and "
            f"where to set both.")


def redact(text: str) -> str:
    """Criterion 11: the token replaced wherever it appears."""
    token = os.environ.get(TOKEN_ENV, "")
    return text.replace(token, REDACTED) if token else text


def _child_env(*, with_credentials: bool = True) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in (TOKEN_ENV, ACCOUNT_ENV)}
    # NO USAGE TELEMETRY, on every invocation (criterion 12).
    env["WRANGLER_SEND_METRICS"] = "false"
    if with_credentials:
        env[TOKEN_ENV] = os.environ.get(TOKEN_ENV, "")
        env[ACCOUNT_ENV] = os.environ.get(ACCOUNT_ENV, "")
    return env


@dataclass(frozen=True)
class SiteSize:
    files: int
    total_bytes: int
    largest: tuple[str, int]
    over_limit: tuple[tuple[str, int], ...]
    over_warning: tuple[tuple[str, int], ...]


def measure(site_dir: Path) -> SiteSize:
    """Every file's size, against the per-file limit (criteria 13 and 14)."""
    sizes = [(p.relative_to(site_dir).as_posix(), p.stat().st_size)
             for p in sorted(Path(site_dir).rglob("*")) if p.is_file()]
    largest = max(sizes, key=lambda x: x[1]) if sizes else ("", 0)
    return SiteSize(files=len(sizes), total_bytes=sum(n for _, n in sizes), largest=largest,
                    over_limit=tuple(s for s in sizes if s[1] > LIMIT_BYTES),
                    over_warning=tuple(s for s in sizes if WARN_BYTES < s[1] <= LIMIT_BYTES))


def mib(n: int) -> str:
    return f"{n / MIB:.2f} MiB"


def deploy_args(site_dir: Path, where: Hosting, commit: str | None) -> list[str]:
    """The arguments for one upload (criteria 9 and 17): the project and the
    production branch named explicitly, so a publish from any git branch is a
    production deployment, and the commit the code was built from."""
    args = ["pages", "deploy", str(site_dir), "--project-name", where.pages_project,
            "--branch", where.production_branch]
    if commit:
        args += ["--commit-hash", commit]
    return args


#: A pages.dev address in wrangler's words or JSON - ending at a quote,
#: bracket or space.
_URL = re.compile(r"https://[A-Za-z0-9.-]+\.pages\.dev[^\s\"'\]\}]*")


@dataclass(frozen=True)
class Deployment:
    url: str
    production_url: str


class UploadFailed(RuntimeError):
    """wrangler said the upload failed; its words, redacted (criterion 15)."""


def upload(site_dir: Path, where: Hosting, commit: str | None) -> Deployment:
    """One upload, never retried (criterion 15)."""
    run = subprocess.run([wrangler(), *deploy_args(site_dir, where, commit)],
                         capture_output=True, text=True, env=_child_env())
    said = redact((run.stdout or "") + (run.stderr or ""))
    if run.returncode:
        raise UploadFailed(said.strip() or f"wrangler exited {run.returncode} and said nothing.")
    found = [u.rstrip(".,)") for u in _URL.findall(said)]
    own = next((u for u in found if not u.startswith(f"https://{where.production_host}")), None)
    if not own:
        raise UploadFailed(f"wrangler reported success but named no deployment URL:\n{said.strip()}")
    return Deployment(url=own, production_url=f"https://{where.production_host}")


def latest_deployment_url(where: Hosting) -> str | None:
    """The most recent deployment's own URL (REQ-PIPE-257 criterion 12), from
    wrangler's deployment list."""
    run = subprocess.run([wrangler(), "pages", "deployment", "list", "--project-name",
                          where.pages_project, "--json"],
                         capture_output=True, text=True, env=_child_env())
    said = redact((run.stdout or "") + (run.stderr or ""))
    if run.returncode:
        raise UploadFailed(said.strip() or "wrangler could not list the deployments.")
    found = [u.rstrip(".,)\"") for u in _URL.findall(said)
             if not u.startswith(f"https://{where.production_host}")]
    return found[0] if found else None
