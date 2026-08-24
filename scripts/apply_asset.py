#!/usr/bin/env python3
"""Reinyecta UN activo desde data/<TICKER>.json a stocks-data.json, sin tocar el resto.

Se usa cuando un push es rechazado porque otra corrida publicó primero: en vez de
rebasar (que produce conflictos en un archivo generado y ya nos costó perder informes),
se vuelve al remoto limpio y se vuelve a aplicar SOLO el activo de esta corrida.

Uso: python3 scripts/apply_asset.py TICKER"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Uso: python3 scripts/apply_asset.py TICKER")
    ticker = sys.argv[1].strip().upper()
    src = HERE / "data" / f"{ticker}.json"
    if not src.exists():
        raise SystemExit(f"❌ No existe data/{ticker}.json — no hay nada que reinyectar.")
    obj = json.load(open(src))
    if obj.get("ticker", "").upper() != ticker:
        raise SystemExit(f"❌ data/{ticker}.json contiene el ticker «{obj.get('ticker')}».")

    sd_path = HERE / "stocks-data.json"
    sd = json.load(open(sd_path))
    antes = len(sd)
    for i, a in enumerate(sd):
        if a["ticker"].upper() == ticker:
            sd[i] = obj
            pos = i
            break
    else:
        # activo nuevo: las acciones van antes del primer par FX, los pares al final
        pos = len(sd) if "/" in ticker else next(
            (i for i, a in enumerate(sd) if "/" in a["ticker"]), len(sd))
        sd.insert(pos, obj)

    assert len(sd) >= antes, "el reensamblado no puede perder activos"
    json.dump(sd, open(sd_path, "w"), ensure_ascii=False, indent=1)
    print(f"✓ {ticker} reinyectado en stocks-data.json (posición {pos}, {len(sd)} activos)")


if __name__ == "__main__":
    main()
