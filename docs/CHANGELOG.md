# Changelog — WowHub

Todos los cambios relevantes del proyecto, organizados por fecha y categoría.
Este archivo sigue parcialmente el estándar [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

---

## [No publicado] — 2026-08-16

### Added — Integración del Asistente Virtual con todos los módulos

#### Endpoints nuevos (4)
- `GET /api/v1/tenants/{id}/analytics/inventory` — análisis de inventario con 6 categorías (`all`, `low_stock`, `out_of_stock`, `overstock`, `dead_stock`, `top_selling`).
- `GET /api/v1/tenants/{id}/analytics/customer-segments` — segmentación de clientes con 6 perfiles (`all`, `inactive`, `top`, `new`, `vip`, `no_orders`).
- `POST /api/v1/tenants/{id}/campaigns` — envío masivo de email por segmento (máx. 500 destinatarios, filtro opt-in).
- `POST /api/v1/tenants/{id}/campaigns/preview` — vista previa de campaña sin envío.

#### AI Tools nuevas (3)
- `analyze_inventory` — inventario categorizado.
- `get_customer_segments` — clientes por segmento.
- `send_campaign` — campaña masiva con confirmación.

#### Sub-agentes actualizados (4)
- **Marketing:** detecta stock bajo, dead stock y segmentos para combos.
- **Growth:** oportunidades de venta cruzada y subida de ticket.
- **Automation:** lanza campañas a inactivos / VIP / nuevos.
- **Marketplace:** detecta sin stock, sin rotación y mejora de catálogo.

#### Router heurístico
- +25 keywords nuevas para detectar intenciones de inventario, segmentos y campañas.
- Tests actualizados para reflejar la nueva taxonomía.

#### Servicios y schemas nuevos
- `app/services/analytics_service.py` (450 líneas, lógica de inventario + segmentos).
- `app/schemas/analytics.py` (modelos Pydantic).
- `app/api/v1/analytics.py` (routers de analytics).
- `app/api/v1/campaigns.py` (routers de campañas + email).

#### Tests
- 14 tests nuevos en `tests/test_analytics_campaigns.py` (100 % pasan).
- 1 test ajustado en `tests/test_ai_orchestrator_fallback.py` por nueva keyword `producto`.

#### Documentación
- Informe detallado en [`docs/INFORME_INTEGRACION_IA.md`](INFORME_INTEGRACION_IA.md).
- Informe del sistema de fidelización en [`docs/INFORME_FIDELIZACION.md`](INFORME_FIDELIZACION.md).

---

## Formato de las versiones

- **Added** — funcionalidades nuevas.
- **Changed** — cambios en funcionalidades existentes.
- **Deprecated** — funcionalidades que se eliminarán pronto.
- **Removed** — funcionalidades eliminadas.
- **Fixed** — corrección de bugs.
- **Security** — cambios de seguridad.

---

## Cómo contribuir al changelog

Cuando añadas un cambio, agrégalo bajo `[No publicado]` con la fecha actual
y la categoría correspondiente. En cada release estable, mueve la sección
a una versión fechada (p. ej. `[0.2.0] — 2026-08-16`).
