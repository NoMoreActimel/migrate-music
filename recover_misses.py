"""Recover unmatched tracks.

Re-search each miss with the improved queries + normalization. New rule matches
are written straight back into matches.json. Tracks that still don't rule-match
but DO have candidates are queued (with candidates) to data/model_queue.json for
a small-model (Haiku) adjudication pass. Resumable + rate-limit aware.
"""
import json
import sys

import config
import matcher
import spotify_client as sc

QUEUE = config.DATA_DIR / "model_queue.json"
DONE = config.DATA_DIR / "recovery_done.json"


def _load(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def main():
    r = json.loads(config.MATCHES_JSON.read_text(encoding="utf-8"))
    misses = [x for x in r if not x["spotify"]]
    done = set(_load(DONE, []))
    queue = _load(QUEUE, [])
    queued = {q["yandex_id"] for q in queue}

    sp = sc.get_client()
    recovered = processed = zero = 0

    def save():
        config.MATCHES_JSON.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        DONE.write_text(json.dumps(sorted(done)), encoding="utf-8")
        QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        for x in misses:
            t = x["yandex"]
            yid = t["yandex_id"]
            if yid in done:
                continue
            y = matcher.prepare_track(t)
            cands = sc.search_tracks(sp, t["full_title"] or t["title"], t["artists"], thorough=True)
            prepared = [matcher.prepare_track({
                "full_title": c["title"], "title": c["title"],
                "artists": c["artists"], "duration_ms": c.get("duration_ms"),
            }) | {"_orig": c} for c in cands]
            best = matcher.best_match(y, prepared)
            if best:
                cand, (tier, score, reason) = best
                x.update(spotify=cand["_orig"], tier=tier, confidence=score,
                         reason=reason + " (recovered)", n_candidates=len(cands))
                recovered += 1
            elif cands and yid not in queued:
                queue.append({"yandex_id": yid, "artists": t["artists"],
                              "title": t["full_title"], "album": t.get("album"),
                              "candidates": cands})
                queued.add(yid)
            elif not cands:
                zero += 1
            done.add(yid)
            processed += 1
            if processed % 20 == 0:
                save()
                print(f"  processed {processed}/{len(misses)} | "
                      f"rule-recovered {recovered} | queued {len(queue)}", end="\r")
    except sc.RateLimited as e:
        save()
        print(f"\nRate-limited (retry ~{e.retry_after}s). Re-run to continue. "
              f"processed {processed} this session.")
        sys.exit(75)

    save()
    print(f"\nDONE. rule-recovered {recovered} | queued-for-model {len(queue)} | "
          f"still-zero-candidates {zero}")
    print(f"queue -> {QUEUE}")


if __name__ == "__main__":
    main()
