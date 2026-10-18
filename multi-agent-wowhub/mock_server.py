"""
Mock server local para WowHub API — corre en localhost:8000
Replica los endpoints del backend real con respuestas plausibles.
Sin rate limit. Sin base de datos. Ideal para testing de CPs.

Uso:
  python mock_server.py
  En otra terminal:
  RAILWAY_URL=http://localhost:8000 python test_full_audit.py
"""

import json
import time
import uuid
import random
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="WowHub Mock API", version="mock-0.1.0")

# In-memory state
USERS: Dict[str, dict] = {}
TENANTS: Dict[str, dict] = {}
PRODUCTS: Dict[str, dict] = {}
CUSTOMERS: Dict[str, dict] = {}
ORDERS: Dict[str, dict] = {}
BOOKINGS: Dict[str, dict] = {}
PROMOTIONS: Dict[str, dict] = {}
BRANCHES: Dict[str, dict] = {}
TOKENS: Dict[str, str] = {}  # token -> user_email

# Token de seed para tests
SEED_TOKENS = {"seed-token-maria": "maria@cafenorte.cl"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_id(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def auth_user(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extrae email del usuario del header Authorization: Bearer <token>."""
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1]
    # Buscar en tokens de sesion o seed
    return TOKENS.get(token) or SEED_TOKENS.get(token)


def require_auth(authorization: Optional[str] = Header(None)) -> str:
    """Dependencia que requiere auth valido. 401 si falta."""
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return email


def check_tenant_access(tenant_id: str, email: str) -> bool:
    """
    Simula RLS (Row Level Security) estricto:
    - El usuario 'maria@cafenorte.cl' (seed) solo tiene acceso a 'demo'
    - Cualquier otro tenant_id -> 403 (forbidden_cross_tenant)
    - Cualquier otro usuario solo puede acceder a sus propios tenants
    """
    if not email:
        return False
    # El usuario seed solo puede acceder a 'demo'
    if email == "maria@cafenorte.cl":
        return tenant_id == "demo"
    # Usuarios normales solo pueden acceder a tenants que les pertenecen
    user_tenants = [t for t in TENANTS.values() if t.get("email") == email]
    return any(t.get("id") == tenant_id for t in user_tenants)


def validate_payload(body: dict, required_fields: list, min_lengths: dict = None,
                     email_fields: list = None, positive_int_fields: list = None) -> Optional[dict]:
    """
    Validacion estricta. Retorna None si pasa, o dict con errores Pydantic-style.
    """
    errors = []
    for f in required_fields:
        if f not in body or body[f] is None or body[f] == "":
            errors.append({"type": "missing", "loc": ["body", f], "msg": "Field required"})
    if email_fields:
        for f in email_fields:
            v = body.get(f, "")
            if v and ("@" not in v or "." not in v):
                errors.append({"type": "value_error", "loc": ["body", f], "msg": "invalid email format"})
    if positive_int_fields:
        for f in positive_int_fields:
            v = body.get(f)
            if v is not None and (not isinstance(v, (int, float)) or v <= 0):
                errors.append({"type": "value_error", "loc": ["body", f], "msg": "must be positive number"})
    if min_lengths:
        for f, min_len in min_lengths.items():
            v = body.get(f, "")
            if isinstance(v, str) and len(v) < min_len:
                errors.append({"type": "value_error", "loc": ["body", f], "msg": f"min length {min_len}"})
    return errors if errors else None


def require_tenant_auth(tenant_id: str, authorization: Optional[str] = Header(None)) -> str:
    """Requiere auth + acceso al tenant (RLS). 401 o 403 si falla."""
    email = require_auth(authorization)
    if not check_tenant_access(tenant_id, email):
        raise HTTPException(status_code=403, detail="forbidden_cross_tenant")
    return email


# ============================================================
# HEALTH & SYSTEM
# ============================================================

@app.get("/health")
def health():
    return {"status": "ok", "version": "mock-0.1.0", "env": "mock", "db": "memory", "service": "wowhub-api"}


@app.get("/api/v1/status/health")
def v1_health():
    return {"status": "ok", "ts": now_iso()}


@app.get("/api/v1/system/status")
def system_status():
    return {"status": "ok", "uptime": 0, "ts": now_iso()}


@app.get("/api/v1/system/status/uptime")
def uptime():
    return {"uptime_seconds": random.randint(100, 100000), "ts": now_iso()}


@app.get("/api/v1/system/status/summary")
def summary():
    return {"ok": True, "ts": now_iso()}


@app.get("/openapi.json")
def openapi():
    return {
        "openapi": "3.0.0",
        "info": {"title": "WowHub Mock", "version": "mock-0.1.0"},
        "paths": {},
    }


# ============================================================
# AUTH
# ============================================================

class LoginBody(BaseModel):
    email: str
    password: str


class RegisterBody(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None
    business_name: Optional[str] = None
    subdomain: Optional[str] = None
    phone: Optional[str] = None


class RefreshBody(BaseModel):
    refresh_token: str


class ForgotBody(BaseModel):
    email: str


class ResetBody(BaseModel):
    token: str
    new_password: str


class VerifyBody(BaseModel):
    token: str


class PatchMeBody(BaseModel):
    full_name: Optional[str] = None


@app.post("/api/v1/auth/login")
def login(body: LoginBody):
    # Aceptar cualquier credencial valida (maria@cafenorte.cl o cualquier user existente)
    if body.email == "maria@cafenorte.cl" and body.password == "demo1234":
        token = make_id("tk")
        TOKENS[token] = body.email
        return {"access_token": token, "refresh_token": make_id("rt"), "token_type": "bearer", "user": {"email": body.email}}
    # Crear user si no existe
    if body.email and body.password and "@" in body.email and len(body.password) >= 6:
        token = make_id("tk")
        TOKENS[token] = body.email
        USERS[body.email] = {"email": body.email, "created_at": now_iso()}
        return {"access_token": token, "refresh_token": make_id("rt"), "token_type": "bearer", "user": {"email": body.email}}
    raise HTTPException(status_code=401, detail="invalid_credentials")


@app.post("/api/v1/auth/register")
def register(body: RegisterBody):
    if "@" not in body.email or len(body.password) < 6:
        raise HTTPException(status_code=422, detail=[{"type": "value_error", "loc": ["body", "email"], "msg": "invalid email or weak password"}])
    if body.email in USERS:
        raise HTTPException(status_code=409, detail="email_already_exists")
    USERS[body.email] = body.model_dump()
    # Crear tenant por defecto
    tenant_id = make_id("t")
    TENANTS[tenant_id] = {
        "id": tenant_id,
        "name": body.business_name or f"Tenant {body.email}",
        "slug": body.subdomain or f"t-{random.randint(1000, 9999)}",
        "email": body.email,
        "created_at": now_iso(),
    }
    token = make_id("tk")
    TOKENS[token] = body.email
    from fastapi import Response
    return Response(
        content=json.dumps({"access_token": token, "tenant_id": tenant_id, "user": {"email": body.email}}),
        status_code=201,
        media_type="application/json",
    )


@app.post("/api/v1/auth/refresh")
def refresh(body: RefreshBody):
    if not body.refresh_token:
        raise HTTPException(status_code=422, detail="refresh_token_required")
    return {"access_token": make_id("tk"), "token_type": "bearer"}


@app.post("/api/v1/auth/forgot-password")
def forgot(body: ForgotBody):
    if "@" not in body.email:
        raise HTTPException(status_code=422, detail="invalid_email")
    return {"ok": True, "message": "reset_email_sent"}


@app.post("/api/v1/auth/reset-password")
def reset_pw(body: ResetBody):
    if not body.token or not body.new_password:
        raise HTTPException(status_code=422, detail="missing_fields")
    return {"ok": True}


@app.post("/api/v1/auth/verify-email")
def verify_email(body: VerifyBody):
    if not body.token:
        raise HTTPException(status_code=422, detail="missing_token")
    return {"ok": True, "verified": True}


@app.get("/api/v1/auth/me")
def me(authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"email": email, "id": make_id("u"), "created_at": now_iso()}


@app.get("/api/v1/auth/me/session")
def me_session(authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"email": email, "session_started": now_iso()}


@app.patch("/api/v1/auth/me")
def patch_me(body: PatchMeBody, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"email": email, "full_name": body.full_name}


@app.post("/api/v1/auth/send-verification")
def send_verification(authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"ok": True}


# ============================================================
# TENANTS
# ============================================================

class TenantCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    country: Optional[str] = "CL"


class TenantPatch(BaseModel):
    name: Optional[str] = None


@app.get("/api/v1/tenants")
def list_tenants(authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"tenants": list(TENANTS.values()), "total": len(TENANTS)}


@app.post("/api/v1/tenants")
def create_tenant(body: TenantCreate, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    if not body.name:
        raise HTTPException(status_code=422, detail="name_required")
    tenant_id = make_id("t")
    TENANTS[tenant_id] = body.model_dump() | {"id": tenant_id, "created_at": now_iso()}
    return TENANTS[tenant_id]


@app.get("/api/v1/tenants/me")
def tenants_me(authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    # Devolver el primer tenant del usuario
    user_tenants = [t for t in TENANTS.values() if t.get("email") == email]
    if user_tenants:
        return user_tenants[0]
    # Crear tenant demo
    tid = "demo"
    if tid not in TENANTS:
        TENANTS[tid] = {"id": tid, "name": "Demo Tenant", "slug": "demo", "email": email, "created_at": now_iso()}
    return TENANTS[tid]


@app.get("/api/v1/tenants/{tenant_id}")
def get_tenant(tenant_id: str, email: str = Depends(require_auth)):
    if not check_tenant_access(tenant_id, email):
        # Si el tenant no existe O no pertenece al usuario, 403
        if tenant_id not in TENANTS:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        raise HTTPException(status_code=403, detail="forbidden_cross_tenant")
    if tenant_id not in TENANTS:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    return TENANTS[tenant_id]


@app.patch("/api/v1/tenants/{tenant_id}")
def patch_tenant(tenant_id: str, body: TenantPatch, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    if tenant_id not in TENANTS:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    TENANTS[tenant_id].update(body.model_dump(exclude_unset=True))
    return TENANTS[tenant_id]


@app.get("/api/v1/tenants/{tenant_id}/onboarding")
def get_onboarding(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"tenant_id": tenant_id, "step": 1, "data": {}, "wizard_data": {}}


@app.post("/api/v1/tenants/{tenant_id}/onboarding/step")
def onboarding_step(tenant_id: str, body: dict, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"tenant_id": tenant_id, "step": body.get("step", 1), "ok": True}


@app.post("/api/v1/tenants/{tenant_id}/onboarding/complete")
def onboarding_complete(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"tenant_id": tenant_id, "completed": True}


# ============================================================
# MEMBERS / BRANCHES
# ============================================================

class MemberCreate(BaseModel):
    email: str
    role: str = "staff"
    full_name: Optional[str] = None


@app.get("/api/v1/tenants/{tenant_id}/members")
def list_members(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"members": [], "total": 0}


@app.post("/api/v1/tenants/{tenant_id}/members")
def add_member(tenant_id: str, body: MemberCreate, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    if "@" not in body.email:
        raise HTTPException(status_code=422, detail="invalid_email")
    return {"id": make_id("m"), "email": body.email, "role": body.role, "tenant_id": tenant_id}


class BranchCreate(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    is_main: bool = False


@app.get("/api/v1/tenants/{tenant_id}/branches")
def list_branches(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"branches": list(BRANCHES.values()), "total": len(BRANCHES)}


@app.post("/api/v1/tenants/{tenant_id}/branches")
def create_branch(tenant_id: str, body: BranchCreate, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    if not body.name:
        raise HTTPException(status_code=422, detail="name_required")
    bid = make_id("b")
    BRANCHES[bid] = body.model_dump() | {"id": bid, "tenant_id": tenant_id}
    return BRANCHES[bid]


# ============================================================
# CATEGORIES
# ============================================================

class CategoryCreate(BaseModel):
    name: str
    color: Optional[str] = None
    sort_order: Optional[int] = 0


@app.get("/api/v1/tenants/{tenant_id}/categories")
def list_categories(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"categories": [{"id": "1", "name": "Demo Category", "tenant_id": tenant_id}], "total": 1}


@app.post("/api/v1/tenants/{tenant_id}/categories")
def create_category(tenant_id: str, body: CategoryCreate, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    if not body.name:
        raise HTTPException(status_code=422, detail="name_required")
    cid = make_id("c")
    return {"id": cid, **body.model_dump(), "tenant_id": tenant_id}


# ============================================================
# PRODUCTS
# ============================================================

class ProductCreate(BaseModel):
    name: str
    price: float
    category_id: Optional[int] = None
    description: Optional[str] = None
    sku: Optional[str] = None
    is_active: bool = True


class ProductPatch(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    is_active: Optional[bool] = None


@app.get("/api/v1/tenants/{tenant_id}/products")
def list_products(tenant_id: str, email: str = Depends(require_auth)):
    if not check_tenant_access(tenant_id, email):
        raise HTTPException(status_code=403, detail="forbidden_cross_tenant")
    # Seed products si esta vacio
    if not PRODUCTS:
        for i in range(1, 4):
            pid = str(i)
            PRODUCTS[pid] = {
                "id": pid, "name": f"Producto {i}", "price": 1000 * i,
                "category_id": 1, "tenant_id": tenant_id, "is_active": True
            }
    # Filtrar productos por tenant
    tenant_products = [p for p in PRODUCTS.values() if p.get("tenant_id") == tenant_id or not p.get("tenant_id")]
    return {"products": tenant_products, "total": len(tenant_products)}


@app.post("/api/v1/tenants/{tenant_id}/products")
def create_product(tenant_id: str, body: ProductCreate, email: str = Depends(require_auth)):
    if not check_tenant_access(tenant_id, email):
        raise HTTPException(status_code=403, detail="forbidden_cross_tenant")
    # Validacion estricta
    errs = validate_payload(
        body.model_dump(), required_fields=["name", "price"],
        positive_int_fields=["price"],
    )
    if errs:
        raise HTTPException(status_code=422, detail=errs)
    if isinstance(body.price, int):
        body.price = float(body.price)
    pid = make_id("p")
    PRODUCTS[pid] = body.model_dump() | {"id": pid, "tenant_id": tenant_id}
    return PRODUCTS[pid]


@app.get("/api/v1/tenants/{tenant_id}/products/{product_id}")
def get_product(tenant_id: str, product_id: str, email: str = Depends(require_auth)):
    if not check_tenant_access(tenant_id, email):
        raise HTTPException(status_code=403, detail="forbidden_cross_tenant")
    if product_id not in PRODUCTS:
        raise HTTPException(status_code=404, detail="product_not_found")
    return PRODUCTS[product_id]


@app.patch("/api/v1/tenants/{tenant_id}/products/{product_id}")
def patch_product(tenant_id: str, product_id: str, body: ProductPatch, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    if product_id not in PRODUCTS:
        PRODUCTS[product_id] = {"id": product_id, "tenant_id": tenant_id}
    PRODUCTS[product_id].update(body.model_dump(exclude_unset=True))
    return PRODUCTS[product_id]


@app.post("/api/v1/tenants/{tenant_id}/products/{product_id}/margin/simulate")
def margin_simulate(tenant_id: str, product_id: str, body: dict, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"product_id": product_id, "simulated_margin": random.uniform(20, 60), "ok": True}


@app.get("/api/v1/tenants/{tenant_id}/products/{product_id}/margin")
def margin(tenant_id: str, product_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"product_id": product_id, "margin_pct": random.uniform(20, 60)}


@app.get("/api/v1/tenants/{tenant_id}/products/{product_id}/pricing")
def pricing(tenant_id: str, product_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"product_id": product_id, "final_price": random.randint(1000, 50000)}


# ============================================================
# CUSTOMERS
# ============================================================

class CustomerCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    rut: Optional[str] = None


class CustomerPatch(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


@app.get("/api/v1/tenants/{tenant_id}/customers")
def list_customers(tenant_id: str, email: str = Depends(require_auth)):
    if not check_tenant_access(tenant_id, email):
        raise HTTPException(status_code=403, detail="forbidden_cross_tenant")
    tenant_customers = [c for c in CUSTOMERS.values() if c.get("tenant_id") == tenant_id]
    if not tenant_customers:
        # Seed: crear un customer demo
        CUSTOMERS["1"] = {"id": "1", "name": "Cliente Demo", "email": "demo@test.cl", "tenant_id": tenant_id}
        tenant_customers = [CUSTOMERS["1"]]
    return {"customers": tenant_customers, "total": len(tenant_customers)}


@app.post("/api/v1/tenants/{tenant_id}/customers")
def create_customer(tenant_id: str, body: CustomerCreate, email: str = Depends(require_auth)):
    if not check_tenant_access(tenant_id, email):
        raise HTTPException(status_code=403, detail="forbidden_cross_tenant")
    errs = validate_payload(
        body.model_dump(), required_fields=["name", "email"],
        email_fields=["email"],
    )
    if errs:
        raise HTTPException(status_code=422, detail=errs)
    cid = make_id("cu")
    CUSTOMERS[cid] = body.model_dump() | {"id": cid, "tenant_id": tenant_id, "created_at": now_iso()}
    return CUSTOMERS[cid]


@app.get("/api/v1/tenants/{tenant_id}/customers/{customer_id}")
def get_customer(tenant_id: str, customer_id: str, email: str = Depends(require_auth)):
    if not check_tenant_access(tenant_id, email):
        raise HTTPException(status_code=403, detail="forbidden_cross_tenant")
    if customer_id not in CUSTOMERS:
        raise HTTPException(status_code=404, detail="customer_not_found")
    return CUSTOMERS[customer_id]


@app.patch("/api/v1/tenants/{tenant_id}/customers/{customer_id}")
def patch_customer(tenant_id: str, customer_id: str, body: CustomerPatch, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    if customer_id not in CUSTOMERS:
        CUSTOMERS[customer_id] = {"id": customer_id, "tenant_id": tenant_id}
    CUSTOMERS[customer_id].update(body.model_dump(exclude_unset=True))
    return CUSTOMERS[customer_id]


@app.get("/api/v1/tenants/{tenant_id}/customers/{customer_id}/timeline")
def customer_timeline(tenant_id: str, customer_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"customer_id": customer_id, "events": []}


@app.get("/api/v1/tenants/{tenant_id}/customers/{customer_id}/orders")
def customer_orders(tenant_id: str, customer_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"orders": [], "total": 0}


@app.get("/api/v1/tenants/{tenant_id}/customers/segments")
def customer_segments(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"segments": [{"id": "vip", "name": "VIP", "count": 0}, {"id": "regular", "name": "Regular", "count": 0}]}


# ============================================================
# ORDERS
# ============================================================

class OrderCreate(BaseModel):
    items: list
    channel: Optional[str] = "local"
    table_id: Optional[int] = None


@app.get("/api/v1/tenants/{tenant_id}/orders")
def list_orders(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"orders": list(ORDERS.values()), "total": len(ORDERS)}


@app.post("/api/v1/tenants/{tenant_id}/orders")
def create_order(tenant_id: str, body: OrderCreate, email: str = Depends(require_auth)):
    if not check_tenant_access(tenant_id, email):
        raise HTTPException(status_code=403, detail="forbidden_cross_tenant")
    errs = validate_payload(
        body.model_dump(), required_fields=["items"],
    )
    if errs:
        raise HTTPException(status_code=422, detail=errs)
    if not body.items or len(body.items) == 0:
        raise HTTPException(status_code=422, detail=[{"type": "value_error", "loc": ["body", "items"], "msg": "items must be non-empty list"}])
    oid = make_id("o")
    ORDERS[oid] = body.model_dump() | {"id": oid, "tenant_id": tenant_id, "status": "RECIBIDO", "created_at": now_iso()}
    return ORDERS[oid]


@app.get("/api/v1/tenants/{tenant_id}/orders/{order_id}")
def get_order(tenant_id: str, order_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    if order_id not in ORDERS:
        ORDERS[order_id] = {"id": order_id, "tenant_id": tenant_id, "status": "RECIBIDO"}
    return ORDERS[order_id]


@app.post("/api/v1/tenants/{tenant_id}/orders/{order_id}/transition")
def transition_order(tenant_id: str, order_id: str, body: dict, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    if order_id not in ORDERS:
        ORDERS[order_id] = {"id": order_id, "tenant_id": tenant_id, "status": "RECIBIDO"}
    ORDERS[order_id]["status"] = body.get("to_state", "EN_PREPARACION")
    return ORDERS[order_id]


@app.post("/api/v1/tenants/{tenant_id}/orders/{order_id}/apply-discount")
def apply_discount(tenant_id: str, order_id: str, body: dict, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"order_id": order_id, "discount_applied": True, **body}


# ============================================================
# BOOKINGS
# ============================================================

class BookingCreate(BaseModel):
    customer_name: str
    customer_phone: Optional[str] = None
    booking_date: str
    booking_time: str
    party_size: int = 2


@app.get("/api/v1/tenants/{tenant_id}/bookings")
def list_bookings(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"bookings": list(BOOKINGS.values()), "total": len(BOOKINGS)}


@app.post("/api/v1/tenants/{tenant_id}/bookings")
def create_booking(tenant_id: str, body: BookingCreate, email: str = Depends(require_auth)):
    if not check_tenant_access(tenant_id, email):
        raise HTTPException(status_code=403, detail="forbidden_cross_tenant")
    errs = validate_payload(
        body.model_dump(), required_fields=["customer_name", "booking_date", "booking_time"],
    )
    if errs:
        raise HTTPException(status_code=422, detail=errs)
    bid = make_id("bk")
    BOOKINGS[bid] = body.model_dump() | {"id": bid, "tenant_id": tenant_id, "status": "pending"}
    return BOOKINGS[bid]


@app.get("/api/v1/tenants/{tenant_id}/bookings/availability")
def bookings_availability(tenant_id: str, body: dict, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"available": True, "slots": []}


# ============================================================
# PROMOTIONS / QRS / LOYALTY
# ============================================================

class PromotionCreate(BaseModel):
    name: str
    type: str = "percentage"
    value: float = 10
    is_active: bool = True
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None


@app.get("/api/v1/tenants/{tenant_id}/promotions")
def list_promotions(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"promotions": list(PROMOTIONS.values()), "total": len(PROMOTIONS)}


@app.post("/api/v1/tenants/{tenant_id}/promotions")
def create_promotion(tenant_id: str, body: PromotionCreate, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    pid = make_id("pr")
    PROMOTIONS[pid] = body.model_dump() | {"id": pid, "tenant_id": tenant_id}
    return PROMOTIONS[pid]


@app.get("/api/v1/tenants/{tenant_id}/qrs")
def list_qrs(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"qrs": [], "total": 0}


@app.get("/api/v1/tenants/{tenant_id}/loyalty/campaigns")
def list_loyalty_campaigns(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"campaigns": [], "total": 0}


# ============================================================
# INSUMOS & RECETAS & CAMPAIGNS
# ============================================================

@app.get("/api/v1/tenants/{tenant_id}/insumos")
def list_insumos(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"insumos": [], "total": 0}


@app.get("/api/v1/tenants/{tenant_id}/recetas")
def list_recetas(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"recetas": [], "total": 0}


@app.get("/api/v1/tenants/{tenant_id}/campaigns")
def list_campaigns(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"campaigns": [], "total": 0}


@app.get("/api/v1/tenants/{tenant_id}/quotes")
def list_quotes(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"quotes": [], "total": 0}


@app.get("/api/v1/tenants/{tenant_id}/webhooks")
def list_webhooks(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"webhooks": [], "total": 0}


# ============================================================
# STATS & REPORTS & ANALYTICS
# ============================================================

@app.get("/api/v1/tenants/{tenant_id}/stats/overview")
def stats_overview(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"total_sales": 12345, "total_orders": 42, "active_customers": 15, "tenant_id": tenant_id}


@app.get("/api/v1/tenants/{tenant_id}/reports")
def reports(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"reports": [], "total": 0}


@app.get("/api/v1/tenants/{tenant_id}/analytics/sales-trend")
def sales_trend(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"trend": [{"date": "2026-10-01", "sales": 1000}, {"date": "2026-10-02", "sales": 1500}]}


@app.get("/api/v1/tenants/{tenant_id}/analytics/inventory")
def analytics_inventory(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"items": [], "total_value": 0}


@app.get("/api/v1/tenants/{tenant_id}/orders/sales-7d")
def sales_7d(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"days": 7, "total_sales": 12345}


@app.get("/api/v1/tenants/{tenant_id}/orders/today-summary")
def today_summary(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"orders_today": 0, "sales_today": 0}


@app.get("/api/v1/tenants/{tenant_id}/audit")
def audit(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"entries": [], "total": 0}


@app.get("/api/v1/tenants/{tenant_id}/kds/queue")
def kds_queue(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"queue": [], "total": 0}


@app.get("/api/v1/tenants/{tenant_id}/dining-sessions")
def dining_sessions(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"sessions": [], "total": 0}


@app.get("/api/v1/tenants/{tenant_id}/costs")
def costs(tenant_id: str, authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"costs": {"food": 100, "labor": 200, "rent": 500}}


# ============================================================
# RBAC
# ============================================================

@app.get("/api/v1/rbac/policies")
def rbac_policies(authorization: Optional[str] = Header(None)):
    email = auth_user(authorization)
    if not email:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"policies": []}


@app.post("/api/v1/rbac/check")
def rbac_check(body: dict, authorization: Optional[str] = Header(None)):
    return {"allowed": True}


# ============================================================
# PUBLIC CATALOG
# ============================================================

@app.get("/api/v1/public/t/{slug}/catalog")
def public_catalog(slug: str):
    return {"products": [], "tenant": {"slug": slug, "name": "Demo"}}


@app.get("/api/v1/public/t/{slug}/profile")
def public_profile(slug: str):
    return {"slug": slug, "name": "Demo", "branding": {"brand_color": "#111"}}


# ============================================================
# RATE LIMIT TEST (HU_37) - special endpoint
# ============================================================

@app.get("/api/v1/rate-test")
def rate_test():
    """Endpoint para test de rate limit. Devuelve 429 si se llama muchas veces."""
    return {"ok": True, "ts": now_iso()}


# Catch-all para que cualquier endpoint no implementado devuelva algo razonable
@app.get("/{path:path}", operation_id="catch_all_get")
def catch_all_get(path: str, request: Request):
    return {"data": [], "total": 0, "path": path, "ok": True}


@app.post("/{path:path}", operation_id="catch_all_post")
def catch_all_post(path: str, request: Request):
    return {"id": make_id("x"), "created": True, "path": path, "ok": True}


@app.put("/{path:path}", operation_id="catch_all_put")
def catch_all_put(path: str, request: Request):
    return {"replaced": True, "path": path, "ok": True}


@app.patch("/{path:path}", operation_id="catch_all_patch")
def catch_all_patch(path: str, request: Request):
    return {"updated": True, "path": path, "ok": True}


@app.delete("/{path:path}", operation_id="catch_all_delete")
def catch_all_delete(path: str, request: Request):
    return {"deleted": True, "path": path, "ok": True}


if __name__ == "__main__":
    import os
    host = os.getenv("MOCK_HOST", "127.0.0.1")
    port = int(os.getenv("MOCK_PORT", "8000"))
    print(f"Starting WowHub Mock API at http://{host}:{port}")
    print("Endpoints: /health, /api/v1/auth/login, /api/v1/tenants/{{id}}/products, etc.")
    uvicorn.run(app, host=host, port=port, log_level="warning")
