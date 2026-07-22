#!/usr/bin/env python3
"""Backfill del histórico diario desde TradingView (Chrome con CDP en el puerto 9222).
Recorre los activos del dashboard + benchmarks, lee las barras diarias ya cargadas en el
gráfico (~300 ruedas) vía la API interna de la página y las fusiona en data/history/ SIN
sobrescribir entradas existentes (las del scanner, más ricas, tienen prioridad).

Requiere: Chrome lanzado con --remote-debugging-port=9222 y sesión de TradingView abierta
(perfil ~/.tradingview-chrome) + pip install websocket-client.
Uso: python3 scripts/backfill_history.py
Regla cuenta gratuita: si falla >3 veces seguidas, aborta (reintentar otro día)."""
import json
import pathlib
import sys
import time
import urllib.request

import websocket

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import history_store  # noqa: E402

# nombre de archivo de histórico -> símbolo TradingView
SYMBOLS = {
    "AAPL": "NASDAQ:AAPL", "MSFT": "NASDAQ:MSFT", "NVDA": "NASDAQ:NVDA",
    "GOOGL": "NASDAQ:GOOGL", "AMZN": "NASDAQ:AMZN", "TSLA": "NASDAQ:TSLA",
    "SPCX": "NASDAQ:SPCX", "CLSK": "NASDAQ:CLSK", "HDSY": "TSE:6324",
    "CCU": "BCS:CCU", "CMPC": "BCS:CMPC", "BTC": "CRYPTO:BTCUSD",
    "FX-USDCLP": "FX_IDC:USDCLP", "FX-EURUSD": "FX:EURUSD", "FX-USDJPY": "FX:USDJPY",
    "BENCH-SPX": "SP:SPX", "BENCH-NI225": "TVC:NI225", "BENCH-DXY": "TVC:DXY",
    "BENCH-ECH": "CBOE:ECH", "BENCH-BTCUSD": "CRYPTO:BTCUSD", "BENCH-TOTAL": "CRYPTOCAP:TOTAL",
}

EXTRACT_JS = """(()=>{
  const s = TradingViewApi.activeChart().getSeries();
  if (s.isLoading()) return "LOADING";
  const out = [];
  s.data().bars().each((i, v) => { out.push([v[0], v[4], v[5] == null ? null : v[5]]); return false; });
  return JSON.stringify({symbol: TradingViewApi.activeChart().symbol(), n: out.length, bars: out.slice(-320)});
})()"""


class CDP:
    def __init__(self):
        targets = json.load(urllib.request.urlopen("http://localhost:9222/json/list"))
        tv = next((t for t in targets if "tradingview.com/chart" in t.get("url", "")), None)
        if not tv:
            raise RuntimeError("No hay pestaña de gráfico de TradingView en el Chrome CDP (9222)")
        self.ws = websocket.create_connection(tv["webSocketDebuggerUrl"], timeout=30,
                                              suppress_origin=True)
        self.mid = 0

    def ev(self, expr):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": "Runtime.evaluate",
                                 "params": {"expression": expr, "returnByValue": True}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.mid:
                res = msg.get("result", {})
                if res.get("exceptionDetails"):
                    raise RuntimeError(str(res["exceptionDetails"].get(
                        "exception", {}).get("description", "excepción JS"))[:200])
                return res.get("result", {}).get("value")


def fetch_bars(cdp, symbol):
    cdp.ev(f"TradingViewApi.activeChart().setSymbol({json.dumps(symbol)})")
    time.sleep(2.5)
    for _ in range(20):  # hasta ~25 s de carga
        raw = cdp.ev(EXTRACT_JS)
        if raw and raw != "LOADING":
            data = json.loads(raw)
            # el símbolo del gráfico puede llevar prefijo de feed (BCS_DLY:CMPC)
            got = data["symbol"].split(":")[-1].upper()
            want = symbol.split(":")[-1].upper()
            if got == want and data["n"] > 10:
                return data["bars"]
        time.sleep(1.2)
    raise RuntimeError(f"timeout esperando barras de {symbol}")


def merge(name, bars):
    today = time.strftime("%Y-%m-%d")
    rows = history_store.load(name) if not name.startswith("BENCH-") else []
    if name.startswith("BENCH-"):
        p = history_store.HIST_DIR / (name + ".json")
        if p.exists():
            try:
                rows = json.load(open(p))
            except ValueError:
                rows = []
    have = {r["date"] for r in rows}
    added = 0
    for t, close, vol in bars:
        d = time.strftime("%Y-%m-%d", time.gmtime(t))
        if d >= today or d in have or close is None:
            continue  # hoy (y futuro) lo escribe el scanner con datos más ricos
        entry = {"date": d, "close": close}
        if vol is not None:
            entry["volume"] = vol
        rows.append(entry)
        have.add(d)
        added += 1
    rows.sort(key=lambda r: r["date"])
    history_store.HIST_DIR.mkdir(parents=True, exist_ok=True)
    json.dump(rows, open(history_store.HIST_DIR / (name + ".json"), "w"),
              ensure_ascii=False, indent=0)
    return added, len(rows)


def main():
    cdp = CDP()
    consecutive_errors = 0
    for name, symbol in SYMBOLS.items():
        try:
            bars = fetch_bars(cdp, symbol)
            added, total = merge(name, bars)
            consecutive_errors = 0
            print(f"  ✓ {name:14} {symbol:18} +{added} días (total {total})")
        except Exception as e:
            consecutive_errors += 1
            print(f"  ✗ {name:14} {symbol:18} ERROR: {e}")
            if consecutive_errors > 3:
                print("  ❌ más de 3 errores seguidos — abortando (cuenta gratuita; "
                      "reintentar otro día)")
                sys.exit(1)
    print("Backfill terminado.")


if __name__ == "__main__":
    main()
