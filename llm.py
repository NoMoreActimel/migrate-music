"""Small-model fallback: pick the best Spotify candidate for a leftover track."""
import json
import re

import config


def pick_match(y: dict, candidates: list):
    """Return (candidate, confidence) chosen by the model, or None."""
    if not config.MODEL_FALLBACK or not candidates:
        return None

    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    cand_lines = "\n".join(
        f"{i}: {', '.join(c['artists'])} — {c['title']}"
        f"  [album: {c.get('album')}, {round((c.get('duration_ms') or 0)/1000)}s]"
        for i, c in enumerate(candidates)
    )
    dur = round((y.get("duration_ms") or 0) / 1000)
    prompt = (
        "You match a song across music services. Source track (Yandex Music):\n"
        f"  Artist(s): {', '.join(y.get('artists') or [])}\n"
        f"  Title: {y.get('full_title') or y.get('title')}\n"
        f"  Album: {y.get('album')}  Duration: {dur}s\n\n"
        "Spotify candidates:\n"
        f"{cand_lines}\n\n"
        "Pick the candidate that is the SAME song/recording. Allow translation, "
        "transliteration (Cyrillic↔Latin), feat. differences, and remaster/edit "
        "variants. If none is clearly the same song, use null.\n"
        'Respond with ONLY JSON: {"index": <int|null>, "confidence": <0-100>}'
    )

    msg = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=80,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None

    idx = data.get("index")
    if idx is None or not isinstance(idx, int) or not (0 <= idx < len(candidates)):
        return None
    return candidates[idx], int(data.get("confidence", 0))
