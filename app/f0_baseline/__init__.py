"""
WowHub V134.1 — F0 Baseline, F1 Hardening & Auditoría.

Módulo que implementa las 3 primeras HU del plan F0 más 3 HU de F1:

  F0 (8 SP) — baseline / auditoría:
    - HU_01 (3 SP): Inventariar funciones `window.*` del prototipo V134.1
    - HU_02 (3 SP): Mapear localStorage keys a modelos SQLAlchemy existentes
    - HU_03 (2 SP): Validar Alembic + tests del proyecto

  F1 (8 SP) — hardening del baseline:
    - F1.1 / HU_04 (3 SP): Pydantic v2 estricto en /f0/* (response_model
      + OpenAPI shape + rechazo de payloads malformados)
    - F1.2 / HU_05 (3 SP): AST-lite parser para `window.*` que reemplaza
      el regex de F0 (sin falsos positivos por strings/comentarios)
    - F1.3 / HU_06 (2 SP): Alembic inicializado + migración autogenerada
      desde `Base` (sustituye `Base.metadata.create_all`)

Total: 16 story points (F0: 8, F1: 8).

Estos HU NO añaden modelos nuevos: la base de datos ya está completa
(30 modelos en `app/models/`). F0/F1 lo que hacen es auditar la coherencia
entre el prototipo HTML y los modelos existentes, y endurecer el baseline
para producción (contratos OpenAPI estrictos, parsing correcto, migrations
versionadas).

Uso rápido:
    from app.f0_baseline import WindowInventory, LocalStorageMapping
    from pathlib import Path

    inv = WindowInventory.from_html(Path("prototypes/f0_baseline/demo.html"))
    rows = inv.extract()

    m = LocalStorageMapping()
    report = m.run()  # incluye JSON + Markdown

    # F1.2: parser AST-lite (si necesitás parsear a más bajo nivel)
    from app.f0_baseline.js_parser import parse_window_functions
    fns = parse_window_functions(html_text)
"""
from __future__ import annotations

__version__ = "1.1.0"
__phase__ = "F1"
__story_points__ = 16
__hu_covered__ = [
    # F0 — baseline
    "HU_01", "HU_02", "HU_03",
    # F1 — hardening
    "HU_04",  # F1.1 Pydantic v2 estricto
    "HU_05",  # F1.2 AST-lite parser
    "HU_06",  # F1.3 Alembic init + autogen
]

__all__ = [
    "WindowInventory",
    "LocalStorageMapping",
    "PrototypeGenerator",
    "router",
    "parse_window_functions",  # F1.2: AST-lite parser
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
    if name == "parse_window_functions":  # F1.2
        from app.f0_baseline.js_parser import parse_window_functions
        return parse_window_functions
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
