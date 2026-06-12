"""Smoke test for YouTube Music: READ liked + SEARCH/WRITE via a Yandex sample.

Uses the cached data/yandex_tracks.json (no Yandex VPN needed) and creates a
small private YT playlist so you can eyeball the matches. Requires youtube_auth.json
(run `python yt_auth.py` first)."""
import json

import config
import matcher
from services.youtube import YouTubeMusicService

PLAYLIST = "yandex-to-yt test"
SAMPLE = 20


def main():
    yt = YouTubeMusicService()

    # ---- READ ----
    liked = yt.read_liked()
    print(f"READ  ok — {len(liked)} liked songs on YouTube Music. First 5:")
    for t in liked[:5]:
        print(f"   {', '.join(t['artists'])} — {t['title']}")

    # ---- SEARCH (migrate a spread sample of the cached Yandex likes) ----
    tracks = json.loads(config.YANDEX_TRACKS.read_text(encoding="utf-8"))
    step = max(1, len(tracks) // SAMPLE)
    sample = tracks[::step][:SAMPLE]
    matched = []
    for t in sample:
        y = matcher.prepare_track(t)
        cands = yt.search(t["full_title"] or t["title"], t["artists"])
        prep = [matcher.prepare_track({
            "full_title": c["title"], "title": c["title"],
            "artists": c["artists"], "duration_ms": c.get("duration_ms"),
        }) | {"_orig": c} for c in cands]
        best = matcher.best_match(y, prep)
        if best:
            matched.append((t, best[0]["_orig"], best[1]))

    print(f"\nSEARCH ok — matched {len(matched)}/{len(sample)} sampled Yandex tracks on YT:")
    for t, c, ev in matched[:10]:
        print(f"   T{ev[0]} {', '.join(t['artists'])} — {t['full_title']}")
        print(f"        -> {', '.join(c['artists'])} — {c['title']}")

    # ---- WRITE ----
    pid = yt.get_or_create_playlist(PLAYLIST, public=False)
    n = yt.add_tracks(pid, [c["id"] for _, c, _ in matched])
    print(f"\nWRITE ok — added {n} tracks to YT playlist '{PLAYLIST}' (id {pid})")
    print(f"   https://music.youtube.com/playlist?list={pid}")


if __name__ == "__main__":
    main()
