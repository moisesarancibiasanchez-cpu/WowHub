"""HU_38 — Adapter SQLAlchemy genérico para Casbin.

Casbin v1.x define ``casbin.persist.Adapter`` con la siguiente interfaz::

    load_policy(model) -> None
    save_policy(model) -> None
    add_policy(sec, ptype, rule) -> None
    remove_policy(sec, ptype, rule) -> None
    remove_filtered_policy(sec, ptype, field_index, *field_values) -> None

Donde ``rule`` es una lista de strings (no tupla). Implementamos todas
las operaciones contra el ORM ``RBACPolicy`` y ``RBACGrouping``.

Detalles:
  * ``add_policy`` es idempotente a nivel ORM (``INSERT ... ON CONFLICT
    DO NOTHING`` o equivalente según dialecto). Casbin NO dedup por sí
    mismo — prefiere falla silenciosa para no romper el runtime.
  * ``load_policy`` itera ``policies`` y ``groupings``. Para cada fila
    hace ``model.add_policy(sec, ptype, rule)``. Si la fila tiene
    campos vacíos o más de los esperados por el modelo, los descarta
    silenciosamente (compat con bases pre-existentes).
  * ``save_policy`` borra todo y re-inserta — útil en admin tools, NO
    en hot path.
  * ``remove_filtered_policy`` soporta wildcards Casbin (``["sub", "*",
    "obj"]``) comparando con ``"*"`` (match-all).
  * El adapter NO maneja conexiones: recibe un ``session_factory``
    callable (e.g. ``SessionLocal``) y abre una sesión por operación.
    Esto aísla cada casbin op del resto de la app y permite tests con
    DB en memoria.

Thread-safety:
  * Casbin enforcer NO es thread-safe por default. Este adapter tampoco.
  * El módulo ``app/core/security.py`` mantiene una sola instancia
    global vía ``_get_rbac_enforcer()`` (lazy) y la usa con un lock
    en ``_RBAC_LOCK`` si fuera necesario.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, List, Optional, Sequence

from casbin.persist import Adapter as CasbinAdapter
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.rbac import RBACGrouping, RBACPolicy

logger = logging.getLogger("wowhub.rbac.adapter")


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def _psec_for_ptype(ptype: str) -> str:
    """Devuelve 'p' o 'g' según el prefijo del ptype."""
    if ptype.startswith("g"):
        return "g"
    return "p"


def _filter_wildcards(field_values: Sequence[str]) -> List[Optional[str]]:
    """Convierte ``'*'`` Casbin a ``None`` (wildcard en SQL)."""
    out: List[Optional[str]] = []
    for v in field_values:
        if v == "*":
            out.append(None)
        else:
            out.append(v)
    return out


# ──────────────────────────────────────────────────────────────────────
# Adapter
# ──────────────────────────────────────────────────────────────────────
class SQLAlchemyAdapter(CasbinAdapter):
    """Adapter SQLAlchemy para Casbin (rbac_policies + rbac_groupings).

    Compatible con ``casbin.persist.Adapter``. Se construye con un
    ``session_factory`` (callable que devuelve un ``Session``) y un
    ``model`` opcional (necesario para ``save_policy``).

    Uso típico::

        adapter = SQLAlchemyAdapter(SessionLocal)
        enforcer = Enforcer("app/core/rbac_model.conf", adapter)

    Hereda de ``casbin.persist.Adapter`` para satisfacer el
    ``isinstance(adapter, Adapter)`` que ``Enforcer.__init__`` exige.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        model: Optional[object] = None,
    ):
        self._session_factory = session_factory
        self._model = model
        self._lock = threading.Lock()

    # ── API de casbin.persist.Adapter ────────────────────────────────
    def load_policy(self, model: object) -> None:
        """Carga todas las policies y groupings al modelo Casbin."""
        with self._session_factory() as session:
            policies = session.execute(select(RBACPolicy)).scalars().all()
            for p in policies:
                rule = [p.sub, p.dom, p.obj, p.act]
                try:
                    model.add_policy("p", "p", rule)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "rbac_adapter.load_policy: descartando policy %s (%s)",
                        rule, exc,
                    )

            groupings = session.execute(select(RBACGrouping)).scalars().all()
            for g in groupings:
                # Casbin 1.43 grouping es ``g(sub, role, dom)``.
                rule = [g.sub, g.role, g.dom]
                try:
                    model.add_policy("g", "g", rule)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "rbac_adapter.load_policy: descartando grouping %s (%s)",
                        rule, exc,
                    )
        logger.info(
            "rbac_adapter.load_policy: %d policies + %d groupings",
            len(policies),
            len(groupings),
        )

    def save_policy(self, model: object) -> None:
        """Vuelca TODO el modelo Casbin a la DB (borra + re-inserta).

        ⚠ NO usar en hot-path. Pensado para ``POST /rbac/seed?reset=true``.
        """
        with self._lock, self._session_factory() as session:
            # 1) Wipe.
            session.execute(delete(RBACPolicy))
            session.execute(delete(RBACGrouping))
            session.flush()

            # 2) Re-insert desde el modelo.
            inserted_p = inserted_g = 0
            model_p = getattr(model, "model", {}).get("p", {})
            for ptype, ast in model_p.items():
                for rule in getattr(ast, "policy", []):
                    if len(rule) < 4:
                        continue
                    session.add(
                        RBACPolicy(
                            sub=rule[0],
                            dom=rule[1],
                            obj=rule[2],
                            act=rule[3],
                            effect="allow",
                            priority=0,
                            note="",
                        )
                    )
                    inserted_p += 1

            model_g = getattr(model, "model", {}).get("g", {})
            for ptype, ast in model_g.items():
                for rule in getattr(ast, "policy", []):
                    if len(rule) < 3:
                        continue
                    session.add(
                        RBACGrouping(sub=rule[0], role=rule[1], dom=rule[2])
                    )
                    inserted_g += 1

            session.commit()
        logger.info(
            "rbac_adapter.save_policy: %d policies + %d groupings",
            inserted_p,
            inserted_g,
        )

    def add_policy(self, sec: str, ptype: str, rule: Sequence[str]) -> None:
        """Inserta una policy/grouping (idempotente vía UNIQUE index)."""
        rule = list(rule)
        if sec == "p" and len(rule) >= 4:
            sub, dom, obj, act = rule[0], rule[1], rule[2], rule[3]
            with self._session_factory() as session:
                try:
                    session.add(
                        RBACPolicy(sub=sub, dom=dom, obj=obj, act=act)
                    )
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    # Idempotente: ya existe.
                    logger.debug(
                        "rbac_adapter.add_policy: ya existe p=%s", rule
                    )
        elif sec == "g" and len(rule) >= 3:
            sub, role, dom = rule[0], rule[1], rule[2]
            with self._session_factory() as session:
                try:
                    session.add(
                        RBACGrouping(sub=sub, role=role, dom=dom)
                    )
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    logger.debug(
                        "rbac_adapter.add_policy: ya existe g=%s", rule
                    )
        else:
            logger.warning(
                "rbac_adapter.add_policy: sec=%s ptype=%s rule=%s — formato "
                "no soportado",
                sec, ptype, rule,
            )

    def remove_policy(self, sec: str, ptype: str, rule: Sequence[str]) -> None:
        """Borra una policy/grouping exacto."""
        rule = list(rule)
        with self._session_factory() as session:
            if sec == "p" and len(rule) >= 4:
                stmt = delete(RBACPolicy).where(
                    RBACPolicy.sub == rule[0],
                    RBACPolicy.dom == rule[1],
                    RBACPolicy.obj == rule[2],
                    RBACPolicy.act == rule[3],
                )
            elif sec == "g" and len(rule) >= 3:
                stmt = delete(RBACGrouping).where(
                    RBACGrouping.sub == rule[0],
                    RBACGrouping.role == rule[1],
                    RBACGrouping.dom == rule[2],
                )
            else:
                logger.warning(
                    "rbac_adapter.remove_policy: sec=%s rule=%s — formato no "
                    "soportado",
                    sec, rule,
                )
                return
            session.execute(stmt)
            session.commit()

    def remove_filtered_policy(
        self,
        sec: str,
        ptype: str,
        field_index: int,
        *field_values: str,
    ) -> None:
        """Borra policies que matchean un filtro parcial.

        Convención Casbin:
          * ``field_index`` = índice desde donde empieza el filtro (0-based).
          * ``field_values[i]`` = valor exacto o ``'*'`` (match-all).
        """
        if sec == "p":
            stmt = delete(RBACPolicy)
            model_cls = RBACPolicy
            cols = ("sub", "dom", "obj", "act")
        elif sec == "g":
            stmt = delete(RBACGrouping)
            model_cls = RBACGrouping
            cols = ("sub", "role", "dom")
        else:
            logger.warning(
                "rbac_adapter.remove_filtered_policy: sec=%s — no soportado",
                sec,
            )
            return

        for offset, raw in enumerate(field_values):
            idx = field_index + offset
            if idx >= len(cols):
                break
            col = getattr(model_cls, cols[idx])
            if raw == "*":
                continue  # wildcard: no filtra
            stmt = stmt.where(col == raw)

        with self._session_factory() as session:
            session.execute(stmt)
            session.commit()

    # ── API extendida (no estándar de Casbin) ──────────────────────
    def list_policies(self, dom: Optional[str] = None) -> List[dict]:
        """Lista policies (para GET /api/v1/rbac/policies)."""
        with self._session_factory() as session:
            stmt = select(RBACPolicy)
            if dom:
                stmt = stmt.where(RBACPolicy.dom == dom)
            rows = session.execute(stmt).scalars().all()
            return [
                {
                    "id": str(p.id),
                    "sub": p.sub,
                    "dom": p.dom,
                    "obj": p.obj,
                    "act": p.act,
                    "effect": p.effect,
                    "priority": p.priority,
                    "note": p.note,
                }
                for p in rows
            ]

    def list_groupings(self) -> List[dict]:
        """Lista groupings."""
        with self._session_factory() as session:
            rows = session.execute(select(RBACGrouping)).scalars().all()
            return [
                {
                    "id": str(g.id),
                    "sub": g.sub,
                    "role": g.role,
                    "dom": g.dom,
                }
                for g in rows
            ]

    def delete_policy_by_id(self, policy_id: str) -> bool:
        """Borra por UUID (para DELETE /api/v1/rbac/policies/{id})."""
        from uuid import UUID
        try:
            uid = UUID(policy_id)
        except (ValueError, TypeError):
            return False
        with self._session_factory() as session:
            row = session.get(RBACPolicy, uid)
            if not row:
                return False
            session.delete(row)
            session.commit()
            return True

    def clear_all(self) -> None:
        """Borra todas las policies y groupings (helper de seed)."""
        with self._session_factory() as session:
            session.execute(delete(RBACPolicy))
            session.execute(delete(RBACGrouping))
            session.commit()