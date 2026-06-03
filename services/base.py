"""Unified music-service interface + normalized Track shape.

A Track is a plain dict so it plugs straight into matcher.prepare_track:
  service, id, title, full_title, artists (list[str]), duration_ms, album, url

`id` is whatever that service needs to add the track to a playlist (Spotify
base-62 id, YouTube videoId, Yandex "track:album"). Each adapter parses its own.

RateLimited is re-exported from spotify_client (the canonical definition) so the
engine can catch one exception type across all services. We deliberately do NOT
import this from spotify_client *into* spotify_client — no import cycle.
"""
from abc import ABC, abstractmethod

from spotify_client import RateLimited  # noqa: F401  (re-exported)


def make_track(service, id, title, artists, duration_ms=None, album=None,
               url=None, version=None):
    title = title or ""
    full = f"{title} ({version})" if version else title
    return {
        "service": service,
        "id": str(id) if id is not None else None,
        "title": title,
        "full_title": full,
        "artists": [a for a in (artists or []) if a],
        "duration_ms": duration_ms,
        "album": album,
        "url": url,
    }


class MusicService(ABC):
    name = "base"
    can_write = True

    @abstractmethod
    def read_liked(self) -> list:
        """Return the user's liked/saved songs as normalized Tracks."""

    @abstractmethod
    def search(self, title: str, artists, limit: int = 10) -> list:
        """Return candidate Tracks for a title + artists query."""

    @abstractmethod
    def get_or_create_playlist(self, name: str, public: bool = False) -> str:
        """Return the id of an existing playlist with this name, or create it."""

    @abstractmethod
    def add_tracks(self, playlist_id: str, track_ids) -> int:
        """Add tracks (by this service's ids); return count newly added."""


_ALIASES = {
    "spotify": "spotify", "sp": "spotify",
    "yandex": "yandex", "ya": "yandex", "yandexmusic": "yandex",
    "youtube": "youtube", "yt": "youtube", "ytmusic": "youtube",
    "youtubemusic": "youtube",
}


def get_service(name: str) -> MusicService:
    key = _ALIASES.get(name.lower().strip())
    if key == "spotify":
        from services.spotify import SpotifyService
        return SpotifyService()
    if key == "yandex":
        from services.yandex import YandexService
        return YandexService()
    if key == "youtube":
        from services.youtube import YouTubeMusicService
        return YouTubeMusicService()
    raise SystemExit(f"Unknown service '{name}'. Use: yandex | spotify | youtube")
