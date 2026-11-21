"""Downloads public data (FRED + CFTC; Yahoo fills days FRED has not published yet) and builds:
  - data.json : dashboard (since 2021)
  - sim.json  : training simulator (11 sectors + market, since 2011)

No external dependencies: Python standard library only.
Usage:  python scripts/update.py
"""
import csv
import datetime as dt
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

START = "2021-01-01"      # dashboard: buffer for the 40-week average from 2022
SIM_START = "2011-05-01"  # simulator: full available sector history
UA = {"User-Agent": "Mozilla/5.0 (mercado-dashboard; GitHub Actions)"}

# display name -> FRED id
FRED = {
    "S&P 500": "SP500",
    "Nasdaq-100": "NASDAQ100",
    "Semis (SOX)": "NASDAQSOX",
    "Technology": "NASDAQNQUSB10",
    "Telecom": "NASDAQNQUSB15",
    "Health Care": "NASDAQNQUSB20",
    "Financials": "NASDAQNQUSB30",
    "Real Estate": "NASDAQNQUSB35",
    "Consumer Discretionary": "NASDAQNQUSB40",
    "Consumer Staples": "NASDAQNQUSB45",
    "Industrials": "NASDAQNQUSB50",
    "Materials": "NASDAQNQUSB55",
    "Energy": "NASDAQNQUSB60",
    "Utilities": "NASDAQNQUSB65",
}
EXTRA = {"VIX": "VIXCLS", "HY spread": "BAMLH0A0HYM2"}
SECTORS = [n for n, sid in FRED.items() if sid.startswith("NASDAQNQUSB")]
SIM_MARKET = ("US Market", "NASDAQNQUSB")  # Nasdaq US Benchmark (total market)

COT_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
COT_CODE = "209742"  # E-mini Nasdaq-100


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8")
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  retry {i + 1} ({e})", file=sys.stderr)
            time.sleep(5 * (i + 1))


def fred_daily(series_id, start):
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv?"
        + urllib.parse.urlencode({"id": series_id, "cosd": start})
    )
    rows = csv.reader(io.StringIO(get(url)))
    next(rows)
    out = {}
    for d, v in rows:
        if v not in ("", "."):
            out[d] = float(v)
    return out


def yahoo_symbol(series_id):
    """Yahoo Finance symbol for a FRED series, or None when Yahoo has no equivalent."""
    if series_id.startswith("NASDAQNQUSB"):
        return "^" + series_id[len("NASDAQ"):]  # NASDAQNQUSB10 -> ^NQUSB10
    return {"SP500": "^GSPC", "NASDAQ100": "^NDX", "NASDAQSOX": "^SOX", "VIXCLS": "^VIX"}.get(series_id)


def yahoo_recent(symbol):
    """Daily closes for the last month from Yahoo, skipping a session that is still open."""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(symbol) + "?range=1mo&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)["chart"]["result"][0]
    meta = res["meta"]
    off = meta.get("gmtoffset", 0)
    reg = meta.get("currentTradingPeriod", {}).get("regular", {})
    now = time.time()
    out = {}
    for ts, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]):
        if c is None:
            continue
        if reg and reg.get("start", 0) <= ts < reg.get("end", 0) and now < reg["end"]:
            continue  # today's session has not closed yet
        out[dt.datetime.fromtimestamp(ts + off, dt.timezone.utc).date().isoformat()] = c
    return out


def fill_from_yahoo(name, series_id, daily, provisional):
    """Adds the days FRED has not published yet (FRED does not publish on weekends).
    FRED stays the source for everything it has; the next run replaces these days."""
    sym = yahoo_symbol(series_id)
    if not sym or not daily:
        return
    try:
        recent = yahoo_recent(sym)
    except Exception as e:  # noqa: BLE001 - Yahoo is optional
        print(f"  Yahoo {sym} unavailable ({e}); keeping FRED only", file=sys.stderr)
        return
    last = max(daily)
    new = {d: v for d, v in recent.items() if d > last}
    if new:
        daily.update(new)
        provisional[name] = sorted(new)
        print(f"  + Yahoo {sym}: {', '.join(sorted(new))} (provisional)")


def week_key(d):
    y, w, _ = dt.date.fromisoformat(d).isocalendar()
    return (y, w)


def to_weekly(daily):
    """Last value of each ISO week -> {last_data_date: value}."""
    last = {}
    for d in sorted(daily):
        last[week_key(d)] = (d, daily[d])
    return dict(sorted(last.values()))


def align(weekly, weeks):
    """Aligns a weekly series to a calendar; fills gaps with the previous value."""
    by_week = {week_key(d): v for d, v in weekly.items()}
    vals, prev = [], None
    for k in weeks:
        v = by_week.get(k, prev)
        vals.append(None if v is None else round(v, 2))
        prev = v if v is not None else prev
    return vals


def write(root, name, data):
    path = os.path.join(root, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"OK -> {path} ({len(data['labels'])} weeks, last data {data['labels'][-1]})")


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    weekly_all, provisional = {}, {}
    for name, sid in {**FRED, **EXTRA, SIM_MARKET[0]: SIM_MARKET[1]}.items():
        start = SIM_START if (name in SECTORS or name == SIM_MARKET[0]) else START
        print(f"FRED {sid} ({name}) from {start}")
        daily = fred_daily(sid, start)
        fill_from_yahoo(name, sid, daily, provisional)
        weekly_all[name] = to_weekly(daily)

    # ---- dashboard (from START), S&P 500 calendar
    weekly = {n: {d: v for d, v in w.items() if d >= START}
              for n, w in weekly_all.items() if n != SIM_MARKET[0]}
    spx = weekly["S&P 500"]
    weeks = [week_key(d) for d in spx]
    labels = list(spx)
    series = {name: align(w, weeks) for name, w in weekly.items()}

    print("CFTC COT Nasdaq-100")
    q = urllib.parse.urlencode({
        "cftc_contract_market_code": COT_CODE,
        "$select": "report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short",
        "$where": f"report_date_as_yyyy_mm_dd >= '{START}'",
        "$order": "report_date_as_yyyy_mm_dd",
        "$limit": "5000",
    })
    cot_rows = json.loads(get(f"{COT_URL}?{q}"))
    cot = {"date": [], "long": [], "short": []}
    for r in cot_rows:
        cot["date"].append(r["report_date_as_yyyy_mm_dd"][:10])
        cot["long"].append(int(float(r["lev_money_positions_long"])))
        cot["short"].append(int(float(r["lev_money_positions_short"])))

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    write(root, "data.json", {
        "updated": now, "last_week": labels[-1], "labels": labels,
        "series": series, "cot": cot, "provisional": provisional,
    })

    # ---- simulator (from SIM_START), total market calendar
    mkt = weekly_all[SIM_MARKET[0]]
    sweeks = [week_key(d) for d in mkt]
    write(root, "sim.json", {
        "updated": now, "labels": list(mkt),
        "series": {n: align(weekly_all[n], sweeks) for n in [*SECTORS, SIM_MARKET[0]]},
    })


if __name__ == "__main__":
    main()
