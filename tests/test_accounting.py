"""La contabilidad tiene que cuadrar siempre: en cualquier régimen, en cualquier mes."""

import numpy as np
import pytest

from msl import Params, Regime
from msl.economy import Economy
from msl.model import Model

SMALL = Params(households=300, months=36, burn_in=12)


@pytest.mark.parametrize("regime", Regime.all(), ids=lambda r: r.key)
def test_every_regime_is_stock_flow_consistent(regime):
    m = Model(regime, SMALL)
    for _ in range(SMALL.months):
        m.step()
        assert m.e.check() < 1e-9, f"descuadre en el mes {m.t}"


@pytest.mark.parametrize("regime", Regime.all(), ids=lambda r: r.key)
def test_balance_sheet_columns_and_rows_close(regime):
    m = Model(regime, SMALL)
    for _ in range(12):
        m.step()
    res = m.result()
    rows = {r["key"]: r for r in res["balance_sheet"]["rows"]}
    # cada instrumento financiero suma cero entre sectores (el activo de uno es el pasivo de otro)
    scale = m.e.bank_dep_liab
    for key in ("deposits", "investment", "loans", "reserves", "treasury", "bonds", "cb_loans"):
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
