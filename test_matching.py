"""Offline sanity test for the matcher (no API needed)."""
import matcher


def mk(title, artists, dur=None):
    return matcher.prepare_track({"full_title": title, "title": title,
                                  "artists": artists, "duration_ms": dur})


CASES = [
    # (yandex_title, yandex_artists, spotify_title, spotify_artists, expect_match, expected_max_tier)
    ("Bohemian Rhapsody", ["Queen"], "Bohemian Rhapsody", ["Queen"], True, 1),
    ("Грустный дэнс", ["Артик & Асти"], "Грустный дэнс", ["Артик & Асти"], True, 1),
    ("Numb", ["Linkin Park"], "Numb (feat. Jay-Z)", ["Linkin Park", "Jay-Z"], True, 2),
    ("Закрой глаза", ["Баста"], "Zakroy glaza", ["Basta"], True, 4),          # translit
    ("Smells Like Teen Spirit", ["Nirvana"],
     "Smells Like Teen Spirit - Remastered 2021", ["Nirvana"], True, 2),
    ("Lose Yourself", ["Eminem"], "Lose Yourself", ["Eminem"], True, 1),
    ("Wonderwall", ["Oasis"], "Wonderwall - Remastered", ["Oasis"], True, 2),
    ("Random Nonexistent Track XYZ", ["Nobody"], "Totally Different Song",
     ["Other Artist"], False, None),
    ("Песня", ["Кино"], "Песня (Live)", ["Кино"], True, 2),
    ("Believer", ["Imagine Dragons"], "Believer", ["Imagine Dragons", "Kygo"], True, 2),
]


def run():
    ok = 0
    for yt, ya, st, sa, expect, max_tier in CASES:
        y = mk(yt, ya)
        cands = [mk(st, sa)]
        best = matcher.best_match(y, cands)
        matched = best is not None
        tier = best[1][0] if best else None
        status = "PASS"
        if matched != expect:
            status = "FAIL"
        elif expect and tier > max_tier:
            status = f"WEAK (tier {tier} > {max_tier})"
        if status == "PASS":
            ok += 1
        detail = f"tier={tier} {best[1][2] if best else ''}" if matched else "no match"
        print(f"[{status}] {ya[0]} - {yt}  ->  {detail}")
    print(f"\n{ok}/{len(CASES)} as expected")


if __name__ == "__main__":
    run()
