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

from dataclasses import replace

import numpy as np

from .config import SHOCKS, SPAIN_WAGE, Params, Regime
from .economy import Economy
from .metrics import gini, top_share

LOLR = {"discretionary"}                 # prestamista de última instancia: crea reservas a demanda
ANCHORED = {"discretionary", "rule_2pct"}  # regímenes con objetivo de inflación creíble
TODAY = Params()                         # valores de partida de las palancas de política


def annuity(balance, rate_m, months):
    months = np.maximum(months, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        pay = np.where(rate_m > 1e-9,
                       balance * rate_m / (1 - (1 + rate_m) ** (-months)),
                       balance / months)
    return np.nan_to_num(pay)


class Model:
    def __init__(self, regime: Regime, params: Params | None = None, policy: dict | None = None,
                 track: bool = False, crn: bool = False):
        self.target = regime
        self.r = Regime()  # el arranque siempre se hace con el sistema actual
        self.p = params or Params()
        # medidas del laboratorio de políticas: se aplican al terminar el arranque, de modo que
        # con la misma semilla los hogares de partida son idénticos con y sin la medida
        self.policy = dict(policy or {})
        unknown = set(self.policy) - set(Params.__dataclass_fields__)
        if unknown:
            raise ValueError(f"Palancas desconocidas: {sorted(unknown)}")
        self.track = track
        # números aleatorios comunes: tras el arranque, cada proceso aleatorio usa su propia
        # secuencia, así que con y sin la medida la economía recibe los mismos shocks
        self.crn = crn
        self.rng = np.random.default_rng(self.p.seed)
        self.rs = dict.fromkeys(("spirits", "build", "hh", "jobs", "misc", "demo"), self.rng)
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
        score = rng.lognormal(0.0, p.wealth_sigma, n) * (1 + (self.age - 20) / 40) * np.sqrt(self.z)
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
        has_mortgage = owners & (self.age < 55) & (rng.random(n) < p.mortgage_prob)
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
        self.mu_hist = [self.mu] * 13
        self.u = p.natural_unemployment
        self.i = p.neutral_rate + p.inflation_target
        self.money_k = self.e.deposits / gdp
        # Fase 2: dinero programable, regla fiscal, crisis y evasión
        self.stim = np.zeros(n)            # euro digital programable pendiente de gastar
        self.rev_ema = None                # recaudación media (12 meses)
        self.transfer_ema = None           # pensiones, prestaciones e intereses (12 meses)
        self.credit_factor = 1.0
        self.animal = 0.0
        self.tax_evaded = 0.0
        self.demurrage_paid = 0.0
        self.real_mort_lr = p.neutral_rate + p.mortgage_spread
        # Laboratorio de políticas: con los valores por defecto nada de esto cambia el modelo
        # (y usa su propio generador aleatorio, para no alterar la secuencia del principal)
        self.prng = np.random.default_rng(p.seed + 104_729)
        self.zw = self.z                   # productividad que se paga (con el SMI)
        self.smi_cost = 1.0                # coste laboral medio por el SMI (se traslada a precios)
        self.job_u = None
        self.almp_level = 0.0
        self.pub_acc = 0.0
        self.pub_pipeline: list[tuple[int, int]] = []
        self.gov_houses = 0
        self.public_tenant = np.zeros(n, dtype=bool)
        self.guaranteed = np.zeros(n, dtype=bool)
        self.rent_i = None
        self.rent_eff = self.rent
        self.withdrawn = 0.0               # parte de los pisos de alquiler retirados por el tope
        self.was_renter = None
        self.extra_Kg = 0.0
        self.A_boost = 1.0
        self.G_real = 0.0
        self.inc12 = self.income.copy()    # renta bruta media de los últimos 12 meses
        self.e.take_flows()

    def _switch_regime(self):
        """Fin del arranque: se aplican las reglas del régimen elegido y se
        toman las referencias con las que se normalizan todas las métricas."""
        e = self.e
        self.r = self.target
        if self.policy:
            self.p = replace(self.p, **self.policy)
        if self.crn:
            streams = np.random.SeedSequence([self.p.seed, 2026]).spawn(len(self.rs))
            self.rs = {k: np.random.default_rng(s) for k, s in zip(self.rs, streams)}
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
        self.money_k = self.money_stock() / self.gdp_ref
        nw = self.net_worth()
        self.initial_rank = nw.argsort().argsort() / (self.p.households - 1)
        self.wealth0_real = nw / self.P
        self._start_policies(nw)
        e.take_flows()

    # ============================================================ utilidades
    @property
    def labor_force(self):
        return self.age < self.p.retirement_age

    def nairu(self) -> float:
        """Paro estructural: el natural, corregido por la generosidad de las prestaciones
        y por las políticas activas de empleo."""
        p = self.p
        u = p.natural_unemployment
        if p.benefit_ratio == TODAY.benefit_ratio and not self.almp_level:
            return u
        if p.benefit_ratio > 0:
            u *= (p.benefit_ratio / TODAY.benefit_ratio) ** p.benefit_elasticity
        u -= p.almp_effectiveness * self.almp_level
        return float(np.clip(u, 0.02, 0.40))

    def to_today_eur(self, x):
        """Euros nominales del modelo → euros de hoy (sin inflación, al salario medio de España)."""
        return x * (self.P_ref / self.P) * (SPAIN_WAGE / self.w_ref)

    def firm_value(self) -> float:
        """Valor de mercado de las empresas: beneficio descontado al tipo de interés
        más una prima de riesgo (por eso la bolsa sube cuando bajan los tipos)."""
        profit_y = 12 * float(np.mean(self.firm_profit_hist[-12:]))
        discount = max(0.03, self.i + 0.04 - 0.015)
        return max(0.0, profit_y) / discount + self.e.firm_dep - self.e.firm_loan

    def money_stock(self) -> float:
        """Dinero en manos del público: depósitos, cuentas de inversión y euro digital."""
        e = self.e
        return e.deposits + float(e.inv.sum()) + float(e.cbdc.sum())

    def shock_age(self) -> int | None:
        """Meses desde que empezó la crisis (None si no hay o aún no ha llegado)."""
        if self.p.shock == "none" or not self.recording:
            return None
        k = self.t - self.p.shock_month
        return k if k >= 0 else None

    def inflation_anchor(self) -> float:
        """Inflación que la gente espera a largo plazo si se cree la regla:
        crecimiento del dinero menos crecimiento de la productividad."""
        p = self.p
        if self.r.issuance in ANCHORED:
            return p.inflation_target
        if self.r.issuance == "gold":
            return p.gold_growth - p.productivity_growth
        issuance = p.fixed_initial_issuance * 0.5 ** (self.t // p.halving_months)
        share = self.base0 / max(self.money_stock(), 1)
        return issuance * share - p.productivity_growth

    def bank_value(self) -> float:
        return max(0.0, self.e.bank_equity(self.bank_houses * self.Ph))

    def net_worth(self) -> np.ndarray:
        e = self.e
        return (e.dep + e.inv + e.cbdc + e.bonds - e.loan + self.houses * self.Ph
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
        return max(0.0, min(by_capital, by_liquidity)) * self.credit_factor

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
        ustar = self.nairu()
        self.zw = self._paid_z()

        # ---------------------------------------------- 1. tipos de interés
        pi_yoy = self.P / self.P_hist[-13] - 1
        if self.r.issuance == "discretionary":
            # regla de Taylor sobre la inflación subyacente: el banco central "mira a través"
            # de los saltos de márgenes (shocks de oferta como el energético)
            core = (1 + pi_yoy) / ((1 + self.mu) / (1 + self.mu_hist[-13])) - 1
            i = p.neutral_rate + core + 0.5 * (core - p.inflation_target) \
                - 0.5 * (self.u - ustar)
            i = max(0.0, i)
        else:
            # sin banco central que fije el precio del dinero, el tipo sale del mercado:
            # sube cuando la economía nominal crece más deprisa que la cantidad de dinero
            money = self.money_stock()
            demand = self.money_k * 12 * self.y_expected * self.P
            i = p.neutral_rate + self.pi_e + p.money_rate_sens * np.log(max(demand, 1) / max(money, 1))
            i = float(np.clip(i, 0.0, 0.25))
        self.i = i
        r_mort = (i + p.mortgage_spread) / 12
        r_firm = (i + p.firm_spread) / 12
        r_bond = (i + p.bond_spread) / 12
        r_dep = max(0.0, i - 0.01) / 12 if self.r.banking == "fractional" else 0.0
        r_inv = max(0.0, i + p.mortgage_spread - 0.015) / 12

        shock = self._shock()

        # ------------------------------------------ 2. emisión de dinero base
        base = e.cb_res_liab + e.cb_acct_liab
        if self.r.issuance == "discretionary":
            g = 2.0 * (p.inflation_target - pi_yoy) + 1.0 * max(0.0, self.u - ustar - 0.02)
            issue = base * float(np.clip(g, 0.0, 0.30)) / 12
        elif self.r.issuance == "rule_2pct":
            issue = base * (p.inflation_target + p.productivity_growth) / 12
        elif self.r.issuance == "gold":
            issue = base * max(0.0, p.gold_growth + self.rs["misc"].normal(0, 0.01)) / 12
        else:
            issue = self.base0 * p.fixed_initial_issuance / 12 * 0.5 ** (t // p.halving_months)
        gov_extra = self._inject(issue)

        # ----------------------------------------------- 3. empleo y salarios
        demand_ratio = self.y_expected / max(self.y_potential / (1 - ustar), 1)
        target_n = int(round(min(0.98, demand_ratio) * lf.sum()))
        blocked = self._smi_priced_out(lf)
        if blocked is not None:
            # los empleos que el SMI deja sin rentabilidad desaparecen (no se dan a otros)
            target_n -= int(round(blocked.sum() * (1 - self.u)))
            self.employed &= ~blocked
        self._adjust_employment(target_n, blocked)
        wages = self.w * self.zw * self.employed
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
                keep = self.rs["misc"].random(n) < affordable
                self.employed &= keep
                wages = self.w * self.zw * self.employed
                bill = float(wages.sum())
        if blocked is not None:
            self.smi_cost = bill / max(self.w * float((self.z * self.employed).sum()), 1)
        e.pay("firm", "hh", "Salarios", dst_vec=wages)
        self.last_wage = np.where(self.employed, self.w * self.zw, self.last_wage)

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
            if self.guaranteed[idx]:
                # aval público (tipo ICO): el Estado cubre la parte financiada por encima del LTV
                cover = min(max(0.0, loss), p.first_buyer_ltv * self.Ph)
                e.pay("gov", "bank", "Aval público hipotecario", amount=cover)
                loss -= cover
                self.guaranteed[idx] = False
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
        tenants = self._allocate_public_housing(renters)
        shortage = tenants.sum() / max(1.0, landlord_w.sum() * (1 - self.withdrawn) + self.bank_houses)
        self.rent = self.rent0 * (self.w / p.wage0) * float(np.clip(shortage, 0.7, 1.6)) ** 0.5
        due = self._contract_rents(tenants)
        rent_vec = np.where(tenants, np.minimum(due, np.maximum(e.dep, 0)), 0.0)
        total_rent = rent_vec.sum()
        if landlord_w.sum() > 0 and total_rent > 0:
            to_vec = total_rent * landlord_w / landlord_w.sum()
            e.pay("hh", "hh", "Alquileres", src_vec=rent_vec, dst_vec=to_vec)
            cap_income += to_vec
        social = np.zeros(n)
        if self.gov_houses:
            social = np.where(self.public_tenant,
                              np.minimum(p.social_rent * self.rent, np.maximum(e.dep, 0)), 0.0)
            e.pay("hh", "gov", "Alquiler social", src_vec=social)

        # impuesto sobre la renta (progresivo)
        gross = wages + pensions + benefits + cap_income
        # evasión: el 20 % más rico oculta parte de sus rentas del capital,
        # más o menos según lo que Hacienda pueda ver de cada pago
        evasion = {"anonymous": p.evasion_anonymous, "mixed": p.evasion_mixed,
                   "traceable": p.evasion_traceable}[self.r.privacy]
        liquid = e.dep + e.bonds + e.inv + e.cbdc + self.houses * self.Ph
        rich = liquid >= np.quantile(liquid, 0.8)
        hidden = np.where(rich, evasion * cap_income, 0.0)
        taxable = gross - hidden
        # IRPF + cotizaciones sociales, con tipo medio progresivo
        avg_rate = p.income_tax_base + p.income_tax_prog * (1 - np.exp(-taxable / (1.5 * self.w)))
        tax = np.minimum(avg_rate * taxable, np.maximum(e.dep, 0))
        self.tax_evaded = float((avg_rate * hidden).sum())
        e.pay("hh", "gov", "IRPF y cotizaciones", src_vec=tax)
        wtax = self._wealth_tax()
        self.income = gross
        self.inc12 += (gross - self.inc12) / 12

        # --------------------------------------------- 6. consumo y gasto público
        rank_inc = gross.argsort().argsort() / (n - 1)
        mpc = p.mpc_low - (p.mpc_low - p.mpc_high) * rank_inc
        # sustitución intertemporal: con tipos reales altos se ahorra más, con tipos
        # reales bajos (o inflación) se adelanta el consumo
        real_rate = i - self.pi_e
        mpc *= float(np.clip(1 - p.hoarding * (real_rate - p.neutral_rate), 0.7, 1.15))
        wealth_mpc = p.wealth_mpc
        released = self._money_properties(gross)
        if self.r.money == "demurrage":
            wealth_mpc += 0.5 * p.demurrage_rate   # guardar cuesta: se gasta antes
        cons = mpc * (gross - tax) + wealth_mpc * np.maximum(e.dep, 0)
        cons = cons * shock["cons"] + released     # el dinero programable se gasta sí o sí
        cons = np.clip(cons, 0, np.maximum(e.dep, 0))
        e.pay("hh", "firm", "Consumo", src_vec=cons)
        G = p.gov_spending_share * self.y_potential * self.P * self.gov_cut
        if self.r.fiscal == "balanced" and self.rev_ema is not None:
            G = float(np.clip(self.rev_ema - self.transfer_ema, 0.5 * G, 1.1 * G))
        self.G_real = G / self.P
        # lo que se oxida se gasta en obra pública el mismo mes (como en Wörgl, 1932)
        G += gov_extra + self.demurrage_paid
        e.pay("gov", "firm", "Compras públicas", amount=G)
        policy_G, public_started = self._policy_spending()

        # --------------------------------------------------- 7. vivienda
        built, house_sales = self._housing_market(r_mort, lf)
        built += public_started

        # IVA: parte de lo que pagan los consumidores va al Estado
        vat = float(cons.sum()) * p.vat / (1 + p.vat)
        e.pay("firm", "gov", "IVA", amount=vat)

        # beneficio y su impuesto
        revenue = float(cons.sum()) - vat + G + policy_G + house_sales
        profit = revenue - bill - firm_int
        ctax = p.corporate_tax * max(0.0, profit)
        ctax = min(ctax, max(0.0, e.firm_dep))
        e.pay("firm", "gov", "Impuesto de sociedades", amount=ctax)
        self.firm_profit = profit - ctax
        self.firm_profit_hist.append(self.firm_profit)
        # las empresas mantienen una deuda proporcional a su capital: piden prestado
        # para invertir si están por debajo del objetivo y amortizan si están por encima
        target_debt = p.firm_leverage * self.K * self.P * (0.7 + 0.3 * self.credit_factor)
        if e.firm_loan < target_debt:
            x = min(0.05 * (target_debt - e.firm_loan), self.lending_room())
            if x > 0:
                e.lend_firm(x)
        elif e.firm_dep > 2 * bill:
            e.repay_firm(min(0.05 * (e.firm_loan - target_debt), e.firm_dep - 2 * bill))

        # medias de 12 meses de lo que entra y sale del Estado (para la regla fiscal)
        revenue_gov = (float(tax.sum()) + vat + ctax + self.demurrage_paid
                       + float(wtax.sum() + social.sum()))
        transfers = (float(pensions.sum() + benefits.sum() + coupons_hh.sum())
                     + e.bank_bonds * r_bond)
        if self.rev_ema is None:
            self.rev_ema, self.transfer_ema = revenue_gov, transfers
        self.rev_ema += (revenue_gov - self.rev_ema) / 12
        self.transfer_ema += (transfers - self.transfer_ema) / 12

        # ------------------------------------------- 8. Estado y bancos
        self._finance_government(G)
        self._bank_liquidity_and_solvency()
        if self.r.banking == "full_reserve":
            self._investment_accounts()
        if self.track and self.recording:
            self._track_step(gross, tax + wtax, rent_vec + social + int_paid + princ)

        # ----------------------------------- 9. precios, salarios, expectativas
        # inversión empresarial: se produce dentro del sector empresas (sin pago
        # entre sectores) pero genera empleo y se financia con caja o crédito
        real_rate = i - self.pi_e
        inv_factor = float(np.clip(1 - p.investment_rate_sens * (real_rate - p.neutral_rate), 0.5, 1.5))
        # "animal spirits": la confianza empresarial fluctúa (proceso AR(1)) y genera ciclos
        self.animal = p.spirits_rho * self.animal + p.spirits_sd * self.rs["spirits"].normal()
        investment = (p.investment_share * self.y_potential * inv_factor * shock["inv"]
                      * float(np.exp(self.animal)))
        self.K = self.K * (1 - p.depreciation / 12) + investment
        # la obra de una vivienda se reparte a lo largo de ~1 año de producción
        self.construction = 0.92 * self.construction + 0.08 * built * 0.75 * p.house_price0
        real_sales = (float(cons.sum()) - vat + G + policy_G) / self.P + self.construction + investment
        self.y_expected = 0.85 * self.y_expected + 0.15 * real_sales
        self.u = 1 - (self.employed & lf).sum() / max(1, lf.sum())
        gap = float(np.clip(real_sales / max(self.y_potential, 1) - 1, -0.3, 0.3))
        self.mu = 0.9 * self.mu + 0.1 * p.markup * (1 + 1.5 * gap)
        self.mu = max(self.mu, shock["mu_floor"])
        wage_growth = self.pi_e + p.productivity_growth + p.phillips * (ustar - self.u)
        wage_growth = max(p.wage_floor, wage_growth)
        self.w *= 1 + wage_growth / 12
        self.A *= (1 + p.productivity_growth / 12) * shock["A"]
        self._public_capital()
        cost = 1 + p.smi_pass_through * (self.smi_cost - 1)   # parte del coste del SMI que va a precios
        self.P = (1 + self.mu) * self.w * cost / self.A
        self.P_hist.append(self.P)
        self.mu_hist.append(self.mu)
        pi_yoy = self.P / self.P_hist[-13] - 1
        # expectativas: adaptativas, pero ancladas a la inflación que implica la regla
        adaptive = 0.92 * self.pi_e + 0.08 * pi_yoy
        w = p.credibility
        self.pi_e = w * self.inflation_anchor() + (1 - w) * adaptive
        self.y_potential = self.A * float((self.z * lf).sum()) * (1 - self.nairu())

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
        if self.r.money == "cbdc":
            # dinero programable: llega en euro digital y caduca si no se gasta
            e.cb_issue_cbdc(vec)
            self.stim += vec
        else:
            e.pay("cb", "hh", "Dinero nuevo", dst_vec=vec)
        self._credit_deciles(vec)
        return 0.0

    def _shock(self) -> dict:
        """Efectos de la crisis elegida en este mes."""
        p, e = self.p, self.e
        out = {"cons": 1.0, "inv": 1.0, "A": 1.0, "mu_floor": 0.0}
        self.credit_factor = 1.0
        k = self.shock_age()
        if k is None:
            return out
        size = p.shock_size
        if k == 0:
            self.events.append({"t": self.t, "type": "shock",
                                "text": f"Empieza la crisis: {SHOCKS[p.shock]['label'].lower()}"})
        if p.shock == "pandemic" and k < 6:
            out["cons"] = 1 - 0.25 * size
            out["inv"] = 1 - 0.30 * size
        elif p.shock == "banking":
            if k == 0:
                self.Ph *= 1 - 0.25 * size
                self.Ph_hist[-1] = self.Ph
                e.write_off_firm(0.06 * size * e.firm_loan)
            if k < 24:
                self.credit_factor = 0.3 + 0.7 * k / 24
            if k < 12:
                # caída de confianza: se invierte menos y se ahorra por precaución
                out["inv"] = 1 - 0.30 * size
                out["cons"] = 1 - 0.06 * size
        elif p.shock == "energy" and k < 12:
            out["mu_floor"] = p.markup + 0.10 * size * (1 - k / 12)
        elif p.shock == "automation" and k < 12:
            out["A"] = (1 + 0.10 * size) ** (1 / 12)
        return out

    def _money_properties(self, income: np.ndarray) -> np.ndarray:
        """Oxidación del dinero o euro digital. Devuelve el gasto forzoso del
        dinero programable que se libera este mes."""
        p, e = self.p, self.e
        self.demurrage_paid = 0.0
        released = np.zeros(p.households)
        if self.r.money == "demurrage":
            exempt = np.maximum(income, 0)               # un mes de renta no se oxida
            fee = p.demurrage_rate * np.maximum(e.dep - exempt, 0)
            e.pay("hh", "gov", "Oxidación del dinero", src_vec=fee)
            bill = self.w * float((self.z * self.employed).sum())
            ffee = p.demurrage_rate * max(0.0, e.firm_dep - 2 * bill)
            e.pay("firm", "gov", "Oxidación del dinero", amount=ffee)
            self.demurrage_paid = float(fee.sum()) + ffee
        elif self.r.money == "cbdc":
            # el dinero programable se gasta en ~4 meses; lo que queda caduca
            if self.stim.sum() > 0:
                out = np.minimum(self.stim * 0.25, e.cbdc)
                e.from_cbdc(out)
                released = out
                self.stim -= out
                expire = np.minimum(self.stim / p.stimulus_expiry, e.cbdc)
                e.expire_cbdc(expire)
                self.stim -= expire
            # cada hogar reparte su liquidez entre depósitos y euro digital (con límite)
            limit = p.cbdc_limit          # límite nominal fijo, como propone el BCE
            free = e.cbdc - self.stim
            target = np.minimum(limit, p.cbdc_share * np.maximum(e.dep + free, 0))
            move = target - free
            up = np.clip(move, 0, np.maximum(e.dep, 0))
            down = np.clip(-move, 0, np.maximum(free, 0))
            if self.r.banking == "fractional" and self.r.issuance not in LOLR:
                # sin prestamista de última instancia el banco no puede perder más reservas de las que tiene
                cap = max(0.0, e.bank_res - p.reserve_ratio * e.bank_dep_liab)
                if up.sum() > cap:
                    up *= cap / up.sum()
            e.to_cbdc(up)
            e.from_cbdc(down)
        return released

    def _credit_deciles(self, vec: np.ndarray):
        nw = self.net_worth()
        dec = np.minimum((nw.argsort().argsort() * 10) // self.p.households, 9)
        self.new_money_deciles += np.bincount(dec, weights=vec, minlength=10)
        self.new_money_to["Hogares"] += float(vec.sum())

    def _adjust_employment(self, target_n: int, blocked: np.ndarray | None = None):
        lf = self.labor_force
        self.employed &= lf
        cur = int(self.employed.sum())
        max_move = max(1, int(0.04 * lf.sum()))
        # con números aleatorios comunes, se contrata (o despide) por orden de una clave al azar
        # de cada hogar: si la medida cambia cuántos, solo cambia quién está en el margen
        keys = self.rs["jobs"].random(self.p.households) if self.crn and self.recording else None
        if target_n > cur:
            free = lf & ~self.employed
            pool = np.flatnonzero(free if blocked is None else free & ~blocked)
            k = min(len(pool), target_n - cur, max_move)
            if k > 0:
                pick = (pool[np.argsort(keys[pool])[:k]] if keys is not None
                        else self.rs["misc"].choice(pool, k, replace=False))
                self.employed[pick] = True
        elif target_n < cur:
            pool = np.flatnonzero(self.employed)
            k = min(len(pool), cur - target_n, max_move)
            if k > 0:
                pick = (pool[np.argsort(keys[pool])[:k]] if keys is not None
                        else self.rs["misc"].choice(pool, k, replace=False))
                self.employed[pick] = False

    def _housing_market(self, r_mort: float, lf: np.ndarray) -> tuple[int, float]:
        p, e, rng, n = self.p, self.e, self.rng, self.p.households
        Ph = self.Ph
        growth_exp = self.Ph_hist[-1] / self.Ph_hist[-13] - 1

        # construcción: más cuanto mayor es el margen sobre el coste
        cost = 0.75 * p.house_price0 * self.P
        margin = Ph / cost - 1
        rate = p.construction_rate * p.permits_speed   # licencias más rápidas: más oferta con el mismo margen
        built = int(self.rs["build"].poisson(max(0.0, n * rate * margin)))
        self.firm_houses += built

        # compradores
        renters = (self.houses == 0) & lf & self.employed & (self.age < 50)
        hh = self.rs["hh"]
        first = renters & (hh.random(n) < 0.03)
        exp_return = 12 * self.rent_eff / Ph + growth_exp
        invest_p = 0.015 if exp_return > 12 * r_mort + 0.01 else 0.003
        investors = (self.houses >= 1) & (e.dep > 0.5 * Ph) & (hh.random(n) < invest_p)
        buyers = np.flatnonzero(first | investors)
        order = hh.random(n) if self.crn and self.recording else None
        if order is None:
            self.rs["misc"].shuffle(buyers)
        else:
            buyers = buyers[np.argsort(order[buyers])]

        # vendedores
        extra = np.maximum(self.houses - 1, 0)
        sell_p = 0.006 if exp_return > 12 * r_mort else 0.012
        old = self.age > 80
        sellers = np.flatnonzero((extra > 0) & ((hh.random(n) < sell_p) | old))
        if order is None:
            self.rs["misc"].shuffle(sellers)
        else:
            sellers = sellers[np.argsort(order[sellers])]
        sellers = list(sellers)
        listings = len(sellers) + self.bank_houses + self.firm_houses

        income_m = np.maximum(self.income, self.w * self.z * self.employed)
        deals, sales_firm, demand = 0, 0.0, 0
        for b in buyers:
            # ayudas a la primera vivienda para menores de 36 años: entrada y aval público
            young = self.houses[b] == 0 and self.age[b] < 36
            aid = p.first_buyer_aid * Ph if young else 0.0
            own = min(0.8 * max(e.dep[b], 0.0) + aid, Ph)
            loan = Ph - own
            if loan > (p.ltv + (p.first_buyer_ltv if young else 0.0)) * Ph:
                continue
            if loan > 0:
                pay = float(annuity(np.array([loan]), r_mort, np.array([p.mortgage_years * 12]))[0])
                if pay > p.dsti * income_m[b] or self.lending_room() < loan:
                    continue
            demand += 1
            if deals >= listings:
                continue
            if aid > 0:
                gv = np.zeros(n)
                gv[b] = aid
                e.pay("gov", "hh", "Ayuda a la compra de vivienda", dst_vec=gv)
            if loan > 0:
                e.lend_hh(b, loan)
                self.months_left[b] = p.mortgage_years * 12
                self.guaranteed[b] = loan > p.ltv * Ph + 1e-6
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
            z = self.rs["demo"].lognormal(0.0, 0.5, len(dead))
            self.z[dead] = z / np.exp(0.125)
            self.employed[dead] = False
            self.last_wage[dead] = self.w * self.z[dead]
            self.public_tenant[dead] = False
            if self.track and self.recording:
                self.tr["dead"][dead] = True

    # ================================================ laboratorio de políticas
    def _start_policies(self, nw: np.ndarray):
        """Estado de las medidas al empezar a aplicarlas (fin del arranque)."""
        p, n = self.p, self.p.households
        self.job_u = self.prng.random(n)           # umbral de cada empleo frente a una subida del SMI
        self.smi_u = self.prng.random(n)           # quién de los que cobran menos del SMI lo cobra por hora
        self.rent_i = np.full(n, self.rent)        # alquiler de cada contrato (con tope)
        self.was_renter = self.houses == 0
        self.Kg_ref = p.public_capital0 * 12 * self.y_expected
        if self.track:
            e, f = self.e, SPAIN_WAGE / self.w_ref
            fin = e.dep + e.inv + e.cbdc + e.bonds + self.shares * (self.firm_value() + self.bank_value())
            self.tr = {
                "age": self.age.copy(), "income": self.inc12 * f, "fin": fin * f, "wealth": nw * f,
                "houses": self.houses.copy(), "mortgage": e.loan > 1e-6, "renter": self.houses == 0,
                "gross": np.zeros(n), "disp": np.zeros(n), "housing": np.zeros(n),
                "unemp": np.zeros(n), "lf": np.zeros(n), "own_month": np.full(n, -1),
                "dead": np.zeros(n, dtype=bool), "months": 0,
            }

    def _paid_z(self) -> np.ndarray:
        """Salario relativo que se paga con el SMI. Quien está entre el SMI actual y el nuevo
        pasa al nuevo. De quienes ganan menos que el SMI anual (jornadas parciales), solo una
        parte cobra el SMI por hora y sube en la misma proporción; el resto ya cobra más por hora."""
        p = self.p
        r = p.smi_raise
        if r == 0 or not self.recording:
            return self.z
        k0 = p.smi_kaitz
        low = np.where(self.smi_u < p.smi_parttime_cover, self.z * (1 + r), self.z)
        return np.where(self.z < k0, low, np.maximum(self.z, k0 * (1 + r)))

    def _smi_priced_out(self, lf: np.ndarray) -> np.ndarray | None:
        """Empleos que dejan de ser rentables con el nuevo SMI: con elasticidad ε, de los
        afectados por una subida g se mantiene una parte (1 + g)^ε."""
        if self.zw is self.z or self.job_u is None:
            return None
        keep = (self.zw / self.z) ** self.p.smi_elasticity
        return lf & (self.job_u > keep)

    def _wealth_tax(self) -> np.ndarray:
        p, e = self.p, self.e
        if p.wealth_tax <= 0:
            return np.zeros(p.households)
        threshold = p.wealth_tax_threshold / SPAIN_WAGE * self.w   # el umbral se indexa a los salarios
        base = np.maximum(self.net_worth() - threshold, 0) * (1 - p.wealth_tax_avoidance)
        wtax = np.minimum(p.wealth_tax / 12 * base, np.maximum(e.dep, 0))
        e.pay("hh", "gov", "Impuesto sobre el patrimonio", src_vec=wtax)
        return wtax

    def _policy_spending(self) -> tuple[float, int]:
        """Políticas activas de empleo y construcción de vivienda pública (pagos del Estado
        a las empresas). Devuelve el gasto y las viviendas públicas que se empiezan."""
        p, e = self.p, self.e
        spent, started = 0.0, 0
        if p.almp_spending > 0 or self.almp_level > 0:
            # el efecto sobre el paro estructural tarda ~2 años en llegar
            self.almp_level += (p.almp_spending - self.almp_level) / 24
            spent += e.pay("gov", "firm", "Políticas activas de empleo",
                           amount=p.almp_spending * self.y_potential * self.P)
        if p.public_housing > 0:
            self.pub_acc += p.public_housing / 1000 / 12 * p.households
            started = int(self.pub_acc)
            self.pub_acc -= started
            if started:
                spent += e.pay("gov", "firm", "Construcción de vivienda pública",
                               amount=started * 0.75 * p.house_price0 * self.P)
                self.pub_pipeline.append((self.t + 24, started))   # se entregan a los 2 años
        if self.pub_pipeline:
            self.gov_houses += sum(k for t0, k in self.pub_pipeline if t0 <= self.t)
            self.pub_pipeline = [(t0, k) for t0, k in self.pub_pipeline if t0 > self.t]
        return spent, started

    def _allocate_public_housing(self, renters: np.ndarray) -> np.ndarray:
        """Asigna la vivienda pública libre a los inquilinos de menor renta. Devuelve los
        hogares que alquilan en el mercado privado."""
        if not self.gov_houses:
            return renters
        self.public_tenant &= renters
        free = self.gov_houses - int(self.public_tenant.sum())
        if free > 0:
            cand = np.flatnonzero(renters & ~self.public_tenant)
            self.public_tenant[cand[np.argsort(self.inc12[cand])[:free]]] = True
        return renters & ~self.public_tenant

    def _contract_rents(self, tenants: np.ndarray):
        """Alquiler que paga cada inquilino. Sin tope, el de mercado. Con tope, cada contrato
        vigente sube como mucho el tope al año; los contratos nuevos (quien empieza a alquilar
        o se muda, ~18 % al año) se firman al precio de mercado, que sube si los caseros
        retiran pisos del alquiler."""
        p = self.p
        if p.rent_cap >= 1 or self.rent_i is None:
            self.rent_eff = self.rent
            return self.rent
        fresh = tenants & (~self.was_renter | (self.prng.random(p.households) < 0.015))
        growth = (1 + p.rent_cap) ** (1 / 12)
        self.rent_i = np.where(fresh, self.rent, np.minimum(self.rent, self.rent_i * growth))
        self.was_renter = tenants.copy()
        self.rent_eff = float(self.rent_i[tenants].mean()) if tenants.any() else self.rent
        # parte de los caseros retira el piso del alquiler residencial (venta, temporada, turístico)
        # cuando lo que cobra queda por debajo del mercado; tarda ~1 año en notarse
        target = min(0.5, p.rent_cap_elasticity * max(0.0, 1 - self.rent_eff / self.rent))
        self.withdrawn += (target - self.withdrawn) / 12
        return self.rent_i

    def _public_capital(self):
        """Inversión pública: el capital público adicional sube la productividad con
        elasticidad θ (A ∝ K_g^θ)."""
        p = self.p
        if not self.recording or (p.gov_investment_share == TODAY.gov_investment_share and not self.extra_Kg):
            return
        self.extra_Kg = (self.extra_Kg * (1 - 0.04 / 12)
                         + (p.gov_investment_share - TODAY.gov_investment_share) * self.G_real)
        boost = max(0.5, 1 + self.extra_Kg / self.Kg_ref) ** p.public_capital_elasticity
        self.A *= boost / self.A_boost
        self.A_boost = boost

    def _track_step(self, gross: np.ndarray, taxes: np.ndarray, housing: np.ndarray):
        """Lo que le pasa a cada hogar, en euros de hoy (para «¿Y a mí cómo me afecta?»)."""
        tr, f = self.tr, self.to_today_eur(1.0)
        lf = self.labor_force
        tr["gross"] += gross * f
        tr["disp"] += (gross - taxes) * f
        tr["housing"] += housing * f
        tr["unemp"] += lf & ~self.employed
        tr["lf"] += lf
        bought = tr["renter"] & (tr["own_month"] < 0) & (self.houses > 0)
        tr["own_month"][bought] = self.t
        tr["months"] += 1

    def household_panel(self) -> dict:
        """Situación de cada hogar al empezar la medida y sus resultados al final."""
        tr, f = self.tr, self.to_today_eur(1.0)
        m = max(1, tr["months"])
        retired = ~self.labor_force
        pension = self.p.pension_ratio * self.z * self.w * f   # la de hoy o la que tendría al jubilarse
        return {
            **{k: tr[k] for k in ("age", "income", "fin", "wealth", "houses", "mortgage", "renter",
                                  "own_month", "dead")},
            "disp": tr["disp"] / m, "gross_avg": tr["gross"] / m, "housing": tr["housing"] / m,
            "burden": tr["housing"] / np.maximum(tr["disp"], 1.0),
            "unemp": tr["unemp"] / np.maximum(tr["lf"], 1), "wealth_end": self.net_worth() * f,
            "pension": pension, "retired_end": retired, "months": m,
        }

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
        self.record("broad_money", self.money_stock() / ref)
        self.record("cbdc_share", float(e.cbdc.sum()) / max(self.money_stock(), 1))
        self.record("tax_gap", 12 * self.tax_evaded / max(gdp_y, 1))
        self.record("demurrage", 12 * self.demurrage_paid / max(gdp_y, 1))
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
        if self.track:
            # series internas del laboratorio de políticas (no salen en result())
            tenants = (self.houses == 0) & ~self.public_tenant
            self.record("_rent_paid", self.rent_eff / max(1.0, median_wage))
            self.record("_public_housing", self.gov_houses / p.households)
            self.record("_tenants", float(tenants.mean()))
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
                       "firm": self.firm_houses * self.Ph,
                       "gov": self.gov_houses * self.Ph}
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
