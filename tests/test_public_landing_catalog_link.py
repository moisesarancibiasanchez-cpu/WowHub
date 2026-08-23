"""Tests de regresión para el bug "Ver el catálogo no funciona" en la
landing pública.

Bug original: el CTA del hero en `app/templates/public/landing.html`
tenía `href="#"` y el JS solo cambiaba el `textContent`, por lo que el
clic llevaba al ancla vacía de la propia landing en lugar de al catálogo.

Este test verifica que los 3 links visibles en la landing apunten
efectivamente a `/u/{slug}/catalogo`.
"""
import re


def _bootstrap(client, slug="landing-bug"):
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@e.com", "password": "test1234", "full_name": "Test User",
        "create_tenant": True,
        "tenant_legal_name": f"Test {slug}", "tenant_slug": slug,
    })
    return r.json()


def test_landing_has_three_catalog_links(client):
    """Los 3 lugares donde aparece 'Ver el catálogo' en la landing deben
    apuntar al catálogo, no a '#' ni a otro destino roto."""
    _bootstrap(client, "landing-bug")
    r = client.get("/u/landing-bug")
    assert r.status_code == 200, r.text
    html = r.text

    # 1) Link del topbar (Ver catálogo)
    # 2) CTA del hero (id="hero-cta", Ver catálogo)
    # 3) Link "Ver todo →" de la sección Destacados
    # Todos deben apuntar a /u/landing-bug/catalogo
    target = "/u/landing-bug/catalogo"

    # a) Topbar
    assert f'href="{target}"' in html, "Topbar link 'Ver catálogo' falta o apunta a otro lado"

    # b) Hero CTA — antes del fix era href="#"
    m = re.search(r'<a[^>]+id="hero-cta"[^>]*>', html)
    assert m, "No se encontró el CTA del hero (id=hero-cta)"
    hero_tag = m.group(0)
    assert 'href="#"' not in hero_tag, (
        "REGRESIÓN: el CTA del hero tiene href='#'. "
        "El bug original está de vuelta."
    )
    assert f'href="{target}"' in hero_tag, (
        f"El CTA del hero debe apuntar a {target}, "
        f"pero su href actual es: {hero_tag}"
    )

    # c) "Ver todo →" de Destacados
    # Aparece en <a ... href="/u/.../catalogo">Ver todo</a>
    pattern = r'<a[^>]+href="' + re.escape(target) + r'"[^>]*>\s*Ver todo'
    assert re.search(pattern, html), (
        f"Falta el link 'Ver todo →' apuntando a {target}"
    )


def test_catalog_page_renders(client):
    """La página de catálogo debe renderizar 200 y contener los
    elementos UI esperados."""
    _bootstrap(client, "cat-fix")
    r = client.get("/u/cat-fix/catalogo")
    assert r.status_code == 200, r.text
    html = r.text
    assert 'id="grid"' in html, "Falta el grid del catálogo"
    assert 'id="search"' in html, "Falta el input de búsqueda"
    assert 'id="category"' in html, "Falta el select de categoría"
    # El slug se inyecta en el JS como const; verificamos que está
    # presente en el template literal del endpoint público.
    assert 'const slug = "cat-fix"' in html, "Slug no inyectado en el JS"
    assert "/api/v1/public/t/${slug}/" in html, (
        "El JS del catálogo no referencia los endpoints públicos por slug"
    )


def test_landing_404_for_unknown_slug(client):
    """El landing debe devolver 404 (o redirección controlada) cuando
    el slug no existe, no un 500."""
    r = client.get("/u/este-slug-no-existe-para-nadie")
    # El main.py tiene su propio manejo — al menos NO debe ser 500
    assert r.status_code != 500, f"Landing explotó con slug inválido: {r.status_code}"
    # Y debe ser 200 (muestra "no encontrado" en pantalla) o 404
    assert r.status_code in (200, 404), f"Status inesperado: {r.status_code}"
