#!/usr/bin/env python3
"""Almacén de histórico diario por activo: data/history/<nombre>.json.
Formato: lista de objetos ordenados cronológicamente:
  {"date": "2026-07-21", "close": 124.1, "rsi": 57.8, "macd": 1.3,
   "macd_signal": 1.1, "volume": 11000000, "sma50": ..., "sma200": ...}
Los campos distintos de date/close pueden faltar (p. ej. días backfilled solo
traen close/volume). Sin dependencias externas."""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent.parent
HIST_DIR = HERE / "data" / "history"


def safe_name(ticker):
    """'USD/CLP' -> 'FX-USDCLP' (misma convención que data/*.json); resto igual."""
    if "/" in ticker:
        return "FX-" + ticker.replace("/", "")
    return ticker


def path_for(ticker):
    return HIST_DIR / (safe_name(ticker) + ".json")


def load(ticker):
    p = path_for(ticker)
    if not p.exists():
        return []
    try:
        rows = json.load(open(p))
    except (ValueError, OSError):
        return []
    return sorted((r for r in rows if r.get("date") and r.get("close") is not None),
                  key=lambda r: r["date"])


def save(ticker, rows):
    HIST_DIR.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: r["date"])
    with open(path_for(ticker), "w") as f:
        json.dump(rows, f, ensure_ascii=False, indent=0)


def append_today(ticker, entry):
    """Agrega la entrada del día; si ya existe esa fecha la reemplaza (re-corridas
    del mismo día actualizan en vez de duplicar). Devuelve el histórico completo."""
    rows = load(ticker)
    rows = [r for r in rows if r["date"] != entry["date"]]
    rows.append(entry)
    save(ticker, rows)
    return sorted(rows, key=lambda r: r["date"])


def closes(rows):
    return [r["close"] for r in rows]
