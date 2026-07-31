#!/usr/bin/env python3
"""Detector mecánico de giros de tendencia (sin IA, corre a diario).
Evalúa 7 señales de PISO (giro alcista) y 7 de TECHO (giro bajista) sobre la serie
de cierres/volúmenes del histórico. No predice: detecta CAMBIO DE CARÁCTER — la
acumulación de señales suele anticipar en semanas a la tendencia obvia.
Uso como módulo: detect(closes, volumes) -> {"piso": n, "techo": n, ...}"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import metrics  # noqa: E402


def _sma_at(closes, n, i=None):
    i = len(closes) - 1 if i is None else i
    if i + 1 < n:
        return None
    return sum(closes[i - n + 1:i + 1]) / n


def _macd_hist_series(closes):
    if len(closes) < 40:
        return None
    ef = metrics.ema_series(closes, 12)
    es = metrics.ema_series(closes, 26)
    macd = [f - s for f, s in zip(ef, es)]
    sig = metrics.ema_series(macd[25:], 9)
    if not sig:
        return None
    hist = [m - s for m, s in zip(macd[25:], sig)]
    return macd, hist  # hist alineado a closes[25:]


def detect(closes, volumes=None):
    n = len(closes)
    if n < 60:
        return None
    rsi = metrics.rsi_series(closes) or []
    price = closes[-1]
    sma20, sma20_prev = _sma_at(closes, 20), _sma_at(closes, 20, n - 2)
    sma50, sma50_prev = _sma_at(closes, 50), _sma_at(closes, 50, n - 2)
    sma200 = _sma_at(closes, 200) if n >= 200 else None
    piso, techo = [], []

    # 1) divergencia RSI (precio hace extremo nuevo, RSI no lo confirma)
    if rsi and rsi[-1] is not None and n >= 30:
        lo_rec, lo_prev = min(closes[-10:]), min(closes[-30:-10])
        ri_rec = min(x for x in rsi[-10:] if x is not None)
        ri_prev_vals = [x for x in rsi[-30:-10] if x is not None]
        if ri_prev_vals and lo_rec < lo_prev and ri_rec > min(ri_prev_vals) + 2:
            piso.append("divergencia RSI alcista")
        hi_rec, hi_prev = max(closes[-10:]), max(closes[-30:-10])
        rx_rec = max(x for x in rsi[-10:] if x is not None)
        if ri_prev_vals and hi_rec > hi_prev and rx_rec < max(ri_prev_vals) - 2:
            techo.append("divergencia RSI bajista")

    # 2) estructura de mínimos/máximos
    if n >= 30:
        l1, l2, l3 = min(closes[-10:]), min(closes[-20:-10]), min(closes[-30:-20])
        if sma50 and price < sma50 and l1 > l2 > l3:
            piso.append("mínimos crecientes en tendencia bajista")
        h1, h2, h3 = max(closes[-10:]), max(closes[-20:-10]), max(closes[-30:-20])
        if sma50 and price > sma50 and h1 < h2 < h3:
            techo.append("máximos decrecientes en tendencia alcista")

    # 3/4) reconquista o pérdida de medias (cruce de ayer a hoy)
    prev = closes[-2]
    for sm, sm_prev, name in ((sma20, sma20_prev, "SMA20"), (sma50, sma50_prev, "SMA50")):
        if sm and sm_prev:
            if prev <= sm_prev and price > sm and (sma200 is None or price < sma200):
                piso.append(f"reconquista de {name}")
            if prev >= sm_prev and price < sm and (sma200 is None or price > sma200):
                techo.append(f"pérdida de {name}")

    # 5) inflexión del histograma MACD
    mh = _macd_hist_series(closes)
    if mh:
        macd, hist = mh
        if len(hist) >= 3 and None not in hist[-3:]:
            if hist[-1] > hist[-2] > hist[-3] and macd[-1] < 0:
                piso.append("histograma MACD girando al alza")
            if hist[-1] < hist[-2] < hist[-3] and macd[-1] > 0:
                techo.append("histograma MACD girando a la baja")

    # 6) volumen: secado en caída (piso) / clímax en subida (techo)
    vols = [v for v in (volumes or []) if v]
    if len(vols) >= 25:
        v5, v20 = sum(vols[-5:]) / 5, sum(vols[-20:]) / 20
        if sma50 and price < sma50 and v5 < 0.65 * v20:
            piso.append("secado del volumen vendedor")
        if sma50 and price > sma50 and v5 > 1.9 * v20:
            techo.append("clímax de volumen")

    # 7) base/techo plano cerca del extremo anual
    if n >= 60:
        rng12 = (max(closes[-12:]) - min(closes[-12:])) / max(min(closes[-12:]), 1e-9)
        lo_y, hi_y = min(closes[-252:] if n >= 252 else closes), max(closes[-252:] if n >= 252 else closes)
        if rng12 < 0.06 and price < lo_y * 1.10:
            piso.append("base construyéndose sobre el mínimo anual")
        if rng12 < 0.05 and price > hi_y * 0.94:
            techo.append("techo plano bajo el máximo anual")

    return {"piso": len(piso), "techo": len(techo), "max": 7,
            "senales_piso": piso, "senales_techo": techo}
