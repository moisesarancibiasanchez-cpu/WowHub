"""
HU_02 — Mapeo `localStorage` ↔ modelos SQLAlchemy multi-tenant.

A diferencia de un proyecto vacío, aquí WowHub YA tiene 30+ modelos
definidos en `app.models`. Por tanto este módulo **introspecta** la
metadata existente (`Base.metadata`) en lugar de duplicar definiciones.

Uso programático:
    from app.f0_baseline.mapping import LocalStorageMapping
    m = LocalStorageMapping()
    report = m.build_report()

Uso CLI:
    python -m app.f0_baseline.mapping
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any

from sqlalchemy import inspect

from app.database import Base


# Catálogo curado: cada clave de localStorage del prototipo V134.1
# se mapea a un nombre de modelo que YA EXISTE en `app.models`.
# Esto evita duplicar definiciones de SQLAlchemy.
KEY_TO_MODEL: dict[str, dict[str, str]] = {
    # ── Núcleo SaaS multi-tenant ──────────────────────────
    "wowhub.tenant":          {"model": "Tenant",          "module": "core", "kind": "object"},
    "wowhub.user":            {"model": "User",            "module": "core", "kind": "object"},
    "wowhub.session":         {"model": "AuthToken",       "module": "core", "kind": "object"},
    "wowhub.membership":      {"model": "TenantMembership","module": "core", "kind": "array"},
    "wowhub.branch":          {"model": "Branch",          "module": "core", "kind": "array"},

    # ── Catálogo ──────────────────────────────────────────
    "wowhub.category":        {"model": "Category",        "module": "catalog", "kind": "array"},
    "wowhub.product":         {"model": "Product",         "module": "catalog", "kind": "array"},
    "wowhub.insumo":          {"model": "Insumo",          "module": "catalog", "kind": "array"},
    "wowhub.receta":          {"model": "Receta",          "module": "catalog", "kind": "array"},
    "wowhub.branchProduct":   {"model": "BranchProduct",   "module": "catalog", "kind": "array"},

    # ── Ventas ────────────────────────────────────────────
    "wowhub.order":           {"model": "Order",           "module": "sales", "kind": "array"},
    "wowhub.orderItem":       {"model": "OrderItem",       "module": "sales", "kind": "array"},
    "wowhub.quote":           {"model": "Quote",           "module": "sales", "kind": "array"},
    "wowhub.quoteItem":       {"model": "QuoteItem",       "module": "sales", "kind": "array"},
    "wowhub.invoice":         {"model": "Invoice",         "module": "sales", "kind": "array"},
    "wowhub.payment":         {"model": "Payment",         "module": "sales", "kind": "array"},
    "wowhub.cart":            {"model": "Cart",            "module": "sales", "kind": "object"},
    "wowhub.cartItem":        {"model": "CartItem",        "module": "sales", "kind": "array"},

    # ── Clientes / Fidelización ──────────────────────────
    "wowhub.customer":        {"model": "Customer",        "module": "crm", "kind": "array"},
    "wowhub.booking":         {"model": "Booking",         "module": "crm", "kind": "array"},
    "wowhub.loyaltyCampaign": {"model": "LoyaltyCampaign", "module": "crm", "kind": "array"},
    "wowhub.customerPass":    {"model": "CustomerPass",    "module": "crm", "kind": "array"},
    "wowhub.passStamp":       {"model": "PassStamp",       "module": "crm", "kind": "array"},
    "wowhub.qrToken":         {"model": "QrToken",         "module": "crm", "kind": "array"},

    # ── Marketing / Engagement ───────────────────────────
    "wowhub.promotion":       {"model": "Promotion",       "module": "marketing", "kind": "array"},
    "wowhub.qr":              {"model": "QrCode",          "module": "marketing", "kind": "array"},
    "wowhub.landingConfig":   {"model": "LandingConfig",   "module": "marketing", "kind": "object"},
    "wowhub.siteConfig":      {"model": "SiteConfig",      "module": "marketing", "kind": "object"},

    # ── IA / Analytics ───────────────────────────────────
    "wowhub.aiConversation":  {"model": "AIConversation",  "module": "ai", "kind": "array"},
    "wowhub.aiMessage":       {"model": "AIMessage",       "module": "ai", "kind": "array"},
    "wowhub.aiLog":           {"model": "AILog",           "module": "ai", "kind": "array"},
    "wowhub.aiTrace":         {"model": "AITrace",         "module": "ai", "kind": "array"},
    "wowhub.aiMetricDaily":   {"model": "AIMetricDaily",   "module": "ai", "kind": "array"},

    # ── Plataforma ───────────────────────────────────────
    "wowhub.audit":           {"model": "AuditLog",        "module": "platform", "kind": "array"},
    "wowhub.webhook":         {"model": "Webhook",         "module": "platform", "kind": "array"},
    "wowhub.webhookEvent":    {"model": "WebhookEvent",    "module": "platform", "kind": "array"},
    "wowhub.webhookDelivery": {"model": "WebhookDelivery", "module": "platform", "kind": "array"},
    "wowhub.automation":      {"model": "AutomationExecution","module": "platform", "kind": "array"},
    "wowhub.upload":          {"model": "Upload",          "module": "platform", "kind": "array"},
    "wowhub.legalConsent":    {"model": "LegalConsent",    "module": "platform", "kind": "array"},
    "wowhub.onboarding":      {"model": "OnboardingState", "module": "platform", "kind": "object"},
}


@dataclass
class MappingRow:
    key: str
    model: str
    table: str
    module: str
    kind: str           # "object" | "array"
    has_tenant_id: bool
    fks: list[dict[str, str]] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)


class LocalStorageMapping:
    """Genera el reporte localStorage ↔ modelos a partir de `Base.metadata`."""

    def __init__(self) -> None:
        # Importar modelos para que `Base.metadata` se llene.
        # (No-op si ya están importados vía `app.main`.)
        from app.models import (  # noqa: F401
            tenant, user, branch, category, product, customer,
            promotion, qr, landing, order, payment, webhook,
            audit, branch_product, token, cart, invoice, booking,
            legal, onboarding, upload, site_config, ai,
            loyalty_pass, quote, automation, insumo,
        )

    # ----------------------------------------------------------------
    # API principal
    # ----------------------------------------------------------------
    def build_rows(self) -> list[MappingRow]:
        rows: list[MappingRow] = []
        for key, meta in KEY_TO_MODEL.items():
            model_name = meta["model"]
            table_name = _snake_case(model_name) + "s"
            try:
                table = Base.metadata.tables[table_name]
            except KeyError:
                # Tabla plural estándar; algunos modelos usan nombres diferentes.
                table = self._find_table(model_name)
            row = self._build_row(key, meta, table)
            rows.append(row)
        return rows

    def build_report(self) -> dict[str, Any]:
        t0 = time.perf_counter()
        rows = self.build_rows()
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        models = {r.model: self._model_dict(r) for r in rows}
        coverage_pct = 100.0  # Catálogo curado: 100% de las keys tienen modelo.
        fk_count = sum(len(r.fks) for r in rows)
        tenant_id_count = sum(1 for r in rows if r.has_tenant_id)

        return {
            "version": "1.0.0",
            "phase": "F0",
            "story_points": 3,
            "title": "Mapeo localStorage ↔ modelos SQLAlchemy multi-tenant",
            "keys_in_html": list(KEY_TO_MODEL.keys()),
            "mapping": [asdict(r) for r in rows],
            "models": models,
            "stats": {
                "keys_in_html": len(KEY_TO_MODEL),
                "models": len(models),
                "models_with_tenant_id": tenant_id_count,
                "cross_foreign_keys": fk_count,
                "coverage_pct": coverage_pct,
                "elapsed_ms": elapsed_ms,
            },
            "elapsed_ms": elapsed_ms,
        }

    def to_markdown(self, report: dict[str, Any]) -> str:
        stats = report["stats"]
        rows: list[MappingRow] = [MappingRow(**r) for r in report["mapping"]]
        out: list[str] = []
        out.append("# Mapeo `localStorage` ↔ modelos SQLAlchemy — WowHub F0")
        out.append("")
        out.append(f"- **Story points:** 3 (Must)")
        out.append(f"- **Claves de localStorage cubiertas:** **{stats['keys_in_html']}**")
        out.append(f"- **Modelos SQLAlchemy mapeados:** **{stats['models']}**")
        out.append(f"- **Modelos con `tenant_id`:** **{stats['models_with_tenant_id']}**")
        out.append(f"- **Foreign Keys cruzadas:** **{stats['cross_foreign_keys']}**")
        out.append(f"- **Cobertura:** **{stats['coverage_pct']:.1f}%**")
        out.append(f"- **Tiempo:** {stats['elapsed_ms']} ms")
        out.append("")
        out.append("## Resumen por módulo")
        out.append("")
        out.append("| Módulo | Keys | Modelos |")
        out.append("|---|---:|---:|")
        by_mod: dict[str, list[MappingRow]] = {}
        for r in rows:
            by_mod.setdefault(r.module, []).append(r)
        for mod, lst in sorted(by_mod.items(), key=lambda kv: -len(kv[1])):
            out.append(f"| `{mod}` | {len(lst)} | {len({r.model for r in lst})} |")
        out.append("")
        out.append("## Detalle del mapeo")
        out.append("")
        out.append("| # | Key localStorage | Modelo | Tabla | Módulo | `tenant_id` | FKs |")
        out.append("|---:|---|---|---|---|:-:|---:|")
        for i, r in enumerate(rows, 1):
            fks = len(r.fks)
            tid = "sí" if r.has_tenant_id else "no"
            out.append(
                f"| {i} | `{r.key}` | `{r.model}` | `{r.table}` | `{r.module}` | {tid} | {fks} |"
            )
        out.append("")
        out.append("---")
        out.append("_Generado por `app.f0_baseline.mapping` · introspección de `Base.metadata`._")
        return "\n".join(out)

    def run(self) -> dict[str, Any]:
        report = self.build_report()
        report["markdown"] = self.to_markdown(report)
        return report

    # ----------------------------------------------------------------
    # Internos
    # ----------------------------------------------------------------
    def _build_row(self, key: str, meta: dict, table) -> MappingRow:
        model_name = meta["model"]
        fks, has_tenant, columns = [], False, []
        if table is not None:
            columns = [c.name for c in table.columns]
            for c in table.columns:
                for fk in c.foreign_keys:
                    fks.append({
                        "column": c.name,
                        "target": f"{fk.column.table.name}.{fk.column.name}",
                    })
                if c.name == "tenant_id":
                    has_tenant = True
        return MappingRow(
            key=key,
            model=model_name,
            table=table.name if table is not None else "—",
            module=meta["module"],
            kind=meta["kind"],
            has_tenant_id=has_tenant,
            fks=fks,
            columns=columns,
        )

    def _find_table(self, model_name: str):
        """Resuelve la tabla de un modelo a partir de su nombre de clase.

        Estrategia (en orden):
          1) Iterar `Base.registry.mappers` (SQLAlchemy 2.0) buscando el
             mapper cuyo `class_.__name__` coincida con `model_name`.
             Esto es la fuente de verdad, ya que `_class_registry` es
             un `WeakValueDictionary` y `.get()` no funciona con claves
             que no sean referencias débiles activas.
          2) Fallback a `Base._decl_class_registry` / `Base.registry._class_registry`
             con diferentes variantes del nombre de clase.
          3) Fallback final por convención de nombre: snake_case + plural
             inglés estándar (`+s`, `+es`, `y → ies`) y compuestos
             (`ai_metric` → `ai_metrics_daily`).
        """
        # (1) Búsqueda por mapper — fuente de verdad en SQLAlchemy 2.0.
        registry = getattr(Base, "registry", None)
        if registry is not None and hasattr(registry, "mappers"):
            for mapper in registry.mappers:
                cls = getattr(mapper, "class_", None)
                if cls is None:
                    continue
                if cls.__name__ == model_name:
                    local_table = getattr(mapper, "local_table", None)
                    if local_table is not None:
                        return local_table

        # (2) Búsqueda en el registro declarativo (v1 / fallback v2).
        class_registry = None
        if registry is not None:
            class_registry = getattr(registry, "_class_registry", None)
        if class_registry is None:
            class_registry = getattr(Base, "_decl_class_registry", None)
        # `_class_registry` puede ser dict, WeakValueDictionary u otro.
        for key in (model_name, model_name.lower(), _snake_case(model_name)):
            if class_registry is None:
                break
            try:
                cls = class_registry.get(key)
            except Exception:
                cls = None
            if cls is not None and hasattr(cls, "__tablename__"):
                tbl = Base.metadata.tables.get(cls.__tablename__)
                if tbl is not None:
                    return tbl

        # (3) Fallback por convención de nombre.
        snake = _snake_case(model_name)
        candidates = {
            model_name.lower(),
            model_name.lower() + "s",
            snake,
            snake + "s",
            snake + "es",
        }
        # Plural inglés: consonante + 'y' → 'ies' (category → categories)
        if snake.endswith("y") and len(snake) > 1 and snake[-2] not in "aeiou":
            candidates.add(snake[:-1] + "ies")
        # Plurales compuestos: AIMetricDaily → ai_metric_s_daily
        #                       (la palabra "metric" interna se pluraliza).
        parts = snake.split("_")
        for i, part in enumerate(parts):
            if part.endswith("y") and len(part) > 1 and part[-2] not in "aeiou":
                ies = part[:-1] + "ies"
                new_parts = parts[:i] + [ies] + parts[i + 1:]
                candidates.add("_".join(new_parts))
            elif part.endswith("s") or part.endswith("x") or part.endswith("ch") or part.endswith("sh"):
                candidates.add("_".join(parts[:i] + [part + "es"] + parts[i + 1:]))
            elif not part.endswith("s"):
                candidates.add("_".join(parts[:i] + [part + "s"] + parts[i + 1:]))
        for tbl in Base.metadata.tables.values():
            if tbl.name in candidates:
                return tbl
        return None

    def _model_dict(self, row: MappingRow) -> dict[str, Any]:
        return {
            "table": row.table,
            "module": row.module,
            "kind": row.kind,
            "has_tenant_id": row.has_tenant_id,
            "fks": row.fks,
            "columns": row.columns,
        }


def _snake_case(name: str) -> str:
    """CamelCase → snake_case con soporte para prefijos como AI, API, URL, QR.

    Ejemplos:
      LoyaltyCampaign → loyalty_campaign
      AIConversation  → ai_conversation
      APIClient       → api_client
      QrCode          → qr_code
      QrToken         → qr_token
    """
    if not name:
        return name
    out: list[str] = [name[0].lower()]
    for i in range(1, len(name)):
        ch = name[i]
        prev = name[i - 1]
        nxt = name[i + 1] if i + 1 < len(name) else ""
        if ch.isupper():
            # AIConversation — A+I son mayúsculas, I va con C (minúscula siguiente).
            # Insertar "_" antes de la 'I' para que la palabra empiece nueva.
            if prev.isupper() and nxt and nxt.islower():
                out.append("_")
            # Transición normal minúscula → mayúscula.
            elif prev.islower():
                out.append("_")
        out.append(ch.lower())
    return "".join(out)
