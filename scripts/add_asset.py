#!/usr/bin/env python3
"""Cablea un activo NUEVO en todo el pipeline del dashboard, sin intervención manual.

Resuelve el símbolo en TradingView, elige benchmark y formato de precio, y parcha:
  scripts/update_numbers.py   (MAP + BENCH + CLP_ASSETS)
  template.html               (ORDER + LIVE_MAP + CHART_SYMBOLS)
  scripts/backfill_history.py (SYMBOLS)
  scripts/REFRESH_PROMPT.md   (lista de estáticos)
NO escribe el informe: eso lo hace Claude en el workflow de informe a pedido.

Uso:
  python3 scripts/add_asset.py MELI                # busca el símbolo solo
  python3 scripts/add_asset.py MELI NASDAQ:MELI    # símbolo explícito
Idempotente: si el activo ya existe, no hace nada y sale con código 0."""
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent.parent
SCANNER = "https://scanner.tradingview.com/global/scan"
SEARCH = ("https://symbol-search.tradingview.com/symbol_search/v3/"
          "?text={q}&hl=0&exchange=&lang=es&search_type=undefined&domain=production")

# formato de precio por moneda: (prefijo, sufijo, decimales, sep. miles, sep. decimal)
FMT_USD = ("$", "", 2, ",", ".")
FMT_CLP = ("$", " CLP", 1, ".", ",")
FMT_JPY = ("¥", "", 0, ",", ".")
FMT_EUR = ("€", "", 2, ".", ",")
FMT_BY_CURRENCY = {"USD": FMT_USD, "CLP": FMT_CLP, "JPY": FMT_JPY, "EUR": FMT_EUR}

BENCH_US = ('("SP:SPX", "S&P 500")', "SP:SPX")
BENCH_CL = ('("CBOE:ECH", "ECH (proxy Chile/IPSA)")', "CBOE:ECH")
BENCH_JP = ('("TVC:NI225", "Nikkei 225")', "TVC:NI225")
BENCH_CRYPTO = ('("CRYPTO:BTCUSD", "Bitcoin")', "CRYPTO:BTCUSD")
BENCH_BY_EXCHANGE = {
    "NASDAQ": BENCH_US, "NYSE": BENCH_US, "AMEX": BENCH_US, "CBOE": BENCH_US,
    "BCS": BENCH_CL, "TSE": BENCH_JP, "CRYPTO": BENCH_CRYPTO, "CRYPTOCAP": BENCH_CRYPTO,
}


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def resolve_symbol(query):
    """Busca el símbolo en TradingView y devuelve el mejor candidato que el scanner
    reconozca (probar es imprescindible: el buscador lista símbolos no cotizables)."""
    data = _get(SEARCH.format(q=urllib.parse.quote(query)),
                {"User-Agent": "Mozilla/5.0", "Origin": "https://www.tradingview.com"})
    cands = []
    for s in data.get("symbols", [])[:12]:
        sym = re.sub(r"</?em>", "", s.get("symbol", ""))
        exch = s.get("exchange", "")
        typ = (s.get("type") or "").lower()
        if not sym or not exch or typ in ("economic", "index"):
            continue
        cands.append((f"{exch}:{sym}", s.get("description", ""), s.get("currency_code", "USD")))
    if not cands:
        raise SystemExit(f"❌ No encontré ningún símbolo para «{query}» en TradingView.")
    # el scanner es el juez: solo sirve lo que devuelve precio
    tickers = [c[0] for c in cands]
    body = json.dumps({"symbols": {"tickers": tickers, "query": {"types": []}},
                       "columns": ["close", "currency"]}).encode()
    req = urllib.request.Request(SCANNER, data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        rows = json.load(r).get("data", [])
    ok = {row["s"]: row["d"] for row in rows if row["d"] and row["d"][0] is not None}
    for sym, desc, cur in cands:
        if sym in ok:
            return sym, desc, (ok[sym][1] or cur or "USD")
    raise SystemExit(f"❌ Encontré símbolos para «{query}» pero ninguno cotiza en el scanner: {tickers[:4]}")


def verify(symbol):
    body = json.dumps({"symbols": {"tickers": [symbol], "query": {"types": []}},
                       "columns": ["close", "currency", "description"]}).encode()
    req = urllib.request.Request(SCANNER, data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        rows = json.load(r).get("data", [])
    if not rows or rows[0]["d"][0] is None:
        raise SystemExit(f"❌ El scanner de TradingView no devuelve precio para {symbol}.")
    d = rows[0]["d"]
    return d[0], (d[1] or "USD"), (d[2] or "")


def patch(path, old, new, what):
    p = HERE / path
    t = p.read_text()
    if new.strip() in t:
        print(f"  = {what}: ya estaba")
        return
    if old not in t:
        raise SystemExit(f"❌ No pude parchar {what} en {path} (ancla no encontrada).")
    p.write_text(t.replace(old, new, 1))
    print(f"  ✓ {what}")


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Uso: python3 scripts/add_asset.py TICKER [EXCHANGE:SIMBOLO]")
    ticker = sys.argv[1].strip().upper()
    if len(sys.argv) >= 3 and ":" in sys.argv[2]:
        symbol = sys.argv[2].strip().upper()
        price, currency, desc = verify(symbol)
    else:
        symbol, desc, currency = resolve_symbol(ticker)
        price, currency, desc2 = verify(symbol)
        desc = desc2 or desc

    # ¿ya existe?
    sd = json.load(open(HERE / "stocks-data.json"))
    if any(a["ticker"] == ticker for a in sd):
        print(f"El activo {ticker} ya está en el dashboard — nada que cablear.")
        return
    if f'"{ticker}":' in (HERE / "scripts" / "update_numbers.py").read_text():
        print(f"{ticker} ya está cableado en update_numbers.py — nada que hacer.")
        return

    exch = symbol.split(":")[0]
    fmt = FMT_BY_CURRENCY.get(currency.upper(), FMT_USD)
    bench_py, _ = BENCH_BY_EXCHANGE.get(exch, BENCH_US)
    print(f"Cableando {ticker} → {symbol} ({desc}) · precio {price} {currency} · benchmark {bench_py}")

    # 1) update_numbers.py: MAP, BENCH y (si aplica) CLP_ASSETS
    fmt_py = f'("{fmt[0]}", "{fmt[1]}", {fmt[2]}, "{fmt[3]}", "{fmt[4]}")'
    patch("scripts/update_numbers.py",
          '    "BTC":     ("CRYPTO:BTCUSD", ("$", "", 0, ",", ".")),',
          f'    "{ticker}": ("{symbol}", {fmt_py}),\n'
          '    "BTC":     ("CRYPTO:BTCUSD", ("$", "", 0, ",", ".")),',
          "update_numbers.MAP")
    patch("scripts/update_numbers.py",
          '    "HDSY": ("TVC:NI225", "Nikkei 225"),',
          f'    "{ticker}": {bench_py},\n'
          '    "HDSY": ("TVC:NI225", "Nikkei 225"),',
          "update_numbers.BENCH")
    if currency.upper() == "CLP":
        t = (HERE / "scripts" / "update_numbers.py").read_text()
        m = re.search(r'CLP_ASSETS = \{([^}]*)\}', t)
        if m and f'"{ticker}"' not in m.group(1):
            (HERE / "scripts" / "update_numbers.py").write_text(
                t.replace(m.group(0), f'CLP_ASSETS = {{{m.group(1)}, "{ticker}"}}', 1))
            print("  ✓ update_numbers.CLP_ASSETS")

    # 2) template.html: ORDER, LIVE_MAP, CHART_SYMBOLS
    t = (HERE / "template.html").read_text()
    m = re.search(r'const ORDER = \[(.*?)\];', t)
    order = json.loads("[" + m.group(1) + "]")
    if ticker not in order:
        # los pares FX van al final; el resto antes del primer par
        idx = next((i for i, x in enumerate(order) if "/" in x), len(order))
        order.insert(idx, ticker)
        new_order = "const ORDER = [" + ",".join(f'"{x}"' for x in order) + "];"
        (HERE / "template.html").write_text(t.replace(m.group(0), new_order, 1))
        print("  ✓ template.ORDER")
    fmt_js = f'["{fmt[0]}", "{fmt[1]}", {fmt[2]}, "{fmt[3]}", "{fmt[4]}"]'
    patch("template.html",
          '    "BTC":     ["CRYPTO:BTCUSD", ["$", "", 0, ",", "."]],',
          f'    "{ticker}": ["{symbol}", {fmt_js}],\n'
          '    "BTC":     ["CRYPTO:BTCUSD", ["$", "", 0, ",", "."]],',
          "template.LIVE_MAP")
    patch("template.html",
          '    "CCU": "BCS:CCU",',
          f'    "{ticker}": "{symbol}",\n    "CCU": "BCS:CCU",',
          "template.CHART_SYMBOLS")

    # 3) backfill_history.py
    patch("scripts/backfill_history.py",
          '    "CCU": "BCS:CCU",',
          f'    "{ticker}": "{symbol}",\n    "CCU": "BCS:CCU",',
          "backfill.SYMBOLS")

    # 4) REFRESH_PROMPT: nace como estático (textos a pedido / rotación)
    p = HERE / "scripts" / "REFRESH_PROMPT.md"
    t = p.read_text()
    m = re.search(r'LOS (\d+) ESTÁTICOS \(([^)]*)\)', t)
    if m and ticker not in m.group(2):
        lista = m.group(2) + f", {ticker}"
        n = int(m.group(1)) + 1
        p.write_text(t.replace(m.group(0), f"LOS {n} ESTÁTICOS ({lista})", 1))
        print("  ✓ REFRESH_PROMPT (estáticos)")

    # 5) registro maestro: el activo queda protegido contra pérdidas
    import datetime
    reg_path = HERE / "data" / "assets-registry.json"
    try:
        reg = json.load(open(reg_path))
    except (ValueError, OSError):
        reg = {"activos": []}
    if ticker not in reg.get("activos", []):
        reg.setdefault("activos", []).append(ticker)
        reg["actualizado"] = datetime.date.today().isoformat()
        json.dump(reg, open(reg_path, "w"), ensure_ascii=False, indent=1)
        print("  ✓ registro de activos")

    print(f"\n{ticker} cableado. Falta el informe: lo escribe Claude en el workflow a pedido.")


if __name__ == "__main__":
    main()
