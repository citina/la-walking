# LA Walking — plan

Working title. A map of the City of Los Angeles for people on foot, in the style of the walking side of
[SF Streets](https://citina.github.io/sf-streets/#walk):

- *Around a spot I pick, what gets reported to police, what do people call police about, and how often are people
  walking hit by cars, when and why?*

Only the walking question. The driving question ("can I park here?") was looked at for LA on 2026-09-27 and dropped:
LA doesn't publish its curb rules (meter hours, time limits, permit hours, tow-away, closures), so the answer would rest
on guesses. LA Street Rules keeps the parking side, from tickets.

Written 2026-09-27. Milestone 1 (the map, search and the card's shell) built 2026-09-29; see §5.

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
time control    When [Any | Daylight | After dark]   Within [100–500 m slider, 200 m to start]
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

1. **Reported to police** — the five kinds (below), most first, then car break-ins; tap a kind for what it covers and,
   with 10 or more, its half-hour dot chart; ranks against every intersection (violence and robbery, drug offenses and
   car break-ins each ranked on their own); an hour chart and how many after dark. Note: "Reports are placed at the
   hundred block or corner LAPD gives. Counts also depend on where police patrol and who calls."
2. **Calls to police** — not a circle count: "In this police reporting district (about 1.2 km²): 312 calls about fights
   and assaults since Jan 2025", per group, with the rank among the 1,135 districts and the hour chart. The district is
   drawn on the map when this row is open. Note: "A call is what someone reported, not what police found. LAPD gives
   only the district." (open decision 3)
3. **People walking hit** — "16 people walking hit since Jan 2025" and "3 badly hurt or killed", big number first; the
   High Injury Network streets through the circle (with a "?" to its explanation); the rank; the hour chart; after dark;
   the top causes in plain words.

Before a spot is picked the card is one line. After a search on a phone, the message above the map gives the short
answer and "See the card ↓", as on SF Streets.

**Police report kinds** (NIBRS codes; counts are 2025-01-01 to 2026-09-05, all premises)

| Kind | NIBRS codes | Count |
|---|---|---|
| Robbery | 120 | 11,995 |
| Assault and other violence | 13A aggravated assault, 13B simple assault, 09A murder, 11A–11D sex offenses | 79,039 |
| Pickpocketing and purse snatching | 23A, 23B | 2,516 |
| Weapons | 520 | 5,600 |
| Drug offenses | 35A, 35B | 12,595 |
| Car break-ins | 23F | 31,539 |

Threats (13C, 7,925) aren't in SF's kinds; still open (decision 2). Car break-ins are on this page (Citina, 2026-09-29, in
place of LA Street Rules' block card): SF Streets has them on its driving side, and LA Walking is LA's only page for
police reports. They're their own kind and their own map layer, counted apart from violence and robbery.

**Call groups** (by LAPD's radio code, officers' own calls left out: `006` "Code 6", 1.18M, and `902` traffic stops,
183k, of 2.55M since Jan 2025). The exact code lists are settled at build time from the code table, as SF's
`CALL_GROUPS` were:

| Group | Radio codes (start) |
|---|---|
| Fights and assaults | 242 battery, 245 assault with a deadly weapon (not shots), 415F fight |
| Someone with a gun or knife | 246 shots fired / heard, 245FJ shots fired, 415M6 man with knives, 417 |
| Robbery | 211 |
| Threats and harassment | 422 threats, 646 stalking, 314 indecent exposure |

Left out, as in SF: calls marked domestic violence (620D, 242D, 620DR) and family or neighbor disputes (620x).

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
  LACMA, Exposition Park, USC, UCLA, LAX...). Only places inside the City: Santa Monica Pier, Universal CityWalk and SoFi
  aren't LAPD's.
- The High Injury Network's share of the street length and of the people walking hit.
- Totals per year: open decision 4.

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
- **Calls**: per reporting district, calls per group (daylight / dark) and their half hours; the district outlines in
  a separate file loaded when the calls row or layer opens.
- **Placing crashes** (CCRS rows without coordinates): find the intersection of `PrimaryRoad` and `SecondaryRoad` in the
  centerlines (names normalized like the ticket addresses on LA Street Rules: "MARTIN LUTHER KING BL" → Martin Luther
  King Jr Blvd), then move `SecondaryDistance` feet in `SecondaryDirection` along the primary road. Where two
  intersections match (long streets that cross twice), use the reporting district or the crash's city beat to pick.
  Report the share placed; crashes that don't place are counted in the city totals only. Rows with coordinates (CHP and
  other agencies) are used as they are. Freeway crashes are left out.
- **Checking the state's crash data** before trusting it: for Jan–Feb 2025, LAPD's own feed has 283 crashes with a
  pedestrian (MO code 3003) and CCRS has 254 LAPD crashes with a pedestrian, about 90%. Match the two by date, time and
  streets to see which ones are missing, and say so in the method.
- **Ranks**: the circle's counts against a circle the same size around every intersection in the City (quantiles per
  radius, as `circle_q` in SF Streets), computed with a KD-tree.
- **Daylight / after dark**: from the sun's times in LA on each date, as in SF.
- **Unknown times**: LAPD writes 00:00 or 12:00 when the time isn't known (10,033 and 9,083 reports since 2025, far
  above their neighbors). Those count in totals but not in hour charts or daylight / dark.
- **Weekly** (`weekly.yml`, Mondays): fetch, analyze, check the counts against last week's (a drop of more than 10% stops
  it), publish `docs/data/` as the `la-data` release, deploy Pages. Months already downloaded are kept in the Actions
  cache; a month is downloaded again when it's one of the last two or its copy is over four weeks old.
- **Lag**: LAPD's reports run about two weeks behind (latest 2026-09-05 on 2026-09-27); calls about a week; CCRS about a
  week. Each part of the page states its own "through" date.

---

## 5. Milestones

- [x] **0. Plan** — this file, DATA_SOURCES.md, README (2026-09-27).
- [x] **1. Map** — LA Street Rules' map, search and neighborhoods, walk-mode card shell from SF Streets, the circle
  (2026-09-29). `fetch_la.py` downloads the centerlines, `analyze_la.py` builds the blocks, intersections and search
  list (about 10 s), and `docs/index.html` has the map, search (street, address, neighborhood), "Show what's around
  me", the circle and its slider, the link (`#@lat,lon/200m`), and the card named by the nearest intersection. The
  card's three rows and the layer chips say "still to come".
- [ ] **2. Police reports** — fetch, kinds, cells, the card's first row, ranks, the layer.
- [ ] **3. High Injury Network** — the layer and the card's line.
- [ ] **4. People walking hit** — CCRS fetch, placing by street names, the check against LAPD's feed, the card's row.
- [ ] **5. Calls to police** — reporting districts, groups, the card's row and layer (if decision 3 keeps them).
- [ ] **6. Summary** — the city as a whole, places.
- [ ] **7. Automation** — `weekly.yml`, `pages.yml`, GitHub Pages.
- [ ] **8. Sister sites** — add it to the masthead and About cards of the other four pages.

---

## 6. Open decisions

1. **Name.** Working title "LA Walking" (repo `citina/la-walking`; GitHub keeps redirects if it's renamed).
2. **Which reports count.** Settled 2026-09-29 (Citina): only reports in public places (street, sidewalk, alley,
   park, parking lot, transit, stores and restaurants), leaving out homes and apartments, since the page is about being
   out on foot. The build groups LAPD's premises into public place / home / other and says in the method which count.
   Still open: reports flagged domestic violence that happened in a public place (recommended: leave out, as SF's calls
   leave out domestic violence), and threats (13C): in "Assault and other violence", as their own kind, or left out?
3. **Calls to police at district level.** Keep them as a district line on the card and a shaded layer, or drop them?
   About 20% of calls have no district.
4. **Totals per year.** SF Streets shows totals per year since 2018. LA's old crime data (2020–2024) counts crimes
   differently from NIBRS (one crime per report, against every offense in an incident), and 2024 is split between the
   two. Options: a chart from 2025 only; or yearly totals with a marked break at 2024; or none.
5. **Crash data completeness.** If CCRS turns out to miss a lot of LAPD's crashes, show crashes as "at least" or wait
   for LAPD's new collision dataset (announced, not yet published).
