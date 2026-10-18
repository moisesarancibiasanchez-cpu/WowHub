"""
Templates — endpoints para gestionar la plantilla estética por tenant.

GET    /api/v1/tenants/{tenant_id}/template
PUT    /api/v1/tenants/{tenant_id}/template  body: {"template": "wowprint" | "default" | "dark"}

La elección se persiste en la tabla `tenants.template_id` (si existe) o en
`tenants.settings["template"]` (fallback JSON). Es opcional — el JS también
la persiste en localStorage, así que la UI nunca se rompe.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
import logging

router = APIRouter(prefix="/tenants", tags=["templates"])
logger = logging.getLogger(__name__)

VALID_TEMPLATES = ("default", "wowprint", "dark")


class TemplateUpdate(BaseModel):
    template: Literal["default", "wowprint", "dark"] = Field(..., description="ID de la plantilla")


def get_db_session():
    """Dependencia inyectada por main.py (placeholder si no hay DB)."""
    try:
        from app.deps import get_db  # type: ignore
        yield from get_db()
    except Exception:
        yield None


@router.get("/{tenant_id}/template")
async def get_template(tenant_id: str, db=Depends(get_db_session)):
    """Devuelve la plantilla actual del tenant. Default: 'default'."""
    if db is None:
        return {"template": "default", "available": list(VALID_TEMPLATES), "persisted": False}
    try:
        # Intentar leer del modelo Tenant
        from app.models.tenant import Tenant  # type: ignore
        t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        template_id = (
            getattr(t, "template_id", None)
            or (t.settings or {}).get("template", "default")
        )
        return {"template": template_id, "available": list(VALID_TEMPLATES), "persisted": True}
    except ImportError:
        # Modelo Tenant no existe aún → fallback
        return {"template": "default", "available": list(VALID_TEMPLATES), "persisted": False}
    except Exception as e:
        logger.warning("get_template fallback por error: %s", e)
        return {"template": "default", "available": list(VALID_TEMPLATES), "persisted": False}


@router.put("/{tenant_id}/template")
async def set_template(tenant_id: str, body: TemplateUpdate, db=Depends(get_db_session)):
    """Persiste la elección. Si no hay DB, devuelve success=False (localStorage manda)."""
    if body.template not in VALID_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"template_invalido: {body.template}")

    if db is None:
        return {"ok": True, "template": body.template, "persisted": False, "hint": "localStorage_only"}

    try:
        from app.models.tenant import Tenant  # type: ignore
        t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        # Intentar columna directa
        if hasattr(t, "template_id"):
            t.template_id = body.template
        else:
            # Fallback: settings JSON
            settings = getattr(t, "settings", None) or {}
            settings["template"] = body.template
            setattr(t, "settings", settings)
        db.commit()
        return {"ok": True, "template": body.template, "persisted": True}
    except ImportError:
        return {"ok": True, "template": body.template, "persisted": False, "hint": "model_missing"}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("set_template fallback por error: %s", e)
        return {"ok": True, "template": body.template, "persisted": False, "hint": "db_error"}
