"""Dimensiones del sistema monetario y parámetros de la economía simulada.

Un régimen monetario no es un bloque cerrado: es una combinación de piezas
independientes (regla de emisión, canal de entrada del dinero nuevo y sistema
bancario). Cada pieza se puede combinar con cualquier otra.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, fields
from itertools import product

# ---------------------------------------------------------------- catálogo

CATALOG = {
    "issuance": {
        "label": "Regla de emisión",
        "help": "Quién decide cuánto dinero base nuevo se crea y con qué criterio.",
        "options": {
            "discretionary": {
                "label": "Discrecional (actual)",
                "short": "Discrecional",
                "desc": "El banco central fija el tipo de interés con una regla de Taylor y "
                        "compra activos (QE) cuando la inflación cae por debajo del objetivo "
                        "o el paro se dispara. Es lo más parecido al BCE actual.",
            },
            "rule_2pct": {
                "label": "Algoritmo del 2 %",
                "short": "Algoritmo 2 %",
                "desc": "La base monetaria crece de forma automática al 2 % más el crecimiento "
                        "tendencial de la productividad. Sin decisiones humanas.",
            },
            "gold": {
                "label": "Patrón oro",
                "short": "Patrón oro",
                "desc": "Solo se crea dinero base cuando aumentan las reservas de oro "
                        "(≈1,5 % anual con ruido). No hay prestamista de última instancia.",
            },
            "fixed_supply": {
                "label": "Oferta fija tipo Bitcoin",
                "short": "Oferta fija",
                "desc": "Emisión programada que se reduce a la mitad cada 4 años (halving) "
                        "hasta un máximo. No hay prestamista de última instancia.",
            },
        },
    },
    "channel": {
        "label": "Canal del dinero nuevo",
        "help": "Por dónde entra en la economía el dinero base que se crea.",
        "options": {
            "banks": {
                "label": "Bancos (compra de bonos)",
                "short": "Bancos",
                "desc": "El banco central compra bonos a los bancos y, si no les quedan, a los "
                        "hogares que los tienen. El dinero entra por el sistema financiero.",
            },
            "government": {
                "label": "Gasto público",
                "short": "Gobierno",
                "desc": "El dinero nuevo se abona al Tesoro, que lo gasta en bienes y servicios. "
                        "Llega primero a las empresas y a sus trabajadores.",
            },
            "dividend": {
                "label": "Dividendo ciudadano",
                "short": "Dividendo",
                "desc": "El dinero nuevo se reparte a partes iguales entre todos los hogares.",
            },
            "miners": {
                "label": "Mineros / validadores",
                "short": "Mineros",
                "desc": "Como en Bitcoin: el dinero nuevo lo reciben quienes poseen la "
                        "infraestructura de validación (concentrada en los hogares más ricos).",
            },
        },
    },
    "banking": {
        "label": "Sistema bancario",
        "help": "Si los bancos pueden crear dinero al prestar o solo prestan ahorro ya existente.",
        "options": {
            "fractional": {
                "label": "Reserva fraccionaria",
                "short": "Fraccionaria",
                "desc": "Los bancos crean depósitos nuevos cuando conceden un préstamo. Están "
                        "limitados por el capital (8 %), el coeficiente de reservas (1 %) y la "
                        "solvencia del cliente.",
            },
            "full_reserve": {
                "label": "Reserva del 100 %",
                "short": "Reserva 100 %",
                "desc": "Chicago Plan: cada depósito está respaldado por reservas. Los bancos solo "
                        "prestan el dinero que los ahorradores ponen en cuentas de inversión.",
            },
        },
    },
}

DIMENSIONS = list(CATALOG)


@dataclass(frozen=True)
class Regime:
    issuance: str = "discretionary"
    channel: str = "banks"
    banking: str = "fractional"

    def __post_init__(self):
        for dim in DIMENSIONS:
            value = getattr(self, dim)
            if value not in CATALOG[dim]["options"]:
                raise ValueError(f"Opción desconocida para {dim}: {value!r}")

    @property
    def key(self) -> str:
        return f"{self.issuance}|{self.channel}|{self.banking}"

    @property
    def label(self) -> str:
        return " · ".join(CATALOG[d]["options"][getattr(self, d)]["short"] for d in DIMENSIONS)

    @classmethod
    def from_key(cls, key: str) -> "Regime":
        return cls(*key.split("|"))

    @classmethod
    def all(cls) -> list["Regime"]:
        return [cls(*combo) for combo in product(*(CATALOG[d]["options"] for d in DIMENSIONS))]


# ------------------------------------------------------------- parámetros

@dataclass
class Params:
    """Parámetros de la economía. Calibración ilustrativa con órdenes de magnitud
    de España (ver Metodología); la calibración formal con EFF/INE es la Fase 3."""

    households: int = 2000
    months: int = 120
    seed: int = 1
    burn_in: int = 48              # meses con el sistema actual antes de cambiar las reglas

    # Mercado laboral y producción
    wage0: float = 2000.0          # salario medio mensual inicial (€)
    markup: float = 0.8            # margen sobre coste laboral → participación salarial ≈ 56 %
    investment_share: float = 0.18 # inversión empresarial sobre el PIB potencial
    investment_rate_sens: float = 3.0  # cuánto cae la inversión por punto de tipo real
    depreciation: float = 0.06     # depreciación anual del capital
    firm_leverage: float = 0.25    # deuda objetivo de las empresas sobre su capital
    productivity_growth: float = 0.012  # crecimiento anual de la productividad
    natural_unemployment: float = 0.10
    phillips: float = 0.6          # sensibilidad salarial al paro
    wage_floor: float = -0.02      # caída anual máxima del salario nominal (rigidez)
    retirement_age: int = 67
    pension_ratio: float = 0.55
    benefit_ratio: float = 0.6

    # Hogares
    mpc_low: float = 1.0           # propensión a consumir de las rentas bajas
    mpc_high: float = 0.85         # propensión a consumir de las rentas altas
    wealth_mpc: float = 0.005      # consumo mensual sobre la riqueza líquida
    hoarding: float = 4.0          # cuánto frena el consumo un tipo real alto

    # Sector público
    gov_spending_share: float = 0.18   # gasto real sobre el PIB potencial
    corporate_tax: float = 0.25
    vat: float = 0.10                  # IVA efectivo sobre el consumo
    income_tax_base: float = 0.08      # tipo medio de IRPF + cotizaciones (rentas bajas)
    income_tax_prog: float = 0.20      # tramo adicional que se alcanza en rentas altas
    debt_to_gdp0: float = 1.0

    # Vivienda
    house_price0: float = 150_000.0
    homeownership0: float = 0.75
    extra_houses0: float = 0.20       # viviendas en alquiler por hogar
    rent_yield: float = 0.04
    ltv: float = 0.8
    dsti: float = 0.35
    mortgage_years: int = 25
    construction_rate: float = 0.0010  # viviendas nuevas al mes por hogar con margen 100 %

    # Banca y política monetaria
    reserve_ratio: float = 0.01
    capital_ratio: float = 0.08
    neutral_rate: float = 0.005
    inflation_target: float = 0.02
    credibility: float = 0.15          # peso mensual del objetivo en las expectativas
    money_rate_sens: float = 0.15      # cuánto sube el tipo de mercado si falta dinero
    mortgage_spread: float = 0.015
    firm_spread: float = 0.02
    bond_spread: float = 0.005

    # Emisión en los regímenes de reglas fijas
    gold_growth: float = 0.015
    fixed_initial_issuance: float = 0.04   # emisión anual inicial sobre la base inicial
    halving_months: int = 48

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Params":
        allowed = {f.name: f.type for f in fields(cls)}
        clean = {}
        for k, v in (data or {}).items():
            if k in allowed:
                default = getattr(cls(), k)
                clean[k] = type(default)(v)
        return cls(**clean)


# Límites para lo que acepta la API (evita simulaciones que tumben el servidor)
LIMITS = {"households": (200, 5000), "months": (24, 240), "seeds": (1, 40)}
