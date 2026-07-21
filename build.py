#!/usr/bin/env python3
"""Ensambla el dashboard unificado (con selector Equity/FX en la página) desde
template.html + stocks-data.json (12 activos: 9 equity/BTC + 3 pares FX).
Uso: python3 build.py [FECHA_CORTA p.ej. 19-jul-2026]
Genera: stock-dashboard.html"""
import json, pathlib, sys

HERE = pathlib.Path(__file__).parent
fecha = sys.argv[1] if len(sys.argv) > 1 else "19-jul-2026"

tpl = (HERE / "template.html").read_text()
stocks = json.load(open(HERE / "stocks-data.json"))
assert any("/" in s["ticker"] for s in stocks) and any("/" not in s["ticker"] for s in stocks)

out = tpl.replace("__DATA_DATE__", fecha)
data_txt = json.dumps(stocks, ensure_ascii=False).replace("</", "<\\/")
out = out.replace("__STOCKS_JSON__", data_txt)
for tok in ["__DATA_DATE__", "__STOCKS_JSON__", "__PAGE_TITLE__", "__BRAND__", "__META_LINE__", "__RAIL_NOTE__", "__CROSS_HTML__"]:
    assert tok not in out, f"token sin reemplazar: {tok}"
(HERE / "stock-dashboard.html").write_text(out)
emb = json.loads(out.split('id="stock-data" type="application/json">')[1].split("</script>")[0].replace("<\\/", "</"))
eq = [s["ticker"] for s in emb if "/" not in s["ticker"]]
fx = [s["ticker"] for s in emb if "/" in s["ticker"]]
print(f"stock-dashboard.html: {len(out)} bytes | equity {len(eq)}: {eq} | fx {len(fx)}: {fx}")
