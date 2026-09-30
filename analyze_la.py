#!/usr/bin/env python3
"""The page's data: data/raw/ (from fetch_la.py) -> docs/data/ (not committed; the weekly workflow will publish it as a
release asset, as LA Street Rules' is).

A block is one centerline segment, keyed by its ASSETID: one street from one intersection to the next, or to a dead end.
Its name is the street and its hundred block, from the segment's house numbers, and it runs between the cross streets at
its two ends. The intersections (the centerlines' INT_ID_FROM and INT_ID_TO) where two or more streets meet name the
walking card's spot, and the card's ranks will compare the circle with the same circle around each of them.

The map is split into cells of about 1 km, as on LA Street Rules and SF Streets, so the page only loads the few cells
it's showing:
  cells/{x}_{y}.json  one cell: {b: blocks, i: intersections}. Positions are zoom-17 pixels from the cell's corner.
                      block         {id: ASSETID, s: street name, h: hundred block (none without house numbers),
                                     a: the house numbers at the start and the end of its line (none without),
                                     g: lines, x: the cross streets at its two ends, sd: 1 or 2 when it carries only
                                     the odd or the even house numbers (half of a divided street)}
                      intersection  [x, y, street name, street name, ...]: the streets that meet there, busiest first,
                                     each once (N and S Vermont Ave are one street)
  index.json          loads with the page: street names (blocks and intersections refer to them by number), which cells
                      exist, the cell size, and the day it was built
  streets.json        loads on the first search: for each street name, first every cell holding one of its blocks (to
                      outline the street), then its hundred blocks, one per place, as [hundred / 100 (-1 without house
                      numbers), cell number, the block nearest its middle (its place in that cell's list)], plus the
                      neighborhood it's in (its place in hoods.json, -1 for none) where the street has that hundred in
                      more than one place, or none
"""
import collections
import json
import math
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "docs" / "data"
N17 = 2 ** 17 * 256
CELL = 1024   # map cell edge in zoom-17 Web Mercator pixels
PX_M = 156543.03392 * math.cos(math.radians(34.05)) / 2 ** 17   # metres per zoom-17 pixel in LA (about 0.83)
SNAP = 4 / PX_M   # a segment's end this close to where the others at its intersection end is at that intersection

# the centerlines' suffixes and roadway notes, as LA Street Rules writes them (ticket-clock/analyze_city.py)
NICE_SUFFIX = {"ROAD": "Rd", "LANE": "Ln", "TR": "Trl", "PZ": "Plaza", "CK": "Creek"}
NICE_SFXDIR = {"(S/R)": "(south roadway)", "(N/R)": "(north roadway)"}   # Exposition Blvd's two roadways


def z17(lon, lat):
    """Zoom-17 Web Mercator pixels, the same grid as OpenStreetMap's tiles."""
    r = math.radians(lat)
    return (lon + 180) / 360 * N17, (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * N17


def nice_street(s):
    """'W 37TH' -> 'W 37th', 'MCCLINTOCK' -> 'McClintock' (ticket-clock/citations.py)."""
    t = s.title()
    t = re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), t)
    return re.sub(r"\bMc(\w)", lambda m: "Mc" + m.group(1).upper(), t)


def street_name(key):
    tdir, name, sfx, sdir = key
    sfx = NICE_SUFFIX.get(sfx, sfx.title())
    return " ".join(t for t in (tdir, nice_street(name), sfx, NICE_SFXDIR.get(sdir, sdir.title())) if t)


def mean_nz(*v):
    v = [x for x in v if x]
    return round(sum(v) / len(v)) if v else 0


# ---------- the centerline segments ----------
feats = json.loads((RAW / "centerlines.json").read_text())["features"]
segs, skipped, seen = [], collections.Counter(), set()
for f in feats:
    p, g = f["properties"], f["geometry"]
    name = (p.get("STNAME") or "").strip().upper()
    if not g or not name:
        skipped["no street name or no line"] += 1
        continue
    if (p.get("Street_Designation") or "").strip() == "Outside City":
        skipped["outside the City"] += 1
        continue
    if p["ASSETID"] in seen:
        skipped["a second copy of a segment"] += 1
        continue
    seen.add(p["ASSETID"])
    parts = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
    lines = [[z17(c[0], c[1]) for c in ln] for ln in parts if len(ln) >= 2]
    if not lines:
        skipped["no street name or no line"] += 1
        continue
    key = ((p["TDIR"] or "").strip().upper(), name, (p["STSFX"] or "").strip().upper(), (p["SFXDIR"] or "").strip().upper())
    left, right = (p["ADLF"] or 0, p["ADLT"] or 0), (p["ADRF"] or 0, p["ADRT"] or 0)
    nums = [v for v in (*left, *right) if v]
    sd = 0   # house numbers on one side only, as each half of a divided street has: 1 odd, 2 even
    if any(left) != any(right):
        sd = 1 if nums[0] % 2 else 2
    segs.append(dict(id=int(p["ASSETID"]), key=key, base=(name, key[2]), lines=lines, lo=min(nums, default=0), hi=max(nums, default=0),
                     f=mean_nz(left[0], right[0]), t=mean_nz(left[1], right[1]), sd=sd, ends=(p["INT_ID_FROM"], p["INT_ID_TO"])))
print(f"{len(segs):,} segments" + ("; left out: " + ", ".join(f"{n:,} {why}" for why, n in skipped.items()) if skipped else ""))

# ---------- intersections: where each one is, and the streets that meet there ----------
# A segment's line should run from its INT_ID_FROM to its INT_ID_TO; each intersection sits at the line end most of the
# segments meeting there share, which also tells which way each line runs.
touch = collections.defaultdict(list)   # intersection -> segments that end there
for k, s in enumerate(segs):
    for n in s["ends"]:
        if n:
            touch[n].append(k)
ends_of = lambda s: (s["lines"][0][0], s["lines"][-1][-1])
node_at = {}
for n, ks in touch.items():
    cands = [e for k in ks for e in ends_of(segs[k])]
    score = lambda c: sum(any(math.hypot(e[0] - c[0], e[1] - c[1]) <= SNAP for e in ends_of(segs[k])) for k in ks)
    best = max(range(len(cands)), key=lambda i: (score(cands[i]), -i))   # a tie (a dead end) goes to the line's own order
    node_at[n] = cands[best]
at_start = at_node = both = 0
for s in segs:
    a, b = (node_at.get(n) for n in s["ends"])
    first, last = ends_of(s)
    d = lambda p, q: math.hypot(p[0] - q[0], p[1] - q[1]) if p and q else math.inf
    s["flip"] = d(first, b) + d(last, a) < d(first, a) + d(last, b)   # the line runs from INT_ID_TO to INT_ID_FROM
    if a and b:
        both += 1
        at_start += not s["flip"]
        at_node += (d(last, a) if s["flip"] else d(first, a)) <= SNAP and (d(first, b) if s["flip"] else d(last, b)) <= SNAP
print(f"{at_start / both:.1%} of segment lines run from their INT_ID_FROM; {at_node / both:.1%} end within {SNAP * PX_M:.0f} m of both their intersections")

names, name_ix = [], {}


def nix(name):
    if name not in name_ix:
        name_ix[name] = len(names)
        names.append(name)
    return name_ix[name]


# each intersection's streets: one name per street (N and S Vermont Ave are one), the busiest first, named as most of
# its segments there name it
streets_at = {}
for n, ks in touch.items():
    per = collections.defaultdict(collections.Counter)
    for k in ks:
        per[segs[k]["base"]][segs[k]["key"]] += 1
    streets_at[n] = sorted(((sum(c.values()), street_name(c.most_common(1)[0][0]), base) for base, c in per.items()), key=lambda t: (-t[0], t[1]))
corners = {n: v for n, v in streets_at.items() if len(v) >= 2}
print(f"{len(corners):,} intersections of two or more streets")


def cross(s, n):
    """The busiest other street at intersection n (not this street's own continuation, like N and S Vermont)."""
    other = [nm for _, nm, base in streets_at.get(n, []) if base != s["base"]]
    return nix(other[0]) if other else None


# ---------- write the cells, the index and the search list ----------
cells = collections.defaultdict(lambda: dict(b=[], i=[]))
cell_of = lambda x, y: (int(x // CELL), int(y // CELL))
placed = collections.defaultdict(list)   # street name -> [hundred (-1 without house numbers), middle x, y, cell, place in the cell's list]
for s in sorted(segs, key=lambda s: (street_name(s["key"]), s["lo"], s["id"])):
    pts = [p for ln in s["lines"] for p in ln]
    mx, my = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    cx, cy = cell_of(mx, my)
    g = []
    for ln in s["lines"]:
        line = []
        for x, y in ln:
            q = [round(x - cx * CELL), round(y - cy * CELL)]
            if line[-2:] != q:
                line += q
        if len(line) >= 4:
            g.append(line)
    if not g:
        continue
    si = nix(street_name(s["key"]))
    fr, to = s["ends"][::-1] if s["flip"] else s["ends"]   # the intersections at the line's start and end
    xs = [c for c in (cross(s, fr), cross(s, to)) if c is not None]
    rec = dict(id=s["id"], s=si, g=g, x=xs)
    if s["lo"]:
        rec["h"] = s["lo"] // 100 * 100
        if s["f"] and s["t"]:
            rec["a"] = [s["t"], s["f"]] if s["flip"] else [s["f"], s["t"]]
    if s["sd"]:
        rec["sd"] = s["sd"]
    placed[si].append((rec.get("h", -100) // 100, mx, my, f"{cx}_{cy}", len(cells[(cx, cy)]["b"])))
    cells[(cx, cy)]["b"].append(rec)
for n, v in corners.items():
    x, y = node_at[n]
    cx, cy = cell_of(x, y)
    cells[(cx, cy)]["i"].append([round(x - cx * CELL), round(y - cy * CELL), *(nix(nm) for _, nm, _ in v)])

shutil.rmtree(OUT, ignore_errors=True)
(OUT / "cells").mkdir(parents=True)
sizes = []
for (cx, cy), c in cells.items():
    body = json.dumps(c, separators=(",", ":"))
    (OUT / "cells" / f"{cx}_{cy}.json").write_text(body)
    sizes.append(len(body))
cell_keys = sorted(f"{cx}_{cy}" for cx, cy in cells)
cell_ix = {k: i for i, k in enumerate(cell_keys)}
# streets.json (see the top). Blocks of one street and hundred more than SPLIT apart are separate places, like S Main
# St's 100 block downtown and in Venice; the search tells them apart by neighborhood (the LA Times outlines the page
# draws, docs/hoods.json).
SPLIT = 800 / PX_M
hoods = []   # [box, rings] in zoom-17 pixels, in hoods.json's order
for _, *rs in json.loads((ROOT / "docs" / "hoods.json").read_text())["h"]:
    rings = []
    for f in rs:
        x, y, pts = f[0], f[1], [(f[0], f[1])]
        for k in range(2, len(f), 2):
            x, y = x + f[k], y + f[k + 1]
            pts.append((x, y))
        rings.append(pts)
    xs, ys = [p[0] for r in rings for p in r], [p[1] for r in rings for p in r]
    hoods.append(((min(xs), min(ys), max(xs), max(ys)), rings))


def hood_of(x, y):
    """The neighborhood a point is in (its place in hoods.json), or -1."""
    for k, ((x0, y0, x1, y1), rings) in enumerate(hoods):
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            continue
        inside = False
        for r in rings:
            for (ax, ay), (bx, by) in zip(r, r[-1:] + r[:-1]):
                if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
                    inside = not inside
        if inside:
            return k
    return -1


streets = [[] for _ in names]
n_groups = 0
for si, bs in placed.items():
    groups = []   # [hundred, [blocks]]
    for b in bs:
        for gr in groups:
            if gr[0] == b[0] and math.hypot(gr[1][0][1] - b[1], gr[1][0][2] - b[2]) < SPLIT:
                gr[1].append(b)
                break
        else:
            groups.append([b[0], [b]])
    out = []
    for h, members in groups:
        gx, gy = sum(b[1] for b in members) / len(members), sum(b[2] for b in members) / len(members)
        mid = min(members, key=lambda b: math.hypot(b[1] - gx, b[2] - gy))
        out.append([h, cell_ix[mid[3]], mid[4], mid[1], mid[2]])
    repeat = collections.Counter(e[0] for e in out)
    out = [e[:3] + ([hood_of(e[3], e[4])] if repeat[e[0]] > 1 or e[0] < 0 else []) for e in out]
    out.sort(key=lambda e: (e[0] < 0, e[0], e[1]))   # without house numbers last
    streets[si] = [sorted({cell_ix[b[3]] for b in bs})] + out
    n_groups += len(out)
print(f"search: {len(names):,} street names, {n_groups:,} hundred blocks")
meta = dict(built=str(datetime.now(ZoneInfo("America/Los_Angeles")).date()), cell=CELL, cells=cell_keys, names=names,
            blocks=sum(len(c["b"]) for c in cells.values()), intersections=len(corners))
(OUT / "index.json").write_text(json.dumps(meta, separators=(",", ":")))
(OUT / "streets.json").write_text(json.dumps(streets, separators=(",", ":")))
sizes.sort()
print(f"{len(cells):,} cells, {sum(sizes) / 2**20:.1f} MB; median {sizes[len(sizes) // 2] / 1024:.0f} KB, largest {sizes[-1] / 1024:.0f} KB;",
      f"index.json {(OUT / 'index.json').stat().st_size / 1024:.0f} KB, streets.json {(OUT / 'streets.json').stat().st_size / 1024:.0f} KB")
