"""Regresión V2.013 (2026-10-24) — menús "Administración" y "SUPER ADMIN".

Defectos reportados por el usuario:
  1. El menú "Administración" (Admin IA + Observabilidad) no aparecía para el
     dueño ni para el admin del tenant.
  2. El menú "SUPER ADMIN" nunca aparecía, ni siquiera para superusuarios
     reales de la plataforma.

Causas raíz corregidas:
  * Cliente: ``applyRoleGuards`` leía el rol de ``user.default_role`` (que es
    sólo el rol por defecto de las membresías nuevas y tiene default STAFF)
    en vez de la membresía del tenant activo (``current_tenant.role`` /
    ``current_tenant.is_owner``).
  * Cliente: el claim ``is_superuser`` se leía con ``atob()`` sobre un
    payload base64url SIN padding → ``InvalidCharacterError`` silencioso →
    ``isSuperuser`` quedaba siempre en ``false``.
  * Cliente: el guard eliminaba los items del DOM (``el.remove()``) en vez de
    ocultarlos, así que un fallo transitorio de sesión borraba el menú.
  * Servidor: los guards de ``/admin/ai`` y ``/dashboard/admin-observability``
    comparaban contra ``user.default_role`` → 302 ``admin_forbidden`` al
    propio dueño del negocio.

Cada test fija el comportamiento para que el defecto no vuelva a aparecer.
"""
from __future__ import annotations

import io
import os
import re
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, "app", "templates")


def _read(path: str) -> str:
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def _base_html() -> str:
    return _read(os.path.join(TPL, "dashboard", "base.html"))


def _app_js() -> str:
    return _read(os.path.join(ROOT, "app", "static", "js", "app.js"))


def _main_py() -> str:
    return _read(os.path.join(ROOT, "app", "main.py"))


def _deps_py() -> str:
    return _read(os.path.join(ROOT, "app", "deps.py"))


def _guard_rol(html: str) -> str:
    """Extrae el bloque de ``applyRoleGuards`` del sidebar."""
    i = html.find("async function applyRoleGuards()")
    assert i != -1, "no se encontró applyRoleGuards en el sidebar del dashboard"
    j = html.find("})();", i)
    assert j != -1, "applyRoleGuards no está cerrado correctamente"
    return html[i:j]


# ════════════════════════════════════════════════════════════════════════
# 1. Sidebar — las secciones "Administración" y "SUPER ADMIN" existen
# ════════════════════════════════════════════════════════════════════════

def test_sidebar_tiene_la_seccion_administracion():
    """Debe existir el encabezado "Administración" con el gate owner,admin."""
    html = _base_html()
    m = re.search(r"<h4([^>]*)>\s*Administración\s*</h4>", html)
    assert m, "no existe el encabezado de la sección Administración en el sidebar"
    attrs = m.group(1)
    assert 'data-requires-role="owner,admin"' in attrs, (
        "el encabezado Administración debe llevar el mismo gate que sus items"
    )
    assert "display:none" in attrs, (
        "el encabezado debe nacer oculto: el guard del cliente lo muestra"
    )


def test_sidebar_tiene_la_seccion_super_admin():
    """Debe existir el encabezado "SUPER ADMIN" con el gate superuser."""
    html = _base_html()
    m = re.search(r"<h4([^>]*)>\s*SUPER ADMIN\s*</h4>", html)
    assert m, "no existe el encabezado de la sección SUPER ADMIN en el sidebar"
    attrs = m.group(1)
    assert 'data-requires-role="superuser"' in attrs, (
        "el encabezado SUPER ADMIN sólo puede abrirse a superusuarios"
    )
    assert "display:none" in attrs


def test_items_de_administracion_conservan_su_gate():
    """Admin IA y Observabilidad siguen con gate owner,admin y ocultos."""
    html = _base_html()
    for href, etiqueta in (
        ("/admin/ai", "Admin IA"),
        ("/dashboard/admin-observability", "Observabilidad"),
    ):
        idx = html.find(f'href="{href}"')
        assert idx != -1, f"falta el item {etiqueta} ({href}) en el sidebar"
        bloque = html[idx:idx + 420]
        assert 'data-requires-role="owner,admin"' in bloque, (
            f"{etiqueta} perdió el gate owner,admin"
        )
        assert "display:none" in bloque, f"{etiqueta} debe nacer oculto"


def test_item_superadmin_conserva_su_gate():
    """El link a /admin/superadmin sigue con gate superuser."""
    html = _base_html()
    idx = html.find('href="/admin/superadmin"')
    assert idx != -1, "falta el link a /admin/superadmin en el sidebar"
    bloque = html[idx:idx + 420]
    assert 'data-requires-role="superuser"' in bloque
    assert "display:none" in bloque


def test_api_docs_no_queda_colgando_de_una_seccion_privilegiada():
    """"API Docs" debe quedar antes de los encabezados con gate.

    Si quedara después, un superusuario vería "API Docs" colgando de la
    sección SUPER ADMIN y un owner lo vería colgando de Administración.
    """
    html = _base_html()
    idx_docs = html.find('href="/docs"')
    idx_admin = html.find(">Administración</h4>")
    idx_super = html.find(">SUPER ADMIN</h4>")
    assert idx_docs != -1, "no se encontró el link de API Docs"
    assert idx_admin != -1 and idx_super != -1
    assert idx_docs < idx_admin, (
        "API Docs debe quedar antes del encabezado Administración"
    )
    assert idx_docs < idx_super, (
        "API Docs debe quedar antes del encabezado SUPER ADMIN"
    )


# ════════════════════════════════════════════════════════════════════════
# 2. Cliente — el guard resuelve el rol real y NO borra el menú
# ════════════════════════════════════════════════════════════════════════

def test_el_guard_ya_no_elimina_los_items_del_dom():
    """El guard debe OCULTAR, nunca eliminar: un fallo transitorio de
    sesión ya no puede borrar el menú de forma permanente."""
    guard = _guard_rol(_base_html())
    assert "el.remove()" not in guard, (
        "el guard sigue eliminando los items del DOM: un fallo transitorio "
        "de sesión dejaría el menú sin Administrators"
    )
    assert 'el.style.display = visible ? "" : "none"' in guard, (
        "el guard debe alternar display:none en vez de remover el nodo"
    )


def test_el_guard_usa_el_rol_de_la_membresia_del_tenant():
    """La fuente de verdad del rol es la membresía del tenant activo."""
    guard = _guard_rol(_base_html())
    assert "tenant.is_owner" in guard, "el guard debe considerar tenant.is_owner"
    assert "tenant.role" in guard, "el guard debe leer tenant.role"
    i_tenant = guard.find("tenant.role")
    i_default = guard.find("user.default_role")
    assert i_default != -1, "se esperaba un fallback a user.default_role"
    assert i_tenant < i_default, (
        "el rol de la membresía debe evaluarse ANTES del fallback a "
        "user.default_role (que por defecto es STAFF)"
    )


def test_el_guard_usa_el_decoder_jwt_del_app():
    """El claim is_superuser se lee con el decodificador base64url con
    padding (WH.Jwt), no con un atob() crudo."""
    guard = _guard_rol(_base_html())
    assert "WH.Jwt" in guard, "el guard debe decodificar el token con WH.Jwt"
    assert "is_superuser" in guard


def test_app_js_expone_el_decoder_jwt():
    """app.js debe exportar el decodificador base64url con padding."""
    js = _app_js()
    assert "const Jwt = {" in js
    assert "TokenStore, Jwt," in js, "WH.Jwt no está exportado en window.WH"


def test_el_decoder_jwt_restaura_el_padding_base64url():
    """Sin padding, atob() lanza InvalidCharacterError y el claim se pierde."""
    js = _app_js()
    assert 'replace(/-/g, "+")' in js
    assert 'replace(/_/g, "/")' in js
    assert 'while (b64.length % 4 !== 0) b64 += "="' in js, (
        "el decodificador debe restaurar el padding base64url"
    )


def test_el_banner_de_impersonacion_usa_el_decoder_con_padding():
    """El banner de impersonación tenía el mismo bug de base64url."""
    html = _base_html()
    i = html.find("function decodeJwtPayload(token)")
    assert i != -1, "no se encontró decodeJwtPayload en el sidebar"
    bloque = html[i:i + 900]
    assert "WH.Jwt" in bloque, "decodeJwtPayload debe delegar en WH.Jwt"
    assert 'while (b64.length % 4 !== 0) b64 += "="' in bloque, (
        "el fallback local también debe restaurar el padding"
    )


# ════════════════════════════════════════════════════════════════════════
# 3. Servidor — el rol se resuelve desde la membresía
# ════════════════════════════════════════════════════════════════════════

def test_deps_expone_el_resolutor_de_rol_efectivo():
    """app.deps debe exponer el helper canónico de rol efectivo."""
    deps = _deps_py()
    assert "def resolve_effective_tenant_role(" in deps
    i = deps.find("def resolve_effective_tenant_role(")
    bloque = deps[i:i + 2200]
    assert "TenantMembership" in bloque, (
        "el helper debe leer el rol de TenantMembership"
    )
    assert "is_active" in bloque, "sólo debe contar membresías activas"


def test_main_ya_no_autoriza_con_default_role():
    """Los guards no pueden volver a comparar contra user.default_role."""
    main = _main_py()
    assert 'getattr(user, "default_role"' not in main, (
        "los guards de administración siguen usando user.default_role "
        "(default STAFF) como criterio de autorización"
    )


def test_los_guards_de_administracion_usan_el_rol_de_membresia():
    """Ambas rutas de administración deben usar el helper de membresía."""
    main = _main_py()
    assert main.count("resolve_effective_tenant_role(db, user, payload)") >= 2, (
        "las rutas /admin/ai y /dashboard/admin-observability deben resolver "
        "el rol por membresía"
    )
    assert "admin_forbidden" in main


def test_el_guard_de_superadmin_sigue_exigiendo_superuser():
    """El guard de /admin/superadmin NO se relajó."""
    main = _main_py()
    i = main.find("def superadmin_page(")
    assert i != -1, "no se encontró la ruta /admin/superadmin"
    bloque = main[i:i + 2600]
    assert "is_superuser" in bloque
    assert "superadmin_forbidden" in bloque


# ════════════════════════════════════════════════════════════════════════
# 4. Funcional — resolución del rol efectivo contra la BD
# ════════════════════════════════════════════════════════════════════════

def _mk_user(db, email, default_role=None, is_superuser=False):
    from app.models.user import User, UserRole
    from app.security import hash_password

    u = User(
        email=email,
        password_hash=hash_password("test-password-123"),
        full_name="Usuario de prueba",
        default_role=default_role if default_role is not None else UserRole.STAFF,
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


def _mk_membership(db, user, tenant, role, is_owner=False, is_active=True):
    from app.models.tenant import TenantMembership

    m = TenantMembership(
        id=uuid.uuid4(),
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        role=role,
        is_owner=is_owner,
        is_active=is_active,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def test_el_dueno_con_default_role_staff_resuelve_owner(db_session):
    """REGRESIÓN: el dueño del negocio tiene default_role=STAFF.

    Antes se leía ese campo y el guard lo trataba como empleado, así que el
    menú "Administración" nunca le aparecía.
    """
    from app.deps import resolve_effective_tenant_role
    from app.models.user import UserRole

    u = _mk_user(db_session, f"owner-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.OWNER, is_owner=True)

    rol = resolve_effective_tenant_role(db_session, u, {"tid": str(t.id)})
    assert rol == "owner"


def test_el_admin_de_tenant_resuelve_admin(db_session):
    from app.deps import resolve_effective_tenant_role
    from app.models.user import UserRole

    u = _mk_user(db_session, f"admin-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.ADMIN)

    rol = resolve_effective_tenant_role(db_session, u, {"tid": str(t.id)})
    assert rol == "admin"


def test_el_empleado_no_califica(db_session):
    from app.deps import resolve_effective_tenant_role
    from app.models.user import UserRole

    u = _mk_user(db_session, f"staff-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.STAFF)

    rol = resolve_effective_tenant_role(db_session, u, {"tid": str(t.id)})
    assert rol == "staff"
    assert rol not in ("owner", "admin")


def test_el_tenant_activo_manda_sobre_las_demas_membresias(db_session):
    """Ser owner en el tenant A no habilita el menú si en el tenant activo B
    el usuario es sólo empleado."""
    from app.deps import resolve_effective_tenant_role
    from app.models.user import UserRole

    u = _mk_user(db_session, f"multi-{uuid.uuid4().hex[:8]}@example.com")
    t_a = _mk_tenant(db_session, f"a-{uuid.uuid4().hex[:8]}")
    t_b = _mk_tenant(db_session, f"b-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t_a, UserRole.OWNER, is_owner=True)
    _mk_membership(db_session, u, t_b, UserRole.STAFF)

    rol = resolve_effective_tenant_role(db_session, u, {"tid": str(t_b.id)})
    assert rol == "staff"


def test_el_flag_is_owner_gana_al_rol_de_membresia(db_session):
    """`is_owner` manda sobre el campo role (mismo criterio que require_role)."""
    from app.deps import resolve_effective_tenant_role
    from app.models.user import UserRole

    u = _mk_user(db_session, f"flag-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.ADMIN, is_owner=True)

    rol = resolve_effective_tenant_role(db_session, u, {"tid": str(t.id)})
    assert rol == "owner"


def test_sin_membresia_se_usa_el_claim_del_jwt(db_session):
    """Sin membresías activas se cae al claim `role` del token."""
    from app.deps import resolve_effective_tenant_role

    u = _mk_user(db_session, f"claim-{uuid.uuid4().hex[:8]}@example.com")
    rol = resolve_effective_tenant_role(db_session, u, {"role": "admin"})
    assert rol == "admin"


def test_sin_membresia_ni_claim_se_usa_el_default_role(db_session):
    """Último recurso: `user.default_role`."""
    from app.deps import resolve_effective_tenant_role
    from app.models.user import UserRole

    u = _mk_user(db_session, f"def-{uuid.uuid4().hex[:8]}@example.com",
                 default_role=UserRole.VIEWER)
    rol = resolve_effective_tenant_role(db_session, u, {})
    assert rol == "viewer"


def test_la_membresia_inactiva_no_habilita_nada(db_session):
    """Una membresía dada de baja no abre el menú de administración."""
    from app.deps import resolve_effective_tenant_role
    from app.models.user import UserRole

    u = _mk_user(db_session, f"inact-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.OWNER, is_owner=True, is_active=False)

    rol = resolve_effective_tenant_role(db_session, u, {"tid": str(t.id)})
    assert rol not in ("owner", "admin")


# ════════════════════════════════════════════════════════════════════════
# 5. Funcional HTTP — los guards de las rutas de administración
# ════════════════════════════════════════════════════════════════════════

def _token_para(user, tenant, role, is_superuser=False):
    from app.security import create_access_token

    return create_access_token(
        user.id,
        tenant_id=tenant.id,
        role=role,
        extra_claims={"is_superuser": bool(is_superuser)},
    )


def test_admin_ai_es_accesible_para_el_dueno_del_tenant(client, db_session):
    """REGRESIÓN HTTP: el dueño recibía 302 admin_forbidden."""
    from app.models.user import UserRole

    u = _mk_user(db_session, f"http-owner-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.OWNER, is_owner=True)

    tk = _token_para(u, t, "owner")
    r = client.get("/admin/ai", headers={"Authorization": f"Bearer {tk}"})
    assert r.status_code == 200, f"el dueño del tenant no puede abrir /admin/ai: {r.status_code}"


def test_admin_ai_es_accesible_para_el_admin_del_tenant(client, db_session):
    from app.models.user import UserRole

    u = _mk_user(db_session, f"http-admin-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.ADMIN)

    tk = _token_para(u, t, "admin")
    r = client.get("/admin/ai", headers={"Authorization": f"Bearer {tk}"})
    assert r.status_code == 200


def test_admin_ai_bloquea_al_empleado(client, db_session):
    from app.models.user import UserRole

    u = _mk_user(db_session, f"http-staff-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.STAFF)

    tk = _token_para(u, t, "staff")
    r = client.get("/admin/ai", headers={"Authorization": f"Bearer {tk}"},
                   follow_redirects=False)
    assert r.status_code == 302, "un empleado no puede abrir /admin/ai"
    assert "reason=admin_forbidden" in r.headers.get("location", "")


def test_observability_es_accesible_para_el_admin_del_tenant(client, db_session):
    from app.models.user import UserRole

    u = _mk_user(db_session, f"http-obs-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.ADMIN)

    tk = _token_para(u, t, "admin")
    r = client.get("/dashboard/admin-observability",
                   headers={"Authorization": f"Bearer {tk}"})
    assert r.status_code == 200


def test_observability_bloquea_al_lector(client, db_session):
    from app.models.user import UserRole

    u = _mk_user(db_session, f"http-view-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.VIEWER)

    tk = _token_para(u, t, "viewer")
    r = client.get("/dashboard/admin-observability",
                   headers={"Authorization": f"Bearer {tk}"},
                   follow_redirects=False)
    assert r.status_code == 302
    assert "reason=admin_forbidden" in r.headers.get("location", "")


def test_superadmin_abre_para_un_superusuario(client, db_session):
    """El menú SUPER ADMIN debe llevar a una página que sí responde."""
    from app.models.user import UserRole

    u = _mk_user(db_session, f"http-su-{uuid.uuid4().hex[:8]}@example.com",
                 is_superuser=True)
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.OWNER, is_owner=True)

    tk = _token_para(u, t, "owner", is_superuser=True)
    r = client.get("/admin/superadmin", headers={"Authorization": f"Bearer {tk}"})
    assert r.status_code == 200


def test_superadmin_bloquea_a_un_admin_normal(client, db_session):
    """El guard de superusuario NO se relajó."""
    from app.models.user import UserRole

    u = _mk_user(db_session, f"http-nosu-{uuid.uuid4().hex[:8]}@example.com")
    t = _mk_tenant(db_session, f"t-{uuid.uuid4().hex[:8]}")
    _mk_membership(db_session, u, t, UserRole.OWNER, is_owner=True)

    tk = _token_para(u, t, "owner")
    r = client.get("/admin/superadmin", headers={"Authorization": f"Bearer {tk}"},
                   follow_redirects=False)
    assert r.status_code == 302
    assert "reason=superadmin_forbidden" in r.headers.get("location", "")


@pytest.mark.parametrize("ruta", ["/admin/ai", "/dashboard/admin-observability"])
def test_las_rutas_de_administracion_exigen_sesion(client, ruta):
    """Sin token se redirige al login, no se renderiza la página."""
    r = client.get(ruta, follow_redirects=False)
    assert r.status_code == 302
    assert "reason=admin_auth" in r.headers.get("location", "")
