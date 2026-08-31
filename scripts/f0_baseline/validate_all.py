"""
CLI: ejecuta el pipeline completo de F0.

Pipeline:
  1) Genera el prototipo HTML si no existe.
  2) Genera el inventario de funciones `window.*` (HU_01).
  3) Genera el reporte de mapeo localStorage ↔ modelos (HU_02).
  4) Imprime el reporte de Alembic + pytest (HU_03).

Uso:
    python -m scripts.f0_baseline.validate_all
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.f0_baseline import generate_prototype, extract_inventory, build_mapping  # noqa: E402
from app.f0_baseline.hu03 import build_report, to_markdown  # noqa: E402


def main() -> int:
    print("=" * 60)
    print(" F0 — Baseline & Auditoría · Pipeline completo")
    print("=" * 60)

    print("\n[1/4] Generando prototipo HTML…")
    rc = generate_prototype.main()
    if rc != 0:
        return rc

    print("\n[2/4] HU_01 — Inventario de funciones window.* …")
    rc = extract_inventory.main()
    if rc != 0:
        return rc

    print("\n[3/4] HU_02 — Mapeo localStorage ↔ modelos SQLAlchemy …")
    rc = build_mapping.main()
    if rc != 0:
        return rc

    print("\n[4/4] HU_03 — Estado de Alembic + pytest …")
    report = build_report()
    md = to_markdown(report)
    (ROOT / "reports" / "f0_baseline").mkdir(parents=True, exist_ok=True)
    (ROOT / "reports" / "f0_baseline" / "migrations.md").write_text(md, encoding="utf-8")
    # Cache JSON para el endpoint /f0/hu03 (no requiere correr pytest en vivo).
    import json as _json
    cache = {"hu": "HU_03", "title": "Estado Alembic + pytest", "result": report}
    (ROOT / "reports" / "f0_baseline" / "migrations.json").write_text(
        _json.dumps(cache, indent=2, default=str), encoding="utf-8"
    )
    print(f"     alembic/ existe: {report['alembic_dir_exists']}")
    print(f"     alembic upgrade: {report['alembic_upgrade']}")
    print(f"     pytest collected: {report['pytest_collected']} tests")
    print(f"     pytest:          {report['pytest']}")
    print(f"     modelos cargados: {report['models_loaded']}")
    print(f"     → reports/f0_baseline/migrations.md")
    print(f"     → reports/f0_baseline/migrations.json")

    print("\n" + "=" * 60)
    print(" ✓ F0 Baseline completado (8 SP: HU_01=3 + HU_02=3 + HU_03=2)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
