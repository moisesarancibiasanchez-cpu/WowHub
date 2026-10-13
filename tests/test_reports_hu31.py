# -*- coding: utf-8 -*-
"""HU_31 — Tests del endpoint de catálogo de reportes programables.

Cubre:
  - GET /api/v1/tenants/{tid}/reports devuelve los 3 reportes hardcoded.
  - La respuesta tiene la forma del schema (id/type/format/last_run_at/schedule).
  - Sin Authorization devuelve 401.
  - Con token válido del tenant la respuesta es 200 OK con la lista esperada.
"""
from __future__ import annotations

from typing import Tuple
from datetime import datetime, timezone


# ── Helpers ─────────────────────────────────────────────────────────────
def _register_with_tenant(client, slug: str) -> dict:
    """Registra un usuario nuevo con su tenant (helper estándar de tests)."""
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@example.com",
        "password": "test1234",
        "full_name": "HU31 Tester",
        "create_tenant": True,
        "tenant_legal_name": f"HU31 Test {slug}",
        "tenant_slug": slug,
    })
    assert r.status_code in (200, 201), f"register falló: {r.status_code} {r.text}"
    return r.json()


def _bootstrap(client, slug: str) -> Tuple[str, str]:
    """Crea usuario + tenant y devuelve (token, tenant_id)."""
    data = _register_with_tenant(client, slug)
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]
    return token, tid


# ── 1. GET /reports sin auth → 401 ──────────────────────────────────────
def test_list_reports_requires_auth(client):
    """Sin Authorization el endpoint devuelve 401 (UnauthorizedError)."""
    # Primero necesitamos un tenant válido en la URL; usamos cualquier UUID.
    fake_tid = "00000000-0000-0000-0000-000000000000"
    r = client.get(f"/api/v1/tenants/{fake_tid}/reports")
    assert r.status_code == 401, r.text


# ── 2. GET /reports con auth devuelve catálogo completo ────────────────────
def test_list_reports_returns_catalog(client):
    """Devuelve 3 reportes con la forma y valores esperados."""
    token, tid = _bootstrap(client, slug="hu31-list")

    r = client.get(
        f"/api/v1/tenants/{tid}/reports",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 3, f"esperaba 3 reportes, obtuve {len(items)}"

    # Validar la forma completa de cada item (schema ReportOut).
    expected_ids = {"sales-monthly", "customers-weekly", "inventory-daily"}
    seen_ids = set()
    for it in items:
        assert set(it.keys()) == {"id", "type", "format", "last_run_at", "schedule"}, it
        assert it["type"] in ("sales", "customers", "inventory"), it
        assert it["format"] in ("pdf", "csv"), it
        assert it["schedule"] in ("daily", "weekly", "monthly"), it
        # HU_31 follow-up: el endpoint graba antes de consultar, así que
        # ``last_run_at`` ya viene hidratado desde la 1ª ejecución. Si es
        # string ISO 8601, debe parsear a un datetime cercano a ``now``.
        assert it["last_run_at"] is not None, it
        seen_ids.add(it["id"])
    assert seen_ids == expected_ids


# ── 3. Smoke: respuesta es JSON parseable y contiene campos clave ───────
def test_list_reports_smoke_shape(client):
    """Smoke test — confirma que la respuesta es una lista JSON con campos clave."""
    token, tid = _bootstrap(client, slug="hu31-smoke")

    r = client.get(
        f"/api/v1/tenants/{tid}/reports",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert isinstance(body, list)
    assert all("id" in x and "schedule" in x for x in body)


# ── Helpers HU_31 follow-up ────────────────────────────────────────────
def _parse_iso(value):
    """Helper: parsea un ISO 8601 string a ``datetime`` UTC-aware.

    SQLite (engine de tests) devuelve datetimes ``naive`` cuando los
    recupera de columnas ``TIMESTAMP WITH TIME ZONE`` — la TZ se pierde
    en el round-trip. Para comparar contra ``datetime.now(timezone.utc)``
    (que SÍ trae tzinfo) tenemos que forzar UTC en el valor parseado.
    """
    if value is None:
        return None
    # Python <3.11 no soporta ``fromisoformat`` con 'Z' directamente;
    # los tests corren en 3.11+, pero por defensa normalizamos.
    s = value.replace("Z", "+00:00") if isinstance(value, str) else value
    parsed = datetime.fromisoformat(s)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ── 4. GET /reports crea 3 filas en report_runs con report_key correcto ─
def test_list_reports_records_three_runs(client, db_session):
    """Cada GET /reports persiste 3 filas en ``report_runs`` (uno por reporte)."""
    from app.models.report_run import ReportRun

    token, tid = _bootstrap(client, slug="hu31-records")
    headers = {"Authorization": f"Bearer {token}"}

    # Antes del GET no debe haber runs
    pre = db_session.query(ReportRun).all()
    assert len(pre) == 0, f"esperaba 0 runs pre-GET, obtuve {len(pre)}"

    r = client.get(f"/api/v1/tenants/{tid}/reports", headers=headers)
    assert r.status_code == 200, r.text

    # Después del GET debe haber exactamente 3 filas con report_key correcto
    runs = db_session.query(ReportRun).order_by(ReportRun.report_key).all()
    assert len(runs) == 3, f"esperaba 3 runs post-GET, obtuve {len(runs)}"

    keys = {run.report_key for run in runs}
    assert keys == {"sales", "customers", "inventory"}, keys

    # Cada run debe tener status="ok", duration_ms>=0, started/finished UTC
    for run in runs:
        assert run.status == "ok", run.status
        assert run.duration_ms is not None and run.duration_ms >= 0, run.duration_ms
        assert run.started_at is not None and run.finished_at is not None


# ── 5. last_run_at en respuesta es no-None tras el primer GET ──────────
def test_list_reports_last_run_at_not_null_after_first_get(client):
    """El primer GET ya devuelve ``last_run_at`` (registra y consulta en el mismo request)."""
    token, tid = _bootstrap(client, slug="hu31-lastrun")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get(f"/api/v1/tenants/{tid}/reports", headers=headers)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 3

    # El primer GET graba 3 filas y luego consulta MAX(started_at), por
    # lo que ``last_run_at`` ya debe estar hidratado (no es null).
    now = datetime.now(timezone.utc)
    for it in items:
        assert it["last_run_at"] is not None, it
        parsed = _parse_iso(it["last_run_at"])
        # Debe estar dentro de los últimos 60 segundos
        assert parsed is not None
        delta = abs((now - parsed).total_seconds())
        assert delta < 60, f"last_run_at={parsed} está muy lejos de now={now} (delta={delta}s)"


# ── 6. Tercera ejecución actualiza last_run_at (orden cronológico) ─────
def test_list_reports_last_run_at_updates_chronologically(client):
    """Una tercera ejecución devuelve un ``last_run_at`` posterior a la previa."""
    import time

    token, tid = _bootstrap(client, slug="hu31-chrono")
    headers = {"Authorization": f"Bearer {token}"}

    # 1ª ejecución
    r1 = client.get(f"/api/v1/tenants/{tid}/reports", headers=headers)
    assert r1.status_code == 200
    first = {it["type"]: _parse_iso(it["last_run_at"]) for it in r1.json()}
    assert all(v is not None for v in first.values()), first

    # Pausa > 1s para garantizar diferencia medible en el timestamp
    # (los reportes graban con ``datetime.now(timezone.utc)`` a microsegundo,
    # pero SQLite truncaría a segundo sin la pausa explícita).
    time.sleep(1.1)

    # 3ª ejecución (saltamos la 2 para forzar el "salto cronológico"
    # del test — la lógica del endpoint es la misma en cada GET, lo que
    # cambia es el timestamp final).
    r3 = client.get(f"/api/v1/tenants/{tid}/reports", headers=headers)
    assert r3.status_code == 200
    third = {it["type"]: _parse_iso(it["last_run_at"]) for it in r3.json()}
    assert all(v is not None for v in third.values()), third

    # Cada report_key debe haber avanzado: third > first (al menos 1s).
    for key in ("sales", "customers", "inventory"):
        delta = (third[key] - first[key]).total_seconds()
        assert delta >= 1.0, (
            f"report_key={key} — last_run_at no avanzó entre 1ª y 3ª ejecución: "
            f"first={first[key]}, third={third[key]}, delta={delta}s"
        )