"""
WowHub V134.1 — F0 Baseline & Auditoría.

Módulo que implementa las 3 primeras HU del plan F0:

  - HU_01 (3 SP): Inventariar funciones `window.*` del prototipo V134.1
  - HU_02 (3 SP): Mapear localStorage keys a modelos SQLAlchemy existentes
  - HU_03 (2 SP): Validar Alembic + tests del proyecto

Total: 8 story points.

Estos HU NO añaden modelos nuevos: la base de datos ya está completa
(23 modelos en `app/models/`). F0 lo que hace es auditar la coherencia
entre el prototipo HTML y los modelos existentes.

Uso rápido:
    from app.f0_baseline import WindowInventory, LocalStorageMapping
    from pathlib import Path

    inv = WindowInventory.from_html(Path("prototypes/f0_baseline/demo.html"))
    rows = inv.extract()

    m = LocalStorageMapping()
    report = m.run()  # incluye JSON + Markdown
"""
from __future__ import annotations

__version__ = "1.0.0"
__phase__ = "F0"
__story_points__ = 8
__hu_covered__ = ["HU_01", "HU_02", "HU_03"]

__all__ = [
    "WindowInventory",
    "LocalStorageMapping",
    "PrototypeGenerator",
    "router",
]


def __getattr__(name: str):  # PEP 562 — lazy attribute access
    if name == "WindowInventory":
        from app.f0_baseline.inventory import WindowInventory
        return WindowInventory
    if name == "LocalStorageMapping":
        from app.f0_baseline.mapping import LocalStorageMapping
        return LocalStorageMapping
    if name == "PrototypeGenerator":
        from app.f0_baseline.prototype_generator import PrototypeGenerator
        return PrototypeGenerator
    if name == "router":
        from app.f0_baseline.router import router
        return router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
