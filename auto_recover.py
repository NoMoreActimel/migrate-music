"""Unattended supervisor for the thorough miss-recovery.

Runs recover_misses.py; on a rate-limit ban (exit 75) it sleeps the real
Retry-After then resumes, until recovery completes (exit 0). Small job — should
finish in one window once the ban clears.
"""
import subprocess
import sys
import time

import config

RETRY_FILE = config.DATA_DIR / "retry_after.txt"


def _ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def main():
    while True:
        print(f"\n[{_ts()}] === recover pass ===", flush=True)
        rc = subprocess.call([sys.executable, "recover_misses.py"])
        if rc == 0:
            print(f"[{_ts()}] recovery complete.", flush=True)
            break
        if rc == 75:
            wait = 3700
            if RETRY_FILE.exists():
                try:
                    wait = int(RETRY_FILE.read_text().strip()) + 60
                except ValueError:
                    pass
            print(f"[{_ts()}] rate-limited; sleeping {wait}s (~{wait/3600:.1f}h).", flush=True)
            time.sleep(wait)
            continue
        print(f"[{_ts()}] unexpected exit {rc}; stopping.", flush=True)
        sys.exit(rc)


if __name__ == "__main__":
    main()
