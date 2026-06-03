"""Spotify adapter — wraps the existing (frozen) spotify_client."""
from services.base import MusicService, make_track
import spotify_client as sc


def _to_track(t: dict) -> dict:
    return make_track(
        "spotify", t["id"], t.get("name"),
        [a["name"] for a in t.get("artists", [])],
        t.get("duration_ms"),
        (t.get("album") or {}).get("name"),
        (t.get("external_urls") or {}).get("spotify"),
    )


class SpotifyService(MusicService):
    name = "spotify"

    def __init__(self):
        self.sp = sc.get_client()

    def read_liked(self) -> list:
        out, offset = [], 0
        while True:
            page = self.sp.current_user_saved_tracks(limit=50, offset=offset)
            for it in page.get("items", []):
                t = it.get("track")
                if t and t.get("id"):
                    out.append(_to_track(t))
            if page.get("next"):
                offset += 50
            else:
                break
        return out

    def search(self, title, artists, limit=10) -> list:
        # sc.search_tracks already throttles + raises RateLimited on a ban
        raw = sc.search_tracks(self.sp, title, artists, limit)
        return [make_track("spotify", c["id"], c["title"], c["artists"],
                           c.get("duration_ms"), c.get("album"), c.get("url"))
                for c in raw]

    def get_or_create_playlist(self, name, public=False) -> str:
        uid = self.sp.current_user()["id"]
        offset = 0
        while True:
            page = self.sp.current_user_playlists(limit=50, offset=offset)
            for pl in page.get("items", []):
                if pl and pl["name"] == name and pl["owner"]["id"] == uid:
                    return pl["id"]
            if page.get("next"):
                offset += 50
            else:
                break
        pl = self.sp.user_playlist_create(uid, name, public=public,
                                          description="Migrated by migrate-music.")
        return pl["id"]

    def add_tracks(self, playlist_id, track_ids) -> int:
        uris = [i if str(i).startswith("spotify:") else f"spotify:track:{i}"
                for i in track_ids]
        return sc.add_tracks(self.sp, playlist_id, uris)
