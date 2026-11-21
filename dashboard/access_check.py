"""Is this address behind the Cloudflare Access sign-in? (REQ-PIPE-257
criteria 9 to 12.)

ONE UNAUTHENTICATED REQUEST, NO REDIRECT FOLLOWED: the answer a stranger's
browser would get. Only a redirect to the configured sign-in domain counts as
protected; a 2xx is an open site, a redirect anywhere else is not the sign-in,
and a request that cannot be made proves nothing - each is said in its own
words, and none can be skipped by a flag (criterion 10).
"""
from __future__ import annotations

import http.client
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

SIGNIN, OPEN, ELSEWHERE, UNREACHABLE = "sign-in", "open", "elsewhere", "unreachable"


@dataclass(frozen=True)
class Verdict:
    url: str
    kind: str
    detail: str

    @property
    def protected(self) -> bool:
        return self.kind == SIGNIN

    def words(self) -> str:
        return {
            SIGNIN: f"{self.url} redirects to the sign-in ({self.detail}).",
            OPEN: f"{self.url} is reachable without sign-in: it answered {self.detail}.",
            ELSEWHERE: f"{self.url} redirects somewhere other than the sign-in: {self.detail}.",
            UNREACHABLE: f"{self.url} could not be checked: {self.detail}.",
        }[self.kind]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def check(url: str, signin_domain: str, timeout: float = 15.0) -> Verdict:
    """The verdict for `url`: a redirect to `signin_domain` (or a host under
    it) is the sign-in."""
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(
        context=ssl.create_default_context()))
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "mothman-verify-access"})
    try:
        with opener.open(request, timeout=timeout) as response:
            return Verdict(url, OPEN, f"HTTP {response.status}")
    except urllib.error.HTTPError as answer:
        status = answer.code
        if 300 <= status < 400:
            where = answer.headers.get("Location", "")
            host = (urlsplit(where).hostname or "").lower()
            domain = signin_domain.lower()
            if host == domain or host.endswith("." + domain):
                return Verdict(url, SIGNIN, f"HTTP {status} to {host}")
            return Verdict(url, ELSEWHERE, f"HTTP {status} to {where or 'no Location'}")
        return Verdict(url, UNREACHABLE, f"HTTP {status}")
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        return Verdict(url, UNREACHABLE, f"{type(exc).__name__}: {reason}")
