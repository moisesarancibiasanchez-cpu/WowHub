"""Plugin config-schema validator (HU_45).

Cada `MarketplacePlugin` declara un JSON Schema (almacenado como TEXT en
`config_schema`). Antes de instalar o actualizar la config del plugin
validamos el payload del tenant contra ese schema.

Usamos `jsonschema` 4.x (ya en el venv). Si por alguna razón no está
disponible (entornos sin internet para resolver deps), caemos a un
validador mínimo que cubre los casos más comunes: required, type,
properties, enum, minLength, maxLength, minimum, maximum, items.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    import jsonschema  # type: ignore
    from jsonschema import Draft7Validator  # type: ignore

    _HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover - fallback
    _HAS_JSONSCHEMA = False

logger = logging.getLogger("wowhub.plugin_schema")

# Tipos JSON Schema soportados por el validador mínimo
_JSON_TYPES = {"string", "number", "integer", "boolean", "array", "object", "null"}


def parse_schema(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """Decodifica el TEXT del schema.

    Devuelve None si el schema está vacío o es inválido (en ese caso
    significa que el plugin no exige config — todo lo que mande el
    tenant pasa).
    """
    if not raw:
        return None
    if not isinstance(raw, str):
        return raw  # ya es dict
    raw = raw.strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("plugin_schema: schema no es JSON válido: %s", e)
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _validate_minimal(schema: Dict[str, Any], config: Any) -> Tuple[bool, List[str]]:
    """Validador mínimo (fallback). Retorna (ok, errores)."""
    errors: List[str] = []

    if "type" in schema:
        expected = schema["type"]
        if isinstance(expected, list):
            ok = any(_type_matches(t, config) for t in expected)
        else:
            ok = _type_matches(expected, config)
        if not ok:
            errors.append(
                f"Tipo incorrecto: esperaba {expected}, recibí {type(config).__name__}"
            )
            # Si el tipo no calza, los demás chequeos son no-ops
            return False, errors

    if isinstance(config, dict):
        for req in schema.get("required", []):
            if req not in config:
                errors.append(f"Campo obligatorio faltante: '{req}'")

        properties = schema.get("properties") or {}
        for key, value in config.items():
            if key in properties:
                sub_ok, sub_errs = _validate_minimal(properties[key], value)
                for e in sub_errs:
                    errors.append(f"{key}.{e}" if "." not in e else f"{key}: {e}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"Propiedad no permitida: '{key}'")

    if isinstance(config, str):
        if "minLength" in schema and len(config) < schema["minLength"]:
            errors.append(f"Longitud mínima {schema['minLength']}, recibí {len(config)}")
        if "maxLength" in schema and len(config) > schema["maxLength"]:
            errors.append(f"Longitud máxima {schema['maxLength']}, recibí {len(config)}")
        if "enum" in schema and config not in schema["enum"]:
            errors.append(f"Valor '{config}' no está en enum {schema['enum']}")

    if isinstance(config, (int, float)) and not isinstance(config, bool):
        if "minimum" in schema and config < schema["minimum"]:
            errors.append(f"Valor mínimo {schema['minimum']}, recibí {config}")
        if "maximum" in schema and config > schema["maximum"]:
            errors.append(f"Valor máximo {schema['maximum']}, recibí {config}")
        if "enum" in schema and config not in schema["enum"]:
            errors.append(f"Valor '{config}' no está en enum {schema['enum']}")

    if isinstance(config, list) and "items" in schema:
        for i, item in enumerate(config):
            sub_ok, sub_errs = _validate_minimal(schema["items"], item)
            for e in sub_errs:
                errors.append(f"[{i}].{e}" if "." not in e else f"[{i}]: {e}")

    return (len(errors) == 0), errors


def _type_matches(type_name: str, value: Any) -> bool:
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "null":
        return value is None
    return True  # tipo desconocido → no bloqueamos


def validate_config(
    schema_raw: Optional[str],
    config: Any,
) -> Tuple[bool, List[str]]:
    """Valida `config` contra el JSON Schema `schema_raw`.

    Args:
        schema_raw: contenido de `MarketplacePlugin.config_schema` (TEXT).
            Si es None o inválido, no se valida nada y retorna (True, []).
        config: payload que mandó el tenant. Puede ser dict, string JSON,
            o cualquier JSON-serializable.

    Returns:
        Tupla (ok, errores). `errores` es lista vacía si todo bien.
    """
    schema = parse_schema(schema_raw)
    if schema is None:
        # Sin schema → sin validación
        return True, []
    if config is None:
        config = {}
    # Si config viene como string, intentamos decodificarlo (algunos
    # endpoints lo reciben como JSON-encoded)
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except json.JSONDecodeError:
            # Si no se puede parsear, es un error de schema (tipo esperado: object)
            if schema.get("type") in ("object", None):
                return False, ["config debe ser un objeto JSON, recibí string"]
            # si el schema esperaba string, lo aceptamos tal cual
            if schema.get("type") == "string":
                config = config

    if _HAS_JSONSCHEMA:
        try:
            validator = Draft7Validator(schema)
            errors = sorted(validator.iter_errors(config), key=lambda e: e.path)
            messages = [f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}" for err in errors]
            return (len(messages) == 0), messages
        except jsonschema.SchemaError as e:  # pragma: no cover
            logger.warning("plugin_schema: schema inválido: %s", e)
            # Si el schema mismo está malformado, no bloqueamos
            return True, []

    # Fallback
    return _validate_minimal(schema, config)


__all__ = ["validate_config", "parse_schema"]