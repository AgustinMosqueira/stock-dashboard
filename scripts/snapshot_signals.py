#!/usr/bin/env python3
"""Snapshot de señales: cada vez que corre el refresco de informes (L-M-V),
guarda score compuesto, grado y señal del día en data/history/signals/<activo>.json.
Es la base para backtest_signals.py (¿las señales anticiparon el precio?).
Uso: python3 scripts/snapshot_signals.py   (después de actualizar stocks-data.json)"""
import datetime
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
from history_store import safe_name  # noqa: E402
import track_metric_changes  # noqa: E402

SIG_DIR = HERE / "data" / "history" / "signals"
EQ_WEIGHTS = {"tecnica": 25, "fundamental": 25, "sentimiento": 20, "riesgo": 15, "conviccion": 15}
GRADES = [(85, "A+", "Strong Buy"), (70, "A", "Buy"), (55, "B", "Hold"),
          (40, "C", "Caution"), (25, "D", "Caution"), (0, "F", "Avoid")]


def composite(asset):
    scores = asset.get("scores") or {}
    if asset.get("customCats"):
        pairs = [(c["key"], c["weight"]) for c in asset["customCats"]]
    else:
        pairs = list(EQ_WEIGHTS.items())
    total_w = sum(w for _, w in pairs) or 1
    val = sum(scores.get(k, {}).get("score", 50) * w for k, w in pairs) / total_w
    return round(val)


def grade_for(score):
    for mn, g, s in GRADES:
        if score >= mn:
            return g, s
    return "F", "Avoid"


def summary_short(asset):
    text = ""
    if asset.get("sections"):
        text = asset["sections"].get("conclusion") or asset["sections"].get("resumen") or ""
    elif asset.get("customSections"):
        for cs in asset["customSections"]:
            if "onclusi" in cs.get("title", ""):
                text = cs.get("body", "")
                break
    text = re.sub(r"[*_#>`]|\n+", " ", text).strip()
    first = re.split(r"(?<=[.!?])\s", text, 1)[0]
    return first[:240]


def main():
    stocks = json.load(open(HERE / "stocks-data.json"))
    today = datetime.date.today().isoformat()
    SIG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Snapshot de señales — {today}")
    for a in stocks:
        score = composite(a)
        grade, signal = grade_for(score)
        entry = {"date": today, "score": score, "grade": grade, "signal": signal,
                 "summary_short": summary_short(a)}
        p = SIG_DIR / (safe_name(a["ticker"]) + ".json")
        rows = []
        if p.exists():
            try:
                rows = json.load(open(p))
            except ValueError:
                rows = []
        prev = next((r for r in reversed(rows) if r.get("date") != today), None)
        if prev and track_metric_changes.log_score_change(a["ticker"], today,
                                                          prev.get("score"), score):
            print(f"  ⚡ {a['ticker']}: salto de score {prev.get('score')} → {score} (logueado)")
        rows = [r for r in rows if r.get("date") != today]
        rows.append(entry)
        rows.sort(key=lambda r: r["date"])
        json.dump(rows, open(p, "w"), ensure_ascii=False, indent=0)
        print(f"  {a['ticker']:8} score {score:3} · {grade:2} · {signal}")


if __name__ == "__main__":
    main()
