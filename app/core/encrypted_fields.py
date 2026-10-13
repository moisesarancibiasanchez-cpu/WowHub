"""HU_39 follow-up — Tipos Pydantic con cifrado transparente para PII (HU_39).

Este módulo expone tres tipos compuestos Pydantic v2 con ``Annotated``:

* ``PhoneEncryptedIn``  — input:  ``BeforeValidator(_encrypt_phone)``  únicamente.
  Aplica ``_encrypt_phone`` al valor recibido (plaintext → ciphertext Fernet).
  Se usa en schemas de **escritura** (UserCreate, UserUpdate).

* ``PhoneEncryptedOut`` — output: ``AfterValidator(_decrypt_phone_with_fallback)``
  únicamente.  Aplica ``_decrypt_phone_with_fallback`` al valor leído de la BD
  (ciphertext Fernet → plaintext).  Se usa en schemas de **lectura** (UserOut).

* ``PhoneEncrypted``    — bidireccional (ambos validators).  Mantenido para
  backwards-compatibility; en los schemas activos se usan ``*In`` / ``*Out``.

Diseño de los validators
-------------------------
* ``_encrypt_phone(plaintext)``: cifra con Fernet.  Valida longitud máxima
  ANTES de cifrar (40 chars) para preservar el contrato de la API.  ``None``
  y string vacío pasan sin tocar.  Si el valor YA parece un token Fernet
  (``is_encrypted``), NO lo re-cifra (idempotencia sobre lecturas ORM
  post-activación).
* ``_decrypt_phone_with_fallback(ciphertext)``: detecta heurísticamente si
  el valor parece un token Fernet.  Si NO parece token, lo retorna tal cual
  (plaintext legacy).  Si Fernet falla, retorna el ciphertext original
  (fail-soft para no romper el SELECT).

Activación real del cifrado (HU_39 follow-up, 2026-10-04)
---------------------------------------------------------
La migración ``2026_10_04_hu39_encrypt_phone`` aplica en orden:

1. ``ALTER TABLE users ALTER COLUMN phone TYPE VARCHAR(255)`` (PostgreSQL).
2. Backfill de filas existentes a ciphertext Fernet.
3. ``PhoneEncryptedIn`` aplicado a schemas de INPUT.
4. ``PhoneEncryptedOut`` aplicado a schemas de OUTPUT.

Ver ``app/core/encryption.py::encrypt_value`` / ``decrypt_value`` /
``is_encrypted`` para los helpers de cifrado de bajo nivel.
"""
from __future__ import annotations

from typing import Annotated, Optional

from pydantic import AfterValidator, BeforeValidator

from app.core.encryption import EncryptionError, decrypt_value, encrypt_value, is_encrypted

# Máximo plaintext aceptado para el campo ``phone``. Coincide con el
# ``max_length=40`` histórico del schema (ahora validado dentro del
# ``BeforeValidator`` porque ``Field(max_length=...)`` se aplica DESPUÉS del
# cifrado y entraría en conflicto con el token Fernet de ~100 chars).
_PHONE_PLAINTEXT_MAX_LEN: int = 40


def _encrypt_phone(v: Optional[str]) -> Optional[str]:
    """Cifra un teléfono con Fernet (idempotente sobre tokens).

    Si el valor YA parece un token Fernet (``is_encrypted``), lo retorna
    tal cual. Esto es necesario porque Pydantic v2 ejecuta el
    ``BeforeValidator`` también en ``model_validate()`` desde ORM — si la
    columna ya tiene ciphertext, no debemos re-cifrar (eso generaría un
    token del token y dispararía ``max_length``).

    Aplica validación de longitud máxima (40 chars) ANTES de cifrar para
    preservar el contrato histórico del schema.

    Args:
        v: teléfono en plaintext, ciphertext Fernet, ``None`` / ``""``.

    Raises:
        ValueError: si el plaintext excede 40 caracteres.
    """
    if v is None:
        return None
    if not isinstance(v, str):
        # Pydantic ya coerciona a str; esto es defensa en profundidad.
        v = str(v)
    if v == "":
        return v
    # Idempotencia: si ya parece token Fernet (lectura ORM post-activación),
    # NO re-cifrar. Pydantic corre BeforeValidator también en ``model_validate``,
    # por lo que este caso es real y no teórico.
    if is_encrypted(v):
        return v
    if len(v) > _PHONE_PLAINTEXT_MAX_LEN:
        raise ValueError(
            f"phone debe tener máximo {_PHONE_PLAINTEXT_MAX_LEN} caracteres "
            f"(recibido: {len(v)})."
        )
    return encrypt_value(v)


def _decrypt_phone_with_fallback(v: Optional[str]) -> Optional[str]:
    """Descifra un teléfono con fallback gracioso a plaintext / ciphertext.

    Si el valor NO parece un token Fernet (heurística ``is_encrypted``),
    lo retorna tal cual — asume plaintext legacy y evita romper SELECT sobre
    filas no migradas.

    Si Fernet falla con ``EncryptionError`` (clave incorrecta, dato
    corrupto, timestamp expirado), retorna el ciphertext original — el caller
    verá ``gAAAAA...`` en la respuesta, fail-soft.

    Args:
        v: teléfono cifrado, plaintext legacy, o ``None`` / ``""``.

    Returns:
        El teléfono descifrado, o el valor original si no aplica descifrado.
    """
    if v is None:
        return None
    if not isinstance(v, str) or v == "":
        return v
    if not is_encrypted(v):
        # No parece token Fernet — plaintext legacy. Lo retornamos tal cual.
        return v
    try:
        return decrypt_value(v)
    except EncryptionError:
        # Fallback gracioso: Fernet no pudo descifrar. Retornamos el
        # ciphertext sin cambios para no romper el flujo.
        return v


# Tipo Pydantic v2 reutilizable. Aplicar a ``phone`` en los schemas de
# ``User`` (UserBase, UserUpdate, UserOut) hace que el cifrado sea
# ``invisible`` para los route handlers — ven ``phone`` como ``str``.
PhoneEncrypted = Annotated[
    Optional[str],
    BeforeValidator(_encrypt_phone),
    AfterValidator(_decrypt_phone_with_fallback),
]

# ── Tipos separados para INPUT / OUTPUT ──────────────────────────────────────
# ``PhoneEncryptedIn`` se aplica en schemas de ESCRITURA (UserCreate, UserUpdate).
# Cifra el plaintext antes de enviar a la BD; si recibe un ciphertext Fernet
# (caso de ``model_validate`` desde ORM), lo deja intacto (idempotencia).
PhoneEncryptedIn = Annotated[
    Optional[str],
    BeforeValidator(_encrypt_phone),
]

# ``PhoneEncryptedOut`` se aplica en schemas de LECTURA (UserOut).
# Descifra el ciphertext Fernet de la BD antes de serializar a JSON;
# si recibe plaintext legacy, lo retorna tal cual (fail-soft).
PhoneEncryptedOut = Annotated[
    Optional[str],
    AfterValidator(_decrypt_phone_with_fallback),
]