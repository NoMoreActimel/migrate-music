"""Text normalization for cross-service song matching.

Two parallel representations are produced for every string:
  * norm     – unicode-normalized, lowercased, de-punctuated (keeps Cyrillic)
  * translit – the same but transliterated to Latin via unidecode

Comparing both lets us bridge Yandex (often Cyrillic) and Spotify (often Latin).
"""
import re
import unicodedata

from unidecode import unidecode

# "feat. X", "(featuring X)", "ft X", "with X" -> drop the trailing credit
_FEAT_RE = re.compile(
    r"\s*[\(\[]?\s*(feat\.?|featuring|ft\.?|with)\s+.*$", re.IGNORECASE
)

# bracketed qualifiers: (Remastered 2011), [Live], (Radio Edit), (Original Mix)...
_QUALIFIER_BRACKET_RE = re.compile(
    r"\s*[\(\[][^)\]]*\b("
    r"remaster|remastered|remix|mix|live|acoustic|version|edit|mono|stereo|"
    r"bonus|deluxe|instrumental|radio|extended|original|karaoke|cover|demo|"
    r"reprise|interlude|skit|explicit|clean|single)\b[^)\]]*[\)\]]",
    re.IGNORECASE,
)

# trailing dash qualifiers: " - 2011 Remaster", " - Live", " - Radio Edit"
_DASH_QUALIFIER_RE = re.compile(
    r"\s*-\s*[^-]*\b("
    r"remaster|remastered|remix|live|acoustic|version|edit|mono|stereo|"
    r"bonus|deluxe|instrumental|radio|extended|original|single)\b.*$",
    re.IGNORECASE,
)

# bracketed non-English / source annotations: (из фильма «…»), (Из "X"), (Демо),
# (prod. by …), (OST), (саундтрек), (минус), (кавер), (концерт)…
_ANNOTATION_RE = re.compile(
    r"\s*[\(\[][^)\]]*(?:"
    r"из\s+фильма|из\s+к/?ф|из\s+|саундтрек|\bost\b|prod\b|продюс|демо|\bdemo\b|"
    r"минус|кавер|концерт|живо|ремикс|версия|при\s+участии|feat|\bft\b"
    r")[^)\]]*[\)\]]",
    re.IGNORECASE,
)
# « » quoted film/source names anywhere in the string
_GUILLEMET_RE = re.compile(r"«[^»]*»")
# any bracketed group (aggressive — used only for the 'bare' recall variant)
_ANY_BRACKET_RE = re.compile(r"\s*[\(\[][^)\]]*[\)\]]")

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def basic_norm(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.lower()
    s = _PUNCT_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


def translit(s: str) -> str:
    return basic_norm(unidecode(s or ""))


def strip_feat(s: str) -> str:
    return _FEAT_RE.sub("", s or "").strip()


def strip_qualifiers(s: str) -> str:
    s = _QUALIFIER_BRACKET_RE.sub("", s or "")
    s = _ANNOTATION_RE.sub("", s)
    s = _GUILLEMET_RE.sub("", s)
    s = _DASH_QUALIFIER_RE.sub("", s)
    return s.strip()


def strip_all_brackets(s: str) -> str:
    return _ANY_BRACKET_RE.sub("", s or "").strip()


def _clean_artist(a: str) -> str:
    # drop nickname parentheticals: "Алексей Хвостенко (Хвост)" -> "Алексей Хвостенко"
    return _ANY_BRACKET_RE.sub("", a or "").strip()


def title_variants(title: str) -> dict:
    raw = title or ""
    core_src = strip_qualifiers(strip_feat(raw))
    bare_src = strip_all_brackets(strip_feat(raw))  # most aggressive, for recall
    return {
        "raw": raw,
        "norm": basic_norm(raw),
        "core": basic_norm(core_src),
        "translit": translit(core_src),
        "bare": basic_norm(bare_src),
        "bare_translit": translit(bare_src),
    }


def artist_variants(artists) -> dict:
    names = [_clean_artist(a) for a in (artists or []) if _clean_artist(a)]
    primary = names[0] if names else ""
    return {
        "names": names,
        "joined_norm": basic_norm(", ".join(names)),
        "joined_translit": translit(", ".join(names)),
        "primary_norm": basic_norm(primary),
        "primary_translit": translit(primary),
        "set_norm": {basic_norm(a) for a in names if basic_norm(a)},
        "set_translit": {translit(a) for a in names if translit(a)},
    }
