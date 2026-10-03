"""HU_39 — Helper de encriptación simétrica para campos sensibles (Fernet / AES).

Este módulo provee dos funciones: ``encrypt_value(plaintext) -> str`` y
``decrypt_value(ciphertext) -> str``. Ambas operan sobre strings UTF-8 y
devuelven/consumen el formato Fernet estándar (token base64 url-safe con
versión, timestamp, IV, ciphertext y HMAC-SHA256).

Por qué Fernet y no AES-CTE / AES-GCM manual:
  * Fernet es la receta recomendada por la librería ``cryptography`` para
    "encrypt-then-authenticate" sin tener que reinventar IV, padding y MAC.
  * Internamente usa AES-128-CBC + HMAC-SHA256 + timestamp (anti-replay).
  * El output es un único string URL-safe — fácil de guardar en columnas
    ``String`` existentes sin migrar el esquema (HU_39 explícitamente pide
    NO aplicar a columnas todavía).

Gestión de la clave:
  * En PRODUCCIÓN (``settings.app_env == "production"``) se REQUIERE
    ``FIELD_ENCRYPTION_KEY`` configurada en el entorno. Si está vacía o es
    placeholder, ``_get_fernet()`` falla con ``RuntimeError`` (fail-closed).
    Esta validación se hace en ``Settings._reject_placeholder_secrets_in_production``
    al levantar el módulo ``app.config``, así que en realidad la app
    directamente NO ARRANCA sin la clave.
  * En DESARROLLO / TESTING: si ``FIELD_ENCRYPTION_KEY`` está vacía, se
    deriva determinísticamente de ``SECRET_KEY`` vía HKDF-SHA256 con un
    salt fijo de la app. Esto permite que los tests pasen sin configurar
    nada extra. La consecuencia: los datos cifrados en dev NO son
    descifrables en producción (claves distintas) — esto es intencional
    y se documenta en ``.env.example``.

HU_39 NO aplica el cifrado a columnas todavía — sólo deja el helper
disponible. La migración a columnas cifradas será un fix separado que
requiere backfill + manejo de ``decrypt_value()`` con fallback a texto
plano para datos legacy.

Comentarios en español (convención del repo).
"""
from __future__ import annotations

import base64
import logging
from functools import lru_cache
from typing import Final

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings

logger = logging.getLogger("wowhub.encryption")

# Salt fijo (público) usado al derivar la clave Fernet de ``SECRET_KEY`` en
# entornos no-productivos. Es seguro que sea público: HKDF está diseñado
# específicamente para que el salt NO necesite ser secreto.
_HKDF_SALT: Final[bytes] = b"wowhub-hu39-field-encryption-salt-v1"
_HKDF_INFO: Final[bytes] = b"wowhub-field-encryption|hu39"


class EncryptionError(Exception):
    """Error al cifrar o descifrar un valor.

    Envuelve ``InvalidToken`` (clave incorrecta, ciphertext manipulado,
    timestamp expirado) y ``ValueError`` (input malformado). El caller
    puede distinguir entre "el dato está corrupto" vs "el caller pasó
    un valor que no era string" inspeccionando ``__cause__``.
    """


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """Devuelve un ``Fernet`` singleton configurado con la clave apropiada.

    Resolución de la clave (en orden):
      1) ``settings.field_encryption_key`` si está seteada y no es el
         default vacío. Validamos que sea base64 url-safe de 32 bytes
         (44 chars antes del padding, 43 si pectxFu tiene padding).
      2) Si NO está seteada y ``settings.app_env != "production"``:
         derivamos una clave estable vía HKDF-SHA256 desde ``SECRET_KEY``.
      3) Si NO está seteada y SÍ es producción: ``EncryptionError``
         (la app ya debería haber abortado en ``Settings``; esto es
         defensa en profundidad por si alguien instancia el helper
         sin pasar por ``app.config.settings``).
    """
    raw = (settings.field_encryption_key or "").strip()

    if raw:
        # El usuario pasó una clave Fernet explícita. Validamos formato.
        try:
            decoded = base64.urlsafe_b64decode(raw)
        except Exception as exc:  # noqa: BLE001
            raise EncryptionError(
                "FIELD_ENCRYPTION_KEY no es base64 url-safe válido. "
                "Generá una nueva con: "
                "python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            ) from exc
        if len(decoded) != 32:
            raise EncryptionError(
                f"FIELD_ENCRYPTION_KEY debe decodificar a 32 bytes "
                f"(Fernet), se obtuvieron {len(decoded)} bytes."
            )
        try:
            return Fernet(raw.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise EncryptionError(
                "FIELD_ENCRYPTION_KEY no es una clave Fernet válida."
            ) from exc

    # No hay clave explícita.
    if settings.is_production:
        # Fail-closed: en producción NUNCA derivamos de SECRET_KEY.
        # Si llegamos acá, la app ya abortó en Settings; esto es belt-and-suspenders.
        raise EncryptionError(
            "HU_39: FIELD_ENCRYPTION_KEY es requerida en producción. "
            "Configúrala antes de desplegar."
        )

    # Dev / staging / testing: derivamos determinísticamente de SECRET_KEY.
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=_HKDF_INFO,
    ).derive(settings.secret_key.encode("utf-8"))
    fernet_key = base64.urlsafe_b64encode(derived)
    logger.warning(
        "HU_39 encryption: FIELD_ENCRYPTION_KEY vacía en entorno "
        "no-productivo — derivando clave Fernet de SECRET_KEY vía HKDF. "
        "Los datos cifrados en este entorno NO son compatibles con "
        "producción (claves distintas)."
    )
    return Fernet(fernet_key)


def encrypt_value(plaintext: str) -> str:
    """Cifra un string con Fernet y devuelve el token (base64 url-safe).

    Acepta cualquier string UTF-8 (incluyendo vacío). Devuelve un token
    Fernet con timestamp embebido — el descifrador puede verificar que
    el token no haya sido generado con un offset de tiempo absurdo.

    Args:
        plaintext: el valor a cifrar (ej. ``"+56 9 1234 5678"``).

    Returns:
        Token Fernet como string ASCII (seguro para columnas ``String``).

    Raises:
        EncryptionError: si el input no es string o Fernet falla.
    """
    if not isinstance(plaintext, str):
        raise EncryptionError(
            f"encrypt_value esperaba str, recibió {type(plaintext).__name__}."
        )
    try:
        token = _get_fernet().encrypt(plaintext.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — defensivo
        raise EncryptionError(f"No se pudo cifrar el valor: {exc}") from exc
    return token.decode("ascii")


def decrypt_value(ciphertext: str) -> str:
    """Descifra un token Fernet y devuelve el string original.

    Acepta el formato producido por ``encrypt_value``. Falla con
    ``EncryptionError`` si:
      * la clave cambió (token generado con otra Fernet key),
      * el token está corrupto / truncado / manipulado,
      * el timestamp interno del token está fuera de la ventana de
        tolerancia de Fernet (``InvalidToken``).

    Args:
        ciphertext: token Fernet (string base64 url-safe).

    Returns:
        El plaintext descifrado como ``str`` UTF-8.

    Raises:
        EncryptionError: token inválido, clave incorrecta, o input no-string.
    """
    if not isinstance(ciphertext, str):
        raise EncryptionError(
            f"decrypt_value esperaba str, recibió {type(ciphertext).__name__}."
        )
    # Aceptamos string vacío como no-cifrado: el caller probablemente
    # tiene una columna nullable y no sabe si el valor es legacy plaintext
    # o token Fernet. Devolver vacío evita que un campo ``phone=NULL`` se
    # convierta en 500 en un SELECT.
    if ciphertext == "":
        return ""
    try:
        plaintext = _get_fernet().decrypt(ciphertext.encode("ascii"))
    except InvalidToken as exc:
        raise EncryptionError(
            "Token Fernet inválido (clave incorrecta, dato manipulado o "
            "valor en texto plano legado)."
        ) from exc
    except Exception as exc:  # noqa: BLE001 — defensivo
        raise EncryptionError(f"No se pudo descifrar el valor: {exc}") from exc
    return plaintext.decode("utf-8")


def is_encrypted(value: str | None) -> bool:
    """Heurística barata para detectar si un string parece un token Fernet.

    Útil en la fase de migración (cuando algunas filas ya están cifradas y
    otras todavía son plaintext legado): el caller puede intentar
    ``decrypt_value()`` y caer a ``value`` original si lanza
    ``EncryptionError``.

    NO es criptográficamente concluyente — un plaintext que empiece con
    ``gAAAAA`` podría pasar el filtro falsamente. La validación real la
    hace ``decrypt_value()`` cuando llama ``Fernet.decrypt()``.

    Args:
        value: string a inspeccionar (``None`` se considera NO cifrado).

    Returns:
        ``True`` si el string tiene la pinta de un token Fernet.
    """
    if not value or not isinstance(value, str):
        return False
    # Fernet version byte = 0x80, codificado en base64 empieza con "gAAA"
    # (4 chars). Mínimo token Fernet es ~96 bytes → 128 chars b64.
    return value.startswith("gAAAAA") and len(value) >= 80