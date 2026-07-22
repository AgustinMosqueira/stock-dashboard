#!/usr/bin/env python3
"""Actualiza los NÚMEROS del dashboard desde el scanner público de TradingView.

Por activo (15) hace, sin IA y sin dependencias externas:
 1. precio, variación día/semana y línea 'Técnico (auto)' (RSI + MACD)
 2. append del día al histórico persistente data/history/<activo>.json
 3. métricas de riesgo (volatilidad 30d, Sharpe, Sortino, max drawdown 1Y) — scripts/metrics.py
 4. comparación vs benchmark (perf relativa 30d/YTD) + percentil del rango de 1 año
 5. bloque "technical" completo (SMAs, EMAs, volumen relativo, etc.) para el Panel Técnico
 6. metadata de origen ("sources") por métrica
 7. log de cambios bruscos día a día (scripts/track_metric_changes.py)

Patcha stocks-data.json Y el bloque static-data horneado en template.html,
luego reconstruye stock-dashboard.html + index.html.
Uso: python3 scripts/update_numbers.py"""
import datetime
import json
import pathlib
import re
import subprocess
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import history_store  # noqa: E402
import metrics  # noqa: E402
import track_metric_changes  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
hoy = datetime.date.today()
FECHA = f"{hoy.day}-{MESES[hoy.month-1]}-{hoy.year}"
NOW_ISO = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

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

# benchmark por activo: (símbolo TradingView, etiqueta visible)
# Nota: el IPSA no está disponible en el scanner gratuito; se usa ECH
# (iShares MSCI Chile, CBOE) como proxy del mercado chileno.
BENCH_US = ("SP:SPX", "S&P 500")
BENCH = {
    "AAPL": BENCH_US, "MSFT": BENCH_US, "NVDA": BENCH_US, "GOOGL": BENCH_US,
    "AMZN": BENCH_US, "TSLA": BENCH_US, "SPCX": BENCH_US,
    "CCU": ("CBOE:ECH", "ECH (proxy Chile/IPSA)"),
    "CMPC": ("CBOE:ECH", "ECH (proxy Chile/IPSA)"),
    "BTC": ("CRYPTOCAP:TOTAL", "Cripto total (ciclo)"),
    "CLSK": ("CRYPTO:BTCUSD", "Bitcoin"),
    "HDSY": ("TVC:NI225", "Nikkei 225"),
    "USD/CLP": ("TVC:DXY", "DXY"),
    "EUR/USD": ("TVC:DXY", "DXY"),
    "USD/JPY": ("TVC:DXY", "DXY"),
}

# tasa libre de riesgo anual para Sharpe/Sortino (activos en CLP usan TPM Chile aprox.)
RISK_FREE_DEFAULT = 0.045
RISK_FREE_CLP = 0.05
CLP_ASSETS = {"CCU", "CMPC"}

COLS = ["close", "change", "change|1W", "RSI", "MACD.macd", "MACD.signal",
        "SMA20", "SMA50", "SMA200", "EMA12", "EMA26",
        "volume", "average_volume_30d_calc",
        "price_52_week_high", "price_52_week_low", "Perf.1M", "Perf.YTD"]

SCANNER_ORIGIN = "TradingView scanner"


def fetch():
    tickers = [v[0] for v in MAP.values()]
    bench_syms = sorted({b[0] for b in BENCH.values()})
    body = json.dumps({"symbols": {"tickers": tickers + bench_syms, "query": {"types": []}},
                       "columns": COLS}).encode()
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
    benches = {s: by_symbol[s] for s in bench_syms if s in by_symbol}
    return out, benches


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


def rnd(v, nd=2):
    return round(v, nd) if isinstance(v, (int, float)) else None


def pct_vs(price, ref):
    if price is None or ref is None or ref == 0:
        return None
    return (price / ref - 1) * 100


def build_extras(ticker, q, benches):
    """Calcula histórico + risk + benchmark + technical + sources para un activo."""
    # — histórico: append de la entrada de hoy —
    closes_prev = history_store.closes(history_store.load(ticker))
    pctile = metrics.price_percentile(q["close"], q.get("price_52_week_low"),
                                      q.get("price_52_week_high"))
    entry = {"date": hoy.isoformat(), "close": q["close"], "rsi": rnd(q.get("RSI")),
             "macd": rnd(q.get("MACD.macd"), 4), "macd_signal": rnd(q.get("MACD.signal"), 4),
             "volume": q.get("volume"), "sma20": rnd(q.get("SMA20"), 4),
             "sma50": rnd(q.get("SMA50"), 4), "sma200": rnd(q.get("SMA200"), 4),
             "percentile_1y": rnd(pctile, 1)}
    hist = history_store.append_today(ticker, entry)
    closes = history_store.closes(hist)
    n_days = len(closes)

    # — riesgo (Paso 1) —
    rf = RISK_FREE_CLP if ticker in CLP_ASSETS else RISK_FREE_DEFAULT
    year_closes = closes[-metrics.TRADING_DAYS:]
    risk = {"volatility_30d": rnd(metrics.historical_volatility(closes)),
            "sharpe": rnd(metrics.sharpe_ratio(closes, rf)),
            "sortino": rnd(metrics.sortino_ratio(closes, rf)),
            "max_drawdown_1y": rnd(metrics.max_drawdown(year_closes) if n_days >= 30 else None),
            "n_days": n_days, "window": 30}

    # — benchmark (Paso 2) —
    bsym, blabel = BENCH[ticker]
    bq = benches.get(bsym)
    benchmark = {"ticker": bsym, "label": blabel,
                 "relative_performance_30d": None, "relative_performance_ytd": None,
                 "price_percentile_1y": rnd(pctile, 1),
                 # percentil calculado sobre el rango 52 sem. del scanner (año completo);
                 # partial solo si hubo que caer al histórico acumulado
                 "partial": False}
    if pctile is None and n_days >= 2:
        benchmark["price_percentile_1y"] = rnd(
            metrics.price_percentile(closes[-1], min(year_closes), max(year_closes)), 1)
        benchmark["partial"] = True
    if bq:
        if q.get("Perf.1M") is not None and bq.get("Perf.1M") is not None:
            benchmark["relative_performance_30d"] = rnd(q["Perf.1M"] - bq["Perf.1M"])
        if q.get("Perf.YTD") is not None and bq.get("Perf.YTD") is not None:
            benchmark["relative_performance_ytd"] = rnd(q["Perf.YTD"] - bq["Perf.YTD"])

    # — panel técnico (Paso 6) —
    vol_avg20 = None
    vols = [r.get("volume") for r in hist if r.get("volume")]
    if len(vols) >= 20:
        vol_avg20 = sum(vols[-20:]) / 20
    elif q.get("average_volume_30d_calc"):
        vol_avg20 = q["average_volume_30d_calc"]  # proxy scanner hasta acumular 20 ruedas
    technical = {
        "price": q["close"],
        "change_1d_pct": rnd(q.get("change")), "change_1w_pct": rnd(q.get("change|1W")),
        "rsi": rnd(q.get("RSI"), 1), "macd": rnd(q.get("MACD.macd"), 4),
        "macd_signal": rnd(q.get("MACD.signal"), 4),
        "sma20": rnd(q.get("SMA20"), 4), "sma50": rnd(q.get("SMA50"), 4),
        "sma200": rnd(q.get("SMA200"), 4),
        "ema12": rnd(q.get("EMA12"), 4), "ema26": rnd(q.get("EMA26"), 4),
        "pct_vs_sma20": rnd(pct_vs(q["close"], q.get("SMA20"))),
        "pct_vs_sma50": rnd(pct_vs(q["close"], q.get("SMA50"))),
        "pct_vs_sma200": rnd(pct_vs(q["close"], q.get("SMA200"))),
        "volume_today": q.get("volume"), "volume_avg20": rnd(vol_avg20, 0),
        "volume_ratio": rnd(q["volume"] / vol_avg20, 2) if q.get("volume") and vol_avg20 else None,
        "volatility_30d": risk["volatility_30d"], "sharpe": risk["sharpe"],
        "sortino": risk["sortino"], "max_drawdown_1y": risk["max_drawdown_1y"],
        "price_percentile_1y": benchmark["price_percentile_1y"],
        "vs_benchmark_30d_pct": benchmark["relative_performance_30d"],
        "perf_1m_pct": rnd(q.get("Perf.1M")), "perf_ytd_pct": rnd(q.get("Perf.YTD")),
    }

    # — trazabilidad (Paso 5a) —
    sources_meta = {
        "price": {"origin": SCANNER_ORIGIN, "fetched_at": NOW_ISO},
        "rsi_macd": {"origin": SCANNER_ORIGIN, "fetched_at": NOW_ISO},
        "smas_volume": {"origin": SCANNER_ORIGIN, "fetched_at": NOW_ISO},
        "benchmark": {"origin": SCANNER_ORIGIN, "symbol": bsym, "fetched_at": NOW_ISO},
        "risk_metrics": {"origin": f"data/history/{history_store.safe_name(ticker)}.json",
                         "n_days": n_days},
    }
    return {"risk": risk, "benchmark": benchmark, "technical": technical,
            "sourcesMeta": sources_meta, "history": hist}


def patch_asset(s, q, extras):
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
    # bloques calculados (pasos 1/2/5a/6)
    s["risk"] = extras["risk"]
    s["benchmark"] = extras["benchmark"]
    s["technical"] = extras["technical"]
    s["sourcesMeta"] = extras["sourcesMeta"]
    if "metricChanges" in extras:
        s["metricChanges"] = extras["metricChanges"]
    return s


def main():
    print(f"Actualizando números — {FECHA}")
    quotes, benches = fetch()
    print(f"  scanner OK: {len(quotes)}/{len(MAP)} activos · {len(benches)} benchmarks")
    if len(quotes) < 10:
        print("  ❌ demasiados activos sin datos; abortando sin tocar nada")
        sys.exit(1)

    # 0) histórico + métricas por activo
    extras = {}
    for tk, q in quotes.items():
        extras[tk] = build_extras(tk, q, benches)
    # benchmarks también acumulan histórico (para backtests futuros)
    for sym, bq in benches.items():
        history_store.append_today("BENCH-" + sym.split(":")[-1],
                                   {"date": hoy.isoformat(), "close": bq["close"],
                                    "volume": bq.get("volume")})

    # 0b) log de cambios bruscos día a día (Paso 5a) + últimos 90 días por activo
    changes_by_ticker = track_metric_changes.run({tk: e["history"] for tk, e in extras.items()})
    for tk in extras:
        extras[tk]["metricChanges"] = changes_by_ticker.get(tk, [])

    # 1) stocks-data.json (fuente de verdad local)
    sd_path = HERE / "stocks-data.json"
    stocks = json.load(open(sd_path))
    for s in stocks:
        if s["ticker"] in quotes:
            patch_asset(s, quotes[s["ticker"]], extras[s["ticker"]])
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
            patch_asset(s, quotes[s["ticker"]], extras[s["ticker"]])
    static_txt = json.dumps(static, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tpl = tpl[:m.start(2)] + static_txt + tpl[m.end(2):]
    tpl_path.write_text(tpl)

    # 3) reconstruir
    subprocess.run([sys.executable, str(HERE / "build.py"), FECHA], check=True, cwd=HERE)
    # 4) index.html para GitHub Pages
    (HERE / "index.html").write_text((HERE / "stock-dashboard.html").read_text())
    print(f"  ✓ dashboard reconstruido (stock-dashboard.html + index.html) con fecha {FECHA}")
    for tk, q in quotes.items():
        e = extras[tk]
        vol = e["risk"]["volatility_30d"]
        extra_txt = (f" vol30 {vol:.1f}%" if vol is not None
                     else f" hist {e['risk']['n_days']}d/30d")
        print(f"    {tk:8} {q['close']:>12} día {q['change']:+.2f}% sem {q['change|1W']:+.2f}%" + extra_txt
              if q.get("change") is not None and q.get("change|1W") is not None
              else f"    {tk:8} {q['close']}")


if __name__ == "__main__":
    main()
