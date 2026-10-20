"""La contabilidad tiene que cuadrar siempre: en cualquier régimen, en cualquier mes."""

import numpy as np
import pytest

from dataclasses import replace

from msl import Params, Regime
from msl.config import SHOCKS
from msl.economy import Economy
from msl.model import Model

SMALL = Params(households=300, months=36, burn_in=12)
TINY = Params(households=150, months=24, burn_in=6, shock_month=6)


@pytest.mark.parametrize("regime", Regime.all(), ids=lambda r: r.key)
def test_every_regime_is_stock_flow_consistent(regime):
    m = Model(regime, TINY)
    for _ in range(TINY.months):
        m.step()
        assert m.e.check() < 1e-9, f"descuadre en el mes {m.t}"


@pytest.mark.parametrize("shock", [s for s in SHOCKS if s != "none"])
@pytest.mark.parametrize("regime", Regime.core(), ids=lambda r: r.key)
def test_every_crisis_is_stock_flow_consistent(regime, shock):
    p = replace(TINY, shock=shock)
    m = Model(regime, p)
    for _ in range(p.months):
        m.step()
        assert m.e.check() < 1e-9, f"descuadre en el mes {m.t} ({shock})"


@pytest.mark.parametrize("regime", Regime.core() + [Regime(money="cbdc"), Regime(money="demurrage")],
                         ids=lambda r: r.key)
def test_balance_sheet_columns_and_rows_close(regime):
    m = Model(regime, SMALL)
    for _ in range(12):
        m.step()
    res = m.result()
    rows = {r["key"]: r for r in res["balance_sheet"]["rows"]}
    # cada instrumento financiero suma cero entre sectores (el activo de uno es el pasivo de otro)
    scale = m.e.bank_dep_liab
    for key in ("deposits", "investment", "loans", "reserves", "treasury", "bonds", "cb_loans", "cbdc"):
        assert abs(rows[key]["total"]) < 1e-9 * scale, key
    # por tanto la riqueza neta total es igual a los activos reales (viviendas)
    assert rows["net"]["total"] == pytest.approx(rows["houses"]["total"], rel=1e-9)


def test_full_reserve_keeps_every_deposit_backed():
    m = Model(Regime("fixed_supply", "miners", "full_reserve"), SMALL)
    for _ in range(SMALL.months):
        m.step()
        assert m.e.bank_res >= m.e.bank_dep_liab - 1e-6


def test_bank_lending_creates_and_repayment_destroys_money():
    e = Economy(3)
    e.bank_res = e.cb_res_liab = 100.0
    e.gov_acct = e.cb_acct_liab = 0.0
    before = e.deposits
    e.lend_hh(0, 50.0)
    assert e.deposits == pytest.approx(before + 50.0)
    e.repay_hh(np.array([50.0, 0.0, 0.0]))
    assert e.deposits == pytest.approx(before)
    assert e.check() == 0.0


def test_payments_across_the_banking_perimeter_move_reserves():
    e = Economy(2)
    e.dep[:] = 10.0
    e.bank_dep_liab = 20.0
    e.bank_res = e.cb_res_liab = 20.0
    e.pay("hh", "gov", "IRPF", src_vec=np.array([4.0, 1.0]))
    assert e.bank_res == pytest.approx(15.0)
    assert e.gov_acct == pytest.approx(5.0)
    assert e.check() == 0.0


def test_new_money_is_tracked_by_channel():
    for channel, recipient in [("dividend", "Hogares"), ("government", "Estado"), ("banks", "Bancos")]:
        m = Model(Regime("rule_2pct", channel, "fractional"), SMALL)
        for _ in range(12):
            m.step()
        assert m.new_money > 0
        assert m.new_money_to[recipient] > 0


def test_cbdc_respects_holding_limit_and_programmable_money_expires():
    p = Params(households=300, months=36, burn_in=12)
    m = Model(Regime("rule_2pct", "dividend", "fractional", "cbdc"), p)
    for _ in range(p.months):
        m.step()
        limit = p.cbdc_limit
        assert ((m.e.cbdc - m.stim) <= limit * 1.0001 + 1e-6).all()
    assert m.e.cbdc.sum() > 0
    assert m.last_flows.get(("hh", "cb", "Caducidad del dinero programable"), 0) > 0


def test_demurrage_is_paid_to_the_state():
    m = Model(Regime(money="demurrage"), SMALL)
    for _ in range(12):
        m.step()
    assert m.demurrage_paid > 0


def test_privacy_changes_tax_evasion():
    gaps = {}
    for privacy in ("anonymous", "mixed", "traceable"):
        m = Model(Regime(privacy=privacy), SMALL)
        for _ in range(12):
            m.step()
        gaps[privacy] = np.mean(m.history["tax_gap"])
    assert gaps["anonymous"] > gaps["mixed"] > gaps["traceable"]


# ------------------------------------------------------ laboratorio de políticas
from msl.policy import ELASTICITIES, LEVERS  # noqa: E402

POLICY = Params(households=300, months=48, burn_in=12, shock_month=12)


def _extremes():
    cases = []
    for key, spec in LEVERS.items():
        values = spec.get("choices") or [spec["min"], spec["max"]]
        for v in (min(values), max(values)):
            levers = {key: v}
            if spec.get("sub"):                       # p. ej. el umbral solo importa con el impuesto activo
                levers[spec["sub"]] = LEVERS[spec["sub"]]["max"]
            if spec.get("elasticity"):
                for end in ("lo", "hi"):
                    cases.append(pytest.param({**levers, spec["elasticity"]: ELASTICITIES[spec["elasticity"]][end]},
                                              id=f"{key}={v}+{spec['elasticity']}={end}"))
            else:
                cases.append(pytest.param(levers, id=f"{key}={v}"))
    lo = {k: (min(s["choices"]) if s.get("choices") else s["min"]) for k, s in LEVERS.items()}
    hi = {k: (max(s["choices"]) if s.get("choices") else s["max"]) for k, s in LEVERS.items()}
    cases += [pytest.param(lo, id="all-min"), pytest.param(hi, id="all-max"),
              pytest.param({**hi, "rent_cap": 0.0}, id="all-max+rent-freeze")]
    return cases


@pytest.mark.parametrize("levers", _extremes())
def test_every_policy_lever_at_its_extremes_is_stock_flow_consistent(levers):
    for p in (POLICY, replace(POLICY, shock="banking")):
        m = Model(Regime(), p, policy=levers, track=True, crn=True)
        for _ in range(p.months):
            m.step()
            assert m.e.check() < 1e-9, f"descuadre en el mes {m.t} ({p.shock})"
        res = m.result()
        rows = {r["key"]: r for r in res["balance_sheet"]["rows"]}
        # la vivienda pública es un activo real del Estado: la riqueza neta total sigue siendo igual a las viviendas
        assert rows["net"]["total"] == pytest.approx(rows["houses"]["total"], rel=1e-9)


def test_levers_at_todays_values_leave_the_model_exactly_unchanged():
    p = Params(households=400, months=36, burn_in=12, shock="pandemic", shock_month=6)
    today = Params().to_dict()
    defaults = {k: today[k] for k in list(LEVERS) + list(ELASTICITIES)}
    ref = Model(Regime(), p)
    for _ in range(p.months):
        ref.step()
    for m in (Model(Regime(), p, policy=defaults), Model(Regime(), p, track=True)):
        for _ in range(p.months):
            m.step()
        assert m.result()["series"] == ref.result()["series"]
