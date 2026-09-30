# LA Walking

A map of the City of Los Angeles for people on foot. Pick a spot on the map, an address or where you are, and a distance
(100 to 500 m). The page shows what gets reported to police around it, what people call police about nearby, and how
often people walking have been hit by cars there, when and why. It also shows the High Injury Network streets, LA's list
of the streets where people are most often killed or badly hurt.

The sister page to the walking side of [SF Streets](https://citina.github.io/sf-streets/) ([sf-streets](https://github.com/citina/sf-streets)),
and built the same way as [LA Street Rules](https://citina.github.io/ticket-clock/streets/)
([ticket-clock](https://github.com/citina/ticket-clock)): one hand-written page, no map library, data split into small
map cells, rebuilt weekly. All from public data: LAPD on [data.lacity.org](https://data.lacity.org), California's crash
reports on [data.ca.gov](https://data.ca.gov), and LADOT's High Injury Network.

**Status:** milestone 6 of 8, not published yet. The map, search, the card's circle, LAPD's reports in public places,
calls to police, the High Injury Network, people walking hit and the citywide summary work; the weekly rebuild and
publishing are still to come. See [PLAN.md](PLAN.md) for how it will work and what's still
open, and [DATA_SOURCES.md](DATA_SOURCES.md) for which dataset is used for what and which were left out.

Working title; the name is still open (PLAN.md §6).

## Run it

```
python3 fetch_la.py      # LA GeoHub, data.lacity.org and data.ca.gov -> data/raw/ (the street centerlines, about
                         # 76 MB; LAPD's reports and calls since 2025, about 50 MB; the High Injury Network, the
                         # reporting districts and the state's crash reports, about 8 MB; a few minutes the first time)
python3 analyze_la.py    # data/raw/ -> docs/data/ (about 35 seconds)
python3 -m http.server 8766 --directory docs
```

then open http://localhost:8766/. Python 3.9 or later, no packages beyond the standard library.

On GitHub, `.github/workflows/weekly.yml` does the same every Monday and publishes docs/data/ as the `la-data` release
(it isn't committed); `pages.yml` puts that release into docs/data/ and deploys the page.

## Who made this

Made by [Citina Liang](https://github.com/citina), a PhD candidate in Industrial & Systems Engineering at USC Viterbi who
models how people behave and how diseases spread.
