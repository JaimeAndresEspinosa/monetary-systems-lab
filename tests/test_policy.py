"""Laboratorio de políticas: cada palanca mueve la economía en la dirección que dice su mecanismo,
el contrafactual está emparejado y «¿Y a mí?» compara hogares parecidos."""

import numpy as np
import pytest

from msl import policy
from msl.policy import PRESETS, clean_levers, household, simulate

SMALL = dict(households=800, months=60, seeds=2)


@pytest.fixture(scope="module")
def sims():
    cases = {"none": {}, "smi": {"smi_raise": 0.2}, "rent_cap": {"rent_cap": 0.0},
             "housing": {"public_housing": 8.0, "permits_speed": 2.5}, "wealth": {"wealth_tax": 0.02},
             "pensions": {"pension_ratio": 0.45}, "young": {"first_buyer_aid": 0.1, "first_buyer_ltv": 0.2}}
    return {k: simulate(v, **SMALL) for k, v in cases.items()}


def d(sim, key):
    return sim["macro"][key]["diff"]["p50"]


def test_no_policy_means_no_difference(sims):
    s = sims["none"]
    for key, v in s["macro"].items():
        assert v["diff"]["p50"] == 0.0, key
    assert all(r["disp"]["p50"] == 0.0 for r in s["groups"]["decile"])


def test_minimum_wage_raises_low_incomes_and_costs_some_jobs(sims):
    s = sims["smi"]
    dec = [r["disp"]["p50"] for r in s["groups"]["decile"]]
    assert np.mean(dec[:5]) > 0 > np.mean(dec[5:])     # sube la renta de la mitad de abajo; la de arriba paga precios
    assert d(s, "unemployment:mean") > 0
    # sin efecto sobre el empleo (elasticidad 0) el paro no sube por el SMI
    s0 = simulate({"smi_raise": 0.2, "smi_elasticity": 0.0}, **SMALL)
    assert d(s0, "unemployment:mean") < d(s, "unemployment:mean")


def test_rent_freeze_helps_sitting_tenants_but_raises_market_rent(sims):
    s = sims["rent_cap"]
    assert d(s, "_rent_paid:last") < 0          # lo que pagan de media los inquilinos baja
    assert d(s, "rent_burden:last") > 0         # el alquiler de mercado (contratos nuevos) sube
    ten = s["groups"]["tenure"]
    assert ten[0]["after_housing"]["p50"] > 0 > ten[3]["after_housing"]["p50"]   # inquilinos ganan, caseros pierden


def test_more_housing_supply_lowers_prices_and_rents(sims):
    s = sims["housing"]
    assert d(s, "price_to_income:last") < 0
    assert d(s, "_rent_paid:last") < 0
    assert s["series"]["_public_housing"]["policy"]["p50"][-1] > 0
    assert d(s, "debt_gdp:last") > 0            # se paga con deuda


def test_wealth_tax_falls_on_the_richest(sims):
    s = sims["wealth"]
    dec = [r["disp"]["p50"] for r in s["groups"]["decile"]]
    assert dec[-1] < -0.01
    assert d(s, "debt_gdp:last") < 0


def test_lower_pensions_hurt_retirees_and_cut_debt(sims):
    s = sims["pensions"]
    age = s["groups"]["age"]
    assert age[-1]["disp"]["p50"] < -0.03
    assert d(s, "debt_gdp:last") < 0


def test_first_buyer_aid_raises_young_homeownership(sims):
    s = sims["young"]
    assert d(s, "homeownership:last") > 0
    h = household(s, age=27, income=2500, tenure="renter", savings=5000, years=5)
    assert h["outcomes"]["buy"]["diff"]["p50"] > 0


def test_household_matching_finds_similar_households(sims):
    h = household(sims["smi"], age=30, income=1500, tenure="renter", savings=3000, years=5)
    m = h["matched"]
    assert m["n"] >= 30 and m["same_tenure"] == 1.0
    assert abs(m["age"]["p50"] - 30) < 7          # muestra pequeña en el test; con 12.000 hogares, ±3 años
    assert 1100 < m["income"]["p50"] < 2000
    o = h["outcomes"]
    for key in ("disp", "housing", "burden", "after_housing", "wealth", "pension"):
        assert o[key]["base"]["p10"] <= o[key]["base"]["p50"] <= o[key]["base"]["p90"]
    assert o["disp"]["diff"]["p50"] > 0          # con 1.500 € el SMI le sube el sueldo
    # el factor regional encarece la vivienda pero no la renta
    h2 = household(sims["smi"], age=30, income=1500, tenure="renter", savings=3000, years=5, region_factor=1.5)
    assert h2["outcomes"]["housing"]["base"]["p50"] == pytest.approx(1.5 * o["housing"]["base"]["p50"])
    assert h2["outcomes"]["disp"]["base"]["p50"] == o["disp"]["base"]["p50"]


def test_levers_are_validated_and_clamped():
    assert clean_levers({"vat": 0.5}) == {"vat": policy.LEVERS["vat"]["max"]}
    assert clean_levers({"vat": 0.10}) == {}                      # valor de hoy: no cambia nada
    assert clean_levers({"retirement_age": 68.4}) == {"retirement_age": 68}
    with pytest.raises(ValueError):
        clean_levers({"households": 10})


def test_presets_use_known_levers_and_explain_themselves():
    for key, pr in PRESETS.items():
        assert clean_levers(pr["levers"]), key
        assert pr["label"]
        for field in ("desc", "evidence", "caveats"):
            assert len(pr[field]) > 40, (key, field)
    for key, spec in policy.LEVERS.items():
        assert spec["conf"] in ("alta", "media", "baja")
        assert len(spec["evidence"]) > 40, key
        if spec.get("elasticity"):
            assert spec["elasticity"] in policy.ELASTICITIES


def test_robustness_reports_each_key_assumption():
    r = policy.robustness({"smi_raise": 0.2}, households=500, months=48, seeds=1)
    row = r["elasticities"]["smi_elasticity"]
    # con elasticidad −0,6 el paro sube más que con 0
    assert row["lo"]["unemployment:mean"] > row["hi"]["unemployment:mean"]
