"""
CLI: HU_02 — Genera el reporte de mapeo localStorage ↔ modelos SQLAlchemy.

Uso:
    python -m scripts.f0_baseline.build_mapping

Genera:
    reports/f0_baseline/mapping.json
    reports/f0_baseline/mapping.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.f0_baseline import LocalStorageMapping  # noqa: E402


def main() -> int:
    out_dir = ROOT / "reports" / "f0_baseline"
    out_dir.mkdir(parents=True, exist_ok=True)
    m = LocalStorageMapping()
    report = m.run()

    json_path = out_dir / "mapping.json"
    md_path = out_dir / "mapping.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(report["markdown"], encoding="utf-8")

    stats = report["stats"]
    print(f"[OK] Mapeo: {stats['keys_in_html']} keys → {stats['models']} modelos en {stats['elapsed_ms']} ms")
    print(f"     modelos con tenant_id: {stats['models_with_tenant_id']}")
    print(f"     FKs cruzadas:         {stats['cross_foreign_keys']}")
    print(f"     cobertura:            {stats['coverage_pct']}%")
    print(f"     → {json_path}")
    print(f"     → {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
