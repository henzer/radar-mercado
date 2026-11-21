# Market radar

Personal dashboard: Nasdaq-100 and Technology trend vs. their 200-day average,
rotation of the 11 sectors and 14 thematic ETFs vs. the S&P 500, VIX, credit spreads and hedge fund
positioning (CFTC). Includes a training simulator to practice sector rotation week by week.

- `scripts/update.py` downloads public data from FRED and CFTC and writes `data.json` and `sim.json`.
  Days FRED has not published yet (it does not publish on weekends) are filled from Yahoo and
  marked provisional until FRED catches up.
- `scripts/themes.py` downloads the thematic ETFs (adjusted closes) from Yahoo and writes
  `themes.json` and `themes.csv`. If Yahoo fails, the previous files are kept.
- `.github/workflows/update.yml` runs both Monday to Friday (22:30 UTC) and on Saturday (14:00 UTC)
  and commits the result. You can also run it manually from
  **Actions → Update data → Run workflow**.
- `index.html` is the dashboard page (GitHub Pages) that reads `data.json` and `themes.json`.
- `simulador.html` is the training simulator that reads `sim.json`.

Informational tool; not financial advice.
