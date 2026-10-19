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
                "desc": "Emisión programada que se reduce a la mitad cada 4 años (halving), "
                        "calibrada con la inflación actual de Bitcoin (≈0,8 % anual). No hay "
                        "prestamista de última instancia.",
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
    "money": {
        "label": "Propiedades del dinero",
        "help": "Qué se puede hacer con el dinero una vez emitido: guardarlo sin coste, o no.",
        "options": {
            "normal": {
                "label": "Dinero normal",
                "short": "Normal",
                "desc": "Como hoy: guardar dinero no cuesta nada (salvo la inflación).",
            },
            "demurrage": {
                "label": "Dinero que se oxida (Gesell)",
                "short": "Se oxida",
                "desc": "Los saldos ociosos pierden un 0,5 % al mes (≈6 % al año); el Estado lo gasta en obra "
                        "pública el mismo mes. Empuja a gastar o a invertir el ahorro. Inspirado en Silvio "
                        "Gesell y el experimento de Wörgl (1932).",
            },
            "cbdc": {
                "label": "Euro digital programable (CBDC)",
                "short": "CBDC",
                "desc": "Los hogares pueden tener dinero directamente en el banco central, con un límite de "
                        "3.000 € (como propone el BCE). El dinero nuevo que reciben los hogares es "
                        "programable: caduca si no se gasta. Los bancos pierden parte de sus depósitos.",
            },
        },
    },
    "privacy": {
        "label": "Privacidad del dinero",
        "help": "Cuánto puede ver Hacienda de cada pago. Afecta a la evasión de las rentas del capital.",
        "options": {
            "mixed": {
                "label": "Mixta (actual)",
                "short": "Mixta",
                "desc": "Cuentas bancarias visibles, efectivo y estructuras opacas no. Se evade ≈10 % de "
                        "las rentas del capital del 20 % más rico.",
            },
            "anonymous": {
                "label": "Anónima",
                "short": "Anónima",
                "desc": "Pagos sin identificar, como el efectivo o una cripto sin KYC. Se evade ≈25 % de las "
                        "rentas del capital del 20 % más rico.",
            },
            "traceable": {
                "label": "Totalmente rastreable",
                "short": "Rastreable",
                "desc": "Cada pago queda registrado. La evasión cae al ≈2 %. El coste, la vigilancia, "
                        "no se mide en euros y el modelo no lo cuantifica.",
            },
        },
    },
    "fiscal": {
        "label": "Regla fiscal",
        "help": "Si el Estado puede endeudarse o tiene que cuadrar sus cuentas cada año.",
        "options": {
            "free": {
                "label": "Déficit libre (actual)",
                "short": "Déficit libre",
                "desc": "El gasto público sigue su tendencia y el déficit se financia con bonos.",
            },
            "balanced": {
                "label": "Presupuesto equilibrado",
                "short": "Equilibrio",
                "desc": "El gasto en bienes y servicios se ajusta a lo que se recauda (media de 12 meses) "
                        "menos pensiones, prestaciones e intereses. Las prestaciones siguen pagándose.",
            },
        },
    },
}

CORE = ["issuance", "channel", "banking"]

SHOCKS = {
    "none": {"label": "Sin crisis", "desc": "La economía evoluciona sin perturbaciones externas."},
    "pandemic": {"label": "Pandemia", "desc": "Durante 6 meses el consumo cae un 25 % (confinamiento) "
                 "y la inversión un 30 %."},
    "banking": {"label": "Crisis bancaria", "desc": "La vivienda cae un 25 % de golpe, impagan el 6 % de los "
                "préstamos a empresas, los bancos cortan el crédito durante 2 años y las empresas se "
                "desapalancan; durante un año cae la confianza (inversión −30 %, consumo −6 %)."},
    "energy": {"label": "Shock energético", "desc": "Los costes de producción suben de golpe (margen +10 "
               "puntos) y se normalizan en un año: inflación importada."},
    "automation": {"label": "Boom de automatización", "desc": "La productividad sube un 10 % en un año: "
                   "se produce lo mismo con menos trabajadores."},
}

DIMENSIONS = list(CATALOG)


@dataclass(frozen=True)
class Regime:
    issuance: str = "discretionary"
    channel: str = "banks"
    banking: str = "fractional"
    money: str = "normal"
    privacy: str = "mixed"
    fiscal: str = "free"

    def __post_init__(self):
        for dim in DIMENSIONS:
            value = getattr(self, dim)
            if value not in CATALOG[dim]["options"]:
                raise ValueError(f"Opción desconocida para {dim}: {value!r}")

    @property
    def key(self) -> str:
        return "|".join(getattr(self, d) for d in DIMENSIONS)

    @property
    def label(self) -> str:
        """Las tres piezas básicas siempre; las demás solo si no son las actuales."""
        default = Regime()
        parts = [CATALOG[d]["options"][getattr(self, d)]["short"] for d in CORE]
        parts += [CATALOG[d]["options"][getattr(self, d)]["short"]
                  for d in DIMENSIONS if d not in CORE and getattr(self, d) != getattr(default, d)]
        return " · ".join(parts)

    @classmethod
    def from_key(cls, key: str) -> "Regime":
        # admite claves cortas (solo las piezas básicas) por compatibilidad
        return cls(*key.split("|"))

    @classmethod
    def all(cls) -> list["Regime"]:
        return [cls(*combo) for combo in product(*(CATALOG[d]["options"] for d in DIMENSIONS))]

    @classmethod
    def core(cls) -> list["Regime"]:
        return [cls(*combo) for combo in product(*(CATALOG[d]["options"] for d in CORE))]


# ------------------------------------------------------------- parámetros

@dataclass
class Params:
    """Parámetros de la economía. Los marcados en data/calibration.json se han
    calibrado por momentos simulados con datos de España (Eurostat y BCE,
    2015–2025); el resto son órdenes de magnitud habituales (ver Metodología)."""

    households: int = 2000
    months: int = 120
    seed: int = 1
    burn_in: int = 48              # meses con el sistema actual antes de cambiar las reglas

    # Mercado laboral y producción
    wage0: float = 2000.0          # salario medio mensual inicial (€)
    markup: float = 0.8            # margen sobre coste laboral → participación salarial ≈ 56 %
    investment_share: float = 0.18 # inversión empresarial sobre el PIB potencial
    investment_rate_sens: float = 3.0  # cuánto cae la inversión por punto de tipo real
    spirits_sd: float = 0.05        # volatilidad mensual de la confianza empresarial
    spirits_rho: float = 0.95      # persistencia de la confianza
    depreciation: float = 0.06     # depreciación anual del capital
    firm_leverage: float = 0.25    # deuda objetivo de las empresas sobre su capital
    productivity_growth: float = 0.012  # crecimiento anual de la productividad
    natural_unemployment: float = 0.14
    phillips: float = 0.6          # sensibilidad salarial al paro
    wage_floor: float = -0.02      # caída anual máxima del salario nominal (rigidez)
    retirement_age: int = 67
    pension_ratio: float = 0.55
    benefit_ratio: float = 0.6

    # Hogares
    wealth_sigma: float = 1.3      # dispersión de la riqueza inicial (log-normal)
    mortgage_prob: float = 0.75    # propietarios < 55 años con hipoteca viva
    mpc_low: float = 1.0           # propensión a consumir de las rentas bajas
    mpc_high: float = 0.85         # propensión a consumir de las rentas altas
    wealth_mpc: float = 0.005      # consumo mensual sobre la riqueza líquida
    hoarding: float = 4.0          # cuánto frena el consumo un tipo real alto

    # Sector público
    gov_spending_share: float = 0.17   # gasto real sobre el PIB potencial
    corporate_tax: float = 0.25
    vat: float = 0.10                  # IVA efectivo sobre el consumo
    income_tax_base: float = 0.08      # tipo medio de IRPF + cotizaciones (rentas bajas)
    income_tax_prog: float = 0.20      # tramo adicional que se alcanza en rentas altas
    debt_to_gdp0: float = 1.1

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
    fixed_initial_issuance: float = 0.008  # emisión anual inicial: la de Bitcoin hoy (0,82 %, data/onchain.json)
    halving_months: int = 48

    # Propiedades del dinero y privacidad
    demurrage_rate: float = 0.005      # oxidación mensual de los saldos ociosos
    cbdc_limit: float = 3000.0         # límite de tenencia de euro digital por hogar (€)
    cbdc_share: float = 0.3            # parte de su liquidez que el hogar quiere en CBDC
    stimulus_expiry: int = 12          # meses hasta que caduca el dinero programable
    evasion_anonymous: float = 0.25
    evasion_mixed: float = 0.10
    evasion_traceable: float = 0.02

    # Crisis
    shock: str = "none"
    shock_month: int = 24
    shock_size: float = 1.0

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
        if clean.get("shock", "none") not in SHOCKS:
            raise ValueError(f"Crisis desconocida: {clean['shock']!r}")
        return cls(**clean)


# Límites para lo que acepta la API (evita simulaciones que tumben el servidor)
LIMITS = {"households": (200, 5000), "months": (24, 240), "seeds": (1, 40)}
