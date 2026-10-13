"""HU_32 — Firmador PKCS#7 para CSV SII (Libro de Ventas).

Firma el contenido de un CSV (Libro de Ventas) con un certificado digital
``.p12`` (PKCS#12) del RUT emisor del tenant. La firma es PKCS#7 detached
en codificación DER — el SII acepta este formato para el Libro de Ventas
mensual (Res. Ex. 4119/1999).

Estrategia **fail-open**: si el archivo ``.p12`` no existe en el path
indicado, está corrupto, o la contraseña es incorrecta, NO lanzamos
excepción. Devolvemos el CSV sin firmar (codificado como ``utf-8-sig``) y
logueamos un warning. Esto es para que el MVP no rompa el flujo de negocio
del tenant si todavía no ha subido su certificado — el SII acepta CSV sin
firma, sólo exige firma cuando se sube por el portal oficial.

Cuando el ``.p12`` está disponible y la contraseña es correcta, devolvemos
los bytes DER del PKCS#7 detached signature. El caller debe almacenar la
firma como archivo separado (ej. ``LV_2026_01.csv.p7s``).
"""
from __future__ import annotations

import logging
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7

logger = logging.getLogger("wowhub.sii.signer")


def sign_csv(content: str, p12_path: str, password: str) -> bytes:
    """Firma un CSV con un certificado ``.p12`` y devuelve la firma PKCS#7 DER.

    Args:
        content: contenido del CSV a firmar (string UTF-8; se codifica con
            ``utf-8-sig`` antes de firmar para que el receptor pueda
            verificar la firma tal como se descargó).
        p12_path: ruta al archivo ``.p12`` (PKCS#12). Si no existe o no es
            un archivo válido, devuelve el CSV sin firmar (fail-open) +
            warning en log.
        password: contraseña del ``.p12``.

    Returns:
        - Si firma OK: bytes DER de la firma PKCS#7 detached.
        - Si fail-open: ``content.encode("utf-8-sig")`` (CSV con BOM, sin firma).
    """
    # Fail-open: sin certificado o sin archivo → devolvemos el CSV sin firmar.
    if not p12_path:
        logger.warning("SII sign_csv: p12_path vacío — devolviendo CSV sin firmar")
        return content.encode("utf-8-sig")

    p12_file = Path(p12_path)
    if not p12_file.exists() or not p12_file.is_file():
        logger.warning(
            "SII sign_csv: .p12 no encontrado en %s — devolviendo CSV sin firmar",
            p12_file,
        )
        return content.encode("utf-8-sig")

    try:
        p12_bytes = p12_file.read_bytes()
    except OSError as e:
        logger.warning("SII sign_csv: no se pudo leer %s (%s) — fail-open", p12_file, e)
        return content.encode("utf-8-sig")

    # Cargamos la clave privada + certificado del PKCS#12.
    try:
        loaded = serialization.pkcs12.load_key_and_certificates(
            p12_bytes,
            password.encode("utf-8") if password else b"",
        )
    except (ValueError, TypeError) as e:
        logger.warning(
            "SII sign_csv: .p12 inválido o contraseña incorrecta (%s) — fail-open",
            e,
        )
        return content.encode("utf-8-sig")

    private_key, cert, additional_certs = loaded
    if private_key is None or cert is None:
        logger.warning(
            "SII sign_csv: .p12 sin clave privada o certificado — fail-open",
        )
        return content.encode("utf-8-sig")

    # Codificamos con utf-8-sig para que el archivo bajado y la firma
    # coincidan byte-a-byte (el BOM es parte del contenido firmado).
    content_bytes = content.encode("utf-8-sig")

    try:
        builder = pkcs7.PKCS7SignatureBuilder(
            data=content_bytes,
            signers=[(cert, private_key, hashes.SHA256())],
        )
        # Incluimos la cadena de certificados cuando estén disponibles
        # (muchos .p12 emitidos por el SII traen certs intermedios).
        if additional_certs:
            for c in additional_certs:
                builder = builder.add_certificate(c)
        signature = builder.sign(
            encoding=serialization.Encoding.DER,
            options=[pkcs7.PKCS7Options.DetachedSignature],
        )
        logger.info(
            "SII sign_csv: firma PKCS#7 generada (%d bytes) para %s",
            len(signature),
            p12_file,
        )
        return signature
    except Exception as e:  # noqa: BLE001
        # Cualquier fallo criptográfico → fail-open (mejor devolver CSV sin
        # firma que romper el endpoint entero).
        logger.warning(
            "SII sign_csv: error firmando (%s) — devolviendo CSV sin firmar",
            e,
        )
        return content.encode("utf-8-sig")
