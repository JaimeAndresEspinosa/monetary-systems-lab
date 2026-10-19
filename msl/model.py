"""Economía basada en agentes con contabilidad stock-flujo consistente.

Cada mes:
  1. Tipos de interés según el régimen.
  2. Emisión de dinero base (regla de emisión) y entrada por su canal.
  3. Empleo y salarios (las empresas contratan según la demanda esperada).
  4. Impuestos, pensiones, prestaciones y rentas del capital.
  5. Servicio de la deuda, impagos y alquileres.
  6. Consumo y gasto público.
  7. Mercado de vivienda: compras, hipotecas, construcción y precio.
  8. Financiación del Estado, liquidez y solvencia de los bancos.
  9. Precios, salarios y expectativas para el mes siguiente.
 10. Métricas y comprobación contable.
"""

from __future__ import annotations

import numpy as np

from .config import Params, Regime
from .economy import Economy
from .metrics import gini, top_share

LOLR = {"discretionary"}                 # prestamista de última instancia: crea reservas a demanda
ANCHORED = {"discretionary", "rule_2pct"}  # regímenes con objetivo de inflación creíble


def annuity(balance, rate_m, months):
    months = np.maximum(months, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        pay = np.where(rate_m > 1e-9,
                       balance * rate_m / (1 - (1 + rate_m) ** (-months)),
                       balance / months)
    return np.nan_to_num(pay)


class Model:
    def __init__(self, regime: Regime, params: Params | None = None):
        self.target = regime
        self.r = Regime()  # el arranque siempre se hace con el sistema actual
        self.p = params or Params()
        self.rng = np.random.default_rng(self.p.seed)
        self.e = Economy(self.p.households)
        self.t = 0
        self.recording = False
        self.history: dict[str, list[float]] = {}
        self.events: list[dict] = []
        self._init_state()
        for _ in range(self.p.burn_in):
            self.step()
        self._switch_regime()

    # =============================================================== inicio
    def _init_state(self):
        p, e, rng, n = self.p, self.e, self.rng, self.p.households

        self.age = rng.uniform(20, 85, n)
        z = rng.lognormal(0.0, 0.5, n)
        self.z = z / z.mean()
        lf = self.age < p.retirement_age
        self.employed = lf & (rng.random(n) > p.natural_unemployment)
        self.last_wage = self.z * p.wage0  # para prestaciones

        # Producción: P0 = 1 → productividad por unidad de trabajo efectivo
        self.P = 1.0
        self.w = p.wage0
        self.A = (1 + p.markup) * p.wage0
        self.pi_e = p.inflation_target
        self.mu = p.markup

        y_month = self.A * float((self.z * self.employed).sum())
        gdp = 12 * y_month
        self.y_expected = y_month
        self.y_potential = self.A * float((self.z * lf).sum()) * (1 - p.natural_unemployment)
        # capital en estado estacionario: inversión = depreciación + crecimiento
        self.K = p.investment_share * self.y_potential / ((p.depreciation + p.productivity_growth) / 12)

        # Riqueza inicial: muy concentrada (cola de Pareto), crece con la edad
        score = rng.lognormal(0.0, 1.3, n) * (1 + (self.age - 20) / 40) * np.sqrt(self.z)
        self.score = score
        rank = score.argsort().argsort() / (n - 1)

        # Vivienda
        self.Ph = p.house_price0
        own_score = rank + 0.3 * (self.age - 20) / 65 + rng.normal(0, 0.25, n)
        owners = own_score >= np.quantile(own_score, 1 - p.homeownership0)
        self.houses = owners.astype(int)
        landlords = rank >= 0.85
        extra = int(round(p.extra_houses0 * n))
        w_land = np.where(landlords, score, 0.0)
        self.houses += rng.multinomial(extra, w_land / w_land.sum())
        self.bank_houses = 0
        self.firm_houses = 0
        self.construction = 0.0
        self.rent0 = p.rent_yield * p.house_price0 / 12
        self.rent = self.rent0

        # Hipotecas vivas
        has_mortgage = owners & (self.age < 55) & (rng.random(n) < 0.55)
        frac = rng.uniform(0.2, 1.0, n) * np.clip((55 - self.age) / 35, 0, 1)
        e.loan = np.where(has_mortgage, p.ltv * p.house_price0 * frac, 0.0)
        self.months_left = np.where(has_mortgage,
                                    np.maximum(12, np.round(p.mortgage_years * 12 * frac)), 0)
        self.arrears = np.zeros(n, dtype=int)

        # Propiedad de empresas, bancos e infraestructura de minado
        w_eq = score ** 1.5
        self.shares = w_eq / w_eq.sum()
        miners = rank >= 0.95
        w_min = np.where(miners, score, 0.0)
        self.miner_shares = w_min / w_min.sum()

        # Balances iniciales coherentes
        e.firm_loan = 0.4 * gdp
        wage_bill = self.w * float((self.z * self.employed).sum())
        e.firm_dep = 2 * wage_bill
        bonds_total = p.debt_to_gdp0 * gdp
        bonds_hh = 0.15 * bonds_total
        w_b = np.where(rank >= 0.8, score, 0.0)
        e.bonds = bonds_hh * w_b / w_b.sum()
        e.cb_bonds = 0.30 * bonds_total
        e.bank_bonds = bonds_total - bonds_hh - e.cb_bonds
        e.gov_bonds_liab = bonds_total
        e.bank_loans = float(e.loan.sum()) + e.firm_loan

        # Depósitos tales que el capital bancario inicial sea el 10 % de los préstamos
        L, Bb = e.bank_loans, e.bank_bonds
        D = (0.9 * L + Bb) / 0.9
        hh_dep = D - e.firm_dep
        e.dep = hh_dep * score / score.sum()
        e.bank_dep_liab = D
        e.bank_res = 0.10 * D
        e.cb_res_liab = e.bank_res
        e.gov_acct = e.cb_bonds - e.cb_res_liab
        e.cb_acct_liab = e.gov_acct

        self.base0 = e.cb_res_liab
        self.gdp0 = gdp
        self.gdp_ref = gdp
        profit0 = (1 - p.investment_share) * y_month - wage_bill
        self.firm_profit = (1 - p.corporate_tax) * max(0.0, profit0)
        self.firm_profit_hist = [self.firm_profit] * 12
        self.bank_profit = 0.0
        self.income = self.z * p.wage0 * self.employed
        self.gov_cut = 1.0
        self.bailouts = 0.0
        self.foreclosures = 0
        self.new_money = 0.0
        self.new_money_to = {"Bancos": 0.0, "Estado": 0.0, "Hogares": 0.0}
        self.new_money_deciles = np.zeros(10)
        self.Ph_hist = [self.Ph] * 13
        self.P_hist = [self.P] * 13
        self.u = p.natural_unemployment
        self.i = p.neutral_rate + p.inflation_target
        self.money_k = self.e.deposits / gdp
        self.real_mort_lr = p.neutral_rate + p.mortgage_spread
        self.e.take_flows()

    def _switch_regime(self):
        """Fin del arranque: se aplican las reglas del régimen elegido y se
        toman las referencias con las que se normalizan todas las métricas."""
        e = self.e
        self.r = self.target
        if self.r.banking == "full_reserve":
            # Transición del Chicago Plan: el banco central presta a los bancos las
            # reservas necesarias para respaldar el 100 % de los depósitos
            gap = e.bank_dep_liab - e.bank_res
            if gap > 0:
                e.cb_lends_bank(gap)
        self.t = 0
        self.recording = True
        self.history = {}
        self.events = []
        self.foreclosures = 0
        self.bailouts = 0.0
        self.new_money = 0.0
        self.new_money_to = {k: 0.0 for k in self.new_money_to}
        self.new_money_deciles = np.zeros(10)
        self.base0 = e.cb_res_liab + e.cb_acct_liab
        self.gdp_ref = 12 * self.y_expected * self.P
        self.P_ref, self.w_ref, self.Ph_ref = self.P, self.w, self.Ph
        self.y_ref = self.y_expected
        self.fv_ref = self.firm_value() / self.P
        self.money_k = (e.deposits + float(e.inv.sum())) / self.gdp_ref
        nw = self.net_worth()
        self.initial_rank = nw.argsort().argsort() / (self.p.households - 1)
        self.wealth0_real = nw / self.P
        e.take_flows()

    # ============================================================ utilidades
    @property
    def labor_force(self):
        return self.age < self.p.retirement_age

    def firm_value(self) -> float:
        """Valor de mercado de las empresas: beneficio descontado al tipo de interés
        más una prima de riesgo (por eso la bolsa sube cuando bajan los tipos)."""
        profit_y = 12 * float(np.mean(self.firm_profit_hist[-12:]))
        discount = max(0.03, self.i + 0.04 - 0.015)
        return max(0.0, profit_y) / discount + self.e.firm_dep - self.e.firm_loan

    def inflation_anchor(self) -> float:
        """Inflación que la gente espera a largo plazo si se cree la regla:
        crecimiento del dinero menos crecimiento de la productividad."""
        p = self.p
        if self.r.issuance in ANCHORED:
            return p.inflation_target
        if self.r.issuance == "gold":
            return p.gold_growth - p.productivity_growth
        issuance = p.fixed_initial_issuance * 0.5 ** (self.t // p.halving_months)
        share = self.base0 / max(self.e.deposits + float(self.e.inv.sum()), 1)
        return issuance * share - p.productivity_growth

    def bank_value(self) -> float:
        return max(0.0, self.e.bank_equity(self.bank_houses * self.Ph))

    def net_worth(self) -> np.ndarray:
        e = self.e
        return (e.dep + e.inv + e.bonds - e.loan + self.houses * self.Ph
                + self.shares * (self.firm_value() + self.bank_value()))

    def lending_room(self) -> float:
        """Cuánto puede prestar hoy el sistema bancario."""
        e, p = self.e, self.p
        eq = e.bank_equity(self.bank_houses * self.Ph)
        by_capital = eq / p.capital_ratio - e.bank_loans
        if self.r.banking == "full_reserve":
            by_liquidity = e.bank_res - e.bank_dep_liab
        elif self.r.issuance in LOLR:
            by_liquidity = np.inf
        else:
            # sin prestamista de última instancia el banco solo presta mientras
            # le sobren reservas: parte de lo prestado acaba saliendo del perímetro
            # (impuestos, compra de bonos) y tiene que poder cubrirlo
            by_liquidity = 5 * max(0.0, e.bank_res - p.reserve_ratio * e.bank_dep_liab)
        return max(0.0, min(by_capital, by_liquidity))

    def bank_spend_room(self) -> float:
        """Lo que el banco puede pagar (dividendos, intereses) sin romper su restricción."""
        if self.r.banking == "full_reserve":
            return max(0.0, self.e.bank_res - self.e.bank_dep_liab)
        return np.inf

    def record(self, key: str, value: float):
        self.history.setdefault(key, []).append(float(value))

    # ================================================================= mes
    def step(self):
        p, e, rng, n = self.p, self.e, self.rng, self.p.households
        t = self.t
        lf = self.labor_force

        # ---------------------------------------------- 1. tipos de interés
        pi_yoy = self.P / self.P_hist[-13] - 1
        if self.r.issuance == "discretionary":
            i = p.neutral_rate + pi_yoy + 0.5 * (pi_yoy - p.inflation_target) \
                - 0.5 * (self.u - p.natural_unemployment)
            i = max(0.0, i)
        else:
            # sin banco central que fije el precio del dinero, el tipo sale del mercado:
            # sube cuando la economía nominal crece más deprisa que la cantidad de dinero
            money = self.e.deposits + float(self.e.inv.sum())
            demand = self.money_k * 12 * self.y_expected * self.P
            i = p.neutral_rate + self.pi_e + p.money_rate_sens * np.log(max(demand, 1) / max(money, 1))
            i = float(np.clip(i, 0.0, 0.25))
        self.i = i
        r_mort = (i + p.mortgage_spread) / 12
        r_firm = (i + p.firm_spread) / 12
        r_bond = (i + p.bond_spread) / 12
        r_dep = max(0.0, i - 0.01) / 12 if self.r.banking == "fractional" else 0.0
        r_inv = max(0.0, i + p.mortgage_spread - 0.015) / 12

        # ------------------------------------------ 2. emisión de dinero base
        base = e.cb_res_liab + e.cb_acct_liab
        if self.r.issuance == "discretionary":
            g = 2.0 * (p.inflation_target - pi_yoy) + 1.0 * max(0.0, self.u - p.natural_unemployment - 0.02)
            issue = base * float(np.clip(g, 0.0, 0.30)) / 12
        elif self.r.issuance == "rule_2pct":
            issue = base * (p.inflation_target + p.productivity_growth) / 12
        elif self.r.issuance == "gold":
            issue = base * max(0.0, p.gold_growth + rng.normal(0, 0.01)) / 12
        else:
            issue = self.base0 * p.fixed_initial_issuance / 12 * 0.5 ** (t // p.halving_months)
        gov_extra = self._inject(issue)

        # ----------------------------------------------- 3. empleo y salarios
        demand_ratio = self.y_expected / max(self.y_potential / (1 - p.natural_unemployment), 1)
        target_n = int(round(min(0.98, demand_ratio) * lf.sum()))
        self._adjust_employment(target_n)
        wages = self.w * self.z * self.employed
        bill = float(wages.sum())
        if e.firm_dep < bill:
            need = bill - e.firm_dep
            room = self.lending_room()
            if room >= need:
                e.lend_firm(need)
            else:
                if room > 0:
                    e.lend_firm(room)
                # no puede pagar a todos: despide hasta poder pagar
                affordable = max(0.0, e.firm_dep) / max(bill, 1)
                keep = rng.random(n) < affordable
                self.employed &= keep
                wages = self.w * self.z * self.employed
                bill = float(wages.sum())
        e.pay("firm", "hh", "Salarios", dst_vec=wages)
        self.last_wage = np.where(self.employed, self.w * self.z, self.last_wage)

        # ---------------------------------- 4. transferencias y rentas del capital
        pensions = np.where(~lf, p.pension_ratio * self.w * self.z, 0.0)
        benefits = np.where(lf & ~self.employed, p.benefit_ratio * self.last_wage, 0.0)
        e.pay("gov", "hh", "Pensiones", dst_vec=pensions)
        e.pay("gov", "hh", "Prestaciones por desempleo", dst_vec=benefits)

        coupons_hh = e.bonds * r_bond
        e.pay("gov", "hh", "Intereses de la deuda", dst_vec=coupons_hh)
        e.pay("gov", "bank", "Intereses de la deuda", amount=e.bank_bonds * r_bond)
        cap_income = coupons_hh.copy()

        # intereses de depósitos y cuentas de inversión
        room = self.bank_spend_room()
        dep_int = np.maximum(e.dep, 0) * r_dep
        inv_int = e.inv * r_inv
        total = dep_int.sum() + inv_int.sum()
        scale = min(1.0, room / total) if total > 0 else 0.0
        e.pay("bank", "hh", "Intereses de depósitos", dst_vec=(dep_int + inv_int) * scale)
        if e.firm_dep > 0 and r_dep > 0:
            e.pay("bank", "firm", "Intereses de depósitos", amount=e.firm_dep * r_dep)
        cap_income += (dep_int + inv_int) * scale

        # dividendos de las empresas (beneficio del mes anterior)
        # reparten el 80 % del beneficio y la caja que exceda tres meses de nóminas
        div = 0.8 * max(0.0, self.firm_profit) + 0.1 * max(0.0, e.firm_dep - 3 * bill)
        div = min(div, max(0.0, e.firm_dep - bill))
        div_vec = self.shares * div
        e.pay("firm", "hh", "Dividendos", dst_vec=div_vec)
        cap_income += div_vec
        # dividendos de los bancos
        eq = e.bank_equity(self.bank_houses * self.Ph)
        # los bancos reparten el capital que les sobra por encima del 12 %
        excess_cap = eq - 1.5 * p.capital_ratio * e.bank_loans
        if excess_cap > 0:
            bdiv = min(0.1 * excess_cap + max(0.0, 0.8 * self.bank_profit), excess_cap,
                       self.bank_spend_room())
            bvec = self.shares * bdiv
            e.pay("bank", "hh", "Dividendos", dst_vec=bvec)
            cap_income += bvec

        # ------------------------------------- 5. deuda, impagos y alquileres
        bank_income = e.bank_bonds * r_bond
        has = e.loan > 1e-6
        pay_due = np.where(has, annuity(e.loan, r_mort, self.months_left), 0.0)
        interest = e.loan * r_mort
        can = has & (e.dep >= pay_due)
        int_paid = np.where(can, interest, 0.0)
        princ = np.where(can, np.minimum(pay_due - interest, e.loan), 0.0)
        e.pay("hh", "bank", "Intereses de hipotecas", src_vec=int_paid)
        e.repay_hh(princ)
        bank_income += float(int_paid.sum())
        self.months_left = np.where(can, np.maximum(self.months_left - 1, 0), self.months_left)
        self.arrears = np.where(has & ~can, self.arrears + 1, np.where(can, 0, self.arrears))
        losses = 0.0
        for idx in np.flatnonzero(self.arrears >= 6):
            # ejecución hipotecaria: el banco se queda la vivienda y da de baja el préstamo
            loss = e.write_off_hh(idx)
            if self.houses[idx] > 0:
                self.houses[idx] -= 1
                self.bank_houses += 1
                loss -= self.Ph
            losses += max(0.0, loss)
            self.arrears[idx] = 0
            self.months_left[idx] = 0
            self.foreclosures += 1
        firm_int = e.firm_loan * r_firm
        e.pay("firm", "bank", "Intereses de préstamos", amount=firm_int)
        bank_income += firm_int
        bank_cost = float((dep_int + inv_int).sum() * scale) + (e.firm_dep * r_dep if r_dep > 0 else 0)
        self.bank_profit = bank_income - bank_cost - losses

        # alquileres: los inquilinos pagan a los caseros
        renters = self.houses == 0
        landlord_w = np.maximum(self.houses - 1, 0).astype(float)
        shortage = renters.sum() / max(1.0, landlord_w.sum() + self.bank_houses)
        self.rent = self.rent0 * (self.w / p.wage0) * float(np.clip(shortage, 0.7, 1.6)) ** 0.5
        rent_vec = np.where(renters, np.minimum(self.rent, np.maximum(e.dep, 0)), 0.0)
        total_rent = rent_vec.sum()
        if landlord_w.sum() > 0 and total_rent > 0:
            to_vec = total_rent * landlord_w / landlord_w.sum()
            e.pay("hh", "hh", "Alquileres", src_vec=rent_vec, dst_vec=to_vec)
            cap_income += to_vec

        # impuesto sobre la renta (progresivo)
        gross = wages + pensions + benefits + cap_income
        # IRPF + cotizaciones sociales, con tipo medio progresivo
        avg_rate = p.income_tax_base + p.income_tax_prog * (1 - np.exp(-gross / (1.5 * self.w)))
        tax = np.minimum(avg_rate * gross, np.maximum(e.dep, 0))
        e.pay("hh", "gov", "IRPF y cotizaciones", src_vec=tax)
        self.income = gross

        # --------------------------------------------- 6. consumo y gasto público
        rank_inc = gross.argsort().argsort() / (n - 1)
        mpc = p.mpc_low - (p.mpc_low - p.mpc_high) * rank_inc
        # sustitución intertemporal: con tipos reales altos se ahorra más, con tipos
        # reales bajos (o inflación) se adelanta el consumo
        real_rate = i - self.pi_e
        mpc *= float(np.clip(1 - p.hoarding * (real_rate - p.neutral_rate), 0.7, 1.15))
        cons = mpc * (gross - tax) + p.wealth_mpc * np.maximum(e.dep, 0)
        cons = np.clip(cons, 0, np.maximum(e.dep, 0))
        e.pay("hh", "firm", "Consumo", src_vec=cons)
        G = p.gov_spending_share * self.y_potential * self.P * self.gov_cut + gov_extra
        e.pay("gov", "firm", "Compras públicas", amount=G)

        # --------------------------------------------------- 7. vivienda
        built, house_sales = self._housing_market(r_mort, lf)

        # IVA: parte de lo que pagan los consumidores va al Estado
        vat = float(cons.sum()) * p.vat / (1 + p.vat)
        e.pay("firm", "gov", "IVA", amount=vat)

        # beneficio y su impuesto
        revenue = float(cons.sum()) - vat + G + house_sales
        profit = revenue - bill - firm_int
        ctax = p.corporate_tax * max(0.0, profit)
        ctax = min(ctax, max(0.0, e.firm_dep))
        e.pay("firm", "gov", "Impuesto de sociedades", amount=ctax)
        self.firm_profit = profit - ctax
        self.firm_profit_hist.append(self.firm_profit)
        # las empresas mantienen una deuda proporcional a su capital: piden prestado
        # para invertir si están por debajo del objetivo y amortizan si están por encima
        target_debt = p.firm_leverage * self.K * self.P
        if e.firm_loan < target_debt:
            x = min(0.05 * (target_debt - e.firm_loan), self.lending_room())
            if x > 0:
                e.lend_firm(x)
        elif e.firm_dep > 2 * bill:
            e.repay_firm(min(0.05 * (e.firm_loan - target_debt), e.firm_dep - 2 * bill))

        # ------------------------------------------- 8. Estado y bancos
        self._finance_government(G)
        self._bank_liquidity_and_solvency()
        if self.r.banking == "full_reserve":
            self._investment_accounts()

        # ----------------------------------- 9. precios, salarios, expectativas
        # inversión empresarial: se produce dentro del sector empresas (sin pago
        # entre sectores) pero genera empleo y se financia con caja o crédito
        real_rate = i - self.pi_e
        inv_factor = float(np.clip(1 - p.investment_rate_sens * (real_rate - p.neutral_rate), 0.5, 1.5))
        investment = p.investment_share * self.y_potential * inv_factor
        self.K = self.K * (1 - p.depreciation / 12) + investment
        # la obra de una vivienda se reparte a lo largo de ~1 año de producción
        self.construction = 0.92 * self.construction + 0.08 * built * 0.75 * p.house_price0
        real_sales = (float(cons.sum()) - vat + G) / self.P + self.construction + investment
        self.y_expected = 0.85 * self.y_expected + 0.15 * real_sales
        self.u = 1 - (self.employed & lf).sum() / max(1, lf.sum())
        gap = float(np.clip(real_sales / max(self.y_potential, 1) - 1, -0.3, 0.3))
        self.mu = 0.9 * self.mu + 0.1 * p.markup * (1 + 1.5 * gap)
        wage_growth = self.pi_e + p.productivity_growth + p.phillips * (p.natural_unemployment - self.u)
        wage_growth = max(p.wage_floor, wage_growth)
        self.w *= 1 + wage_growth / 12
        self.A *= 1 + p.productivity_growth / 12
        self.P = (1 + self.mu) * self.w / self.A
        self.P_hist.append(self.P)
        pi_yoy = self.P / self.P_hist[-13] - 1
        # expectativas: adaptativas, pero ancladas a la inflación que implica la regla
        adaptive = 0.92 * self.pi_e + 0.08 * pi_yoy
        w = p.credibility
        self.pi_e = w * self.inflation_anchor() + (1 - w) * adaptive
        self.y_potential = self.A * float((self.z * lf).sum()) * (1 - p.natural_unemployment)

        self._demography()
        if self.recording:
            self._record(pi_yoy, real_sales, issue)
        else:
            e.take_flows()
        self.t += 1

    # ======================================================= subprocesos
    def _inject(self, x: float) -> float:
        """Mete en la economía el dinero base nuevo por el canal elegido.
        Devuelve el gasto público adicional financiado con dinero nuevo."""
        if x <= 0:
            return 0.0
        e, ch = self.e, self.r.channel
        self.new_money += x
        if ch == "banks":
            from_bank = min(x, e.bank_bonds)
            if from_bank > 0:
                e.cb_buys_bank_bonds(from_bank)
            rest = x - from_bank
            if rest > 0 and e.bonds.sum() > 0:
                take = min(rest, float(e.bonds.sum()))
                vec = e.bonds * (take / e.bonds.sum())
                e.cb_buys_hh_bonds(vec)
                self._credit_deciles(vec)
                rest -= take
            if rest > 0:
                e.cb_lends_bank(rest)
            self.new_money_to["Bancos"] += from_bank + max(rest, 0.0)
            return 0.0
        if ch == "government":
            e.pay("cb", "gov", "Dinero nuevo", amount=x)
            self.new_money_to["Estado"] += x
            return x
        vec = (np.full(self.p.households, x / self.p.households) if ch == "dividend"
               else self.miner_shares * x)
        e.pay("cb", "hh", "Dinero nuevo", dst_vec=vec)
        self._credit_deciles(vec)
        return 0.0

    def _credit_deciles(self, vec: np.ndarray):
        nw = self.net_worth()
        dec = np.minimum((nw.argsort().argsort() * 10) // self.p.households, 9)
        self.new_money_deciles += np.bincount(dec, weights=vec, minlength=10)
        self.new_money_to["Hogares"] += float(vec.sum())

    def _adjust_employment(self, target_n: int):
        lf = self.labor_force
        self.employed &= lf
        cur = int(self.employed.sum())
        max_move = max(1, int(0.04 * lf.sum()))
        if target_n > cur:
            pool = np.flatnonzero(lf & ~self.employed)
            k = min(len(pool), target_n - cur, max_move)
            if k > 0:
                self.employed[self.rng.choice(pool, k, replace=False)] = True
        elif target_n < cur:
            pool = np.flatnonzero(self.employed)
            k = min(len(pool), cur - target_n, max_move)
            if k > 0:
                self.employed[self.rng.choice(pool, k, replace=False)] = False

    def _housing_market(self, r_mort: float, lf: np.ndarray) -> tuple[int, float]:
        p, e, rng, n = self.p, self.e, self.rng, self.p.households
        Ph = self.Ph
        growth_exp = self.Ph_hist[-1] / self.Ph_hist[-13] - 1

        # construcción: más cuanto mayor es el margen sobre el coste
        cost = 0.75 * p.house_price0 * self.P
        margin = Ph / cost - 1
        built = int(rng.poisson(max(0.0, n * p.construction_rate * margin)))
        self.firm_houses += built

        # compradores
        renters = (self.houses == 0) & lf & self.employed & (self.age < 50)
        first = renters & (rng.random(n) < 0.03)
        exp_return = 12 * self.rent / Ph + growth_exp
        invest_p = 0.015 if exp_return > 12 * r_mort + 0.01 else 0.003
        investors = (self.houses >= 1) & (e.dep > 0.5 * Ph) & (rng.random(n) < invest_p)
        buyers = np.flatnonzero(first | investors)
        rng.shuffle(buyers)

        # vendedores
        extra = np.maximum(self.houses - 1, 0)
        sell_p = 0.006 if exp_return > 12 * r_mort else 0.012
        old = self.age > 80
        sellers = list(np.flatnonzero((extra > 0) & ((rng.random(n) < sell_p) | old)))
        rng.shuffle(sellers)
        listings = len(sellers) + self.bank_houses + self.firm_houses

        income_m = np.maximum(self.income, self.w * self.z * self.employed)
        deals, sales_firm, demand = 0, 0.0, 0
        for b in buyers:
            own = min(0.8 * max(e.dep[b], 0.0), Ph)
            loan = Ph - own
            if loan > p.ltv * Ph:
                continue
            if loan > 0:
                pay = float(annuity(np.array([loan]), r_mort, np.array([p.mortgage_years * 12]))[0])
                if pay > p.dsti * income_m[b] or self.lending_room() < loan:
                    continue
            demand += 1
            if deals >= listings:
                continue
            if loan > 0:
                e.lend_hh(b, loan)
                self.months_left[b] = p.mortgage_years * 12
            vec = np.zeros(n)
            vec[b] = Ph
            if self.firm_houses > 0:
                e.pay("hh", "firm", "Compra de vivienda nueva", src_vec=vec)
                self.firm_houses -= 1
                sales_firm += Ph
            elif self.bank_houses > 0:
                e.pay("hh", "bank", "Compra de vivienda embargada", src_vec=vec)
                self.bank_houses -= 1
            else:
                s = sellers.pop()
                to = np.zeros(n)
                to[s] = Ph
                e.pay("hh", "hh", "Compraventa de vivienda", src_vec=vec, dst_vec=to)
                self.houses[s] -= 1
                # el vendedor cancela su hipoteca si la tenía y le sobra liquidez
                if e.loan[s] > 0 and self.houses[s] == 0:
                    e.repay_hh(np.where(np.arange(n) == s, min(e.loan[s], e.dep[s]), 0.0))
            self.houses[b] += 1
            deals += 1

        # precio: exceso de demanda + ancla en el valor fundamental (alquiler / coste de uso)
        excess = (demand - listings) / max(listings, 5)
        # coste de uso: tipo hipotecario real + mantenimiento − revalorización esperada
        # (los compradores usan el tipo real que esperan a largo plazo, no el de este mes)
        self.real_mort_lr = 0.97 * self.real_mort_lr + 0.03 * (12 * r_mort - self.pi_e)
        user_cost = max(0.025, self.real_mort_lr + 0.02 - 0.2 * float(np.clip(growth_exp, -0.02, 0.03)))
        fundamental = 12 * self.rent / user_cost
        dlog = 0.003 * float(np.clip(excess, -3, 3)) + 0.02 * np.log(fundamental / Ph) + 0.05 * growth_exp / 12
        self.Ph = Ph * float(np.exp(np.clip(dlog, -0.05, 0.05)))
        self.Ph_hist.append(self.Ph)
        self.deals = deals
        return built, sales_firm

    def _finance_government(self, G: float):
        e, p = self.e, self.p
        buffer = 0.5 * G
        need = buffer - e.gov_acct
        self.gov_cut = min(1.0, self.gov_cut + 0.02)
        if need <= 0:
            return
        # 1) bancos con liquidez disponible
        if self.r.banking == "full_reserve":
            bank_cap = max(0.0, e.bank_res - e.bank_dep_liab)
        else:
            bank_cap = max(0.0, e.bank_res - p.reserve_ratio * e.bank_dep_liab)
            if self.r.issuance in LOLR:
                bank_cap = need  # el banco central le presta reservas si le faltan
        x = min(need, bank_cap)
        if x > 0:
            if e.bank_res - x < p.reserve_ratio * e.bank_dep_liab and self.r.issuance in LOLR:
                e.cb_lends_bank(x)
            e.bank_buys_bonds(x)
            need -= x
        # 2) hogares con ahorro líquido
        if need > 0:
            spare = np.maximum(e.dep - 6 * np.maximum(self.income, 1), 0)
            if spare.sum() > 0:
                take = min(need, 0.5 * float(spare.sum()))
                e.hh_buy_bonds(spare * (take / spare.sum()))
                need -= take
        # 3) nadie compra: recorte de gasto el mes siguiente
        if need > 1e-6:
            self.gov_cut = max(0.6, self.gov_cut - 0.1)
            self.events.append({"t": self.t, "type": "austerity",
                                "text": "El Estado no logra colocar su deuda y recorta gasto"})

    def _bank_liquidity_and_solvency(self):
        e, p = self.e, self.p
        if self.r.banking == "fractional":
            short = p.reserve_ratio * e.bank_dep_liab - e.bank_res
            if short > 0 and self.r.issuance in LOLR:
                e.cb_lends_bank(short)
            elif short < 0 and e.bank_cb_loan > 0:
                e.bank_repays_cb(min(e.bank_cb_loan, -short * 0.5))
        eq = e.bank_equity(self.bank_houses * self.Ph)
        if eq < 0.02 * e.bank_loans:
            # rescate público para devolver el capital al 8 %
            x = p.capital_ratio * e.bank_loans - eq
            e.pay("gov", "bank", "Rescate bancario", amount=x)
            self.bailouts += x
            self.events.append({"t": self.t, "type": "bailout",
                                "text": f"Rescate bancario de {x / self.gdp_ref * 100:.1f} % del PIB"})

    def _investment_accounts(self):
        """Reserva 100 %: los hogares con ahorro de sobra lo pasan a cuentas de inversión,
        que es lo único que los bancos pueden prestar."""
        e = self.e
        cushion = 6 * np.maximum(self.income, 1)
        spare = np.maximum(e.dep - cushion, 0)
        e.to_investment(0.03 * spare)
        lacking = np.maximum(cushion * 0.5 - e.dep, 0)
        want = np.minimum(lacking, e.inv)
        room = max(0.0, e.bank_res - e.bank_dep_liab)
        if want.sum() > 0 and room > 0:
            e.from_investment(want * min(1.0, room / want.sum()))

    def _demography(self):
        self.age += 1 / 12
        dead = np.flatnonzero(self.age >= 85)
        if len(dead):
            # herencia dinástica: el patrimonio pasa a un heredero de 20 años
            self.age[dead] = 20.0
            z = self.rng.lognormal(0.0, 0.5, len(dead))
            self.z[dead] = z / np.exp(0.125)
            self.employed[dead] = False
            self.last_wage[dead] = self.w * self.z[dead]

    def _record(self, pi_yoy: float, real_sales: float, issue: float):
        e, p = self.e, self.p
        nw = self.net_worth()
        gdp_y = 12 * real_sales * self.P
        ref = self.gdp_ref
        lf = self.labor_force
        self.record("inflation", pi_yoy)
        self.record("unemployment", self.u)
        self.record("price_level", self.P / self.P_ref)
        self.record("real_wage", (self.w / self.P) / (self.w_ref / self.P_ref))
        self.record("real_gdp", real_sales / self.y_ref)
        self.record("gini_wealth", gini(np.maximum(nw, 0)))
        self.record("gini_income", gini(self.income))
        self.record("top10_wealth", top_share(np.maximum(nw, 0), 0.10))
        self.record("bottom50_wealth", 1 - top_share(np.maximum(nw, 0), 0.50))
        self.record("house_price_real", (self.Ph / self.P) / (self.Ph_ref / self.P_ref))
        self.record("price_to_income", self.Ph / (12 * self.w))
        self.record("homeownership", float((self.houses > 0).mean()))
        workers = lf & self.employed
        median_wage = float(np.median(self.income[workers])) if workers.any() else self.w
        self.record("rent_burden", self.rent / max(1.0, median_wage))
        self.record("broad_money", (e.deposits + float(e.inv.sum())) / ref)
        self.record("base_money", (e.cb_res_liab + e.cb_acct_liab) / ref)
        self.record("credit_gdp", e.bank_loans / max(gdp_y, 1))
        self.record("debt_gdp", e.gov_bonds_liab / max(gdp_y, 1))
        self.record("policy_rate", self.i)
        self.record("mortgage_rate", self.i + p.mortgage_spread)
        self.record("foreclosures", self.foreclosures / p.households)
        self.record("bank_capital", e.bank_equity(self.bank_houses * self.Ph) / max(e.bank_loans, 1))
        self.record("stock_index", (self.firm_value() / self.P) / max(1.0, self.fv_ref))
        self.record("new_money", issue * 12 / max(gdp_y, 1))
        self.record("bailouts", self.bailouts / ref)
        self.record("sfc_error", e.check())
        self.last_flows = e.take_flows()

    # =========================================================== resultados
    def result(self) -> dict:
        nw_real = self.net_worth() / self.P
        dec = np.minimum((self.initial_rank * 10).astype(int), 9)
        # cuota de la riqueza total de cada decil (los mismos hogares al inicio y al final)
        w0 = np.bincount(dec, weights=self.wealth0_real, minlength=10)
        w1 = np.bincount(dec, weights=nw_real, minlength=10)
        share0, share1 = w0 / w0.sum(), w1 / w1.sum()
        hist = {k: v for k, v in self.history.items() if not k.startswith("_")}
        house_value = {"hh": float(self.houses.sum()) * self.Ph,
                       "bank": self.bank_houses * self.Ph,
                       "firm": self.firm_houses * self.Ph}
        bs = self.e.balance_sheet(house_value, self.firm_value())
        flows = [{"from": k[0], "to": k[1], "purpose": k[2], "amount": v}
                 for k, v in sorted(self.last_flows.items(), key=lambda kv: -kv[1])]
        return {
            "series": hist,
            "wealth_share_start": share0.tolist(),
            "wealth_share_end": share1.tolist(),
            "new_money_deciles": (self.new_money_deciles / max(self.new_money, 1)).tolist(),
            "new_money_to": {k: v / max(self.new_money, 1) for k, v in self.new_money_to.items()},
            "balance_sheet": bs,
            "flows": flows,
            "events": self.events[:50],
            "sfc_max_error": float(max(self.history.get("sfc_error", [0.0]))),
        }


def run(regime: Regime, params: Params | None = None) -> dict:
    m = Model(regime, params)
    for _ in range(m.p.months):
        m.step()
    return m.result()
