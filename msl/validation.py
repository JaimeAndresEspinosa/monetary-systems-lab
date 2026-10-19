"""Validación frente a datos reales de España (Fase 3).

Dos niveles, como es habitual en los modelos de agentes:
  1. Momentos: niveles medios del sistema actual frente a Eurostat y BCE.
  2. Hechos estilizados: relaciones que el modelo no impone y que debería
     reproducir (ley de Okun, curva de Phillips, volatilidades relativas).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from .config import Params, Regime
from .model import Model

DATA = Path(__file__).resolve().parents[1] / "data" / "spain.json"

# Ventana de referencia: los últimos años, ya fuera de la crisis de 2008–2013
WINDOW = ("2015", "2025")

MOMENTS = {
    "unemployment": {"label": "Paro medio", "fmt": "pct", "weight": 1.0},
    "inflation": {"label": "Inflación media", "fmt": "pct", "weight": 1.0},
    "debt_gdp": {"label": "Deuda pública / PIB", "fmt": "pct", "weight": 0.6},
    "credit_gdp": {"label": "Deuda privada / PIB", "fmt": "pct", "weight": 0.6},
    "top10_wealth": {"label": "Riqueza del 10 % más rico", "fmt": "pct", "weight": 1.0},
    "bottom50_wealth": {"label": "Riqueza del 50 % más pobre", "fmt": "pct", "weight": 0.6},
    "gini_income": {"label": "Gini de la renta", "fmt": "dec", "weight": 0.4},
}


def load_real() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _window(values: dict[str, float], start=WINDOW[0], end=WINDOW[1]) -> np.ndarray:
    return np.array([v for y, v in values.items() if start <= y <= end and v is not None])


def real_moments(real: dict | None = None) -> dict:
    real = real or load_real()
    s = real["series"]
    out = {k: float(_window(s[k]["values"]).mean()) for k in MOMENTS}
    # hechos estilizados con datos anuales 2000–2025
    u = s["unemployment"]["values"]
    g = s["gdp_growth"]["values"]
    pi = s["inflation"]["values"]
    w = s["comp_per_employee"]["values"]
    years = sorted(set(u) & set(g) & set(w))
    U = np.array([u[y] for y in years]); G = np.array([g[y] for y in years])
    W = np.array([w[y] for y in years])
    dU = np.diff(U); Gs = G[1:]; wg = np.diff(W) / W[:-1]
    out["okun"] = float(np.corrcoef(Gs, dU)[0, 1])
    out["phillips"] = float(np.corrcoef(U[1:], wg)[0, 1])
    pyears = sorted(set(pi) & set(g))
    out["vol_ratio"] = float(np.std([pi[y] for y in pyears]) / np.std([g[y] for y in pyears]))
    out["years_stylized"] = f"{years[0]}–{years[-1]}"
    return out


def _annual(x: np.ndarray, how: str = "mean") -> np.ndarray:
    n = len(x) // 12
    x = np.asarray(x[: n * 12]).reshape(n, 12)
    return x.mean(axis=1) if how == "mean" else x[:, -1]


def model_moments(params: Params, seeds: int = 4, regime: Regime | None = None) -> dict:
    regime = regime or Regime()
    acc: dict[str, list[float]] = {}
    for k in range(seeds):
        m = Model(regime, replace(params, seed=params.seed + k))
        for _ in range(params.months):
            m.step()
        h = {key: np.asarray(v) for key, v in m.history.items()}
        res = m.result()
        # cuotas con el ranking del final (como las publica el BCE), no del inicio
        nw = np.maximum(m.net_worth(), 0)
        order = np.sort(nw)[::-1]
        top10 = order[: len(order) // 10].sum() / order.sum()
        bottom50 = np.sort(nw)[: len(nw) // 2].sum() / nw.sum()
        U = _annual(h["unemployment"])
        Y = _annual(h["real_gdp"])
        P = _annual(h["price_level"])
        Wn = _annual(h["real_wage"] * h["price_level"])
        gy, gw, gp = np.diff(Y) / Y[:-1], np.diff(Wn) / Wn[:-1], np.diff(P) / P[:-1]
        vals = {
            "unemployment": float(h["unemployment"][12:].mean()),
            "inflation": float(h["inflation"][12:].mean()),
            "debt_gdp": float(h["debt_gdp"][-12:].mean()),
            "credit_gdp": float(h["credit_gdp"][-12:].mean()),
            "top10_wealth": float(top10),
            "bottom50_wealth": float(bottom50),
            "gini_income": float(h["gini_income"][12:].mean()),
            "okun": float(np.corrcoef(gy, np.diff(U))[0, 1]),
            "phillips": float(np.corrcoef(U[1:], gw)[0, 1]),
            "vol_ratio": float(np.std(gp) / max(np.std(gy), 1e-9)),
            "sfc": res["sfc_max_error"],
        }
        for key, v in vals.items():
            acc.setdefault(key, []).append(v)
    return {k: float(np.nanmedian(v)) for k, v in acc.items()}


def distance(model: dict, real: dict) -> float:
    """Error cuadrático relativo ponderado entre momentos del modelo y reales."""
    return float(sum(w["weight"] * ((model[k] - real[k]) / max(abs(real[k]), 0.02)) ** 2
                     for k, w in MOMENTS.items()))
