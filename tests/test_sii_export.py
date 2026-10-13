"""HU_32 — Tests mínimos del exportador SII Chile.

Cubre:
  - test_validate_rut_with_valid      → RUTs válidos (12.345.678-5, 20.123.456-K, 1-9)
  - test_validate_rut_with_invalid    → DV mal, letras en cuerpo, vacío, None
  - test_format_rut                   → formato canónico "12.345.678-9"
  - test_export_ventas_returns_csv_headers → headers SII correctos + totales
  - test_endpoint_validate_rut_returns_correct_format → endpoint FastAPI

Los tests de servicios (validator/exporter) son unitarios puros — no
necesitan DB. El test de endpoint usa el fixture ``client`` del conftest.
"""
from __future__ import annotations

import csv
from io import StringIO
from uuid import uuid4

from app.services.sii_exporter import LIBRO_VENTAS_HEADER, export_ventas
from app.services.sii_validator import clean_rut, format_rut, validate_rut


# ── 1) Validator: RUTs válidos ─────────────────────────────────────
def test_validate_rut_with_valid():
    """RUTs con DV correcto (módulo 11) deben validar."""
    # 12.345.678-5 → clásico ejemplo de prueba del SII
    assert validate_rut("12.345.678-5") is True
    assert validate_rut("12345678-5") is True          # sin puntos
    assert validate_rut("123456785") is True           # sin separadores
    assert validate_rut(" 12.345.678-5 ") is True      # con espacios
    # DV = K (1.000.005-K y 10.000.013-K son RUTs reales con DV=K)
    assert validate_rut("1.000.005-K") is True
    assert validate_rut("10.000.013-K") is True
    assert validate_rut("1000005-K") is True
    assert validate_rut("1000005k") is True            # k minúscula también OK
    # RUT mínimo (1-9)
    assert validate_rut("1-9") is True
    assert validate_rut("19") is True


# ── 2) Validator: RUTs inválidos ────────────────────────────────────
def test_validate_rut_with_invalid():
    """DV mal, letras en cuerpo, vacío, None, formato roto."""
    # DV incorrecto (12.345.678-9, el DV correcto es 5)
    assert validate_rut("12.345.678-9") is False
    assert validate_rut("12345678-0") is False
    # Cuerpo no numérico
    assert validate_rut("abc") is False
    assert validate_rut("12a345678-5") is False
    # Vacío / None
    assert validate_rut("") is False
    assert validate_rut("   ") is False
    assert validate_rut(None) is False  # type: ignore[arg-type]
    # Tipo incorrecto
    assert validate_rut(12345678) is False  # type: ignore[arg-type]
    # Sólo DV sin cuerpo
    assert validate_rut("K") is False
    assert validate_rut("-K") is False
    # Cuerpo demasiado largo (max 8 dígitos por convención)
    assert validate_rut("123456789-K") is False


# ── 3) format_rut: canónico ────────────────────────────────────────
def test_format_rut():
    """Formato canónico con puntos cada 3 dígitos + guión + DV."""
    assert format_rut("123456785") == "12.345.678-5"
    assert format_rut("12345678-5") == "12.345.678-5"
    assert format_rut("12.345.678-5") == "12.345.678-5"
    assert format_rut("1000005-K") == "1.000.005-K"
    assert format_rut("1000005k") == "1.000.005-K"  # uppercase
    # RUT corto (1 dígito de cuerpo)
    assert format_rut("1-9") == "1-9"
    assert format_rut("19") == "1-9"
    # RUT con 3 dígitos de cuerpo (sin puntos)
    assert format_rut("1111") == "111-1"
    assert format_rut("111-1") == "111-1"
    # RUT con 7 dígitos de cuerpo → un grupo de 3 + grupo de 2
    assert format_rut("1234567-4") == "1.234.567-4"
    # clean_rut funciona
    assert clean_rut(" 12.345.678-5 ") == "123456785"
    assert clean_rut("1-000-005-k") == "1000005K"


# ── 4) Exporter: headers SII correctos + totales ───────────────────
def test_export_ventas_returns_csv_headers():
    """CSV vacío (sin órdenes) debe traer headers + fila TOTAL con ceros."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        tenant_id = uuid4()  # tenant inexistente → 0 órdenes
        csv_str = export_ventas(tenant_id, 2026, 1, db)
    finally:
        db.close()

    # El CSV retornado es un string (sin BOM; el caller codifica con utf-8-sig)
    assert isinstance(csv_str, str)
    # Encoding utf-8-sig debe preprendar el BOM 0xEF 0xBB 0xBF
    encoded = csv_str.encode("utf-8-sig")
    assert encoded.startswith(b"\xef\xbb\xbf"), (
        "El CSV codificado con utf-8-sig debe empezar con el BOM UTF-8"
    )

    # Parseamos SIN el BOM para inspeccionar el contenido
    text = encoded.decode("utf-8-sig")
    reader = csv.reader(StringIO(text), delimiter=";")
    rows = list(reader)

    # Header (1ra fila) = 17 columnas oficiales del SII
    assert rows[0] == LIBRO_VENTAS_HEADER
    assert len(rows[0]) == 17, "El header debe tener exactamente 17 columnas"

    # Fila TOTAL (2da fila) con todos los montos en "0,00"
    assert len(rows) >= 2, "Debe haber al menos 2 filas (header + TOTAL)"
    total_row = rows[1]
    assert total_row[2] == "TOTAL", f"La 3a columna debe ser 'TOTAL', got {total_row[2]!r}"
    # Montos en posiciones 7-10 deben ser 0,00
    assert total_row[6] == "0,00", f"Monto Exento total: {total_row[6]}"
    assert total_row[7] == "0,00", f"Monto Neto total: {total_row[7]}"
    assert total_row[8] == "0,00", f"Monto IVA total: {total_row[8]}"
    assert total_row[9] == "0,00", f"Monto Total total: {total_row[9]}"

    # Separador usado: ;
    assert ";" in csv_str


# ── 5) Endpoint: validate-rut vía HTTP ─────────────────────────────
def test_endpoint_validate_rut_returns_correct_format(client):
    """POST /api/v1/tenants/{tid}/sii/validate-rut debe responder JSON."""
    # Bootstrap: registrar usuario + tenant + membresía
    r = client.post("/api/v1/auth/register", json={
        "email": "sii-owner@example.com",
        "password": "test1234",
        "full_name": "SII Owner",
        "create_tenant": True,
        "tenant_legal_name": "SII Test SpA",
        "tenant_slug": "sii-test",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    token = body["access_token"]
    tid = body["current_tenant"]["tenant_id"]

    # RUT válido
    r = client.post(
        f"/api/v1/tenants/{tid}/sii/validate-rut",
        json={"rut": "12.345.678-5"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["valid"] is True
    assert data["formatted"] == "12.345.678-5"
    assert data["clean"] == "123456785"

    # RUT inválido (DV mal)
    r = client.post(
        f"/api/v1/tenants/{tid}/sii/validate-rut",
        json={"rut": "12.345.678-9"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["valid"] is False
    assert data["clean"] == "123456789"
