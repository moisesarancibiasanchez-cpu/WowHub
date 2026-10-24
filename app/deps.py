"""Dependencias compartidas: get_current_user, get_current_membership, get_tenant_id."""
from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core import tenant_context
from app.database import get_db
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User, UserRole
from app.security import decode_token


def _extract_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise UnauthorizedError("Falta header Authorization")
    if not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Header Authorization debe usar Bearer")
    return authorization.split(" ", 1)[1].strip()


def _peek_jwt_payload(request: Request) -> dict:
    """Lee el payload del JWT del request sin requerir BD.
    Usado por dependencias que necesitan claims como `tid` antes de
    resolver el User. Prioridad: header Authorization → cookie de sesión."""
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    token = ""
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get(ACCESS_COOKIE_NAME) or ""
    if not token:
        return {}
    try:
        return decode_token(token) or {}
    except Exception:
        return {}


def _resolve_impersonation(
    request: Request,
    db: Session,
    payload: dict,
    admin: User,
) -> Optional[User]:
    """Si el JWT tiene un claim `imp` válido, devuelve el usuario impersonado.

    En caso contrario devuelve None. Como side-effect setea
    `request.state.admin_user` y `request.state.impersonation` para que
    endpoints y audit middleware puedan registrar quién es el admin real.

    Reglas de seguridad:
    - El claim `imp` debe traer `uid` (UUID del usuario target).
    - El target debe existir, estar activo y NO ser superuser.
    - Si `imp.expires_at` está seteado, la sesión debe no estar expirada.
    """
    imp = payload.get("imp")
    if not imp:
        return None
    target_id = imp.get("uid")
    if not target_id:
        return None
    try:
        target_uid = UUID(str(target_id))
    except (ValueError, TypeError):
        return None
    target = db.get(User, target_uid)
    if not target or not target.is_active:
        return None
    # Defensa: nunca permitir impersonar a otro superuser (aunque
    # el endpoint /impersonate ya bloquea, validamos acá también por
    # si alguien forja un token directamente con jose).
    if getattr(target, "is_superuser", False):
        return None
    # Validar expiración
    expires_at_str = imp.get("expires_at")
    if expires_at_str:
        from datetime import datetime, timezone
        try:
            exp_dt = datetime.fromisoformat(str(expires_at_str).replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if now > exp_dt:
                # Impersonación expirada: devolver al admin silenciosamente.
                # (El frontend ya habrá visto expirar el banner.)
                return None
        except (ValueError, TypeError):
            pass
    # Stash para auditoría
    request.state.admin_user = admin
    request.state.impersonation = imp
    return target


def _user_from_token(request: Request, db: Session, token: str) -> User:
    """Núcleo de resolución del usuario actual a partir de un JWT de acceso.

    Concentra la lógica que comparten `get_current_user` (header
    Authorization) y `get_current_user_allow_cookie` (header o cookie).
    """
    try:
        payload = decode_token(token)
    except ValueError as e:
        raise UnauthorizedError(str(e))
    if payload.get("type") != "access":
        raise UnauthorizedError("Token inválido (no es access)")
    sub = payload.get("sub")
    if not sub:
        raise UnauthorizedError("Token sin 'sub'")
    try:
        admin_uid = UUID(sub)
    except (ValueError, TypeError):
        raise UnauthorizedError("Token con 'sub' inválido")
    admin = db.get(User, admin_uid)
    if not admin or not admin.is_active:
        raise UnauthorizedError("Usuario no encontrado o inactivo")
    # ¿Hay impersonación activa?
    target = _resolve_impersonation(request, db, payload, admin)
    if target is not None:
        return target
    return admin


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Resuelve el usuario actual a partir del JWT.

    Si el token está expirado o es inválido, lanza `UnauthorizedError`
    (que se traduce en 401).

    IMPERSONACIÓN: si el JWT incluye el claim `imp` (sólo lo emite
    `POST /superadmin/impersonate/{user_id}`), devuelve el usuario
    impersonado. El admin original queda accesible en
    `request.state.admin_user` para fines de auditoría.
    """
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    return _user_from_token(request, db, _extract_token(auth))


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Variante opcional: devuelve el User si el token es válido, o None.

    Usada por middlewares (audit, analytics) donde NO se debe cortar el
    request si no hay auth — sólo queremos enriquecer el log con el
    `user_id` cuando haya un token válido.

    IMPERSONACIÓN: igual que `get_current_user`, si el JWT tiene `imp`,
    devuelve el usuario impersonado. El admin original queda accesible
    en `request.state.admin_user`.
    """
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    try:
        payload = decode_token(auth.split(" ", 1)[1].strip())
    except Exception:
        return None
    if payload.get("type") != "access":
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    try:
        admin_uid = UUID(sub)
    except (ValueError, TypeError):
        return None
    admin = db.get(User, admin_uid)
    if not admin or not admin.is_active:
        return None
    target = _resolve_impersonation(request, db, payload, admin)
    if target is not None:
        return target
    return admin


def get_current_membership(
    request: Request,
    tenant_id: Optional[UUID] = None,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantMembership:
    """Resuelve la membresía activa. Orden de prioridad:
    1) path param `tenant_id` si viene
    2) header `X-Tenant-Id`
    3) claim `tid` del JWT (FIX: antes sólo se documentaba, ahora funciona)
    """
    return _resolve_membership(db, request, user, tenant_id, x_tenant_id)


def _resolve_membership(
    db: Session,
    request: Request,
    user: User,
    tenant_id: Optional[UUID],
    x_tenant_id: Optional[str],
) -> TenantMembership:
    """Núcleo de resolución de membresía (compartido por las dos variantes)."""
    tid: Optional[str] = None

    if tenant_id:
        tid = str(tenant_id)
    elif x_tenant_id:
        tid = x_tenant_id
    else:
        # Fallback 3: leer el claim `tid` directamente del JWT presente
        # en el request (sin revalidar, ya se validó en get_current_user).
        payload = _peek_jwt_payload(request)
        tid = payload.get("tid")

    if not tid:
        raise UnauthorizedError(
            "Falta tenant_id (path, header X-Tenant-Id o claim tid en JWT)"
        )

    m = db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == str(user.id),
            TenantMembership.tenant_id == tid,
            TenantMembership.is_active == True,  # noqa: E712
        )
    ).scalar_one_or_none()
    if not m:
        raise ForbiddenError("No tienes acceso a este tenant")
    return m


# ── Cookie de sesión ─────────────────────────────────────────────────────────
# El login setea una cookie httpOnly ("wowhub_access_token", SameSite=Lax,
# path=/) con el access token. Un `<img src>` NO puede mandar el header
# Authorization, así que toda imagen servida por un endpoint autenticado
# daba 401 en un `<img>` nativo (miniaturas del catálogo, logos, etc.).
#
# Estos dos helpers existen SÓLO para endpoints de LECTURA que el browser
# consume como subrecurso (<img>, <video>). No se usan en ningún endpoint
# que modifique estado, de modo que no se abre superficie de CSRF: la cookie
# es SameSite=Lax (no viaja en POST/PUT/DELETE cross-site) y además el
# token sigue siendo de tipo "access".
ACCESS_COOKIE_NAME = "wowhub_access_token"


def get_current_user_allow_cookie(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Como `get_current_user`, pero acepta también la cookie de sesión.

    Prioridad: header `Authorization` (API) → cookie httpOnly (`<img>`).
    """
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    token = ""
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get(ACCESS_COOKIE_NAME) or ""
    return _user_from_token(request, db, token)


def get_current_membership_allow_cookie(
    request: Request,
    tenant_id: Optional[UUID] = None,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
    user: User = Depends(get_current_user_allow_cookie),
    db: Session = Depends(get_db),
) -> TenantMembership:
    """Como `get_current_membership`, pero aceptando la cookie de sesión.

    Se usa en los endpoints que sirven ARCHIVOS para el dashboard.
    """
    return _resolve_membership(db, request, user, tenant_id, x_tenant_id)


def get_tenant_for_membership(
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> Tenant:
    tenant_id = membership.tenant_id
    if not isinstance(tenant_id, UUID):
        tenant_id = UUID(str(tenant_id))
    t = db.get(Tenant, tenant_id)
    if not t:
        raise ForbiddenError("Tenant no encontrado")
    tenant_context.set_tenant(t.id)
    return t


def require_role(*allowed: UserRole):
    """Factory de dependencias para requerir un rol específico."""
    allowed_vals = {r.value for r in allowed}

    def _checker(membership: TenantMembership = Depends(get_current_membership)) -> TenantMembership:
        if membership.role.value not in allowed_vals and not membership.is_owner:
            raise ForbiddenError(f"Requiere rol: {', '.join(allowed_vals)}")
        return membership
    return _checker


def _role_value(membership: TenantMembership) -> str:
    """Valor de rol de una membresía, normalizado a string."""
    role = getattr(membership, "role", None)
    if role is None:
        return ""
    return getattr(role, "value", str(role))


def _membership_role_value(membership: TenantMembership) -> str:
    """Rol efectivo de una membresía en minúsculas.

    ``is_owner=True`` implica "owner" aunque ``role`` diga otra cosa: el
    flag de propietario es el que el resto del sistema usa como criterio
    de autorización (mismo criterio que ``require_role``).
    """
    if getattr(membership, "is_owner", False):
        return "owner"
    return _role_value(membership).strip().lower()


def resolve_effective_tenant_role(
    db: Session,
    user: User,
    payload: Optional[dict] = None,
) -> str:
    """Rol efectivo del usuario en el tenant activo (string en minúsculas).

    FUENTE DE VERDAD: ``TenantMembership.role`` (+ ``is_owner``), **nunca**
    ``User.default_role``. ``default_role`` es sólo el rol por defecto que
    hereda una membresía nueva y su default es ``STAFF``; usarlo como
    criterio de autorización dejó a los dueños y admins de un tenant sin
    acceso a las páginas de administración del tenant (FIX V2.013).

    Orden de resolución:
      1. Claim ``tid`` del JWT → membresía activa de ese tenant.
      2. Sin ``tid`` → la membresía activa más privilegiada (owner > admin).
      3. Claim ``role`` del JWT (emitido en el login/refresh).
      4. ``User.default_role`` (último recurso).
    """
    payload = payload or {}

    rows = db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == str(user.id),
            TenantMembership.is_active == True,  # noqa: E712
        )
    ).scalars().all()

    tid = payload.get("tid")
    if tid:
        for m in rows:
            if str(m.tenant_id) == str(tid):
                return _membership_role_value(m)

    best = ""
    for m in rows:
        rv = _membership_role_value(m)
        if rv == "owner":
            return "owner"
        if rv == "admin" and not best:
            best = "admin"
    if best:
        return best

    claim_role = payload.get("role")
    if isinstance(claim_role, str) and claim_role.strip():
        return claim_role.strip().lower()

    default_role = getattr(user, "default_role", None)
    return getattr(default_role, "value", str(default_role or "")).strip().lower()


def require_platform_admin(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    """Guard para endpoints de ADMINISTRACIÓN DE PLATAFORMA (no por tenant).

    FIX 2026-09-27 (escalada de privilegios): los guards de `site_config` y
    `admin_ai` comparaban contra `user.default_role`, que el registro NUNCA
    asigna — por lo que todo usuario autogistrado quedaba con `OWNER` y podía
    editar la configuración global (tema, `maintenance_mode`) o abrir el
    circuit breaker del LLM de toda la plataforma.

    Criterio correcto: superuser, o OWNER/ADMIN de al menos una membresía
    ACTIVA. El rol se lee de `TenantMembership.role`, que es donde vive la
    autorización real, no de `User.default_role`.
    """
    if bool(getattr(user, "is_superuser", False)):
        return user

    rows = db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == str(user.id),
            TenantMembership.is_active == True,  # noqa: E712
        )
    ).scalars().all()

    for m in rows:
        if getattr(m, "is_owner", False) or _role_value(m) in ("owner", "admin"):
            return user

    raise ForbiddenError("Requiere rol OWNER o ADMIN en al menos un tenant")


def _peek_jwt_superuser(request: Request) -> bool:
    """Lee el claim `is_superuser` del JWT (sin tocar la BD).

    Si el claim no está (tokens emitidos antes de este cambio) o el token
    es inválido, devuelve False. La verificación final de DB se hace en
    `require_superuser`."""
    payload = _peek_jwt_payload(request)
    val = payload.get("is_superuser")
    if isinstance(val, bool):
        return val
    if isinstance(val, (int,)):
        return bool(val)
    if isinstance(val, str):
        return val.lower() in ("1", "true", "yes", "y", "t")
    return False


def require_superuser(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    """Guard: requiere que el usuario sea SUPERUSER de plataforma.

    Estrategia de doble verificación:
    1) Claim `is_superuser` del JWT (rápido, sin BD).
    2) Si falla el claim, fallback a `user.is_superuser` en BD (fuente de verdad).

    El flag es a nivel de USUARIO (no de membresía): un superuser ve TODOS
    los tenants y puede ejecutar acciones cross-tenant.
    """
    if _peek_jwt_superuser(request):
        return user
    if bool(getattr(user, "is_superuser", False)):
        return user
    raise ForbiddenError("Requiere rol SUPERADMIN de plataforma")


def is_superuser(user: Optional[User]) -> bool:
    """Helper: chequea is_superuser sin lanzar excepciones. Para guards opcionales."""
    return bool(user and getattr(user, "is_superuser", False))
