"""Generate a self-contained HTML report of matches + unmatched -> data/report.html."""
import html
import json

import config

TIER_COLORS = {1: "#1db954", 2: "#3e9e63", 3: "#e6a700", 4: "#e67e22", 5: "#9b59b6"}
TIER_LABEL = {1: "exact", 2: "normalized", 3: "fuzzy", 4: "rule", 5: "model"}


def esc(s):
    return html.escape("" if s is None else str(s))


def main():
    r = json.loads(config.MATCHES_JSON.read_text(encoding="utf-8"))
    matched = [x for x in r if x["spotify"]]
    unmatched = [x for x in r if not x["spotify"]]

    mrows = []
    for i, x in enumerate(matched, 1):
        s, y, tier = x["spotify"], x["yandex"], x["tier"]
        url = s.get("url") or "#"
        mrows.append(
            f"<tr><td class=pos>{i}</td>"
            f"<td><a href='{esc(url)}' target=_blank>{esc(', '.join(s['artists']))} — {esc(s['title'])}</a></td>"
            f"<td class=ya>{esc(', '.join(y['artists']))} — {esc(y['full_title'])}</td>"
            f"<td><span class=tier style='background:{TIER_COLORS.get(tier,'#888')}'>"
            f"T{tier} {TIER_LABEL.get(tier,'')}</span></td>"
            f"<td class=conf>{x['confidence']}</td></tr>"
        )

    urows = []
    for x in unmatched:
        y = x["yandex"]
        urows.append(
            f"<tr><td class=ya>{esc(', '.join(y['artists']))} — {esc(y['full_title'])}</td>"
            f"<td>{esc(y.get('album'))}</td><td>{x.get('n_candidates', 0)}</td></tr>"
        )

    doc = f"""<!doctype html><html><head><meta charset=utf-8>
<title>migrate-music report</title>
<style>
:root {{ color-scheme: dark; }}
body {{ font: 14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; margin:0; background:#121212; color:#eee; }}
header {{ position:sticky; top:0; background:#181818; padding:16px 24px; border-bottom:1px solid #2a2a2a; }}
h1 {{ margin:0 0 6px; font-size:18px; }}
.stat {{ color:#aaa; font-size:13px; }}
.bar {{ display:flex; gap:8px; align-items:center; margin-top:10px; }}
button {{ background:#282828; color:#eee; border:0; padding:8px 14px; border-radius:18px; cursor:pointer; font-size:13px; }}
button.active {{ background:#1db954; color:#000; font-weight:600; }}
input {{ flex:1; background:#282828; border:0; color:#eee; padding:8px 14px; border-radius:18px; font-size:13px; }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ text-align:left; padding:7px 24px; border-bottom:1px solid #222; vertical-align:top; }}
th {{ position:sticky; top:128px; background:#1d1d1d; font-size:12px; color:#aaa; z-index:1; }}
tr:hover td {{ background:#1a1a1a; }}
a {{ color:#1db954; text-decoration:none; }} a:hover {{ text-decoration:underline; }}
.pos {{ color:#777; width:46px; }} .conf {{ color:#aaa; width:50px; }}
.ya {{ color:#9a9a9a; }}
.tier {{ color:#000; font-size:11px; padding:2px 8px; border-radius:10px; white-space:nowrap; }}
#unmatched {{ display:none; }}
</style></head><body>
<header>
  <h1>🎵 migrate-music — Yandex → Spotify</h1>
  <div class=stat>{len(matched)} matched · {len(unmatched)} unmatched · {len(r)} total &nbsp;|&nbsp;
     matched shown in playlist order (newest-liked first)</div>
  <div class=bar>
    <button id=bM class=active onclick="show('matched')">Matched ({len(matched)})</button>
    <button id=bU onclick="show('unmatched')">Unmatched ({len(unmatched)})</button>
    <input id=q placeholder="filter…" oninput="filt()">
  </div>
</header>
<table id=matched><thead><tr><th>#</th><th>Spotify (as it'll appear)</th><th>was (Yandex)</th><th>match</th><th>conf</th></tr></thead>
<tbody>{''.join(mrows)}</tbody></table>
<table id=unmatched><thead><tr><th>Yandex track (no Spotify match)</th><th>album</th><th>candidates</th></tr></thead>
<tbody>{''.join(urows)}</tbody></table>
<script>
function show(w){{
  document.getElementById('matched').style.display = w=='matched'?'table':'none';
  document.getElementById('unmatched').style.display = w=='unmatched'?'table':'none';
  document.getElementById('bM').classList.toggle('active', w=='matched');
  document.getElementById('bU').classList.toggle('active', w=='unmatched');
  filt();
}}
function filt(){{
  var s=document.getElementById('q').value.toLowerCase();
  var t=document.querySelector('table[style*="table"],#matched');
  document.querySelectorAll('table').forEach(function(tb){{
    if(tb.style.display=='none') return;
    tb.querySelectorAll('tbody tr').forEach(function(tr){{
      tr.style.display = tr.textContent.toLowerCase().indexOf(s)>=0?'':'none';
    }});
  }});
}}
</script></body></html>"""

    out = config.DATA_DIR / "report.html"
    out.write_text(doc, encoding="utf-8")
    print(f"Wrote {out}  ({len(matched)} matched, {len(unmatched)} unmatched)")


if __name__ == "__main__":
    main()
