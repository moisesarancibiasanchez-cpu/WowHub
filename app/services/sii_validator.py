"""HU_32 — Validador y formateador de RUT chileno (sin dependencias externas).

Implementa el algoritmo oficial del SII (Servicio de Impuestos Internos de Chile)
para validar el dígito verificador (DV) de un RUT mediante módulo 11.

Funciones:
    - clean_rut(rut):    quita puntos, espacios y guiones; uppercase al DV
    - validate_rut(rut): True si el DV coincide (módulo 11)
    - format_rut(rut):   formato canónico "12.345.678-9"

No usa `python-rut` ni librerías externas — implementación pura en stdlib.
"""
from __future__ import annotations

import re
from typing import Final

# Regex que acepta: 1-8 dígitos + (punto|guión opcional) + dígito o K mayúscula
# (sin la K minúscula, porque el SII la canonicaliza a mayúscula).
_RUT_RE: Final = re.compile(r"^(\d{1,8})[\.\-]?([0-9K])$")


def clean_rut(rut: str) -> str:
    """Quita puntos, espacios y guiones; deja el DV en mayúscula.

    >>> clean_rut("12.345.678-5")
    '123456785'
    >>> clean_rut(" 12-345-678-k ")
    '12345678K'
    """
    if not isinstance(rut, str):
        return ""
    return rut.replace(".", "").replace(" ", "").replace("-", "").upper().strip()


def _dv_calc(body: str) -> str:
    """Calcula el dígito verificador esperado (módulo 11) para `body`."""
    s = 0
    factor = 2
    for ch in reversed(body):
        s += int(ch) * factor
        factor = 2 if factor == 7 else factor + 1
    expected = 11 - (s % 11)
    if expected == 11:
        return "0"
    if expected == 10:
        return "K"
    return str(expected)


def validate_rut(rut: str) -> bool:
    """Valida un RUT chileno.

    Acepta cualquier formato razonable:
      - "12345678-5" (con guión)
      - "12.345.678-5" (con puntos y guión)
      - "123456785" (sin separadores)

    >>> validate_rut("12.345.678-5")
    True
    >>> validate_rut("20.123.456-K")
    True
    >>> validate_rut("1-9")
    True
    >>> validate_rut("12.345.678-9")
    False
    >>> validate_rut("")
    False
    >>> validate_rut("abc")
    False
    """
    if not isinstance(rut, str) or not rut:
        return False
    raw = clean_rut(rut)
    if not raw or len(raw) < 2:
        return False
    if not _RUT_RE.match(raw):
        return False
    body, dv = raw[:-1], raw[-1]
    if not body.isdigit():
        return False
    return _dv_calc(body) == dv


def format_rut(rut: str) -> str:
    """Devuelve el RUT en formato canónico "12.345.678-9".

    Inserta puntos cada 3 dígitos desde la derecha y agrega el guión antes del DV.

    >>> format_rut("123456785")
    '12.345.678-5'
    >>> format_rut("12345678K")
    '12.345.678-K'
    >>> format_rut("1-9")
    '1-9'
    """
    if not isinstance(rut, str) or not rut:
        return ""
    raw = clean_rut(rut)
    if not raw or len(raw) < 2:
        return raw
    # Si el formato limpio no calza, devolvemos tal cual (no rompemos).
    if not _RUT_RE.match(raw):
        return raw
    body, dv = raw[:-1], raw[-1]
    # Inserción de puntos desde la derecha cada 3 dígitos.
    parts: list[str] = []
    buf = ""
    for ch in reversed(body):
        buf = ch + buf
        if len(buf) == 3:
            parts.insert(0, buf)
            buf = ""
    if buf:
        parts.insert(0, buf)
    return f"{'.'.join(parts)}-{dv}"
