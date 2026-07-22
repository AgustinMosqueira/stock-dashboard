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


def event_alerts(stocks):
    """Eventos del calendario a N días o menos (Paso 7)."""
    days = RULES.get("event_alert_days")
    if not days:
        return []
    today = datetime.date.today()
    out = []
    for a in stocks:
        for e in a.get("events") or []:
            try:
                d = datetime.date.fromisoformat(e.get("date", ""))
            except ValueError:
                continue
            delta = (d - today).days
            if 0 <= delta <= days:
                score = composite(a)
                _, signal = grade_for(score)
                cuando = "HOY" if delta == 0 else ("mañana" if delta == 1 else f"en {delta} días")
                out.append(f"📅 *{a['ticker']}* — {e.get('label', 'Evento')} {cuando} "
                           f"({d.strftime('%d/%m')}). Score actual: {score} ({signal}).")
    return out


def send(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("Telegram no configurado (faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) — "
              "no se envía nada. Ver README para el setup.")
        return False
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
