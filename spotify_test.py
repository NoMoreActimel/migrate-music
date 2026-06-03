"""One-time Spotify auth + a small matching quality check (no writes)."""
import json

import config
import matcher
import spotify_client as sc


def main():
    sp = sc.get_client()
    me = sp.current_user()
    print(f"SPOTIFY AUTH OK -> {me.get('display_name')} ({me['id']}) product={me.get('product')}")

    tracks = json.load(open(config.YANDEX_TRACKS, encoding="utf-8"))
    # evenly spread sample across the whole library for variety
    n = 25
    step = max(1, len(tracks) // n)
    sample = tracks[::step][:n]

    tiers = {}
    print(f"\nMatching {len(sample)} sampled tracks (of {len(tracks)}):\n")
    for t in sample:
        y = matcher.prepare_track(t)
        raw = sc.search_tracks(sp, y["title_v"]["raw"] or t["title"], t["artists"])
        cands = [matcher.prepare_track({
            "full_title": c["title"], "title": c["title"], "artists": c["artists"],
            "duration_ms": c.get("duration_ms"),
        }) | {"_orig": c} for c in raw]
        best = matcher.best_match(y, cands)

        ya = ", ".join(t["artists"]) or "(no artist)"
        if best:
            cand, (tier, score, _) = best
            s = cand["_orig"]
            tiers[tier] = tiers.get(tier, 0) + 1
            print(f"  T{tier} {score:>3}  {ya} — {t['full_title']}")
            print(f"         -> {', '.join(s['artists'])} — {s['title']}")
        else:
            tiers[0] = tiers.get(0, 0) + 1
            print(f"  MISS    {ya} — {t['full_title']}  ({len(raw)} candidates)")

    print("\n--- tier summary ---")
    matched = sum(v for k, v in tiers.items() if k)
    print(f"matched {matched}/{len(sample)}")
    for k in sorted(tiers):
        label = "MISS" if k == 0 else matcher.TIER_LABELS[k]
        print(f"  {('T'+str(k)) if k else '--'} {label:<18} {tiers[k]}")


if __name__ == "__main__":
    main()
