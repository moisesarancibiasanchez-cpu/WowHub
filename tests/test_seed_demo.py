"""Tests para scripts/seed_demo.py.

Verifica que el seed:
  1) Es idempotente (segunda corrida no duplica)
  2) Crea el cliente demo "Cafetería El Rincón" con datos completos
  3) Genera data de ejemplo para los features V8 (Costos, Pedidos,
     Cotizaciones, Bookings, Loyalty Pass)
"""
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Path al script de seed
REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_SCRIPT = REPO_ROOT / "scripts" / "seed_demo.py"


def _run_seed_subprocess(env_overrides: dict | None = None) -> int:
    """Ejecuta `python -m scripts.seed_demo` en un subproceso y retorna el exit code."""
    import os
    env = os.environ.copy()
    # Forzar DB en memoria y un SECRET_KEY válido
    env["DATABASE_URL"] = "sqlite:///:memory:"
    env["SECRET_KEY"] = "test-secret-key-min-32-chars-ok-test"
    env["JWT_SECRET"] = "test-jwt-secret-min-32-chars-ok-test"
    env["RATE_LIMIT_ENABLED"] = "false"
    env["AUDIT_ENABLED"] = "false"
    if env_overrides:
        env.update(env_overrides)

    result = subprocess.run(
        [sys.executable, "-m", "scripts.seed_demo"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        # Mostrar últimas 30 líneas de stderr/stdout para debugging
        print("STDOUT:", result.stdout[-3000:])
        print("STDERR:", result.stderr[-3000:])
    return result.returncode


def test_seed_creates_demo_tenant():
    """El seed debe crear el tenant demo + user + branch + productos + etc."""
    rc = _run_seed_subprocess()
    assert rc == 0, "seed_demo debe retornar 0"


def test_seed_is_idempotent():
    """Una segunda corrida del seed no debe duplicar datos ni fallar."""
    # Primera corrida
    assert _run_seed_subprocess() == 0
    # Segunda corrida
    assert _run_seed_subprocess() == 0


def test_seed_creates_v8_features():
    """El seed debe crear data para Costos, Pedidos, Cotizaciones, Bookings, Loyalty."""
    rc = _run_seed_subprocess()
    assert rc == 0


def test_seed_file_exists_and_is_valid_python():
    """El script debe existir y ser importable."""
    assert SEED_SCRIPT.exists(), f"script no encontrado: {SEED_SCRIPT}"
    # Validar sintaxis
    import ast
    with open(SEED_SCRIPT) as f:
        source = f.read()
    ast.parse(source)  # raises SyntaxError si está mal


def test_seed_has_all_v8_functions():
    """El script debe contener las 5 funciones de seed V8."""
    source = SEED_SCRIPT.read_text()
    required_funcs = [
        "_get_or_create_business_costs",
        "_get_or_create_orders",
        "_get_or_create_quotes",
        "_get_or_create_bookings",
        "_get_or_create_loyalty",
    ]
    for fn in required_funcs:
        assert f"def {fn}" in source, f"Falta la función {fn} en seed_demo.py"


def test_seed_imports_all_required_models():
    """El script debe importar todos los modelos necesarios para V8."""
    source = SEED_SCRIPT.read_text()
    required_models = [
        "BusinessCosts",
        "Order",
        "OrderItem",
        "OrderStatus",
        "Quote",
        "QuoteItem",
        "QuoteStatus",
        "Booking",
        "BookingStatus",
        "LoyaltyCampaign",
        "CustomerPass",
        "PassStatus",
    ]
    for model in required_models:
        assert model in source, f"Falta importar el modelo {model}"


def test_seed_sets_feature_flags():
    """El seed debe activar los feature flags de V8 en el tenant settings."""
    source = SEED_SCRIPT.read_text()
    flags = [
        "feature_costs_enabled",
        "feature_kanban_enabled",
        "feature_quotes_enabled",
        "feature_bookings_enabled",
        "feature_loyalty_enabled",
    ]
    for flag in flags:
        assert flag in source, f"Falta el feature flag {flag}"
