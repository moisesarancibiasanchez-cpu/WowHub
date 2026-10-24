"""Regresión V2.012 (2026-10-24) — 9 defectos reportados por el usuario.

1. Modales con panel negro translúcido (texto ilegible).
2. "⚡ Recalcular RFM" → HTTP 403 (role:OWNER no puede 'write' sobre 'customer').
3. Menú Cocina (KDS) con ``target="_blank"``.
4. Imágenes de la landing que no cargaban.
5. Botón "+ Crear pedido" sin acción.
6. Inventario sin ocupar el 100% del MAIN.
7. Cotizaciones sin ocupar el 100% del MAIN (y sin previsualización al crear).
8. Asistente IA sin ocupar el 100% del MAIN.
9. "❌ Mis Plugins Instalados" → "Error al cargar tus plugins."
10. Menú PIPELINE que en realidad llevaba a Pedidos.
11. Menú Webhooks sin explicación de su utilidad.

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
CSS = os.path.join(ROOT, "app", "static", "css")


def _read(path: str) -> str:
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def _template(*parts: str) -> str:
    return _read(os.path.join(TPL, *parts))


# ════════════════════════════════════════════════════════════════════════
# 1. Modales: el PANEL es blanco, el VELO es oscuro
# ════════════════════════════════════════════════════════════════════════

def test_modales_no_pintan_de_oscuro_el_dialog():
    """``[role="dialog"]`` no puede repintar de negro el panel del modal.

    El modal reutilizable de app.js (``.wh-modal-dialog``) tiene
    ``role="dialog"``. Su regla base es blanca (specificity 0,1,0) y la del
    tema era (0,2,0), así que ganaba el fondo oscuro y el texto quedaba
    ilegible.
    """
    css = _read(os.path.join(CSS, "templates", "dashboard.css"))
    regla_oscura = re.search(
        r"\.template-moderna[^{]*\{[^}]*rgba\(11,\s*13,\s*18[^}]*\}", css
    )
    assert regla_oscura, "no se encontró la regla del velo oscuro"
    assert "[role=\"dialog\"]" not in regla_oscura.group(0), (
        "la regla del velo sigue aplicando a [role=dialog] y repinta el "
        "panel del modal de negro translúcido"
    )


def test_modales_tienen_regla_de_panel_blanco():
    """Debe existir la regla que deja los paneles en blanco con texto oscuro."""
    css = _read(os.path.join(CSS, "templates", "dashboard.css"))
    assert re.search(
        r"\.template-moderna[^{]*\.wh-modal-dialog\s*\{[^}]*background:\s*#ffffff",
        css,
    ), "no se encontró la regla de panel blanco para .wh-modal-dialog"
    assert re.search(
        r"\.template-moderna[^{]*\.wh-modal-dialog\s*\{[^}]*color:\s*#172033",
        css,
    ), "el panel blanco debe llevar texto oscuro explícito"


def test_modal_marketplace_es_blanco():
    """El modal del marketplace ya no es #1e1e2e."""
    html = _template("dashboard", "marketplace.html")
    bloque = re.search(r"\.mp-modal\s*\{[^}]*\}", html)
    assert bloque, "no se encontró el estilo .mp-modal"
    assert "background: #ffffff" in bloque.group(0)


# ════════════════════════════════════════════════════════════════════════
# 2. Layout: las páginas ocupan el 100% del MAIN
# ════════════════════════════════════════════════════════════════════════

def test_layout_regla_grid_column_full():
    """Todo hijo directo de .dash-content que no sea widget hace span."""
    css = _read(os.path.join(CSS, "app.css"))
    regla = re.search(
        r"\.dash-content\s*>\s*:not\(\[data-widget-type\]\)\s*\{[^}]*\}", css
    )
    assert regla, "no se encontró la regla de span del contenido del dashboard"
    assert "grid-column: 1 / -1" in regla.group(0)


def test_layout_los_widgets_del_resumen_no_estan_afectados():
    """La regla debe EXCLUIR a los widgets del Resumen (tienen grid-area)."""
    css = _read(os.path.join(CSS, "app.css"))
    regla = re.search(
        r"\.dash-content\s*>\s*:not\(\[data-widget-type\]\)\s*\{[^}]*\}", css
    )
    assert ":not([data-widget-type])" in regla.group(0), (
        "si la regla no excluye a los widgets, el Resumen pierde su layout"
    )


# ════════════════════════════════════════════════════════════════════════
# 3. "+ Crear pedido" y el antipatrón del listener por referencia
# ════════════════════════════════════════════════════════════════════════

def test_orders_crear_pedido_usa_arrow_function():
    """El listener NO puede pasar la función por referencia.

    ``addEventListener("click", openNewOrderModal)`` se evaluaba al
    registrar, cuando la función todavía no estaba declarada (vivía en otro
    ``<script>``): ReferenceError que abortaba el script entero.
    """
    html = _template("dashboard", "orders.html")
    assert 'addEventListener("click", openNewOrderModal)' not in html, (
        "el listener sigue pasando la función por referencia"
    )
    assert re.search(
        r'addEventListener\(\s*"click"\s*,\s*\(\)\s*=>\s*openNewOrderModal\(\)\s*\)',
        html,
    ), "no se encontró el listener con arrow function"


def test_ningun_template_registra_una_funcion_declarada_mas_tarde():
    """Barrido genérico del antipatrón en todo el dashboard.

    Sólo cuenta como defecto el listener registrado en el NIVEL SUPERIOR
    de un ``<script>``: ahí la referencia se evalúa al registrar, y si la
    función se declara más abajo (o es un ``const`` en TDZ) todavía no
    existe → ReferenceError y el script se aborta.

    Un listener dentro de otra función se evalúa cuando esa función corre,
    y para entonces la declaración ya existe: no es un defecto.
    """
    from app.f0_baseline.js_parser import _find_matching_brace

    patron_listener = re.compile(
        r"addEventListener\(\s*['\"](?:click|input|change|submit)['\"]\s*,\s*"
        r"([A-Za-z_$][\w$]*)\s*\)"
    )
    # Declaraciones de función y asignaciones de flecha/función a const/let/var.
    patron_decl = re.compile(
        r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("
        r"|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?"
        r"(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>|"
        r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function"
    )
    patron_script = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S)

    offenses = []
    for dirpath, _dirs, files in os.walk(TPL):
        for name in files:
            if not name.endswith(".html"):
                continue
            path = os.path.join(dirpath, name)
            texto = _read(path)
            for bloque in patron_script.finditer(texto):
                js = bloque.group(1)

                # 1) Rangos de cuerpo de función: un listener dentro de
                #    ellos no se evalúa al registrar.
                cuerpos = []
                for m in re.finditer(r"function\s+[A-Za-z_$][\w$]*\s*\(", js):
                    abre = js.find("{", m.end())
                    if abre == -1:
                        continue
                    cierra = _find_matching_brace(js, abre)
                    if cierra:
                        cuerpos.append((abre, cierra))

                # 2) Posiciones de cada declaración.
                decls: dict[str, int] = {}
                for m in patron_decl.finditer(js):
                    nombre = m.group(1) or m.group(2) or m.group(3)
                    if nombre:
                        decls.setdefault(nombre, m.start())

                # 3) Listeners en el nivel superior.
                for m in patron_listener.finditer(js):
                    fn = m.group(1)
                    if fn not in decls:
                        continue
                    if any(abre < m.start() < cierra for abre, cierra in cuerpos):
                        continue  # está dentro de una función: es seguro
                    if decls[fn] > m.start():
                        linea = texto[: bloque.start(1) + m.start()].count("\n") + 1
                        offenses.append(
                            f"{os.path.relpath(path, ROOT)}:{linea} "
                            f"usa {fn} (declarada en la {js[: decls[fn]].count(chr(10)) + 1})"
                        )
    assert not offenses, "antipatrón de listener por referencia: " + "; ".join(offenses)


# ════════════════════════════════════════════════════════════════════════
# 4. Navegación: KDS, Pipeline y links internos
# ════════════════════════════════════════════════════════════════════════

def test_kds_no_abre_en_pestana_nueva():
    html = _template("dashboard", "base.html")
    link_kds = re.search(r'<a[^>]*href="/dashboard/kds/[^>]*>', html)
    assert link_kds, "no se encontró el link de Cocina (KDS)"
    assert "target=" not in link_kds.group(0), (
        "KDS sigue abriendo en una pestaña nueva"
    )


def test_menu_no_tiene_item_pipeline_duplicado():
    """/dashboard/pipeline es alias de Pedidos: no debe seguir en el menú."""
    html = _template("dashboard", "base.html")
    items = re.findall(r'<a[^>]*class="nav-link"[^>]*>', html)
    assert not any("/dashboard/pipeline" in i for i in items), (
        "el item Pipeline sigue en el menú y lleva a Pedidos"
    )
    assert any("/dashboard/orders" in i for i in items), "se perdió el item Pedidos"


def test_link_interno_a_costs_no_abre_en_pestana_nueva():
    html = _template("dashboard", "products.html")
    link = re.search(r'<a[^>]*href="/dashboard/costs"[^>]*>', html)
    assert link, "no se encontró el enlace a /dashboard/costs"
    assert "target=" not in link.group(0)


def test_no_quedan_links_internos_con_target_blank():
    """Ningún enlace a una RUTA INTERNA del dashboard abre otra pestaña.

    Se permiten (y son correctos) las aperturas en pestaña nueva de:
      - /docs (la documentación de la API)
      - las páginas públicas del tenant (landing, QR, sitio público)
      - los enlaces que se rellenan por JS (widgets, vista previa)

    Lo que NO puede pasar es un enlace a una ruta del propio dashboard
    (tipo /dashboard/...) abriendo en otra pestaña: saca al usuario del
    flujo sin avisar.
    """
    offenders = []
    for dirpath, _dirs, files in os.walk(os.path.join(TPL, "dashboard")):
        for name in files:
            if not name.endswith(".html"):
                continue
            path = os.path.join(dirpath, name)
            texto = _read(path)
            # Fuera los comentarios de Jinja y de HTML: no son enlaces.
            limpio = re.sub(r"\{#.*?#\}", "", texto, flags=re.S)
            limpio = re.sub(r"<!--.*?-->", "", limpio, flags=re.S)
            for m in re.finditer(r"<a\b[^>]*target\s*=\s*[\"']_blank[\"'][^>]*>", limpio):
                tag = m.group(0)
                href = re.search(r'href\s*=\s*["\']([^"\']*)', tag)
                href = href.group(1) if href else ""
                if not href.startswith("/dashboard/"):
                    continue
                offenders.append(
                    f"{os.path.relpath(path, ROOT)}:{limpio[: m.start()].count(chr(10)) + 1} "
                    f"href={href}"
                )
    assert not offenders, "links internos del dashboard con target=_blank: " + "; ".join(offenders)


# ════════════════════════════════════════════════════════════════════════
# 5. Marketplace: token httpOnly + orden de scripts
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "ruta",
    [
        os.path.join("dashboard", "marketplace.html"),
        os.path.join("superadmin", "marketplace_admin.html"),
    ],
)
def test_marketplace_no_lee_el_token_de_la_cookie(ruta):
    """La cookie wowhub_access_token es httpOnly: el JS no puede leerla."""
    html = _read(os.path.join(TPL, ruta))
    assert "document.cookie.match" not in html, (
        "sigue leyendo el token de document.cookie: siempre da una cabecera "
        "Authorization vacía y el API responde 401"
    )
    assert "TokenStore" in html, "no usa WH.TokenStore"


def test_marketplace_script_esta_fuera_del_bloque_de_contenido():
    """El script debe renderizarse DESPUÉS de app.js."""
    html = _template("dashboard", "marketplace.html")
    bloques = re.findall(r"\{%\s*block\s+(\w+)\s*%\}", html)
    assert "dash_scripts" in bloques, (
        "el script de marketplace sigue dentro del bloque de contenido, que "
        "se renderiza antes de app.js"
    )
    # El <script> real tiene que estar dentro del bloque dash_scripts.
    idx_scripts = html.find("{% block dash_scripts %}")
    idx_script = html.find("<script>", idx_scripts)
    assert idx_scripts != -1 and idx_script != -1


def test_marketplace_no_deja_scripts_inline_en_dash_content():
    """Ningún <script> inline puede quedar dentro del bloque de contenido."""
    html = _template("dashboard", "marketplace.html")
    ini = html.find("{% block dash_content %}")
    fin = html.find("{% endblock %}", ini)
    cuerpo = html[ini:fin]
    assert "<script" not in cuerpo, (
        "quedó un <script> dentro del bloque de contenido (se ejecuta antes "
        "de app.js)"
    )


# ════════════════════════════════════════════════════════════════════════
# 6. Webhooks: explicación y eventos reales
# ════════════════════════════════════════════════════════════════════════

def test_webhooks_explica_para_que_sirven():
    html = _template("dashboard", "webhooks.html")
    assert "¿Para qué sirve?" in html, "falta la explicación del menú Webhooks"
    assert "X-WowHub-Signature" in html, "no explica la firma HMAC"
    assert "HMAC" in html.upper()


def test_webhooks_lista_los_eventos_reales():
    html = _template("dashboard", "webhooks.html")
    for evento in (
        "on_order_created",
        "on_customer_created",
        "on_payment_received",
        "order.paid",
    ):
        assert evento in html, f"falta el evento real {evento}"


def test_webhooks_no_anuncia_eventos_inexistentes():
    """El placeholder anterior usaba eventos que la app nunca emite."""
    html = _template("dashboard", "webhooks.html")
    placeholder = re.search(r'id="wh-events"[^>]*placeholder="([^"]*)"', html)
    assert placeholder, "no se encontró el campo de eventos"
    for fantasma in ("order.created", "payment.confirmed"):
        assert fantasma not in placeholder.group(1), (
            f"el placeholder anuncia {fantasma}, que no se emite nunca"
        )


def test_eventos_de_webhook_coinciden_con_el_codigo():
    """Los eventos documentados tienen que existir en el código."""
    import glob
    fuentes = []
    for path in glob.glob(os.path.join(ROOT, "app", "**", "*.py"), recursive=True):
        fuentes.append(_read(path))
    codigo = "\n".join(fuentes)
    for evento in (
        "on_order_created",
        "on_customer_created",
        "on_payment_received",
        "order.paid",
    ):
        assert f'event="{evento}"' in codigo, (
            f"el evento {evento} está documentado pero la app no lo emite"
        )


# ════════════════════════════════════════════════════════════════════════
# 7. Cotizaciones: previsualización tras crear
# ════════════════════════════════════════════════════════════════════════

def test_quotes_abre_previsualizacion_al_crear():
    html = _template("dashboard", "quotes.html")
    bloque = re.search(r"async function saveQuote\(\)\s*\{.*?\n\}", html, re.S)
    assert bloque, "no se encontró saveQuote()"
    assert "viewQuote(" in bloque.group(0), (
        "tras crear una cotización no se abre su previsualización"
    )


# ════════════════════════════════════════════════════════════════════════
# 8. RBAC: el seed y la reparación del drift de tipo
# ════════════════════════════════════════════════════════════════════════

def test_rbac_el_seed_reconcilia_y_no_aborta_todo():
    """El seed no puede volver a tumbarse entero si una policy falla."""
    fuente = _read(os.path.join(ROOT, "app", "core", "rbac_seed.py"))
    assert "existing = session.query(RBACPolicy).count()" not in fuente, (
        "el seed vuelve a saltarse todo si la tabla no está vacía"
    )
    # Cada INSERT con su propio commit.
    assert fuente.count("session.commit()") >= 2, (
        "el seed debe confirmar cada policy por separado"
    )
    assert "rbac_policies quedó VACÍA" in fuente, (
        "el seed debe avisar en ERROR si la tabla queda vacía (todo denegado)"
    )


def test_rbac_migracion_es_idempotente():
    """La migración consulta el tipo real antes de alterar."""
    fuente = _read(
        os.path.join(ROOT, "alembic", "versions", "2026_10_24_fix_rbac_id_type.py")
    )
    assert "information_schema.columns" in fuente, (
        "la migración debe leer el tipo real de la columna antes de alterar"
    )
    assert "TYPE uuid" in fuente
    assert "SET DEFAULT now()" in fuente


def test_reconciliador_repara_tipos_y_defaults():
    """El reconciliador (capa autoritativa) debe reparar el drift de tipo."""
    fuente = _read(os.path.join(ROOT, "scripts", "reconcile_schema.py"))
    assert "_repair_column_types" in fuente
    assert "column_types_fixed" in fuente
    assert "column_defaults_fixed" in fuente
    assert "rtrim(" in fuente and "::uuid" in fuente


def test_reconciliador_detecta_char32_como_uuid():
    """Los helpers puros que decide el tipo a reparar."""
    import importlib
    mod = importlib.import_module("scripts.reconcile_schema")
    assert mod._live_is_char32("CHAR(32)") is True
    assert mod._live_is_char32("character varying(32)") is True
    assert mod._live_is_char32("uuid") is False
    assert mod._live_is_char32("VARCHAR(64)") is False


def test_modelo_guids_es_uuid_en_postgres():
    """GUID debe mapear a UUID nativo en PostgreSQL (no a CHAR(32)).

    Ese desajuste con la DDL cruda de la migración 0003 es lo que rompía
    el seed de permisos.
    """
    from sqlalchemy import Column
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateColumn

    from app.models.base import GUID

    ddl_pg = str(
        CreateColumn(Column("id", GUID())).compile(dialect=postgresql.dialect())
    )
    ddl_sqlite = str(
        CreateColumn(Column("id", GUID())).compile(dialect=sqlite.dialect())
    )
    assert "UUID" in ddl_pg, f"en PostgreSQL el DDL dio: {ddl_pg}"
    assert "CHAR(32)" in ddl_sqlite, f"en SQLite el DDL dio: {ddl_sqlite}"


# ════════════════════════════════════════════════════════════════════════
# 9. Media: las imágenes de la landing vuelven a cargar
# ════════════════════════════════════════════════════════════════════════

def test_uploads_busca_el_archivo_por_stored_filename():
    """En disco el archivo se llama stored_filename, no filename."""
    fuente = _read(os.path.join(ROOT, "app", "api", "v1", "uploads.py"))
    assert "upload.stored_filename" in fuente, (
        "el endpoint de contenido busca por upload.filename: el archivo nunca "
        "existe en disco con ese nombre"
    )
    # La ruta que se arma debe usar stored_filename (el nombre en disco).
    ruta = re.search(r"candidate\s*=\s*\(.*?\)\.resolve\(\)", fuente, re.S)
    assert ruta, "no se encontró la construcción de la ruta del archivo"
    assert "upload.stored_filename" in ruta.group(0), (
        "la ruta del archivo sigue usando el nombre original en vez del "
        "nombre en disco"
    )


def test_upload_service_guarda_una_url_que_existe():
    """La URL guardada no puede apuntar a /storage (ya no está montado)."""
    fuente = _read(os.path.join(ROOT, "app", "services", "upload_service.py"))
    # Se mira el CÓDIGO, no la documentación (que menciona el valor viejo
    # a propósito, para explicar el fix).
    codigo = "\n".join(
        linea for linea in fuente.splitlines()
        if not linea.strip().startswith("#")
    )
    codigo = re.sub(r'""".*?"""', "", codigo, flags=re.S)
    assert "/storage/" not in codigo, (
        "sigue guardando la URL /storage, que en producción no existe"
    )
    assert "/uploads/" in fuente and "/content" in fuente


def test_public_tiene_endpoint_de_media_por_slug():
    fuente = _read(os.path.join(ROOT, "app", "api", "v1", "public.py"))
    assert '/t/{slug}/media/{upload_id}' in fuente, (
        "falta el endpoint público de media por slug"
    )
    assert "_PUBLIC_MEDIA_PURPOSES" in fuente, (
        "la media pública debe estar restringida a usos públicos"
    )


def test_public_reescribe_las_urls_de_la_landing():
    """profile, landing, catalog, product y promotions reescriben la URL."""
    fuente = _read(os.path.join(ROOT, "app", "api", "v1", "public.py"))
    assert fuente.count("_public_media_url(") >= 6, (
        "las URLs de media no se reescriben en todos los endpoints públicos"
    )


def test_landing_publico_maneja_el_fallo_de_imagen():
    """El logo se oculta y el hero se precarga: nada de imágenes rotas."""
    html = _template("public", "landing.html")
    assert "onerror" in html, "el logo no tiene fallback si la imagen no carga"
    assert "probe.onload" in html, "el hero no precarga la imagen antes de aplicarla"


def test_imagepicker_preview_usa_el_bearer():
    """Un <img src> no puede mandar Authorization: el preview lo hace con fetch."""
    js = _read(os.path.join(ROOT, "app", "static", "js", "app.js"))
    assert "async function previewSrc" in js, (
        "el preview del ImagePicker no descarga la imagen autenticada"
    )
    assert "URL.createObjectURL" in js


# ════════════════════════════════════════════════════════════════════════
# 10. Endpoint público de media (funcional)
# ════════════════════════════════════════════════════════════════════════

def test_media_publica_404_si_no_existe(client):
    """Un upload inexistente responde 404 (no 500)."""
    resp = client.get(
        f"/api/v1/public/t/cualquiera/media/{uuid.uuid4()}", follow_redirects=False
    )
    assert resp.status_code in (404, 404), resp.status_code


def test_media_publica_no_sirve_archivos_de_otros_tenants(client, db_session):
    """Un upload de uso NO público responde 404 aunque exista."""
    from app.models.tenant import Tenant
    from app.models.upload import Upload

    tenant = Tenant(
        id=uuid.uuid4(),
        legal_name="Media SpA",
        display_name="Media",
        slug="media-test-tenant",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.flush()

    upload = Upload(
        id=uuid.uuid4(),
        tenant_id=str(tenant.id),
        filename="privado.png",
        stored_filename="abc123-privado.png",
        url="",
        storage_backend="local",
        content_type="image/png",
        size_bytes=10,
        purpose="general",  # NO es de uso público
    )
    db_session.add(upload)
    db_session.flush()
    upload_id = str(upload.id)

    resp = client.get(
        f"/api/v1/public/t/media-test-tenant/media/{upload_id}",
        follow_redirects=False,
    )
    assert resp.status_code == 404, resp.status_code
