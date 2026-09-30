# LA Walking — plan

Working title. A map of the City of Los Angeles for people on foot, in the style of the walking side of
[SF Streets](https://citina.github.io/sf-streets/#walk):

- *Around a spot I pick, what gets reported to police, what do people call police about, and how often are people
  walking hit by cars, when and why?*

Only the walking question. The driving question ("can I park here?") was looked at for LA on 2026-09-27 and dropped:
LA doesn't publish its curb rules (meter hours, time limits, permit hours, tow-away, closures), so the answer would rest
on guesses. LA Street Rules keeps the parking side, from tickets.

Written 2026-09-27. Milestones 1–6 (the map, police reports, the High Injury Network, people walking hit, calls to
police, the summary) built 2026-09-29; see §5.

---

## 1. What carries over, and what's different in LA

**Reused from sf-streets (walking side) and ticket-clock (LA Street Rules)**

- The hand-written page, no build step, no map library: SVG over OpenStreetMap tiles, pan, zoom, a two-finger turn with
  a compass back to north, the search box, and "Show what's around me" (`sf-streets/docs/index.html`, walk mode only).
- The walking card: rows closed until tapped, each with its count under its name; kinds as rows that open to a note and
  a half-hour dot chart; ranks against every intersection ("Top 4% of LA intersections"); daylight / after dark; the
  circle (100 to 500 m, 200 m to start); the link carries the spot and size but never your own location
  (`#@34.05223,-118.24368/250m`).
- The City of LA street centerlines (LA GeoHub, `Street_Information/MapServer/36`, ~85k segments) for search, blocks and
  intersections, as `ticket-clock/fetch_city.py` downloads them; the address parsing in `ticket-clock/analyze_city.py`.
- The LA Times neighborhoods (`ticket-clock/docs/streets/hoods.json`, 113 of 114, CC BY 4.0), committed as a static file.
- Design tokens, type (Barlow / Barlow Condensed / IBM Plex Mono), the five text sizes (12 / 14 / 15 / 16 / 18.5 px), the
  sister-site masthead and About cards, the method as closed rows, the small disclaimer. The map stays light in dark
  mode.
- Data split into ~1 km map cells (`data/cells/{key}.json`) so the page only loads what's on screen. Weekly GitHub
  Action → release asset → Pages.

**Different in LA**

- **Much bigger.** The City is about 1,300 km², ten times SF. LA Street Rules already needs ~1,200 cells. Every build
  runs on GitHub Actions, never on the laptop.
- **Police reports are placed at a hundred block or an intersection, not a corner.** LAPD rounds each location for
  privacy ("16100 Devonshire St", "E 42nd St & Compton Ave") and gives its coordinates (`hndrdth_lat`, `hndrdth_lon`).
  The page counts a report inside the circle by those coordinates. 99.97% have them.
- **LAPD changed record systems on 2024-03-07** (to the FBI's NIBRS). Reports from Mar–Dec 2024 are split between the
  old dataset and the new one, with different categories. The new one is complete from **2025-01-01** (about 18,000
  offenses a month since then, against 11,000–14,000 in late 2024). So the window starts on 2025-01-01 and grows until
  it reaches two years on 2027-01-01, then rolls (`START = max(2025-01-01, latest − 2 years)`). The page says "since
  Jan 2025" until then.
- **Calls to police have no location finer than a police reporting district** (1,135 of them, about 1 km² each). They
  can't be counted in a circle. See §3.
- **LAPD's own crash data stopped on 2025-03-08.** Pedestrian crashes come from California's crash reports (CCRS),
  which carry LAPD's reports up to last week, but 99.5% of LAPD's rows have no coordinates, only the two streets
  ("Vermont Av at 8th St, 50 ft W"). They get placed at build time from the centerlines. See §4.
- **LAPD reports carry a premise** (street, sidewalk, home, store...) and a domestic-violence flag. A third of the
  reports of violence are in a home and a quarter are flagged domestic violence. The page is about being out on foot,
  so only reports in public places count (decision 2, settled 2026-09-29).

---

## 2. Data

See **[DATA_SOURCES.md](DATA_SOURCES.md)**: what will be used and for what, and what was looked at and left out.

---

## 3. The page (`docs/index.html`)

```
mast            LA Walking · (sister sites)                        Updated Sep 27 · About
h1 + lede       "Pick a spot in LA to see what gets reported to police around it, and how often people walking are hit
                 by cars there." + a link to the city summary
find bar        Show what's around me · search address / street / neighborhood / place
time control    Dates [Since Jan 2025 ▾]   When [Any | Daylight | After dark]   Within [100–500 m slider, 200 m to start]
┌───────────────── map ─────────────────┐ ┌──────── card ────────┐
│ layer chips                           │ │ "Near X & Y", hood    │
│ OSM tiles + layers + the circle       │ │ rows (below)          │
│ zoom / fit LA / north                 │ │                       │
└───────────────────────────────────────┘ └───────────────────────┘
legend
summary         the City as a whole
method          one closed row per topic
about · disclaimer
```

**The card** (for the circle picked)

1. **Reported to police** — the six kinds (below), most first; tap a kind for what it covers and, with 10 or more,
   its half-hour dot chart; ranks against every intersection (violence and robbery, drug offenses and
   car break-ins each ranked on their own); an hour chart and how many after dark. Note: "Reports are placed at the
   hundred block or corner LAPD gives. Counts also depend on where police patrol and who calls."
2. **Calls to police** — not a circle count: "In this police reporting district (about 1.2 km²): 312 calls about fights
   and assaults since Jan 2025", per group, with the rank among the 1,135 districts and the hour chart. The district is
   drawn on the map when this row is open. Note: "A call is what someone reported, not what police found. LAPD gives
   only the district." (decision 3: kept)
3. **People walking hit** — "16 people walking hit since Jan 2025" and "3 badly hurt or killed", big number first; the
   High Injury Network streets through the circle (with a "?" to its explanation); the rank; the hour chart; after dark;
   the top causes in plain words.

Before a spot is picked the card is one line. After a search on a phone, the message above the map gives the short
answer and "See the card ↓", as on SF Streets.

**Police report kinds** (NIBRS codes; counts are 2025-01-01 to 2026-09-05, all premises)

| Kind | NIBRS codes | Count |
|---|---|---|
| Robbery | 120 | 11,995 |
| Assault and other violence | 13A aggravated assault, 13B simple assault, 13C threats, 09A murder, 11A–11D sex offenses | 86,964 |
| Pickpocketing and purse snatching | 23A, 23B | 2,516 |
| Weapons | 520 | 5,600 |
| Drug offenses | 35A, 35B | 12,595 |
| Car break-ins | 23F | 31,539 |

Threats (13C, 7,925) are in "Assault and other violence" (decision 2). Car break-ins are on this page (Citina, 2026-09-29, in
place of LA Street Rules' block card): SF Streets has them on its driving side, and LA Walking is LA's only page for
police reports. They're their own kind and their own map layer, counted apart from violence and robbery.

**Call groups** (by LAPD's radio code, `analyze_la.py` `call_group`; built 2026-09-29, counts 2025-01-01 to
2026-09-25). The code carries suffixes (SN suspect now, J/O just occurred, A ambulance, PS possible, 7 hate crime...),
so a group takes every code that starts with its number:

| Group | Radio codes | Calls |
|---|---|---|
| Fights and assaults | 242 battery, 245 assault with a deadly weapon (not shots), 415 disturbances whose text says fight or assaulting | 165,370 |
| Someone with a gun or knife | 246 shooting at a home or car, 245 codes whose text says shots, 415 codes whose text says gun, knife or shots | 36,284 |
| Robbery | 211 (carjacking and purse snatching included) | 19,039 |
| Threats and harassment | 422 criminal threats, 314 indecent exposure (no 646 stalking codes in the data) | 26,646 |

Left out: calls marked domestic violence (242 or 245 with D after the number: 36,957), family or neighbor disputes
(620, never downloaded), and 558 calls with no district. These calls nearly all have a district (99.8%, against about
80% of all calls).

**Map layers**

- *High Injury Network* (on) — LA County's list, the corridors inside the City.
- *Violence & robbery reports* (on) — dots at LAPD's hundred blocks and corners, bigger = more.
- *Drug offenses* (off).
- *Car break-ins* (off) — dots, in their own color, as on SF Streets' driving side.
- *People walking hit* (off) — dots at the places the build worked out.
- *Calls to police* (off) — reporting districts shaded by calls per km² when zoomed out, the picked spot's district
  outlined.
- Neighborhoods shaded while the whole city shows (violence and robbery reports per km of street), as on SF Streets.
- The card's circle on top. What to tap is said on the map ("Tap the map to pick a spot") until something is picked.

**Summary** (the City as a whole, like SF Streets' walking summary)

- When people walking were hit: by month and hour, what they were doing (`PedestrianActionDesc`), causes, daylight or
  dark, the corners with the most.
- Violence and robbery reports by hour and by month.
- Around the places visitors go: a hand-kept list of about 24 places inside the City (Hollywood & Highland, Union
  Station, Grand Park, Crypto.com Arena, Little Tokyo, Olvera St, the Venice boardwalk, Griffith Observatory, The Grove,
  LACMA, Exposition Park, USC...). Only places inside the City where LAPD is the police: Santa Monica Pier, Universal
  CityWalk and SoFi aren't in the City, and LAX, UCLA and the port have their own police, so they're left out; so is
  the Hollywood Bowl, whose circle holds almost no streets. 26 places in `analyze_la.py` `PLACES`.
- The High Injury Network's share of the street length and of the people walking hit.
- Month by month from January 2025 (decision 4), not totals per year.

**Wording rules** (from SF Streets, Citina)

- Never claim 100% unless it's literally 100%; ranks are rounded down.
- Labels say literally what they mean.
- No "safe time" or "safe street" claims, and no "dangerous neighborhood" either: counts, ranks and what they depend on.
- The disclaimer is one short paragraph: built from LAPD's and the state's data, which miss what isn't reported; the
  explanations are the page's own reading of the data. "What the page loads" behind "More".
- Privacy lines promise only what the page does: "Show what's around me" puts the circle there, in the browser, kept out
  of the link.
- A term the reader meets is explained where it's used, or linked with a "?".
- No dataset IDs, NIBRS codes or radio codes on the page. Datasets named in the method are linked.
- How badly one person was hurt isn't shown for a small circle (it could point to someone), as on SF Streets. No victim
  age, sex or descent anywhere.

---

## 4. Build pipeline

```
fetch_la.py      data/raw/  (not committed)   downloads (DATA_SOURCES.md), police reports and calls a month at a time
analyze_la.py    docs/data/ (release asset)   index.json, streets.json, cells/{key}.json
hoods.json       docs/hoods.json (committed)  copied from ticket-clock/docs/streets/hoods.json
```

- **Cells**: per cell, the blocks and intersections (milestone 1, below), the report points `[x, y, kind counts
  daylight / dark, half hours]`, the crashes `[x, y, hour, severity, dark, cause]`, and the HIN lines in view.
- **Blocks and intersections** (built 2026-09-29): a block is one centerline segment (85,055, keyed by ASSETID), as on
  SF Streets, not LA Street Rules' hundred block cut from segments by address: the walking page needs the streets as a
  backdrop and a place to tap, not addresses to match tickets to. Each block keeps the house numbers at the two ends of
  its line, so a searched address lands at its place along the block. Intersections are the centerlines'
  `INT_ID_FROM` / `INT_ID_TO` where two or more streets meet (45,815), placed where most of their segments end; N and S
  Vermont Ave count as one street. They name the card's spot ("Near S Vermont Ave & W 36th St") and will be the places
  the ranks compare against. `streets.json`, for search, lists each street's hundred blocks, one per place, pointing
  into the cells, with the neighborhood where a street has the same hundred in two places (S Main St's 100 block in
  Downtown and in Venice): 873 KB, 273 KB gzipped.
- **Calls** (built 2026-09-29): `fetch_la.py` downloads only the codes the groups come from, a month at a time by
  `dispatch_date` (about 13,500 a month; the whole window in 50 s). `analyze_la.py` counts them per reporting district
  and group in daylight and after dark (from the dispatch time), with their half hours, into `districts.json` with the
  district outlines (simplified to 3 px; 750 KB, 209 KB gzipped), loaded with the first spot. Districts are ranked by
  calls per km² (median district 0.68 km²; median 227 calls per km², top 1% at least 5,285).
- **Placing crashes** (built 2026-09-29; CCRS rows without coordinates, 99.6% of LAPD's): the people walking hurt come
  from `InjuredWitnessPassengers` (`InjuredPersonType` Pedestrian), their crashes from `Crashes`, both queried on
  data.ca.gov (City Name Los Angeles), a year per file. A report sent twice keeps its last version. The crash goes
  where `PrimaryRoad` and `SecondaryRoad` meet in the centerlines: with the suffixes as written, then any suffix, then
  the second street spelled a little differently among those meeting the first (difflib, 0.85), then where the two
  come within 60 m without sharing an intersection. Names are normalized ("MLK JR BL" → Martin Luther King, Jr Blvd,
  "105 ST" → 105th St, "WEST BL" is West Blvd, not a direction). It then moves `SecondaryDistance` feet in
  `SecondaryDirection` along the primary road, block by block, or straight that way where the road doesn't run that
  way. A house number in either street field ("13520 PAXTON ST", "SUNLAND BL 10048") places it at the address along
  the block instead. Where the streets meet in places more than 150 m apart, LAPD's reporting district picks (its
  outlines from LA GeoHub), then the area in the report number, then the first when what's left is within 300 m.
  For 2025-01-01 to 2026-09-28: 2,599 people placed (95.7% of those off the freeways); left out 100 on a freeway, 100
  whose streets weren't found together, 17 whose streets meet in more than one place. Checked against LAPD's own
  coordinates for Jan–Mar 2025 (177 crashes matched by date and minute): half within 12 m, 75% within 50 m, 92% within
  200 m; the far ones traced were LAPD's point, not the placement. 57% of the people walking hit are on the High
  Injury Network or at its corners, on 7.9% of the street length.
- **Checking the state's crash data** (2026-09-29): for 2025-01-01 to 2025-03-08, LAPD's own feed has 312 crashes with
  a pedestrian (MO code 3003) and CCRS 297 LAPD crashes with someone walking hurt, 95% (decision 5). The method says so.
- **Police reports** (built 2026-09-29): `fetch_la.py` downloads only the page's NIBRS codes, a month at a time by
  `date_occ` (about 7,500 offenses a month; the whole window in 30 s). `analyze_la.py` keeps offenses from 2025-01-01
  (or two years back) to the last day with at least half a typical day's count, then leaves out, in this order:
  domestic violence (LAPD's flag, then descriptions of partner violence the flag missed: IPV, intimate partner,
  spousal, 273.5), places that aren't public (`place_kind`: homes first, then a list of public premises; the rest,
  like businesses, hotels, schools, hospitals and a vehicle with no place, is "other"), rows with no place, and a
  second offense of the same kind in the same report. Each report place (LAPD's rounded point) keeps its counts per
  kind in daylight / after dark / no time, and its half hours. For 2025-01-01 to 2026-09-18: 84,854 reports at 22,344
  places; left out 29,021 in homes, 26,870 flagged domestic violence plus 439 by description, 12,361 elsewhere, 250
  without a place, 2,681 second offenses. The build prints the home and "other" premises it left out, to check the
  lists against.
- **Ranks**: the circle's counts against a circle the same size around every intersection in the City (quantiles per
  radius, as `circle_q` in SF Streets): each intersection's report places within 500 m, nearest first with running
  totals, so every radius is one cut. At 200 m half the intersections have 2 or fewer reports of violence and robbery,
  the top 1% at least 76.
- **Daylight / after dark**: from the sun's times in LA on each date, as in SF.
- **Unknown times**: LAPD writes 00:00 or 12:00 when the time isn't known (10,033 and 9,083 reports since 2025, far
  above their neighbors). Those count in totals but not in hour charts or daylight / dark.
- **Weekly** (`weekly.yml`, Mondays, written 2026-09-30): restore last week's downloads from the `la-downloads`
  release (data/raw/, 31 MB packed; a release, not the Actions cache, which drops what's unused for 7 days), fetch,
  keep the downloads, analyze, check the counts against the `la-data` release's notes (a drop of more than 10% in
  reports, people walking hit or calls stops it), publish docs/data/ as the `la-data` release (6 MB packed), then start
  `pages.yml`, which puts the release into docs/data/ and deploys Pages. Nothing in docs/data/ is committed.
- **Dates** (Citina, 2026-09-30): a menu over the map picks the dates the map and the card count: since January 2025,
  the last 12 months, 90 days or 30 days, or the last full calendar month. Every report, crash and call keeps its day
  (reports as one number with their half hour and kind, calls in a file per district), and each dataset counts back
  from its own last day. Neighborhood and district shading follow it (`hood_range`, districts' `r`); the ranks and the
  summary stay on the whole window. For dates within six months of the last crash report, the card says the crashes
  are still coming in.
- **Lag**: LAPD's reports run about two weeks behind (latest 2026-09-18 on 2026-09-30); calls about a week; the state's
  crash reports have crashes to a day or two ago, but LAPD's reports reach it late (half within 33 days, 85% within 90),
  so recent months fill in for half a year. Each part of the page states its own dates.

---

## 5. Milestones

- [x] **0. Plan** — this file, DATA_SOURCES.md, README (2026-09-27).
- [x] **1. Map** — LA Street Rules' map, search and neighborhoods, walk-mode card shell from SF Streets, the circle
  (2026-09-29). `fetch_la.py` downloads the centerlines, `analyze_la.py` builds the blocks, intersections and search
  list (about 10 s), and `docs/index.html` has the map, search (street, address, neighborhood), "Show what's around
  me", the circle and its slider, the link (`#@lat,lon/200m`), and the card named by the nearest intersection. The
  card's three rows and the layer chips say "still to come".
- [x] **2. Police reports** — fetch, kinds, cells, the card's first row, ranks, the layer (2026-09-29). The card's
  "Reported to police" row (the six kinds that open to a note and a half-hour dot chart, a rank line each for violence
  and robbery, drug offenses and car break-ins, the hour chart, after dark and no time recorded); When chips (any time,
  daylight, after dark); three layers (violence and robbery on, drug offenses and car break-ins off); neighborhoods
  shaded by violence and robbery per km of street; the method's police, after dark and limits rows; after a search on
  a phone, the short answer above the map.
- [x] **3. High Injury Network** — the layer and the card's line (2026-09-29). LADOT's 2024 network for people walking
  (551 miles), not the county's: the county hub publishes each city's ranked road windows with no cut-off, while LADOT
  publishes the City's own network, with one for people walking. 7,845 blocks are on it (a block is on it when most of
  it is within 20 m of an HIN line of the same street name; 99.2% of LADOT's lines are covered). Drawn under the dots
  (on to start), named in the card's last row, with a "?" to the note under the map and a method row.
- [x] **4. People walking hit** — CCRS fetch, placing by street names, the check against LAPD's feed, the card's row
  (2026-09-29). 2,599 people walking hurt or killed in 2,464 crashes from 2025-01-01 to 2026-09-28, 95.7% of those off
  the freeways placed; the card's row (count, HIN streets, rank, hour chart, after dark, top causes) and a map layer
  (off to start). Severity isn't shown for a circle.
- [x] **5. Calls to police** — reporting districts, groups, the card's row and layer (2026-09-29). 247,339 calls from
  2025-01-01 to 2026-09-25 in 1,131 of 1,135 districts; the card's second row counts the spot's district (its size,
  the four groups with notes and dot charts, the rank per km² among districts, the hour chart, after dark) and outlines
  it on the map while open; the layer (off to start) shades every district by these calls per km², in place of the
  neighborhood shading when zoomed out.
- [x] **6. Summary** — the city as a whole, places (2026-09-29). A section under the map: a headline and four numbers
  (people walking hit, killed and badly hurt, the share crossing in a crosswalk, the share of the killed hit after
  dark: 79%); people walking hit and reports of violence and robbery month by month from January 2025 (decision 4; the
  last six months of crashes and the current month of reports faded) and by hour; 26 places visitors go, with their
  200 m counts and ranks, sortable; the neighborhoods with the most violence and robbery and the most people walking hit
  per km of street; the intersections where the most were hit; what the people hit were doing and the main causes; a
  note on why the page starts in 2025. The City totals count every crash off the freeways, placed or not (2,716
  people, 215 killed, 1,003 badly hurt).
- [x] **7. Automation** — `weekly.yml`, `pages.yml`, GitHub Pages. Live since 2026-09-30: the first run passed in
  3.5 minutes and published the `la-data` and `la-downloads` releases, and Pages deploys from Actions. Runs on Python
  3.12, since Ubuntu 26 (`ubuntu-latest` from October 19, 2026) has no 3.9; the files match the laptop's 3.9 build.
- [x] **Dates menu** — the date range for the map and the card (Citina, 2026-09-30); see §4.
- [ ] **8. Sister sites** — add it to the masthead and About cards of the other four pages.

---

## 6. Open decisions

1. **Name.** Working title "LA Walking" (repo `citina/la-walking`; GitHub keeps redirects if it's renamed).
2. **Which reports count.** Settled 2026-09-29 (Citina): only reports in public places (street, sidewalk, alley,
   park, parking lot, transit, stores and restaurants), leaving out homes and apartments, since the page is about being
   out on foot. The build groups LAPD's premises into public place / home / other and says in the method which count.
   Reports of domestic violence are left out wherever they happened (LAPD's flag, and partner violence the flag
   missed), and threats (13C) go in "Assault and other violence" (both Citina, 2026-09-29). Homeless encampments count
   as public places, not a kind of their own: LAPD names the premise "Transient Encampment" on only 72 counted reports
   since Jan 2025, at 62 places, too few for a row or a layer, and reports at an encampment on a sidewalk are often
   filed as "Sidewalk" (Citina, 2026-09-29). Homeless shelters count as homes.
3. **Calls to police at district level.** Settled 2026-09-29 (Citina): kept, as a district line on the card and a
   shaded layer, not a circle count. About 20% of calls have no district.
4. **Totals per year.** Settled 2026-09-29 (Citina): a chart from 2025 only, month by month. LA's old crime data
   (2020–2024) counts crimes differently from NIBRS (one crime per report, against every offense in an incident), and
   2024 is split between the two: the old dataset falls from about 19,000 crimes a month in January 2024 to 4,700 in
   December, while the new one grows from a few hundred offenses to 11,000–14,000 and reaches 18,000 only in 2025.
5. **Crash data completeness.** Checked 2026-09-29: for 2025-01-01 to 2025-03-08, LAPD's own feed has 312 crashes with a
   pedestrian (MO 3003) and CCRS 297 LAPD crashes with someone walking hurt, 95%. So crashes are shown as counted, not
   "at least". What CCRS does miss is recent months: LAPD's reports reach it late (half within 33 days, 85% within 90,
   94% within 180), so the method and the card say the last few months are still coming in. Switch to LAPD's new
   collision dataset if it's published.
