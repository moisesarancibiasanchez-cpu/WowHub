"""HU_38 — RBAC Granular con Casbin.

Dos tablas planas que actúan como backend del ``casbin.persist.Adapter``:

  * ``rbac_policies``  — reglas ``(sub, dom, obj, act)``.
  * ``rbac_groupings`` — relaciones de jerarquía ``(sub, role, dom)``
                         (e.g. ``(role:CASHIER, role:STAFF, tenant-uuid)``).

Ambas son portables: usan ``String`` para todos los campos (no hay
``JSON``, ``ARRAY`` ni tipos dependientes del dialecto). Los UUIDs de
``dom`` se almacenan como texto.

Diseño:
  * Primary key surrogate (UUID v4 vía ``BaseModel``).
  * Índices por (sub, dom) y (dom) para que el adapter cargue policies
    rápido en ``load_policy()`` (O(N) por dominio).
  * Sin FK cross-DB — RBAC puede crecer más rápido que el resto del
    schema, no queremos que un ``DROP TABLE tenants`` rompa el módulo.
"""
from __future__ import annotations

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class RBACPolicy(BaseModel):
    """Una regla RBAC (subject, domain, object, action).

    Ejemplo: ``('role:OWNER', '*', '*', '*')`` → OWNER puede todo.
    """

    __tablename__ = "rbac_policies"

    # Los 4 campos canónicos de Casbin.
    sub: Mapped[str] = mapped_column(String(120), nullable=False)
    dom: Mapped[str] = mapped_column(String(120), nullable=False)
    obj: Mapped[str] = mapped_column(String(120), nullable=False)
    act: Mapped[str] = mapped_column(String(60), nullable=False)

    # Metadata opcional (no usada por Casbin runtime; útil para la UI).
    effect: Mapped[str] = mapped_column(String(16), default="allow", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    __table_args__ = (
        Index("ix_rbac_policy_sub_dom", "sub", "dom"),
        Index("ix_rbac_policy_dom", "dom"),
        # (sub, dom, obj, act) — índice único para que el adapter rechace
        # duplicados sin race (mejor que CONSTRAINT UNIQUE directo).
        Index(
            "uq_rbac_policy_rule",
            "sub",
            "dom",
            "obj",
            "act",
            unique=True,
        ),
    )


class RBACGrouping(BaseModel):
    """Una relación de jerarquía (subject hereda de role en un dominio).

    Casbin interpreta la tupla como ``g(sub, role, dom)``: ``sub`` hereda
    los permisos de ``role`` DENTRO del dominio ``dom``.

    Ejemplo: ``('role:CASHIER', 'role:STAFF', 'tenant-uuid')`` →
    CASHIER hereda de STAFF sólo dentro de ese tenant.
    """

    __tablename__ = "rbac_groupings"

    sub: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(120), nullable=False)
    dom: Mapped[str] = mapped_column(String(120), nullable=False)

    __table_args__ = (
        Index("ix_rbac_group_sub", "sub"),
        Index("ix_rbac_group_role_dom", "role", "dom"),
        Index(
            "uq_rbac_group_rule",
            "sub",
            "role",
            "dom",
            unique=True,
        ),
    )