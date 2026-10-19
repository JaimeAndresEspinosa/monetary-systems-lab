"""Ejecuta las reglas monetarias del simulador como contratos inteligentes en una cadena
Ethereum local durante 10 años y comprueba que dan exactamente lo mismo que el modelo.
También mide el gas de cada operación → data/contracts_demo.json

    pip install -r requirements-chain.txt
    python scripts/contracts_demo.py
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from msl import Params  # noqa: E402
from msl.chain import Chain  # noqa: E402

E18 = 10**18
MONTH = 30 * 24 * 3600
YEARS = 10


def main():
    p = Params()
    out: dict = {"years": YEARS, "gas": {}}
    gas = out["gas"]

    # -------------------------------------------- oferta fija tipo Bitcoin
    c = Chain()
    a = c.accounts
    genesis = 1_000_000 * E18
    reward = genesis * int(p.fixed_initial_issuance * 1e6) // (12 * 10**6)
    tok = c.deploy("HalvingToken", 21_000_000 * E18, reward, p.halving_months, MONTH, genesis)
    c.tx(tok.functions.setValidator(a[1], 3))
    c.tx(tok.functions.setValidator(a[2], 1))
    chain_path, model_path = [], []
    model = 1.0
    for t in range(12 * YEARS):
        r = c.tx(tok.functions.mintEpochs())
        if t == 1:
            gas["Emitir un periodo (oferta fija)"] = r.gasUsed
        chain_path.append(tok.functions.totalSupply().call() / genesis)
        # misma regla en el simulador: base0 · emisión/12 · 0,5^(t // halving)
        model += p.fixed_initial_issuance / 12 * 0.5 ** (t // p.halving_months)
        model_path.append(model)
        c.advance(MONTH)
    gas["Transferencia ERC-20"] = c.tx(tok.functions.transfer(a[3], E18), sender=a[1]).gasUsed
    out["halving"] = {"chain": chain_path, "model": [m - p.fixed_initial_issuance / 12 for m in model_path],
                      "validators": {"A (peso 3)": tok.functions.balanceOf(a[1]).call() / genesis,
                                     "B (peso 1)": tok.functions.balanceOf(a[2]).call() / genesis}}
    # el contrato emite en el periodo 0 al desplegarse: el modelo lo hace al final del primer mes
    out["halving"]["model"] = [1 + sum(p.fixed_initial_issuance / 12 * 0.5 ** (k // p.halving_months)
                                       for k in range(t + 1)) for t in range(12 * YEARS)]
    out["halving"]["max_abs_diff"] = max(abs(x - y) for x, y in zip(out["halving"]["chain"], out["halving"]["model"]))

    # -------------------------------------------- algoritmo 2 % + dividendo
    c = Chain()
    a = c.accounts
    rate_bps = int(round((p.inflation_target + p.productivity_growth) * 10_000))
    tok = c.deploy("AlgorithmicDividend", rate_bps, MONTH, a[0], genesis)
    citizens = a[1:5]
    for x in citizens:
        r = c.tx(tok.functions.registerCitizen(x))
    gas["Registrar un ciudadano"] = r.gasUsed
    chain_path, model_path, per_citizen = [], [], []
    for t in range(12 * YEARS):
        c.advance(MONTH)
        r = c.tx(tok.functions.issue())
        if t == 0:
            gas["Emitir el dividendo del mes"] = r.gasUsed
        chain_path.append(tok.functions.totalSupply().call() / genesis)
        model_path.append((1 + rate_bps / 10_000 / 12) ** (t + 1))
        per_citizen.append(tok.functions.owed(citizens[0]).call() / E18)
    gas["Cobrar el dividendo"] = c.tx(tok.functions.claim(), sender=citizens[0]).gasUsed
    out["dividend"] = {"rate_bps": rate_bps, "chain": chain_path, "model": model_path,
                       "per_citizen": per_citizen,
                       "max_abs_diff": max(abs(x - y) for x, y in zip(chain_path, model_path))}

    # -------------------------------------------- dinero que se oxida
    c = Chain()
    a = c.accounts
    treasury = a[9]
    rate = int(p.demurrage_rate * E18)
    tok = c.deploy("DemurrageToken", rate, MONTH, 1_000 * E18, treasury)
    c.tx(tok.functions.mint(a[1], 10_000 * E18))
    path = []
    for t in range(25):
        path.append(tok.functions.balanceOf(a[1]).call() / E18)
        c.advance(MONTH)
    gas["Transferencia con oxidación"] = c.tx(tok.functions.transfer(a[2], E18), sender=a[1]).gasUsed
    out["demurrage"] = {"rate": p.demurrage_rate, "exemption": 1_000, "start": 10_000, "path": path,
                        "treasury": tok.functions.balanceOf(treasury).call() / E18}

    # -------------------------------------------- euro digital programable
    c = Chain()
    a = c.accounts
    cbdc = c.deploy("ProgrammableCBDC", int(p.cbdc_limit) * E18)
    holder, bank, shop = a[1], a[2], a[3]
    c.tx(cbdc.functions.setIntermediary(bank, True))
    c.tx(cbdc.functions.setMerchant(shop, True))
    c.tx(cbdc.functions.linkBank(bank), sender=holder)
    c.tx(cbdc.functions.setIntermediary(a[4], True))      # el "empleador" es una empresa
    c.tx(cbdc.functions.issue(a[4], 10_000 * E18))
    r = c.tx(cbdc.functions.transfer(holder, 4_500 * E18), sender=a[4])   # nómina de 4.500 €
    gas["Pago con cascada al banco"] = r.gasUsed
    after_salary = {"holder": cbdc.functions.balanceOf(holder).call() / E18,
                    "bank": cbdc.functions.balanceOf(bank).call() / E18}
    r = c.tx(cbdc.functions.issueStimulus([holder], 300 * E18, c.now() + 6 * MONTH))
    gas["Emitir estímulo programable"] = r.gasUsed
    c.tx(cbdc.functions.transfer(shop, 3_100 * E18), sender=holder)
    stim_left = cbdc.functions.stimulus(holder).call()[0] / E18
    c.advance(7 * MONTH)
    gas["Hacer caducar el estímulo"] = c.tx(cbdc.functions.expire(holder)).gasUsed
    out["cbdc"] = {"limit": p.cbdc_limit, "salary": 4_500, "after_salary": after_salary,
                   "stimulus": 300, "spent_at_shop": 3_100, "stimulus_left_before_expiry": stim_left,
                   "after_expiry": cbdc.functions.balanceOf(holder).call() / E18}

    # -------------------------------------------- hipoteca tokenizada
    c = Chain()
    a = c.accounts
    lender, borrower = a[1], a[2]
    money = c.deploy("LabStable")
    reg = c.deploy("HouseRegistry")
    c.tx(money.functions.mint(lender, 200_000 * E18))
    c.tx(money.functions.mint(borrower, 30_000 * E18))
    gas["Inscribir una vivienda (NFT)"] = c.tx(reg.functions.register(borrower, "28079A0001")).gasUsed
    rate_bps = int(round((p.neutral_rate + p.inflation_target + p.mortgage_spread) * 10_000))
    m = c.deploy("TokenizedMortgage", money.address, reg.address, 1, lender, borrower,
                 120_000 * E18, rate_bps, p.mortgage_years * 12, 6)
    c.tx(reg.functions.approve(m.address, 1), sender=borrower)
    c.tx(money.functions.approve(m.address, 2**256 - 1), sender=lender)
    c.tx(money.functions.approve(m.address, 2**256 - 1), sender=borrower)
    gas["Conceder la hipoteca"] = c.tx(m.functions.fund(), sender=lender).gasUsed
    rows = []
    for k in range(12):
        c.advance(MONTH)
        r = c.tx(m.functions.pay(), sender=borrower)
        ev = m.events.Paid().process_receipt(r)[0]["args"]
        rows.append({"n": ev["number"], "interest": ev["interest"] / E18,
                     "principal": ev["principalPart"] / E18, "remaining": ev["remaining"] / E18})
    gas["Pagar una cuota"] = r.gasUsed
    out["mortgage"] = {"principal": 120_000, "rate_bps": rate_bps, "months": p.mortgage_years * 12,
                       "installment": m.functions.installment().call() / E18,
                       "house_owner_now": "contrato (garantía)" if reg.functions.ownerOf(1).call() == m.address else "prestatario",
                       "first_year": rows}

    path = ROOT / "data" / "contracts_demo.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"oferta fija: diferencia máx. contrato vs modelo {out['halving']['max_abs_diff']:.2e}")
    print(f"dividendo:   diferencia máx. contrato vs modelo {out['dividend']['max_abs_diff']:.2e}")
    print("gas:", gas)
    print(f"-> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
