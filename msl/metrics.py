"""Medidas de desigualdad y descripción de cada métrica que muestra la web."""

from __future__ import annotations

import numpy as np


def gini(x: np.ndarray) -> float:
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    total = x.sum()
    if n == 0 or total <= 0:
        return 0.0
    cum = np.cumsum(x)
    return float((n + 1 - 2 * (cum / total).sum()) / n)


def top_share(x: np.ndarray, q: float) -> float:
    x = np.sort(np.asarray(x, dtype=float))[::-1]
    total = x.sum()
    if total <= 0:
        return 0.0
    k = max(1, int(round(q * len(x))))
    return float(x[:k].sum() / total)


# fmt: unidad de la web · better: qué dirección es deseable (para colorear)
METRICS = {
    "inflation":        {"label": "Inflación interanual", "fmt": "pct", "better": "target", "group": "Precios"},
    "price_level":      {"label": "Nivel de precios", "fmt": "idx", "better": None, "group": "Precios"},
    "unemployment":     {"label": "Paro", "fmt": "pct", "better": "low", "group": "Empleo"},
    "real_wage":        {"label": "Salario real", "fmt": "idx", "better": "high", "group": "Empleo"},
    "real_gdp":         {"label": "PIB real", "fmt": "idx", "better": "high", "group": "Actividad"},
    "gini_wealth":      {"label": "Gini de la riqueza", "fmt": "dec", "better": "low", "group": "Desigualdad"},
    "gini_income":      {"label": "Gini de la renta", "fmt": "dec", "better": "low", "group": "Desigualdad"},
    "top10_wealth":     {"label": "Riqueza del 10 % más rico", "fmt": "pct", "better": "low", "group": "Desigualdad"},
    "bottom50_wealth":  {"label": "Riqueza del 50 % más pobre", "fmt": "pct", "better": "high", "group": "Desigualdad"},
    "house_price_real": {"label": "Precio real de la vivienda", "fmt": "idx", "better": None, "group": "Vivienda"},
    "price_to_income":  {"label": "Años de salario por vivienda", "fmt": "x", "better": "low", "group": "Vivienda"},
    "homeownership":    {"label": "Hogares propietarios", "fmt": "pct", "better": "high", "group": "Vivienda"},
    "rent_burden":      {"label": "Alquiler / salario mediano", "fmt": "pct", "better": "low", "group": "Vivienda"},
    "broad_money":      {"label": "Dinero total / PIB inicial", "fmt": "x", "better": None, "group": "Dinero"},
    "base_money":       {"label": "Dinero base / PIB inicial", "fmt": "x", "better": None, "group": "Dinero"},
    "new_money":        {"label": "Emisión de dinero base (anual, % PIB)", "fmt": "pct", "better": None, "group": "Dinero"},
    "credit_gdp":       {"label": "Crédito / PIB", "fmt": "pct", "better": None, "group": "Finanzas"},
    "debt_gdp":         {"label": "Deuda pública / PIB", "fmt": "pct", "better": "low", "group": "Finanzas"},
    "policy_rate":      {"label": "Tipo de interés oficial", "fmt": "pct", "better": None, "group": "Finanzas"},
    "mortgage_rate":    {"label": "Tipo hipotecario", "fmt": "pct", "better": None, "group": "Finanzas"},
    "foreclosures":     {"label": "Ejecuciones hipotecarias (acum.)", "fmt": "pct", "better": "low", "group": "Finanzas"},
    "bank_capital":     {"label": "Capital bancario / préstamos", "fmt": "pct", "better": None, "group": "Finanzas"},
    "stock_index":      {"label": "Bolsa (valor real de las empresas)", "fmt": "idx", "better": None, "group": "Finanzas"},
    "bailouts":         {"label": "Rescates bancarios (acum., % PIB)", "fmt": "pct", "better": "low", "group": "Finanzas"},
    "cbdc_share":       {"label": "Dinero en euro digital", "fmt": "pct", "better": None, "group": "Dinero"},
    "tax_gap":          {"label": "Impuestos evadidos (% PIB)", "fmt": "pct", "better": "low", "group": "Estado"},
    "demurrage":        {"label": "Recaudación por oxidación (% PIB)", "fmt": "pct", "better": None, "group": "Estado"},
}

# Resumen que aparece en las tarjetas y en el explorador
SUMMARY = [
    ("inflation", "mean"), ("unemployment", "mean"), ("real_wage", "last"),
    ("gini_wealth", "delta"), ("top10_wealth", "delta"), ("house_price_real", "last"),
    ("price_to_income", "last"), ("real_gdp", "last"), ("debt_gdp", "last"),
    ("foreclosures", "last"), ("stock_index", "last"), ("bailouts", "last"),
    ("tax_gap", "mean"), ("unemployment", "max"), ("real_gdp", "min"),
]


def summarize(series: dict[str, list[float]]) -> dict[str, float]:
    out = {}
    for key, how in SUMMARY:
        s = np.asarray(series[key])
        if how == "mean":
            out[f"{key}:{how}"] = float(s[12:].mean() if len(s) > 12 else s.mean())
        elif how == "max":
            out[f"{key}:{how}"] = float(s.max())
        elif how == "min":
            out[f"{key}:{how}"] = float(s.min())
        elif how == "last":
            out[f"{key}:{how}"] = float(s[-1])
        else:
            out[f"{key}:{how}"] = float(s[-1] - s[0])
    return out
