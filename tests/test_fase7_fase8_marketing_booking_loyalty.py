"""Tests de regresión para Fase 7 (Marketing Studio UI) y Fase 8
(Reservas con web booking + fidelidad con QR visual).

Cubre:
- Render del template /dashboard/marketing (Fase 7)
- Render del template /u/{slug}/tarjeta (alias de /loyalty/{slug})
- Soporte HEAD en /u/{slug}/reservar y /u/{slug}/tarjeta (capability probe)
- Endpoint de recuperación de pase (Fase 8) — POST /api/v1/loyalty/c/{slug}/lookup
- Landing con los nuevos enlaces de Reservar y Mi tarjeta (con capability probe)
- Loyalty page con stage de recuperación
"""
import re


def _bootstrap_tenant(client, slug="fase78"):
    """Helper: crea un tenant con slug y devuelve el JSON del registro."""
    r = client.post("/api/v1/auth/register", json={
        "email": f"owner-{slug}@e.com",
        "password": "test1234",
        "full_name": "Owner Fase 7-8",
        "create_tenant": True,
        "tenant_legal_name": f"Negocio {slug}",
        "tenant_slug": slug,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


# ════════════════════════════════════════════════════════════════
# FASE 7: Marketing Studio UI
# ════════════════════════════════════════════════════════════════

def test_dashboard_marketing_route_exists(client):
    """La página /dashboard/marketing debe renderizar 200 con el formulario
    completo (intent, tone, audience, variants, etc.)."""
    r = client.get("/dashboard/marketing")
    assert r.status_code == 200, r.text
    html = r.text
    # Elementos clave del formulario
    assert 'id="marketing-form"' in html, "Falta el formulario principal"
    assert 'id="m_intent"' in html, "Falta el selector de intent"
    assert 'id="m_topic"' in html, "Falta el input de topic"
    assert 'id="m_tone"' in html, "Falta el selector de tono"
    assert 'id="m_audience"' in html, "Falta el selector de audiencia"
    assert 'id="m_variants"' in html, "Falta el selector de nº de variantes"
    assert 'id="m_generate_btn"' in html, "Falta el botón Generar"
    # Integs del UI Marketing IA visibles
    assert "Marketing Studio" in html, "Falta el título Marketing Studio"
    assert "Generar copy" in html or "Generar" in html, "Falta el botón de acción"


def test_marketing_studio_intents_enumerated(client):
    """El selector de intents debe listar los 13 canales del backend."""
    r = client.get("/dashboard/marketing")
    html = r.text
    expected_intents = [
        "instagram_post", "instagram_story", "instagram_reel",
        "facebook_post", "whatsapp_broadcast", "whatsapp_status",
        "email_subject", "email_body", "sms",
        "product_description", "promotion_headline", "promotion_body",
        "general",
    ]
    for intent in expected_intents:
        assert f'value="{intent}"' in html, f"Falta el intent {intent} en el selector"


def test_marketing_studio_nav_link_in_sidebar(client):
    """El sidebar del dashboard debe tener un link visible a /dashboard/marketing."""
    r = client.get("/dashboard")
    assert r.status_code == 200
    html = r.text
    assert 'href="/dashboard/marketing"' in html, (
        "Falta el link 'Marketing IA' en el sidebar del dashboard"
    )
    assert "Marketing IA" in html, "Falta el texto 'Marketing IA' en el sidebar"


# ════════════════════════════════════════════════════════════════
# FASE 8: Reservas con web booking + fidelidad con QR visual
# ════════════════════════════════════════════════════════════════

def test_public_booking_supports_HEAD_probe(client):
    """La página /u/{slug}/reservar debe soportar HEAD (capability probe
    desde la landing)."""
    _bootstrap_tenant(client, "book-probe")
    r = client.head("/u/book-probe/reservar")
    assert r.status_code == 200, f"HEAD en /reservar devolvió {r.status_code}"
    # GET también debe funcionar (que es el render real)
    r2 = client.get("/u/book-probe/reservar")
    assert r2.status_code == 200, r2.text
    # El template debe estar presente
    assert "Reserva" in r2.text or "reservar" in r2.text, "Página booking no renderiza"


def test_public_loyalty_alias_supports_HEAD_and_GET(client):
    """La ruta /u/{slug}/tarjeta debe ser alias de /loyalty/{slug} y
    soportar tanto HEAD como GET."""
    # Tenant sin campaña activa: 404 esperado
    _bootstrap_tenant(client, "loy-alias")
    r_head = client.head("/u/loy-alias/tarjeta")
    r_get  = client.get("/u/loy-alias/tarjeta")
    # Sin campaña activa, ambos deben ser 404 (consistente con /loyalty/{slug})
    assert r_head.status_code == 404, f"HEAD en /tarjeta (sin campaña) = {r_head.status_code}"
    assert r_get.status_code == 404, f"GET en /tarjeta (sin campaña) = {r_get.status_code}"
    # Ahora con campaña: 200
    from app.models.loyalty_pass import LoyaltyCampaign
    from app.models.tenant import Tenant
    from app.database import SessionLocal
    from sqlalchemy import select

    with SessionLocal() as db:
        t = db.execute(
            select(Tenant).where(Tenant.slug == "loy-alias")
        ).scalar_one()
        c = LoyaltyCampaign(
            tenant_id=str(t.id),
            name="Tarjeta de prueba",
            reward_label="1 café gratis",
            stamps_required=6,
            primary_color="#1A73E8",
            text_color="#FFFFFF",
            is_active=True,
        )
        db.add(c)
        db.commit()
        db.refresh(c)

    r_head2 = client.head("/u/loy-alias/tarjeta")
    r_get2  = client.get("/u/loy-alias/tarjeta")
    assert r_head2.status_code == 200, r_head2.text
    assert r_get2.status_code == 200, r_get2.text
    assert "Tarjeta de Fidelidad" in r_get2.text or "fidelidad" in r_get2.text.lower()


def test_loyalty_page_has_recover_stage(client):
    """La página pública de fidelidad debe tener el stage de recuperación
    (¿Ya tienes una? → Recuperar mi tarjeta)."""
    from app.models.loyalty_pass import LoyaltyCampaign
    from app.models.tenant import Tenant
    from app.database import SessionLocal
    from sqlalchemy import select

    _bootstrap_tenant(client, "loy-rec")
    with SessionLocal() as db:
        t = db.execute(select(Tenant).where(Tenant.slug == "loy-rec")).scalar_one()
        c = LoyaltyCampaign(
            tenant_id=str(t.id),
            name="Tarjeta",
            reward_label="1 café",
            stamps_required=5,
            primary_color="#1A73E8",
            text_color="#FFFFFF",
            is_active=True,
        )
        db.add(c); db.commit()

    r = client.get("/u/loy-rec/tarjeta")
    assert r.status_code == 200
    html = r.text
    # El nuevo stage de recuperación debe estar en el HTML
    assert 'id="stage-recover"' in html, "Falta el stage de recuperación de pase"
    assert 'id="recover-link"' in html, "Falta el link 'Recuperar mi tarjeta'"
    assert 'id="recover-form"' in html, "Falta el form de recuperación"
    assert 'id="rec_email"' in html, "Falta el input de email para recovery"
    assert 'id="rec_phone"' in html, "Falta el input de phone para recovery"
    # Y la API que consume
    assert "/api/v1/loyalty/c/${SLUG}/lookup" in html, (
        "El form de recovery no apunta al endpoint /lookup"
    )


def test_loyalty_lookup_endpoint_returns_existing_pass(client):
    """POST /api/v1/loyalty/c/{slug}/lookup con email/phone de un cliente
    registrado debe devolver su pase."""
    from app.models.loyalty_pass import LoyaltyCampaign
    from app.models.tenant import Tenant
    from app.database import SessionLocal
    from sqlalchemy import select

    _bootstrap_tenant(client, "loy-lookup-ok")
    slug = "loy-lookup-ok"

    with SessionLocal() as db:
        t = db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one()
        c = LoyaltyCampaign(
            tenant_id=str(t.id),
            name="Tarjeta Lookup",
            reward_label="1 postre",
            stamps_required=4,
            primary_color="#1A73E8",
            text_color="#FFFFFF",
            is_active=True,
        )
        db.add(c); db.commit(); db.refresh(c)

    # Registrar un cliente vía API
    register_body = {
        "full_name": "Cliente Lookup",
        "email": "lookup@e.com",
        "phone": "+56911111111",
        "accepts_marketing": True,
        "accepts_terms": True,
    }
    rr = client.post(f"/api/v1/loyalty/c/{slug}/register", json=register_body)
    assert rr.status_code in (200, 201), rr.text
    pass_data = rr.json()
    assert pass_data.get("stamps_current") == 0
    serial = pass_data.get("serial_number") or pass_data.get("serial")
    assert serial, f"El register no devolvió serial: {pass_data}"

    # Ahora lookup por email
    r = client.post(
        f"/api/v1/loyalty/c/{slug}/lookup",
        json={"email": "lookup@e.com"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    returned_serial = data.get("serial_number") or data.get("serial")
    assert returned_serial == serial, f"Lookup devolvió un pase diferente: {data}"
    assert data.get("reward_label") == "1 postre"
    assert data.get("stamps_current") == 0

    # Y lookup por phone
    r2 = client.post(
        f"/api/v1/loyalty/c/{slug}/lookup",
        json={"phone": "+56911111111"},
    )
    assert r2.status_code == 200, r2.text
    returned_serial_2 = r2.json().get("serial_number") or r2.json().get("serial")
    assert returned_serial_2 == serial


def test_loyalty_lookup_404_when_not_found(client):
    """Lookup con email/phone no registrado debe devolver 404."""
    _bootstrap_tenant(client, "loy-lookup-404")
    slug = "loy-lookup-404"
    from app.models.loyalty_pass import LoyaltyCampaign
    from app.models.tenant import Tenant
    from app.database import SessionLocal
    from sqlalchemy import select
    with SessionLocal() as db:
        t = db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one()
        c = LoyaltyCampaign(
            tenant_id=str(t.id),
            name="Tarjeta 404",
            reward_label="X",
            stamps_required=3,
            primary_color="#1A73E8",
            text_color="#FFFFFF",
            is_active=True,
        )
        db.add(c); db.commit()

    # Email/phone que NO existe
    r = client.post(
        f"/api/v1/loyalty/c/{slug}/lookup",
        json={"email": "no-existe@e.com"},
    )
    assert r.status_code == 404, f"Esperado 404, recibido {r.status_code}"


def test_loyalty_lookup_400_when_no_contact(client):
    """Lookup sin email ni phone debe devolver 400."""
    _bootstrap_tenant(client, "loy-lookup-400")
    slug = "loy-lookup-400"
    from app.models.loyalty_pass import LoyaltyCampaign
    from app.models.tenant import Tenant
    from app.database import SessionLocal
    from sqlalchemy import select
    with SessionLocal() as db:
        t = db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one()
        c = LoyaltyCampaign(
            tenant_id=str(t.id),
            name="Tarjeta 400",
            reward_label="X",
            stamps_required=3,
            primary_color="#1A73E8",
            text_color="#FFFFFF",
            is_active=True,
        )
        db.add(c); db.commit()

    r = client.post(f"/api/v1/loyalty/c/{slug}/lookup", json={})
    assert r.status_code == 400, f"Esperado 400, recibido {r.status_code}"


def test_landing_has_booking_and_loyalty_nav_links(client):
    """La landing pública debe tener los nuevos enlaces a Reservar y
    Mi tarjeta de fidelidad, que se muestran condicionalmente según
    las capabilities del tenant (Fase 8)."""
    _bootstrap_tenant(client, "landing-nav")
    r = client.get("/u/landing-nav")
    assert r.status_code == 200, r.text
    html = r.text
    # Los hrefs están en el HTML (estáticos, se muestran via JS)
    assert 'href="/u/landing-nav/reservar"' in html, "Falta el link a /u/{slug}/reservar"
    assert 'href="/u/landing-nav/tarjeta"' in html, "Falta el link a /u/{slug}/tarjeta"
    # Los IDs de capability probe están en el JS
    assert 'id="nav-bookings"' in html, "Falta el id nav-bookings"
    assert 'id="nav-loyalty"' in html, "Falta el id nav-loyalty"
    # Y la lógica de HEAD probe
    assert 'method: "HEAD"' in html or "method: 'HEAD'" in html, (
        "Falta el código JS que hace capability probe con HEAD"
    )
    # Y el texto de los enlaces
    assert "Reservar" in html, "Falta el texto 'Reservar'"
    assert "Mi tarjeta" in html or "★ Mi tarjeta" in html, "Falta el texto 'Mi tarjeta'"
