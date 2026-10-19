"""Simula todas las combinaciones de régimen monetario y guarda el resultado
en data/grid.json, que es lo que muestra el Explorador de la web.

    python scripts/build_grid.py            # 10 semillas por combinación
    python scripts/build_grid.py --seeds 20
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from msl import Params, grid  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()

    params = Params()
    t0 = time.time()
    cells = grid(params, seeds=args.seeds, workers=args.workers)
    out = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "seeds": args.seeds,
        "params": params.to_dict(),
        "cells": cells,
    }
    path = ROOT / "data" / "grid.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    worst = max(c["sfc_max_error"] for c in cells)
    print(f"{len(cells)} combinaciones x {args.seeds} semillas en {time.time() - t0:.0f} s "
          f"· error contable máximo {worst:.1e} -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
