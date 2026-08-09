"""I18nService — internacionalización (es, en, pt)."""
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("wowhub.i18n")

# Directorio de traducciones (relativo a /app)
I18N_DIR = Path(__file__).parent.parent / "i18n"

# Cache en memoria
_TRANSLATIONS: dict[str, dict] = {}


def _load(lang: str) -> dict:
    if lang in _TRANSLATIONS:
        return _TRANSLATIONS[lang]
    path = I18N_DIR / f"{lang}.json"
    if not path.exists():
        path = I18N_DIR / "es.json"  # fallback
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            _TRANSLATIONS[lang] = data
            return data
    except Exception as e:
        logger.warning("No se pudo cargar i18n %s: %s", lang, e)
        return {}


class I18nService:
    """Servicio de traducciones."""

    SUPPORTED = ["es", "en", "pt"]

    def __init__(self, lang: str = "es"):
        self.lang = lang if lang in self.SUPPORTED else "es"
        self.translations = _load(self.lang)

    def t(self, key: str, default: Optional[str] = None, **kwargs) -> str:
        """Traduce una clave. Soporta interpolación {var}."""
        value = self.translations.get(key, default or key)
        try:
            return value.format(**kwargs)
        except Exception:
            return value

    def get_all(self) -> dict:
        return dict(self.translations)

    def available(self) -> list[str]:
        return self.SUPPORTED

    @staticmethod
    def detect_lang(accept_language: str) -> str:
        """Detecta idioma desde header Accept-Language."""
        if not accept_language:
            return "es"
        # Parsear "es-CL,es;q=0.9,en;q=0.8"
        for part in accept_language.split(","):
            lang = part.split(";")[0].strip().lower()
            short = lang.split("-")[0]
            if short in I18nService.SUPPORTED:
                return short
        return "es"
