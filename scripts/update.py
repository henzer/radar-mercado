"""Descarga datos públicos (FRED + CFTC) y genera data.json para el dashboard.

Sin dependencias externas: solo la librería estándar de Python.
Uso:  python scripts/update.py            -> escribe data.json en la raíz del repo
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

START = "2021-01-01"  # margen para calcular la media de 40 semanas desde 2022
UA = {"User-Agent": "Mozilla/5.0 (mercado-dashboard; GitHub Actions)"}

# nombre visible -> id de FRED
FRED = {
    "S&P 500": "SP500",
    "Nasdaq-100": "NASDAQ100",
    "Semis (SOX)": "NASDAQSOX",
    "Tecnología": "NASDAQNQUSB10",
    "Telecom": "NASDAQNQUSB15",
    "Salud": "NASDAQNQUSB20",
    "Financieras": "NASDAQNQUSB30",
    "Real estate": "NASDAQNQUSB35",
    "Consumo discrecional": "NASDAQNQUSB40",
    "Consumo básico": "NASDAQNQUSB45",
    "Industriales": "NASDAQNQUSB50",
    "Materiales": "NASDAQNQUSB55",
    "Energía": "NASDAQNQUSB60",
    "Utilities": "NASDAQNQUSB65",
}
EXTRA = {"VIX": "VIXCLS", "HY spread": "BAMLH0A0HYM2"}

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
            print(f"  reintento {i + 1} ({e})", file=sys.stderr)
            time.sleep(5 * (i + 1))


def fred_daily(series_id):
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv?"
        + urllib.parse.urlencode({"id": series_id, "cosd": START})
    )
    rows = csv.reader(io.StringIO(get(url)))
    next(rows)
    out = {}
    for d, v in rows:
        if v not in ("", "."):
            out[d] = float(v)
    return out


def week_key(d):
    y, w, _ = dt.date.fromisoformat(d).isocalendar()
    return (y, w)


def to_weekly(daily):
    """Último dato de cada semana ISO -> {fecha_del_ultimo_dato: valor}."""
    last = {}
    for d in sorted(daily):
        last[week_key(d)] = (d, daily[d])
    return dict(sorted(last.values()))


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    weekly = {}
    for name, sid in {**FRED, **EXTRA}.items():
        print(f"FRED {sid} ({name})")
        weekly[name] = to_weekly(fred_daily(sid))

    # Calendario común: semanas del S&P 500, etiquetadas por el último día hábil
    spx = weekly["S&P 500"]
    weeks = [week_key(d) for d in spx]
    labels = list(spx)
    series = {}
    for name, w in weekly.items():
        by_week = {week_key(d): v for d, v in w.items()}
        vals, prev = [], None
        for k in weeks:
            v = by_week.get(k, prev)  # rellena huecos (feriados) con el valor previo
            vals.append(None if v is None else round(v, 2))
            prev = v if v is not None else prev
        series[name] = vals

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

    data = {
        "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "last_week": labels[-1],
        "labels": labels,
        "series": series,
        "cot": cot,
    }
    path = os.path.join(root, "data.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"OK -> {path} ({len(labels)} semanas, último dato {labels[-1]})")


if __name__ == "__main__":
    main()
