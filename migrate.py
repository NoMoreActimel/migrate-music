#!/usr/bin/env python3
"""End-to-end Yandex → Spotify migration.

Commands:
  fetch   pull liked tracks from Yandex Music     -> data/yandex_tracks.json
  match   match each track to Spotify (rules+model) -> data/matches.json + CSVs
  add     create/use playlist and add matched tracks (review-gated)
  stats   summarize current match results

Typical flow:
  python migrate.py fetch
  python migrate.py match
  # review data/matches.csv and data/unmatched.csv
  python migrate.py add            # dry run first
  python migrate.py add --commit   # actually write to Spotify
"""
import argparse
import csv
import json
import sys

import config
import matcher
import spotify_client as sc


# ── IO helpers ──────────────────────────────────────────────────────────────
def _load(path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


# ── fetch ─────────────────────────────────────────────────────────────────--
def cmd_fetch(_args):
    import yandex_fetch

    yandex_fetch.main()


# ── match ───────────────────────────────────────────────────────────────────
def _write_match_csvs(results):
    matched = [r for r in results if r["spotify"]]
    unmatched = [r for r in results if not r["spotify"]]

    matched.sort(key=lambda r: (r["tier"], -r["confidence"]))
    with open(config.MATCHES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["tier", "tier_label", "confidence", "reason",
             "yandex_artists", "yandex_title",
             "spotify_artists", "spotify_title", "spotify_url"]
        )
        for r in matched:
            s = r["spotify"]
            w.writerow([
                r["tier"], matcher.TIER_LABELS.get(r["tier"], "?"),
                r["confidence"], r["reason"],
                ", ".join(r["yandex"]["artists"]), r["yandex"]["full_title"],
                ", ".join(s["artists"]), s["title"], s["url"],
            ])

    with open(config.UNMATCHED_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["yandex_artists", "yandex_title", "yandex_album", "n_candidates"])
        for r in unmatched:
            y = r["yandex"]
            w.writerow([", ".join(y["artists"]), y["full_title"], y.get("album"),
                        r.get("n_candidates", 0)])


def cmd_match(args):
    tracks = _load(config.YANDEX_TRACKS)
    if tracks is None:
        sys.exit("No data/yandex_tracks.json — run `python migrate.py fetch` first.")

    # resume: skip every track already attempted (matched OR miss) so we never
    # waste rate-limited requests re-searching. --retry-misses drops misses from
    # the cache to re-attempt them (e.g. a later pass with the model fallback);
    # --rematch starts completely fresh.
    prior_recs = _load(config.MATCHES_JSON) or []
    if args.rematch:
        prior = {}
    elif args.retry_misses:
        prior = {r["yandex"]["yandex_id"]: r for r in prior_recs if r["spotify"]}
    else:
        prior = {r["yandex"]["yandex_id"]: r for r in prior_recs}

    sp = sc.get_client()
    use_model = config.MODEL_FALLBACK and not args.no_model
    if config.MODEL_FALLBACK and args.no_model:
        print("Model fallback disabled for this run (--no-model).")
    elif not config.MODEL_FALLBACK:
        print("Model fallback off (no ANTHROPIC_API_KEY / MODEL_FALLBACK=false).")

    results = []
    n = len(tracks)
    new_this_run = 0
    rate_limited = False
    for i, t in enumerate(tracks, 1):
        yid = t["yandex_id"]
        if yid in prior:
            results.append(prior[yid])
            continue
        if args.max_new and new_this_run >= args.max_new:
            print(f"\nReached --max-new={args.max_new} for this session; stopping.")
            break

        y = matcher.prepare_track(t)
        try:
            raw_cands = sc.search_tracks(sp, y["title_v"]["raw"] or t["title"], t["artists"])
        except sc.RateLimited as e:
            _save(config.MATCHES_JSON, results)
            wait = e.retry_after or 3700
            (config.DATA_DIR / "retry_after.txt").write_text(str(wait))
            print(f"\n\nSpotify rate limit hit after {new_this_run} new track(s) this run. "
                  f"Progress saved ({sum(1 for r in results if r['spotify'])} matched).")
            print(f"Resume after ~{wait}s (~{wait/3600:.1f}h): python migrate.py match")
            rate_limited = True
            break

        cands = [matcher.prepare_track({
            "full_title": c["title"], "title": c["title"], "artists": c["artists"],
            "duration_ms": c.get("duration_ms"),
        }) | {"_orig": c} for c in raw_cands]

        rec = {"yandex": t, "spotify": None, "tier": None,
               "confidence": 0, "reason": "", "n_candidates": len(cands)}

        best = matcher.best_match(y, cands)
        if best:
            cand, (tier, score, reason) = best
            rec.update(spotify=cand["_orig"], tier=tier, confidence=score, reason=reason)
        elif use_model and raw_cands:
            import llm
            picked = llm.pick_match(t, raw_cands)
            if picked:
                cand, conf = picked
                rec.update(spotify=cand, tier=5, confidence=conf, reason="model")

        results.append(rec)
        new_this_run += 1
        if new_this_run % 10 == 0:
            done = sum(1 for r in results if r["spotify"])
            print(f"  +{new_this_run} new this run | {done}/{len(results)} matched", end="\r")
        if new_this_run % 25 == 0:
            _save(config.MATCHES_JSON, results)
    print()

    _save(config.MATCHES_JSON, results)
    _write_match_csvs(results)
    _print_stats(results)
    remaining = n - len(results)
    if remaining and not rate_limited:
        print(f"\n{remaining} tracks not yet processed this session.")
    if remaining:
        print("Run `python migrate.py match` again to continue (resumes automatically).")
    else:
        rl = config.DATA_DIR / "retry_after.txt"
        rl.unlink(missing_ok=True)
        print(f"\nReview: {config.MATCHES_CSV}\n        {config.UNMATCHED_CSV}")
        print("Then:   python migrate.py add          (dry run)")
        print("        python migrate.py add --commit (write to Spotify)")
    # exit 75 (EX_TEMPFAIL) on rate limit so a supervisor can wait + retry
    if rate_limited:
        sys.exit(75)


# ── add ───────────────────────────────────────────────────────────────────--
def cmd_add(args):
    results = _load(config.MATCHES_JSON)
    if results is None:
        sys.exit("No data/matches.json — run `python migrate.py match` first.")

    selected = [
        r for r in results
        if r["spotify"]
        and r["tier"] <= args.max_tier
        and r["confidence"] >= args.min_confidence
    ]
    uris = [r["spotify"]["uri"] for r in selected]

    by_tier = {}
    for r in selected:
        by_tier[r["tier"]] = by_tier.get(r["tier"], 0) + 1
    print(f"Selected {len(uris)} tracks "
          f"(max_tier={args.max_tier}, min_confidence={args.min_confidence})")
    for t in sorted(by_tier):
        print(f"  tier {t} ({matcher.TIER_LABELS.get(t)}): {by_tier[t]}")

    if not args.commit:
        print("\nDry run — nothing written. Re-run with --commit to add to Spotify.")
        return

    sp = sc.get_client()
    playlist_id = sc.get_or_create_playlist(sp)
    added = sc.add_tracks(sp, playlist_id, uris)
    _save(config.ADDED_JSON, {"playlist_id": playlist_id,
                              "selected": len(uris), "newly_added": added})
    print(f"Added {added} new tracks to playlist {playlist_id} "
          f"({len(uris) - added} were already present).")


# ── stats ─────────────────────────────────────────────────────────────────--
def _print_stats(results):
    total = len(results)
    matched = [r for r in results if r["spotify"]]
    print(f"\n{len(matched)}/{total} matched ({total - len(matched)} unmatched)")
    for t in range(1, 6):
        n = sum(1 for r in matched if r["tier"] == t)
        if n:
            print(f"  tier {t} {matcher.TIER_LABELS[t]:<18} {n}")


def cmd_stats(_args):
    results = _load(config.MATCHES_JSON)
    if results is None:
        sys.exit("No data/matches.json yet.")
    _print_stats(results)


# ── sync (generic any->any) ────────────────────────────────────────────────--
def cmd_sync(args):
    # lazy import so the frozen fetch/match/add path never depends on it
    import engine
    engine.migrate(args.source, args.target, playlist_name=args.playlist,
                   public=args.public, max_new=args.max_new,
                   commit=args.commit, no_model=args.no_model)


# ── CLI ─────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("fetch", help="fetch liked tracks from Yandex Music")

    pm = sub.add_parser("match", help="match tracks to Spotify")
    pm.add_argument("--rematch", action="store_true", help="ignore prior results, start fresh")
    pm.add_argument("--retry-misses", action="store_true", help="re-attempt previously-unmatched tracks")
    pm.add_argument("--no-model", action="store_true", help="skip the model fallback this run")
    pm.add_argument("--max-new", type=int, default=0, help="process at most N new tracks this session (0=all)")

    pa = sub.add_parser("add", help="add matched tracks to the Spotify playlist")
    pa.add_argument("--commit", action="store_true", help="actually write (default is dry run)")
    pa.add_argument("--max-tier", type=int, default=5, help="only add tiers <= this (default 5=all)")
    pa.add_argument("--min-confidence", type=int, default=0, help="only add confidence >= this")

    sub.add_parser("stats", help="summarize match results")

    ps = sub.add_parser("sync", help="generic migrate between any two services")
    ps.add_argument("--source", required=True, help="yandex | spotify | youtube")
    ps.add_argument("--target", required=True, help="yandex | spotify | youtube")
    ps.add_argument("--playlist", help="target playlist name (required with --commit)")
    ps.add_argument("--public", action="store_true", help="make created playlist public")
    ps.add_argument("--commit", action="store_true", help="add matches to the target playlist")
    ps.add_argument("--no-model", action="store_true", help="skip the model fallback this run")
    ps.add_argument("--max-new", type=int, default=0, help="process at most N new tracks this session")

    args = p.parse_args()
    {"fetch": cmd_fetch, "match": cmd_match, "add": cmd_add,
     "stats": cmd_stats, "sync": cmd_sync}[args.cmd](args)


if __name__ == "__main__":
    main()
