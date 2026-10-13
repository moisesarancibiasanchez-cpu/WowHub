"""Seguridad: hashing de passwords, JWT tokens, helpers.

Nota: usamos ``bcrypt`` directamente (no ``passlib``) porque passlib 1.7.4
(último release, 2020) rompió compatibilidad con bcrypt 4.x/5.x al
referenciar ``bcrypt.__about__`` que ya no existe. La API de ``bcrypt``
es estable y nos da control explícito del truncado a 72 bytes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.config import settings

# ── Password hashing ─────────────────────────────────────────────────
# bcrypt tiene un límite de 72 bytes por password. Aplicamos el truncado
# de forma explícita (en bytes UTF-8) tanto al hashear como al verificar,
# para mantener consistencia con hashes preexistentes generados por
# passlib en la misma app.
_BCRYPT_MAX_BYTES = 72
_BCRYPT_DEFAULT_ROUNDS = 12  # mismo coste por defecto que passlib


def _normalize(plain: str) -> bytes:
    """Codifica un password a bytes y trunca a 72 bytes (límite de bcrypt)."""
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    """Hashea un password en texto plano con bcrypt + sal aleatoria.

    Devuelve el hash como ``str`` (decodificado del ``bytes`` que produce
    ``bcrypt.hashpw``) para mantener el contrato previo con la base de
    datos (columna ``password_hash`` de tipo ``String``).
    """
    if not plain:
        raise ValueError("password must be a non-empty string")
    salt = bcrypt.gensalt(rounds=_BCRYPT_DEFAULT_ROUNDS)
    return bcrypt.hashpw(_normalize(plain), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica un password contra un hash bcrypt.

    Acepta tanto hashes ``$2b$`` (generados por esta función) como
    ``$2a$`` (los que producía passlib 1.7.4 con bcrypt 3.x/4.0.x),
    porque ``bcrypt.checkpw`` reconoce ambos prefijos.
    """
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(_normalize(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Hash malformado o encoding inválido: nunca coincidirá.
        return False


# ── JWT ──────────────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    subject: str | UUID,
    *,
    tenant_id: Optional[UUID] = None,
    role: Optional[str] = None,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """Genera un access token JWT.

    `subject` = user_id. Incluye `tid` (tenant) y `role` si aplica.
    """
    now = _now()
    expire = now + timedelta(minutes=settings.jwt_access_ttl_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }
    if tenant_id is not None:
        payload["tid"] = str(tenant_id)
    if role is not None:
        payload["role"] = role
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str | UUID) -> str:
    now = _now()
    expire = now + timedelta(days=settings.jwt_refresh_ttl_days)
    payload = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Decodifica y valida un JWT. Lanza JWTError si es inválido/expirado."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e
