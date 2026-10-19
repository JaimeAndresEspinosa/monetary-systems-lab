"""Simula todas las combinaciones de régimen monetario en cada escenario de crisis
y guarda el resultado en data/grid.json, que es lo que muestra el Explorador.

    python scripts/build_grid.py              # 576 sistemas x 5 escenarios x 5 semillas
    python scripts/build_grid.py --seeds 10 --scenarios none
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from msl import Params, Regime, grid  # noqa: E402
from msl.config import SHOCKS  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--scenarios", nargs="*", default=list(SHOCKS))
    ap.add_argument("--only", default=None,
                    help="recalcula solo las combinaciones con dim=valor (p. ej. money=demurrage) y las fusiona")
    args = ap.parse_args()

    base = Params()
    path = ROOT / "data" / "grid.json"
    out = {"generated": time.strftime("%Y-%m-%d %H:%M"), "seeds": args.seeds,
           "params": base.to_dict(), "scenarios": {}}
    if path.exists():  # conserva los escenarios que no se recalculan
        old = json.loads(path.read_text(encoding="utf-8"))
        out["scenarios"] = {k: v for k, v in old.get("scenarios", {}).items() if k not in args.scenarios}
    regimes = None
    if args.only:
        dim, val = args.only.split("=")
        regimes = [r for r in Regime.all() if getattr(r, dim) == val]
        out["scenarios"] = old["scenarios"]  # se parte del archivo existente
    for sc in args.scenarios:
        t0 = time.time()
        cells = grid(replace(base, shock=sc), seeds=args.seeds, workers=args.workers, regimes=regimes)
        if regimes is not None:
            new = {c["key"]: c for c in cells}
            cells = [new.get(c["key"], c) for c in out["scenarios"][sc]]
        out["scenarios"][sc] = cells
        worst = max(c["sfc_max_error"] for c in cells)
        print(f"{sc:11s} {len(cells)} sistemas x {args.seeds} semillas en {time.time() - t0:.0f} s, "
              f"error contable max {worst:.1e}", flush=True)
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"-> {path.relative_to(ROOT)} ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
