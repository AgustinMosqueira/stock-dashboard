#!/usr/bin/env python3
"""Actualización intradía SOLO del calendario económico (resultados que van saliendo).
Corre cada ~30 min en horario de mercado vía econ-live.yml: re-descarga el calendario
(con los valores 'actual' ya publicados), patcha el bloque econ-data de index.html y
stock-dashboard.html y guarda data/econ-calendar.json. NO comitea ni toca precios —
el workflow despliega a Pages solo si algo cambió (deja el marcador _econ_changed).
Uso: python3 scripts/update_econ_live.py"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from update_numbers import HERE, fetch_econ_calendar  # noqa: E402

MARKER = HERE / "_econ_changed"


def main():
    if MARKER.exists():
        MARKER.unlink()
    econ = fetch_econ_calendar()
    if econ is None:
        print("sin datos nuevos (endpoint no disponible) — no se despliega")
        return

    prev_path = HERE / "data" / "econ-calendar.json"
    try:
        prev = json.load(open(prev_path))
    except (ValueError, OSError):
        prev = None
    if prev == econ:
        print("calendario económico sin cambios — no se despliega")
        return

    con_actual = sum(1 for e in econ if e.get("actual") is not None)
    econ_txt = json.dumps(econ, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    patched = 0
    for fname in ("index.html", "stock-dashboard.html"):
        p = HERE / fname
        if not p.exists():
            continue
        t = p.read_text()
        m = re.search(r'(<script id="econ-data" type="application/json">)(.*?)(</script>)', t, re.S)
        if not m:
            print(f"  ⚠️  {fname}: sin bloque econ-data")
            continue
        p.write_text(t[:m.start(2)] + econ_txt + t[m.end(2):])
        patched += 1
    json.dump(econ, open(prev_path, "w"), ensure_ascii=False)
    MARKER.write_text("yes")
    print(f"✓ calendario económico actualizado: {len(econ)} eventos, "
          f"{con_actual} con resultado publicado · {patched} páginas patchadas")


if __name__ == "__main__":
    main()
