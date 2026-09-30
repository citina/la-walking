#!/usr/bin/env python3
"""Download what the page needs into data/raw/ (not committed). DATA_SOURCES.md says what each file is for.

- centerlines.json: the City of Los Angeles street centerlines, with address ranges per side and the intersection at
  each end (LA GeoHub, Street_Information MapServer layer 36, ~85k segments), the same download as LA Street Rules'
  (ticket-clock/fetch_city.py). They barely change, so they're refetched once the copy is four weeks old.
- fetched.json: the date each file above was downloaded.

Police reports, calls to police, crash reports and the High Injury Network come with the milestones that use them
(PLAN.md §5).

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


def get(url, params, timeout=600, tries=4):
    """One request, retried on a server error: the city's map server hands out the odd 502, and a single one
    shouldn't throw away a download that takes minutes."""
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


missing = []   # files with no copy yet that couldn't be downloaded; the run fails at the end, after the rest


def refresh(name, fetch):
    """Run fetch(path), which writes data/raw/<name> and returns a line to print. If it fails and an older copy exists,
    keep that copy and say so. With no copy, carry on with the other files and fail at the end, so what did download is
    kept for the next run."""
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


RAW.mkdir(parents=True, exist_ok=True)
today = dt.date.today()
MANIFEST = RAW / "fetched.json"
fetched = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}   # file -> date downloaded
age = lambda name: (today - dt.date.fromisoformat(fetched[name])).days if name in fetched else 10 ** 6


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

MANIFEST.write_text(json.dumps(fetched, indent=1, sort_keys=True))
if missing:
    sys.exit(f"stopping: no copy of {', '.join(missing)}; the rest is downloaded and kept for the next run")
