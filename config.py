"""Central config: loads .env and exposes typed settings + a validator."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# Yandex
YANDEX_MUSIC_TOKEN = os.getenv("YANDEX_MUSIC_TOKEN", "").strip()
# Optional proxy for Yandex catalog calls, which are geo-blocked (HTTP 451)
# outside licensed regions (RU/BY/KZ + CIS). e.g. socks5://user:pass@host:1080
# or http://host:8080. Only the Yandex fetch routes through it.
YANDEX_PROXY = os.getenv("YANDEX_PROXY", "").strip()

# Spotify
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback").strip()
SPOTIFY_PLAYLIST_NAME = os.getenv("SPOTIFY_PLAYLIST_NAME", "Yandex Liked").strip()
SPOTIFY_PLAYLIST_PUBLIC = _bool("SPOTIFY_PLAYLIST_PUBLIC", False)
SPOTIFY_EXISTING_PLAYLIST = os.getenv("SPOTIFY_EXISTING_PLAYLIST", "").strip()
SPOTIFY_CACHE = str(ROOT / ".spotify_cache")
# Seconds between search requests. Rolling 30s window → a slow steady rate
# sustains; we burst at ~2-3/s and got banned, so default to ~1 req / 2s.
SPOTIFY_THROTTLE_S = float(os.getenv("SPOTIFY_THROTTLE_S", "2.0"))
# A 429 Retry-After above this many seconds is treated as a punitive ban
# (bubble up so the supervisor sleeps it); at/below, we wait it out inline.
SPOTIFY_BAN_THRESHOLD_S = float(os.getenv("SPOTIFY_BAN_THRESHOLD_S", "120"))

# Model fallback
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001").strip()
MODEL_FALLBACK = _bool("MODEL_FALLBACK", True) and bool(ANTHROPIC_API_KEY)

# Data files
YANDEX_TRACKS = DATA_DIR / "yandex_tracks.json"
MATCHES_JSON = DATA_DIR / "matches.json"
MATCHES_CSV = DATA_DIR / "matches.csv"
UNMATCHED_CSV = DATA_DIR / "unmatched.csv"
ADDED_JSON = DATA_DIR / "added.json"


def require(*names: str) -> None:
    """Raise a friendly error if any required env var is missing."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise SystemExit(
            "Missing required config: "
            + ", ".join(missing)
            + "\nCopy .env.example to .env and fill these in."
        )
