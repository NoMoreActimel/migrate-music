"""YouTube Music adapter (ytmusicapi, browser-header auth)."""
import os
import time

import config
from services.base import MusicService, make_track

YT_AUTH = str(config.ROOT / "youtube_auth.json")
_last = [0.0]
_THROTTLE = 0.3


def _throttle():
    dt = time.time() - _last[0]
    if dt < _THROTTLE:
        time.sleep(_THROTTLE - dt)
    _last[0] = time.time()


def _to_track(t: dict) -> dict:
    dur = t.get("duration_seconds")
    artists = [a["name"] for a in (t.get("artists") or []) if a.get("name")]
    album = t.get("album")
    album = album.get("name") if isinstance(album, dict) else None
    return make_track("youtube", t.get("videoId"), t.get("title"), artists,
                      dur * 1000 if dur else None, album)


class YouTubeMusicService(MusicService):
    name = "youtube"

    def __init__(self):
        from ytmusicapi import YTMusic

        if not os.path.exists(YT_AUTH):
            raise SystemExit(
                "No youtube_auth.json. Set it up once:\n"
                "  python yt_auth.py   (paste request headers from music.youtube.com)")
        self.yt = YTMusic(YT_AUTH)

    def read_liked(self) -> list:
        _throttle()
        data = self.yt.get_liked_songs(limit=10000)
        return [_to_track(t) for t in data.get("tracks", []) if t.get("videoId")]

    def search(self, title, artists, limit=10) -> list:
        _throttle()
        q = " ".join(x for x in [(artists[0] if artists else ""), title] if x).strip()
        res = self.yt.search(q, filter="songs", limit=limit)
        return [_to_track(t) for t in res[:limit] if t.get("videoId")]

    def get_or_create_playlist(self, name, public=False) -> str:
        for pl in self.yt.get_library_playlists(limit=200):
            if pl.get("title") == name:
                return pl["playlistId"]
        return self.yt.create_playlist(
            name, "Migrated by migrate-music",
            privacy_status="PUBLIC" if public else "PRIVATE")

    def add_tracks(self, playlist_id, track_ids) -> int:
        ids = list(dict.fromkeys(track_ids))
        if not ids:
            return 0
        self.yt.add_playlist_items(playlist_id, ids, duplicates=False)
        return len(ids)
