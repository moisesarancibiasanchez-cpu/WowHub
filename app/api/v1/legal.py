"""Legal API — términos, privacidad, cookies."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.config import settings
from app.core.tenant_context import get_tenant

router = APIRouter(prefix="/legal", tags=["legal"])


@router.get("/terms", response_class=HTMLResponse, include_in_schema=False)
def terms_page(request: Request):
    return HTMLResponse(_render_legal_page(
        "Términos y Condiciones",
        "Bienvenido a WowHub. Al usar nuestra plataforma aceptas los siguientes términos:",
        [
            ("1. Aceptación", "Al crear una cuenta y usar WowHub, aceptas cumplir con estos términos."),
            ("2. Servicio", "WowHub provee una plataforma SaaS para que negocios creen páginas, catálogos, QRs y promociones."),
            ("3. Cuenta", "Eres responsable de mantener la seguridad de tu cuenta y contraseña."),
            ("4. Contenido", "Eres dueño del contenido que subes. No nos hacemos responsables por su uso."),
            ("5. Pagos", "Los planes pagos se renuevan automáticamente hasta que canceles."),
            ("6. Cancelación", "Puedes cancelar en cualquier momento desde tu panel."),
            ("7. Limitación de responsabilidad", "WowHub no se hace responsable por daños indirectos derivados del uso del servicio."),
        ],
    ))


@router.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
def privacy_page(request: Request):
    return HTMLResponse(_render_legal_page(
        "Política de Privacidad",
        "WowHub respeta tu privacidad. Esta política describe qué datos recopilamos y cómo los usamos:",
        [
            ("Datos que recopilamos", "Email, nombre, teléfono (opcional), datos de tu negocio y contenido que subes."),
            ("Uso de datos", "Para proveer y mejorar el servicio, enviar comunicaciones transaccionales, y soporte."),
            ("Compartir datos", "No vendemos tus datos. Solo compartimos con proveedores necesarios (MercadoPago, hosting, email)."),
            ("Cookies", "Usamos cookies para autenticación y analytics. Puedes deshabilitarlas desde tu navegador."),
            ("Tus derechos", "Puedes acceder, rectificar, eliminar o exportar tus datos en cualquier momento."),
            ("Retención", "Conservamos tus datos mientras tu cuenta esté activa y por 90 días después de eliminarla."),
            ("Contacto", "Para consultas de privacidad: privacy@wowhub.app"),
        ],
    ))


@router.get("/cookies", response_class=HTMLResponse, include_in_schema=False)
def cookies_page(request: Request):
    return HTMLResponse(_render_legal_page(
        "Política de Cookies",
        "WowHub usa cookies para mejorar tu experiencia:",
        [
            ("Cookies esenciales", "Necesarias para autenticación y seguridad. No se pueden deshabilitar."),
            ("Cookies de preferencia", "Recuerdan tu idioma, tema y configuración."),
            ("Cookies de analytics", "Nos ayudan a entender cómo usas el servicio para mejorarlo."),
            ("Cookies de marketing", "Usadas para mostrar contenido relevante (opcional)."),
            ("Gestión", "Puedes deshabilitar cookies no esenciales desde la configuración de tu navegador."),
        ],
    ))


def _render_legal_page(title: str, intro: str, sections: list[tuple[str, str]]) -> str:
    sections_html = "\n".join(f"""
        <section style="margin-bottom:24px">
            <h3 style="color:#7c5cff">{h}</h3>
            <p>{p}</p>
        </section>
    """ for h, p in sections)
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="utf-8">
        <title>{title} — WowHub</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: -apple-system, sans-serif; max-width: 720px; margin: 0 auto; padding: 40px 20px; line-height: 1.6; color: #2d3748; }}
            h1 {{ color: #1a202c; }}
            .intro {{ color: #4a5568; padding: 16px; background: #f7fafc; border-left: 4px solid #7c5cff; margin: 24px 0; }}
            a.back {{ display: inline-block; margin-bottom: 24px; color: #7c5cff; text-decoration: none; }}
        </style>
    </head>
    <body>
        <a class="back" href="/">← Volver al inicio</a>
        <h1>{title}</h1>
        <div class="intro">{intro}</div>
        {sections_html}
        <hr style="margin: 40px 0; border: none; border-top: 1px solid #e2e8f0;">
        <p style="color: #718096; font-size: 14px">Última actualización: {settings.app_env or "agosto 2026"} · WowHub v0.1.0</p>
    </body>
    </html>
    """
