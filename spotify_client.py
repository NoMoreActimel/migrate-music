"""Spotify auth, search, and playlist writes.

Search uses raw HTTP (so we can read the real `Retry-After` header, which
spotipy hides); auth and playlist writes use spotipy.
"""
import time

import requests

import config


class RateLimited(Exception):
    """Raised on a punitive 429 (long Retry-After) so callers can stop+resume."""

    def __init__(self, retry_after):
        try:
            self.retry_after = int(float(retry_after))
        except (TypeError, ValueError):
            self.retry_after = None
        super().__init__(f"Spotify rate limit; retry after {self.retry_after}s")


# Self-imposed throttle (see config) so we stay under the rolling-window limit.
THROTTLE_S = config.SPOTIFY_THROTTLE_S
_last_call = [0.0]
_session = requests.Session()


def _throttle():
    dt = time.time() - _last_call[0]
    if dt < THROTTLE_S:
        time.sleep(THROTTLE_S - dt)
    _last_call[0] = time.time()


def get_client():
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth

    config.require("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET")
    scope = "playlist-modify-private playlist-modify-public playlist-read-private"
    auth = SpotifyOAuth(
        client_id=config.SPOTIFY_CLIENT_ID,
        client_secret=config.SPOTIFY_CLIENT_SECRET,
        redirect_uri=config.SPOTIFY_REDIRECT_URI,
        scope=scope,
        cache_path=config.SPOTIFY_CACHE,
        open_browser=True,
    )
    # retries=0: do NOT auto-retry on 429 (that escalates the penalty)
    return spotipy.Spotify(auth_manager=auth, requests_timeout=30, retries=0)


def _track_dict(it: dict) -> dict:
    return {
        "id": it["id"],
        "uri": it["uri"],
        "title": it["name"],
        "artists": [a["name"] for a in it["artists"]],
        "duration_ms": it.get("duration_ms"),
        "album": (it.get("album") or {}).get("name"),
        "url": (it.get("external_urls") or {}).get("spotify"),
    }


def _search_once(sp, q: str, limit: int) -> dict:
    """One search request with throttle + inline backoff.

    Short 429s (rolling-window) are waited out here; a long Retry-After (a
    punitive ban) is raised as RateLimited for the supervisor to sleep.
    """
    for _ in range(5):
        _throttle()
        token = sp.auth_manager.get_access_token(as_dict=False)
        r = _session.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": q, "type": "track", "limit": limit},
            timeout=30,
        )
        if r.status_code == 429:
            ra = float(r.headers.get("Retry-After", "0") or 0)
            if ra > config.SPOTIFY_BAN_THRESHOLD_S:
                raise RateLimited(ra)
            time.sleep(ra + 1)  # rolling-window blip: wait it out and retry
            continue
        r.raise_for_status()
        return r.json()
    raise RateLimited(config.SPOTIFY_BAN_THRESHOLD_S)  # stuck on short 429s


def search_tracks(sp, title: str, artists, limit: int = 10) -> list:
    """Try a few query shapes; return de-duplicated candidate dicts.

    Propagates RateLimited (punitive ban). Other transient errors yield no
    candidates for that query (the track becomes a miss and is retried later).
    """
    primary = artists[0] if artists else ""
    queries = []
    if title and primary:
        queries.append(f'track:"{title}" artist:"{primary}"')
        queries.append(f"{primary} {title}")
    if title:
        queries.append(title)

    seen = {}
    for q in queries:
        try:
            res = _search_once(sp, q, limit)
        except RateLimited:
            raise
        except Exception:
            continue
        for it in res.get("tracks", {}).get("items", []):
            if it and it["id"] not in seen:
                seen[it["id"]] = _track_dict(it)
        if seen:  # first query that yields anything wins; later ones are fallbacks
            break
    return list(seen.values())


def _find_playlist_by_name(sp, user_id: str, name: str):
    offset = 0
    while True:
        page = sp.current_user_playlists(limit=50, offset=offset)
        for pl in page.get("items", []):
            if pl and pl["name"] == name and pl["owner"]["id"] == user_id:
                return pl["id"]
        if page.get("next"):
            offset += 50
        else:
            return None


def get_or_create_playlist(sp) -> str:
    if config.SPOTIFY_EXISTING_PLAYLIST:
        pid = config.SPOTIFY_EXISTING_PLAYLIST
        # accept full URL or spotify:playlist:ID too
        if "playlist" in pid:
            pid = pid.rstrip("/").split("playlist")[-1].lstrip(":/")
            pid = pid.split("?")[0]
        return pid

    user_id = sp.current_user()["id"]
    existing = _find_playlist_by_name(sp, user_id, config.SPOTIFY_PLAYLIST_NAME)
    if existing:
        print(f"Using existing playlist '{config.SPOTIFY_PLAYLIST_NAME}' ({existing})")
        return existing

    pl = sp.user_playlist_create(
        user_id,
        config.SPOTIFY_PLAYLIST_NAME,
        public=config.SPOTIFY_PLAYLIST_PUBLIC,
        description="Imported from Yandex Music liked songs.",
    )
    print(f"Created playlist '{config.SPOTIFY_PLAYLIST_NAME}' ({pl['id']})")
    return pl["id"]


def existing_uris(sp, playlist_id: str) -> set:
    uris, offset = set(), 0
    while True:
        page = sp.playlist_items(
            playlist_id, fields="items(track(uri)),next", limit=100, offset=offset
        )
        items = page.get("items", [])
        for it in items:
            tr = it.get("track")
            if tr and tr.get("uri"):
                uris.add(tr["uri"])
        if page.get("next"):
            offset += 100
        else:
            break
    return uris


def add_tracks(sp, playlist_id: str, uris) -> int:
    present = existing_uris(sp, playlist_id)
    to_add = [u for u in dict.fromkeys(uris) if u not in present]
    for i in range(0, len(to_add), 100):
        sp.playlist_add_items(playlist_id, to_add[i : i + 100])
    return len(to_add)
