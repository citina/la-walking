#!/usr/bin/env python3
"""The page's data: data/raw/ (from fetch_la.py) -> docs/data/ (not committed; weekly.yml publishes it as the la-data
release, and pages.yml puts it on the page).

A block is one centerline segment, keyed by its ASSETID: one street from one intersection to the next, or to a dead end.
Its name is the street and its hundred block, from the segment's house numbers, and it runs between the cross streets at
its two ends. The intersections (the centerlines' INT_ID_FROM and INT_ID_TO) where two or more streets meet name the
walking card's spot, and the card's ranks compare the circle with the same circle around each of them.

Police reports are LAPD's NIBRS offenses of the page's kinds (fetch_la.py KINDS) in public places, from 2025 (when
LAPD's new records are complete) or two years back, whichever is later. A report counts once per kind. LAPD places each
at its hundred block or intersection, so a report place is a point shared by every report LAPD rounded to it. Each is
marked daylight or after dark from the sun's times in LA on its date; LAPD writes 00:00 or 12:00 when it doesn't know
the time, and those count with no time of day.

People walking hit are the people walking hurt or killed in the state's crash reports (CCRS), off the freeways. LAPD's
reports give two streets, not a point, so each crash is placed where they meet and moved along the first street by
the distance the report gives (or at the house number, when there is one). Calls to police are LAPD's calls for service
in four groups by radio code, domestic violence left out, counted per reporting district: LAPD gives no place finer
than that. The High Injury Network is LADOT's 2024 network for people walking: a block is on it when most of the block
lies along one of its lines.

Every report, crash and call keeps its day, counted from its dataset's first, so the page can count any of the date
ranges (index.json ranges) itself.

The map is split into cells of about 1 km, as on LA Street Rules and SF Streets, so the page only loads the few cells
it's showing:
  cells/{x}_{y}.json  one cell: {b: blocks, i: intersections, r: report places, x: crashes}. Positions are zoom-17
                      pixels from the cell's corner.
                      block         {id: ASSETID, s: street name, h: hundred block (none without house numbers),
                                     a: the house numbers at the start and the end of its line (none without),
                                     g: lines, x: the cross streets at its two ends, sd: 1 or 2 when it carries only
                                     the odd or the even house numbers (half of a divided street), hin: 1 on the
                                     High Injury Network}
                      intersection  [x, y, street name, street name, ...]: the streets that meet there, busiest first,
                                     each once (N and S Vermont Ave are one street)
                      report place  {p: [x, y], e: its reports, each one number (report_code): its day, its half hour
                                     (0-47 in daylight, 48-95 after dark, 96 not known) and its kind}
                      crash         [x, y, half hour, people walking hurt, main cause (its place in index.json's
                                     crashes.causes), day]
  index.json          loads with the page: street names (blocks and intersections refer to them by number), which cells
                      exist, the cell size, the day it was built; the police reports' window, kinds and what was left
                      out; the crashes' window, count, causes and how many were placed; the High Injury Network's share
                      of the streets and of the people walking hit; the calls' window, groups and the calls per km2 at
                      each percent of the districts (calls.q); the date ranges (each dataset's first and last day in
                      each) and the last full month; per neighborhood (hoods.json's order) its km of street and reports
                      of violence and robbery, drug offenses and car break-ins and people walking hit, in all
                      (hood_stats) and per date range (hood_range); the summary (the City as a whole: people walking hit
                      and reports of violence and robbery month by month from 2025 and by hour, what the people hit
                      were doing and why, the places visitors go and the intersections with the most people hit); and
                      for each size of the card's circle, the counts at each percent of the intersections (circle_q),
                      for the card's ranks
  districts.json      loads with the first spot or the calls layer: LAPD's reporting districts, as {d: [district, km2,
                      outlines (a first point in zoom-17 pixels, then the steps)], r: its calls in each date range}
  calls/{district}.json  loads for the spot's district: its calls, each one number: (day * 96 + half hour) * 4 + group
  streets.json        loads on the first search: for each street name, first every cell holding one of its blocks (to
                      outline the street), then its hundred blocks, one per place, as [hundred / 100 (-1 without house
                      numbers), cell number, the block nearest its middle (its place in that cell's list)], plus the
                      neighborhood it's in (its place in hoods.json, -1 for none) where the street has that hundred in
                      more than one place, or none
"""
import bisect
import collections
import csv
import difflib
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
NO_TIME = {"0000", "1200"}
# the summary compares the circle around places people go, visitors especially, with the same circle around every
# intersection: only places inside the City (Santa Monica Pier, Universal CityWalk and SoFi Stadium aren't LAPD's),
# and none where LAPD isn't the police (LAX, UCLA and the port have their own)
PLACE_M = 200
PLACES = [("Hollywood & Highland", 34.10170, -118.33860), ("Hollywood & Vine", 34.10160, -118.32670),
          ("Griffith Observatory", 34.11840, -118.30040),
          ("Union Station", 34.05620, -118.23650), ("Olvera Street", 34.05750, -118.23800), ("Chinatown", 34.06280, -118.23800),
          ("Grand Park", 34.05580, -118.24530), ("Walt Disney Concert Hall", 34.05530, -118.24980),
          ("Grand Central Market", 34.05080, -118.24890), ("Pershing Square", 34.04830, -118.25260),
          ("Little Tokyo", 34.04900, -118.23980), ("Arts District", 34.04080, -118.23260),
          ("Crypto.com Arena and L.A. Live", 34.04300, -118.26730), ("Exposition Park", 34.01550, -118.28650),
          ("USC", 34.02060, -118.28540), ("Dodger Stadium", 34.07390, -118.24000), ("Echo Park Lake", 34.07260, -118.26060),
          ("MacArthur Park", 34.05770, -118.27800), ("Koreatown (Wilshire & Western)", 34.06170, -118.30900),
          ("LACMA", 34.06390, -118.35920), ("The Grove", 34.07210, -118.35740), ("Century City", 34.05800, -118.41800),
          ("Westwood Village", 34.06170, -118.44740),
          ("Venice Beach Boardwalk", 33.98540, -118.47270), ("Leimert Park", 34.00450, -118.33210),
          ("Watts Towers", 33.93880, -118.24120)]
HIN_M = 20   # a block is on the High Injury Network when most of it is this close to one of its lines of the same name
             # (its line runs down the middle of a divided street, like Venice Blvd, up to 20 m from each roadway's)   # LAPD's times for "not known" (far above the minutes around them)


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


NO_HH = 96   # a report's half hour when LAPD doesn't know the time


def report_code(day, hh, kind):
    """One police report as one number: its day (from the window's first), its half hour (0-47 in daylight, 48-95
    after dark, NO_HH not known) and its kind. The page takes it apart the same way."""
    return (day * (NO_HH + 1) + hh) * len(KINDS) + kind


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

# ---------- the High Injury Network for people walking (LADOT, 2024): which blocks are on it ----------
# LADOT drew it on the same centerlines, so a block is on it when most of the points along it (every 20 m and the
# middle) are within HIN_M of one of its lines with the block's street name. The name keeps out a short cross street
# whose whole length is within HIN_M of the network.
HIN_CELL = 64
hin_grid = collections.defaultdict(list)   # 64 px square -> [(ax, ay, bx, by, name)]
hin_px = 0.0
for f in json.loads((RAW / "hin.json").read_text())["features"]:
    g, nm = f["geometry"], f["properties"]["str_name"].replace("*", "").strip().upper()
    for ln in g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]:
        pts = [z17(c[0], c[1]) for c in ln]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            hin_px += math.hypot(bx - ax, by - ay)
            for gx in range(int(min(ax, bx) // HIN_CELL), int(max(ax, bx) // HIN_CELL) + 1):
                for gy in range(int(min(ay, by) // HIN_CELL), int(max(ay, by) // HIN_CELL) + 1):
                    hin_grid[(gx, gy)].append((ax, ay, bx, by, nm))


def near_hin(x, y, name):
    lim = HIN_M / PX_M
    for gx in range(int((x - lim) // HIN_CELL), int((x + lim) // HIN_CELL) + 1):
        for gy in range(int((y - lim) // HIN_CELL), int((y + lim) // HIN_CELL) + 1):
            for ax, ay, bx, by, nm in hin_grid.get((gx, gy), ()):
                if not (nm.startswith(name) or name.startswith(nm)):   # SAN FERNANDO ROAD SOUTHWEST (RDWY)
                    continue
                dx, dy = bx - ax, by - ay
                t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy or 1)))
                if math.hypot(ax + t * dx - x, ay + t * dy - y) <= lim:
                    return True
    return False


def along(lines, step):
    """Points every step px along a segment's lines, and its middle."""
    out, total = [], sum(math.hypot(b[0] - a[0], b[1] - a[1]) for ln in lines for a, b in zip(ln, ln[1:]))
    mid, run, nxt = total / 2, 0.0, step / 2
    for ln in lines:
        for (ax, ay), (bx, by) in zip(ln, ln[1:]):
            d = math.hypot(bx - ax, by - ay)
            while nxt <= run + d:
                t = (nxt - run) / (d or 1)
                out.append((ax + t * (bx - ax), ay + t * (by - ay)))
                nxt += step
            if run <= mid <= run + d:
                t = (mid - run) / (d or 1)
                out.append((ax + t * (bx - ax), ay + t * (by - ay)))
            run += d
    return out, total


hin_on_px = 0.0
for s in segs:
    pts, length = along(s["lines"], 20 / PX_M)
    s["hin"] = bool(pts) and sum(near_hin(x, y, s["base"][0]) for x, y in pts) * 2 > len(pts)
    hin_on_px += length * s["hin"]
print(f"High Injury Network: {hin_px * PX_M / 1609.344:,.0f} miles of lines; {sum(s['hin'] for s in segs):,} blocks on it, "
      f"{hin_on_px * PX_M / 1609.344:,.0f} miles ({hin_on_px / hin_px:.0%} of its length)")

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
cells = collections.defaultdict(lambda: dict(b=[], i=[], r=[], x=[]))
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
    if s["hin"]:
        rec["hin"] = 1
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
pol_hour = [[0, 0] for _ in range(24)]   # for the summary: violence and robbery, drug offenses, by the hour (known times)
pol_month = collections.defaultdict(lambda: [0, 0, 0])   # violence and robbery per month: daylight, after dark, no time
at = collections.defaultdict(lambda: dict(k=[0] * (3 * len(KINDS)), t=collections.defaultdict(collections.Counter), e=[]))
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
        if k in PEOPLE or k in DRUGS:
            pol_hour[t.hour][k in DRUGS] += 1
    else:
        place["k"][3 * k + 2] += 1
    if k in PEOPLE:
        pol_month[f"{d:%Y-%m}"][dark(t) if ok else 2] += 1
    place["e"].append(report_code((d - p_start).days, half_hour(t) if ok else NO_HH, k))
n_police = len(seen)
n_kind = [sum(p["k"][3 * k] + p["k"][3 * k + 1] + p["k"][3 * k + 2] for p in at.values()) for k in range(len(KINDS))]
no_time = sum(p["k"][3 * k + 2] for p in at.values() for k in range(len(KINDS)))
print(f"police reports {p_start} to {p_end}: {n_police:,} counted at {len(at):,} places ({no_time:,} with no time of day);",
      "per kind " + ", ".join(f"{KINDS[k][0].lower()} {n:,}" for k, n in enumerate(n_kind)))
print("  left out: " + ", ".join(f"{n:,} {why}" for why, n in left.most_common()))
for pk in ("home", "other"):
    print(f"  {pk}: " + ", ".join(f"{p} {n:,}" for p, n in premises[pk].most_common(12)))

# the report places into the cells, and what each neighborhood holds (per date range, once they're known)
hood_rep = [[0, 0, 0] for _ in hoods]   # violence and robbery, drug offenses, car break-ins
hood_reports = []   # (neighborhood, the reports at a place), for the counts per date range
points = []   # [x, y, violence and robbery, drug offenses, car break-ins, people walking hit] at any time of day, for the ranks
for (lat, lon), p in at.items():
    x, y = z17(lon, lat)
    cx, cy = cell_of(x, y)
    k = p["k"]
    tot = lambda ks: sum(k[3 * j] + k[3 * j + 1] + k[3 * j + 2] for j in ks)
    v = [tot(PEOPLE), tot(DRUGS), tot([CARS])]
    points.append((x, y, *v, 0))
    h = hood_of(x, y)
    if h >= 0:
        hood_rep[h] = [a + b for a, b in zip(hood_rep[h], v)]
        hood_reports.append((h, p["e"]))
    cells[(cx, cy)]["r"].append(dict(p=[round(x - cx * CELL), round(y - cy * CELL)], e=sorted(p["e"])))
hood_stats = [[round(km, 1), *r] for km, r in zip(hood_km, hood_rep)]
print(f"  {sum(sum(r) for r in hood_rep):,} of {sum(n_kind):,} reports inside a neighborhood outline")

# ---------- people walking hit: the state's crash reports (CCRS) where someone walking was hurt or killed ----------
# LAPD's reports have no coordinates, only two streets ("VERMONT AV" at "8TH ST", 50 ft W). A crash goes where the two
# meet (the suffixes as written, then any suffix, then the second street spelled a little differently among those
# meeting the first), then that far along the first street in that direction. Where the two meet in places more than
# 150 m apart, the report's reporting district picks, or else its LAPD area. Freeway crashes are left out; rows with
# coordinates (CHP and other agencies, off the freeways) are used as they are.
CCRS_SFX = {"AV": "AVE", "AVENUE": "AVE", "BL": "BLVD", "BLV": "BLVD", "BLVSD": "BLVD", "BOULEVARD": "BLVD", "HY": "HWY", "STREET": "ST", "STR": "ST", "PLACE": "PL",
            "DRIVE": "DR", "RD": "ROAD", "WY": "WAY", "LN": "LANE", "COURT": "CT", "TERRACE": "TER", "TERR": "TER",
            "CIRCLE": "CIR", "HIGHWAY": "HWY", "TRL": "TR", "TRAIL": "TR", "PARKWAY": "PKWY", "PLZ": "PZ", "PLAZA": "PZ"}
CCRS_DIRS = {"N", "S", "E", "W", "NORTH", "SOUTH", "EAST", "WEST"}
CCRS_ALIAS = {"MLK": "MARTIN LUTHER KING JR", "MLK JR": "MARTIN LUTHER KING JR", "MARTIN LUTHER KING": "MARTIN LUTHER KING JR",
              "M L KING": "MARTIN LUTHER KING JR", "MARTIN L KING": "MARTIN LUTHER KING JR", "MARTIN L KING JR": "MARTIN LUTHER KING JR"}
COMPASS = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}
KSI = {"Fatal", "SuspectSerious", "SevereInactive"}   # killed or badly hurt ("suspected serious injury")
# what the person walking was doing, from the crash report
ACTION = {"CROSSING IN CROSS WALK AT INTERSECTION": "Crossing in a crosswalk at an intersection",
          "CROSSING IN CROSS WALK - NOT AT INTERSECTION": "Crossing in a mid-block crosswalk",
          "CROSSING - NOT IN CROSSWALK": "Crossing outside a crosswalk", "IN ROAD - INCLUDES SHOULDER": "In the road, not crossing",
          "NOT IN ROAD": "Not in the road", "APPROACHING/LEAVING SCHOOL BUS": "Getting on or off a school bus"}
# the crash report's primary collision factor (a Vehicle Code section), in plain words, as SF Streets words them
CAUSE = {"21950A": "Driver didn't yield to someone in a crosswalk", "21950": "Driver didn't yield to someone in a crosswalk",
         "21950B": "Person stepped into the car's path", "21950C": "Driver didn't slow down for someone in a crosswalk",
         "21954A": "Person crossing outside a crosswalk didn't yield", "21954": "Person crossing outside a crosswalk didn't yield",
         "21954B": "Driver didn't take care around someone walking in the road", "21955": "Crossing mid-block between signals",
         "21456": "Person crossed against the walk signal", "21453A": "Driver ran a red light", "21453": "Driver ran a red light",
         "21453B": "Driver turning right on a red light didn't stop or yield", "21453C": "Driver ran a red arrow",
         "21453D": "Person crossed on a red light", "21451A": "Driver turning on a green light didn't yield",
         "22350": "Driving too fast for conditions", "22106": "Driver started or backed up unsafely",
         "22107": "Unsafe turn or lane change", "22450A": "Driver didn't stop at a stop sign", "22450": "Driver didn't stop at a stop sign",
         "21801A": "Driver turning left didn't yield", "21800": "Driver didn't yield at a corner", "21802A": "Driver at a stop sign didn't yield",
         "21804A": "Driver pulling out of a driveway or alley didn't yield", "21952": "Driver crossing the sidewalk didn't yield",
         "21956A": "Person walking in the road where it isn't allowed", "21658A": "Driver straddled lanes or used the wrong lane",
         "23152": "Driving under the influence", "23153": "Driving under the influence", "20001": "Hit and run: the driver didn't stop",
         "21235G": "Motorized scooter ridden against the rules", "21650": "Driver didn't keep to the right",
         "22100": "Driver turned from the wrong lane", "22101D": "Driver didn't follow the turn markings", "22102": "Illegal U-turn",
         "21461A": "Driver didn't obey a sign or signal", "21461": "Driver didn't obey a sign or signal", "23103A": "Reckless driving",
         "23103": "Reckless driving", "21966": "Person walking in a bike lane", "21703": "Following too closely",
         "UNSAFE SPEED": "Driving too fast for conditions", "UNSAFE BACKING": "Driver started or backed up unsafely",
         "UNSAFE STARTING": "Driver started or backed up unsafely", "UNSAFE TURNING MOVEMENT": "Unsafe turn or lane change"}
CAUSE_BY_CODE = {"B": "Other improper driving", "C": "Something other than a driver or a person walking", "D": "Not recorded",
                 "E": "Driver fell asleep"}


def cause_of(r):
    v = re.sub(r"\s*VC$|[\s()]", "", (r["Primary Collision Factor Violation"] or "").upper())
    words = (r["Primary Collision Factor Violation"] or "").strip().upper()
    for key in (v, re.sub(r"[A-Z]$", "", v), v[:5], words):
        if key in CAUSE:
            return CAUSE[key]
    code = (r["Primary Collision Factor Code"] or "").strip()
    return CAUSE_BY_CODE.get(code, "Another traffic law broken" if code == "A" else "Not recorded")


norm = lambda s: re.sub(r"\s+", " ", re.sub(r"[.,'#]", " ", (s or "").upper())).strip()
cl_sfx = {sg["key"][2] for sg in segs if sg["key"][2]}
by_name, by_name_sfx, names_at = collections.defaultdict(set), collections.defaultdict(set), collections.defaultdict(set)
for n, ks in touch.items():
    if n not in node_at:
        continue
    for k in ks:
        nm, sx = norm(segs[k]["base"][0]), segs[k]["base"][1]
        by_name[nm].add(n)
        by_name_sfx[(nm, sx)].add(n)
        names_at[n].add(nm)


ORDINAL = {"FIRST": "1ST", "SECOND": "2ND", "THIRD": "3RD", "FOURTH": "4TH", "FIFTH": "5TH", "SIXTH": "6TH", "SEVENTH": "7TH",
           "EIGHTH": "8TH", "NINTH": "9TH", "TENTH": "10TH"}


def ordinal(t):
    """'105' -> '105TH', '3RS' -> '3RD', 'FIRST' -> '1ST': numbered streets as the centerlines spell them."""
    if t in ORDINAL:
        return ORDINAL[t]
    m = re.fullmatch(r"(\d+)(ST|ND|RD|TH|RS|TS)?", t)
    if not m:
        return t
    n = int(m.group(1))
    return f"{n}{'TH' if 10 <= n % 100 <= 20 else {1: 'ST', 2: 'ND', 3: 'RD'}.get(n % 10, 'TH')}"


def parse_road(s):
    """'E 84TH PL' -> ('84TH', 'PL', None); 'LA BREA' -> ('LA BREA', None, None); '13520 PAXTON ST' -> ('PAXTON', 'ST',
    13520); 'SUNLAND BL 10048' -> ('SUNLAND', 'BLVD', 10048); 'MLK JR BL' -> ('MARTIN LUTHER KING JR', 'BLVD', None)."""
    toks = norm(re.sub(r"\(.*?\)", " ", s or "")).split()
    if not toks or toks == ["NULL"]:
        return None
    num = None
    if len(toks) > 2 and re.fullmatch(r"\d{2,6}", toks[0]):
        num = int(toks.pop(0))
    elif len(toks) > 2 and re.fullmatch(r"\d{2,6}", toks[-1]) and toks[0] not in ("AVENUE", "AVE", "AV"):
        num = int(toks.pop())
    if len(toks) > 1 and CCRS_SFX.get(toks[-1], toks[-1]) in cl_sfx:
        sfx = CCRS_SFX.get(toks.pop(), None)
        sfx = sfx or s.split()[-1].upper()
    else:
        sfx = None
    sfx = CCRS_SFX.get(sfx, sfx)
    if len(toks) > 1 and toks[0] in CCRS_DIRS:   # a direction, unless it's the name ("WEST BL" is West Blvd)
        toks.pop(0)
    if len(toks) > 1 and toks[-1] in CCRS_DIRS:
        toks.pop()
    if toks and toks[0] not in ("AVENUE", "AVE", "AV"):
        toks[0] = ordinal(toks[0])
    toks = ["CANYON" if t == "CYN" else t for t in toks]
    name = re.sub(r"^AVE? (\d+)$", r"AVENUE \1", " ".join(toks))
    return CCRS_ALIAS.get(name, name), sfx, num


def alike(a, b):
    return a == b or min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)) or \
        difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def meet(p, q):
    """The intersections where streets p and q meet, and which way they were found."""
    a, b = by_name_sfx.get(p[:2]) if p[1] else None, by_name_sfx.get(q[:2]) if q[1] else None
    if a and b and a & b:
        return a & b, "as written"
    a, b = by_name.get(p[0], set()), by_name.get(q[0], set())
    if a & b:
        return a & b, "another suffix"
    for nodes, other in ((a, q[0]), (b, p[0])):
        found = {n for n in nodes if any(alike(other, nm) for nm in names_at[n] if nm != (p[0] if other == q[0] else q[0]))}
        if found:
            return found, "a different spelling"
    # where the two streets come within 60 m without sharing an intersection (a corner the centerlines split in two)
    grid = collections.defaultdict(list)
    for n in b:
        grid[(int(node_at[n][0] // 100), int(node_at[n][1] // 100))].append(n)
    found = set()
    for n in a:
        x, y = node_at[n]
        for i in range(int(x // 100) - 1, int(x // 100) + 2):
            for j in range(int(y // 100) - 1, int(y // 100) + 2):
                if any(math.hypot(node_at[m][0] - x, node_at[m][1] - y) <= 60 / PX_M for m in grid.get((i, j), ())):
                    found.add(n)
    return found, "the streets 60 m apart" if found else None


seg_by_name = collections.defaultdict(list)
for k, sg in enumerate(segs):
    if sg["lo"]:
        seg_by_name[norm(sg["base"][0])].append(k)


def address(p):
    """The place of house number p[2] on street p: along the block whose numbers take it in, from the house numbers at
    the block's two ends. Every place it could be, as (point, block)."""
    out = []
    for k in seg_by_name.get(p[0], ()):
        sg = segs[k]
        if p[1] and sg["base"][1] != p[1] or not sg["lo"] <= p[2] <= sg["hi"] or not (sg["f"] and sg["t"]) or sg["f"] == sg["t"]:
            continue
        a, z = (sg["t"], sg["f"]) if sg["flip"] else (sg["f"], sg["t"])
        frac = min(1.0, max(0.0, (p[2] - a) / (z - a)))
        pts = [q for ln in sg["lines"] for q in ln]
        total = sum(math.hypot(v[0] - u[0], v[1] - u[1]) for u, v in zip(pts, pts[1:]))
        left = frac * total
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            d = math.hypot(bx - ax, by - ay)
            if d >= left:
                out.append(((ax + (bx - ax) * left / (d or 1), ay + (by - ay) * left / (d or 1)), k))
                break
            left -= d
    return out


# LAPD's reporting districts: which one a point is in, and its LAPD area
districts = []   # (district, area, box, rings)
for f in json.loads((RAW / "districts.json").read_text())["features"]:
    pr, g = f["properties"], f["geometry"]
    if not pr["REPDIST"] or not g:
        continue
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    rings = [[z17(c[0], c[1]) for c in ring] for poly in polys for ring in poly]
    xs, ys = [p[0] for r in rings for p in r], [p[1] for r in rings for p in r]
    districts.append((int(pr["REPDIST"]), int(pr["PREC"]), (min(xs), min(ys), max(xs), max(ys)), rings))


def district_at(x, y):
    for d, area, (x0, y0, x1, y1), rings in districts:
        if x0 <= x <= x1 and y0 <= y <= y1:
            inside = False
            for r in rings:
                for (ax, ay), (bx, by) in zip(r, r[-1:] + r[:-1]):
                    if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
                        inside = not inside
            if inside:
                return d, area
    return None, None


def pick(cands, rd, area, at=lambda n: node_at[n]):
    """One place among those found: those within 150 m of each other are one place (a divided street meets the other
    street twice); more than one place goes to the report's district, then its area, then, when what's left is within
    300 m (a street that jogs where it crosses), to the first."""
    places = []
    for n in cands:
        for pl in places:
            if math.hypot(at(n)[0] - at(pl[0])[0], at(n)[1] - at(pl[0])[1]) < 150 / PX_M:
                pl.append(n)
                break
        else:
            places.append([n])
    if len(places) > 1 and rd:
        places = [pl for pl in places if district_at(*at(pl[0]))[0] == rd] or places
    if len(places) > 1 and area:
        places = [pl for pl in places if district_at(*at(pl[0]))[1] == area] or places
    if len(places) > 1 and max(math.hypot(at(a[0])[0] - at(b[0])[0], at(a[0])[1] - at(b[0])[1]) for a in places for b in places) < 300 / PX_M:
        places = places[:1]
    return places[0] if len(places) == 1 else None


def line_from(sg, n):
    """A segment's points, starting at its end at intersection n."""
    pts = [p for ln in sg["lines"] for p in ln]
    x, y = node_at[n]
    return pts if math.hypot(pts[0][0] - x, pts[0][1] - y) <= math.hypot(pts[-1][0] - x, pts[-1][1] - y) else pts[::-1]


def walk(nodes, name, d, way):
    """From the intersection, d px along street name in compass direction way: the point and the block it's on. None when
    the street doesn't run that way from there."""
    ux, uy = COMPASS[way]
    n, prev, left = nodes[0], None, d
    for _ in range(60):
        best = None
        for k in touch[n]:
            sg = segs[k]
            if k == prev or not alike(norm(sg["base"][0]), name):
                continue
            pts = line_from(sg, n)
            vx, vy = pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]
            ln = math.hypot(vx, vy)
            if ln and (vx * ux + vy * uy) / ln > 0.3 and (best is None or (vx * ux + vy * uy) / ln > best[0]):
                best = ((vx * ux + vy * uy) / ln, k, pts)
        if best is None:
            return None if prev is None else (pts_end, prev)
        _, k, pts = best
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            sd = math.hypot(bx - ax, by - ay)
            if sd >= left:
                t = left / sd
                return (ax + t * (bx - ax), ay + t * (by - ay)), k
            left -= sd
        pts_end, prev = pts[-1], k
        other = [e for e in segs[k]["ends"] if e and e != n]
        if not other or other[0] not in node_at:
            return pts_end, k
        n = other[0]
    return pts_end, prev


people_in = collections.defaultdict(list)   # collision -> how badly each person walking was hurt
crash_rows = []
for f in sorted((RAW / "crashes").glob("*.json")):
    d = json.loads(f.read_text())
    crash_rows += d["crashes"]
    for pr in d["people"]:
        people_in[int(pr["CollisionId"])].append(pr["ExtentOfInjuryCode"])
latest = {}   # a report sent more than once: its last version
for r in crash_rows:
    key = r["Report Number"] or r["Collision Id"]
    if key not in latest or float(r["Report Version"] or 0) > float(latest[key]["Report Version"] or 0):
        latest[key] = r
c_end = max(date.fromisoformat(r["Crash Date Time"][:10]) for r in latest.values())
c_start = max(POLICE_FROM, c_end - timedelta(days=729))
c_left, how = collections.Counter(), collections.Counter()
causes, cause_ix = [], {}
crashes = []   # (x, y, time, people, badly hurt or killed, cause, the block or intersection it's at)
city_hit = []   # every crash off the freeways, placed or not: (time, people, badly hurt or killed, killed, cause, what they were doing)
for r in latest.values():
    t = datetime.fromisoformat(r["Crash Date Time"])
    hurt = people_in.get(int(float(r["Collision Id"])), [])
    if not c_start <= t.date() <= c_end or not hurt:
        continue
    if r["IsFreeway"] == "True":
        c_left["on a freeway"] += len(hurt)
        continue
    cause = cause_of(r)
    if cause not in cause_ix:
        cause_ix[cause] = len(causes)
        causes.append(cause)
    one = (t, len(hurt), sum(e in KSI for e in hurt), sum(e == "Fatal" for e in hurt), cause_ix[cause],
           ACTION.get((r["PedestrianActionDesc"] or "").strip(), "Not recorded"))
    city_hit.append(one)   # placed or not
    at = None
    if r["Latitude"] and r["Longitude"]:
        x, y = z17(float(r["Longitude"]), float(r["Latitude"]))
        how["coordinates"] += 1
    else:
        p, q = parse_road(r["PrimaryRoad"]), parse_road(r["SecondaryRoad"])
        if p and "/" in (r["PrimaryRoad"] or "") and (not q or q[0] == parse_road(r["PrimaryRoad"].split("/")[0])[0]):
            p, q = parse_road(r["PrimaryRoad"].split("/")[0]), parse_road(r["PrimaryRoad"].split("/")[1])   # "SHERMAN WAY/HINDS AVE"
        rd = int(r["ReportingDistrict"]) if (r["ReportingDistrict"] or "").isdigit() else None
        rn = r["Report Number"] or ""   # LAPD's 2503-04052, 250304052 or 25-03-04052: the year, then the area
        area = int(re.sub(r"\D", "", rn)[2:4]) if re.fullmatch(r"\d{2}-?\d{2}-?\d{5}", rn) else rd // 100 if rd else None
        area = area if area and 1 <= area <= 21 else None
        # a house number on either street: the address, when the block is found
        spot = None
        for a in (p, q):
            if a and a[2] and (a is p or not p or alike(q[0], p[0])):
                found = address(a)
                chosen = pick(range(len(found)), rd, area, at=lambda i: found[i][0]) if found else None
                if chosen is not None:
                    spot = found[chosen[0]]
                    break
        if spot:
            (x, y), k = spot
            at = ("b", k)
            how["at the address"] += 1
        else:
            cands, found = meet(p, q) if p and q and p[0] != q[0] else (set(), None)
            place = pick(sorted(cands, key=str), rd, area)
            if not place:
                c_left["no place: the streets weren't found together" if not cands else "no place: the streets meet in more than one place"] += len(hurt)
                continue
            x, y = node_at[place[0]]
            at = ("i", place[0])
            dist = float(r["SecondaryDistance"] or 0) * (5280 if r["SecondaryUnitOfMeasure"] == "M" else 1) * 0.3048 / PX_M
            way = (r["SecondaryDirection"] or "").strip().upper()
            if dist and way in COMPASS:
                moved = walk(place, p[0], dist, way)
                if moved:
                    (x, y), k = moved
                    at = ("b", k)
                    how[f"at the streets' corner ({found}), then along the street"] += 1
                else:
                    how[f"at the streets' corner ({found}), then straight that way"] += 1
                    x, y = x + COMPASS[way][0] * dist, y + COMPASS[way][1] * dist
                    at = None
            else:
                how[f"at the streets' corner ({found})"] += 1
    crashes.append((x, y, t, len(hurt), one[2], cause_ix[cause], at))
n_hit = sum(c[3] for c in crashes)
n_ksi = sum(c[4] for c in crashes)
n_left = sum(c_left.values())
print(f"people walking hit {c_start} to {c_end}: {n_hit:,} placed in {len(crashes):,} crashes ({n_ksi:,} badly hurt or killed),"
      f" {n_hit / (n_hit + n_left - c_left['on a freeway']):.1%} of those off the freeways")
print("  placed: " + ", ".join(f"{n:,} {w}" for w, n in how.most_common()))
print("  left out: " + ", ".join(f"{n:,} {w}" for w, n in c_left.most_common()))
print("  causes: " + ", ".join(f"{causes[k]} {n:,}" for k, n in collections.Counter(c[5] for c in crashes).most_common(8)))

# on the High Injury Network: placed on one of its blocks, or at an intersection where one of them ends
hin_nodes = {e for sg in segs if sg["hin"] for e in sg["ends"] if e}
on_hin = lambda at: at is not None and (segs[at[1]]["hin"] if at[0] == "b" else at[1] in hin_nodes)
hit_on_hin = sum(c[3] for c in crashes if on_hin(c[6]))
km_all = sum(math.hypot(ln[i][0] - ln[i - 1][0], ln[i][1] - ln[i - 1][1]) for sg in segs for ln in sg["lines"] for i in range(1, len(ln))) * PX_M / 1000
km_hin = hin_on_px * PX_M / 1000
print(f"  on the High Injury Network: {hit_on_hin:,} of {n_hit:,} people walking hit ({hit_on_hin / n_hit:.0%}), on {km_hin / km_all:.1%} of the street length")
hood_hit = [0] * len(hoods)
hood_crashes = []   # (neighborhood, day, people walking hit), for the counts per date range
for x, y, t, n, _, cause, _ in crashes:
    cx, cy = cell_of(x, y)
    day = (t.date() - c_start).days
    cells[(cx, cy)]["x"].append([round(x - cx * CELL), round(y - cy * CELL), half_hour(t), n, cause, day])
    h = hood_of(x, y)
    if h >= 0:
        hood_hit[h] += n
        hood_crashes.append((h, day, n))
hood_stats = [st + [hh] for st, hh in zip(hood_stats, hood_hit)]   # and people walking hit, last

# ---------- calls to police: LAPD's calls for service, per reporting district ----------
# LAPD gives each call only its reporting district. The groups come from the radio codes (fetch_la.py CALL_CODES);
# calls marked domestic violence are left out, as the reports are. A call's time is when it was dispatched.
CALL_GROUPS = ["Fights and assaults", "Someone with a gun or knife", "Robbery", "Threats and harassment"]


def call_group(code, text):
    c, t = code.strip().upper(), text.upper()
    if c.startswith("211"):
        return 2
    if c.startswith("246") or c.startswith(("245", "415")) and re.search(r"GUN|KNI|SHOT", t):
        return 1
    if re.match(r"(242|245)[APOH]*D", c):   # 242D, 245ADS, 242PD...: domestic violence
        return "domestic violence"
    if c.startswith(("242", "245", "415")):
        return 0
    if c.startswith(("422", "314")):
        return 3
    return "another kind of call"


call_rows = []
for f in sorted((RAW / "calls").glob("*.csv")):
    with f.open(newline="") as fh:
        call_rows += list(csv.DictReader(fh))
per_day = collections.Counter(r["dispatch_date"][:10] for r in call_rows)
typical = sorted(per_day.values())[len(per_day) // 2]
q_end = date.fromisoformat(max(d for d, n in per_day.items() if n >= typical / 2))
q_start = max(POLICE_FROM, q_end - timedelta(days=729))
# the districts' outlines (LA GeoHub), their area and the neighborhood each is mostly in
dist_geo = {}   # district -> [polygons as [outer ring, holes...] in zoom-17 pixels]
for f in json.loads((RAW / "districts.json").read_text())["features"]:
    pr, g = f["properties"], f["geometry"]
    if pr["REPDIST"] and g:
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        dist_geo.setdefault(int(pr["REPDIST"]), []).extend([[z17(c[0], c[1]) for c in ring] for ring in poly] for poly in polys)
ring_area = lambda r: abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(r, r[1:] + r[:1]))) / 2
dist_km2 = {d: sum(ring_area(p[0]) - sum(ring_area(h) for h in p[1:]) for p in polys) * PX_M ** 2 / 1e6 for d, polys in dist_geo.items()}
q_left = collections.Counter()
q_at = collections.defaultdict(lambda: dict(q=[0] * (2 * len(CALL_GROUPS)), e=[]))
for r in call_rows:
    d = date.fromisoformat(r["dispatch_date"][:10])
    if not q_start <= d <= q_end:
        continue
    g = call_group(r["call_type_code"], r["call_type_text"])
    if not isinstance(g, int):
        q_left[g] += 1
        continue
    rd = int(r["rpt_dist"]) if (r["rpt_dist"] or "").isdigit() else None
    if rd not in dist_geo:
        q_left["no reporting district"] += 1
        continue
    hh, mm = int(r["dispatch_time"][:2]), int(r["dispatch_time"][3:5])
    t = datetime(d.year, d.month, d.day, hh, mm)
    q_at[rd]["q"][2 * g + dark(t)] += 1
    q_at[rd]["e"].append(((d - q_start).days * 96 + half_hour(t)) * len(CALL_GROUPS) + g)   # day, half hour, group
n_calls = sum(sum(v["q"]) for v in q_at.values())
per_group = [sum(v["q"][2 * g] + v["q"][2 * g + 1] for v in q_at.values()) for g in range(len(CALL_GROUPS))]
print(f"calls to police {q_start} to {q_end}: {n_calls:,} in {len(q_at):,} of {len(dist_geo):,} reporting districts;",
      "per group " + ", ".join(f"{CALL_GROUPS[g].lower()} {n:,}" for g, n in enumerate(per_group)))
print("  left out: " + ", ".join(f"{n:,} {why}" for why, n in q_left.most_common()))
# ranks: every district's calls per km2 (any time of day); calls_q[p - 1] as circle_q
rates = sorted(sum(q_at[d]["q"]) / dist_km2[d] if d in q_at else 0 for d in dist_geo if dist_km2[d] > 0)
calls_q = [round(rates[math.ceil(len(rates) * p / 100) - 1], 1) for p in range(1, 100)]
print(f"  districts: median {sorted(dist_km2.values())[len(dist_km2) // 2]:.2f} km2; calls per km2, median {calls_q[49]:,}, top 1% {calls_q[98]:,}")


def simplify(pts, tol):
    """Douglas-Peucker: the ring's points that keep it within tol of the original."""
    if len(pts) < 3:
        return pts
    (ax, ay), (bx, by) = pts[0], pts[-1]
    dx, dy = bx - ax, by - ay
    ln = math.hypot(dx, dy)
    far_i, far_d = 0, -1.0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        dd = abs(dy * (px - ax) - dx * (py - ay)) / ln if ln else math.hypot(px - ax, py - ay)
        if dd > far_d:
            far_i, far_d = i, dd
    if far_d <= tol:
        return [pts[0], pts[-1]]
    return simplify(pts[:far_i + 1], tol)[:-1] + simplify(pts[far_i:], tol)


def encode(ring):
    """[x, y, dx, dy, ...] in whole zoom-17 pixels, as hoods.json has them."""
    pts = [(round(x), round(y)) for x, y in simplify(ring, 3)]
    out = list(pts[0])
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        if (bx, by) != (ax, ay):
            out += [bx - ax, by - ay]
    return out


districts_out = dict(d=[], r=[])
for d in sorted(dist_geo):
    rings = [encode(r) for poly in dist_geo[d] for r in poly]
    districts_out["d"].append([d, round(dist_km2[d], 2), *[r for r in rings if len(r) >= 6]])

# ---------- the page's date ranges: since the window starts, the last 12 months, 90 days and 30 days, and the last
# full calendar month; each dataset's counted back from its own last day ----------
m_last = min(p_end, q_end)
if (m_last + timedelta(days=1)).day != 1:   # the month before, unless the data runs to the end of this one
    m_last = m_last.replace(day=1) - timedelta(days=1)
month = (m_last.replace(day=1), m_last)


def day_ranges(start, end):
    """The date ranges for data from start to end: {range: [first day, last day]}, days counted from start."""
    last = (end - start).days
    out = {"all": [0, last]}
    for key, n in (("12m", 365), ("90d", 90), ("30d", 30)):
        if n <= last + 1:
            out[key] = [last - n + 1, last]
    if month[0] >= start and month[1] <= end:
        out["month"] = [(month[0] - start).days, (month[1] - start).days]
    return out


per_set = dict(police=day_ranges(p_start, p_end), crashes=day_ranges(c_start, c_end), calls=day_ranges(q_start, q_end))
range_keys = [k for k in ("all", "12m", "90d", "month", "30d") if all(k in v for v in per_set.values())]
ranges = [dict(k=k, **{ds: v[k] for ds, v in per_set.items()}) for k in range_keys]
inr = lambda ds, k, day: per_set[ds][k][0] <= day <= per_set[ds][k][1]
# per neighborhood and range: violence and robbery, drug offenses, car break-ins, people walking hit
hood_range = {k: [[0, 0, 0, 0] for _ in hoods] for k in range_keys}
for h, events in hood_reports:
    for code in events:
        kind, day = code % len(KINDS), code // len(KINDS) // (NO_HH + 1)
        j = 0 if kind in PEOPLE else 1 if kind in DRUGS else 2
        for k in range_keys:
            if inr("police", k, day):
                hood_range[k][h][j] += 1
for h, day, n in hood_crashes:
    for k in range_keys:
        if inr("crashes", k, day):
            hood_range[k][h][3] += n
# per district and range: its calls, for the layer's shading
for d in sorted(dist_geo):
    ev = q_at[d]["e"] if d in q_at else []
    districts_out["r"].append([sum(inr("calls", k, code // len(CALL_GROUPS) // 96) for code in ev) for k in range_keys])
print(f"date ranges: {', '.join(range_keys)}; last month {month[0]:%B %Y}")

# ---------- ranks: the card's circle against the same circle around every intersection ----------
# For each intersection, the report places within the biggest circle, nearest first, with running totals; each smaller
# circle is then a cut of that list. circle_q[m][key] is the count at each percent of the intersections: at least p% of
# them have fewer than v when q[p - 1] < v, for p from 1 to 99 (the page rounds down, as SF Streets does).
points += [(x, y, 0, 0, 0, n) for x, y, _, n, *_ in crashes]
R = max(RADII) / PX_M
grid = collections.defaultdict(list)
for pt in points:
    grid[(int(pt[0] // R), int(pt[1] // R))].append(pt)
near = []   # per intersection: (squared distances, running totals per group)
for n in corners:
    x, y = node_at[n]
    found = sorted(((px - x) ** 2 + (py - y) ** 2, v) for i in range(int(x // R) - 1, int(x // R) + 2) for j in range(int(y // R) - 1, int(y // R) + 2)
                   for px, py, *v in grid.get((i, j), ()) if (px - x) ** 2 + (py - y) ** 2 <= R * R)
    run, tot = [], [0, 0, 0, 0]
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
        circ.append(run[i - 1] if i else [0, 0, 0, 0])
    q = {}
    for key, j in (("people", 0), ("drugs", 1), ("cars", 2), ("hit", 3)):
        v = sorted(c[j] for c in circ)
        q[key] = [v[math.ceil(len(v) * p / 100) - 1] for p in range(1, 100)]
    circle_q[m] = q
    if m == PLACE_M:
        circ_place = circ
print(f"  ranks: at 200 m, half the intersections have {circle_q[200]['people'][49]:,} or fewer reports of violence and robbery,",
      f"the top 1% at least {circle_q[200]['people'][98]:,}; people walking hit: half have {circle_q[200]['hit'][49]:,} or fewer,",
      f"the top 1% at least {circle_q[200]['hit'][98]:,}")

# ---------- the summary: the City as a whole ----------
# around the places people go: what's within PLACE_M, and the share of intersections with fewer (as the card's ranks)
ranked = [sorted(c[j] for c in circ_place) for j in range(4)]
rank_of = lambda j, v: 100 * bisect.bisect_left(ranked[j], v) // len(circ_place)
places = []
for name, lat, lon in PLACES:
    x, y = z17(lon, lat)
    r2 = (PLACE_M / PX_M) ** 2
    v = [0, 0, 0, 0]
    for i in range(int(x // R) - 1, int(x // R) + 2):
        for j in range(int(y // R) - 1, int(y // R) + 2):
            for px, py, *w in grid.get((i, j), ()):
                if (px - x) ** 2 + (py - y) ** 2 <= r2:
                    v = [a + b for a, b in zip(v, w)]
    near_corner = min(corners, key=lambda n: (node_at[n][0] - x) ** 2 + (node_at[n][1] - y) ** 2)
    places.append([name, round(x), round(y), v[3], v[0], v[1], rank_of(3, v[3]), rank_of(0, v[0]), rank_of(1, v[1])])
    print(f"  {name}: near {' & '.join(nm for _, nm, _ in corners[near_corner][:2])}; hit {v[3]}, violence and robbery {v[0]:,}, drugs {v[1]:,}")
# the intersections where the most people walking were hit (crashes placed there, not along a block): the top five, and
# any tied with the fifth, ten at most
by_corner = collections.Counter()
for c in crashes:
    if c[6] and c[6][0] == "i" and c[6][1] in corners:
        by_corner[c[6][1]] += c[3]
top = by_corner.most_common()
cut = top[4][1] if len(top) >= 5 else 0
top_corners = [[" & ".join(nm for _, nm, _ in corners[n][:2]), round(node_at[n][0]), round(node_at[n][1]), v] for n, v in top[:10] if v >= cut]
# people walking hit across the City, placed or not: per month and hour, in daylight and after dark; killed and badly
# hurt; what they were doing; the main causes
months = lambda a, b: [f"{y}-{m:02d}" for y in range(a.year, b.year + 1) for m in range(1, 13) if (a.year, a.month) <= (y, m) <= (b.year, b.month)]
hit_month = {m: [0, 0] for m in months(c_start, c_end)}
hit_hour = [[0, 0] for _ in range(24)]
for t, n, ksi, killed, cause, act in city_hit:
    hit_month[f"{t:%Y-%m}"][dark(t)] += n
    hit_hour[t.hour][dark(t)] += n
summary = dict(place_m=PLACE_M, intersections=len(corners), places=places, corners=top_corners,
               hit=dict(n=sum(c[1] for c in city_hit), ksi=sum(c[2] for c in city_hit), killed=sum(c[3] for c in city_hit),
                        killed_dark=sum(c[3] for c in city_hit if dark(c[0])),
                        month=[[m, *v] for m, v in hit_month.items()], hour=hit_hour,
                        actions=[[a, n] for a, n in sum((collections.Counter({c[5]: c[1]}) for c in city_hit), collections.Counter()).most_common()],
                        causes=[[k, n] for k, n in sum((collections.Counter({c[4]: c[1]}) for c in city_hit), collections.Counter()).most_common(6)]),
               police=dict(month=[[m, *pol_month[m]] for m in months(p_start, p_end)], hour=pol_hour))
H = summary["hit"]
print(f"summary: {H['n']:,} people walking hit off the freeways ({H['killed']} killed, {H['ksi'] - H['killed']:,} badly hurt),"
      f" {H['killed_dark']} of the killed after dark; corners with the most: " + ", ".join(f"{c[0]} {c[3]}" for c in top_corners))

# ---------- write the cells, the index and the search list ----------
shutil.rmtree(OUT, ignore_errors=True)
(OUT / "cells").mkdir(parents=True)
sizes = []
for (cx, cy), c in cells.items():
    for k in ("r", "x"):
        if not c[k]:
            del c[k]
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
            crashes=dict(start=str(c_start), end=str(c_end), n=n_hit, crashes=len(crashes), ksi=n_ksi, causes=causes,
                         left=dict(c_left), placed=round(n_hit / (n_hit + n_left - c_left["on a freeway"]), 3)),
            hin=dict(km=round(km_hin), share_km=round(km_hin / km_all, 3), hit=hit_on_hin, share_hit=round(hit_on_hin / n_hit, 3)),
            calls=dict(start=str(q_start), end=str(q_end), n=n_calls, groups=CALL_GROUPS, per_group=per_group, left=dict(q_left),
                       districts=len(dist_geo), q=calls_q),
            ranges=ranges, month=f"{month[0]:%Y-%m}", hood_range=hood_range, hood_stats=hood_stats, circle_q=circle_q, summary=summary)
(OUT / "index.json").write_text(json.dumps(meta, separators=(",", ":")))
(OUT / "streets.json").write_text(json.dumps(streets, separators=(",", ":")))
(OUT / "districts.json").write_text(json.dumps(districts_out, separators=(",", ":")))
(OUT / "calls").mkdir()
for d, v in q_at.items():
    (OUT / "calls" / f"{d}.json").write_text(json.dumps(sorted(v["e"]), separators=(",", ":")))
sizes.sort()
print(f"{len(cells):,} cells, {sum(sizes) / 2**20:.1f} MB; median {sizes[len(sizes) // 2] / 1024:.0f} KB, largest {sizes[-1] / 1024:.0f} KB;",
      f"index.json {(OUT / 'index.json').stat().st_size / 1024:.0f} KB, streets.json {(OUT / 'streets.json').stat().st_size / 1024:.0f} KB,",
      f"districts.json {(OUT / 'districts.json').stat().st_size / 1024:.0f} KB")
