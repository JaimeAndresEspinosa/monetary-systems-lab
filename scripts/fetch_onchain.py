"""Datos on-chain → data/onchain.json

  · Bitcoin: altura y oferta reales (mempool.space, blockchain.info) frente a la
    oferta que implica el protocolo (50 BTC por bloque, halving cada 210.000 bloques).
  · Stablecoins: circulación total y por moneda (DefiLlama).

La inflación anual actual de Bitcoin calibra la regla `fixed_supply` del simulador.

    python scripts/fetch_onchain.py
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.request
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover
    CTX = ssl.create_default_context()

HALVING = 210_000
BLOCKS_PER_YEAR = 6 * 24 * 365
SAT = 100_000_000


def get(url: str, as_json: bool = True):
    req = urllib.request.Request(url, headers={"User-Agent": "MonetarySystemsLab/1.0"})
    with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
        body = r.read()
    return json.loads(body) if as_json else body.decode().strip()


def reward_sats(height: int) -> int:
    halvings = height // HALVING
    return (50 * SAT) >> halvings if halvings < 64 else 0


def protocol_supply(height: int) -> int:
    """Satoshis emitidos hasta el bloque `height` incluido, según las reglas del protocolo."""
    total, h = 0, 0
    while h <= height:
        end = min(height, (h // HALVING + 1) * HALVING - 1)
        total += reward_sats(h) * (end - h + 1)
        h = end + 1
    return total


def bitcoin() -> dict:
    height = int(get("https://mempool.space/api/blocks/tip/height", as_json=False))
    reported = int(get("https://blockchain.info/q/totalbc", as_json=False))
    reward = reward_sats(height)
    supply_p = protocol_supply(height)
    schedule = []
    for year in range(2009, 2141, 1):
        h = (year - 2009) * BLOCKS_PER_YEAR
        s0, s1 = protocol_supply(h), protocol_supply(h + BLOCKS_PER_YEAR)
        schedule.append({"year": year, "supply": s1 / SAT,
                         "inflation": (s1 - s0) / s0 if s0 else None})
    next_halving = (height // HALVING + 1) * HALVING
    return {
        "height": height,
        "supply_reported": reported / SAT,
        "supply_protocol": supply_p / SAT,
        "max_supply": protocol_supply(64 * HALVING) / SAT,
        "reward": reward / SAT,
        "annual_inflation": reward * BLOCKS_PER_YEAR / supply_p,
        "next_halving_height": next_halving,
        "blocks_to_halving": next_halving - height,
        "schedule": schedule,
        "sources": ["https://mempool.space/api/blocks/tip/height", "https://blockchain.info/q/totalbc"],
    }


def stablecoins() -> dict:
    hist = get("https://stablecoins.llama.fi/stablecoincharts/all")
    monthly: "OrderedDict[str, float]" = OrderedDict()
    for row in hist:
        month = datetime.fromtimestamp(int(row["date"]), tz=timezone.utc).strftime("%Y-%m")
        monthly[month] = row["totalCirculatingUSD"].get("peggedUSD", 0.0)  # último dato del mes
    assets = get("https://stablecoins.llama.fi/stablecoins?includePrices=false")["peggedAssets"]

    def circ(a):
        c = a.get("circulating") or {}
        return float(c.get(a.get("pegType"), 0) or 0)

    top = sorted(assets, key=lambda a: -circ(a) if a.get("pegType") == "peggedUSD" else 0)[:6]
    by_peg: dict[str, float] = {}
    for a in assets:
        by_peg[a.get("pegType", "?")] = by_peg.get(a.get("pegType", "?"), 0.0) + circ(a)
    eur = sorted([a for a in assets if a.get("pegType") == "peggedEUR"], key=lambda a: -circ(a))[:5]
    return {
        "monthly_usd": [{"month": k, "usd": v} for k, v in monthly.items()],
        "top_usd": [{"symbol": a["symbol"], "name": a["name"], "circulating": circ(a)} for a in top],
        "top_eur": [{"symbol": a["symbol"], "name": a["name"], "circulating": circ(a)} for a in eur],
        "by_peg": by_peg,
        "sources": ["https://stablecoins.llama.fi/stablecoincharts/all", "https://stablecoins.llama.fi/stablecoins"],
    }


def main():
    out = {"fetched": time.strftime("%Y-%m-%d"), "bitcoin": bitcoin(), "stablecoins": stablecoins()}
    path = ROOT / "data" / "onchain.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    b = out["bitcoin"]
    print(f"Bitcoin: bloque {b['height']:,}, oferta real {b['supply_reported']:,.2f} BTC, "
          f"protocolo {b['supply_protocol']:,.2f} BTC, inflación anual {b['annual_inflation'] * 100:.2f} %")
    s = out["stablecoins"]
    print(f"Stablecoins: {s['monthly_usd'][-1]['usd'] / 1e9:,.1f} mil M$ · "
          f"{len(s['monthly_usd'])} meses · EUR {s['by_peg'].get('peggedEUR', 0) / 1e6:,.0f} M€")
    print(f"-> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
