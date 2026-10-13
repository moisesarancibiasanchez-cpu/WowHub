"""Entry point con compat router para resolver el bug 'Cargando...' de la UI.

Importa la app original y le agrega el compat router. Mantener este archivo
NUEVO (no modifica main.py). Para usarlo:

    uvicorn app.main_compat:app --reload

En producción, Render entrypoint.sh ya hace este wiring automáticamente.
"""
from app.main import app  # noqa: F401
from app.api_compat import compat_router

# Incluye el router compat sin tocar el resto de la app
app.include_router(compat_router)
