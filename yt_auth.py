"""One-time YouTube Music auth from browser headers -> youtube_auth.json.

Robust to how modern DevTools copies headers. You can paste either:
  * classic  "name: value"  lines, OR
  * the new DevTools format with the name and value on SEPARATE lines, OR
  * honestly just the Cookie value on its own.

How to get them:
  1. Open https://music.youtube.com (logged in) -> DevTools -> Network -> filter
     "browse" -> reload -> click a POST to music.youtube.com.
  2. Copy its request headers (or just the Cookie value).
  3. Run:  python yt_auth.py   then paste, and press Ctrl-D.
"""
import hashlib
import re
import sys
import time

import config

WANT = {"cookie", "authorization", "user-agent", "x-goog-authuser",
        "x-goog-visitor-id", "origin"}
DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
ORIGIN = "https://music.youtube.com"


def parse_headers(blob: str) -> dict:
    headers, lines = {}, [l.rstrip() for l in blob.splitlines()]
    # 1) classic "name: value" (skip HTTP/2 pseudo-headers like :path)
    for line in lines:
        s = line.strip()
        if not s or s.startswith(":"):
            continue
        m = re.match(r"([A-Za-z][A-Za-z0-9-]*):\s+(.+)$", s)
        if m and m.group(1).lower() in WANT:
            headers.setdefault(m.group(1).lower(), m.group(2).strip())
    # 2) new DevTools format: a bare header name, value on the next line
    for i, line in enumerate(lines):
        name = line.strip().lower()
        if name in WANT and name not in headers and i + 1 < len(lines):
            val = lines[i + 1].strip()
            if val and val.lower() not in WANT:
                headers[name] = val
    # 3) last resort: sniff a raw Cookie string anywhere in the blob
    if "cookie" not in headers:
        m = re.search(r"((?:[^\s=;]+=[^\s;]*;\s*){2,}[^\s=;]+=[^\s;]*)", blob)
        if m and ("SID" in m.group(1) or "SAPISID" in m.group(1)):
            headers["cookie"] = m.group(1).strip()
    return headers


def _sapisidhash(cookie: str) -> str | None:
    m = re.search(r"(?:__Secure-3PAPISID|SAPISID)=([^;]+)", cookie)
    if not m:
        return None
    ts = int(time.time())
    digest = hashlib.sha1(f"{ts} {m.group(1)} {ORIGIN}".encode()).hexdigest()
    return f"SAPISIDHASH {ts}_{digest}"


def build_headers(blob: str) -> dict:
    h = parse_headers(blob)
    if "cookie" not in h:
        sys.exit("Could not find a Cookie in the pasted text. Paste the request "
                 "headers (or at least the Cookie value) from music.youtube.com.")
    h.setdefault("user-agent", DEFAULT_UA)
    h.setdefault("x-goog-authuser", "0")
    h.setdefault("origin", ORIGIN)
    h.setdefault("accept", "*/*")
    h.setdefault("accept-language", "en")
    h.setdefault("content-type", "application/json")
    # ytmusicapi 1.12 only treats this as BROWSER auth if an authorization header
    # with SAPISIDHASH is present; compute one from the cookie if it's missing.
    if "SAPISIDHASH" not in h.get("authorization", ""):
        ah = _sapisidhash(h["cookie"])
        if not ah:
            sys.exit("Cookie has no SAPISID/__Secure-3PAPISID — copy the full Cookie.")
        h["authorization"] = ah
    return h


def main():
    from ytmusicapi import setup, YTMusic

    print("Paste the request headers (or just the Cookie), then press Ctrl-D:")
    blob = sys.stdin.read()
    if not blob.strip():
        sys.exit("Nothing pasted.")
    headers = build_headers(blob)
    headers_raw = "\n".join(f"{k}: {v}" for k, v in headers.items())
    path = str(config.ROOT / "youtube_auth.json")
    setup(filepath=path, headers_raw=headers_raw)

    yt = YTMusic(path)
    liked = yt.get_liked_songs(limit=1)
    print(f"Auth OK -> youtube_auth.json  ({liked.get('trackCount')} liked songs visible)")


if __name__ == "__main__":
    main()
