# Dashboard de Research — Equity / FX / Calendario

Dashboard unificado de análisis (15 activos: acciones EE.UU. y Chile, SpaceX, Bitcoin, Harmonic Drive,
CleanSpark y pares FX) con informes de 8-9 secciones, scores compuestos, señales y calendario de eventos.

## Automatización

| Workflow | Cuándo | Qué hace | Costo |
|---|---|---|---|
| `daily-numbers.yml` | Todos los días 18:30 Chile | Actualiza **precio, variación día/semana y RSI/MACD** de los 15 activos desde el scanner público de **TradingView**, reconstruye y despliega a GitHub Pages | **Gratis** (sin IA) |
| `refresh-reports.yml` | Lunes, miércoles y viernes 18:00 Chile | Re-investiga con Claude los **informes completos** de los 6 dinámicos (SPCX, BTC, HDSY, CLSK, USD/CLP, USD/JPY) | Usa tu suscripción Claude |

Los 9 estáticos (AAPL, MSFT, NVDA, GOOGL, AMZN, TSLA, CCU, CMPC, EUR/USD) actualizan **números a diario**
pero sus textos solo cambian a pedido (pídeselo a Claude en el proyecto local).

## Setup (una sola vez)

1. Crear el repo y subir este directorio:
   ```bash
   cd "stock-research/dashboard"
   gh repo create stock-dashboard --private --source . --push
   ```
2. Activar GitHub Pages: repo → Settings → Pages → Source: **GitHub Actions**.
   (o `gh api repos/{owner}/stock-dashboard/pages -X POST -f build_type=workflow`)
3. Para los informes L-M-V con Claude: generar un token con `claude setup-token` y guardarlo:
   ```bash
   gh secret set CLAUDE_CODE_OAUTH_TOKEN
   ```
4. Probar: pestaña Actions → "Números diarios (TradingView)" → Run workflow. El dashboard queda en
   `https://<usuario>.github.io/stock-dashboard/`.

## Estructura

- `template.html` — plantilla (UI + estáticos horneados; tokens `__DATA_DATE__` y `__STOCKS_JSON__`)
- `stocks-data.json` — datos de los 15 activos (fuente de verdad)
- `data/*.json` — copia por activo
- `build.py` — ensambla `stock-dashboard.html`
- `scripts/update_numbers.py` — números diarios desde TradingView (sin IA, sin dependencias)
- `scripts/REFRESH_PROMPT.md` — instrucciones del refresco de informes L-M-V
- `index.html` — salida publicada en Pages

> Herramienta de investigación educativa. No constituye asesoría de inversión.
