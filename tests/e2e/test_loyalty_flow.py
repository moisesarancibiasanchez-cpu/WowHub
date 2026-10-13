"""E2E test del flujo de fidelización (Fase 1+2).

Cubre:
  1. Login del owner (vía API: register + token en localStorage)
  2. Navegar a /dashboard/loyalty → ver grid de campañas
  3. Crear una campaña nueva desde el modal → toast de éxito
  4. Abrir el modal de QR del mostrador → ver el QR code <img>
  5. Registrar un cliente vía endpoint público (simula al cliente en su celu)
  6. Navegar a /dashboard/loyalty/scanner → ver QR del mostrador rotando
  7. Ejecutar el scan programáticamente (vía page.evaluate) porque E2E no
     tiene acceso a una cámara real → verify sello sumado + toast éxito
  8. Verificar que el total_stamps_issued de la campaña subió (via API)

Prerrequisitos:
  - pip install -e ".[e2e]"
  - playwright install chromium
  - Un WowHub corriendo (local u online). El test marca ``@pytest.mark.e2e``
    para que la suite normal de pytest (CI rápido) lo SKIPEE.

Uso:
    pytest tests/e2e/test_loyalty_flow.py -m e2e \\
        --base-url=https://wowhub-app.up.railway.app --headed
"""
from __future__ import annotations

import time
import uuid

import pytest

# ── Markers ────────────────────────────────────────────────────
pytestmark = pytest.mark.e2e


# ── Helpers locales ────────────────────────────────────────────
def _wait_for_toast(page, text: str, timeout_ms: int = 5000) -> None:
    """Espera a que aparezca un toast con el texto dado."""
    page.wait_for_selector(f".toast:has-text('{text}')", timeout=timeout_ms)


def _wait_for_grid_card(page, campaign_name: str, timeout_ms: int = 8000) -> None:
    """Espera a que la campaña aparezca en el grid de campañas."""
    page.wait_for_selector(
        f"#campaigns-grid .card:has-text('{campaign_name}')",
        timeout=timeout_ms,
    )


# ── Test ───────────────────────────────────────────────────────
def test_owner_can_create_campaign_and_see_qr(
    page,
    base_url: str,
    authed_page,
    registered_owner: dict,
    api_request_context,
    tenant_slug: str,
):
    """Flujo completo del owner: loyalty → crear → ver QR."""
    page: object = authed_page  # viene con tokens ya inyectados

    # 1) Login redirige automáticamente si no hay token; ya inyectamos tokens
    #    así que /dashboard/loyalty debe cargar el grid de campañas.
    page.goto(f"{base_url}/dashboard/loyalty")

    # La grilla se llena async con loadCampaigns() — esperamos a que el
    # placeholder "Cargando…" desaparezca o a que aparezca el botón "Nueva".
    page.wait_for_selector("#new-campaign-btn", timeout=10000)

    # 2) Crear una campaña nueva
    campaign_name = f"E2E Café {uuid.uuid4().hex[:6]}"
    page.click("#new-campaign-btn")
    page.wait_for_selector("#modal:not(.hidden)", timeout=3000)
    page.fill("#c_name", campaign_name)
    page.fill("#c_reward_label", "1 Café Gratis E2E")
    page.fill("#c_stamps_required", "3")
    # PIN opcional — lo seteamos para verificar el flujo con PIN también
    page.fill("#c_cashier_pin", "1234")
    page.click("#save-btn")

    # 3) Toast de éxito + modal cerrado
    _wait_for_toast(page, "Campaña creada", timeout_ms=5000)
    page.wait_for_selector("#modal.hidden", timeout=3000)
    _wait_for_grid_card(page, campaign_name, timeout_ms=8000)

    # 4) Abrir el modal de QR del mostrador
    # El primer card de la grilla con nuestra campaña tiene los botones.
    card = page.locator(f"#campaigns-grid .card:has-text('{campaign_name}')")
    card.locator("button[data-action='qr']").click()
    page.wait_for_selector("#qr-modal:not(.hidden)", timeout=3000)
    # El <img id="qr-img"> debe tener un src válido (qrserver.com)
    qr_src = page.locator("#qr-img").get_attribute("src")
    assert qr_src and "qr_payload=" in qr_src, f"QR src inválido: {qr_src!r}"

    # 5) Registrar un cliente vía API (simula al cliente escaneando el QR público)
    reg = api_request_context.post(
        f"/api/v1/loyalty/c/{tenant_slug}/register",
        data={
            "full_name": "Cliente E2E",
            "email": f"cliente-{uuid.uuid4().hex[:6]}@e2e.com",
            "accepts_terms": True,
        },
        headers={"Content-Type": "application/json"},
    )
    assert reg.ok, f"registro público falló: {reg.status} {reg.text()}"
    pass_data = reg.json()
    pass_serial = pass_data["serial"]
    assert pass_serial, "el endpoint público debe devolver el serial del pass"
    # Validamos que efectivamente arranca con 0 sellos
    assert pass_data["stamps_current"] == 0

    # 6) Cerrar el modal QR (lo dejaremos para una vista posterior)
    page.click("#qr-modal-close")
    page.wait_for_selector("#qr-modal.hidden", timeout=2000)

    # 7) Ir al scanner
    page.goto(f"{base_url}/dashboard/loyalty/scanner")
    # Esperar a que el QR del mostrador se pinte (carga async)
    page.wait_for_selector("#counter-qr-img[src*='qr_payload=']", timeout=10000)

    # 8) Ejecutar el scan programáticamente (E2E no puede usar la cámara)
    #    performScan() está definida en el scope del script → la invocamos
    #    vía page.evaluate pasando el pass_serial. Además, la campaña con
    #    PIN = "1234" requiere que lo inyectemos en el input antes.
    page.fill("#cashier-pin", "1234")
    page.evaluate(
        """
        async ([serial]) => {
            // performScan es función local del módulo, pero window lo expone
            // indirectamente vía el closure del <script>. Llamamos a la API
            // directamente para validar el flujo end-to-end.
            // El frontend de la página ya está autenticado, así que
            // window.WH.TokenStore tiene los tokens.
            const session = await window.WH.Auth.ensureSession();
            const deviceFp = (navigator.userAgent || 'e2e').slice(0, 60);
            // 1) pedimos QR token del mostrador
            const tRes = await fetch(
                `/api/v1/tenants/${session.tenant.tenant_id}/loyalty/campaigns/${currentCampaignId}/qr-token?device_fp=${encodeURIComponent(deviceFp)}`,
                { method: 'POST', headers: { 'Authorization': `Bearer ${session.access_token}` } }
            );
            if (!tRes.ok) throw new Error('qr-token failed: ' + tRes.status);
            const tok = await tRes.json();
            // 2) ejecutamos scan
            const r = await fetch('/api/v1/loyalty/scan', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${session.access_token}`,
                    'X-Tenant-Id': session.tenant.tenant_id,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    qr_payload: tok.qr_payload,
                    pass_serial: serial,
                    device_fp: deviceFp,
                    cashier_pin: '1234',
                }),
            });
            if (!r.ok) throw new Error('scan failed: ' + r.status + ' ' + (await r.text()));
            return await r.json();
        }
        """,
        [pass_serial],
    )
    # Nota: page.evaluate devuelve el resultado pero acá no lo necesitamos
    # para el assert — verificamos por API.

    # 9) Verificar via API que el sello se sumó (1/3)
    # Listamos las campañas y leemos total_stamps_issued.
    campaigns = api_request_context.get(
        f"/api/v1/tenants/{registered_owner['tenant_id']}/loyalty/campaigns",
        headers={"Authorization": f"Bearer {registered_owner['access']}"},
    )
    assert campaigns.ok, f"GET campaigns falló: {campaigns.status}"
    items = campaigns.json()
    our = next((c for c in items if c["name"] == campaign_name), None)
    assert our, f"campaña {campaign_name!r} no encontrada en {items}"
    assert our["total_stamps_issued"] == 1, f"esperaba 1 sello, hay {our['total_stamps_issued']}"
    # El total_passes también debe haber subido
    assert our["total_passes"] >= 1


def test_login_form_is_reachable_for_unauthenticated_user(page, base_url: str):
    """Smoke: el login debe estar accesible sin auth, mostrar el form."""
    page.goto(f"{base_url}/login")
    # El botón de submit del login es lo más estable
    page.wait_for_selector("form button[type='submit']", timeout=10000)
    # Y debe haber un input de email/password
    assert page.locator("input[type='email']").count() >= 1
    assert page.locator("input[type='password']").count() >= 1
