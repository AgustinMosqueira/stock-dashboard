#!/usr/bin/env python3
"""Avisos de calendario económico por Telegram, con precisión de minutos (a diferencia
de telegram_alerts.py, que corre una sola vez al día). Pedido del usuario, dos mecanismos:
  1) Resumen de TODO lo del día siguiente, una vez, a las 19:00 hora Chile.
  2) Aviso individual 10-15 min antes de cada dato que tiene horario propio, durante el día.
Corre cada 5 min vía cron (calendar-notify.yml). Guarda en
data/calendar-alert-state.json qué ya se avisó, para no repetir si el workflow se
dispara más de una vez dentro de la misma ventana (los cron de GitHub son erráticos).
Uso: python3 scripts/calendar_notify.py"""
import datetime
import json
import pathlib
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from telegram_alerts import send  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
TZ = ZoneInfo("America/Santiago")
STATE_PATH = HERE / "data" / "calendar-alert-state.json"
FLAGS = {"US": "🇺🇸", "CL": "🇨🇱"}


def load_state():
    if not STATE_PATH.exists():
        return {"digest_sent": [], "event_sent": []}
    try:
        return json.load(open(STATE_PATH))
    except ValueError:
        return {"digest_sent": [], "event_sent": []}


def save_state(now, state):
    # nos quedamos solo con lo de los últimos 10 días — el archivo no debe crecer sin límite
    cutoff = (now.date() - datetime.timedelta(days=10)).isoformat()
    state["digest_sent"] = [d for d in state["digest_sent"] if d >= cutoff]
    state["event_sent"] = [e for e in state["event_sent"] if e.split("|", 1)[0] >= cutoff]
    json.dump(state, open(STATE_PATH, "w"), ensure_ascii=False, indent=1)


def fmt_event(e):
    flag = FLAGS.get(e.get("country"), "")
    extra = []
    if e.get("forecast") is not None:
        extra.append(f"est {e['forecast']}{e.get('unit', '')}")
    if e.get("previous") is not None:
        extra.append(f"prev {e['previous']}{e.get('unit', '')}")
    det = f" ({' · '.join(extra)})" if extra else ""
    estrellas = "★" * e.get("stars", 0)
    return f"{flag} {e.get('time', '?')} h — *{e['label']}* {estrellas}{det}"


def digest(now, econ, state):
    """A las 19:00 Chile: resumen de TODO lo del día siguiente, una sola vez por día.
    Devuelve True si hubo que tocar el estado (y por lo tanto hay que persistirlo)."""
    if now.hour != 19:
        return False
    today_iso = now.date().isoformat()
    if today_iso in state["digest_sent"]:
        return False
    state["digest_sent"].append(today_iso)  # se marca igual sin eventos: no reintentar hoy
    manana = (now.date() + datetime.timedelta(days=1)).isoformat()
    eventos = sorted((e for e in econ if e.get("date") == manana),
                      key=lambda e: e.get("time", ""))
    if eventos:
        cuerpo = "\n".join(fmt_event(e) for e in eventos)
        fecha_fmt = datetime.date.fromisoformat(manana).strftime("%d/%m")
        msg = (f"🗓️ *Calendario de mañana ({fecha_fmt})*\n\n{cuerpo}\n\n"
               "_Aviso automático — 19:00 hora Chile._")
        if send(msg):
            print(f"✓ resumen del día siguiente enviado ({len(eventos)} eventos)")
    else:
        print("Resumen 19:00: sin eventos mañana, no se envía nada.")
    return True


def per_event(now, econ, state):
    """Aviso individual 10-15 min antes de cada dato con horario propio, durante el día.
    Devuelve True si avisó de al menos un evento (y por lo tanto hay que persistir)."""
    hoy_iso = now.date().isoformat()
    changed = False
    for e in econ:
        if e.get("date") != hoy_iso or not e.get("time"):
            continue
        try:
            hh, mm = e["time"].split(":")
            ev_dt = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        except ValueError:
            continue
        minutos_para = (ev_dt - now).total_seconds() / 60
        # ventana 0-15 (no exacta 10-15): el cron de GitHub puede atrasarse varios
        # minutos — mejor avisar un poco antes de tiempo que arriesgarse a no avisar.
        if not (0 < minutos_para <= 15):
            continue
        uid = f"{e['date']}|{e['time']}|{e['label']}"
        if uid in state["event_sent"]:
            continue
        state["event_sent"].append(uid)
        changed = True
        msg = (f"⏰ *En ~{int(round(minutos_para))} min:* {e['label']} "
               f"({e['time']} h Chile) {FLAGS.get(e.get('country'), '')}\n\n{fmt_event(e)}")
        if send(msg):
            print(f"✓ aviso previo enviado: {e['label']} ({e['time']})")
    return changed


def main():
    econ_path = HERE / "data" / "econ-calendar.json"
    if not econ_path.exists():
        print("Sin data/econ-calendar.json — nada que avisar.")
        return
    econ = json.load(open(econ_path))
    now = datetime.datetime.now(TZ)
    state = load_state()
    changed = digest(now, econ, state) | per_event(now, econ, state)
    if changed:
        save_state(now, state)
    else:
        print("Sin novedades en esta pasada.")


if __name__ == "__main__":
    main()
