"""Unattended resume runner for the matching step.

Repeatedly runs `migrate.py match`. When Spotify rate-limits us, match exits 75
and writes the retry-after; this supervisor sleeps exactly that long (no polling
that could extend the penalty), then resumes. Stops when a full pass completes.

Safe to Ctrl-C and re-run — all progress is saved in matches.json.
Run under caffeinate so the Mac doesn't sleep:
    caffeinate -i .venv/bin/python auto_match.py
"""
import subprocess
import sys
import time

import config

RETRY_FILE = config.DATA_DIR / "retry_after.txt"
BATCH = ["--max-new", "400"]  # checkpoint roughly every 400 new tracks


def _ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def main():
    attempt = 0
    while True:
        attempt += 1
        print(f"\n[{_ts()}] === match pass #{attempt} ===", flush=True)
        rc = subprocess.call([sys.executable, "migrate.py", "match", *BATCH])

        if rc == 0:
            # a pass ended without rate limit. Are we fully done?
            import json
            tracks = json.load(open(config.YANDEX_TRACKS, encoding="utf-8"))
            res = json.load(open(config.MATCHES_JSON, encoding="utf-8"))
            seen = {r["yandex"]["yandex_id"] for r in res}
            left = sum(1 for t in tracks if t["yandex_id"] not in seen)
            matched = sum(1 for r in res if r["spotify"])
            if left == 0:
                print(f"\n[{_ts()}] DONE — full pass complete. "
                      f"{matched}/{len(tracks)} matched.", flush=True)
                break
            print(f"[{_ts()}] batch checkpoint: {len(seen)}/{len(tracks)} processed, "
                  f"{matched} matched, {left} to go.", flush=True)
            time.sleep(2)
            continue

        if rc == 75:
            wait = 3700
            if RETRY_FILE.exists():
                try:
                    wait = int(RETRY_FILE.read_text().strip())
                except ValueError:
                    pass
            wait += 60  # buffer
            print(f"[{_ts()}] rate-limited; sleeping {wait}s (~{wait/3600:.1f}h) "
                  f"then resuming.", flush=True)
            time.sleep(wait)
            continue

        print(f"[{_ts()}] unexpected exit code {rc}; stopping.", flush=True)
        sys.exit(rc)


if __name__ == "__main__":
    main()
