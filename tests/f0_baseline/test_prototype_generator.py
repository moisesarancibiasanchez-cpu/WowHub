"""Tests del PrototypeGenerator y de la integración F0."""
from __future__ import annotations

from pathlib import Path

from app.f0_baseline import PrototypeGenerator
from app.f0_baseline.prototype_generator import MODULES, LOCALSTORAGE_DEMO


def test_generator_produces_html(tmp_path: Path) -> None:
    target = tmp_path / "demo.html"
    PrototypeGenerator(output_path=target).write()
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "<!doctype html>" in text
    assert "WowHub" in text
    # 11 módulos
    for mod_name, _ in MODULES:
        assert mod_name in text


def test_generator_function_count() -> None:
    expected = sum(n for _, n in MODULES) + 1  # +1 para localStorage_seed
    g = PrototypeGenerator()
    html = g.build()
    # Cuenta "window.<name> = function" en el HTML
    import re
    found = len(re.findall(r"window\.\w+\s*=\s*function", html))
    assert found == expected, f"Esperaba {expected} funciones, encontré {found}"


def test_generator_localstorage_seeds_match_mapping() -> None:
    """Las claves localStorage del HTML deben estar todas en el mapeo HU_02."""
    from app.f0_baseline.mapping import KEY_TO_MODEL
    keys_in_demo = {k for k, _ in LOCALSTORAGE_DEMO}
    mapped = set(KEY_TO_MODEL.keys())
    # Toda key del demo debe tener un mapeo
    assert keys_in_demo.issubset(mapped), (
        f"Keys sin mapeo: {keys_in_demo - mapped}"
    )


def test_generator_html_has_220_functions() -> None:
    g = PrototypeGenerator()
    html = g.build()
    # 11 × 20 = 220 funciones de módulo
    # + 1 función extra (localStorage_seed) = 221
    import re
    n = len(re.findall(r"window\.\w+\s*=\s*function", html))
    expected = sum(n for _, n in MODULES) + 1
    assert n == expected, f"Esperaba {expected} funciones, encontré {n}"
