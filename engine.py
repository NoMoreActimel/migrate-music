"""Generic any->any migration engine.

read_liked(source) -> for each, search(target) -> tiered match -> (optional) add
to a target playlist. Resumable and rate-limit-aware, exactly like the Yandex->
Spotify `match` path, but parameterized by service.

State per direction: data/sync_<source>_to_<target>.json
On a punitive rate-limit it saves and exits 75 (so a supervisor can sleep+resume).
"""
import csv
import json
import sys

import config
import matcher
from services.base import RateLimited, get_service


def _state_file(source, target):
    return config.DATA_DIR / f"sync_{source}_to_{target}.json"


def _csv_file(source, target):
    return config.DATA_DIR / f"sync_{source}_to_{target}.csv"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path, results):
    rows = [r for r in results if r["match"]]
    rows.sort(key=lambda r: (r["tier"], -r["confidence"]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tier", "confidence", "reason", "src_artists", "src_title",
                    "tgt_artists", "tgt_title", "tgt_url"])
        for r in rows:
            s, m = r["source"], r["match"]
            w.writerow([r["tier"], r["confidence"], r["reason"],
                        ", ".join(s["artists"]), s["full_title"],
                        ", ".join(m["artists"]), m["full_title"], m.get("url")])


def migrate(source_name, target_name, playlist_name=None, public=False,
            max_new=0, commit=False, no_model=False, source_cache=None):
    tgt = get_service(target_name)
    src_name = source_name.lower()

    if source_cache:
        # read the source liked list from a cached fetch (e.g. data/yandex_tracks.json)
        # so we don't need live source access (handy when the source is geo-locked)
        from pathlib import Path
        from services.base import make_track
        p = Path(source_cache)
        if not p.is_absolute():
            p = config.ROOT / source_cache
        raw = json.loads(p.read_text(encoding="utf-8"))
        liked = [make_track(src_name, t.get("id") or t.get("yandex_id"), t.get("title"),
                            t.get("artists"), t.get("duration_ms"), t.get("album"),
                            version=t.get("version")) for t in raw]
        print(f"Loaded {len(liked)} tracks from cache '{source_cache}'; matching against {tgt.name}.")
    else:
        src = get_service(source_name)
        src_name = src.name
        print(f"Reading liked songs from {src_name}...")
        liked = src.read_liked()
        print(f"{len(liked)} liked on {src_name}; matching against {tgt.name}.")

    state = _state_file(src_name, tgt.name)
    prior = {r["src_id"]: r for r in (_load(state) or [])}

    use_model = config.MODEL_FALLBACK and not no_model
    results, new_this_run, rate_limited = [], 0, False

    for t in liked:
        sid = f"{src_name}:{t['id']}"
        if sid in prior:
            results.append(prior[sid])
            continue
        if max_new and new_this_run >= max_new:
            print(f"\nReached --max-new={max_new}; stopping this session.")
            break

        y = matcher.prepare_track(t)
        try:
            cands = tgt.search(t["full_title"] or t["title"], t["artists"])
        except RateLimited as e:
            _save(state, results)
            (config.DATA_DIR / "retry_after.txt").write_text(str(e.retry_after or 3700))
            print(f"\n{tgt.name} rate limit after {new_this_run} new. Progress saved.")
            print(f"Resume after ~{e.retry_after}s: migrate.py sync "
                  f"--source {src_name} --target {tgt.name}")
            rate_limited = True
            break

        prepared = [matcher.prepare_track(c) | {"_orig": c} for c in cands]
        rec = {"src_id": sid, "source": t, "match": None, "tier": None,
               "confidence": 0, "reason": "", "n_candidates": len(cands)}
        best = matcher.best_match(y, prepared)
        if best:
            cand, (tier, score, reason) = best
            rec.update(match=cand["_orig"], tier=tier, confidence=score, reason=reason)
        elif use_model and cands:
            import llm
            picked = llm.pick_match(t, cands)
            if picked:
                cand, conf = picked
                rec.update(match=cand, tier=5, confidence=conf, reason="model")

        results.append(rec)
        new_this_run += 1
        if new_this_run % 10 == 0:
            done = sum(1 for r in results if r["match"])
            print(f"  +{new_this_run} new | {done}/{len(results)} matched", end="\r")
        if new_this_run % 25 == 0:
            _save(state, results)
    print()

    _save(state, results)
    _write_csv(_csv_file(src_name, tgt.name), results)
    matched = [r for r in results if r["match"]]
    print(f"{len(matched)}/{len(results)} matched. CSV: {_csv_file(src_name, tgt.name)}")

    remaining = len(liked) - len(results)
    if commit and not remaining and not rate_limited:
        if not playlist_name:
            sys.exit("Pass --playlist NAME to add matches to a playlist.")
        ids = [r["match"]["id"] for r in matched]
        print(f"Adding {len(ids)} tracks to '{playlist_name}' on {tgt.name}...")
        pid = tgt.get_or_create_playlist(playlist_name, public=public)
        added = tgt.add_tracks(pid, ids)
        print(f"Added {added} new tracks (playlist {pid}).")
    elif commit and remaining:
        print(f"{remaining} tracks left to match — finish matching before --commit.")

    if rate_limited:
        sys.exit(75)
    return results
