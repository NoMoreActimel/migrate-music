"""Fetch liked tracks from Yandex Music into a plain list of dicts."""
import json
import os

import config


def _apply_proxy():
    """Route Yandex catalog calls through a licensed-region proxy if configured.

    Yandex Music's /tracks, /search, /likes endpoints return HTTP 451 outside
    licensed regions (RU/BY/KZ + CIS); a proxy in such a region bypasses it.
    requests (used by yandex-music) honors these env vars.
    """
    if config.YANDEX_PROXY:
        os.environ["HTTPS_PROXY"] = config.YANDEX_PROXY
        os.environ["HTTP_PROXY"] = config.YANDEX_PROXY
        print(f"Routing Yandex calls via proxy {config.YANDEX_PROXY.split('@')[-1]}")


def _track_to_dict(t) -> dict:
    version = getattr(t, "version", None)
    title = t.title or ""
    full_title = f"{title} ({version})" if version else title
    album = None
    if getattr(t, "albums", None):
        album = t.albums[0].title
    return {
        "yandex_id": str(t.id),
        "title": title,
        "version": version,
        "full_title": full_title,
        "artists": [a.name for a in (t.artists or []) if a.name],
        "duration_ms": getattr(t, "duration_ms", None),
        "album": album,
    }


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def fetch_liked() -> list:
    from yandex_music import Client

    config.require("YANDEX_MUSIC_TOKEN")
    _apply_proxy()
    client = Client(config.YANDEX_MUSIC_TOKEN).init()

    likes = client.users_likes_tracks()
    short = likes.tracks if likes else []
    ids = [t.track_id for t in short]
    print(f"Found {len(ids)} liked tracks; fetching details...")

    out = []
    for batch in _chunks(ids, 100):
        full = client.tracks(batch)
        for t in full:
            if t is not None:
                out.append(_track_to_dict(t))
        print(f"  fetched {len(out)}/{len(ids)}", end="\r")
    print()
    return out


def main():
    tracks = fetch_liked()
    config.YANDEX_TRACKS.write_text(
        json.dumps(tracks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Saved {len(tracks)} tracks -> {config.YANDEX_TRACKS}")


if __name__ == "__main__":
    main()
