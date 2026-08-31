"""Tests para HU_01 — WindowInventory."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.f0_baseline import WindowInventory
from app.f0_baseline.prototype_generator import PrototypeGenerator


@pytest.fixture(scope="module")
def prototype_path(tmp_path_factory) -> Path:
    p = tmp_path_factory.mktemp("f0") / "demo.html"
    PrototypeGenerator(output_path=p).write()
    return p


def test_inventory_finds_all_functions(prototype_path: Path) -> None:
    inv = WindowInventory.from_html(prototype_path)
    rows = inv.extract()
    # 11 módulos × 20 funciones = 220 + 1 función de localStorage
    assert len(rows) >= 220
    fn_names = {r.name for r in rows}
    assert "dashboard_func_01" in fn_names
    assert "reportes_func_20" in fn_names
    assert "localStorage_seed" in fn_names


def test_inventory_groups_by_module(prototype_path: Path) -> None:
    inv = WindowInventory.from_html(prototype_path)
    rows = inv.extract()
    modules = {r.module for r in rows}
    # 11 módulos de negocio + 1 sección LOCALSTORAGE = 12
    assert len(modules) == 12
    assert "DASHBOARD" in modules
    assert "REPORTES" in modules
    assert "LOCALSTORAGE" in modules


def test_inventory_captures_descriptions(prototype_path: Path) -> None:
    inv = WindowInventory.from_html(prototype_path)
    rows = inv.extract()
    # Cada función tiene descripción del generador
    for r in rows:
        assert r.description
        assert r.line > 0
        assert r.n > 0


def test_inventory_to_markdown_includes_summary(prototype_path: Path) -> None:
    inv = WindowInventory.from_html(prototype_path)
    rows = inv.extract()
    md = inv.to_markdown(rows, elapsed_ms=1)
    assert "Inventario" in md
    assert "Total funciones" in md
    assert "DASHBOARD" in md
    assert "| # |" in md


def test_inventory_run_returns_complete_dict(prototype_path: Path) -> None:
    inv = WindowInventory.from_html(prototype_path)
    out = inv.run()
    assert out["total"] >= 220
    assert out["elapsed_ms"] >= 0
    assert isinstance(out["rows"], list)
    assert "markdown" in out
