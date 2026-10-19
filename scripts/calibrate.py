"""Calibración por el método de los momentos simulados (SMM) → data/calibration.json

Busca los parámetros con los que el sistema actual reproduce mejor los momentos
de España (Eurostat y BCE, 2015–2025) y los hechos estilizados (Okun, Phillips).
Descenso por coordenadas: en cada ronda prueba, para cada parámetro, todos sus
valores candidatos con los demás fijos y se queda con el mejor.

    python scripts/fetch_data.py      # primero, los datos reales
    python scripts/calibrate.py
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from msl import Params  # noqa: E402
from msl.validation import MOMENTS, distance, model_moments, real_moments  # noqa: E402

GRID = {
    "natural_unemployment": [0.10, 0.12, 0.14, 0.16],
    "spirits_sd": [0.0, 0.02, 0.035, 0.05],
    "debt_to_gdp0": [1.0, 1.1, 1.2, 1.3],
    "gov_spending_share": [0.17, 0.18, 0.19, 0.20],
    "firm_leverage": [0.25, 0.4, 0.55, 0.7],
    "mortgage_prob": [0.55, 0.75, 0.95],
    "wealth_sigma": [1.3, 1.6, 1.9, 2.2],
}
EVAL = dict(households=1200, months=240)
SEEDS = 3


def objective(model: dict, real: dict) -> float:
    d = distance(model, real)
    # hechos estilizados: el signo y la fuerza de Okun y Phillips
    d += 0.5 * ((model["okun"] - real["okun"]) / 0.3) ** 2
    d += 0.3 * ((model["phillips"] - real["phillips"]) / 0.3) ** 2
    return d


def _eval(params_dict: dict) -> dict:
    return model_moments(Params(**params_dict), seeds=SEEDS)


def main():
    real = real_moments()
    current = {**Params().to_dict(), **EVAL}
    before = _eval(current)
    best_d = objective(before, real)
    print(f"inicio: distancia {best_d:.3f}", flush=True)
    history = [{"round": 0, "distance": best_d}]
    with ProcessPoolExecutor() as ex:
        for rnd in (1, 2):
            for key, values in GRID.items():
                cands = [{**current, key: v} for v in values]
                moms = list(ex.map(_eval, cands))
                scores = [objective(m, real) for m in moms]
                j = min(range(len(values)), key=scores.__getitem__)
                if scores[j] < best_d:
                    current, best_d = cands[j], scores[j]
                print(f"ronda {rnd} · {key:22s} -> {current[key]}  (distancia {best_d:.3f})", flush=True)
            history.append({"round": rnd, "distance": best_d})
    after = model_moments(Params(**current), seeds=6)
    calibrated = {k: current[k] for k in GRID}
    out = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "method": "SMM, descenso por coordenadas (2 rondas)",
        "window": "2015–2025",
        "real": real,
        "before": before,
        "after": after,
        "params_before": {k: Params().to_dict()[k] for k in GRID},
        "params": calibrated,
        "distance_before": objective(before, real),
        "distance_after": objective(after, real),
        "history": history,
        "moments": MOMENTS,
    }
    path = ROOT / "data" / "calibration.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("parámetros calibrados:", calibrated)
    print(f"distancia {out['distance_before']:.3f} -> {out['distance_after']:.3f}")


if __name__ == "__main__":
    main()
