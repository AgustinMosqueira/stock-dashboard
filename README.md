# Dashboard de Research — Equity / FX / Calendario

Dashboard unificado de análisis (15 activos: acciones EE.UU. y Chile, SpaceX, Bitcoin, Harmonic Drive,
CleanSpark y pares FX) con informes de 8-9 secciones, scores compuestos, señales y calendario de eventos.

## Automatización

| Workflow | Cuándo | Qué hace | Costo |
|---|---|---|---|
| `daily-numbers.yml` | Todos los días 18:30 Chile | Actualiza **precio, variación, RSI/MACD, medias móviles, volatilidad/Sharpe/Sortino/drawdown, percentil 1A y comparación vs benchmark** de los 15 activos desde el scanner público de **TradingView**; acumula el **histórico diario** (`data/history/`), loguea cambios bruscos, manda **alertas Telegram** si hay umbrales cruzados, reconstruye y despliega a GitHub Pages | **Gratis** (sin IA) |
| `refresh-reports.yml` | Lunes, miércoles y viernes 18:00 Chile | Re-investiga con Claude los **informes completos** de los 6 dinámicos (SPCX, BTC, HDSY, CLSK, USD/CLP, USD/JPY) y guarda un **snapshot de señales** para el backtest | Usa tu suscripción Claude |
| `backtest.yml` | Día 1 de cada mes (o manual) | Mide si las señales pasadas anticiparon el precio (retornos a 5/10/20 ruedas) → `data/backtest_report.json` | **Gratis** (sin IA) |

Los 9 estáticos (AAPL, MSFT, NVDA, GOOGL, AMZN, TSLA, CCU, CMPC, EUR/USD) actualizan **números a diario**
pero sus textos solo cambian a pedido (pídeselo a Claude en el proyecto local).

**Benchmarks:** acciones EE.UU. → S&P 500 · Chile → ECH (iShares MSCI Chile, proxy del IPSA — el IPSA
no está en el scanner gratuito) · HDSY → Nikkei 225 · CLSK → Bitcoin · BTC → cripto total (ciclo) · FX → DXY.

## Alertas por Telegram (opcional, gratis)

`scripts/telegram_alerts.py` corre a diario tras actualizar los números y manda **un solo mensaje**
agrupado cuando se cruzan umbrales (RSI sobrecompra/sobreventa, golden/death cross, precio vs SMA50/200,
cruce MACD, movimiento diario >5%, percentil extremo del rango anual, pico de volumen, eventos del
calendario a ≤3 días). Umbrales configurables en `scripts/alert_rules.json`. Si no hay alertas, no envía nada.

Setup (una sola vez):
1. En Telegram, habla con **@BotFather** → `/newbot` → guarda el token que te da.
2. Mándale cualquier mensaje a tu bot nuevo, y luego abre en el navegador
   `https://api.telegram.org/bot<TU_TOKEN>/getUpdates` — el `"chat":{"id": ...}` que aparece es tu chat_id.
3. Guarda ambos como secrets del repo:
   ```bash
   gh secret set TELEGRAM_BOT_TOKEN   # pega el token
   gh secret set TELEGRAM_CHAT_ID     # pega el chat_id
   ```
Sin estos secrets el paso simplemente se salta (no falla).

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
- `data/history/<activo>.json` — histórico diario persistente (precio, RSI, MACD, SMAs, volumen, percentil)
- `data/history/signals/` — snapshots de score/señal de cada corrida L-M-V (base del backtest)
- `data/history/metric_changes_log.json` — log de cambios bruscos de métricas
- `build.py` — ensambla `stock-dashboard.html`
- `scripts/update_numbers.py` — números diarios desde TradingView (sin IA, sin dependencias)
- `scripts/metrics.py` + `scripts/test_metrics.py` — métricas de riesgo (funciones puras + tests)
- `scripts/history_store.py` — lectura/escritura del histórico
- `scripts/track_metric_changes.py` — detección de cambios bruscos día a día
- `scripts/telegram_alerts.py` + `scripts/alert_rules.json` — alertas Telegram y sus umbrales
- `scripts/snapshot_signals.py` / `scripts/backtest_signals.py` — señales históricas y su backtest
- `scripts/REFRESH_PROMPT.md` — instrucciones del refresco de informes L-M-V
- `index.html` — salida publicada en Pages

> Herramienta de investigación educativa. No constituye asesoría de inversión.
