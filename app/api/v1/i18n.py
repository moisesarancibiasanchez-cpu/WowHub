"""i18n API — traducciones."""
from fastapi import APIRouter, Header, Query

from app.services.i18n_service import I18nService

router = APIRouter(prefix="/i18n", tags=["i18n"])


@router.get("")
def get_translations(
    lang: str = Query("es"),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
):
    """Retorna todas las traducciones para el idioma solicitado."""
    if not lang or lang == "auto":
        lang = I18nService.detect_lang(accept_language or "")
    svc = I18nService(lang)
    return {
        "lang": svc.lang,
        "available": svc.available(),
        "translations": svc.get_all(),
    }


@router.get("/detect")
def detect_language(accept_language: str | None = Header(default=None, alias="Accept-Language")):
    return {"detected": I18nService.detect_lang(accept_language or "")}
