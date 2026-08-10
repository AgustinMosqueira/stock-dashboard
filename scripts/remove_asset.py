#!/usr/bin/env python3
"""Elimina un activo del dashboard, deshaciendo TODO su cableado.

Quita el activo de:
  stocks-data.json y el bloque static-data de template.html
  scripts/update_numbers.py   (MAP + BENCH + CLP_ASSETS + OWN_CHART)
  template.html               (ORDER + LIVE_MAP + CHART_SYMBOLS + CHART_NOTES)
  scripts/backfill_history.py (SYMBOLS)
  scripts/stamp_report_date.py (DINAMICOS)
  scripts/REFRESH_PROMPT.md   (listas de dinámicos/estáticos)
  data/<TICKER>.json y data/event-results.json
El HISTÓRICO no se borra: se archiva en data/history/_archive/ por si el activo
vuelve (así no se pierden los 300 días de precios ya acumulados).

Uso: python3 scripts/remove_asset.py TICKER
Idempotente: si el activo no existe, informa y sale con código 0."""
import json
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent


def safe_name(ticker):
    return "FX-" + ticker.replace("/", "") if "/" in ticker else ticker


def drop_lines(path, ticker, what):
    """Elimina las líneas que declaran el ticker como clave de un dict."""
    p = HERE / path
    t = p.read_text()
    pat = re.compile(r'^[ \t]*"' + re.escape(ticker) + r'"[ \t]*:.*\n', re.M)
    nuevo, n = pat.subn("", t)
    if n:
        p.write_text(nuevo)
        print(f"  ✓ {what} ({n} línea{'s' if n > 1 else ''})")
    else:
        print(f"  = {what}: no estaba")


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Uso: python3 scripts/remove_asset.py TICKER")
    ticker = sys.argv[1].strip().upper()

    sd_path = HERE / "stocks-data.json"
    sd = json.load(open(sd_path))
    en_datos = any(a["ticker"] == ticker for a in sd)
    # un activo puede estar CABLEADO sin informe todavía (alta a medias): también se limpia
    cableado = f'"{ticker}"' in (HERE / "scripts" / "update_numbers.py").read_text()
    if not en_datos and not cableado:
        print(f"El activo {ticker} no está en el dashboard — nada que eliminar.")
        return
    if en_datos and len(sd) <= 2:
        raise SystemExit("❌ Me niego a dejar el dashboard con menos de 2 activos.")

    print(f"Eliminando {ticker} del dashboard…")

    # 1) datos: stocks-data.json + bloque estático + copia por activo
    if en_datos:
        sd = [a for a in sd if a["ticker"] != ticker]
        json.dump(sd, open(sd_path, "w"), ensure_ascii=False)
        print(f"  ✓ stocks-data.json (quedan {len(sd)} activos)")
    else:
        print("  = sin informe en stocks-data.json (estaba solo cableado)")

    t = (HERE / "template.html").read_text()
    m = re.search(r'(<script id="static-data" type="application/json">)(.*?)(</script>)', t, re.S)
    if m:
        static = json.loads(m.group(2).replace("<\\/", "</"))
        n0 = len(static)
        static = [a for a in static if a["ticker"] != ticker]
        if len(static) != n0:
            txt = json.dumps(static, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
            t = t[:m.start(2)] + txt + t[m.end(2):]
            (HERE / "template.html").write_text(t)
            print("  ✓ bloque static-data")

    for f in (HERE / "data" / f"{safe_name(ticker)}.json", HERE / "data" / f"{ticker}.json"):
        if f.exists():
            f.unlink()
            print(f"  ✓ {f.relative_to(HERE)}")

    # 2) resultados de eventos
    p = HERE / "data" / "event-results.json"
    if p.exists():
        try:
            res = json.load(open(p))
            nuevo = [r for r in res if r.get("ticker") != ticker]
            if len(nuevo) != len(res):
                json.dump(nuevo, open(p, "w"), ensure_ascii=False, indent=1)
                print("  ✓ event-results.json")
        except ValueError:
            pass

    # 3) ORDER del template
    m = re.search(r'const ORDER = \[(.*?)\];', t)
    if m:
        order = json.loads("[" + m.group(1) + "]")
        if ticker in order:
            order.remove(ticker)
            t = t.replace(m.group(0), "const ORDER = [" + ",".join(f'"{x}"' for x in order) + "];", 1)
            (HERE / "template.html").write_text(t)
            print("  ✓ template.ORDER")

    # 4) diccionarios de configuración
    drop_lines("scripts/update_numbers.py", ticker, "update_numbers.MAP/BENCH")
    drop_lines("template.html", ticker, "template.LIVE_MAP/CHART_SYMBOLS/CHART_NOTES")
    drop_lines("scripts/backfill_history.py", ticker, "backfill.SYMBOLS")

    # 5) sets (CLP_ASSETS, OWN_CHART, DINAMICOS)
    for path, nombres in (("scripts/update_numbers.py", ("CLP_ASSETS", "OWN_CHART")),
                          ("scripts/stamp_report_date.py", ("DINAMICOS",))):
        p = HERE / path
        t2 = p.read_text()
        cambiado = False
        for nombre in nombres:
            mm = re.search(nombre + r' = \{([^}]*)\}', t2)
            if not mm or f'"{ticker}"' not in mm.group(1):
                continue
            items = [x.strip() for x in mm.group(1).split(",") if x.strip() and x.strip() != f'"{ticker}"']
            t2 = t2.replace(mm.group(0), f'{nombre} = {{{", ".join(items)}}}' if items else f'{nombre} = set()', 1)
            cambiado = True
            print(f"  ✓ {nombre}")
        if cambiado:
            p.write_text(t2)

    # 6) REFRESH_PROMPT: listas de dinámicos y estáticos
    p = HERE / "scripts" / "REFRESH_PROMPT.md"
    r = p.read_text()
    mm = re.search(r'LOS (\d+) ESTÁTICOS \(([^)]*)\)', r)
    if mm and ticker in [x.strip() for x in mm.group(2).split(",")]:
        lista = [x.strip() for x in mm.group(2).split(",") if x.strip() != ticker]
        r = r.replace(mm.group(0), f"LOS {len(lista)} ESTÁTICOS ({', '.join(lista)})", 1)
        print("  ✓ REFRESH_PROMPT (estáticos)")
    # si era dinámico: quitar su línea numerada y renumerar
    lineas = r.split("\n")
    idx = next((i for i, l in enumerate(lineas)
                if re.match(r'^\d+\.\s+' + re.escape(ticker) + r'\b', l.strip())), None)
    if idx is not None:
        lineas.pop(idx)
        n = 0
        for i, l in enumerate(lineas):
            mo = re.match(r'^(\d+)\.\s+(.*)$', l)
            if mo and i < 40:  # solo la lista de dinámicos, al inicio del archivo
                n += 1
                lineas[i] = f"{n}. {mo.group(2)}"
        r = "\n".join(lineas)
        r = re.sub(r'los \d+ ACTIVOS DINÁMICOS', f'los {n} ACTIVOS DINÁMICOS', r)
        r = re.sub(r'\(re-investigar los \d+\)', f'(re-investigar los {n})', r)
        r = re.sub(r'## METODOLOGÍA \(para los \d+\)', f'## METODOLOGÍA (para los {n})', r)
        print(f"  ✓ REFRESH_PROMPT (dinámicos → {n})")
    p.write_text(r)

    # 6b) registro maestro: esta es la ÚNICA vía legítima de sacar un activo
    import datetime
    reg_path = HERE / "data" / "assets-registry.json"
    try:
        reg = json.load(open(reg_path))
        if ticker in reg.get("activos", []):
            reg["activos"] = [t for t in reg["activos"] if t != ticker]
            reg["actualizado"] = datetime.date.today().isoformat()
            json.dump(reg, open(reg_path, "w"), ensure_ascii=False, indent=1)
            print("  ✓ registro de activos")
    except (ValueError, OSError):
        pass

    # 7) histórico: se archiva, no se borra
    arch = HERE / "data" / "history" / "_archive"
    arch.mkdir(parents=True, exist_ok=True)
    for nombre in (safe_name(ticker), ticker):
        for sub in ("", "signals/"):
            f = HERE / "data" / "history" / sub / f"{nombre}.json"
            if f.exists():
                destino = arch / f"{sub.replace('/', '_')}{nombre}.json"
                shutil.move(str(f), str(destino))
                print(f"  ✓ histórico archivado → {destino.relative_to(HERE)}")

    print(f"\n{ticker} eliminado. Corre `python3 scripts/update_numbers.py` para reconstruir el dashboard.")


if __name__ == "__main__":
    main()
