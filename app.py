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
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from msl import CATALOG, Params, Regime, monte_carlo
from msl import policy as pol
from msl.config import CORE, LIMITS, SHOCKS
from msl.economy import INSTRUMENTS, SECTOR_LABELS
from msl.metrics import METRICS, SUMMARY

ROOT = Path(__file__).parent
DATA = ROOT / "data"
CONTRACTS = ROOT / "contracts"

app = FastAPI(title="Monetary Systems Lab", version="2.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

# Una simulación a la vez por proceso: el plan gratuito de Render tiene 1 CPU
_sem = asyncio.Semaphore(int(os.getenv("MSL_CONCURRENCY", "1")))


@app.middleware("http")
async def revalidate_static(request, call_next):
    # el navegador comprueba el ETag en cada carga: tras un despliegue nunca usa JS/CSS viejos
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


class SimRequest(BaseModel):
    issuance: str = "discretionary"
    channel: str = "banks"
    banking: str = "fractional"
    money: str = "normal"
    privacy: str = "mixed"
    fiscal: str = "free"
    seeds: int = Field(8, ge=LIMITS["seeds"][0], le=LIMITS["seeds"][1])
    params: dict = {}


def _clamp_params(raw: dict) -> Params:
    try:
        p = Params.from_dict(raw)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    for key in ("households", "months"):
        lo, hi = LIMITS[key]
        setattr(p, key, max(lo, min(hi, getattr(p, key))))
    p.shock_month = max(0, min(p.months - 1, p.shock_month))
    return p


@lru_cache(maxsize=256)
def _cached(regime_key: str, params_json: str, seeds: int) -> str:
    params = Params.from_dict(json.loads(params_json))
    return json.dumps(monte_carlo(Regime.from_key(regime_key), params, seeds))


@lru_cache(maxsize=8)
def _json(name: str) -> dict | None:
    path = DATA / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _need(name: str) -> dict:
    data = _json(name)
    if data is None:
        raise HTTPException(503, f"Falta data/{name}. Ver README (scripts/).")
    return data


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/catalog")
def catalog():
    return {
        "dimensions": CATALOG,
        "core": CORE,
        "shocks": SHOCKS,
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
        regime = Regime(req.issuance, req.channel, req.banking, req.money, req.privacy, req.fiscal)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    params = _clamp_params(req.params)
    key = json.dumps(params.to_dict(), sort_keys=True)
    async with _sem:
        out = await asyncio.to_thread(_cached, regime.key, key, req.seeds)
    return json.loads(out)


@app.get("/api/grid")
def grid(scenario: str = "none"):
    g = _need("grid.json")
    if scenario not in g["scenarios"]:
        raise HTTPException(404, f"Escenario sin calcular: {scenario}")
    return {"generated": g["generated"], "seeds": g["seeds"], "scenario": scenario,
            "scenarios": list(g["scenarios"]), "cells": g["scenarios"][scenario]}


@app.get("/api/sensitivity")
def sensitivity():
    return _need("sensitivity.json")


@app.get("/api/validation")
def validation():
    return {"calibration": _need("calibration.json"), "spain": _need("spain.json")}


@app.get("/api/onchain")
def onchain():
    return _need("onchain.json")


CONTRACT_INFO = {
    "HalvingToken": "Oferta fija tipo Bitcoin: emisión que se reduce a la mitad cada 4 años y se reparte entre validadores.",
    "AlgorithmicDividend": "Algoritmo del 2 %: la oferta crece un porcentaje fijo y el dinero nuevo se reparte a partes iguales entre ciudadanos.",
    "DemurrageToken": "Dinero que se oxida: los saldos ociosos pierden un 0,5 % al mes, que va al Tesoro.",
    "ProgrammableCBDC": "Euro digital: límite de 3.000 €, cascada al banco, estímulos que caducan y congelación de cuentas.",
    "TokenizedMortgage": "Hipoteca como contrato: la vivienda (NFT) queda en garantía hasta la última cuota.",
    "BaseToken": "ERC-20 mínimo, aritmética de punto fijo y control de acceso que usan todos los demás.",
}


@app.get("/api/contracts")
def contracts():
    deployments = CONTRACTS / "deployments.json"
    return {
        "demo": _json("contracts_demo.json"),
        "deployments": json.loads(deployments.read_text(encoding="utf-8")) if deployments.exists() else None,
        "sources": [{"name": n, "desc": d, "lines": len((CONTRACTS / f"{n}.sol").read_text(encoding="utf-8").splitlines())}
                    for n, d in CONTRACT_INFO.items() if (CONTRACTS / f"{n}.sol").exists()],
    }


@app.get("/api/contracts/{name}", response_class=PlainTextResponse)
def contract_source(name: str):
    if name not in CONTRACT_INFO:
        raise HTTPException(404, "Contrato desconocido")
    return (CONTRACTS / f"{name}.sol").read_text(encoding="utf-8")


# ------------------------------------------------------ laboratorio de políticas
class PolicyRequest(BaseModel):
    levers: dict = {}
    shock: str = "none"
    shock_month: int = Field(24, ge=0, le=180)
    months: int = Field(120, ge=60, le=180)
    households: int = Field(1500, ge=500, le=3000)
    seeds: int = Field(4, ge=2, le=12)
    robustness: bool = False


class HouseholdRequest(PolicyRequest):
    age: float = Field(..., ge=18, le=80)
    income: float = Field(..., ge=0, le=100_000)
    tenure: str = "renter"
    savings: float = Field(0, ge=0, le=10_000_000)
    years: int = Field(5, ge=1, le=15)
    region_factor: float = Field(1.0, ge=0.3, le=3.0)


def _policy_key(req: PolicyRequest) -> str:
    if req.shock not in SHOCKS:
        raise HTTPException(400, f"Crisis desconocida: {req.shock!r}")
    try:
        levers = pol.clean_levers(req.levers)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return json.dumps({"levers": levers, "shock": req.shock, "shock_month": min(req.shock_month, req.months - 1),
                       "months": req.months, "households": req.households, "seeds": req.seeds}, sort_keys=True)


@lru_cache(maxsize=12)
def _policy_sim(key: str) -> dict:
    return pol.simulate(**json.loads(key))


@lru_cache(maxsize=32)
def _policy_robust(key: str) -> dict:
    args = json.loads(key)
    return pol.robustness(args["levers"], shock=args["shock"], shock_month=args["shock_month"], months=args["months"])


@app.get("/api/policy/catalog")
def policy_catalog():
    return {**pol.catalog(), "sensitivity": _json("policy_sensitivity.json")}


@app.post("/api/policy/simulate")
async def policy_simulate(req: PolicyRequest):
    key = _policy_key(req)
    async with _sem:
        sim = await asyncio.to_thread(_policy_sim, key)
        out = pol.public(sim)
        if req.robustness:
            out["robustness"] = await asyncio.to_thread(_policy_robust, key)
    return out


@app.post("/api/policy/household")
async def policy_household(req: HouseholdRequest):
    key = _policy_key(req)
    async with _sem:
        sim = await asyncio.to_thread(_policy_sim, key)
    try:
        return pol.household(sim, req.age, req.income, req.tenure, req.savings, req.years, req.region_factor)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/health")
def health():
    return {"ok": True, **{n: (DATA / n).exists() for n in
                           ("grid.json", "sensitivity.json", "calibration.json", "onchain.json",
                            "policy_sensitivity.json")}}
