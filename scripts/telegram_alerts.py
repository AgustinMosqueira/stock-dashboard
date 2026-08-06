#!/usr/bin/env python3
"""Alertas por Telegram cuando se cruzan umbrales técnicos (Python puro, sin IA).
Corre a diario en daily-numbers.yml DESPUÉS de update_numbers.py; lee lo que ese
script ya calculó (stocks-data.json + data/history/) y las reglas de
scripts/alert_rules.json. Agrupa todo en UN solo mensaje; si no hay alertas, no
envía nada. Credenciales por env: TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID (GitHub
Secrets) — si faltan, el script informa y termina sin error.
Uso: python3 scripts/telegram_alerts.py"""
import datetime
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import history_store  # noqa: E402
import metrics  # noqa: E402
from snapshot_signals import composite, grade_for  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
RULES = json.load(open(HERE / "scripts" / "alert_rules.json"))


def fmt_price(technical):
    p = technical.get("price")
    if p is None:
        return "s/d"
    return f"{p:,.2f}" if p < 10000 else f"{p:,.0f}"


def contexto(a):
    t = a.get("technical") or {}
    d = t.get("change_1d_pct")
    return f"(precio {fmt_price(t)}, día {d:+.2f}%)" if d is not None else f"(precio {fmt_price(t)})"


def crossed(prev_a, prev_b, cur_a, cur_b):
    """'up' si a cruzó por encima de b entre ayer y hoy, 'down' si por debajo."""
    if None in (prev_a, prev_b, cur_a, cur_b):
        return None
    if prev_a <= prev_b and cur_a > cur_b:
        return "up"
    if prev_a >= prev_b and cur_a < cur_b:
        return "down"
    return None


def newly(prev, cur, thr, above=True):
    """True si la condición (>=thr o <=thr) es verdadera hoy y NO lo era ayer
    (con ayer desconocido, alerta igual — mejor un aviso de más que uno de menos)."""
    if cur is None or thr is None:
        return False
    cond_cur = cur >= thr if above else cur <= thr
    if not cond_cur:
        return False
    if prev is None:
        return True
    return not (prev >= thr if above else prev <= thr)


def alerts_for(a):
    tk = a["ticker"]
    t = a.get("technical") or {}
    out = []
    hist = history_store.load(tk)
    prev = hist[-2] if len(hist) >= 2 else {}
    cur = hist[-1] if hist else {}

    # RSI sobrecompra / sobreventa (solo al entrar en la zona)
    rsi, rsi_prev = t.get("rsi"), prev.get("rsi")
    if newly(rsi_prev, rsi, RULES.get("rsi_overbought"), above=True):
        out.append(f"⚠️ *{tk}* — RSI en {rsi:.0f} (sobrecompra). {contexto(a)}")
    if newly(rsi_prev, rsi, RULES.get("rsi_oversold"), above=False):
        out.append(f"⚠️ *{tk}* — RSI en {rsi:.0f} (sobreventa). {contexto(a)}")

    # movimiento diario fuerte
    chg = t.get("change_1d_pct")
    thr = RULES.get("price_change_1d_pct")
    if chg is not None and thr and abs(chg) >= thr:
        emoji = "🟢" if chg > 0 else "🔴"
        out.append(f"{emoji} *{tk}* — movió {chg:+.2f}% en el día. {contexto(a)}")

    # percentil extremo del rango de 1 año (solo al entrar)
    pct, pct_prev = t.get("price_percentile_1y"), prev.get("percentile_1y")
    if newly(pct_prev, pct, RULES.get("price_percentile_1y_high"), above=True):
        out.append(f"📈 *{tk}* — precio en percentil {pct:.0f} de su rango de 1 año "
                   f"(cerca del máximo). {contexto(a)}")
    if newly(pct_prev, pct, RULES.get("price_percentile_1y_low"), above=False):
        out.append(f"📉 *{tk}* — precio en percentil {pct:.0f} de su rango de 1 año "
                   f"(cerca del mínimo). {contexto(a)}")

    # pico de volumen
    vr = t.get("volume_ratio")
    thr = RULES.get("volume_spike_ratio")
    if vr is not None and thr and vr >= thr:
        out.append(f"📊 *{tk}* — volumen {vr:.1f}× su promedio de 20 ruedas. {contexto(a)}")

    # cruces de medias móviles (ayer vs hoy, del histórico)
    watch = (RULES.get("sma_cross") or {}).get("watch", [])
    price_prev, price_cur = prev.get("close"), cur.get("close")
    if "sma50_vs_sma200" in watch:
        c = crossed(prev.get("sma50"), prev.get("sma200"), cur.get("sma50"), cur.get("sma200"))
        if c == "up":
            out.append(f"🟢 *{tk}* — Golden cross: SMA50 superó a la SMA200 "
                       f"(señal alcista clásica de largo plazo). {contexto(a)}")
        elif c == "down":
            out.append(f"🔴 *{tk}* — Death cross: SMA50 cayó bajo la SMA200 "
                       f"(señal bajista clásica de largo plazo). {contexto(a)}")
    for key, name, plazo in (("price_vs_sma200", "SMA200", "largo plazo"),
                             ("price_vs_sma50", "SMA50", "mediano plazo")):
        if key in watch:
            c = crossed(price_prev, prev.get(name.lower()), price_cur, cur.get(name.lower()))
            if c == "up":
                out.append(f"🟢 *{tk}* — Precio cruzó por encima de su {name} "
                           f"(recupera tendencia de {plazo}). {contexto(a)}")
            elif c == "down":
                out.append(f"🔴 *{tk}* — Precio cruzó por debajo de su {name} "
                           f"(pierde tendencia de {plazo}). {contexto(a)}")

    # cruce MACD vs señal
    if (RULES.get("macd_cross") or {}).get("notify_on") == "cross":
        c = crossed(prev.get("macd"), prev.get("macd_signal"), cur.get("macd"), cur.get("macd_signal"))
        if c == "up":
            out.append(f"🟢 *{tk}* — MACD cruzó su señal hacia arriba (momentum alcista). {contexto(a)}")
        elif c == "down":
            out.append(f"🔴 *{tk}* — MACD cruzó su señal hacia abajo (momentum bajista). {contexto(a)}")
    return out


MACRO_KEYS = ["fomc", "fed", "bce", "ecb", "boj", "banco central", "bcch", "tpm", "ipc",
              "cpi", "pce", "payroll", "nfp", "ipom", "halving", "opep", "opec", "jackson hole"]


def _event_key(e):
    """Mismo criterio de agrupación que el calendario del dashboard: solo eventos macro
    compartidos (FOMC, BCE…) se unifican; earnings/corporate son propios de cada activo."""
    if (e.get("kind") or "macro") != "macro":
        return None
    label = (e.get("label") or "").lower()
    for k in MACRO_KEYS:
        if k in label:
            return "k:" + k
    return "l:" + label.strip()


def event_alerts(stocks):
    """Eventos del calendario a N días o menos (Paso 7), agrupando los macro compartidos."""
    days = RULES.get("event_alert_days")
    if not days:
        return []
    today = datetime.date.today()
    groups = {}  # (fecha, clave) -> {label, tickers, delta, d}
    uid = 0
    for a in stocks:
        for e in a.get("events") or []:
            try:
                d = datetime.date.fromisoformat(e.get("date", ""))
            except ValueError:
                continue
            delta = (d - today).days
            if not (0 <= delta <= days):
                continue
            key = _event_key(e)
            if key is None:
                key = f"u:{uid}"
                uid += 1
            gk = (e["date"], key)
            g = groups.setdefault(gk, {"label": e.get("label", "Evento"), "time": e.get("time"),
                                       "tickers": [], "delta": delta, "d": d})
            if a["ticker"] not in g["tickers"]:
                g["tickers"].append(a["ticker"])
            if len(e.get("label", "")) < len(g["label"]):
                g["label"] = e["label"]
            if not g.get("time") and e.get("time"):
                g["time"] = e["time"]
    out = []
    by_ticker = {a["ticker"]: a for a in stocks}
    for g in sorted(groups.values(), key=lambda g: (g["delta"], g["label"])):
        cuando = "HOY" if g["delta"] == 0 else ("mañana" if g["delta"] == 1 else f"en {g['delta']} días")
        hora = f" a las {g['time']} (Chile)" if g.get("time") else ""
        if len(g["tickers"]) == 1:
            a = by_ticker[g["tickers"][0]]
            score = composite(a)
            _, signal = grade_for(score)
            out.append(f"📅 *{g['tickers'][0]}* — {g['label']} {cuando} "
                       f"({g['d'].strftime('%d/%m')}{hora}). Score actual: {score} ({signal}).")
        else:
            out.append(f"📅 {g['label']} — {cuando} ({g['d'].strftime('%d/%m')}{hora}). "
                       f"Afecta a: {', '.join(g['tickers'])}.")
    return out


def econ_alerts():
    """Datos del calendario económico (US/CL) de HOY y MAÑANA: los de importancia alta
    (★★★) con detalle; los de importancia media (★★) resumidos en una línea."""
    days = RULES.get("event_alert_days")
    if days is None:
        return []
    p = HERE / "data" / "econ-calendar.json"
    if not p.exists():
        return []
    try:
        econ = json.load(open(p))
    except ValueError:
        return []
    today = datetime.date.today()
    flags = {"US": "🇺🇸", "CL": "🇨🇱"}
    out = []
    for e in econ:
        try:
            d = datetime.date.fromisoformat(e.get("date", ""))
        except ValueError:
            continue
        delta = (d - today).days
        if not (0 <= delta <= min(days, 1)):
            continue
        if e.get("stars", 0) < 4:
            continue
        cuando = "HOY" if delta == 0 else "mañana"
        extra = []
        if e.get("forecast") is not None:
            extra.append(f"est {e['forecast']}{e.get('unit', '')}")
        if e.get("previous") is not None:
            extra.append(f"prev {e['previous']}{e.get('unit', '')}")
        det = f" · {' · '.join(extra)}" if extra else ""
        out.append(f"🗓️ {flags.get(e.get('country'), '')} {e.get('label')} — {cuando} "
                   f"{e.get('time', '')} h Chile{det}")
    return out


def price_verification(stocks):
    """Verificación multi-fuente: compara los precios del dashboard contra fuentes
    independientes (Binance para BTC, er-api para FX, stooq para acciones si responde).
    Divergencia >2.5% => alerta. Pedido del usuario tras el bug de SPCX (5-ago-2026)."""
    out = []
    prices = {a["ticker"]: ((a.get("technical") or {}).get("price")) for a in stocks}

    def get(url, timeout=15):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode()

    checks = []  # (ticker, valor_alternativo, fuente)
    try:
        b = json.loads(get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"))
        checks.append(("BTC", float(b["price"]), "Binance"))
    except Exception:
        pass
    try:
        rates = json.loads(get("https://open.er-api.com/v6/latest/USD")).get("rates", {})
        if rates.get("JPY"):
            checks.append(("USD/JPY", rates["JPY"], "er-api"))
        if rates.get("EUR"):
            checks.append(("EUR/USD", 1 / rates["EUR"], "er-api"))
    except Exception:
        pass
    # stooq para acciones (best effort; desde algunos IPs no responde)
    import csv, io
    STOOQ = {"AAPL": "aapl.us", "MSFT": "msft.us", "NVDA": "nvda.us", "GOOGL": "googl.us",
             "AMZN": "amzn.us", "TSLA": "tsla.us", "MU": "mu.us", "MSTR": "mstr.us",
             "SPCX": "spcx.us", "CLSK": "clsk.us", "HDSY": "6324.jp"}
    for tk, sym in STOOQ.items():
        try:
            txt = get(f"https://stooq.com/q/l/?s={sym}&f=sd2t2c&e=csv", timeout=10)
            row = list(csv.DictReader(io.StringIO(txt)))
            if row and row[0].get("Close") not in (None, "", "N/D"):
                checks.append((tk, float(row[0]["Close"]), "stooq"))
        except Exception:
            continue

    verificados = 0
    for tk, alt, fuente in checks:
        p = prices.get(tk)
        if not p or not alt:
            continue
        verificados += 1
        drift = (p / alt - 1) * 100
        if abs(drift) > 2.5:
            out.append(f"🚨 *{tk}* — VERIFICACIÓN DE PRECIO: dashboard {p} vs {fuente} {alt:.2f} "
                       f"({drift:+.1f}%). Revisar el feed antes de confiar en este precio.")
    print(f"  verificación multi-fuente: {verificados} precios contrastados, "
          f"{len(out)} divergencias >2.5%")
    return out


def trend_alerts(stocks):
    """Detector de giros: avisa cuando un activo ACUMULA >=4 de 7 señales de piso o
    techo y ayer no las tenía (entrada a zona de giro, no repetición diaria)."""
    out = []
    for a in stocks:
        tr = a.get("trend")
        if not tr:
            continue
        hist = history_store.load(a["ticker"])
        prev = hist[-2] if len(hist) >= 2 else {}
        for lado, emoji, desc in (("piso", "🧭🟢", "PISO (posible giro alcista)"),
                                   ("techo", "🧭🔴", "TECHO (posible giro bajista)")):
            cur_n = tr.get(lado, 0)
            prev_n = prev.get(lado)
            if cur_n >= 4 and (prev_n is None or prev_n < 4):
                sen = ", ".join(tr.get("senales_" + lado, [])[:4])
                out.append(f"{emoji} *{a['ticker']}* — Detector de giro: {cur_n}/7 señales de "
                           f"{desc}: {sen}. {contexto(a)}")
    return out


def fx_drift_check(stocks):
    """Guardián del feed de USD/CLP: compara el precio del dashboard contra er-api
    (fuente independiente). Si el desvío supera 0.7%, avisa — así un feed desviado
    (como pasó con FX_IDC el 29-jul-2026) no vuelve a pasar inadvertido."""
    clp = next((a for a in stocks if a["ticker"] == "USD/CLP"), None)
    price = ((clp or {}).get("technical") or {}).get("price")
    if not price:
        return []
    try:
        req = urllib.request.Request("https://open.er-api.com/v6/latest/USD",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ref = json.load(r).get("rates", {}).get("CLP")
    except Exception:
        return []
    if not ref:
        return []
    drift = (price / ref - 1) * 100
    print(f"  chequeo USD/CLP: dashboard {price} vs referencia {ref:.2f} (desvío {drift:+.2f}%)")
    if abs(drift) > 0.7:
        return [f"⚠️ *USD/CLP* — el feed del dashboard ({price}) difiere {drift:+.1f}% de la "
                f"referencia independiente ({ref:.2f}). Revisar la fuente antes de confiar en el precio."]
    return []


def send(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("Telegram no configurado (faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) — "
              "no se envía nada. Ver README para el setup.")
        return False
    # deja constancia en el log de por cuál bot sale el mensaje (evita confusiones si
    # hubiera otro token de Telegram en el ambiente — el oficial es el del secret de GitHub)
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=15) as r:
            me = json.load(r).get("result", {})
        print(f"  enviando vía @{me.get('username')} al chat {chat}")
    except Exception:
        pass

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    def _post(params):
        body = urllib.parse.urlencode(params).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=30) as r:
            return json.load(r)

    try:
        resp = _post({"chat_id": chat, "text": text, "parse_mode": "Markdown",
                      "disable_web_page_preview": "true"})
    except urllib.error.HTTPError as e:
        # típico 400: un _ o * del contenido rompe el Markdown legacy → reintento plano
        print(f"  aviso: sendMessage con Markdown falló ({e.code}); reintento sin formato")
        resp = _post({"chat_id": chat, "text": text.replace("*", ""),
                      "disable_web_page_preview": "true"})
    return bool(resp.get("ok"))


def main():
    stocks = json.load(open(HERE / "stocks-data.json"))
    lines = []
    for a in stocks:
        lines.extend(alerts_for(a))
    lines.extend(event_alerts(stocks))
    lines.extend(econ_alerts())
    lines.extend(fx_drift_check(stocks))
    lines.extend(trend_alerts(stocks))
    lines.extend(price_verification(stocks))

    if not lines:
        print("Sin alertas hoy — no se envía mensaje (por diseño, para no hacer ruido).")
        return

    fecha = datetime.date.today().strftime("%d/%m/%Y")
    msg = f"*Alertas del dashboard — {fecha}*\n\n" + "\n\n".join(lines) + \
        "\n\n_Señales mecánicas según umbrales configurados en el repo. No es asesoría._"
    print(f"Alertas ({len(lines)}):")
    for l in lines:
        print("  " + l.replace("*", ""))
    if send(msg):
        print("✓ mensaje enviado a Telegram")


if __name__ == "__main__":
    main()
