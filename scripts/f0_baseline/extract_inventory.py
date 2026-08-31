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
    result.pop("markdown", None)  # se regenera a continuación
    result["markdown"] = inv.to_markdown(result.pop("rows", []) and __import__("dataclasses").asdict if False else [], result["elapsed_ms"])

    out_dir = ROOT / "reports" / "f0_baseline"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "window-functions.json"
    md_path = out_dir / "window-functions.md"

    # Re-generar filas + markdown de forma limpia
    rows = inv.extract()
    elapsed = result["elapsed_ms"]
    md = inv.to_markdown(rows, elapsed)

    payload = {
        "html": str(proto),
        "total": len(rows),
        "elapsed_ms": elapsed,
        "rows": [r.__dict__ for r in rows],
        "markdown": md,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(md, encoding="utf-8")

    print(f"[OK] Inventario: {len(rows)} funciones en {elapsed} ms")
    print(f"     → {json_path}")
    print(f"     → {md_path}")
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    raise SystemExit(main(arg))
