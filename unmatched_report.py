"""Report the still-unmatched tracks with their candidates + matcher scores,
so a human can spot any the rules/model were too strict on.
-> data/unmatched_candidates.html (+ console sample)."""
import html
import json

import config
import matcher


def esc(s):
    return html.escape("" if s is None else str(s))


def main():
    r = json.loads(config.MATCHES_JSON.read_text(encoding="utf-8"))
    queue = {x["yandex_id"]: x for x in json.loads((config.DATA_DIR / "model_queue.json").read_text(encoding="utf-8"))}
    unmatched = [x for x in r if not x["spotify"]]

    rows = []  # (best_title_score, yandex_track, [(cand, tscore, ascore, durdelta, tier)])
    for x in unmatched:
        t = x["yandex"]
        q = queue.get(t["yandex_id"])
        cands = q["candidates"] if q else []
        y = matcher.prepare_track(t)
        scored = []
        for c in cands:
            cp = matcher.prepare_track({"full_title": c["title"], "title": c["title"],
                                        "artists": c["artists"], "duration_ms": c.get("duration_ms")})
            ts = matcher._title_score(y["title_v"], cp["title_v"])
            asc = matcher._artist_score(y["artist_v"], cp["artist_v"])
            dd = None
            if t.get("duration_ms") and c.get("duration_ms"):
                dd = round((c["duration_ms"] - t["duration_ms"]) / 1000)
            ev = matcher.evaluate(y, cp)
            scored.append((c, ts, asc, dd, ev[0] if ev else None))
        scored.sort(key=lambda z: -z[1])
        best = scored[0][1] if scored else 0
        rows.append((best, t, scored))
    rows.sort(key=lambda z: -z[0])

    # console sample
    print(f"{len(unmatched)} unmatched. Top 15 by best title-score (most likely salvageable):\n")
    for best, t, scored in rows[:15]:
        print(f"  [{best:>3}t] {', '.join(t['artists'])} — {t['full_title']}")
        for c, ts, asc, dd, tier in scored[:2]:
            dstr = f"{dd:+d}s" if dd is not None else "?"
            print(f"        -> {', '.join(c['artists'])} — {c['title']}   t={ts} a={asc} dur={dstr}")

    # html
    blocks = []
    for best, t, scored in rows:
        crows = []
        for c, ts, asc, dd, tier in scored:
            hot = "background:#1e3a24" if ts >= 85 and asc >= 70 else ""
            dstr = f"{dd:+d}s" if dd is not None else "?"
            crows.append(
                f"<tr style='{hot}'><td>{esc(', '.join(c['artists']))} — {esc(c['title'])}</td>"
                f"<td class=n>{ts}</td><td class=n>{asc}</td><td class=n>{esc(dstr)}</td>"
                f"<td class=n>{('T'+str(tier)) if tier else '—'}</td>"
                f"<td><a href='{esc(c.get('url') or '#')}' target=_blank>↗</a></td></tr>")
        blocks.append(
            f"<div class=track><div class=ya>{esc(', '.join(t['artists']))} — {esc(t['full_title'])}"
            f"<span class=alb> · {esc(t.get('album'))}</span></div>"
            f"<table><thead><tr><th>candidate</th><th>title%</th><th>artist%</th><th>Δdur</th><th>tier</th><th></th></tr></thead>"
            f"<tbody>{''.join(crows)}</tbody></table></div>")

    doc = f"""<!doctype html><meta charset=utf-8><title>unmatched candidates</title>
<style>
body{{font:13px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;background:#121212;color:#eee;margin:0;padding:20px}}
h1{{font-size:17px}} .hint{{color:#aaa;margin-bottom:16px}}
.track{{margin:0 0 18px;border:1px solid #262626;border-radius:8px;overflow:hidden}}
.ya{{background:#1d1d1d;padding:8px 12px;font-weight:600}}
.alb{{color:#888;font-weight:400}}
table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:5px 12px;border-top:1px solid #222}}
th{{color:#999;font-size:11px}} td.n{{text-align:right;color:#bbb;width:60px;font-variant-numeric:tabular-nums}}
a{{color:#1db954;text-decoration:none}}
</style>
<h1>🔎 {len(unmatched)} unmatched — candidates &amp; matcher scores</h1>
<div class=hint>Sorted by best title-score. Green rows = title≥85 &amp; artist≥70 (a model/rule call worth a second look). title%/artist% are fuzzy 0–100; Δdur is candidate minus source seconds.</div>
{''.join(blocks)}"""
    out = config.DATA_DIR / "unmatched_candidates.html"
    out.write_text(doc, encoding="utf-8")
    print(f"\nFull browsable report -> {out}")


if __name__ == "__main__":
    main()
