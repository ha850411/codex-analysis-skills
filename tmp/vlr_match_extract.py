#!/usr/bin/env python3
import html
import json
import re
import sys
import urllib.request


def clean(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def extract(url: str) -> dict:
    raw = fetch(url)
    title_match = re.search(r"<title>(.*?)</title>", raw, re.S)
    title = clean(title_match.group(1)) if title_match else url
    veto_match = re.search(
        r'<div class="match-header-note">.*?</div>\s*<div class="match-header-note">.*?</div>\s*'
        r'<div class="match-header-vs">.*?</div>\s*</div>\s*'
        r'<div class="match-header-note">.*?</div>\s*</div>\s*'
        r'<div class="match-header-note">(.*?)</div>',
        raw,
        re.S,
    )
    if not veto_match:
        veto_match = re.search(
            r"((?:[A-Z0-9]+|[A-Za-z ]+) ban [A-Za-z]+; .*? remains)",
            clean(raw),
        )
    veto = clean(veto_match.group(1)) if veto_match else ""
    maps = []
    pattern = re.compile(
        r'<div class="vm-stats-game\s*" data-game-id="[^"]+">(.*?)'
        r'<div style="text-align: center; margin-top: 15px;">',
        re.S,
    )
    for block in pattern.findall(raw):
        names = [clean(x) for x in re.findall(r'class="team-name">\s*(.*?)</div>', block, re.S)]
        scores = [clean(x) for x in re.findall(r'class="score[^"]*"[^>]*>\s*(.*?)</div>', block, re.S)]
        map_match = re.search(
            r'<div class="map">.*?<span style="position: relative;">\s*([A-Za-z]+)',
            block,
            re.S,
        )
        if len(names) >= 2 and len(scores) >= 2 and map_match:
            maps.append(
                {
                    "map": map_match.group(1),
                    "team1": names[0],
                    "score1": int(re.search(r"\d+", scores[0]).group()),
                    "team2": names[1],
                    "score2": int(re.search(r"\d+", scores[1]).group()),
                }
            )
    players = []
    all_marker = '<div class="vm-stats-game mod-active" data-game-id="all">'
    all_block = raw.split(all_marker, 1)[1] if all_marker in raw else ""
    player_pattern = re.compile(
        r'ovw-player-name[^>]*>\s*(.*?)</div>.*?'
        r'ovw-player-tag[^>]*>\s*(.*?)</div>.*?'
        r'data-col="rating2".*?side mod-both[^>]*>\s*([^<]+)</span>.*?'
        r'data-col="acs".*?side mod-both[^>]*>\s*([^<]+)</span>.*?'
        r'data-col="kast".*?side mod-both[^>]*>\s*([^<]+)</span>.*?'
        r'data-col="adr".*?side mod-both[^>]*>\s*([^<]+)</span>.*?'
        r'data-col="fb".*?side mod-both[^>]*>\s*([^<]+)</span>.*?'
        r'data-col="fd".*?side mod-both[^>]*>\s*([^<]+)</span>',
        re.S,
    )
    for match in player_pattern.finditer(all_block):
        name, tag, rating, acs, kast, adr, fk, fd = [clean(x) for x in match.groups()]
        if not all((rating, acs, adr, fk, fd)):
            continue
        players.append(
            {
                "name": name,
                "tag": tag,
                "rating": float(rating),
                "acs": int(acs),
                "kast": kast,
                "adr": int(adr),
                "fk": int(fk),
                "fd": int(fd),
            }
        )
    return {"url": url, "title": title, "veto": veto, "maps": maps, "players": players[:10]}


if __name__ == "__main__":
    print(json.dumps([extract(url) for url in sys.argv[1:]], ensure_ascii=False, indent=2))
