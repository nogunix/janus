#!/usr/bin/env python3
"""Mechanical URL liveness check for report references (backs gate C1/url).

A curl-level check only: does each public URL in the given markdown
file(s) resolve to something other than 404/410? A dead or
unresolvable reference is the signature of a fabricated citation —
content quality stays the human-level gates' job; this catches the
references that provably point at nothing.

Classification:
  OK          2xx/3xx to the same content (a genuinely live reference)
  gated       401/403/429, or a redirect into a login/SSO flow — the
              portal (e.g. access.redhat.com) masks both real gated pages
              and fabricated paths behind login, so existence is NOT
              content-confirmed; flagged for a human, never a clean live
              and never a hard FAIL
  warning     5xx, timeouts, or a connection *reset* by a host that did
              resolve and accept the TCP connection (anti-automation, not
              fabrication — the host is provably live)
  FAIL        404/410, or unresolvable host / connection refused

Exit 1 on any FAIL — except when *every* URL is unreachable, which
means the network itself is down (air-gapped installs are normal for
okp-mcp users): print a notice and exit 0. `gated` URLs never fail the
run but are reported separately so a reviewer verifies them by hand.

Usage: python3 urlcheck.py <file.md> [file.md ...]
Stdlib-only, like chain.py.
"""

import errno
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

URL_RE = re.compile(r"https?://[^\s<>\)\]\"'`]+")
TRAILING = ".,;:!?"
TIMEOUT = 10
HEADERS = {"User-Agent": "janus-urlcheck (+https://github.com/nogunix/janus)"}

GATED_ERRORS = (401, 403, 429)  # exists, just auth-gated
DEAD_ERRORS = (404, 410)
# A redirect that lands here means the portal masked the resource behind
# login — a real gated page and a fabricated path that doesn't exist are
# indistinguishable without authenticating, so neither is a clean "live".
LOGIN_HOST_RE = re.compile(r"(^|\.)(sso|login|accounts|auth|oauth|idp)\.", re.I)
LOGIN_PATH_RE = re.compile(r"/(auth|login|oauth|saml|openid)", re.I)


def extract_urls(text):
    urls = []
    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(TRAILING)
        if url not in urls:
            urls.append(url)
    return urls


def _request(url, method):
    """Returns (status_code, final_url) after following redirects."""
    req = urllib.request.Request(url, method=method, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.status, resp.geturl()


def _is_login(url):
    parts = urllib.parse.urlsplit(url)
    return bool(LOGIN_HOST_RE.search(parts.netloc) or LOGIN_PATH_RE.search(parts.path))


def check(url):
    """Returns (status, detail): ok | gated | warn | dead | unreachable.

    gated = reachable but existence not content-confirmed (auth wall or a
    redirect into a login/SSO flow) — flagged for a human, never counted
    as a clean live URL and never a hard FAIL.
    """
    origin = urllib.parse.urlsplit(url).netloc
    for method in ("HEAD", "GET"):
        try:
            code, final_url = _request(url, method)
            if _is_login(final_url) and not _is_login(url):
                return ("gated", f"{code} → login redirect ({urllib.parse.urlsplit(final_url).netloc})")
            return ("ok", code)
        except urllib.error.HTTPError as e:
            if e.code in GATED_ERRORS:
                return ("gated", f"{e.code} (auth-gated)")
            if e.code in DEAD_ERRORS:
                return ("dead", e.code)
            if e.code == 405 and method == "HEAD":
                continue  # server dislikes HEAD — retry as GET
            return ("warn", e.code)
        except (socket.timeout, TimeoutError):
            return ("warn", "timeout")
        except Exception as e:
            reason = getattr(e, "reason", e)
            # A connection *reset* proves the host resolved and completed
            # the TCP handshake before dropping us — i.e. it is live and
            # merely refusing this client (anti-automation, as
            # issues.redhat.com does). That is not a dead citation, so it
            # is a non-blocking warning, unlike an unresolvable host or a
            # connection *refused* (which stay hard FAILs below).
            if isinstance(reason, ConnectionResetError) or \
                    getattr(reason, "errno", None) == errno.ECONNRESET:
                return ("warn", "connection reset (host live; anti-automation)")
            return ("unreachable", str(reason))
    return ("warn", "405 on HEAD and GET")


def main(argv):
    if len(argv) < 2:
        print("usage: urlcheck.py <file.md> [file.md ...]")
        return 2
    urls = []
    for arg in argv[1:]:
        path = Path(arg)
        if not path.is_file():
            print(f"error: no such file: {path}")
            return 2
        for url in extract_urls(path.read_text(encoding="utf-8")):
            if url not in urls:
                urls.append(url)
    if not urls:
        print("no URLs found")
        return 0

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(check, urls))

    failures = gated = 0
    for url, (status, detail) in zip(urls, results):
        if status == "ok":
            print(f"OK: {url} ({detail})")
        elif status == "gated":
            print(f"gated: {url} ({detail}) — existence not confirmed, "
                  "verify by hand")
            gated += 1
        elif status == "warn":
            print(f"warning: {url} ({detail})")
        else:
            print(f"FAIL: {url} ({detail})")
            failures += 1

    if failures and all(s == "unreachable" for s, _ in results):
        print(f"note: all {len(urls)} URLs unreachable — network appears "
              "unavailable; liveness not checked (not counted as failures)")
        return 0
    if failures:
        print(f"{failures}/{len(urls)} references point at nothing — "
              "send back to synthesize under C1/url")
        return 1
    live = len(urls) - gated
    tail = f" ({gated} gated — verify by hand)" if gated else ""
    print(f"OK: {live}/{len(urls)} URLs live{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
