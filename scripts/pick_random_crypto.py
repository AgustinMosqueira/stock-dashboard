#!/usr/bin/env python3
"""Elige N criptomonedas al azar para refrescar (pedido del usuario, 22-oct-2026:
martes, actualizar 5 informes de cripto al azar).

A diferencia de pick_stale.py (que prioriza los informes más viejos), acá no
importa la fecha: las criptos son volátiles y noticiosas, así que conviene una
rotación pareja al azar en vez de encadenarse siempre a las mismas.

La lista de criptos NO está hardcodeada: se deriva de scripts/update_numbers.py
leyendo qué tickers del diccionario MAP usan un símbolo "CRYPTO:..." de
TradingView — así, si se agrega una cripto nueva al dashboard (ya sea a mano o
por este mismo refresco), entra sola a este sorteo sin tocar este archivo.

Uso: python3 scripts/pick_random_crypto.py [N]   (default N=5)
Imprime un ticker por línea."""
import pathlib
import random
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent


def load_crypto_tickers():
    txt = (HERE / "scripts" / "update_numbers.py").read_text()
    m = re.search(r"^MAP = \{\n(.*?)\n\}\n", txt, re.S | re.M)
    if not m:
        return []
    return [tk for tk, _sym in re.findall(r'"([^"]+)":\s*\("(CRYPTO:[^"]+)"', m.group(1))]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    cryptos = load_crypto_tickers()
    random.shuffle(cryptos)
    elegidos = cryptos[:n]
    for t in elegidos:
        print(t)
    print(f"({len(elegidos)} elegidos al azar de {len(cryptos)} criptos)", file=sys.stderr)


if __name__ == "__main__":
    main()
