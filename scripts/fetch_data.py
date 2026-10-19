"""Descarga las series reales de España que usa la validación → data/spain.json

Fuentes (APIs públicas, sin clave):
  · Eurostat: paro, IPCA, deuda y déficit público, crédito privado, vivienda,
    PIB real, remuneración por asalariado, Gini de la renta.
  · BCE, Distributional Wealth Accounts (DWA): riqueza neta de los hogares por grupo.

    python scripts/fetch_data.py
"""

from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover
    CTX = ssl.create_default_context()

EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
ECB = "https://data-api.ecb.europa.eu/service/data/"

SERIES = {
    "unemployment": ("une_rt_a?geo=ES&age=Y15-74&sex=T&unit=PC_ACT", "Paro (% población activa)", 0.01),
    "inflation": ("prc_hicp_aind?geo=ES&coicop=CP00&unit=RCH_A_AVG", "Inflación IPCA (%)", 0.01),
    "hicp_index": ("prc_hicp_aind?geo=ES&coicop=CP00&unit=INX_A_AVG", "IPCA (índice 2015 = 100)", 1),
    "debt_gdp": ("gov_10dd_edpt1?geo=ES&na_item=GD&sector=S13&unit=PC_GDP", "Deuda pública (% PIB)", 0.01),
    "deficit_gdp": ("gov_10dd_edpt1?geo=ES&na_item=B9&sector=S13&unit=PC_GDP", "Saldo público (% PIB)", 0.01),
    "credit_gdp": ("tipspd20?geo=ES&unit=PC_GDP", "Deuda privada consolidada (% PIB)", 0.01),
    "house_index": ("prc_hpi_a?geo=ES&purchase=TOTAL&unit=I15_A_AVG", "Precio de la vivienda (2015 = 100)", 1),
    "gdp_growth": ("nama_10_gdp?geo=ES&unit=CLV_PCH_PRE&na_item=B1GQ", "Crecimiento del PIB real (%)", 0.01),
    "comp_per_employee": ("nama_10_lp_ulc?geo=ES&na_item=D1_SAL_PER&unit=EUR", "Remuneración por asalariado (€)", 1),
    "gini_income": ("ilc_di12?geo=ES&age=TOTAL", "Gini de la renta disponible", 0.01),
}

DWA_GROUPS = ["D10", "B50", "Q1", "Q2", "Q3", "Q4", "Q5"]


def get(url: str) -> dict:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, context=CTX, timeout=90) as r:
                return json.load(r)
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(2)


def eurostat(query: str, scale: float) -> dict[str, float]:
    d = get(EUROSTAT + query)
    idx = d["dimension"]["time"]["category"]["index"]
    vals = d["value"]
    return {t: round(vals[str(i)] * scale, 6) for t, i in sorted(idx.items(), key=lambda kv: kv[1])
            if str(i) in vals}


def dwa() -> dict[str, dict[str, float]]:
    """Riqueza neta de los hogares por grupo (fin de año, último trimestre disponible)."""
    out = {}
    for g in DWA_GROUPS:
        d = get(f"{ECB}DWA/Q.ES.S14.N.LE.NWA.{g}.EUR.S.N?format=jsondata")
        series = next(iter(d["dataSets"][0]["series"].values()))["observations"]
        periods = [v["id"] for v in d["structure"]["dimensions"]["observation"][0]["values"]]
        by_year: dict[str, float] = {}
        for k, obs in series.items():
            per = periods[int(k)]
            if obs[0] is not None:
                by_year[per[:4]] = obs[0]  # se queda con el último trimestre del año
        out[g] = by_year
    total = {y: sum(out[q][y] for q in ("Q1", "Q2", "Q3", "Q4", "Q5")) for y in out["Q1"]}
    return {
        "top10_wealth": {y: round(out["D10"][y] / total[y], 6) for y in total if y in out["D10"]},
        "bottom50_wealth": {y: round(out["B50"][y] / total[y], 6) for y in total if y in out["B50"]},
    }


def main():
    data = {"fetched": time.strftime("%Y-%m-%d"), "country": "ES", "series": {}}
    for key, (query, label, scale) in SERIES.items():
        values = eurostat(query, scale)
        data["series"][key] = {"label": label, "source": "Eurostat " + query.split("?")[0],
                               "url": EUROSTAT + query, "values": values}
        print(f"{key:18s} {len(values):3d} años  último {list(values.items())[-1]}")
    for key, values in dwa().items():
        data["series"][key] = {"label": "Cuota de la riqueza neta (" + ("10 % más rico" if key.startswith("top") else "50 % más pobre") + ")",
                               "source": "BCE Distributional Wealth Accounts",
                               "url": ECB + "DWA", "values": values}
        print(f"{key:18s} {len(values):3d} años  último {list(values.items())[-1]}")
    path = ROOT / "data" / "spain.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
