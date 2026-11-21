"""Downloads thematic ETF prices from Yahoo Finance and builds:
  - themes.json : weekly adjusted closes for the dashboard's Themes section
  - themes.csv  : the same data, for download

Prices are adjusted closes (dividends included), last close of each ISO week.
If any download fails, the script exits with an error and leaves the previous
files untouched, so the dashboard keeps the last good data.

No external dependencies: Python standard library only.
Usage:  python scripts/themes.py
"""
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

START = "2011-01-01"
BENCHMARK = ("S&P 500 ETF", "SPY")
THEMES = [  # (name, ETF ticker)
    ("Artificial Intelligence", "AIQ"),
    ("Robotics & Automation", "ROBO"),
    ("Semiconductors", "SMH"),
    ("Cloud Computing", "SKYY"),
    ("Data Centers", "DTCR"),
    ("Power Grid", "GRID"),
    ("Nuclear & Uranium", "NLR"),
    ("Cybersecurity", "CIBR"),
    ("Aerospace & Defense", "XAR"),
    ("Space", "UFO"),
    ("Quantum Computing", "QTUM"),
    ("Clean Energy", "QCLN"),
    ("Biotech", "XBI"),
    ("Blockchain", "BLOK"),
]
REFERENCE = ("Small Caps", "IWM")  # shown last, as a yardstick for small-cap themes


def yahoo_daily(ticker, tries=3):
    """Daily adjusted closes since START, skipping a session that is still open."""
    p1 = int(dt.datetime.fromisoformat(START).replace(tzinfo=dt.timezone.utc).timestamp())
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(ticker)
           + "?" + urllib.parse.urlencode({"period1": p1, "period2": int(time.time()), "interval": "1d"}))
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r)["chart"]["result"][0]
            break
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise RuntimeError(f"Yahoo {ticker}: {e}") from e
            print(f"  retry {i + 1} {ticker} ({e})", file=sys.stderr)
            time.sleep(5 * (i + 1))
    meta = res["meta"]
    off = meta.get("gmtoffset", 0)
    reg = meta.get("currentTradingPeriod", {}).get("regular", {})
    now = time.time()
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    out = {}
    for ts, c in zip(res["timestamp"], adj):
        if c is None:
            continue
        if reg and reg.get("start", 0) <= ts < reg.get("end", 0) and now < reg["end"]:
            continue  # today's session has not closed yet
        out[dt.datetime.fromtimestamp(ts + off, dt.timezone.utc).date().isoformat()] = c
    if not out:
        raise RuntimeError(f"Yahoo {ticker}: no data")
    return out


def week_key(d):
    y, w, _ = dt.date.fromisoformat(d).isocalendar()
    return (y, w)


def to_weekly(daily):
    last = {}
    for d in sorted(daily):
        last[week_key(d)] = (d, daily[d])
    return dict(sorted(last.values()))


def align(weekly, weeks):
    """Aligns to the benchmark calendar; fills gaps with the previous value (never before the first)."""
    by_week = {week_key(d): v for d, v in weekly.items()}
    vals, prev = [], None
    for k in weeks:
        v = by_week.get(k, prev)
        vals.append(None if v is None else round(v, 2))
        prev = v if v is not None else prev
    return vals


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    all_ = [BENCHMARK, *THEMES, REFERENCE]
    weekly = {}
    for name, tk in all_:
        print(f"Yahoo {tk} ({name})")
        weekly[name] = to_weekly(yahoo_daily(tk))

    bench = weekly[BENCHMARK[0]]
    labels = list(bench)
    weeks = [week_key(d) for d in labels]
    series = {name: align(weekly[name], weeks) for name, _ in all_}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    data = {
        "updated": now, "source": "Yahoo Finance (adjusted close, weekly)",
        "labels": labels, "benchmark": BENCHMARK[0], "reference": REFERENCE[0],
        "tickers": {name: tk for name, tk in all_}, "series": series,
    }
    with open(os.path.join(root, "themes.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(root, "themes.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["week_ending", *[f"{name} ({tk})" for name, tk in all_]])
        for i, d in enumerate(labels):
            w.writerow([d, *["" if series[n][i] is None else series[n][i] for n, _ in all_]])
    print(f"OK -> themes.json / themes.csv ({len(labels)} weeks, last {labels[-1]})")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"Themes not updated: {e}", file=sys.stderr)
        sys.exit(1)
