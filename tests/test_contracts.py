"""Los contratos inteligentes cumplen la regla monetaria que dicen implementar.

Se ejecutan en una cadena Ethereum local en memoria (eth-tester), avanzando el reloj
para simular meses y años. Requiere requirements-chain.txt; si falta, se omiten.
"""

import pytest

pytest.importorskip("web3")
pytest.importorskip("solcx")
pytest.importorskip("eth_tester")

from eth_tester.exceptions import TransactionFailed  # noqa: E402
from web3.exceptions import ContractLogicError  # noqa: E402

REVERT = (ContractLogicError, TransactionFailed)

from msl.chain import Chain  # noqa: E402

E18 = 10**18
MONTH = 30 * 24 * 3600


@pytest.fixture()
def chain():
    return Chain()


def test_halving_token_follows_the_emission_schedule(chain):
    a = chain.accounts
    tok = chain.deploy("HalvingToken", 1_000_000 * E18, 10_000 * E18, 4, MONTH, 0)
    chain.tx(tok.functions.setValidator(a[1], 3))
    chain.tx(tok.functions.setValidator(a[2], 1))
    chain.tx(tok.functions.mintEpochs())                 # periodo 0
    assert tok.functions.totalSupply().call() == 10_000 * E18
    assert tok.functions.balanceOf(a[1]).call() == 7_500 * E18   # 3/4 de la recompensa
    chain.advance(5 * MONTH)                              # periodos 1..5
    chain.tx(tok.functions.mintEpochs())
    expected = sum(tok.functions.rewardAt(e).call() for e in range(6))
    assert tok.functions.totalSupply().call() == expected
    assert tok.functions.rewardAt(4).call() == 5_000 * E18       # primer halving
    # nadie puede emitir dos veces el mismo periodo
    chain.tx(tok.functions.mintEpochs())
    assert tok.functions.totalSupply().call() == expected


def test_halving_token_never_exceeds_max_supply(chain):
    tok = chain.deploy("HalvingToken", 50_000 * E18, 10_000 * E18, 2, MONTH, 0)
    chain.tx(tok.functions.setValidator(chain.accounts[1], 1))
    chain.advance(40 * MONTH)
    chain.tx(tok.functions.mintEpochs())
    assert tok.functions.totalSupply().call() <= 50_000 * E18


def test_algorithmic_dividend_grows_supply_and_shares_it_equally(chain):
    a = chain.accounts
    tok = chain.deploy("AlgorithmicDividend", 320, MONTH, a[0], 1_000_000 * E18)
    for c in a[1:4]:
        chain.tx(tok.functions.registerCitizen(c))
    chain.advance(12 * MONTH)
    chain.tx(tok.functions.issue())
    supply = tok.functions.totalSupply().call()
    growth = supply / (1_000_000 * E18) - 1
    assert growth == pytest.approx((1 + 0.032 / 12) ** 12 - 1, rel=1e-6)
    owed = [tok.functions.owed(c).call() for c in a[1:4]]
    assert owed[0] == owed[1] == owed[2] > 0
    assert tok.functions.owed(a[5]).call() == 0                  # no ciudadano
    chain.tx(tok.functions.claim(), sender=a[1])
    assert tok.functions.balanceOf(a[1]).call() == owed[0]
    assert tok.functions.totalSupply().call() == supply           # reclamar no crea dinero
    # quien se registra tarde no cobra dividendos anteriores
    chain.tx(tok.functions.registerCitizen(a[6]))
    assert tok.functions.owed(a[6]).call() == 0


def test_demurrage_moves_idle_balances_to_the_treasury(chain):
    a = chain.accounts
    treasury = a[9]
    tok = chain.deploy("DemurrageToken", 5 * 10**15, MONTH, 100 * E18, treasury)   # 0,5 % al mes
    chain.tx(tok.functions.mint(a[1], 1_100 * E18))
    chain.advance(12 * MONTH)
    expected = 100 + 1_000 * 0.995**12
    assert tok.functions.balanceOf(a[1]).call() / E18 == pytest.approx(expected, rel=1e-9)
    chain.tx(tok.functions.transfer(a[2], 10 * E18), sender=a[1])   # liquida al moverse
    fee = tok.functions.balanceOf(treasury).call() / E18
    assert fee == pytest.approx(1_000 * (1 - 0.995**12), rel=1e-9)
    assert tok.functions.totalSupply().call() == 1_100 * E18       # la oferta se conserva


def test_cbdc_holding_limit_waterfall_stimulus_and_freeze(chain):
    a = chain.accounts
    cb, holder, bank, shop, other = a[0], a[1], a[2], a[3], a[4]
    tok = chain.deploy("ProgrammableCBDC", 3_000 * E18)
    chain.tx(tok.functions.setIntermediary(bank, True))
    chain.tx(tok.functions.setMerchant(shop, True))
    chain.tx(tok.functions.linkBank(bank), sender=holder)
    chain.tx(tok.functions.issue(holder, 5_000 * E18))
    assert tok.functions.balanceOf(holder).call() == 3_000 * E18   # límite
    assert tok.functions.balanceOf(bank).call() == 2_000 * E18     # cascada inversa

    chain.tx(tok.functions.issueStimulus([holder], 500 * E18, chain.now() + 2 * MONTH))
    with pytest.raises(REVERT):                          # fuera de comercios
        chain.tx(tok.functions.transfer(other, 3_200 * E18), sender=holder)
    chain.tx(tok.functions.transfer(shop, 3_200 * E18), sender=holder)  # en un comercio, sí
    assert tok.functions.stimulus(holder).call()[0] == 300 * E18
    chain.advance(3 * MONTH)
    chain.tx(tok.functions.expire(holder))
    assert tok.functions.stimulus(holder).call()[0] == 0
    assert tok.functions.balanceOf(holder).call() == 0               # el estímulo ha caducado

    chain.tx(tok.functions.freeze(bank, True, "orden judicial"))
    with pytest.raises(REVERT):
        chain.tx(tok.functions.transfer(holder, 1 * E18), sender=bank)


def _mortgage(chain, months=12, grace=3):
    a = chain.accounts
    lender, borrower = a[1], a[2]
    money = chain.deploy("LabStable")
    reg = chain.deploy("HouseRegistry")
    chain.tx(money.functions.mint(lender, 200_000 * E18))
    chain.tx(money.functions.mint(borrower, 20_000 * E18))
    chain.tx(reg.functions.register(borrower, "28079A0001"))
    m = chain.deploy("TokenizedMortgage", money.address, reg.address, 1, lender, borrower,
                     150_000 * E18, 300, months, grace)
    chain.tx(reg.functions.approve(m.address, 1), sender=borrower)
    chain.tx(money.functions.approve(m.address, 2**256 - 1), sender=lender)
    chain.tx(money.functions.approve(m.address, 2**256 - 1), sender=borrower)
    chain.tx(m.functions.fund(), sender=lender)
    return m, money, reg, lender, borrower


def test_mortgage_installment_matches_the_annuity_formula(chain):
    m, *_ = _mortgage(chain, months=300)
    r = 0.03 / 12
    expected = 150_000 * r / (1 - (1 + r) ** -300)
    assert m.functions.installment().call() / E18 == pytest.approx(expected, rel=1e-9)


def test_mortgage_repaid_releases_the_house(chain):
    m, money, reg, lender, borrower = _mortgage(chain)
    assert reg.functions.ownerOf(1).call() == m.address               # en garantía
    for _ in range(12):
        chain.advance(MONTH)
        chain.tx(m.functions.pay(), sender=borrower)
    assert m.functions.status().call() == 2                           # Repaid
    assert reg.functions.ownerOf(1).call() == borrower
    assert m.functions.balance().call() == 0


def test_mortgage_default_lets_the_lender_foreclose_only_after_grace(chain):
    m, money, reg, lender, borrower = _mortgage(chain)
    chain.advance(2 * MONTH + 60)
    with pytest.raises(REVERT):
        chain.tx(m.functions.foreclose(), sender=lender)
    chain.advance(MONTH)
    chain.tx(m.functions.foreclose(), sender=lender)
    assert reg.functions.ownerOf(1).call() == lender
    assert m.functions.status().call() == 3                           # Foreclosed
