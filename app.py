"""API y web de Monetary Systems Lab.

    uvicorn app:app --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from msl import CATALOG, Params, Regime, monte_carlo
from msl.config import LIMITS
from msl.economy import INSTRUMENTS, SECTOR_LABELS
from msl.metrics import METRICS, SUMMARY

ROOT = Path(__file__).parent
GRID = ROOT / "data" / "grid.json"

app = FastAPI(title="Monetary Systems Lab", version="1.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def revalidate_static(request, call_next):
    # el navegador comprueba el ETag en cada carga: tras un despliegue nunca usa JS/CSS viejos
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response

# Una simulación a la vez por proceso: el plan gratuito de Render tiene 1 CPU
_sem = asyncio.Semaphore(int(os.getenv("MSL_CONCURRENCY", "1")))


class SimRequest(BaseModel):
    issuance: str = "discretionary"
    channel: str = "banks"
    banking: str = "fractional"
    seeds: int = Field(8, ge=LIMITS["seeds"][0], le=LIMITS["seeds"][1])
    params: dict = {}


def _clamp_params(raw: dict) -> Params:
    p = Params.from_dict(raw)
    for key in ("households", "months"):
        lo, hi = LIMITS[key]
        setattr(p, key, max(lo, min(hi, getattr(p, key))))
    return p


@lru_cache(maxsize=256)
def _cached(regime_key: str, params_json: str, seeds: int) -> str:
    params = Params.from_dict(json.loads(params_json))
    return json.dumps(monte_carlo(Regime.from_key(regime_key), params, seeds))


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/catalog")
def catalog():
    return {
        "dimensions": CATALOG,
        "metrics": METRICS,
        "summary": [f"{k}:{how}" for k, how in SUMMARY],
        "params": Params().to_dict(),
        "limits": LIMITS,
        "sectors": SECTOR_LABELS,
        "instruments": INSTRUMENTS,
        "regimes": len(Regime.all()),
    }


@app.post("/api/simulate")
async def simulate(req: SimRequest):
    try:
        regime = Regime(req.issuance, req.channel, req.banking)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    params = _clamp_params(req.params)
    key = json.dumps(params.to_dict(), sort_keys=True)
    async with _sem:
        out = await asyncio.to_thread(_cached, regime.key, key, req.seeds)
    return json.loads(out)


@app.get("/api/grid")
def grid():
    if not GRID.exists():
        raise HTTPException(503, "El explorador aún no está calculado: python scripts/build_grid.py")
    return json.loads(GRID.read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    return {"ok": True, "grid": GRID.exists()}
