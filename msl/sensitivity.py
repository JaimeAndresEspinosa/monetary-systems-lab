"""Análisis de sensibilidad global (índices de Sobol).

Responde a: ¿qué supuestos del modelo mueven de verdad cada resultado? Para cada
parámetro se calcula
  S1  efecto de primer orden: parte de la varianza del resultado que explica ese
      parámetro por sí solo.
  ST  efecto total: incluye sus interacciones con los demás.
Estimadores de Saltelli (2010) para S1 y de Jansen (1999) para ST, con matrices
A, B y A_B^(i). Coste: N · (D + 2) simulaciones, más N para medir el ruido.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace

import numpy as np

from .config import Params, Regime
from .metrics import summarize
from .model import run

# Parámetros inciertos y su rango plausible
FACTORS = {
    "natural_unemployment": ("Paro natural", 0.07, 0.13),
    "phillips": ("Pendiente de la curva de Phillips", 0.3, 0.9),
    "mpc_high": ("Propensión a consumir (rentas altas)", 0.80, 0.90),
    "hoarding": ("Sensibilidad del consumo al tipo real", 2.0, 6.0),
    "credibility": ("Credibilidad de la regla", 0.05, 0.30),
    "money_rate_sens": ("Sensibilidad del tipo al dinero", 0.05, 0.30),
    "investment_rate_sens": ("Sensibilidad de la inversión al tipo", 1.5, 4.5),
    "ltv": ("LTV máximo hipotecario", 0.6, 0.9),
}
OUTPUTS = ["inflation:mean", "unemployment:mean", "top10_wealth:delta",
           "gini_wealth:delta", "price_to_income:last", "debt_gdp:last"]


def corrected(s1: list[float], st: list[float], noise: float) -> dict:
    """Índices como parte de la varianza NO aleatoria: se descuenta la varianza que produce
    el azar de la simulación (medida con parámetros fijos y semillas distintas)."""
    if noise >= 0.9:
        return {"S1c": [None] * len(s1), "STc": [None] * len(st)}
    k = 1 - noise
    return {"S1c": [min(1.0, max(0.0, x / k)) for x in s1],
            "STc": [min(1.0, max(0.0, (x - noise) / k)) for x in st]}


def _eval(args):
    regime_key, params = args
    return summarize(run(Regime.from_key(regime_key), params)["series"])


def sobol(regime: Regime, base: Params, n: int = 64, seed: int = 0,
          workers: int | None = None) -> dict:
    rng = np.random.default_rng(seed)
    names = list(FACTORS)
    d = len(names)
    lo = np.array([FACTORS[k][1] for k in names])
    hi = np.array([FACTORS[k][2] for k in names])
    A = lo + rng.random((n, d)) * (hi - lo)
    B = lo + rng.random((n, d)) * (hi - lo)
    mats = [A, B] + [np.where(np.arange(d) == i, B, A) for i in range(d)]
    rows = np.vstack(mats)
    # misma semilla de la economía en las N filas emparejadas: solo cambian los parámetros
    jobs = [(regime.key, replace(base, seed=1 + (j % n), **{k: float(v) for k, v in zip(names, row)}))
            for j, row in enumerate(rows)]
    # ruido: los mismos parámetros (punto medio) con N semillas distintas. Mide qué parte de
    # la varianza es puro azar de la simulación y no se debe a ningún supuesto.
    mid = {k: float(v) for k, v in zip(names, (lo + hi) / 2)}
    noise_jobs = [(regime.key, replace(base, seed=1000 + j, **mid)) for j in range(n)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_eval, jobs, chunksize=8))
        noise = list(ex.map(_eval, noise_jobs, chunksize=8))

    out = {}
    for key in OUTPUTS:
        y = np.array([r[key] for r in res])
        fA, fB = y[:n], y[n:2 * n]
        var = np.var(np.concatenate([fA, fB]))
        s1, st = [], []
        for i in range(d):
            fAB = y[(2 + i) * n:(3 + i) * n]
            if var < 1e-14:
                s1.append(0.0); st.append(0.0)
                continue
            s1.append(float(np.mean(fB * (fAB - fA)) / var))
            st.append(float(0.5 * np.mean((fA - fAB) ** 2) / var))
        noise_share = min(1.0, float(np.var([r[key] for r in noise]) / var)) if var > 1e-14 else 0.0
        out[key] = {"S1": s1, "ST": st, "mean": float(np.mean(fA)), "std": float(np.std(fA)),
                    "noise_share": noise_share, **corrected(s1, st, noise_share)}
    return {"regime": regime.key, "label": regime.label, "n": n, "runs": len(rows) + n,
            "factors": [{"key": k, "label": FACTORS[k][0], "lo": FACTORS[k][1], "hi": FACTORS[k][2]}
                        for k in names],
            "outputs": out}
