"""Customer: cliente final de un tenant (consumidor del producto WowHub del cliente)."""
from typing import Optional

from sqlalchemy import Boolean, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TenantMixin


class Customer(BaseModel, TenantMixin):
    __tablename__ = "customers"

    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str] = mapped_column(String(40), nullable=True, index=True)
    address: Mapped[str] = mapped_column(String(500), nullable=True)
    city: Mapped[str] = mapped_column(String(80), nullable=True)
    notes: Mapped[str] = mapped_column(String(1000), nullable=True)

    # Métricas
    total_orders: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_spent_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_order_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # Tags / segmentación
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    accepts_marketing: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Segmento manual (opcional). Si es NULL, el sistema calcula uno automático
    # según puntos y last_order_at. Valores sugeridos: "nuevo", "regular",
    # "vip", "inactivo", "recurrente". Default "nuevo" cuando recién se crea.
    segmento: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # HU_26 — Segmentación RFM real (recency / frequency / monetary quintiles)
    # ---------------------------------------------------------------------
    # Estas columnas se rellenan por la tarea Celery ``app.tasks.rfm.run_rfm_analysis``
    # (o su equivalente síncrono ``compute_rfm_for_tenant_sync``) y se exponen en
    # ``CustomerOut`` para el dashboard RFM. Persistirlas en la tabla evita
    # recalcular la matriz 5x5 cada vez que se lista un cliente.
    rfm_segment: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    r_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    f_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    m_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Celda RFM concatenada (ej. "555" para champions perfectos, "111" para lost).
    rfm_cell: Mapped[Optional[str]] = mapped_column(String(8), nullable=True, index=True)
    # Timestamp ISO de la última corrida RFM que escribió estos valores.
    rfm_updated_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # ═══════════════════════════════════════════════════════════════════════
    # TOBE v134.2-Producción-v2 (HU_50, HU_56, HU_57)
    # ═══════════════════════════════════════════════════════════════════════
    # Tipo de cliente (de WowPrint customerType): 'particular' | 'empresa'.
    # Default 'particular' (cliente retail típico LATAM).
    customer_type: Mapped[str] = mapped_column(
        String(20), default="particular", nullable=False, index=True,
        comment="HU_50: particular | empresa",
    )
    # Marketing consent granular (de WowPrint marketingEmail/WhatsApp):
    # 'pending' | 'authorized' | 'revoked'. Default 'pending'.
    marketing_email_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False,
        comment="HU_50: pending|authorized|revoked",
    )
    marketing_whatsapp_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False,
        comment="HU_50: pending|authorized|revoked",
    )
    # Deuda actual en centavos (cacheada desde último PaymentRecord).
    # Se actualiza en cada registro de pago (HU_56) o ajuste (HU_57).
    current_debt_cents: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="HU_56, HU_57: snapshot de deuda",
    )
