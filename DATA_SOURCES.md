# LA Walking — data sources

What the page will be built from, what each dataset is for, and what was looked at and left out. Checked 2026-09-27.
Only datasets with **a place for each row** (coordinates, a line or shape, or a key that places it) and **data from the
last three years** are listed as in use. Counts are from 2025-01-01 unless noted.

The window starts on **2025-01-01**, when LAPD's new records (NIBRS) are complete, and grows until it reaches two years,
then rolls (PLAN.md §1).

## To use

| Dataset | Where | ID | For | Notes |
|---|---|---|---|---|
| LAPD NIBRS Offenses Dataset | data.lacity.org | `k7nn-b2ep` | "Reported to police": the five kinds and car break-ins, their half hours, daylight or dark, ranks; the map's report dots; neighborhood shading; the summary | ~18k offenses a month since 2025; runs ~2 weeks behind. One row per offense (`uniquenibrno`), so an incident with a robbery and an assault counts once in each kind. Place: `hndrdth_lat`/`hndrdth_lon`, rounded by LAPD to the hundred block or intersection (`hndrdth_loc_chk`); 99.97% have one. Also `premis_desc` (only public places count, decision 2), `domestic_violence_crime` (left out when Yes: 26,870 of the page's kinds in the window, and 439 more whose `nibr_description` is partner violence), `weapon_desc`, `victim_shot`. `time_occ` 0000 and 1200 mean no time known. Renamed and merged on 2026-08-18 (it now holds every NIBRS record since 2024-03-07); `y8y3-fqfu` (2024–2025) stopped updating then |
| LAPD Calls for Service 2024 to Present | data.lacity.org | `xjgu-z4ju` | "Calls to police" per reporting district and group, with half hours | 2.55M calls since 2025, ~125k a month, ~1 week behind. Only `area_occ` and `rpt_dist` (a reporting district, 80% have one), `dispatch_date`/`time`, `call_type_code`/`text`. No coordinates and no field for who called: officers' own calls are left out by code (`006` Code 6, `902` traffic stop). Suffixes on the codes: SN suspect now, S suspect gone, PS possible suspect, J/O just occurred, A ambulance |
| LAPD Reporting District | LA GeoHub (`services5.arcgis.com/7nsPwEMP38bSkCjy/.../LAPD_Reporting_District/FeatureServer`, item 924f1b2e8df642f38a6dcbcf3c7b1709) | — | The outlines the calls are counted in | Updated 2026-07-21. 1,135 districts in the calls data |
| California Crash Reporting System (CCRS): Crashes, Parties, InjuredWitnessPassengers | data.ca.gov, package `ccrs` (CKAN datastore; `Crashes_2025` is `9f4fc839-122d-4595-a146-43bc4ed16f46`, `Crashes_2026` is `b8ce0ca4-b4e9-490d-b4d1-1f4ec48cbefb`) | — | "People walking hit": count, badly hurt or killed, time, daylight or dark, what they were doing, cause; the summary | City of LA rows (`City Name` = Los Angeles); LAPD is `NCIC Code` 1942. With a pedestrian (`PedestrianActionCode` not A): 1,811 LAPD crashes in 2025, 138 people killed; 1,067 in 2026 through Sep 24. **99.5% of LAPD's rows have no coordinates**: placed from `PrimaryRoad`, `SecondaryRoad`, `SecondaryDistance`, `SecondaryDirection` (PLAN.md §4). CHP's rows in the City (freeways, mostly) have coordinates and few pedestrians. Severity from the injured persons' extent of injury. Cause from `Primary Collision Factor Violation` (a Vehicle Code section, e.g. 21950A driver didn't yield to someone in a crosswalk) in plain words. About 90% of LAPD's own count for Jan–Feb 2025: check before trusting (PLAN.md §4) |
| LA County High Injury Network | LA County (hub `hin-lacounty.hub.arcgis.com`, updated Sep 2026) | — | The HIN layer, the card's list of HIN streets in the circle, its share of streets and of people walking hit | Covers the whole county, the City included. Its working layer `Merged_SlidingWindows20` (74,598 road windows, 31,587 in the City, with killed and seriously injured counts; `hin` numbers the corridors) is public; pick the published corridor layer at build time and write down its method in the page's method row |
| Street centerlines | LA GeoHub, `maps.lacity.org/lahub/rest/services/Street_Information/MapServer/36` | — | Blocks, intersections (for naming the card's spot, for ranks and for placing crashes), street search | 85,192 segments (2026-09-29), with address ranges and the intersection at each end. The same download as `ticket-clock/fetch_city.py`. No freeways. 42 are marked outside the City and left out. `STATUS` W marks 234 walkways (Ocean Front Walk, Venice's canal paths and walk streets, the Marina's pedestrian malls); they're kept |
| LA Times neighborhoods | DataLA item d6c55385a0e749519f238b77135eafac | — | Neighborhood outlines, search, the tag naming the one in view, shading | CC BY 4.0. Copied from `ticket-clock/docs/streets/hoods.json` (113 of 114) |
| OpenStreetMap tiles | tile.openstreetmap.org | — | The map images | Loaded by the reader's browser, only for the part on screen |

## Maybe later

| Dataset | ID | Could be used for |
|---|---|---|
| LAPD NIBRS Victims Dataset | `gqf2-vm2j` | How many people were hurt per report (`totalvictimcount` is already in the offenses). Victim age, sex and descent stay out |
| Calls with code `904AP` "904 AMB PEDESTRIAN I" | `xjgu-z4ju` | Ambulance calls for a person walking hurt (4,634 since 2025), per district: a second, faster count of people walking hit to set beside the crash reports |
| Traffic Collision Data from 2010 to Present | `d5tf-ez2w` | Stopped 2025-03-08 when LAPD moved crash reports to its new system. Used only for the CCRS check (Jan–Mar 2025). LAPD says a new collision dataset will be published: switch to it when it is |
| LADOT High Injury Network (2015) | ArcGIS `hin_082015` | The City's own list, from 2015. Only if the county's turns out not to fit |

## Looked at and not used

| Dataset | ID | Why not |
|---|---|---|
| Crime Data from 2020 to 2024 | `2nrs-mtv8` | LAPD's old records system, which ended with 2024 (its last months are partial, as reports moved to NIBRS). Different categories from NIBRS. Only for yearly totals if open decision 4 wants them |
| Crime Data from 2010 to 2019 | `63jg-8b9z` | Older still |
| LAPD NIBRS Offenses Dataset 2024 to 2025 | `y8y3-fqfu` | Stopped 2026-08-18; merged into `k7nn-b2ep` |
| Arrest Data from 2020 to 4/30/2025 | `amvf-fr72` | Ends Apr 2025, and arrests show where police patrol, not what happens to people walking |
| Domestic Violence Calls from 2020 to Present | `qq59-f26t` | A view of the old crime data; and in homes, not on the street |
| LAPD Calls for Service 2014–2023 | yearly datasets (`uq7m-rynj` 2023...) | Before the window |
| Traffic Collision Data 01Jan2015-31May2017 VistaDelMar-Imperial-Culver, Pedestrian Collisions at 84th and Hoover, and similar | `6tkk-tfyj`, `9i5w-vk8b`... | Filtered views of `d5tf-ez2w` for one place |
| LA County Road Closures | pw.lacounty.gov/roadclosures | Unincorporated county roads only, not the City's streets; a web page, no data feed |

Some links are charts of another dataset, so the dataset behind them is what counts:

| Link | Is a view of | Status |
|---|---|---|
| `fs5a-69wz` Types of Crime and their Amount in Areas within City of Los Angeles, 2020 to Present | `2nrs-mtv8` (old crime data, 2020–2024) | Not used: it stops with 2024. The same breakdown (kinds by LAPD area) comes from `k7nn-b2ep` for 2025 on, and could go in the summary |
| `hikj-664h` Crime in Los Angeles in 2020 Bar Chart | `2nrs-mtv8` | Not used: 2020 only. Yearly totals are open decision 4 |

## Numbers behind the plan (2025-01-01 to 2026-09-05 unless noted)

- NIBRS offenses by kind: simple assault 50,066; aggravated assault 25,002; robbery 11,995; drug possession 9,043 and
  paraphernalia 3,552; threats 7,925; weapons 5,600; sex offenses 3,614; pickpocketing 1,992; purse snatching 524;
  murder 357. Car break-ins (BFMV, 23F) 31,539, of which 11,707 on a street or parkway.
- Of the 100,211 reports of violence, robbery, pickpocketing and weapons, about a third (32,492) were in a home or
  apartment, and 24,862 were flagged domestic violence (a quarter). On a street, sidewalk, road or alley: 35,753.
- Premise names are LAPD's (`premis_desc`); the build groups them into public place / home / other.
