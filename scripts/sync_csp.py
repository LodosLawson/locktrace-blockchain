#!/usr/bin/env python3
"""
CSP Hash Synchronizer (F-07)
============================
Removes `'unsafe-inline'` and CDN allow-lists from `script-src`. Inline <script> blocks of
frontend/index.html are authorised by SHA-256 hash; inline event-handler *attributes* stay
allowed through `script-src-attr` only (injected <script> tags are blocked).

Run after ANY edit of frontend/index.html (fast_deploy.py does it automatically):
    python scripts/sync_csp.py          # rewrite CSP in nginx / netlify / server.py
    python scripts/sync_csp.py --check  # exit 1 if out of sync
"""
import base64
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEXES = ["frontend/index.html", "templates/index.html"]
TARGETS = ["deploy/nginx.conf", "deploy/nginx_ssl.conf", "frontend/netlify.toml", "server.py"]
EXTERNAL_SCRIPT_HOSTS = "https://cdn.tailwindcss.com"  # Tailwind Play CDN (no SRI possible; build step is the long-term fix)

INLINE_RE = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.S | re.I)


def inline_hashes(path):
    text = open(os.path.join(ROOT, path), encoding="utf-8", newline="").read().replace("\r\n", "\n")
    hashes = []
    for m in INLINE_RE.finditer(text):
        attrs = m.group("attrs")
        if re.search(r"\bsrc\s*=", attrs, re.I):
            continue
        t = re.search(r'type\s*=\s*"([^"]*)"', attrs, re.I)
        if t and t.group(1).strip().lower() not in ("", "text/javascript", "module", "application/javascript"):
            continue
        digest = base64.b64encode(hashlib.sha256(m.group("body").encode("utf-8")).digest()).decode()
        hashes.append(f"'sha256-{digest}'")
    return sorted(set(hashes))


def build_directive(hashes):
    return "script-src 'self' " + " ".join(hashes) + f" {EXTERNAL_SCRIPT_HOSTS}; script-src-attr 'unsafe-inline';"


def main():
    check = "--check" in sys.argv
    hs = [inline_hashes(p) for p in INDEXES]
    if hs[0] != hs[1]:
        print("[!] frontend/index.html and templates/index.html inline scripts differ")
        return 1
    directive = build_directive(hs[0])
    stale = False
    for rel in TARGETS:
        path = os.path.join(ROOT, rel)
        raw = open(path, encoding="utf-8", newline="").read()
        s = raw.replace(" script-src-attr 'unsafe-inline';", "")
        new, n = re.subn(r"script-src\s[^;\"]*;", lambda _m: directive, s)
        if n == 0:
            print(f"[!] no script-src found in {rel}")
            return 1
        if new != raw:
            stale = True
            if not check:
                open(path, "w", encoding="utf-8", newline="").write(new)
                print(f"[+] updated {rel} ({n} policy block(s))")
            else:
                print(f"[!] out of sync: {rel}")
    if check:
        return 1 if stale else 0
    print(f"[SUCCESS] {len(hs[0])} inline script hash(es) pinned; unsafe-inline removed from script-src.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

