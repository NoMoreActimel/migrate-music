"""Yandex Music adapter (yandex-music). Read + search are solid; write is
best-effort (Yandex needs track_id + album_id, encoded here as "track:album")."""
import time

import config
from services.base import MusicService, make_track

_last = [0.0]
_THROTTLE = 0.3


def _throttle():
    dt = time.time() - _last[0]
    if dt < _THROTTLE:
        time.sleep(_THROTTLE - dt)
    _last[0] = time.time()


def _track_id(t) -> str:
    album = t.albums[0].id if getattr(t, "albums", None) else ""
    return f"{t.id}:{album}" if album else str(t.id)


def _to_track(t) -> dict:
    return make_track(
        "yandex", _track_id(t), t.title,
        [a.name for a in (t.artists or []) if a.name],
        getattr(t, "duration_ms", None),
        t.albums[0].title if getattr(t, "albums", None) else None,
        version=getattr(t, "version", None),
    )


class YandexService(MusicService):
    name = "yandex"

    def __init__(self):
        from yandex_music import Client
        import yandex_fetch

        config.require("YANDEX_MUSIC_TOKEN")
        yandex_fetch._apply_proxy()  # geo proxy if configured
        self.client = Client(config.YANDEX_MUSIC_TOKEN).init()

    def read_liked(self) -> list:
        import yandex_fetch
        # reuse the proven fetch (handles batching), then normalize
        return [make_track("yandex",
                           f"{t['yandex_id']}",
                           t["title"], t["artists"], t.get("duration_ms"),
                           t.get("album"), version=t.get("version"))
                for t in yandex_fetch.fetch_liked()]

    def search(self, title, artists, limit=10) -> list:
        _throttle()
        q = " ".join(x for x in [(artists[0] if artists else ""), title] if x).strip()
        res = self.client.search(q, type_="track")
        out = []
        if res and res.tracks:
            for t in res.tracks.results[:limit]:
                out.append(_to_track(t))
        return out

    def get_or_create_playlist(self, name, public=False) -> str:
        for pl in self.client.users_playlists_list():
            if pl.title == name:
                return str(pl.kind)
        pl = self.client.users_playlists_create(
            name, visibility="public" if public else "private")
        return str(pl.kind)

    def add_tracks(self, playlist_id, track_ids) -> int:
        kind = int(playlist_id)
        added = 0
        for tid in track_ids:
            parts = str(tid).split(":")
            if len(parts) != 2 or not parts[1]:
                continue  # need both track and album id to insert
            track_id, album_id = int(parts[0]), int(parts[1])
            try:
                pl = self.client.users_playlists(kind)
                self.client.users_playlists_insert_track(
                    kind, track_id, album_id, revision=pl.revision)
                added += 1
            except Exception:
                pass
        return added
