"""Regresión Bug 2 y Bug 3 (2026-10-21) — dashboard: rutas y orden de scripts.

Bug 2 — Mesero Virtual
    ``/dashboard/mesero`` moría con:
        TypeError: Cannot read properties of undefined (reading 'Auth')
    Causa: el JS inline estaba dentro de ``{% block dash_content %}``, que se
    materializa en ``base.html:84`` (dentro de ``<main>``), ANTES de
    ``<script src="/static/js/app.js">`` (``base.html:87``). Como ``app.js`` es
    quien define ``window.WH``, el IIFE del mesero se ejecutaba con
    ``window.WH === undefined``.

Bug 3 — /dashboard/templates
    El commit ``9ea9bec`` sobrescribió ``app/main.py`` con una versión
    anterior a V2.01 y borró 6 rutas (entre ellas ``/dashboard/templates``),
    que devolvían 404 → la página pública mostraba
    "El negocio "" no existe o está inactivo".

Estos tests fijan:
  1. Las 6 rutas restauradas existen y responden con el status correcto.
  2. ``/dashboard/templates`` renderiza con sus 4 plantillas.
  3. Ningún bloque ``<script>`` usa ``WH.*`` sin guard antes de ``app.js``.
  4. ``/dashboard/orders`` conserva el bloque ``scripts`` del padre (``super()``).
"""
from __future__ import annotations

import re

import pytest

# Rutas restauradas: (ruta, status esperado, Location esperado o None)
RUTAS_RESTAURADAS = [
    ("/dashboard/templates", 200, None),
    ("/dashboard/v1", 200, None),
    ("/dashboard/settings", 307, "/dashboard/templates"),
    ("/dashboard/production", 307, "/dashboard/kds"),
    ("/dashboard/analytics", 307, "/dashboard/stats"),
    ("/pricing", 307, "/#pricing"),
]

PAGES_DASHBOARD = [
    "/dashboard/mesero",
    "/dashboard/orders",
    "/dashboard/customers",
    "/dashboard/products",
    "/dashboard/templates",
    "/dashboard/kds/",
    "/dashboard/marketing",
    "/dashboard/loyalty/scanner",
    "/dashboard/onboarding",
    "/dashboard/inventory",
    "/dashboard/customer-360",
    "/dashboard/stats",
    "/dashboard/quotes",
    "/dashboard/notifications",
    "/dashboard/pipeline",
    "/dashboard/landing",
    "/dashboard/costs",
    "/dashboard/webhooks",
    "/dashboard/ai",
]

APP_JS = '<script src="/static/js/app.js'
USO_WH = re.compile(
    r"(?:window\.)?\bWH\.(Auth|api|TokenStore|Toast|Upload|ImagePicker)\b"
)
SCRIPT_BLOCK = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
LINE_COMMENT = re.compile(r"//[^\n]*")


def _unguarded_uses(js: str) -> list:
    """Usos de WH sin guard, ignorando comentarios HTML y de una línea."""
    js = HTML_COMMENT.sub("", js)
    js = LINE_COMMENT.sub("", js)
    out = []
    for m in USO_WH.finditer(js):
        prefix = js[max(0, m.start() - 130):m.start()]
        if "WH &&" in prefix or "&& window.WH" in prefix:
            continue
        out.append(m.group(0))
    return out


@pytest.mark.parametrize(("ruta", "status", "location"), RUTAS_RESTAURADAS)
def test_ruta_restaurada(client, ruta, status, location):
    """Las 6 rutas perdidas en 9ea9bec deben volver a existir."""
    resp = client.get(ruta, follow_redirects=False)
    assert resp.status_code == status, f"{ruta} devolvió {resp.status_code}"
    if location is not None:
        assert resp.headers.get("location") == location


def test_dashboard_templates_renderiza_4_plantillas(client):
    """La página de Apariencia debe renderizar con sus 4 tarjetas."""
    resp = client.get("/dashboard/templates", follow_redirects=False)
    assert resp.status_code == 200
    for nombre in ("Moderna", "WowPrint", "Dark", "Default"):
        assert nombre in resp.text, f"falta la plantilla {nombre}"


def test_dashboard_templates_no_usa_url_for_static(client):
    """``url_for('static', filename=...)`` lanza NoMatchFound en Starlette.

    Starlette exige ``path=`` en ``Mount.url_path_for``; con ``filename=``
    la página devolvía 500 en vez de 200.
    """
    resp = client.get("/dashboard/templates", follow_redirects=False)
    assert resp.status_code == 200
    assert "url_for('static'" not in resp.text
    assert "/static/css/templates/dashboard.css" in resp.text


@pytest.mark.parametrize("ruta", PAGES_DASHBOARD)
def test_pagina_dashboard_renderiza(client, ruta):
    """Todas las páginas del dashboard deben renderizar sin error 500."""
    resp = client.get(ruta, follow_redirects=True)
    assert resp.status_code == 200, f"{ruta} devolvió {resp.status_code}"


@pytest.mark.parametrize("ruta", PAGES_DASHBOARD)
def test_orden_carga_scripts(client, ruta):
    """Ningún bloque ``<script>`` puede usar ``WH`` antes de que cargue app.js."""
    body = client.get(ruta, follow_redirects=True).text
    app_js_pos = body.find(APP_JS)
    assert app_js_pos != -1, f"{ruta}: no se encontró app.js en el HTML"

    for m in SCRIPT_BLOCK.finditer(body):
        uses = _unguarded_uses(m.group(1))
        if not uses:
            continue
        assert m.start() > app_js_pos, (
            f"{ruta}: un bloque <script> usa {sorted(set(uses))} y se ejecuta "
            f"antes de app.js ({app_js_pos})"
        )


def test_mesero_js_esta_en_dash_scripts():
    """El JS del mesero debe vivir en ``dash_scripts``, no en ``dash_content``.

    ``dash_content`` se renderiza dentro de ``<main>`` (antes de app.js);
    ``dash_scripts`` se renderiza al final del ``<body>`` (después de app.js).
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "templates" / "dashboard" / "mesero.html"
    ).read_text(encoding="utf-8")

    assert "{% block dash_scripts %}" in src
    # El JS del mesero debe estar DESPUÉS del cierre de dash_content.
    idx_scripts = src.index("{% block dash_scripts %}")
    idx_init = src.index("/* ── Mesero Virtual JS")
    assert idx_init > idx_scripts, "el JS del mesero sigue dentro de dash_content"


def test_orders_conserva_scripts_del_padre(client):
    """``orders.html`` debe llamar ``super()`` en su bloque ``scripts``.

    Sin ``super()`` la página perdía ``ai.js``, ``ai-context.js``,
    ``WH.Auth.requireLogin()``, el listener del botón "Salir" y
    ``dashboard-compat.js``.
    """
    body = client.get("/dashboard/orders", follow_redirects=True).text

    for marker in (
        "ai.js",
        "ai-context.js",
        "dashboard-compat.js",
        "requireLogin",
    ):
        assert marker in body, f"/dashboard/orders perdió {marker}"

    # Y debe conservar su propio JS de creación inline de pedidos.
    for marker in (
        "openNewOrderModal",
        "submitNewOrder",
        "newOrderAddItemRow",
        "wcRefreshProductoSelect",
        "wcRefreshClienteSelect",
    ):
        assert marker in body, f"/dashboard/orders perdió {marker}"
