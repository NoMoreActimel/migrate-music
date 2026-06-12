"""Tiered matching between a Yandex track and Spotify candidates.

Tiers (lower = more confident):
  1  normalized exact      title + full artist set identical (norm or translit)
  2  normalized loose       core title identical + at least one artist overlaps
  3  small discrepancies    high fuzzy title & artist (+ duration sanity)
  4  priority rules         ordered heuristics that accept weaker evidence
  5  model fallback         resolved by the small LLM (assigned in migrate.py)

A candidate's variants are computed lazily and cached on the dict.
"""
from rapidfuzz import fuzz

import normalize as N

TIER_LABELS = {
    1: "exact-normalized",
    2: "normalized-loose",
    3: "small-discrepancy",
    4: "priority-rule",
    5: "model",
}


def prepare_track(t: dict) -> dict:
    t = dict(t)
    t["title_v"] = N.title_variants(t.get("full_title") or t.get("title"))
    t["artist_v"] = N.artist_variants(t.get("artists"))
    return t


def _artist_overlap(a: set, b: set) -> bool:
    return bool(a and b and (a & b))


def _artist_score(ya: dict, ca: dict) -> int:
    scores = [
        fuzz.token_set_ratio(ya["joined_translit"], ca["joined_translit"]),
        fuzz.ratio(ya["primary_translit"], ca["primary_translit"]),
    ]
    if ya["joined_norm"] and ca["joined_norm"]:
        scores.append(fuzz.token_set_ratio(ya["joined_norm"], ca["joined_norm"]))
    return max(scores) if scores else 0


def _title_score(yt: dict, ct: dict) -> int:
    return max(
        fuzz.ratio(yt["core"], ct["core"]),
        fuzz.ratio(yt["translit"], ct["translit"]),
        fuzz.ratio(yt.get("bare", ""), ct.get("bare", "")),
        fuzz.ratio(yt.get("bare_translit", ""), ct.get("bare_translit", "")),
    )


def _duration_ok(y: dict, c: dict) -> bool:
    yd, cd = y.get("duration_ms"), c.get("duration_ms")
    if not yd or not cd:
        return True  # unknown -> don't penalize
    return abs(yd - cd) <= 7000


def evaluate(y: dict, c: dict):
    """Return (tier, score, reason) for one candidate, or None."""
    yt, ya = y["title_v"], y["artist_v"]
    ct, ca = c["title_v"], c["artist_v"]

    # Tier 1 — exact normalized / transliterated
    if yt["norm"] and yt["norm"] == ct["norm"] and ya["set_norm"] and ya["set_norm"] == ca["set_norm"]:
        return (1, 100, "exact-normalized")
    if yt["translit"] and yt["translit"] == ct["translit"] and ya["set_translit"] and ya["set_translit"] == ca["set_translit"]:
        return (1, 99, "exact-translit")

    # Tier 2 — core title identical + artist overlap
    if yt["core"] and yt["core"] == ct["core"] and _artist_overlap(ya["set_norm"], ca["set_norm"]):
        return (2, 95, "core-title + artist-overlap")
    if yt["translit"] and yt["translit"] == ct["translit"] and _artist_overlap(ya["set_translit"], ca["set_translit"]):
        return (2, 93, "translit-title + artist-overlap")
    if yt.get("bare") and yt["bare"] == ct.get("bare") and _artist_overlap(ya["set_norm"], ca["set_norm"]):
        return (2, 92, "bare-title + artist-overlap")

    tscore = _title_score(yt, ct)
    ascore = _artist_score(ya, ca)
    dur_ok = _duration_ok(y, c)

    # Tier 3 — small discrepancies
    if tscore >= 90 and ascore >= 85 and dur_ok:
        return (3, min(92, (tscore + ascore) // 2), f"fuzzy t={tscore} a={ascore}")

    # Tier 4 — priority rules (ordered)
    if tscore >= 95 and ascore >= 70:
        return (4, 86, f"rule:strong-title t={tscore} a={ascore}")
    if ascore >= 92 and tscore >= 80:
        return (4, 83, f"rule:strong-artist t={tscore} a={ascore}")
    combo = fuzz.token_sort_ratio(
        f"{ya['joined_translit']} {yt['translit']}",
        f"{ca['joined_translit']} {ct['translit']}",
    )
    if combo >= 90 and dur_ok:
        return (4, 80, f"rule:combo={combo}")

    return None


def best_match(y: dict, candidates: list):
    """Pick the best-tier, then best-score candidate. Returns (cand, eval) or None."""
    best = None
    for c in candidates:
        ev = evaluate(y, c)
        if ev is None:
            continue
        if best is None or (ev[0], -ev[1]) < (best[1][0], -best[1][1]):
            best = (c, ev)
    return best
