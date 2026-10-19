"""Validación económica: el sistema actual tiene que parecerse a una economía real
antes de fiarse de lo que dice sobre sistemas alternativos."""

import numpy as np

from msl import Params, Regime, monte_carlo
from msl.metrics import gini, top_share

P = Params(households=1200, months=120)


def test_baseline_reproduces_stylised_facts():
    res = monte_carlo(Regime(), P, seeds=4)
    s = {k: np.asarray(v["p50"]) for k, v in res["series"].items()}
    assert 0.06 < s["unemployment"].mean() < 0.13          # paro en torno a su nivel natural
    assert 0.0 < s["inflation"][12:].mean() < 0.04         # inflación cerca del objetivo
    assert 0.45 < s["gini_wealth"].mean() < 0.75           # España ≈ 0,69 (EFF)
    assert 0.3 < s["debt_gdp"][-1] < 1.3
    assert 0.3 < s["credit_gdp"][-1] < 1.2
    assert res["sfc_max_error"] < 1e-9


def test_fixed_supply_has_lower_inflation_than_discretionary():
    base = monte_carlo(Regime(), P, seeds=3)
    fixed = monte_carlo(Regime("fixed_supply", "banks", "fractional"), P, seeds=3)
    assert fixed["summary"]["inflation:mean"]["p50"] < base["summary"]["inflation:mean"]["p50"]


def test_results_are_reproducible_with_the_same_seed():
    a = monte_carlo(Regime(), Params(households=300, months=24), seeds=2)
    b = monte_carlo(Regime(), Params(households=300, months=24), seeds=2)
    assert a["series"]["inflation"] == b["series"]["inflation"]


def test_inequality_measures():
    assert gini(np.ones(100)) == 0.0
    x = np.zeros(100)
    x[-1] = 1.0
    assert gini(x) > 0.98
    assert top_share(np.arange(1, 11), 0.1) == 10 / 55
