"""
CLI: HU_01 — Inventario de funciones `window.*` del prototipo.

Uso:
    python -m scripts.f0_baseline.extract_inventory

Genera:
    reports/f0_baseline/window-functions.json
    reports/f0_baseline/window-functions.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.f0_baseline import WindowInventory  # noqa: E402


def main(html: str | None = None) -> int:
    proto = Path(html) if html else ROOT / "prototypes" / "f0_baseline" / "demo.html"
    if not proto.exists():
        print(f"[WARN] {proto} no existe — generando prototipo…")
        from app.f0_baseline.prototype_generator import PrototypeGenerator
        PrototypeGenerator(output_path=proto).write()

    inv = WindowInventory.from_html(proto)
    result = inv.run()

    out_dir = ROOT / "reports" / "f0_baseline"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "window-functions.json"
    md_path = out_dir / "window-functions.md"

    # `inv.run()` ya produce el payload completo con `rows`, `markdown`,
    # `total` y `elapsed_ms`. Lo escribimos tal cual al disco.
    json_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md_path.write_text(result["markdown"], encoding="utf-8")

    print(f"[OK] Inventario: {result['total']} funciones en {result['elapsed_ms']} ms")
    print(f"     → {json_path}")
    print(f"     → {md_path}")
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    raise SystemExit(main(arg))
