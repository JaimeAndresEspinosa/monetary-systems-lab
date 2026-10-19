"""Experimentos: Monte Carlo de un régimen y barrido de todas las combinaciones."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace

import numpy as np

from .config import Params, Regime
from .metrics import summarize
from .model import run


def _bands(runs: list[list[float]]) -> dict[str, list[float]]:
    arr = np.asarray(runs)
    return {
        "p10": np.percentile(arr, 10, axis=0).round(6).tolist(),
        "p50": np.percentile(arr, 50, axis=0).round(6).tolist(),
        "p90": np.percentile(arr, 90, axis=0).round(6).tolist(),
    }


def monte_carlo(regime: Regime, params: Params, seeds: int = 10) -> dict:
    """Repite la simulación con distinta aleatoriedad y devuelve medianas y bandas 10–90 %."""
    results = [run(regime, replace(params, seed=params.seed + k)) for k in range(seeds)]
    keys = results[0]["series"].keys()
    series = {k: _bands([r["series"][k] for r in results]) for k in keys}
    summaries = [summarize(r["series"]) for r in results]
    summary = {k: {"p10": float(np.percentile([s[k] for s in summaries], 10)),
                   "p50": float(np.median([s[k] for s in summaries])),
                   "p90": float(np.percentile([s[k] for s in summaries], 90))}
               for k in summaries[0]}
    first = results[0]
    return {
        "regime": {"key": regime.key, "label": regime.label, **regime.__dict__},
        "params": params.to_dict(),
        "seeds": seeds,
        "series": series,
        "summary": summary,
        "wealth_share_start": np.median([r["wealth_share_start"] for r in results], axis=0).tolist(),
        "wealth_share_end": np.median([r["wealth_share_end"] for r in results], axis=0).tolist(),
        "new_money_deciles": np.median([r["new_money_deciles"] for r in results], axis=0).tolist(),
        "new_money_to": {k: float(np.median([r["new_money_to"][k] for r in results]))
                         for k in first["new_money_to"]},
        "balance_sheet": first["balance_sheet"],
        "flows": first["flows"],
        "events": first["events"],
        "sfc_max_error": float(max(r["sfc_max_error"] for r in results)),
    }


def _grid_cell(args):
    regime_key, params, seeds = args
    r = Regime.from_key(regime_key)
    res = monte_carlo(r, params, seeds)
    # versión compacta: el explorador solo necesita la mediana
    return {"key": r.key, **r.__dict__,
            "summary": {k: round(v["p50"], 6) for k, v in res["summary"].items()},
            "wealth_share_start": [round(x, 5) for x in res["wealth_share_start"]],
            "wealth_share_end": [round(x, 5) for x in res["wealth_share_end"]],
            "sfc_max_error": res["sfc_max_error"]}


def grid(params: Params, seeds: int = 8, workers: int | None = None,
         regimes: list[Regime] | None = None) -> list[dict]:
    """Simula todas las combinaciones de piezas del régimen monetario."""
    jobs = [(r.key, params, seeds) for r in (regimes or Regime.all())]
    if workers == 1:
        return [_grid_cell(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_grid_cell, jobs, chunksize=4))
