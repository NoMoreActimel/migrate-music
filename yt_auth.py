"""One-time YouTube Music auth via browser headers -> youtube_auth.json.

How to get the headers:
  1. Open https://music.youtube.com in your browser, logged in.
  2. DevTools (Cmd+Opt+I) -> Network tab. Filter: /browse
  3. Click any POST request to music.youtube.com (e.g. .../youtubei/v1/browse).
  4. Right-click the request -> Copy -> Copy request headers
     (or copy the Request Headers block manually).
  5. Run:  python yt_auth.py   then paste, and press Ctrl-D (twice if needed).
"""
import sys

import config


def main():
    from ytmusicapi import setup

    print("Paste the request headers, then press Ctrl-D:")
    raw = sys.stdin.read().strip()
    if not raw:
        sys.exit("No headers pasted.")
    setup(filepath=str(config.ROOT / "youtube_auth.json"), headers_raw=raw)
    print(f"Saved {config.ROOT / 'youtube_auth.json'}")
    # smoke test
    from services.youtube import YouTubeMusicService
    yt = YouTubeMusicService()
    liked = yt.read_liked()
    print(f"Auth OK — {len(liked)} liked songs visible.")


if __name__ == "__main__":
    main()
