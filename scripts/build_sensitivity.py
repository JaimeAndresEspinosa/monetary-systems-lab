"""Índices de Sobol para varios sistemas monetarios → data/sensitivity.json

    python scripts/build_sensitivity.py --n 64
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from msl import Params, Regime  # noqa: E402
from msl.sensitivity import sobol  # noqa: E402

REGIMES = [
    "discretionary|banks|fractional",
    "gold|banks|fractional",
    "fixed_supply|miners|fractional",
    "rule_2pct|dividend|full_reserve",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=64)
    ap.add_argument("--households", type=int, default=1000)
    args = ap.parse_args()
    base = Params(households=args.households)
    out = {"generated": time.strftime("%Y-%m-%d %H:%M"), "households": args.households, "results": []}
    for key in REGIMES:
        t0 = time.time()
        res = sobol(Regime.from_key(key), base, n=args.n)
        out["results"].append(res)
        print(f"{key:36s} {res['runs']} simulaciones en {time.time() - t0:.0f} s", flush=True)
    path = ROOT / "data" / "sensitivity.json"
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"-> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
