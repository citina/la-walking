#!/usr/bin/env python3
"""Download what the page needs into data/raw/ (not committed). DATA_SOURCES.md says what each file is for.

- centerlines.json: the City of Los Angeles street centerlines, with address ranges per side and the intersection at
  each end (LA GeoHub, Street_Information MapServer layer 36, ~85k segments), the same download as LA Street Rules'
  (ticket-clock/fetch_city.py). They barely change, so they're refetched once the copy is four weeks old.
- police/YYYY-MM.csv: LAPD's NIBRS offenses (data.lacity.org k7nn-b2ep) of the kinds the page shows (POLICE_CODES),
  by the month they happened in, from POLICE_FROM (when LAPD's new records are complete) or two years back, whichever
  is later. Late reports keep filling in recent months, so the last two are refetched every run, and an older one once
  its copy is four weeks old. Months that fall out of the window are deleted.
- fetched.json: the date each file above was downloaded.

Calls to police, crash reports and the High Injury Network come with the milestones that use them (PLAN.md §5).

When a download fails and an older copy is on disk, that copy is kept with a warning, so a city server that's down for
a day doesn't stop the rebuild; a file with no copy yet still stops it.
"""
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parent / "data" / "raw"
STREETS = "https://maps.lacity.org/lahub/rest/services/Street_Information/MapServer/36/query"
FIELDS = "ASSETID,INT_ID_FROM,INT_ID_TO,ADLF,ADLT,ADRF,ADRT,ZIP_L,ZIP_R,TDIR,STNAME,STSFX,SFXDIR,STATUS,Street_Designation"
STREETS_DAYS = 28   # the centerlines are refetched once the copy is this old
POLICE = "https://data.lacity.org/resource/k7nn-b2ep.csv"
POLICE_COLS = "uniquenibrno,caseno,date_occ,time_occ,nibr_code,nibr_description,premis_desc,domestic_violence_crime,hndrdth_lat,hndrdth_lon"
POLICE_FROM = dt.date(2025, 1, 1)   # LAPD moved to NIBRS on 2024-03-07; its new records are complete from 2025
POLICE_DAYS = 28   # an older month is refetched once its copy is this old
# the police report kinds the page shows (analyze_la.py KINDS), by NIBRS code
KINDS = [("Robbery", ["120"]),
         ("Assault and other violence", ["13A", "13B", "13C", "09A", "11A", "11B", "11C", "11D"]),
         ("Pickpocketing and purse snatching", ["23A", "23B"]),
         ("Weapons", ["520"]),
         ("Drug offenses", ["35A", "35B"]),
         ("Car break-ins", ["23F"])]
POLICE_CODES = [c for _, cs in KINDS for c in cs]


def get(url, params, timeout=600, tries=4):
    """One request, retried on a server error: the city's servers hand out the odd 502, and a single one shouldn't
    throw away a download that takes minutes."""
    for k in range(tries):
        try:
            with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=timeout) as r:
                return r.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            code = getattr(e, "code", None)
            if k == tries - 1 or (code is not None and code < 500):
                raise
            print(f"warning: {url.split('/')[2]} said {code or e}; retrying in {20 * (k + 1)}s")
            time.sleep(20 * (k + 1))


def get_json(url, params, **kw):
    """A request whose answer has to parse as JSON: the map server also answers 200 with an HTML error page, which is
    just as broken as a 502."""
    for k in range(4):
        body = get(url, params, **kw)
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            if k == 3:
                raise
            print(f"warning: {url.split('/')[2]} answered with something that isn't JSON; retrying in {20 * (k + 1)}s")
            time.sleep(20 * (k + 1))


def write(path, body):
    tmp = path.with_suffix(".part")   # a run that dies halfway leaves the old copy, not half a file
    tmp.write_bytes(body)
    tmp.replace(path)


def months(start, end):
    m = start.replace(day=1)
    while m <= end:
        nxt = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield m, nxt
        m = nxt


def main():
    missing = []   # files with no copy yet that couldn't be downloaded; the run fails at the end, after the rest
    RAW.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    manifest = RAW / "fetched.json"
    fetched = json.loads(manifest.read_text()) if manifest.exists() else {}   # file -> date downloaded
    age = lambda name: (today - dt.date.fromisoformat(fetched[name])).days if name in fetched else 10 ** 6

    def refresh(name, fetch):
        """Run fetch(path), which writes data/raw/<name> and returns a line to print. If it fails and an older copy
        exists, keep that copy and say so. With no copy, carry on with the other files and fail at the end, so what
        did download is kept for the next run."""
        path = RAW / name
        try:
            print(fetch(path))
            fetched[name] = today.isoformat()
        except Exception as e:
            if not path.exists():
                print(f"error: couldn't download {name} ({str(e)[:120]}), and there's no earlier copy")
                missing.append(name)
                return
            print(f"warning: couldn't refresh {name} ({str(e)[:120]}); keeping the copy from {fetched.get(name, 'an earlier run')}")

    # ---- street centerlines, 1,000 per request ----
    def fetch_streets(path):
        feats, off = [], 0
        while True:
            page = get_json(STREETS, {"where": "1=1", "outFields": FIELDS, "outSR": "4326", "orderByFields": "OBJECTID",
                                      "resultOffset": off, "resultRecordCount": 1000, "f": "geojson"}, timeout=120)
            feats += page["features"]
            off += len(page["features"])
            if not page["features"] or not (page.get("exceededTransferLimit") or page.get("properties", {}).get("exceededTransferLimit")):
                break
        write(path, json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")).encode())
        return f"centerlines.json {len(feats)} segments"

    if age("centerlines.json") >= STREETS_DAYS or not (RAW / "centerlines.json").exists():
        refresh("centerlines.json", fetch_streets)
    else:
        print(f"centerlines.json: keeping the copy from {fetched['centerlines.json']}")

    # ---- police reports, a month at a time ----
    pdir = RAW / "police"
    pdir.mkdir(exist_ok=True)
    start = max(POLICE_FROM, today.replace(year=today.year - 2, day=1))
    for old in pdir.glob("*.csv"):
        if old.stem < f"{start:%Y-%m}":
            old.unlink()
            fetched.pop(f"police/{old.name}", None)
    window = list(months(start, today))
    codes = ",".join(f"'{c}'" for c in POLICE_CODES)

    def month_fetcher(m, nxt):
        def fetch(path):
            body = get(POLICE, {"$select": POLICE_COLS, "$where": f"date_occ >= '{m}' and date_occ < '{nxt}' and nibr_code in ({codes})",
                                "$order": "uniquenibrno", "$limit": "1000000"}, timeout=300)
            write(path, body)
            n = body.count(b"\n") - 1
            return f"police/{path.name} {n} offenses"
        return fetch

    for i, (m, nxt) in enumerate(window):
        name = f"police/{m:%Y-%m}.csv"
        if (RAW / name).exists() and i < len(window) - 2 and age(name) < POLICE_DAYS:
            continue
        refresh(name, month_fetcher(m, nxt))

    manifest.write_text(json.dumps(fetched, indent=1, sort_keys=True))
    if missing:
        sys.exit(f"stopping: no copy of {', '.join(missing)}; the rest is downloaded and kept for the next run")


if __name__ == "__main__":
    main()
