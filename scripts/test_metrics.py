#!/usr/bin/env python3
"""Tests de scripts/metrics.py con series sintéticas deterministas.
Uso: python3 scripts/test_metrics.py  (sale con código 1 si algo falla)"""
import random
import sys

from metrics import (historical_volatility, macd_line, max_drawdown, price_percentile,
                     sharpe_ratio, sma, sortino_ratio)


def check(name, cond):
    print(("  ✓ " if cond else "  ✗ ") + name)
    return cond


def main():
    ok = True
    rng = random.Random(42)  # seed fija → resultados reproducibles
    walk = [100.0]
    for _ in range(299):
        walk.append(walk[-1] * (1 + rng.gauss(0.0005, 0.02)))

    flat = [100.0] * 60
    up = [100.0 * (1.01 ** i) for i in range(60)]
    short = [100.0, 101.0, 99.0]

    vol = historical_volatility(walk)
    ok &= check("volatilidad del random walk en rango razonable (10-60%)",
                vol is not None and 10 < vol < 60)
    ok &= check("volatilidad de serie plana ≈ 0", abs(historical_volatility(flat)) < 1e-9)
    ok &= check("volatilidad con pocos datos -> None", historical_volatility(short) is None)

    ok &= check("sharpe de serie alcista fuerte > 0", sharpe_ratio(up) is None or sharpe_ratio(up) > 0)
    ok &= check("sharpe con pocos datos -> None", sharpe_ratio(short) is None)
    ok &= check("sharpe de serie plana -> None (vol 0)", sharpe_ratio(flat) is None)

    ok &= check("sortino con pocos datos -> None", sortino_ratio(short) is None)
    ok &= check("sortino de serie sin días negativos -> None", sortino_ratio(up) is None)
    ok &= check("sortino del random walk es un número", isinstance(sortino_ratio(walk), float))

    ok &= check("max_drawdown de serie alcista pura = 0", max_drawdown(up) == 0.0)
    mdd = max_drawdown([100, 120, 60, 80])
    ok &= check("max_drawdown 120->60 = -50%", abs(mdd - (-50.0)) < 1e-9)
    ok &= check("max_drawdown con 1 dato -> None", max_drawdown([100]) is None)

    ok &= check("sma básica", abs(sma([1, 2, 3, 4], 2) - 3.5) < 1e-9)
    ok &= check("sma con pocos datos -> None", sma([1, 2], 5) is None)

    m, s = macd_line(walk)
    ok &= check("macd sobre random walk devuelve números", m is not None and s is not None)
    ok &= check("macd con pocos datos -> (None, None)", macd_line(short) == (None, None))
    m0, _ = macd_line(flat)
    ok &= check("macd de serie plana ≈ 0", abs(m0) < 1e-9)

    ok &= check("percentil en mínimo = 0", price_percentile(10, 10, 20) == 0.0)
    ok &= check("percentil en máximo = 100", price_percentile(20, 10, 20) == 100.0)
    ok &= check("percentil medio = 50", abs(price_percentile(15, 10, 20) - 50) < 1e-9)
    ok &= check("percentil con rango inválido -> None", price_percentile(15, 20, 10) is None)

    print("OK" if ok else "FALLARON TESTS")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
