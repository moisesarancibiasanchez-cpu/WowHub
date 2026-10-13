"""ProductPricing — helpers puros para cálculo de costo real, margen y precio sugerido.

Alineado con `WowHub_V8_Costos_Onboarding.html` (Fase 3):

  costo_real     = costo_insumos + (tiempo_min / 60) * costo_hora
  margen_actual  = (precio - costo_real) / precio * 100
  precio_sug     = costo_real / (1 - margen_objetivo/100)
  health:
      healthy → margin >= target_margin_pct       (✓)
      warning → margin >= 50% del target          (⚠)
      danger  → margin < 50% del target           (❌)
      unknown → no hay BusinessCosts configurado todavía

Estos helpers son **puros** (no tocan DB) para que sean fáciles de testear.
El método `compute_for_product()` es el atajo que el `ProductService` usa
para poblar los campos derivados en las respuestas (`ProductOut` /
`ProductListItem`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

from app.models.product import Product

Health = Literal["healthy", "warning", "danger", "unknown"]


# ── Constantes ────────────────────────────────────────────
# Banda de "warning" cuando el margen actual está entre el 50% y el 100%
# del margen objetivo. Si está por debajo del 50% → "danger".
WARNING_RATIO = 0.5


# ── Funciones puras ───────────────────────────────────────
def compute_labor_cents(production_time_min: int, cost_hour_cents: int) -> int:
    """Componente de mano de obra del costo real.

    Redondeo hacia arriba (defensivo: cualquier residuo se cobra, no se
    regala). Si no hay `cost_hour_cents` configurado, devuelve 0.
    """
    if not cost_hour_cents or production_time_min <= 0:
        return 0
    return int(math.ceil((production_time_min / 60.0) * cost_hour_cents))


def compute_real_cost(
    cost_cents: Optional[int],
    production_time_min: int,
    cost_hour_cents: int,
) -> int:
    """costo_real = insumos + (tiempo / 60) * costo_hora.

    `cost_cents` puede ser None (producto sin costo cargado) → tratamos
    como 0. Si `cost_hour_cents` es 0 (tenant sin Costos configurados),
    el componente de mano de obra queda en 0 (degradación elegante).
    """
    material = int(cost_cents or 0)
    labor = compute_labor_cents(production_time_min, cost_hour_cents)
    return material + labor


def compute_margin_pct(price_cents: int, real_cost_cents: int) -> Optional[float]:
    """Margen actual (%). Retorna None si no se puede calcular."""
    if price_cents <= 0:
        return None
    if real_cost_cents < 0:
        return None
    return round((price_cents - real_cost_cents) / price_cents * 100, 2)


def compute_suggested_price(
    real_cost_cents: int,
    target_margin_pct: int,
) -> int:
    """Precio sugerido = cost_real / (1 - margen/100).

    Caso degenerado (margen >= 100): devolvemos cost_real * 100 como
    cota superior segura (en la práctica nunca debería pasar porque
    validamos target_margin_pct en [0, 99] en el schema).
    """
    if target_margin_pct >= 100:
        return real_cost_cents * 100
    if target_margin_pct < 0:
        target_margin_pct = 0
    if real_cost_cents <= 0:
        return 0
    return int(math.ceil(real_cost_cents / (1 - target_margin_pct / 100.0)))


def health_for_margin(
    current_margin_pct: Optional[float],
    target_margin_pct: Optional[int],
) -> Health:
    """Clasifica la salud de pricing de un producto.

    - `unknown`: no hay datos suficientes (margin o target es None).
    - `healthy`: margin >= target.
    - `warning`: margin >= target * WARNING_RATIO.
    - `danger`: margin < target * WARNING_RATIO (o margin < 0).
    """
    if current_margin_pct is None or target_margin_pct is None:
        return "unknown"
    if current_margin_pct < 0:
        return "danger"
    if current_margin_pct >= target_margin_pct:
        return "healthy"
    if current_margin_pct >= target_margin_pct * WARNING_RATIO:
        return "warning"
    return "danger"


def health_message(
    health: Health,
    *,
    current_margin_pct: Optional[float],
    target_margin_pct: Optional[int],
    suggested_price_cents: int,
    price_cents: int,
) -> Optional[str]:
    """Mensaje corto listo para mostrar en la celda 'Salud' del dashboard."""
    if health == "unknown":
        return None
    if health == "healthy":
        return "Saludable"
    if health == "warning":
        return "Margen bajo"
    # danger
    if suggested_price_cents > 0 and price_cents > 0 and suggested_price_cents != price_cents:
        return "Subir precio"
    return "Margen crítico"


# ── Estructura de salida ──────────────────────────────────
@dataclass(frozen=True)
class ProductPricing:
    """Snapshot inmutable de los derivados de pricing de un producto.

    Lo devuelve `compute_for_product()` y lo consume el `ProductService`
    para poblar `ProductOut` y `ProductListItem`.
    """
    cost_real_cents: int
    suggested_price_cents: int
    current_margin_pct: Optional[float]
    target_margin_pct: Optional[int]
    cost_hour_used_cents: int
    health: Health
    health_message: Optional[str]

    @classmethod
    def empty(cls) -> "ProductPricing":
        """Valores neutros cuando el tenant aún no configuró Costos."""
        return cls(
            cost_real_cents=0,
            suggested_price_cents=0,
            current_margin_pct=None,
            target_margin_pct=None,
            cost_hour_used_cents=0,
            health="unknown",
            health_message=None,
        )


def compute_for_product(
    product: Product,
    *,
    cost_hour_cents: int,
    target_margin_pct: Optional[int],
) -> ProductPricing:
    """Atajo: toma un `Product` y devuelve un `ProductPricing` calculado.

    Si el tenant no configuró Costos (cost_hour_cents=0 y target=None),
    devuelve `ProductPricing.empty()` para que la UI pueda degradar
    elegantemente (mostrar "—" en vez de números falsos).
    """
    if not cost_hour_cents and target_margin_pct is None:
        return ProductPricing.empty()

    cost_real = compute_real_cost(
        product.cost_cents,
        int(product.production_time_min or 0),
        int(cost_hour_cents or 0),
    )
    margin = compute_margin_pct(int(product.price_cents or 0), cost_real)
    target = int(target_margin_pct) if target_margin_pct is not None else None

    if target is None or target <= 0:
        # Sin margen objetivo no podemos sugerir.
        suggested = 0
        health: Health = "unknown" if margin is None else (
            "healthy" if margin >= 0 else "danger"
        )
        msg: Optional[str] = None
    else:
        suggested = compute_suggested_price(cost_real, target)
        health = health_for_margin(margin, target)
        msg = health_message(
            health,
            current_margin_pct=margin,
            target_margin_pct=target,
            suggested_price_cents=suggested,
            price_cents=int(product.price_cents or 0),
        )

    return ProductPricing(
        cost_real_cents=cost_real,
        suggested_price_cents=suggested,
        current_margin_pct=margin,
        target_margin_pct=target,
        cost_hour_used_cents=int(cost_hour_cents or 0),
        health=health,
        health_message=msg,
    )
