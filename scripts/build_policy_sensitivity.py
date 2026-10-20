"""Sensibilidad de cada medida predefinida a sus supuestos clave → data/policy_sensitivity.json

Para cada medida del laboratorio de políticas varían a la vez las elasticidades de sus
palancas y tres supuestos estructurales (Phillips, consumo, construcción) y se
descompone la varianza de su efecto (con la medida − sin ella) con índices de Sobol.

    python scripts/build_policy_sensitivity.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from msl.policy import PRESETS, SENS_OUTPUTS, sobol  # noqa: E402

N = 32


def main():
    t0 = time.time()
    out = {"generated": time.strftime("%Y-%m-%d %H:%M"), "n": N, "outputs": SENS_OUTPUTS, "presets": {}}
    for key, preset in PRESETS.items():
        res = sobol(preset["levers"], n=N)
        out["presets"][key] = res
        print(f"{key:18s} {res['runs']} simulaciones · {time.time() - t0:.0f} s", flush=True)
    path = ROOT / "data" / "policy_sensitivity.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
