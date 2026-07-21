#!/usr/bin/env python3
"""Actualiza los NÚMEROS del dashboard desde el scanner público de TradingView:
precio, variación día/semana y línea 'Técnico (auto)' (RSI + MACD) de los 15 activos.
Patcha stocks-data.json Y el bloque static-data horneado en template.html,
luego reconstruye stock-dashboard.html + index.html.
Sin dependencias externas (solo stdlib). Uso: python3 scripts/update_numbers.py"""
import json, re, sys, urllib.request, datetime, pathlib, subprocess

HERE = pathlib.Path(__file__).resolve().parent.parent
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
hoy = datetime.date.today()
FECHA = f"{hoy.day}-{MESES[hoy.month-1]}-{hoy.year}"

# ticker del dashboard -> (símbolo TradingView, formato de precio)
# formato: (prefijo, sufijo, decimales, separador_miles, separador_decimal)
MAP = {
    "AAPL":    ("NASDAQ:AAPL",  ("$", "", 2, ",", ".")),
    "MSFT":    ("NASDAQ:MSFT",  ("$", "", 2, ",", ".")),
    "NVDA":    ("NASDAQ:NVDA",  ("$", "", 2, ",", ".")),
    "GOOGL":   ("NASDAQ:GOOGL", ("$", "", 2, ",", ".")),
    "AMZN":    ("NASDAQ:AMZN",  ("$", "", 2, ",", ".")),
    "TSLA":    ("NASDAQ:TSLA",  ("$", "", 2, ",", ".")),
    "SPCX":    ("NASDAQ:SPCX",  ("$", "", 2, ",", ".")),
    "CLSK":    ("NASDAQ:CLSK",  ("$", "", 2, ",", ".")),
    "HDSY":    ("TSE:6324",     ("¥", "", 0, ",", ".")),
    "CCU":     ("BCS:CCU",      ("$", " CLP", 0, ".", ",")),
    "CMPC":    ("BCS:CMPC",     ("$", " CLP", 1, ".", ",")),
    "BTC":     ("CRYPTO:BTCUSD", ("$", "", 0, ",", ".")),
    "USD/CLP": ("FX_IDC:USDCLP", ("", "", 2, ",", ".")),
    "EUR/USD": ("FX:EURUSD",    ("", "", 5, ",", ".")),
    "USD/JPY": ("FX:USDJPY",    ("", "", 3, ",", ".")),
}
COLS = ["close", "change", "change|1W", "RSI", "MACD.macd", "MACD.signal"]


def fetch():
    tickers = [v[0] for v in MAP.values()]
    body = json.dumps({"symbols": {"tickers": tickers, "query": {"types": []}}, "columns": COLS}).encode()
    req = urllib.request.Request(
        "https://scanner.tradingview.com/global/scan", data=body,
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        data = json.load(r)
    by_symbol = {row["s"]: dict(zip(COLS, row["d"])) for row in data.get("data", [])}
    out = {}
    for tk, (sym, fmt) in MAP.items():
        if sym not in by_symbol or by_symbol[sym]["close"] is None:
            print(f"  ⚠️  sin datos para {tk} ({sym}) — se conserva el valor anterior")
            continue
        out[tk] = by_symbol[sym]
    return out


def fmt_precio(v, fmt):
    pre, suf, dec, miles, decsep = fmt
    s = f"{v:,.{dec}f}"                       # 1,234,567.89
    s = s.replace(",", "\x00").replace(".", decsep).replace("\x00", miles)
    return f"{pre}{s}{suf}"


def fmt_tecnico(q):
    parts = []
    if q.get("RSI") is not None:
        parts.append(f"RSI {q['RSI']:.1f}")
    if q.get("MACD.macd") is not None and q.get("MACD.signal") is not None:
        parts.append(f"MACD {q['MACD.macd']:+.2f} / señal {q['MACD.signal']:+.2f}")
    return " · ".join(parts) + f" (TradingView, {FECHA})" if parts else None


def patch_asset(s, q):
    fmt = MAP[s["ticker"]][1]
    # precio (primer par del statsList)
    if s.get("statsList") and s["statsList"][0][0] == "Precio":
        s["statsList"][0][1] = f"{fmt_precio(q['close'], fmt)} ({FECHA})"
    elif s.get("stats") and "precio" in s["stats"]:
        s["stats"]["precio"] = f"{fmt_precio(q['close'], fmt)} ({FECHA})"
    # variaciones
    s["change"] = {
        "day": round(q["change"], 2) if q.get("change") is not None else s.get("change", {}).get("day"),
        "week": round(q["change|1W"], 2) if q.get("change|1W") is not None else s.get("change", {}).get("week"),
    }
    # línea técnico (auto): reemplaza si existe, agrega si no
    tec = fmt_tecnico(q)
    if tec and s.get("statsList"):
        for pair in s["statsList"]:
            if pair[0] == "Técnico (auto)":
                pair[1] = tec
                break
        else:
            s["statsList"].append(["Técnico (auto)", tec])
    return s


def main():
    print(f"Actualizando números — {FECHA}")
    quotes = fetch()
    print(f"  scanner OK: {len(quotes)}/{len(MAP)} activos")
    if len(quotes) < 10:
        print("  ❌ demasiados activos sin datos; abortando sin tocar nada")
        sys.exit(1)

    # 1) stocks-data.json (dinámicos y copia completa local)
    sd_path = HERE / "stocks-data.json"
    stocks = json.load(open(sd_path))
    for s in stocks:
        if s["ticker"] in quotes:
            patch_asset(s, quotes[s["ticker"]])
    json.dump(stocks, open(sd_path, "w"), ensure_ascii=False)

    # 2) bloque static-data horneado en template.html
    tpl_path = HERE / "template.html"
    tpl = tpl_path.read_text()
    m = re.search(r'(<script id="static-data" type="application/json">)(.*?)(</script>)', tpl, re.S)
    if not m:
        print("  ❌ no se encontró el bloque static-data en template.html")
        sys.exit(1)
    static = json.loads(m.group(2).replace("<\\/", "</"))
    for s in static:
        if s["ticker"] in quotes:
            patch_asset(s, quotes[s["ticker"]])
    static_txt = json.dumps(static, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tpl = tpl[:m.start(2)] + static_txt + tpl[m.end(2):]
    tpl_path.write_text(tpl)

    # 3) reconstruir
    subprocess.run([sys.executable, str(HERE / "build.py"), FECHA], check=True, cwd=HERE)
    # 4) index.html para GitHub Pages
    (HERE / "index.html").write_text((HERE / "stock-dashboard.html").read_text())
    print(f"  ✓ dashboard reconstruido (stock-dashboard.html + index.html) con fecha {FECHA}")
    for tk, q in quotes.items():
        print(f"    {tk:8} {q['close']:>12} día {q['change']:+.2f}% sem {q['change|1W']:+.2f}%"
              if q.get("change") is not None and q.get("change|1W") is not None else f"    {tk:8} {q['close']}")


if __name__ == "__main__":
    main()
