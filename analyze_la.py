#!/usr/bin/env python3
"""The page's data: data/raw/ (from fetch_la.py) -> docs/data/ (not committed; the weekly workflow will publish it as a
release asset, as LA Street Rules' is).

A block is one centerline segment, keyed by its ASSETID: one street from one intersection to the next, or to a dead end.
Its name is the street and its hundred block, from the segment's house numbers, and it runs between the cross streets at
its two ends. The intersections (the centerlines' INT_ID_FROM and INT_ID_TO) where two or more streets meet name the
walking card's spot, and the card's ranks compare the circle with the same circle around each of them.

Police reports are LAPD's NIBRS offenses of the page's kinds (fetch_la.py KINDS) in public places, from 2025 (when
LAPD's new records are complete) or two years back, whichever is later. A report counts once per kind. LAPD places each
at its hundred block or intersection, so a report place is a point shared by every report LAPD rounded to it. Each is
marked daylight or after dark from the sun's times in LA on its date; LAPD writes 00:00 or 12:00 when it doesn't know
the time, and those count with no time of day.

The map is split into cells of about 1 km, as on LA Street Rules and SF Streets, so the page only loads the few cells
it's showing:
  cells/{x}_{y}.json  one cell: {b: blocks, i: intersections, r: report places}. Positions are zoom-17 pixels from the
                      cell's corner.
                      block         {id: ASSETID, s: street name, h: hundred block (none without house numbers),
                                     a: the house numbers at the start and the end of its line (none without),
                                     g: lines, x: the cross streets at its two ends, sd: 1 or 2 when it carries only
                                     the odd or the even house numbers (half of a divided street)}
                      intersection  [x, y, street name, street name, ...]: the streets that meet there, busiest first,
                                     each once (N and S Vermont Ave are one street)
                      report place  {p: [x, y], k: reports per kind, in daylight, after dark and at no known time in
                                     turn (the zeros at the end left off), kt: when they happened, per kind, as
                                     [half hour, count, half hour, count, ...] with the half hours of the day 0-47 in
                                     daylight and 48-95 after dark; only with any}
  index.json          loads with the page: street names (blocks and intersections refer to them by number), which cells
                      exist, the cell size, the day it was built; the police reports' window, kinds and what was left
                      out; per neighborhood (hoods.json's order) its km of street and reports of violence and robbery,
                      drug offenses and car break-ins; and for each size of the card's circle, the counts at each
                      percent of the intersections (circle_q), for the card's ranks
  streets.json        loads on the first search: for each street name, first every cell holding one of its blocks (to
                      outline the street), then its hundred blocks, one per place, as [hundred / 100 (-1 without house
                      numbers), cell number, the block nearest its middle (its place in that cell's list)], plus the
                      neighborhood it's in (its place in hoods.json, -1 for none) where the street has that hundred in
                      more than one place, or none
"""
import bisect
import collections
import csv
import json
import math
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fetch_la import KINDS, POLICE_FROM

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "docs" / "data"
N17 = 2 ** 17 * 256
CELL = 1024   # map cell edge in zoom-17 Web Mercator pixels
PX_M = 156543.03392 * math.cos(math.radians(34.05)) / 2 ** 17   # metres per zoom-17 pixel in LA (about 0.83)
SNAP = 4 / PX_M   # a segment's end this close to where the others at its intersection end is at that intersection
LA_TZ = ZoneInfo("America/Los_Angeles")
RADII = list(range(100, 501, 50))   # the card's circle, in metres (the page's slider)

# the centerlines' suffixes and roadway notes, as LA Street Rules writes them (ticket-clock/analyze_city.py)
NICE_SUFFIX = {"ROAD": "Rd", "LANE": "Ln", "TR": "Trl", "PZ": "Plaza", "CK": "Creek"}
NICE_SFXDIR = {"(S/R)": "(south roadway)", "(N/R)": "(north roadway)"}   # Exposition Blvd's two roadways

# police report kinds (fetch_la.py KINDS): the ones about harm to people out on foot, drug offenses, car break-ins
PEOPLE, DRUGS, CARS = [0, 1, 2, 3], [4], 5
# Only reports in public places count (Citina, 2026-09-29): streets, sidewalks, alleys, parks, parking lots, buses,
# trains and stations, stores, restaurants and other places open to the public, and homeless encampments (Citina,
# 2026-09-29: they're on sidewalks, in parks and under freeways, where people walk). LAPD's premise names, lower case;
# homes are checked first, so an apartment building's laundry room is a home. Anything else (workplaces, schools,
# hospitals, hotels, a vehicle with no place given) is "other" and doesn't count; so are a few the public words would
# catch (NOT_PUBLIC). The build prints the home and other premises it left out, to check these against.
HOME = re.compile(r"residen|home|apartment|condo|townhouse|driveway \(residential|dwelling|dormitory|frat|housing|tenement|"
                  r"hospice|shelter|motorhome|single residence|vacation rental|yard \(adjacent|porch|patio \(residential|"
                  r"storage shed \(residential|^common laundry room")
NOT_PUBLIC = re.compile(r"fire station|freight|non-retail")
PUBLIC = re.compile(r"street|parkway|sidewalk|alley|highway / road|underpass|bridge|tunnel|parking lot|parking underground|"
                    r"mta parking|valet|park / playground|pool/public|basketball|golf|skateboard|beach|river bed|lake|reservoir|"
                    r"field / woods|public use|public restroom|\bmta\b|metro|station|terminal|metrolink|train, other|tram/|"
                    r"railroad|municipal bus|airport|depot|store|market|mart\b|shop|restaurant|\bbar\b|night club|coffee|"
                    r"drive-thru|gas station|grocery|pharmacy|liquor|dispensary|cannabis|swap meet|laundry|dry cleaner|"
                    r"car wash|bank|atm\b|check cashing|salon|barber|tattoo|theater|arcade|bowling|entertainment|concert|"
                    r"arena|stadium|crypto|convention|museum|zoo|library|community center|sport venue|mall|overcrossing|the grove|"
                    r"beverly c|coliseum|amusement park|rest area|greyhound|amtrak|interstate|gun/sporting|appliance|"
                    r"computer services|pay phone|mail box|trash can|monument|hockey|campground|drive thru|encampment")
# violence between partners is domestic violence whether or not the report carries LAPD's flag
PARTNER = re.compile(r"\bIPV\b|intimate partner|spous|273\.5", re.I)
NO_TIME = {"0000", "1200"}   # LAPD's times for "not known" (far above the minutes around them)


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


_sun = {}


def dark(t):
    """Whether a local time in Los Angeles is between sunset and sunrise (NOAA's approximation, within a few minutes;
    as SF Streets works it out)."""
    d = t.date()
    if d not in _sun:
        g = 2 * math.pi / 365 * (d.timetuple().tm_yday - 1)
        eq = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g)
                       - 0.040849 * math.sin(2 * g))
        dec = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
               + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
        lat, lon = math.radians(34.05), -118.25
        ha = math.degrees(math.acos(math.cos(math.radians(90.833)) / (math.cos(lat) * math.cos(dec))
                                    - math.tan(lat) * math.tan(dec)))
        off = datetime(d.year, d.month, d.day, 12, tzinfo=LA_TZ).utcoffset().total_seconds() / 60
        _sun[d] = (720 - 4 * (lon + ha) - eq + off, 720 - 4 * (lon - ha) - eq + off)
    m = t.hour * 60 + t.minute
    return m < _sun[d][0] or m >= _sun[d][1]


def half_hour(t):
    """The half hour of the day a local time falls in, 0-47, plus 48 after dark."""
    return t.hour * 2 + t.minute // 30 + 48 * dark(t)


def pairs(counter):
    """{half hour: count} -> [half hour, count, ...] in order of the half hour."""
    return [v for h in sorted(counter) for v in (h, counter[h])]


def place_kind(desc):
    d = (desc or "").strip().lower()
    return "home" if HOME.search(d) else "public" if PUBLIC.search(d) and not NOT_PUBLIC.search(d) else "other"


# ---------- the neighborhoods: the LA Times outlines the page draws (docs/hoods.json) ----------
hood_names, hoods = [], []   # [box, rings] in zoom-17 pixels, in hoods.json's order
for name, *rs in json.loads((ROOT / "docs" / "hoods.json").read_text())["h"]:
    rings = []
    for f in rs:
        x, y, pts = f[0], f[1], [(f[0], f[1])]
        for k in range(2, len(f), 2):
            x, y = x + f[k], y + f[k + 1]
            pts.append((x, y))
        rings.append(pts)
    xs, ys = [p[0] for r in rings for p in r], [p[1] for r in rings for p in r]
    hood_names.append(name)
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


# ---------- blocks and intersections into the cells ----------
cells = collections.defaultdict(lambda: dict(b=[], i=[], r=[]))
cell_of = lambda x, y: (int(x // CELL), int(y // CELL))
placed = collections.defaultdict(list)   # street name -> [hundred (-1 without house numbers), middle x, y, cell, place in the cell's list]
hood_km = [0.0] * len(hoods)   # km of street per neighborhood, each block by its middle
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
    h = hood_of(mx, my)
    if h >= 0:
        hood_km[h] += sum(math.hypot(ln[i][0] - ln[i - 1][0], ln[i][1] - ln[i - 1][1]) for ln in s["lines"] for i in range(1, len(ln))) * PX_M / 1000
for n, v in corners.items():
    x, y = node_at[n]
    cx, cy = cell_of(x, y)
    cells[(cx, cy)]["i"].append([round(x - cx * CELL), round(y - cy * CELL), *(nix(nm) for _, nm, _ in v)])

# ---------- police reports: LAPD's offenses of the page's kinds, in public places ----------
kind_of = {c: k for k, (_, cs) in enumerate(KINDS) for c in cs}
rows = []
for f in sorted((RAW / "police").glob("*.csv")):
    with f.open(newline="") as fh:
        rows += list(csv.DictReader(fh))
# the last day that looks complete: the feed's last day or two hold only the reports taken so far
per_day = collections.Counter(r["date_occ"][:10] for r in rows)
typical = sorted(per_day.values())[len(per_day) // 2]
p_end = date.fromisoformat(max(d for d, n in per_day.items() if n >= typical / 2))
p_start = max(POLICE_FROM, p_end - timedelta(days=729))   # two years at most, both ends included
left = collections.Counter()   # why offenses were left out
premises = collections.defaultdict(collections.Counter)   # place kind -> LAPD premise -> offenses (for the printout)
seen = set()
at = collections.defaultdict(lambda: dict(k=[0] * (3 * len(KINDS)), t=collections.defaultdict(collections.Counter)))
for r in rows:
    d = date.fromisoformat(r["date_occ"][:10])
    k = kind_of.get(r["nibr_code"])
    if k is None or not p_start <= d <= p_end:
        continue
    if (r["domestic_violence_crime"] or "").strip().lower() == "yes":
        left["domestic violence"] += 1
        continue
    if PARTNER.search(r["nibr_description"] or ""):
        left["domestic violence (unflagged, by its description)"] += 1
        continue
    pk = place_kind(r["premis_desc"])
    premises[pk][(r["premis_desc"] or "(none)").strip()] += 1
    if pk != "public":
        left[pk] += 1
        continue
    try:
        lat, lon = float(r["hndrdth_lat"]), float(r["hndrdth_lon"])
    except ValueError:
        lat = lon = 0.0
    if not lat or not lon:
        left["no place"] += 1
        continue
    if (r["caseno"], k) in seen:   # a report counts once per kind
        left["another offense of the same kind in the same report"] += 1
        continue
    seen.add((r["caseno"], k))
    tm = (r["time_occ"] or "").strip().zfill(4)
    ok = tm.isdigit() and tm not in NO_TIME and int(tm[:2]) < 24 and int(tm[2:]) < 60
    place = at[(round(lat, 4), round(lon, 4))]
    if ok:
        t = datetime(d.year, d.month, d.day, int(tm[:2]), int(tm[2:]))
        place["k"][3 * k + dark(t)] += 1
        place["t"][k][half_hour(t)] += 1
    else:
        place["k"][3 * k + 2] += 1
n_police = len(seen)
n_kind = [sum(p["k"][3 * k] + p["k"][3 * k + 1] + p["k"][3 * k + 2] for p in at.values()) for k in range(len(KINDS))]
no_time = sum(p["k"][3 * k + 2] for p in at.values() for k in range(len(KINDS)))
print(f"police reports {p_start} to {p_end}: {n_police:,} counted at {len(at):,} places ({no_time:,} with no time of day);",
      "per kind " + ", ".join(f"{KINDS[k][0].lower()} {n:,}" for k, n in enumerate(n_kind)))
print("  left out: " + ", ".join(f"{n:,} {why}" for why, n in left.most_common()))
for pk in ("home", "other"):
    print(f"  {pk}: " + ", ".join(f"{p} {n:,}" for p, n in premises[pk].most_common(12)))

# the report places into the cells, and what each neighborhood holds
hood_rep = [[0, 0, 0] for _ in hoods]   # violence and robbery, drug offenses, car break-ins
points = []   # [x, y, violence and robbery, drug offenses, car break-ins] at any time of day, for the ranks
for (lat, lon), p in at.items():
    x, y = z17(lon, lat)
    cx, cy = cell_of(x, y)
    k = p["k"]
    tot = lambda ks: sum(k[3 * j] + k[3 * j + 1] + k[3 * j + 2] for j in ks)
    v = [tot(PEOPLE), tot(DRUGS), tot([CARS])]
    points.append((x, y, *v))
    h = hood_of(x, y)
    if h >= 0:
        hood_rep[h] = [a + b for a, b in zip(hood_rep[h], v)]
    while k and not k[-1]:
        k.pop()
    rec = dict(p=[round(x - cx * CELL), round(y - cy * CELL)], k=k)
    kt = [pairs(p["t"].get(j, {})) for j in range(len(KINDS))]
    while kt and not kt[-1]:
        kt.pop()
    if kt:
        rec["kt"] = kt
    cells[(cx, cy)]["r"].append(rec)
hood_stats = [[round(km, 1), *r] for km, r in zip(hood_km, hood_rep)]
print(f"  {sum(sum(r) for r in hood_rep):,} of {sum(n_kind):,} reports inside a neighborhood outline")

# ---------- ranks: the card's circle against the same circle around every intersection ----------
# For each intersection, the report places within the biggest circle, nearest first, with running totals; each smaller
# circle is then a cut of that list. circle_q[m][key] is the count at each percent of the intersections: at least p% of
# them have fewer than v when q[p - 1] < v, for p from 1 to 99 (the page rounds down, as SF Streets does).
R = max(RADII) / PX_M
grid = collections.defaultdict(list)
for pt in points:
    grid[(int(pt[0] // R), int(pt[1] // R))].append(pt)
near = []   # per intersection: (squared distances, running totals per group)
for n in corners:
    x, y = node_at[n]
    found = sorted(((px - x) ** 2 + (py - y) ** 2, v) for i in range(int(x // R) - 1, int(x // R) + 2) for j in range(int(y // R) - 1, int(y // R) + 2)
                   for px, py, *v in grid.get((i, j), ()) if (px - x) ** 2 + (py - y) ** 2 <= R * R)
    run, tot = [], [0, 0, 0]
    for _, v in found:
        tot = [a + b for a, b in zip(tot, v)]
        run.append(tot)
    near.append(([f[0] for f in found], run))
circle_q = {}
for m in RADII:
    r2 = (m / PX_M) ** 2
    circ = []
    for d2, run in near:
        i = bisect.bisect_right(d2, r2)
        circ.append(run[i - 1] if i else [0, 0, 0])
    q = {}
    for key, j in (("people", 0), ("drugs", 1), ("cars", 2)):
        v = sorted(c[j] for c in circ)
        q[key] = [v[math.ceil(len(v) * p / 100) - 1] for p in range(1, 100)]
    circle_q[m] = q
print(f"  ranks: at 200 m, half the intersections have {circle_q[200]['people'][49]:,} or fewer reports of violence and robbery,",
      f"the top 1% at least {circle_q[200]['people'][98]:,}")

# ---------- write the cells, the index and the search list ----------
shutil.rmtree(OUT, ignore_errors=True)
(OUT / "cells").mkdir(parents=True)
sizes = []
for (cx, cy), c in cells.items():
    if not c["r"]:
        del c["r"]
    body = json.dumps(c, separators=(",", ":"))
    (OUT / "cells" / f"{cx}_{cy}.json").write_text(body)
    sizes.append(len(body))
cell_keys = sorted(f"{cx}_{cy}" for cx, cy in cells)
cell_ix = {k: i for i, k in enumerate(cell_keys)}
# streets.json (see the top). Blocks of one street and hundred more than SPLIT apart are separate places, like S Main
# St's 100 block downtown and in Venice; the search tells them apart by neighborhood.
SPLIT = 800 / PX_M
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
meta = dict(built=str(datetime.now(LA_TZ).date()), cell=CELL, cells=cell_keys, names=names,
            blocks=sum(len(c["b"]) for c in cells.values()), intersections=len(corners),
            police=dict(start=str(p_start), end=str(p_end), n=n_police, kinds=[k for k, _ in KINDS], per_kind=n_kind,
                        people=PEOPLE, drugs=DRUGS, cars=CARS, no_time=no_time, left=dict(left)),
            hood_stats=hood_stats, circle_q=circle_q)
(OUT / "index.json").write_text(json.dumps(meta, separators=(",", ":")))
(OUT / "streets.json").write_text(json.dumps(streets, separators=(",", ":")))
sizes.sort()
print(f"{len(cells):,} cells, {sum(sizes) / 2**20:.1f} MB; median {sizes[len(sizes) // 2] / 1024:.0f} KB, largest {sizes[-1] / 1024:.0f} KB;",
      f"index.json {(OUT / 'index.json').stat().st_size / 1024:.0f} KB, streets.json {(OUT / 'streets.json').stat().st_size / 1024:.0f} KB")
