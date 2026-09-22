#!/usr/bin/env python3
"""Reconstruye stock-dashboard.html/index.html desde stocks-data.json (GARANTIZADO,
sin depender de que el agente de Claude se acuerde de correr build.py) y verifica que
el ticker de la solicitud haya quedado embebido en el HTML final.

Se agregó tras el bug de NIKE (22-sep-2026): el agente del informe a pedido cableó el
activo en stocks-data.json, assets-registry.json y update_numbers.py, pero nunca corrió
build.py — el dashboard publicado quedó ~10 horas sin NIKE aunque Telegram avisó "listo".
Ahora el workflow reconstruye SIEMPRE (no depende de que el agente se acuerde) y falla
en voz alta si, pese a eso, el ticker no aparece en el HTML publicado.

Uso: python3 scripts/rebuild_and_verify.py TICKER"""
import datetime
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Uso: python3 scripts/rebuild_and_verify.py TICKER")
    ticker = sys.argv[1].strip().upper()
    hoy = datetime.date.today()
    fecha = f"{hoy.day}-{MESES[hoy.month - 1]}-{hoy.year}"

    subprocess.run([sys.executable, str(HERE / "build.py"), fecha], check=True, cwd=HERE)
    (HERE / "index.html").write_text((HERE / "stock-dashboard.html").read_text())
    print(f"✓ stock-dashboard.html + index.html reconstruidos ({fecha})")

    html = (HERE / "index.html").read_text()
    m = re.search(r'id="stock-data" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise SystemExit("❌ No encuentro el bloque stock-data en index.html — algo rompió el build.")
    data = json.loads(m.group(1).replace("<\\/", "</"))
    tickers = [a["ticker"] for a in data]
    if ticker not in tickers:
        raise SystemExit(
            f"❌ {ticker} NO está en el HTML publicado después de reconstruir — el "
            f"dashboard tiene {len(tickers)} activos y {ticker} no es uno de ellos. "
            f"Revisa si el agente realmente agregó el activo a stocks-data.json."
        )
    print(f"✓ {ticker} verificado en el HTML publicado ({len(tickers)} activos en total)")


if __name__ == "__main__":
    main()
