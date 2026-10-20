"""Laboratorio de políticas: medidas económicas sobre el sistema monetario actual.

Cada simulación se hace dos veces con la misma semilla: sin la medida (situación de
partida) y con ella. Las medidas se aplican al terminar el arranque, así que los
hogares de partida son exactamente los mismos en las dos versiones y se pueden
comparar uno a uno (contrafactual emparejado). De ahí salen:

  - el efecto sobre la economía (paro, precios, vivienda, deuda);
  - quién gana y quién pierde (por decil de renta, edad y tenencia de vivienda);
  - «¿Y a mí cómo me afecta?»: los hogares simulados más parecidos al del usuario.

Las cantidades en euros son euros de hoy: se descuenta la inflación y se reescalan
para que el salario medio del modelo sea el de España (INE).
"""

from __future__ import annotations

from dataclasses import fields, replace

import numpy as np

from .config import Params, Regime
from .metrics import summarize
from .model import Model

TODAY = Params()
GROUPS = {
    "taxes": "Impuestos",
    "pensions": "Pensiones",
    "labour": "Trabajo",
    "housing": "Vivienda",
    "spending": "Gasto público",
}

# kind: pct (fracción), num, eur, years, x (multiplicador) · conf: alta | media | baja
LEVERS = {
    # ------------------------------------------------------------- impuestos
    "income_tax_base": {
        "group": "taxes", "kind": "pct", "min": 0.04, "max": 0.14, "step": 0.005, "conf": "media",
        "label": "IRPF y cotizaciones: tipo de las rentas bajas",
        "help": "Tipo medio que pagan las rentas más bajas por IRPF y cotizaciones sociales.",
        "evidence": "Lo mecánico (cuánto se recauda y a quién) es fiable. Lo que el modelo no tiene es que la gente "
                    "trabaje más o menos horas, o declare distinto, cuando cambian los impuestos. La evidencia indica que "
                    "esa respuesta es moderada para la mayoría y mayor en las rentas altas (Saez, Slemrod y Giertz, 2012).",
    },
    "income_tax_prog": {
        "group": "taxes", "kind": "pct", "min": 0.10, "max": 0.30, "step": 0.01, "conf": "media",
        "label": "IRPF: tramo adicional de las rentas altas (progresividad)",
        "help": "Cuántos puntos más paga, en media, una renta alta que una baja.",
        "evidence": "Como el modelo no tiene respuesta del trabajo ni de la planificación fiscal, puede exagerar lo que "
                    "recauda una subida en rentas altas y lo que cuesta una bajada (Saez, Slemrod y Giertz, 2012).",
    },
    "vat": {
        "group": "taxes", "kind": "pct", "min": 0.06, "max": 0.16, "step": 0.005, "conf": "media",
        "label": "IVA efectivo",
        "help": "Lo que se recauda por IVA dividido entre el consumo. En España ronda el 10 % aunque el tipo general es "
                "el 21 %, por los tipos reducidos y las exenciones.",
        "evidence": "En el modelo el IVA lo pagan los consumidores en cada compra. La evidencia indica que se traslada en "
                    "gran parte a los precios, aunque las bajadas se trasladan menos que las subidas (Benzarti et al., 2020).",
    },
    "corporate_tax": {
        "group": "taxes", "kind": "pct", "min": 0.15, "max": 0.35, "step": 0.01, "conf": "baja",
        "label": "Impuesto de sociedades",
        "help": "Tipo sobre el beneficio de las empresas (el general en España es el 25 %).",
        "evidence": "En el modelo reduce el beneficio que se reparte y el valor de las empresas, pero no cambia la inversión "
                    "ni dónde se instalan. En la realidad sí influye, y parte del impuesto acaba en salarios más bajos: "
                    "Fuest, Peichl y Siegloch (2018) estiman que en Alemania los trabajadores soportan cerca de la mitad.",
    },
    "wealth_tax": {
        "group": "taxes", "kind": "pct", "min": 0.0, "max": 0.03, "step": 0.0025, "conf": "baja",
        "elasticity": "wealth_tax_avoidance",
        "label": "Impuesto sobre el patrimonio (adicional)",
        "help": "Tipo anual sobre el patrimonio neto que supera el umbral.",
        "evidence": "España ya tiene impuesto sobre el patrimonio y de solidaridad de las grandes fortunas, pero recaudan "
                    "poco (≈0,1 % del PIB) y varias comunidades lo bonifican; el modelo de partida no los incluye, así que "
                    "esta palanca es un impuesto adicional. Lo más incierto es cuánto se elude: estudios para España "
                    "(Agrawal, Foremny y Martínez-Toledano, 2020), Dinamarca (Jakobsen et al., 2020) y Suiza encuentran que "
                    "el patrimonio declarado responde bastante al impuesto (cambios de residencia, planificación).",
    },
    "wealth_tax_threshold": {
        "group": "taxes", "kind": "eur", "min": 300_000, "max": 3_000_000, "step": 100_000, "conf": "baja",
        "sub": "wealth_tax",
        "label": "Umbral exento del impuesto sobre el patrimonio",
        "help": "Patrimonio neto (incluida la vivienda) a partir del cual se paga.",
        "evidence": "Con 700.000 € pagaría en torno al 4 % de los hogares del modelo. En España declaran el impuesto "
                    "actual muchos menos, porque la vivienda habitual y la empresa familiar están en gran parte exentas.",
    },
    # ------------------------------------------------------------- pensiones
    "pension_ratio": {
        "group": "pensions", "kind": "pct", "min": 0.40, "max": 0.70, "step": 0.01, "conf": "media",
        "label": "Generosidad de la pensión (tasa de sustitución)",
        "help": "Pensión pública como fracción del salario medio de su nivel (en el modelo, 55 %). Se indexa a los salarios.",
        "evidence": "Lo mecánico es fiable: subir la pensión aumenta la renta de los jubilados y el gasto público. Aviso "
                    "importante: el modelo no tiene envejecimiento de la población (la proporción de jubilados es constante), "
                    "que es el motivo principal del debate sobre las pensiones en España. Por eso infravalora el coste a "
                    "largo plazo de subirlas y el ahorro de bajarlas.",
    },
    "retirement_age": {
        "group": "pensions", "kind": "years", "min": 63, "max": 70, "step": 1, "conf": "media",
        "label": "Edad de jubilación",
        "help": "Edad a la que se deja de trabajar y se cobra la pensión (hoy, 67 años en el modelo).",
        "evidence": "Retrasarla mantiene a más gente trabajando o buscando empleo y reduce el gasto en pensiones. En el "
                    "modelo el cambio es inmediato (en la realidad se aplica poco a poco) y quien sigue activo tiene que "
                    "encontrar empleo; si no lo encuentra, cobra la prestación por desempleo. Sin envejecimiento demográfico.",
    },
    # ---------------------------------------------------------------- trabajo
    "benefit_ratio": {
        "group": "labour", "kind": "pct", "min": 0.30, "max": 0.80, "step": 0.05, "conf": "media",
        "elasticity": "benefit_elasticity",
        "label": "Prestación por desempleo (fracción del último salario)",
        "help": "Lo que cobra quien pierde el empleo, como fracción de su último salario.",
        "evidence": "Una prestación más generosa protege más la renta de quien pierde el empleo, pero suele alargar algo la "
                    "búsqueda de trabajo. Esa respuesta se ha medido muchas veces y es moderada (Card, Chetty y Weber, 2007; "
                    "Lalive, 2008; para España, Rebollo-Sanz y Rodríguez-Planas, 2020).",
    },
    "smi_raise": {
        "group": "labour", "kind": "pct", "min": 0.0, "max": 0.40, "step": 0.01, "conf": "baja",
        "elasticity": "smi_elasticity",
        "label": "Subida del salario mínimo (SMI)",
        "help": "Subida sobre el SMI actual (16.576 € brutos al año en 2025, ≈62 % del salario medio). Quien cobra menos "
                "del SMI porque trabaja a tiempo parcial sube en la misma proporción.",
        "evidence": "Sube la renta de quien lo cobra, pero puede reducir el empleo de los trabajos menos productivos, y parte "
                    "del coste se traslada a los precios (el modelo traslada el 75 %, como encuentran Harasztosi y Lindner, 2019, para Hungría). La evidencia sobre el empleo es discutida: para EE. UU., Cengiz et al. (2019) "
                    "encuentran efectos sobre el empleo cercanos a cero en subidas moderadas; para la subida del 22 % de "
                    "2019 en España, el Banco de España estimó pérdidas de empleo apreciables entre los afectados y otros "
                    "estudios, menores. De subidas muy grandes respecto al salario medio se sabe poco.",
    },
    "almp_spending": {
        "group": "labour", "kind": "pct", "min": 0.0, "max": 0.01, "step": 0.0005, "conf": "baja",
        "elasticity": "almp_effectiveness",
        "label": "Políticas activas de empleo (gasto adicional, % del PIB)",
        "help": "Formación, orientación e incentivos a la contratación, además de lo que se gasta hoy (≈0,7 % del PIB).",
        "evidence": "Tienen efectos pequeños a corto plazo y mayores a 2–3 años, y dependen mucho del programa: la formación "
                    "y los incentivos al empleo privado funcionan mejor que el empleo público directo (Card, Kluve y Weber, "
                    "2018). Cuántos puntos de paro baja cada euro es muy incierto. También suben la demanda, porque son gasto.",
    },
    # --------------------------------------------------------------- vivienda
    "permits_speed": {
        "group": "housing", "kind": "x", "min": 1.0, "max": 3.0, "step": 0.1, "conf": "media",
        "label": "Licencias más rápidas (respuesta de la construcción)",
        "help": "Cuánta vivienda nueva se construye para el mismo margen de beneficio (×1 = hoy).",
        "evidence": "Donde la oferta de vivienda responde más, los precios suben menos cuando aumenta la demanda (Glaeser y "
                    "Gyourko, 2018). El modelo no tiene suelo limitado ni escasez de trabajadores de la construcción, que "
                    "también frenan la oferta; por eso el efecto de esta palanca es más bien un máximo.",
    },
    "public_housing": {
        "group": "housing", "kind": "num", "min": 0.0, "max": 10.0, "step": 0.5, "conf": "media",
        "label": "Vivienda pública en alquiler (nuevas al año por cada 1.000 hogares)",
        "help": "El Estado paga la construcción, la entrega a los 2 años y la alquila por debajo del mercado a los "
                "inquilinos de menor renta. España termina hoy unas 4–5 viviendas al año por cada 1.000 hogares en total.",
        "evidence": "España tiene muy poca vivienda social (≈2–3 % del parque, frente a más del 20 % en Países Bajos o "
                    "Austria). En el modelo, cada vivienda pública saca a un hogar del alquiler privado y eso modera el "
                    "alquiler de mercado. No modela el suelo, la gestión ni el mantenimiento, ni el tiempo real de "
                    "tramitación, que suele ser mayor de 2 años.",
    },
    "social_rent": {
        "group": "housing", "kind": "pct", "min": 0.3, "max": 0.8, "step": 0.05, "conf": "media",
        "sub": "public_housing",
        "label": "Alquiler de la vivienda pública (fracción del de mercado)",
        "help": "Lo que paga el inquilino de una vivienda pública respecto al alquiler de mercado.",
        "evidence": "Cuanto más bajo, más ayuda al inquilino y más cuesta al Estado.",
    },
    "rent_cap": {
        "group": "housing", "kind": "pct", "min": 0.0, "max": 1.0, "conf": "baja",
        "choices": [1.0, 0.05, 0.03, 0.02, 0.01, 0.0], "elasticity": "rent_cap_elasticity",
        "label": "Tope a la subida del alquiler (contratos vigentes)",
        "help": "Cuánto puede subir al año el alquiler de un contrato en vigor. Los contratos nuevos se firman a precio de mercado.",
        "evidence": "Los topes ayudan a quien ya tiene contrato, pero reducen la oferta de alquiler y encarecen el piso para "
                    "quien busca uno nuevo: en San Francisco, los caseros afectados redujeron su oferta de alquiler ≈15 % "
                    "(Diamond, McQuade y Qian, 2019). Para la regulación catalana de 2020, Jofre-Monseny, Martínez-Mazza y "
                    "Segú (2023) estiman que los alquileres bajaron algo y que también se redujo la oferta. El modelo no "
                    "tiene escasez visible (todo el que busca piso lo encuentra): el coste aparece como alquileres de "
                    "mercado más altos y más venta de pisos de alquiler.",
    },
    "first_buyer_aid": {
        "group": "housing", "kind": "pct", "min": 0.0, "max": 0.10, "step": 0.01, "conf": "media",
        "label": "Ayuda directa para la entrada (% del precio, menores de 36)",
        "help": "Subvención del Estado a quien compra su primera vivienda antes de los 36 años.",
        "evidence": "Permite comprar antes a quien tiene ingresos pero no ahorros. Si la oferta no responde, parte de la "
                    "ayuda acaba en precios más altos: con Help to Buy en Reino Unido, en Londres casi toda la ayuda se "
                    "tradujo en precios (Carozzi, Hilber y Yu, 2024). En el modelo los precios suben con el exceso de "
                    "demanda, así que este efecto aparece.",
    },
    "first_buyer_ltv": {
        "group": "housing", "kind": "pct", "min": 0.0, "max": 0.20, "step": 0.05, "conf": "media",
        "label": "Aval público para la hipoteca (financiación extra, menores de 36)",
        "help": "Financiación por encima del 80 % que avala el Estado, como la línea ICO de 2023 (hasta el 100 %).",
        "evidence": "La línea de avales ICO ya existe desde 2023, pero el modelo de partida no la incluye. El aval permite "
                    "comprar sin ahorro previo a cambio de más deuda; si el comprador no paga, el Estado cubre la pérdida.",
    },
    # ---------------------------------------------------------- gasto público
    "gov_spending_share": {
        "group": "spending", "kind": "pct", "min": 0.13, "max": 0.21, "step": 0.005, "conf": "media",
        "label": "Compras públicas (% del PIB potencial)",
        "help": "Gasto del Estado en bienes y servicios (sin pensiones ni prestaciones).",
        "evidence": "Más gasto sube la demanda y el empleo a corto plazo, y la deuda. El multiplicador del gasto se estima "
                    "en torno a 0,5–1,5, mayor en recesiones (Ramey, 2019). El modelo no valora los servicios públicos en "
                    "sí (sanidad, educación): solo su efecto sobre la economía.",
    },
    "gov_investment_share": {
        "group": "spending", "kind": "pct", "min": 0.05, "max": 0.30, "step": 0.01, "conf": "media",
        "elasticity": "public_capital_elasticity",
        "label": "Parte del gasto que es inversión pública",
        "help": "Infraestructuras, I+D, digitalización. Hoy ≈12 % de las compras públicas.",
        "evidence": "Pasar gasto corriente a inversión puede subir la productividad a largo plazo. Un metaanálisis (Bom y "
                    "Ligthart, 2014) sitúa la elasticidad del PIB al capital público en ≈0,08 (≈0,12 en infraestructuras "
                    "básicas). El efecto tarda años, y el modelo no mide lo que se deja de prestar en servicios corrientes.",
    },
}

# Supuestos de comportamiento de los que depende cada palanca (y su rango plausible)
ELASTICITIES = {
    "smi_elasticity": {
        "lo": -0.6, "hi": 0.0, "step": 0.05,
        "label": "Elasticidad del empleo al SMI",
        "help": "Si a un trabajador afectado le sube el salario un 10 %, su empleo cae ε × 10 %. 0 = sin efecto.",
    },
    "almp_effectiveness": {
        "lo": 0.2, "hi": 1.5, "step": 0.1,
        "label": "Eficacia de las políticas activas",
        "help": "Puntos de paro estructural que baja cada 1 % del PIB de gasto adicional, a 2 años.",
    },
    "benefit_elasticity": {
        "lo": 0.0, "hi": 0.6, "step": 0.05,
        "label": "Respuesta del paro a la prestación",
        "help": "Elasticidad del paro estructural a la generosidad de la prestación.",
    },
    "rent_cap_elasticity": {
        "lo": 0.0, "hi": 1.5, "step": 0.1,
        "label": "Respuesta de los caseros al tope",
        "help": "Parte de los pisos que los caseros retiran del alquiler residencial (venta, temporada, turístico) por cada punto que el alquiler queda por debajo del mercado. 0 = ninguno.",
    },
    "public_capital_elasticity": {
        "lo": 0.02, "hi": 0.15, "step": 0.01,
        "label": "Elasticidad del PIB al capital público",
        "help": "Cuánto sube la producción si el capital público sube un 1 %.",
    },
    "wealth_tax_avoidance": {
        "lo": 0.0, "hi": 0.6, "step": 0.05,
        "label": "Elusión del impuesto sobre el patrimonio",
        "help": "Parte de la base que se elude (traslados de residencia, sociedades, valoración).",
    },
}

PRESETS = {
    "housing_supply": {
        "label": "Más vivienda: licencias rápidas + vivienda pública",
        "levers": {"permits_speed": 2.0, "public_housing": 4.0, "social_rent": 0.5},
        "desc": "Se duplica la respuesta de la construcción (licencias más ágiles) y el Estado construye 4 viviendas de "
                "alquiler social al año por cada 1.000 hogares, alquiladas a la mitad del precio de mercado.",
        "evidence": "Aumentar la oferta es la medida en la que más coinciden los economistas para moderar precios, pero "
                    "tarda años. La vivienda social es casi inexistente en España comparada con Europa.",
        "caveats": "El modelo no tiene suelo limitado ni escasez de mano de obra en la construcción, así que el efecto de "
                   "las licencias es optimista. Se paga con deuda: no se sube ningún impuesto.",
    },
    "smi": {
        "label": "Subir el SMI un 15 %",
        "levers": {"smi_raise": 0.15},
        "desc": "El salario mínimo sube un 15 % (≈19.000 € al año). Quien cobra por debajo porque trabaja a tiempo parcial "
                "sube en la misma proporción.",
        "evidence": "Sube la renta de los trabajadores con salarios bajos. El efecto sobre el empleo es lo más discutido: "
                    "desde casi nulo (Cengiz et al., 2019) hasta pérdidas apreciables entre los afectados (Banco de España "
                    "para la subida de 2019).",
        "caveats": "El resultado depende sobre todo de la elasticidad del empleo, que puedes cambiar. El modelo no tiene "
                   "economía sumergida ni efectos sobre los salarios justo por encima del SMI.",
    },
    "pensions": {
        "label": "Reforma de pensiones: jubilación a los 68 y pensión un 5 % menor",
        "levers": {"retirement_age": 68, "pension_ratio": 0.52},
        "desc": "La edad de jubilación pasa de 67 a 68 años y la pensión media baja del 55 % al 52 % del salario de "
                "referencia.",
        "evidence": "Retrasar la jubilación y moderar la pensión reduce el gasto y la deuda, a costa de los jubilados y de "
                    "quienes están cerca de jubilarse.",
        "caveats": "El modelo no tiene envejecimiento de la población, que es la razón principal de estas reformas: el "
                   "ahorro que muestra es menor que el que tendría con una población que envejece.",
    },
    "income_tax_cut": {
        "label": "Rebaja de IRPF",
        "levers": {"income_tax_base": 0.07, "income_tax_prog": 0.18},
        "desc": "Baja 1 punto el tipo de las rentas bajas y 2 puntos el tramo adicional de las rentas altas.",
        "evidence": "Más renta disponible para todos, más en euros para quien más gana. Se paga con más deuda (o menos "
                    "gasto si hay regla de equilibrio).",
        "caveats": "El modelo no tiene respuesta de la oferta de trabajo a los impuestos: si la gente trabajara más con la "
                   "rebaja, el coste sería algo menor.",
    },
    "rent_cap": {
        "label": "Tope del 2 % a la subida del alquiler",
        "levers": {"rent_cap": 0.02},
        "desc": "El alquiler de los contratos en vigor no puede subir más de un 2 % al año. Los contratos nuevos se firman "
                "a precio de mercado.",
        "evidence": "Protege a quien ya alquila; la evidencia (San Francisco, Cataluña) muestra que reduce la oferta de "
                    "alquiler y encarece el piso para quien busca uno nuevo.",
        "caveats": "El resultado depende de cuánto vendan los caseros (elasticidad ajustable). El modelo no tiene escasez "
                   "visible: no hay gente que se quede sin piso.",
    },
    "young_buyers": {
        "label": "Ayuda a los jóvenes para comprar",
        "levers": {"first_buyer_aid": 0.05, "first_buyer_ltv": 0.15},
        "desc": "Menores de 36 años: ayuda directa del 5 % del precio y aval público para financiar hasta el 95 %.",
        "evidence": "Adelanta la compra a quien tiene ingresos pero no ahorros. Si la oferta no responde, parte de la ayuda "
                    "sube los precios (Help to Buy en Reino Unido).",
        "caveats": "Más deuda hipotecaria entre los jóvenes; el Estado asume parte del riesgo de impago.",
    },
    "wealth_almp": {
        "label": "Impuesto al patrimonio para pagar políticas activas",
        "levers": {"wealth_tax": 0.01, "almp_spending": 0.004},
        "desc": "Impuesto del 1 % anual sobre el patrimonio que supera 700.000 € y 0,4 % del PIB más en formación y "
                "orientación para el empleo.",
        "evidence": "La recaudación depende de cuánto se eluda; la eficacia de las políticas activas, del diseño de los "
                    "programas. Las dos cosas son muy inciertas.",
        "caveats": "El modelo no tiene fuga de patrimonio a otros países salvo a través de la elusión (ajustable).",
    },
    "public_investment": {
        "label": "Más inversión pública (sin gastar más)",
        "levers": {"gov_investment_share": 0.20},
        "desc": "La parte del gasto público que es inversión sube del 12 % al 20 %, con el mismo gasto total.",
        "evidence": "Puede subir la productividad y los salarios a largo plazo (Bom y Ligthart, 2014), con efectos que "
                    "tardan años.",
        "caveats": "El modelo no mide lo que se pierde en servicios corrientes (sanidad, educación) al pasar gasto a inversión.",
    },
}

AGE_GROUPS = [(20, 35, "20–34"), (35, 50, "35–49"), (50, 65, "50–64"), (65, 86, "65+")]
TENURES = {"renter": "Inquilinos", "mortgage": "Propietarios con hipoteca",
           "outright": "Propietarios sin hipoteca", "landlord": "Caseros (más de una vivienda)"}

# Indicadores de la economía: (serie, cómo se resume)
MACRO = [
    ("unemployment", "mean"), ("inflation", "mean"), ("real_wage", "last"), ("real_gdp", "last"),
    ("debt_gdp", "last"), ("homeownership", "last"), ("_rent_paid", "last"), ("rent_burden", "last"),
    ("price_to_income", "last"), ("house_price_real", "last"), ("gini_income", "mean"), ("top10_wealth", "last"),
]


def catalog() -> dict:
    defaults = TODAY.to_dict()
    lev = {k: {**v, "default": defaults[k]} for k, v in LEVERS.items()}
    ela = {k: {**v, "default": defaults[k]} for k, v in ELASTICITIES.items()}
    return {"groups": GROUPS, "levers": lev, "elasticities": ela, "presets": PRESETS,
            "age_groups": [g[2] for g in AGE_GROUPS], "tenures": TENURES,
            "macro": [f"{k}:{h}" for k, h in MACRO]}


def clean_levers(raw: dict | None) -> dict:
    """Valida las palancas: solo claves conocidas, dentro de su rango y con su tipo.
    Devuelve solo las que cambian respecto a hoy."""
    types = {f.name: type(getattr(TODAY, f.name)) for f in fields(Params)}
    out = {}
    for k, v in (raw or {}).items():
        spec = LEVERS.get(k) or ELASTICITIES.get(k)
        if spec is None:
            raise ValueError(f"Palanca desconocida: {k!r}")
        lo, hi = (spec["min"], spec["max"]) if k in LEVERS else (spec["lo"], spec["hi"])
        x = types[k](min(hi, max(lo, float(v))))
        if x != getattr(TODAY, k):
            out[k] = x
    return out


# --------------------------------------------------------------- simulación
def _run_pair(params: Params, levers: dict) -> tuple[Model, Model]:
    base = Model(Regime(), params, track=True, crn=True)
    pol = Model(Regime(), params, policy=levers, track=True, crn=True)
    for _ in range(params.months):
        base.step()
        pol.step()
    return base, pol


def _macro(m: Model) -> dict:
    out = summarize(m.history)
    for key, how in MACRO:
        s = np.asarray(m.history[key])
        out[f"{key}:{how}"] = float(s[12:].mean() if how == "mean" and len(s) > 12 else
                                    s.mean() if how == "mean" else s[-1])
    return out


def _q(x, qs=(10, 50, 90)) -> dict:
    x = np.asarray(x, dtype=float)
    if not len(x):
        return {"p10": None, "p50": None, "p90": None}
    v = np.percentile(x, qs)
    return {"p10": float(v[0]), "p50": float(v[1]), "p90": float(v[2])}


def _tenure(panel: dict) -> np.ndarray:
    t = np.where(panel["renter"], 0, np.where(panel["mortgage"], 1, 2))
    return np.where(panel["houses"] >= 2, 3, t)


def _groups(b: dict, p: dict) -> dict:
    """Ganadores y perdedores en un par de simulaciones (mismos hogares)."""
    alive = ~b["dead"]
    inc = b["income"]
    dec = np.minimum((inc.argsort().argsort() * 10) // len(inc), 9)
    ten = _tenure(b)
    masks = {"decile": [alive & (dec == d) for d in range(10)],
             "age": [alive & (b["age"] >= lo) & (b["age"] < hi) for lo, hi, _ in AGE_GROUPS],
             "tenure": [alive & (ten == j) for j in range(4)]}
    after_b, after_p = b["disp"] - b["housing"], p["disp"] - p["housing"]
    out = {}
    for name, ms in masks.items():
        rows = []
        for m in ms:
            if m.sum() < 3:
                rows.append({"disp": 0.0, "after_housing": 0.0, "wealth": 0.0, "n": int(m.sum())})
                continue
            rows.append({
                "disp": float((p["disp"][m] - b["disp"][m]).sum() / max(1.0, b["disp"][m].sum())),
                "after_housing": float((after_p[m] - after_b[m]).sum() / max(1.0, np.abs(after_b[m]).sum())),
                "wealth": float(np.median(p["wealth_end"][m] - b["wealth_end"][m])),
                "n": int(m.sum()),
            })
        out[name] = rows
    return out


def simulate(levers: dict, shock: str = "none", shock_month: int = 24, months: int = 120,
             households: int = 2000, seeds: int = 6) -> dict:
    """Simula la economía con y sin las medidas. Devuelve el resultado completo, con los
    paneles de hogares (arrays) para «¿Y a mí?»; `public()` lo deja listo para la API."""
    levers = clean_levers(levers)
    pairs, macro_b, macro_p, groups, series_b, series_p = [], [], [], [], [], []
    for k in range(seeds):
        params = Params(households=households, months=months, seed=1 + k, shock=shock, shock_month=shock_month)
        b, p = _run_pair(params, levers)
        pb, pp = b.household_panel(), p.household_panel()
        pairs.append((pb, pp))
        macro_b.append(_macro(b))
        macro_p.append(_macro(p))
        groups.append(_groups(pb, pp))
        series_b.append(b.history)
        series_p.append(p.history)
        sfc = max(max(b.history["sfc_error"]), max(p.history["sfc_error"]))
        if k == 0:
            sfc_max = sfc
        sfc_max = max(sfc_max, sfc)
    keys = macro_b[0].keys()
    macro = {k: {"base": _q([m[k] for m in macro_b]), "policy": _q([m[k] for m in macro_p]),
                 "diff": _q([mp[k] - mb[k] for mb, mp in zip(macro_b, macro_p)])} for k in keys}
    show = ["unemployment", "inflation", "real_wage", "real_gdp", "debt_gdp", "homeownership", "_rent_paid",
            "price_to_income", "house_price_real", "gini_income", "_public_housing"]
    series = {k: {"base": _bands([s[k] for s in series_b]), "policy": _bands([s[k] for s in series_p])}
              for k in show}
    grp = {}
    for name in groups[0]:
        grp[name] = [{f: _q([g[name][i][f] for g in groups]) for f in ("disp", "after_housing", "wealth")}
                     | {"n": int(np.mean([g[name][i]["n"] for g in groups]))}
                     for i in range(len(groups[0][name]))]
    return {"levers": levers, "shock": shock, "shock_month": shock_month, "months": months,
            "households": households, "seeds": seeds, "macro": macro, "series": series, "groups": grp,
            "sfc_max_error": float(sfc_max), "_pairs": pairs}


def _bands(runs: list[list[float]]) -> dict:
    arr = np.asarray(runs)
    return {q: np.percentile(arr, int(q[1:]), axis=0).round(5).tolist() for q in ("p10", "p50", "p90")}


def public(sim: dict) -> dict:
    return {k: v for k, v in sim.items() if not k.startswith("_")}


# ---------------------------------------------------------- «¿Y a mí?»
def household(sim: dict, age: float, income: float, tenure: str = "renter", savings: float = 0.0,
              years: int = 5, region_factor: float = 1.0, k: int = 60) -> dict:
    """Busca los k hogares simulados más parecidos (edad, renta, ahorro y tenencia al empezar
    la medida) y compara sus resultados con y sin ella."""
    if tenure not in ("renter", "mortgage", "outright"):
        raise ValueError("tenure debe ser renter, mortgage u outright")
    years = int(max(1, min(years, sim["months"] // 12)))
    horizon = sim["months"] / 12
    B = {key: np.concatenate([b[key] for b, _ in sim["_pairs"]]) for key in sim["_pairs"][0][0] if key != "months"}
    P = {key: np.concatenate([p[key] for _, p in sim["_pairs"]]) for key in sim["_pairs"][0][1] if key != "months"}
    seed_of = np.concatenate([np.full(len(b["age"]), i) for i, (b, _) in enumerate(sim["_pairs"])])
    ten = np.where(B["renter"], "renter", np.where(B["mortgage"], "mortgage", "outright"))
    ok = ~B["dead"] & (B["age"] + horizon < 85)
    d2 = (((B["age"] - age) / 6) ** 2
          + ((np.log(np.maximum(B["income"], 200)) - np.log(max(income, 200))) / 0.04) ** 2
          + ((np.log1p(np.maximum(B["fin"], 0) / 3000) - np.log1p(max(savings, 0) / 3000)) / 1.2) ** 2
          + np.where(ten == tenure, 0.0, 25.0))
    d2 = np.where(ok, d2, np.inf)
    idx = np.argsort(d2)[:k]
    idx = idx[np.isfinite(d2[idx])]
    if not len(idx):
        raise ValueError("No hay hogares simulados parecidos")
    rf = float(region_factor)

    def outcome(X):
        housing = X["housing"][idx] * rf
        return {"disp": X["disp"][idx], "housing": housing,
                "burden": housing / np.maximum(X["disp"][idx], 1.0),
                "after_housing": X["disp"][idx] - housing,
                "wealth": X["wealth_end"][idx], "pension": X["pension"][idx], "unemp": X["unemp"][idx]}

    ob, op = outcome(B), outcome(P)
    res = {key: {"base": _q(ob[key]), "policy": _q(op[key]), "diff": _q(op[key] - ob[key])} for key in ob}
    # probabilidad de comprar vivienda en N años (inquilinos al empezar)
    renters = B["renter"][idx]
    if renters.sum() >= 5:
        rng = np.random.default_rng(0)
        bought_b = ((B["own_month"][idx] >= 0) & (B["own_month"][idx] < 12 * years)).astype(float)
        bought_p = ((P["own_month"][idx] >= 0) & (P["own_month"][idx] < 12 * years)).astype(float)
        r = np.flatnonzero(renters)
        boots = rng.choice(r, (400, len(r)))
        res["buy"] = {"base": {"p50": float(bought_b[r].mean()), **_band(bought_b[boots].mean(1))},
                      "policy": {"p50": float(bought_p[r].mean()), **_band(bought_p[boots].mean(1))},
                      "diff": {"p50": float(bought_p[r].mean() - bought_b[r].mean()),
                               **_band((bought_p[boots] - bought_b[boots]).mean(1))}}
    else:
        res["buy"] = None
    return {
        "matched": {"n": int(len(idx)), "seeds": int(len(np.unique(seed_of[idx]))),
                    "age": _q(B["age"][idx]), "income": _q(B["income"][idx]), "savings": _q(B["fin"][idx]),
                    "same_tenure": float((ten[idx] == tenure).mean())},
        "years": years, "region_factor": rf, "retired_by_end": float(P["retired_end"][idx].mean()),
        "outcomes": res,
    }


def _band(x) -> dict:
    v = np.percentile(x, [10, 90])
    return {"p10": float(v[0]), "p90": float(v[1])}


# ----------------------------------------------------------- robustez
ROBUST_KEYS = ["unemployment:mean", "real_wage:last", "debt_gdp:last", "homeownership:last", "_rent_paid:last"]


def robustness(levers: dict, shock: str = "none", shock_month: int = 24, months: int = 120,
               households: int = 1500, seeds: int = 3) -> dict:
    """Repite la medida con cada supuesto clave en el extremo bajo y alto de su rango.
    Si el resultado cambia mucho, la conclusión depende de ese supuesto."""
    levers = clean_levers(levers)
    active = [LEVERS[k]["elasticity"] for k in levers if k in LEVERS and LEVERS[k].get("elasticity")]
    active = list(dict.fromkeys(active))
    out = {}
    base_cache = {}
    for ela in active:
        spec = ELASTICITIES[ela]
        row = {}
        for end in ("lo", "hi"):
            diffs = []
            for k in range(seeds):
                params = Params(households=households, months=months, seed=1 + k, shock=shock, shock_month=shock_month)
                if k not in base_cache:
                    b = Model(Regime(), params, track=True, crn=True)
                    for _ in range(months):
                        b.step()
                    base_cache[k] = _macro(b)
                pol = Model(Regime(), params, policy={**levers, ela: spec[end]}, track=True, crn=True)
                for _ in range(months):
                    pol.step()
                mp = _macro(pol)
                diffs.append({key: mp[key] - base_cache[k][key] for key in ROBUST_KEYS})
            row[end] = {key: float(np.median([d[key] for d in diffs])) for key in ROBUST_KEYS}
        out[ela] = {"lo_value": spec["lo"], "hi_value": spec["hi"], **row}
    return {"levers": levers, "keys": ROBUST_KEYS, "elasticities": out, "seeds": seeds}


# ------------------------------------------------- sensibilidad (Sobol)
# Supuestos estructurales que afectan a cualquier medida, además de los de cada palanca
COMMON_FACTORS = {
    "phillips": ("Pendiente de la curva de Phillips", 0.3, 0.9),
    "hoarding": ("Sensibilidad del consumo al tipo real", 2.0, 6.0),
    "construction_rate": ("Respuesta de la construcción al precio", 0.0005, 0.002),
}
SENS_OUTPUTS = ["unemployment:mean", "real_wage:last", "debt_gdp:last", "_rent_paid:last",
                "homeownership:last", "disp_bottom50", "disp_top10"]


def preset_factors(levers: dict) -> dict:
    out = {}
    for k in levers:
        e = LEVERS.get(k, {}).get("elasticity")
        if e:
            out[e] = (ELASTICITIES[e]["label"], ELASTICITIES[e]["lo"], ELASTICITIES[e]["hi"])
    return {**out, **COMMON_FACTORS}


def _pair_outputs(args) -> dict:
    """Diferencias con y sin la medida para un juego de supuestos (misma semilla)."""
    levers, assumptions, seed, households, months = args
    struct = {k: v for k, v in assumptions.items() if k in COMMON_FACTORS}
    behav = {k: v for k, v in assumptions.items() if k not in COMMON_FACTORS}
    params = replace(Params(households=households, months=months, seed=seed), **struct)
    b, p = _run_pair(params, {**levers, **behav})
    mb, mp = _macro(b), _macro(p)
    out = {k: mp[k] - mb[k] for k in SENS_OUTPUTS if k in mb}
    pb, pp = b.household_panel(), p.household_panel()
    alive = ~pb["dead"]
    rank = pb["income"].argsort().argsort() / len(pb["income"])
    for name, m in (("disp_bottom50", alive & (rank < 0.5)), ("disp_top10", alive & (rank >= 0.9))):
        out[name] = float((pp["disp"][m] - pb["disp"][m]).sum() / max(1.0, pb["disp"][m].sum()))
    return out


def sobol(levers: dict, n: int = 32, households: int = 1200, months: int = 120, seed: int = 0,
          workers: int | None = None) -> dict:
    """Índices de Sobol (Saltelli / Jansen) de los supuestos sobre el efecto de una medida."""
    from concurrent.futures import ProcessPoolExecutor

    from .sensitivity import corrected
    levers = clean_levers(levers)
    factors = preset_factors(levers)
    names = list(factors)
    d = len(names)
    lo = np.array([factors[k][1] for k in names])
    hi = np.array([factors[k][2] for k in names])
    rng = np.random.default_rng(seed)
    A = lo + rng.random((n, d)) * (hi - lo)
    B = lo + rng.random((n, d)) * (hi - lo)
    rows = np.vstack([A, B] + [np.where(np.arange(d) == i, B, A) for i in range(d)])
    jobs = [(levers, dict(zip(names, map(float, r))), 1 + j % n, households, months) for j, r in enumerate(rows)]
    mid = dict(zip(names, map(float, (lo + hi) / 2)))
    noise_jobs = [(levers, mid, 1000 + j, households, months) for j in range(n)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_pair_outputs, jobs, chunksize=4))
        noise = list(ex.map(_pair_outputs, noise_jobs, chunksize=4))
    out = {}
    for key in SENS_OUTPUTS:
        y = np.array([r[key] for r in res])
        fA, fB = y[:n], y[n:2 * n]
        var = float(np.var(np.concatenate([fA, fB])))
        s1, st = [], []
        for i in range(d):
            fAB = y[(2 + i) * n:(3 + i) * n]
            if var < 1e-14:
                s1.append(0.0)
                st.append(0.0)
                continue
            s1.append(float(np.mean(fB * (fAB - fA)) / var))
            st.append(float(0.5 * np.mean((fA - fAB) ** 2) / var))
        noise_share = min(1.0, float(np.var([r[key] for r in noise]) / var)) if var > 1e-14 else 0.0
        both = np.concatenate([fA, fB])
        out[key] = {"S1": s1, "ST": st, "mean": float(both.mean()), "std": float(both.std()),
                    "p10": float(np.percentile(both, 10)), "p90": float(np.percentile(both, 90)),
                    "noise_share": noise_share, **corrected(s1, st, noise_share)}
    return {"levers": levers, "n": n, "runs": 2 * (len(rows) + n),
            "factors": [{"key": k, "label": factors[k][0], "lo": factors[k][1], "hi": factors[k][2]} for k in names],
            "outputs": out}
