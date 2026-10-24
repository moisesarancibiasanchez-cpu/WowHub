"""Regresión V2.014 (2026-10-24) — uploaders y previsualización de imágenes.

Defecto reportado por el usuario:

    "Revisa cada uno de los UPLOADER de archivos en todas las páginas, dado
     que cuando se cargan arroja un error: ⚠ No se pudo cargar la imagen.
     La URL puede haber cambiado o el archivo ya no existe.
     /api/v1/tenants/{tid}/uploads/{uid}/content"

Causas raíz:

  1) ``app/api/v1/uploads.py`` importaba ``HTTPException`` desde
     ``fastapi.responses``, donde ese nombre NO existe. Como el import
     estaba DENTRO de la función, cada petición a
     ``GET /tenants/{tid}/uploads/{uid}/content`` moría con ImportError y
     respondía **500**. El preview del dashboard (que descarga la imagen
     con fetch + Bearer) recibía ese 500 y caía en la URL cruda, que el
     ``<img>`` no puede autenticar → 401 → "⚠ No se pudo cargar la
     imagen".

  2) El mensaje de error del preview era engañoso: siempre culpaba a la
     URL, aunque la URL estuviera perfecta y el problema fuera otro.

  3) Un ``<img src>`` no puede mandar el header ``Authorization``, así que
     las miniaturas nativas del dashboard (catálogo de productos, logos)
     recibían 401 aunque la imagen existiera. Ahora el endpoint acepta
     además la cookie httpOnly de sesión.

  4) En producción el almacenamiento es efímero: los archivos se pierden en
     cada despliegue. Eso no lo arregla el código, pero el endpoint ahora
     lo dice explícitamente y hay un script para listar qué falta
     (``scripts/check_missing_uploads.py``).
"""
from __future__ import annotations

import io
import os
import re
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# PNG 1x1 válido (RGBA)
PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def _read(path: str) -> str:
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


# ════════════════════════════════════════════════════════════════════════
# 0. Barrido de imports: la causa raíz del 500
# ════════════════════════════════════════════════════════════════════════

def test_ningun_modulo_importa_http_exception_desde_fastapi_responses():
    """`fastapi.responses` NO exporta HTTPException.

    Ese import (sólo en uploads.py) provocaba un ImportError en runtime
    que convertía TODO el endpoint de contenido en un 500.
    """
    offenders = []
    for dirpath, _dirnames, filenames in os.walk(os.path.join(ROOT, "app")):
        if "__pycache__" in dirpath:
            continue
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            src = _read(path)
            for m in re.finditer(r"from\s+fastapi\.responses\s+import\s+([^\n]+)", src):
                names = m.group(1)
                if "HTTPException" in names:
                    offenders.append(f"{os.path.relpath(path, ROOT)}: {m.group(0).strip()}")
    assert not offenders, (
        "HTTPException se importa desde fastapi.responses (no existe ahí) en: "
        + " | ".join(offenders)
    )


def test_el_endpoint_de_contenido_no_importa_dentro_de_la_funcion():
    """El import debe estar a nivel de módulo: dentro de la función el
    ImportError se convertía en un 500 en cada petición."""
    src = _read(os.path.join(ROOT, "app", "api", "v1", "uploads.py"))
    cuerpo = src.split("def get_upload_content", 1)[1]
    assert "from fastapi.responses import" not in cuerpo, (
        "el import de fastapi.responses no debe quedar dentro de la función"
    )
    assert "from fastapi import" in src and "HTTPException" in src.split("def ", 1)[0], (
        "HTTPException debe importarse a nivel de módulo desde fastapi"
    )


# ════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════

@pytest.fixture
def storage_tmp(monkeypatch, tmp_path):
    """Redirige el almacenamiento a un directorio temporal."""
    from app.config import settings

    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "storage_path", str(tmp_path), raising=False)
    return tmp_path


def _mk_user(db, email, is_superuser=False):
    from app.models.user import User, UserRole
    from app.security import hash_password

    u = User(
        email=email,
        password_hash=hash_password("test-password-123"),
        full_name="Usuario de prueba",
        default_role=UserRole.STAFF,
        is_superuser=is_superuser,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _mk_tenant(db, slug):
    from app.models.tenant import Tenant, TenantPlan

    t = Tenant(
        slug=slug,
        legal_name="Empresa de prueba SpA",
        display_name="Empresa de prueba",
        plan=TenantPlan.FREE,
        is_active=True,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _mk_membership(db, user, tenant, role, is_owner=False):
    from app.models.tenant import TenantMembership

    m = TenantMembership(
        id=uuid.uuid4(),
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        role=role,
        is_owner=is_owner,
        is_active=True,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _token(user, tenant, role="owner"):
    from app.security import create_access_token

    return create_access_token(user.id, tenant_id=tenant.id, role=role)


def _subir(db, tenant, content=PNG_1x1, filename="prueba.png", purpose="product_image"):
    """Sube una imagen con el servicio real y devuelve la fila Upload."""
    from app.services.upload_service import UploadService

    svc = UploadService(db)
    return svc.save_image(
        tenant.id,
        content=content,
        filename=filename,
        content_type="image/png",
        purpose=purpose,
    )


# ════════════════════════════════════════════════════════════════════════
# 1. El endpoint de contenido
# ════════════════════════════════════════════════════════════════════════

def test_el_contenido_se_sirve_con_bearer(client, db_session, storage_tmp):
    """REGRESIÓN: esto devolvía 500 (ImportError)."""
    from app.models.user import UserRole

    u = _mk_user(db_session, f"up-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.OWNER, is_owner=True)
    up = _subir(db_session, t)

    r = client.get(up.url, headers={"Authorization": f"Bearer {_token(u, t)}"})
    assert r.status_code == 200, f"el endpoint de contenido no sirve la imagen: {r.status_code}"
    assert r.headers["content-type"].startswith("image/")
    assert r.content == PNG_1x1


def test_el_contenido_se_sirve_con_la_cookie_de_sesion(client, db_session, storage_tmp):
    """Un <img src> no puede mandar Authorization: la cookie httpOnly
    (wowhub_access_token) debe autenticar la petición."""
    from app.models.user import UserRole

    u = _mk_user(db_session, f"ck-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.OWNER, is_owner=True)
    up = _subir(db_session, t)

    client.cookies.set("wowhub_access_token", _token(u, t))
    r = client.get(up.url)
    assert r.status_code == 200, (
        f"un <img> nativo (sin header Authorization) no puede cargar la imagen: {r.status_code}"
    )
    assert r.content == PNG_1x1


def test_el_contenido_sin_sesion_responde_401(client, db_session, storage_tmp):
    from app.models.user import UserRole

    u = _mk_user(db_session, f"ns-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.OWNER, is_owner=True)
    up = _subir(db_session, t)

    r = client.get(up.url)
    assert r.status_code == 401


def test_el_contenido_de_un_tenant_ajeno_responde_403(client, db_session, storage_tmp):
    """La cookie de otro tenant no habilita el acceso."""
    from app.models.user import UserRole

    u = _mk_user(db_session, f"aj-{uuid.uuid4().hex[:8]}@example.com")
    t_mio = _mk_tenant(db_session, f"mio-{uuid.uuid4().hex[:8]}")
    t_otro = _mk_tenant(db_session, f"otro-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t_mio, UserRole.OWNER, is_owner=True)
    up = _subir(db_session, t_otro)

    client.cookies.set("wowhub_access_token", _token(u, t_mio))
    r = client.get(f"/api/v1/tenants/{t_otro.id}/uploads/{up.id}/content")
    assert r.status_code in (403, 404), f"un tenant ajeno no debe leer el archivo: {r.status_code}"


def test_el_contenido_inexistente_responde_404(client, db_session, storage_tmp):
    from app.models.user import UserRole

    u = _mk_user(db_session, f"ix-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.OWNER, is_owner=True)

    r = client.get(
        f"/api/v1/tenants/{t.id}/uploads/{uuid.uuid4()}/content",
        headers={"Authorization": f"Bearer {_token(u, t)}"},
    )
    assert r.status_code == 404


def test_si_el_archivo_no_esta_en_disco_el_error_lo_dice(client, db_session, storage_tmp):
    """El registro existe pero el archivo se perdió (storage efímero).

    El 404 debe explicar qué pasó, para que el usuario sepa que hay que
    volver a subir la imagen y no que la URL esté mal.
    """
    from app.models.user import UserRole

    u = _mk_user(db_session, f"pd-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.OWNER, is_owner=True)
    up = _subir(db_session, t)

    # Se borra el archivo del disco (simula un despliegue sin volumen).
    (storage_tmp / str(t.id) / up.stored_filename).unlink()

    r = client.get(up.url, headers={"Authorization": f"Bearer {_token(u, t)}"})
    assert r.status_code == 404
    detalle = (r.json().get("detail") or "").lower()
    assert "vuelve a subir" in detalle, (
        f"el 404 debe indicar que hay que volver a subir la imagen: {detalle!r}"
    )
    assert "despliegue" in detalle, (
        f"el 404 debe explicar que el archivo se perdió en un despliegue: {detalle!r}"
    )


# ════════════════════════════════════════════════════════════════════════
# 2. Flujo completo de subida (lo que hace el uploader del dashboard)
# ════════════════════════════════════════════════════════════════════════

def test_el_flujo_completo_de_subida_sirve_la_imagen(client, db_session, storage_tmp):
    """POST /uploads -> URL canónica -> GET de esa URL con Bearer."""
    from app.models.user import UserRole

    u = _mk_user(db_session, f"fl-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.OWNER, is_owner=True)
    tok = _token(u, t)

    r = client.post(
        f"/api/v1/tenants/{t.id}/uploads",
        headers={"Authorization": f"Bearer {tok}"},
        files={"file": ("prueba.png", PNG_1x1, "image/png")},
        data={"purpose": "product_image"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["url"].endswith("/content")
    assert f"/api/v1/tenants/{t.id}/uploads/{body['id']}/content" == body["url"]

    r2 = client.get(body["url"], headers={"Authorization": f"Bearer {tok}"})
    assert r2.status_code == 200, f"la imagen recién subida no se pudo leer: {r2.status_code}"
    assert r2.content == PNG_1x1


def test_la_url_de_la_imagen_es_relativa_y_estable(client, db_session, storage_tmp):
    """La URL guardada debe ser relativa (host-agnostic): si guardara el
    dominio, cambiar de host dejaría todas las imágenes rotas."""
    from app.models.user import UserRole

    u = _mk_user(db_session, f"ur-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.OWNER, is_owner=True)

    r = client.post(
        f"/api/v1/tenants/{t.id}/uploads",
        headers={"Authorization": f"Bearer {_token(u, t)}"},
        files={"file": ("prueba.png", PNG_1x1, "image/png")},
        data={"purpose": "product_image"},
    )
    assert r.status_code == 201, r.text
    url = r.json()["url"]
    assert url.startswith("/api/v1/"), f"la URL debe ser relativa, no absoluta: {url}"
    assert "localhost" not in url and "http" not in url


# ════════════════════════════════════════════════════════════════════════
# 3. El preview del cliente
# ════════════════════════════════════════════════════════════════════════

def test_el_preview_devuelve_el_motivo_real_del_fallo():
    """previewSrc debe devolver {src, error}: si el fetch falla, el error
    se conoce y se puede mostrar."""
    js = _read(os.path.join(ROOT, "app", "static", "js", "app.js"))
    i = js.find("async function previewSrc(url)")
    assert i != -1, "no se encontró previewSrc en app.js"
    bloque = js[i:i + 1600]
    assert "return { src: url, error:" in bloque, (
        "previewSrc debe devolver el error real cuando la descarga falla"
    )
    assert "if (!res.ok) return url;" not in bloque, (
        "el preview no puede caer en silencio a una URL que el <img> no "
        "puede autenticar"
    )


def test_el_preview_muestra_el_motivo_y_no_la_url_como_culpa():
    js = _read(os.path.join(ROOT, "app", "static", "js", "app.js"))
    assert "La URL puede haber cambiado o el archivo ya no existe" not in js, (
        "ese mensaje culpaba siempre a la URL, aunque el problema fuera otro"
    )
    assert "function previewErrorMessage(err)" in js
    for esperado in ("st === 401", "st === 403", "st === 404", "st === 0", "st >= 500"):
        assert esperado in js, (
            f"el preview debe distinguir el status {esperado!r}"
        )
    assert "Vuelve a subirlo" in js or "Vuelve a subir" in js, (
        "el preview debe indicar que la imagen se puede volver a subir"
    )


def test_el_preview_conserva_la_url_directa_como_plan_b():
    """Con el fix del cookie, la URL directa vuelve a ser utilizable."""
    js = _read(os.path.join(ROOT, "app", "static", "js", "app.js"))
    i = js.find("async function previewSrc(url)")
    bloque = js[i:i + 1600]
    assert "sin token" in bloque.lower() or "Sin token" in bloque, (
        "sin token en localStorage se debe usar la URL directa (cookie)"
    )


# ════════════════════════════════════════════════════════════════════════
# 4. deps: los helpers de cookie
# ════════════════════════════════════════════════════════════════════════

def test_deps_expone_los_helpers_de_cookie():
    deps = _read(os.path.join(ROOT, "app", "deps.py"))
    assert "def get_current_user_allow_cookie(" in deps
    assert "def get_current_membership_allow_cookie(" in deps
    assert 'ACCESS_COOKIE_NAME = "wowhub_access_token"' in deps


def test_get_current_user_sigue_exigiendo_el_header_authorization():
    """El cambio de cookie NO debe relajar la API: sin header y sin cookie
    sigue siendo 401."""
    deps = _read(os.path.join(ROOT, "app", "deps.py"))
    i = deps.find("def get_current_user(")
    bloque = deps[i:i + 900]
    assert "get_current_user_allow_cookie" not in bloque, (
        "get_current_user no debe aceptar cookies: sólo lo hacen las "
        "variantes *_allow_cookie"
    )


def test_el_logo_de_la_campana_se_reescribe_en_la_ruta_publica(client, db_session, storage_tmp):
    """La tarjeta del cliente es PÚBLICA: la URL autenticada del logo
    daba 401. Debe reescribirse a /api/v1/public/t/{slug}/media/{id}."""
    from app.models.loyalty_pass import LoyaltyCampaign

    t = _mk_tenant(db_session, f"c-{uuid.uuid4().hex[:8]}")
    up = _subir(db_session, t, filename="logo.png", purpose="loyalty_campaign_logo")
    db_session.add(LoyaltyCampaign(
        tenant_id=str(t.id),
        name="Campaña de prueba",
        reward_label="Café gratis",
        stamps_required=6,
        logo_url=up.url,
        is_active=True,
    ))
    db_session.commit()

    r = client.get(f"/api/v1/loyalty/c/{t.slug}/campaign")
    assert r.status_code == 200, r.text
    logo = r.json()["campaign"]["logo_url"]
    assert logo == f"/api/v1/public/t/{t.slug}/media/{up.id}", (
        f"el logo de la campaña debe servirse por la ruta pública: {logo!r}"
    )


def test_el_script_de_diagnostico_de_archivos_faltantes_existe():
    path = os.path.join(ROOT, "scripts", "check_missing_uploads.py")
    assert os.path.isfile(path)
    src = _read(path)
    assert "check_missing_uploads" in src or "uploads" in src
    assert "unlink" not in src, "el script es de sólo lectura: no debe borrar nada"
