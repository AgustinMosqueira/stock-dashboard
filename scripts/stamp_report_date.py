#!/usr/bin/env python3
"""Estampa la fecha de informe ("reportDate", formato largo en español) en los 6
activos DINÁMICOS de stocks-data.json. Lo llama refresh-reports.yml justo después
del paso de Claude, para que cada informe muestre la fecha real de su última
re-investigación (los 9 estáticos conservan la suya).
Uso: python3 scripts/stamp_report_date.py"""
import datetime
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent.parent
DINAMICOS = {"SPCX", "BTC", "HDSY", "CLSK", "USD/CLP", "USD/JPY"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

hoy = datetime.date.today()
fecha = f"{hoy.day} de {MESES[hoy.month - 1]} de {hoy.year}"

p = HERE / "stocks-data.json"
stocks = json.load(open(p))
for s in stocks:
    if s["ticker"] in DINAMICOS:
        s["reportDate"] = fecha
json.dump(stocks, open(p, "w"), ensure_ascii=False)
print(f"reportDate = «{fecha}» estampada en: {', '.join(sorted(DINAMICOS))}")
