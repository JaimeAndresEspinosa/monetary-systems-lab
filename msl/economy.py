"""Balances de todos los sectores y asientos de doble entrada.

Cada instrumento financiero tiene un tenedor (activo) y un emisor (pasivo), y
ambos lados se llevan por separado. `check()` comprueba en cada mes que, para
cada instrumento, la suma de activos es igual a la suma de pasivos: si un
asiento creara dinero "de la nada" sin su contrapartida, el error saltaría.

Perímetro bancario: hogares, empresas y bancos pagan con depósitos. Estado y
banco central pagan con dinero del banco central. Cuando un pago cruza ese
perímetro, se mueven también las reservas de los bancos en el banco central.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

SECTORS = ("hh", "firm", "bank", "gov", "cb")
SECTOR_LABELS = {
    "hh": "Hogares", "firm": "Empresas", "bank": "Bancos",
    "gov": "Estado", "cb": "Banco central",
}
INSIDE = {"hh", "firm", "bank"}

INSTRUMENTS = {
    "deposits": "Depósitos",
    "investment": "Cuentas de inversión",
    "loans": "Préstamos",
    "reserves": "Reservas",
    "treasury": "Cuenta del Tesoro",
    "bonds": "Bonos del Estado",
    "cb_loans": "Préstamos del banco central",
    "cbdc": "Euro digital (CBDC)",
}


class Economy:
    def __init__(self, n: int):
        self.n = n
        # Hogares (vectores)
        self.dep = np.zeros(n)
        self.inv = np.zeros(n)
        self.bonds = np.zeros(n)
        self.loan = np.zeros(n)
        self.cbdc = np.zeros(n)         # dinero digital del banco central en manos de hogares (sector agregado)
        self.firm_dep = 0.0
        self.firm_loan = 0.0
        # Bancos (sector agregado)
        self.bank_res = 0.0
        self.bank_loans = 0.0
        self.bank_bonds = 0.0
        self.bank_dep_liab = 0.0
        self.bank_inv_liab = 0.0
        self.bank_cb_loan = 0.0
        # Estado
        self.gov_acct = 0.0
        self.gov_bonds_liab = 0.0
        # Banco central
        self.cb_bonds = 0.0
        self.cb_loan_asset = 0.0
        self.cb_res_liab = 0.0
        self.cb_acct_liab = 0.0
        self.cb_cbdc_liab = 0.0
        self.cb_issued = 0.0  # dinero base creado sin activo de contrapartida (señoreaje)
        # Flujos del mes: (origen, destino, concepto) -> importe
        self.flows: dict[tuple[str, str, str], float] = defaultdict(float)

    # ------------------------------------------------------------ pagos
    def pay(self, src: str, dst: str, purpose: str, amount: float | None = None,
            src_vec: np.ndarray | None = None, dst_vec: np.ndarray | None = None) -> float:
        """Pago de `src` a `dst`. Para hogares se pasa el vector por hogar."""
        if src == "hh":
            amount = float(src_vec.sum())
        elif dst == "hh":
            amount = float(dst_vec.sum())
        if amount is None or amount == 0:
            return 0.0

        # Lado del pagador
        if src == "hh":
            self.dep -= src_vec
            self.bank_dep_liab -= amount
        elif src == "firm":
            self.firm_dep -= amount
            self.bank_dep_liab -= amount
        elif src == "gov":
            self.gov_acct -= amount
            self.cb_acct_liab -= amount
        elif src == "cb":
            self.cb_issued += amount
        # src == "bank": paga con sus recursos propios (baja su patrimonio)

        # Lado del cobrador
        if dst == "hh":
            self.dep += dst_vec
            self.bank_dep_liab += amount
        elif dst == "firm":
            self.firm_dep += amount
            self.bank_dep_liab += amount
        elif dst == "gov":
            self.gov_acct += amount
            self.cb_acct_liab += amount
        elif dst == "cb":
            self.cb_issued -= amount

        # Liquidación entre el perímetro bancario y el banco central
        if src in INSIDE and dst not in INSIDE:
            self.bank_res -= amount
            self.cb_res_liab -= amount
        elif src not in INSIDE and dst in INSIDE:
            self.bank_res += amount
            self.cb_res_liab += amount

        self.flows[(src, dst, purpose)] += amount
        return amount

    # -------------------------------------------------------- préstamos
    def lend_hh(self, i: int, x: float):
        """El banco concede un préstamo: crea a la vez el préstamo y el depósito."""
        self.loan[i] += x
        self.dep[i] += x
        self.bank_loans += x
        self.bank_dep_liab += x
        self.flows[("bank", "hh", "Nuevos préstamos")] += x

    def lend_firm(self, x: float):
        self.firm_loan += x
        self.firm_dep += x
        self.bank_loans += x
        self.bank_dep_liab += x
        self.flows[("bank", "firm", "Nuevos préstamos")] += x

    def repay_hh(self, vec: np.ndarray):
        """Amortización: se destruyen a la vez depósito y préstamo."""
        s = float(vec.sum())
        self.dep -= vec
        self.loan -= vec
        self.bank_loans -= s
        self.bank_dep_liab -= s
        self.flows[("hh", "bank", "Amortización de préstamos")] += s

    def repay_firm(self, x: float):
        self.firm_dep -= x
        self.firm_loan -= x
        self.bank_loans -= x
        self.bank_dep_liab -= x
        self.flows[("firm", "bank", "Amortización de préstamos")] += x

    def write_off_firm(self, x: float):
        """Impago de empresas: el banco pierde el préstamo, la empresa deja de deberlo."""
        self.firm_loan -= x
        self.bank_loans -= x

    def write_off_hh(self, i: int) -> float:
        """Impago: el banco da de baja el préstamo (pérdida para su patrimonio)."""
        x = float(self.loan[i])
        self.loan[i] = 0.0
        self.bank_loans -= x
        return x

    # ------------------------------------------------- cuentas de inversión
    def to_investment(self, vec: np.ndarray):
        s = float(vec.sum())
        self.dep -= vec
        self.bank_dep_liab -= s
        self.inv += vec
        self.bank_inv_liab += s
        self.flows[("hh", "bank", "Paso a cuentas de inversión")] += s

    def from_investment(self, vec: np.ndarray):
        s = float(vec.sum())
        self.inv -= vec
        self.bank_inv_liab -= s
        self.dep += vec
        self.bank_dep_liab += s
        self.flows[("bank", "hh", "Retirada de cuentas de inversión")] += s

    # ------------------------------------------------------------ bonos
    def bank_buys_bonds(self, x: float):
        self.bank_res -= x
        self.cb_res_liab -= x
        self.bank_bonds += x
        self.gov_acct += x
        self.cb_acct_liab += x
        self.gov_bonds_liab += x
        self.flows[("bank", "gov", "Compra de bonos nuevos")] += x

    def hh_buy_bonds(self, vec: np.ndarray):
        s = float(vec.sum())
        self.dep -= vec
        self.bank_dep_liab -= s
        self.bank_res -= s
        self.cb_res_liab -= s
        self.bonds += vec
        self.gov_acct += s
        self.cb_acct_liab += s
        self.gov_bonds_liab += s
        self.flows[("hh", "gov", "Compra de bonos nuevos")] += s

    def cb_buys_bank_bonds(self, x: float):
        self.bank_bonds -= x
        self.cb_bonds += x
        self.bank_res += x
        self.cb_res_liab += x
        self.flows[("cb", "bank", "Compra de bonos (QE)")] += x

    def cb_buys_hh_bonds(self, vec: np.ndarray):
        s = float(vec.sum())
        self.bonds -= vec
        self.cb_bonds += s
        self.dep += vec
        self.bank_dep_liab += s
        self.bank_res += s
        self.cb_res_liab += s
        self.flows[("cb", "hh", "Compra de bonos (QE)")] += s

    def cb_lends_bank(self, x: float):
        self.cb_loan_asset += x
        self.bank_cb_loan += x
        self.bank_res += x
        self.cb_res_liab += x
        self.flows[("cb", "bank", "Préstamo de liquidez")] += x

    def bank_repays_cb(self, x: float):
        self.cb_loan_asset -= x
        self.bank_cb_loan -= x
        self.bank_res -= x
        self.cb_res_liab -= x
        self.flows[("bank", "cb", "Devolución de liquidez")] += x

    # ------------------------------------------------------------ CBDC
    def to_cbdc(self, vec: np.ndarray):
        """El hogar pasa depósitos a euro digital: el banco pierde depósitos y reservas."""
        s = float(vec.sum())
        self.dep -= vec
        self.bank_dep_liab -= s
        self.bank_res -= s
        self.cb_res_liab -= s
        self.cbdc += vec
        self.cb_cbdc_liab += s
        self.flows[("hh", "cb", "Paso a euro digital")] += s

    def from_cbdc(self, vec: np.ndarray):
        s = float(vec.sum())
        self.cbdc -= vec
        self.cb_cbdc_liab -= s
        self.dep += vec
        self.bank_dep_liab += s
        self.bank_res += s
        self.cb_res_liab += s
        self.flows[("cb", "hh", "Vuelta a depósitos")] += s

    def cb_issue_cbdc(self, vec: np.ndarray):
        """Dinero nuevo directamente en euro digital (sin pasar por los bancos)."""
        s = float(vec.sum())
        self.cbdc += vec
        self.cb_cbdc_liab += s
        self.cb_issued += s
        self.flows[("cb", "hh", "Dinero nuevo (euro digital)")] += s

    def expire_cbdc(self, vec: np.ndarray):
        """Dinero programable que caduca sin gastarse: vuelve al banco central."""
        s = float(vec.sum())
        self.cbdc -= vec
        self.cb_cbdc_liab -= s
        self.cb_issued -= s
        self.flows[("hh", "cb", "Caducidad del dinero programable")] += s

    def hh_buy_bank_bonds(self, vec: np.ndarray):
        """Mercado secundario: los hogares compran a los bancos bonos ya emitidos."""
        s = float(vec.sum())
        self.dep -= vec
        self.bank_dep_liab -= s
        self.bank_bonds -= s
        self.bonds += vec
        self.flows[("hh", "bank", "Compra de bonos a los bancos")] += s

    # ------------------------------------------------------- agregados
    @property
    def deposits(self) -> float:
        return float(self.dep.sum()) + self.firm_dep

    def bank_equity(self, real_assets: float = 0.0) -> float:
        return (self.bank_res + self.bank_loans + self.bank_bonds + real_assets
                - self.bank_dep_liab - self.bank_inv_liab - self.bank_cb_loan)

    def instruments(self) -> dict[str, dict[str, float]]:
        """Posición de cada sector en cada instrumento (+ activo, − pasivo)."""
        return {
            "deposits": {"hh": float(self.dep.sum()), "firm": self.firm_dep,
                         "bank": -self.bank_dep_liab},
            "investment": {"hh": float(self.inv.sum()), "bank": -self.bank_inv_liab},
            "loans": {"hh": -float(self.loan.sum()), "firm": -self.firm_loan,
                      "bank": self.bank_loans},
            "reserves": {"bank": self.bank_res, "cb": -self.cb_res_liab},
            "treasury": {"gov": self.gov_acct, "cb": -self.cb_acct_liab},
            "bonds": {"hh": float(self.bonds.sum()), "bank": self.bank_bonds,
                      "cb": self.cb_bonds, "gov": -self.gov_bonds_liab},
            "cb_loans": {"bank": -self.bank_cb_loan, "cb": self.cb_loan_asset},
            "cbdc": {"hh": float(self.cbdc.sum()), "cb": -self.cb_cbdc_liab},
        }

    def check(self) -> float:
        """Error máximo entre activos y pasivos de un mismo instrumento,
        relativo al tamaño de la economía. Debe ser ~0 (precisión numérica)."""
        scale = max(1.0, self.bank_dep_liab + self.gov_bonds_liab)
        worst = 0.0
        for positions in self.instruments().values():
            worst = max(worst, abs(sum(positions.values())))
        return worst / scale

    def balance_sheet(self, house_value: dict[str, float], firm_value: float) -> dict:
        """Matriz de balances: filas = instrumentos, columnas = sectores."""
        rows = []
        for key, positions in self.instruments().items():
            row = {"key": key, "label": INSTRUMENTS[key]}
            for s in SECTORS:
                row[s] = positions.get(s, 0.0)
            row["total"] = sum(positions.values())
            rows.append(row)
        houses = {"key": "houses", "label": "Viviendas (activo real)"}
        for s in SECTORS:
            houses[s] = house_value.get(s, 0.0)
        houses["total"] = sum(house_value.values())
        rows.append(houses)
        net = {"key": "net", "label": "Patrimonio neto"}
        for s in SECTORS:
            net[s] = sum(r[s] for r in rows)
        net["total"] = sum(net[s] for s in SECTORS)
        rows.append(net)
        return {"sectors": [{"key": s, "label": SECTOR_LABELS[s]} for s in SECTORS],
                "rows": rows}

    def take_flows(self) -> dict:
        out = dict(self.flows)
        self.flows = defaultdict(float)
        return out
