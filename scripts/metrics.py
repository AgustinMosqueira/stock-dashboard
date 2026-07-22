#!/usr/bin/env python3
"""Métricas de riesgo y técnicas calculadas sobre una serie de precios de cierre
(lista de floats en orden cronológico). Funciones puras, solo stdlib, sin red.
Todas devuelven None si no hay datos suficientes en vez de fallar."""
import math

TRADING_DAYS = 252


def _log_returns(prices):
    return [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))
            if prices[i] > 0 and prices[i - 1] > 0]


def _std(xs):
    if len(xs) < 2:
        return None
    mean = sum(xs) / len(xs)
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1))


def historical_volatility(prices, window=30):
    """Volatilidad anualizada en %: desvío estándar de retornos log diarios de la
    última `window` de ruedas * sqrt(252)."""
    if prices is None or len(prices) < window:
        return None
    rets = _log_returns(prices[-window:])
    sd = _std(rets)
    return sd * math.sqrt(TRADING_DAYS) * 100 if sd is not None else None


def _annualized_return(prices, window):
    """Retorno anualizado simple de la ventana, en fracción (0.10 = 10%)."""
    p0, p1 = prices[-window], prices[-1]
    if p0 <= 0:
        return None
    total = p1 / p0 - 1
    years = (window - 1) / TRADING_DAYS
    if years <= 0:
        return None
    # anualización geométrica; cae a lineal si la base es negativa extrema
    base = 1 + total
    return base ** (1 / years) - 1 if base > 0 else total / years


def sharpe_ratio(prices, risk_free_rate=0.045, window=30):
    """Sharpe aproximado: (retorno anualizado - tasa libre de riesgo) / volatilidad.
    risk_free_rate anual en fracción (0.045 = 4.5%)."""
    if prices is None or len(prices) < window:
        return None
    vol = historical_volatility(prices, window)
    ret = _annualized_return(prices, window)
    if vol is None or vol == 0 or ret is None:
        return None
    return (ret - risk_free_rate) / (vol / 100)


def sortino_ratio(prices, risk_free_rate=0.045, window=30):
    """Como Sharpe pero penaliza solo el desvío de los retornos negativos
    (downside deviation)."""
    if prices is None or len(prices) < window:
        return None
    rets = _log_returns(prices[-window:])
    downside = [r for r in rets if r < 0]
    if len(downside) < 2:
        return None
    dd = math.sqrt(sum(r ** 2 for r in downside) / len(downside)) * math.sqrt(TRADING_DAYS)
    ret = _annualized_return(prices, window)
    if dd == 0 or ret is None:
        return None
    return (ret - risk_free_rate) / dd


def max_drawdown(prices):
    """Máxima caída en % desde un máximo previo (valor negativo, ej. -18.5).
    None con menos de 2 precios."""
    if prices is None or len(prices) < 2:
        return None
    peak = prices[0]
    mdd = 0.0
    for p in prices:
        if p > peak:
            peak = p
        if peak > 0:
            dd = (p / peak - 1) * 100
            if dd < mdd:
                mdd = dd
    return mdd


# — Medias móviles / MACD sobre la serie (para detección de cruces día a día) —

def sma(prices, n):
    if prices is None or len(prices) < n:
        return None
    return sum(prices[-n:]) / n


def ema_series(prices, n):
    """Serie EMA completa (misma longitud que prices) o None si faltan datos."""
    if prices is None or len(prices) < n:
        return None
    k = 2 / (n + 1)
    out = [sum(prices[:n]) / n] * n  # semilla: SMA de las primeras n
    for p in prices[n:]:
        out.append(p * k + out[-1] * (1 - k))
    return out


def macd_line(prices, fast=12, slow=26, signal=9):
    """Devuelve (macd, señal) del último día calculados sobre la serie, o (None, None)."""
    if prices is None or len(prices) < slow + signal:
        return (None, None)
    ef, es = ema_series(prices, fast), ema_series(prices, slow)
    macd_full = [f - s for f, s in zip(ef, es)]
    macd_valid = macd_full[slow - 1:]
    sig = ema_series(macd_valid, signal)
    return (macd_full[-1], sig[-1] if sig else None)


def price_percentile(price, low, high):
    """Percentil 0-100 del precio dentro del rango [low, high]; None si el rango es inválido."""
    if price is None or low is None or high is None or high <= low:
        return None
    return max(0.0, min(100.0, (price - low) / (high - low) * 100))
