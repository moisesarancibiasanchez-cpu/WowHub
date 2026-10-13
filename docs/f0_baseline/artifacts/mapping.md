# Mapeo `localStorage` ↔ modelos SQLAlchemy — WowHub F0

- **Story points:** 3 (Must)
- **Claves de localStorage cubiertas:** **41**
- **Modelos SQLAlchemy mapeados:** **41**
- **Modelos con `tenant_id`:** **32**
- **Foreign Keys cruzadas:** **75**
- **Cobertura:** **100.0%**
- **Tiempo:** 0 ms

## Resumen por módulo

| Módulo | Keys | Modelos |
|---|---:|---:|
| `sales` | 8 | 8 |
| `platform` | 8 | 8 |
| `crm` | 6 | 6 |
| `core` | 5 | 5 |
| `catalog` | 5 | 5 |
| `ai` | 5 | 5 |
| `marketing` | 4 | 4 |

## Detalle del mapeo

| # | Key localStorage | Modelo | Tabla | Módulo | `tenant_id` | FKs |
|---:|---|---|---|---|:-:|---:|
| 1 | `wowhub.tenant` | `Tenant` | `tenants` | `core` | no | 0 |
| 2 | `wowhub.user` | `User` | `users` | `core` | no | 0 |
| 3 | `wowhub.session` | `AuthToken` | `auth_tokens` | `core` | no | 1 |
| 4 | `wowhub.membership` | `TenantMembership` | `tenant_memberships` | `core` | sí | 2 |
| 5 | `wowhub.branch` | `Branch` | `branches` | `core` | sí | 1 |
| 6 | `wowhub.category` | `Category` | `categories` | `catalog` | sí | 1 |
| 7 | `wowhub.product` | `Product` | `products` | `catalog` | sí | 2 |
| 8 | `wowhub.insumo` | `Insumo` | `insumos` | `catalog` | sí | 1 |
| 9 | `wowhub.receta` | `Receta` | `recetas` | `catalog` | sí | 3 |
| 10 | `wowhub.branchProduct` | `BranchProduct` | `branch_products` | `catalog` | sí | 3 |
| 11 | `wowhub.order` | `Order` | `orders` | `sales` | sí | 3 |
| 12 | `wowhub.orderItem` | `OrderItem` | `order_items` | `sales` | no | 2 |
| 13 | `wowhub.quote` | `Quote` | `quotes` | `sales` | sí | 4 |
| 14 | `wowhub.quoteItem` | `QuoteItem` | `quote_items` | `sales` | no | 2 |
| 15 | `wowhub.invoice` | `Invoice` | `invoices` | `sales` | sí | 2 |
| 16 | `wowhub.payment` | `Payment` | `payments` | `sales` | sí | 2 |
| 17 | `wowhub.cart` | `Cart` | `carts` | `sales` | sí | 3 |
| 18 | `wowhub.cartItem` | `CartItem` | `cart_items` | `sales` | no | 2 |
| 19 | `wowhub.customer` | `Customer` | `customers` | `crm` | sí | 1 |
| 20 | `wowhub.booking` | `Booking` | `bookings` | `crm` | sí | 4 |
| 21 | `wowhub.loyaltyCampaign` | `LoyaltyCampaign` | `loyalty_campaigns` | `crm` | sí | 1 |
| 22 | `wowhub.customerPass` | `CustomerPass` | `customer_passes` | `crm` | sí | 3 |
| 23 | `wowhub.passStamp` | `PassStamp` | `pass_stamps` | `crm` | sí | 4 |
| 24 | `wowhub.qrToken` | `QrToken` | `qr_tokens` | `crm` | sí | 5 |
| 25 | `wowhub.promotion` | `Promotion` | `promotions` | `marketing` | sí | 1 |
| 26 | `wowhub.qr` | `QrCode` | `qr_codes` | `marketing` | sí | 2 |
| 27 | `wowhub.landingConfig` | `LandingConfig` | `landing_configs` | `marketing` | sí | 1 |
| 28 | `wowhub.siteConfig` | `SiteConfig` | `site_config` | `marketing` | no | 0 |
| 29 | `wowhub.aiConversation` | `AIConversation` | `ai_conversations` | `ai` | sí | 2 |
| 30 | `wowhub.aiMessage` | `AIMessage` | `ai_messages` | `ai` | sí | 3 |
| 31 | `wowhub.aiLog` | `AILog` | `ai_logs` | `ai` | sí | 3 |
| 32 | `wowhub.aiTrace` | `AITrace` | `ai_traces` | `ai` | sí | 3 |
| 33 | `wowhub.aiMetricDaily` | `AIMetricDaily` | `ai_metrics_daily` | `ai` | sí | 1 |
| 34 | `wowhub.audit` | `AuditLog` | `audit_logs` | `platform` | sí | 1 |
| 35 | `wowhub.webhook` | `Webhook` | `webhooks` | `platform` | sí | 1 |
| 36 | `wowhub.webhookEvent` | `WebhookEvent` | `—` | `platform` | no | 0 |
| 37 | `wowhub.webhookDelivery` | `WebhookDelivery` | `webhook_deliveries` | `platform` | sí | 1 |
| 38 | `wowhub.automation` | `AutomationExecution` | `automation_executions` | `platform` | sí | 2 |
| 39 | `wowhub.upload` | `Upload` | `uploads` | `platform` | sí | 1 |
| 40 | `wowhub.legalConsent` | `LegalConsent` | `legal_consents` | `platform` | no | 0 |
| 41 | `wowhub.onboarding` | `OnboardingState` | `onboarding_states` | `platform` | sí | 1 |

---
_Generado por `app.f0_baseline.mapping` · introspección de `Base.metadata`._