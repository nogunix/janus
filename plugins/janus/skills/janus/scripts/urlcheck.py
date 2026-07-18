#!/usr/bin/env python3
"""Mechanical URL liveness check for report references (backs gate G2-URL).

A curl-level check only: does each public URL in the given markdown
file(s) resolve to something other than 404/410? A dead or
unresolvable reference is the signature of a fabricated citation —
content quality stays the human-level gates' job; this catches the
references that provably point at nothing.

Classification:
  OK          2xx/3xx, or 401/403/429 (reachable but login-walled —
              normal for access.redhat.com)
  warning     5xx, timeouts (server trouble is not fabrication)
  FAIL        404/410, or unresolvable host / connection refused

Exit 1 on any FAIL — except when *every* URL is unreachable, which
means the network itself is down (air-gapped installs are normal for
okp-mcp users): print a notice and exit 0.

Usage: python3 urlcheck.py <file.md> [file.md ...]
Stdlib-only, like chain.py.
"""

import re
import socket
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

URL_RE = re.compile(r"https?://[^\s<>\)\]\"'`]+")
TRAILING = ".,;:!?"
TIMEOUT = 10
HEADERS = {"User-Agent": "janus-urlcheck (+https://github.com/nogunix/janus)"}

REACHABLE_ERRORS = (401, 403, 429)  # exists, just gated
DEAD_ERRORS = (404, 410)


def extract_urls(text):
    urls = []
    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(TRAILING)
        if url not in urls:
            urls.append(url)
    return urls


def _request(url, method):
    req = urllib.request.Request(url, method=method, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.status


def check(url):
    """Returns (status, detail): ok | warn | dead | unreachable."""
    for method in ("HEAD", "GET"):
        try:
            return ("ok", _request(url, method))
        except urllib.error.HTTPError as e:
            if e.code in REACHABLE_ERRORS:
                return ("ok", f"{e.code} (reachable, access-gated)")
            if e.code in DEAD_ERRORS:
                return ("dead", e.code)
            if e.code == 405 and method == "HEAD":
                continue  # server dislikes HEAD — retry as GET
            return ("warn", e.code)
        except (socket.timeout, TimeoutError):
            return ("warn", "timeout")
        except Exception as e:
            reason = getattr(e, "reason", e)
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

    failures = 0
    for url, (status, detail) in zip(urls, results):
        if status == "ok":
            print(f"OK: {url} ({detail})")
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
              "send back to synthesize under G2-URL")
        return 1
    print(f"OK: {len(urls)} URLs live")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
