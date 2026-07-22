#!/usr/bin/env python3
"""Backtest de señales: cruza data/history/signals/*.json (señales emitidas por los
informes L-M-V) con data/history/*.json (precios) y mide el retorno real del activo
5, 10 y 20 ruedas después de cada señal. Genera data/backtest_report.json.
Solo lee histórico ya guardado — pensado para correr manual o mensual (workflow
backtest.yml), no a diario. Uso: python3 scripts/backtest_signals.py"""
import json
import pathlib
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent.parent
SIG_DIR = HERE / "data" / "history" / "signals"
HIST_DIR = HERE / "data" / "history"
HORIZONS = [5, 10, 20]  # ruedas (entradas de histórico) hacia adelante

# Las señales se agrupan en 3 buckets direccionales para medir precisión
BUCKET = {"Strong Buy": "compra", "Buy": "compra", "Hold": "neutral",
          "Caution": "venta", "Avoid": "venta"}


def load_json(p):
    try:
        return json.load(open(p))
    except (ValueError, OSError):
        return []


def main():
    if not SIG_DIR.exists():
        print("No hay señales guardadas todavía (data/history/signals/ vacío). "
              "Se llenará con cada corrida de informes L-M-V.")
        return

    per_signal = []
    for sp in sorted(SIG_DIR.glob("*.json")):
        name = sp.stem
        hist = load_json(HIST_DIR / (name + ".json"))
        dates = [r["date"] for r in hist]
        closes = [r["close"] for r in hist]
        for sig in load_json(sp):
            d = sig.get("date")
            # posición del primer día de histórico >= fecha de la señal
            idx = next((i for i, dt in enumerate(dates) if dt >= d), None)
            if idx is None:
                continue
            base = closes[idx]
            rets = {}
            for h in HORIZONS:
                if idx + h < len(closes) and base:
                    rets[f"ret_{h}d"] = round((closes[idx + h] / base - 1) * 100, 2)
                else:
                    rets[f"ret_{h}d"] = None  # todavía no pasaron h ruedas
            per_signal.append({"asset": name, "date": d, "score": sig.get("score"),
                               "signal": sig.get("signal"),
                               "bucket": BUCKET.get(sig.get("signal"), "neutral"),
                               "close_en_senal": base, **rets})

    # tabla de precisión: % de señales de cada bucket con retorno en la dirección esperada
    accuracy = {}
    for h in HORIZONS:
        key = f"ret_{h}d"
        stats = defaultdict(lambda: {"n": 0, "aciertos": 0, "ret_promedio": 0.0})
        for s in per_signal:
            r = s[key]
            if r is None:
                continue
            b = s["bucket"]
            st = stats[b]
            st["n"] += 1
            st["ret_promedio"] += r
            if (b == "compra" and r > 0) or (b == "venta" and r < 0) or (b == "neutral" and abs(r) < 3):
                st["aciertos"] += 1
        accuracy[f"{h}d"] = {
            b: {"n": st["n"],
                "precision_pct": round(st["aciertos"] / st["n"] * 100, 1) if st["n"] else None,
                "ret_promedio_pct": round(st["ret_promedio"] / st["n"], 2) if st["n"] else None}
            for b, st in stats.items()}

    evaluadas = sum(1 for s in per_signal if s["ret_10d"] is not None)
    report = {
        "nota": ("Retornos medidos en ruedas de histórico (días con dato), no días calendario. "
                 "Los buckets agrupan: compra=Strong Buy/Buy, neutral=Hold, venta=Caution/Avoid. "
                 "Una señal 'neutral' se considera acierto si el activo se movió menos de ±3%."),
        "n_senales": len(per_signal), "n_evaluadas_10d": evaluadas,
        "precision": accuracy, "senales": per_signal,
    }
    out = HERE / "data" / "backtest_report.json"
    json.dump(report, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"Backtest: {len(per_signal)} señales, {evaluadas} con ≥10 ruedas de historia posterior")
    for h, buckets in accuracy.items():
        for b, st in buckets.items():
            if st["n"]:
                print(f"  {h:>3} {b:8} n={st['n']:3} precisión={st['precision_pct']}% "
                      f"ret.prom={st['ret_promedio_pct']}%")
    print(f"  → {out.relative_to(HERE)}")


if __name__ == "__main__":
    main()
