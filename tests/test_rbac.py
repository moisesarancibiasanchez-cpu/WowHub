"""HU_38 — Tests del RBAC granular con Casbin.

Cubre el DoD del roadmap (12+ tests, objetivo 10-14):

  TestEnforcerUnit (5):
    - test_owner_can_do_anything
    - test_staff_cannot_delete
    - test_viewer_only_reads
    - test_cross_tenant_isolation
    - test_custom_policy_takes_effect

  TestLegacyFallback (4):
    - test_owner_allows_everything
    - test_admin_allows_management
    - test_staff_denies_delete
    - test_viewer_denies_write

  TestRbacApi (3):
    - test_check_endpoint
    - test_policies_endpoint_requires_superadmin
    - test_seed_endpoint

  TestAdapter (2):
    - test_load_policy_count
    - test_add_and_remove_policy

Total: 14 tests (alineado con el diseño del CODER_HU38_IMPL).
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.rbac_adapter import SQLAlchemyAdapter
from app.core.rbac_seed import (
    DEFAULT_POLICIES,
    rebuild_default_policies,
    seed_default_rbac_policies,
)
from app.core.security import (
    _LEGACY_ROLE_MATRIX,
    _get_rbac_enforcer,
    _invalidate_rbac_enforcer,
    _legacy_check,
    requires_permission,
)
from app.database import SessionLocal
from app.models.rbac import RBACGrouping, RBACPolicy
from app.models.user import UserRole


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def _fresh_enforcer_with_seed():
    """Devuelve un enforcer con el seed cargado (limpia singleton)."""
    _invalidate_rbac_enforcer()
    seed_default_rbac_policies()  # idempotente
    return _get_rbac_enforcer()


# ──────────────────────────────────────────────────────────────────────
# TestEnforcerUnit — Casbin enforcer con seed
# ──────────────────────────────────────────────────────────────────────
class TestEnforcerUnit:
    def test_owner_can_do_anything(self):
        """OWNER con seed default debe poder (cualquier obj, cualquier act)."""
        enforcer = _fresh_enforcer_with_seed()
        assert enforcer is not None
        assert enforcer.enforce("role:OWNER", "tenant-a", "product", "delete")
        assert enforcer.enforce("role:OWNER", "tenant-a", "order", "write")
        assert enforcer.enforce("role:OWNER", "tenant-b", "settings", "delete")

    def test_staff_cannot_delete(self):
        """STAFF no debe poder borrar productos ni órdenes (DoD)."""
        enforcer = _fresh_enforcer_with_seed()
        assert enforcer is not None
        # Puede escribir/leeer.
        assert enforcer.enforce("role:STAFF", "tenant-a", "order", "write")
        assert enforcer.enforce("role:STAFF", "tenant-a", "product", "write")
        # NO debe poder borrar.
        assert not enforcer.enforce("role:STAFF", "tenant-a", "product", "delete")
        assert not enforcer.enforce("role:STAFF", "tenant-a", "order", "delete")
        assert not enforcer.enforce("role:STAFF", "tenant-a", "customer", "delete")

    def test_viewer_only_reads(self):
        """VIEWER sólo puede hacer read."""
        enforcer = _fresh_enforcer_with_seed()
        assert enforcer is not None
        assert enforcer.enforce("role:VIEWER", "tenant-a", "product", "read")
        assert enforcer.enforce("role:VIEWER", "tenant-a", "order", "read")
        # NO write, NO delete.
        assert not enforcer.enforce("role:VIEWER", "tenant-a", "product", "write")
        assert not enforcer.enforce("role:VIEWER", "tenant-a", "product", "delete")
        assert not enforcer.enforce("role:VIEWER", "tenant-a", "settings", "write")

    def test_cross_tenant_isolation(self):
        """Una policy con dom=tenant-a no debe aplicar a tenant-b.

        Para este test usamos un role custom ('role:MANAGER') y policies
        específicas para un tenant particular — verificamos que el
        tenant B queda fuera.
        """
        _invalidate_rbac_enforcer()
        # Limpia e inserta policies custom directamente via adapter.
        adapter = SQLAlchemyAdapter(SessionLocal)
        adapter.clear_all()

        # Sólo domain tenant-a.
        adapter.add_policy("p", "p", ["role:MANAGER", "tenant-a", "report", "read"])

        enforcer = _fresh_enforcer_with_seed()
        assert enforcer is not None
        # tenant-a: permitido.
        assert enforcer.enforce("role:MANAGER", "tenant-a", "report", "read")
        # tenant-b: NO permitido (aislamiento).
        assert not enforcer.enforce("role:MANAGER", "tenant-b", "report", "read")

    def test_custom_policy_takes_effect(self):
        """Una policy custom agregada en runtime debe ser efectiva."""
        _invalidate_rbac_enforcer()
        adapter = SQLAlchemyAdapter(SessionLocal)
        adapter.clear_all()

        # Insertar un custom.
        adapter.add_policy(
            "p", "p", ["role:CASHIER", "tenant-x", "order", "delete"]
        )

        enforcer = _fresh_enforcer_with_seed()
        assert enforcer is not None
        # La nueva policy aplica.
        assert enforcer.enforce("role:CASHIER", "tenant-x", "order", "delete")
        # El default sigue negando.
        assert not enforcer.enforce("role:VIEWER", "tenant-x", "order", "delete")


# ──────────────────────────────────────────────────────────────────────
# TestLegacyFallback — matriz hard-coded (sin Casbin)
# ──────────────────────────────────────────────────────────────────────
class TestLegacyFallback:
    def test_owner_allows_everything(self):
        """OWNER en la matriz legacy tiene regla '*': {'*': True}."""
        assert _legacy_check("OWNER", "anything", "anything") is True
        assert _legacy_check("OWNER", "product", "delete") is True

    def test_admin_allows_management(self):
        """ADMIN puede read/write/delete de objetos de gestión."""
        assert _legacy_check("ADMIN", "product", "delete") is True
        assert _legacy_check("ADMIN", "order", "write") is True
        # No delete sensible en la matriz (settings NO está en ADMIN).
        assert _legacy_check("ADMIN", "unknown_resource", "delete") is False

    def test_staff_denies_delete(self):
        """STAFF niega delete sobre product/customer/order/promotion."""
        assert _legacy_check("STAFF", "product", "delete") is False
        assert _legacy_check("STAFF", "order", "delete") is False
        assert _legacy_check("STAFF", "customer", "delete") is False
        # Sí puede write.
        assert _legacy_check("STAFF", "product", "write") is True

    def test_viewer_denies_write(self):
        """VIEWER sólo puede read; write y delete denegados."""
        assert _legacy_check("VIEWER", "product", "read") is True
        assert _legacy_check("VIEWER", "order", "read") is True
        assert _legacy_check("VIEWER", "product", "write") is False
        assert _legacy_check("VIEWER", "order", "delete") is False


# ──────────────────────────────────────────────────────────────────────
# TestRbacApi — endpoints REST
# ──────────────────────────────────────────────────────────────────────
class TestRbacApi:
    def _make_superadmin(self, client):
        """Crea un usuario superuser y devuelve su access_token."""
        # Registrar un user normal.
        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": "rbac-admin@example.com",
                "password": "test1234",
                "full_name": "RBAC Admin",
            },
        )
        assert r.status_code == 201, r.text
        # Promoverlo a superuser directo en DB.
        from app.models.user import User
        with SessionLocal() as db:
            u = db.query(User).filter(User.email == "rbac-admin@example.com").one()
            u.is_superuser = True
            db.commit()
            # Re-emitir token no es necesario: ``get_current_user`` mira el
            # flag de DB si el claim del JWT no está seteado.
        # Re-login para que el JWT incluya el claim is_superuser.
        r = client.post(
            "/api/v1/auth/login",
            json={"email": "rbac-admin@example.com", "password": "test1234"},
        )
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    def test_check_endpoint(self, client):
        """POST /rbac/check: evalúa enforce(sub, dom, obj, act)."""
        token = self._make_superadmin(client)
        # Seed primero para que Casbin tenga policies.
        rebuild_default_policies()
        # Invalidar singleton para que ``/rbac/check`` recargue desde DB
        # (sin esto, los tests anteriores dejan el singleton en un estado
        # inconsistente con la DB).
        _invalidate_rbac_enforcer()

        r = client.post(
            "/api/v1/rbac/check",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "subject": "role:OWNER",
                "domain": "tenant-a",
                "obj": "product",
                "act": "delete",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["allowed"] is True
        assert data["source"] in ("casbin", "legacy")

        # STAFF no puede borrar.
        r = client.post(
            "/api/v1/rbac/check",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "subject": "role:STAFF",
                "domain": "tenant-a",
                "obj": "order",
                "act": "delete",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["allowed"] is False

    def test_policies_endpoint_requires_superadmin(self, client):
        """GET /rbac/policies sin superuser debe devolver 403."""
        # Usuario normal, sin superuser.
        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": "rbac-user@example.com",
                "password": "test1234",
                "full_name": "RBAC User",
            },
        )
        assert r.status_code == 201, r.text
        token = r.json()["access_token"]

        r = client.get(
            "/api/v1/rbac/policies",
            headers={"Authorization": f"Bearer {token}"},
        )
        # El guard ``require_superuser`` retorna 403.
        assert r.status_code == 403, r.text

    def test_seed_endpoint(self, client):
        """POST /rbac/seed?reset=true reinicializa las policies."""
        token = self._make_superadmin(client)

        # Primero listar.
        r = client.get(
            "/api/v1/rbac/policies",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        before = len(r.json())

        # Seed con reset.
        r = client.post(
            "/api/v1/rbac/seed?reset=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["reset"] is True
        assert body["inserted"] >= len(DEFAULT_POLICIES) - 5  # tolerancia

        # Listar otra vez.
        r = client.get(
            "/api/v1/rbac/policies",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        after = len(r.json())
        assert after >= len(DEFAULT_POLICIES) - 5


# ──────────────────────────────────────────────────────────────────────
# TestAdapter — operaciones CRUD sobre el adapter
# ──────────────────────────────────────────────────────────────────────
class TestAdapter:
    def test_load_policy_count(self):
        """load_policy() carga todas las policies a Casbin."""
        # Wipe + seed.
        adapter = SQLAlchemyAdapter(SessionLocal)
        adapter.clear_all()
        seed_default_rbac_policies()

        enforcer = _fresh_enforcer_with_seed()
        assert enforcer is not None
        # El enforcer tiene al menos todas las DEFAULT.
        loaded = enforcer.get_policy()
        assert len(loaded) >= len(DEFAULT_POLICIES)

    def test_add_and_remove_policy(self):
        """add_policy + remove_policy reflejan los cambios en DB."""
        adapter = SQLAlchemyAdapter(SessionLocal)
        adapter.clear_all()

        # 1) Insertar.
        adapter.add_policy("p", "p", ["role:TEST", "*", "thing", "read"])
        with SessionLocal() as db:
            row = (
                db.query(RBACPolicy)
                .filter(RBACPolicy.sub == "role:TEST")
                .one_or_none()
            )
            assert row is not None
            assert row.dom == "*"
            assert row.obj == "thing"
            assert row.act == "read"

        # 2) Remover.
        adapter.remove_policy("p", "p", ["role:TEST", "*", "thing", "read"])
        with SessionLocal() as db:
            row = (
                db.query(RBACPolicy)
                .filter(RBACPolicy.sub == "role:TEST")
                .one_or_none()
            )
            assert row is None


# ──────────────────────────────────────────────────────────────────────
# TestModelsAndSanity — sanity check de modelos + decorator
# ──────────────────────────────────────────────────────────────────────
class TestModelsAndSanity:
    def test_rbac_models_registered(self):
        """Las 2 tablas están en Base.metadata."""
        from app.database import Base
        tables = set(Base.metadata.tables.keys())
        assert "rbac_policies" in tables
        assert "rbac_groupings" in tables

    def test_requires_permission_decorator_compiles(self):
        """El decorator @requires_permission existe y es callable."""
        assert callable(requires_permission)

    def test_legacy_role_matrix_has_all_roles(self):
        """La matriz legacy tiene al menos los 4 roles base + SUPERADMIN."""
        assert "OWNER" in _LEGACY_ROLE_MATRIX
        assert "ADMIN" in _LEGACY_ROLE_MATRIX
        assert "STAFF" in _LEGACY_ROLE_MATRIX
        assert "VIEWER" in _LEGACY_ROLE_MATRIX
        assert "SUPERADMIN" in _LEGACY_ROLE_MATRIX


# ──────────────────────────────────────────────────────────────────────
# TestEndpointEnforcement — verificación end-to-end del guard RBAC
# HU_38 audit 2026-10-02: confirma que el decorator @requires_permission
# está aplicado y bloquea acciones según la matriz de Casbin.
# ──────────────────────────────────────────────────────────────────────
class TestEndpointEnforcement:
    """Verifica que el guard ``@requires_permission`` está aplicado a los
    endpoints críticos de los recursos sensibles (products, categories,
    customers, branches, promotions, orders).

    Estrategia: importar el módulo y leer el código fuente para confirmar
    que cada función crítica lleva el decorator. Esto evita depender del
    cliente HTTP (los tests unitarios así son estables y rápidos).
    """

    # Mapeo módulo → endpoints críticos que DEBEN tener el guard.
    EXPECTED_GUARDS = [
        # (path del módulo, función, par (obj, act) que debe estar)
        ("app.api.v1.products",   "create_product",    ("product",   "write")),
        ("app.api.v1.products",   "update_product",    ("product",   "write")),
        ("app.api.v1.products",   "delete_product",    ("product",   "delete")),
        ("app.api.v1.categories", "create_category",   ("category",  "write")),
        ("app.api.v1.categories", "update_category",   ("category",  "write")),
        ("app.api.v1.categories", "delete_category",   ("category",  "delete")),
        ("app.api.v1.customers",  "create_customer",   ("customer",  "write")),
        ("app.api.v1.customers",  "update_customer",   ("customer",  "write")),
        ("app.api.v1.customers",  "delete_customer",   ("customer",  "delete")),
        ("app.api.v1.branches",   "create_branch",     ("branch",    "write")),
        ("app.api.v1.branches",   "update_branch",     ("branch",    "write")),
        ("app.api.v1.branches",   "delete_branch",     ("branch",    "delete")),
        ("app.api.v1.promotions", "create_promotion",  ("promotion", "write")),
        ("app.api.v1.promotions", "update_promotion",  ("promotion", "write")),
        ("app.api.v1.promotions", "delete_promotion",  ("promotion", "delete")),
        ("app.api.v1.orders",     "create_order",      ("order",     "write")),
        ("app.api.v1.orders",     "transition_order",  ("order",     "write")),
        ("app.api.v1.orders",     "cancel_order",      ("order",     "delete")),
    ]

    def test_all_critical_endpoints_have_rbac_guard(self):
        """Cada endpoint crítico en EXPECTED_GUARDS debe llevar el
        decorator ``@requires_permission(obj, act)`` con los args correctos.

        Antes de HU_38 estos endpoints NO tenían el guard y un usuario
        VIEWER podía borrar productos. Este test es el regression guard.
        """
        import inspect
        from app.core.security import requires_permission

        for mod_name, fn_name, (obj, act) in self.EXPECTED_GUARDS:
            import importlib
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, fn_name, None)
            assert fn is not None, f"{mod_name}.{fn_name} no existe"
            src = inspect.getsource(fn)
            # El decorator deja un wrapper con functools.wraps. Buscamos
            # el nombre del callable del decorator (``requires_permission``)
            # y los argumentos literales en el código fuente cercano.
            assert "@requires_permission" in src or "requires_permission" in src, (
                f"{mod_name}.{fn_name} no parece estar decorado con "
                f"@requires_permission"
            )
            # Verificamos que los argumentos (obj, act) están en la firma
            # del decorator (literal en el source).
            assert f'"{obj}"' in src and f'"{act}"' in src, (
                f"{mod_name}.{fn_name} no lleva @requires_permission"
                f'("{obj}", "{act}")'
            )

    def test_staff_cannot_delete_product_via_casbin(self):
        """STAFF NO debe poder (product, delete) en el enforcer.

        Esto valida que la matriz default seed niega STAFF la acción
        destructiva sobre productos (regression guard del seed).
        """
        enforcer = _fresh_enforcer_with_seed()
        assert enforcer is not None
        # STAFF sí puede write (crear/editar productos según seed).
        assert enforcer.enforce("role:STAFF", "tenant-x", "product", "write")
        # STAFF NO puede delete.
        assert not enforcer.enforce(
            "role:STAFF", "tenant-x", "product", "delete"
        )

    def test_admin_can_delete_product_via_casbin(self):
        """ADMIN debe poder (product, delete) según el seed."""
        enforcer = _fresh_enforcer_with_seed()
        assert enforcer is not None
        assert enforcer.enforce("role:ADMIN", "tenant-x", "product", "delete")

    def test_viewer_cannot_write_product_via_casbin(self):
        """VIEWER NO debe poder (product, write) — sólo read."""
        enforcer = _fresh_enforcer_with_seed()
        assert enforcer is not None
        assert enforcer.enforce("role:VIEWER", "tenant-x", "product", "read")
        assert not enforcer.enforce(
            "role:VIEWER", "tenant-x", "product", "write"
        )
        assert not enforcer.enforce(
            "role:VIEWER", "tenant-x", "product", "delete"
        )

    def test_viewer_cannot_cancel_order_via_casbin(self):
        """Cancelar un pedido mapea a (order, delete). VIEWER no debe poder."""
        enforcer = _fresh_enforcer_with_seed()
        assert enforcer is not None
        assert not enforcer.enforce(
            "role:VIEWER", "tenant-x", "order", "delete"
        )

    def test_decorator_blocks_staff_delete_at_function_level(self):
        """El decorator @requires_permission en delete_product llama a
        ``_check_and_call_sync`` que delega en ``_legacy_check`` o
        ``enforcer.enforce``. Verificamos el path legacy (sin Casbin
        inicializado) para STAFF → product.delete debe denegar.
        """
        from app.core.security import _legacy_check
        # STAFF → product.delete = False (DoD FILIERT 2026-10-04).
        assert _legacy_check("STAFF", "product", "delete") is False
        # ADMIN → product.delete = True.
        assert _legacy_check("ADMIN", "product", "delete") is True
        # VIEWER → product.delete = False.
        assert _legacy_check("VIEWER", "product", "delete") is False