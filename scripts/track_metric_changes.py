#!/usr/bin/env python3
"""Trazabilidad de cambios bruscos día a día (Python puro, sin IA).
Compara la última entrada del histórico contra la anterior y, si el delta de una
métrica supera el umbral de scripts/alert_rules.json (metric_change_log), lo
registra en data/history/metric_changes_log.json:
  {"ticker": "BTC", "date": "2026-07-21", "metric": "rsi", "from": 45, "to": 68}
También registra los saltos de score de los informes L-M-V (vía snapshot_signals).
Lo invoca update_numbers.py; puede correrse suelto: python3 scripts/track_metric_changes.py"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import history_store  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
LOG_PATH = HERE / "data" / "history" / "metric_changes_log.json"
RULES_PATH = HERE / "scripts" / "alert_rules.json"


def load_rules():
    try:
        return json.load(open(RULES_PATH)).get("metric_change_log", {})
    except (ValueError, OSError):
        return {}


def load_log():
    if not LOG_PATH.exists():
        return []
    try:
        return json.load(open(LOG_PATH))
    except (ValueError, OSError):
        return []


def save_log(entries):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries.sort(key=lambda e: (e["date"], e["ticker"], e["metric"]))
    json.dump(entries, open(LOG_PATH, "w"), ensure_ascii=False, indent=0)


def _detect(prev, cur, rules):
    """Deltas entre dos entradas consecutivas del histórico de un activo."""
    found = []

    def jump(metric, key, thr, pct=False):
        a, b = prev.get(key), cur.get(key)
        if a is None or b is None or thr is None:
            return
        delta = (b / a - 1) * 100 if pct and a else b - a
        if abs(delta) >= thr:
            found.append({"metric": metric, "from": round(a, 2), "to": round(b, 2)})

    jump("rsi", "rsi", rules.get("rsi_jump"))
    jump("percentil_1y", "percentile_1y", rules.get("percentile_jump"))
    jump("precio_pct", "close", rules.get("price_jump_pct"), pct=True)
    return found


def run(hist_by_ticker):
    """Detecta cambios bruscos para cada activo (histórico ya con la entrada de hoy),
    actualiza el log global y devuelve {ticker: [entradas de los últimos 90 días]}."""
    rules = load_rules()
    log = load_log()
    seen = {(e["ticker"], e["date"], e["metric"]) for e in log}
    nuevos = 0
    for tk, hist in hist_by_ticker.items():
        if len(hist) < 2:
            continue
        prev, cur = hist[-2], hist[-1]
        for ch in _detect(prev, cur, rules):
            entry = {"ticker": tk, "date": cur["date"], **ch}
            key = (tk, cur["date"], ch["metric"])
            if key not in seen:
                log.append(entry)
                seen.add(key)
                nuevos += 1
    save_log(log)
    if nuevos:
        print(f"  cambios bruscos detectados hoy: {nuevos} (→ metric_changes_log.json)")

    # últimos 90 días por activo, para el panel colapsable del dashboard
    import datetime
    cutoff = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    out = {}
    for e in log:
        if e["date"] >= cutoff:
            out.setdefault(e["ticker"], []).append(e)
    for tk in out:
        out[tk].sort(key=lambda e: e["date"], reverse=True)
    return out


def log_score_change(ticker, date, prev_score, new_score):
    """Registra un salto de score de los informes L-M-V (lo llama snapshot_signals)."""
    rules = load_rules()
    thr = rules.get("score_jump")
    if thr is None or prev_score is None or new_score is None:
        return False
    if abs(new_score - prev_score) < thr:
        return False
    log = load_log()
    key = (ticker, date, "score")
    if any((e["ticker"], e["date"], e["metric"]) == key for e in log):
        return False
    log.append({"ticker": ticker, "date": date, "metric": "score",
                "from": prev_score, "to": new_score})
    save_log(log)
    return True


if __name__ == "__main__":
    # modo suelto: recorre los históricos ya guardados (nombre de archivo = activo)
    hists = {}
    for p in sorted((HERE / "data" / "history").glob("*.json")):
        if p.name == "metric_changes_log.json" or p.stem.startswith("BENCH-"):
            continue
        try:
            rows = json.load(open(p))
        except ValueError:
            continue
        if rows:
            hists[p.stem] = sorted(rows, key=lambda r: r.get("date", ""))
    res = run(hists)
    print(f"activos con cambios en 90d: {len(res)}")
