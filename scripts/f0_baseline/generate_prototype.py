"""
CLI: genera el prototipo HTML sintético en `prototypes/f0_baseline/demo.html`.

Uso:
    python -m scripts.f0_baseline.generate_prototype
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permitir `python scripts/f0_baseline/generate_prototype.py` desde la raíz.
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.f0_baseline.prototype_generator import PrototypeGenerator  # noqa: E402


def main() -> int:
    target = ROOT / "prototypes" / "f0_baseline" / "demo.html"
    g = PrototypeGenerator(output_path=target)
    out = g.write()
    print(f"[OK] Prototipo generado: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
