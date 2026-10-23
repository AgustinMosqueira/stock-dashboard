#!/usr/bin/env python3
"""Elige los N activos con el informe más desactualizado para refrescar.

Pedido del usuario (22-oct-2026): actualizar 5 informes por semana, los de fecha
más antigua, para que ningún activo quede años sin revisarse. Excluye los
DINAMICOS (ya se re-investigan solos lunes/miércoles/viernes, scripts/stamp_report_date.py)
— este script es solo para los ESTÁTICOS, que solo se actualizan a pedido.

Un activo sin "reportDate" (los más viejos del dashboard, de antes de que ese
campo existiera) se trata como "más antiguo que cualquier fecha real" — son los
primeros candidatos, no un caso raro a ignorar.

Uso: python3 scripts/pick_stale.py [N]   (default N=5)
Imprime un ticker por línea, el más urgente primero."""
import datetime
import json
import pathlib
import random
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11,
    "diciembre": 12,
}


def parse_fecha(s):
    """'28 de septiembre de 2026' -> date(2026, 9, 28); None si no parsea."""
    if not s:
        return None
    m = re.match(r"\s*(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\s*$", s, re.I)
    if not m:
        return None
    dia, mes_txt, anio = m.groups()
    mes = MESES.get(mes_txt.lower())
    if not mes:
        return None
    try:
        return datetime.date(int(anio), mes, int(dia))
    except ValueError:
        return None


def load_dinamicos():
    txt = (HERE / "scripts" / "stamp_report_date.py").read_text()
    m = re.search(r"DINAMICOS = \{([^}]*)\}", txt)
    if not m:
        return set()
    return {t.strip().strip('"') for t in m.group(1).split(",") if t.strip()}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    stocks = json.load(open(HERE / "stocks-data.json"))
    dinamicos = load_dinamicos()

    candidatos = [a for a in stocks if a["ticker"] not in dinamicos]
    random.shuffle(candidatos)  # desempate aleatorio entre fechas iguales (sort es estable)
    # date.min ordena antes que cualquier fecha real: sin reportDate = más urgente
    candidatos.sort(key=lambda a: parse_fecha(a.get("reportDate")) or datetime.date.min)

    elegidos = candidatos[:n]
    for a in elegidos:
        print(a["ticker"])

    print(f"({len(elegidos)} elegidos de {len(candidatos)} candidatos estáticos; "
          f"excluidos {len(dinamicos)} dinámicos)", file=sys.stderr)
    for a in elegidos:
        print(f"  {a['ticker']}: reportDate={a.get('reportDate')!r}", file=sys.stderr)


if __name__ == "__main__":
    main()
