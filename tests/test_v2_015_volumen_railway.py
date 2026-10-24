"""Regresión V2.015 (2026-10-24) — volumen persistente de Railway.

Contexto
--------
El almacenamiento de producción (Railway) es EFÍMERO: el directorio
``/app/storage`` vive dentro del contenedor y no está montado en un volumen
persistente, así que cada despliegue borra las imágenes subidas. Verificado
en producción: los 12 uploads del tenant de prueba estaban registrados en
la base de datos y ninguno tenía archivo en disco.

Este release deja el lado de código listo para que el volumen funcione y
documenta el procedimiento exacto (docs/DEPLOY_RAILWAY.md §7).

Los tests fijan:
  · el entrypoint ajusta los permisos del volumen y baja privilegios;
  · el script de diagnóstico distingue "disco local" de "disco de
    producción" y tiene un modo --db-only;
  · el runbook documenta el procedimiento completo.
"""
from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(path: str) -> str:
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def _entrypoint() -> str:
    return _read(os.path.join(ROOT, "scripts", "entrypoint.sh"))


def _script() -> str:
    return _read(os.path.join(ROOT, "scripts", "check_missing_uploads.py"))


def _dockerfile() -> str:
    return _read(os.path.join(ROOT, "Dockerfile"))


def _runbook() -> str:
    return _read(os.path.join(ROOT, "docs", "DEPLOY_RAILWAY.md"))


# ════════════════════════════════════════════════════════════════════════
# 1. El entrypoint deja el volumen utilizable
# ════════════════════════════════════════════════════════════════════════

def test_el_entrypoint_ajusta_los_permisos_del_volumen():
    """Railway monta el volumen como root y la imagen corre como `wowhub`:
    sin chown, las subidas fallan con EACCES."""
    sh = _entrypoint()
    assert 'chown -R wowhub:wowhub /app/storage' in sh, (
        "el entrypoint debe darle el volumen al usuario de la app"
    )
    assert 'mkdir -p /app/storage' in sh


def test_el_entrypoint_baja_privilegios_antes_de_arrancar_uvicorn():
    """Con RAILWAY_RUN_UID=0 el contenedor arranca como root; la app debe
    seguir corriendo como `wowhub`."""
    sh = _entrypoint()
    i = sh.find('if [ "$(id -u)" = "0" ]')
    assert i != -1, "el entrypoint debe detectar si arrancó como root"
    bloque = sh[i:i + 2000]
    for herramienta in ("gosu", "setpriv", "su -s /bin/sh"):
        assert herramienta in bloque, (
            f"debe existir una vía de bajada de privilegios ({herramienta})"
        )
    # El bloque de privilegios tiene que ejecutarse ANTES de arrancar uvicorn.
    j_uvicorn = sh.find("exec uvicorn")
    assert 0 < i < j_uvicorn, (
        "los privilegios se deben bajar antes de arrancar uvicorn"
    )


def test_el_bloque_de_privilegios_no_se_reentra_en_bucle():
    """Al re-ejecutar el entrypoint como `wowhub`, `id -u` ya no es 0: el
    bloque no debe volver a ejecutarse (si no, bucle infinito)."""
    sh = _entrypoint()
    i = sh.find('if [ "$(id -u)" = "0" ]')
    bloque = sh[i:i + 2000]
    assert bloque.count('if [ "$(id -u)" = "0" ]') == 1, (
        "el bloque de root debe aparecer una sola vez"
    )
    assert "exit 0" not in bloque.split("fi")[0]


def test_la_imagen_sigue_corriendo_como_usuario_no_root():
    """El Dockerfile declara `USER wowhub`: por eso hace falta el bloque de
    permisos cuando hay un volumen montado."""
    df = _dockerfile()
    assert "USER wowhub" in df
    assert "RUN useradd" in df


def test_el_workdir_de_la_imagen_coincide_con_el_mount_path():
    """STORAGE_PATH por defecto es ./storage y el WORKDIR es /app: el
    volumen debe montarse en /app/storage para que coincidan."""
    df = _dockerfile()
    assert "WORKDIR /app" in df
    assert "mkdir -p /app/data /app/storage" in df


# ════════════════════════════════════════════════════════════════════════
# 2. El script de diagnóstico
# ════════════════════════════════════════════════════════════════════════

def test_el_script_tiene_modo_db_only():
    """Desde la máquina del usuario el disco de producción no existe: el
    modo --db-only lista lo que la plataforma tiene registrado."""
    src = _script()
    assert '"--db-only"' in src
    assert "db_only" in src


def test_el_script_avisa_cuando_el_disco_no_es_el_de_produccion():
    """Sin ese aviso, correrlo localmente haría creer que se perdió todo."""
    src = _script()
    assert "no existe en esta máquina" in src
    assert "railway ssh" in src or "railway run" in src


def test_el_script_no_borra_nada():
    """Es de sólo lectura: no puede tocar la base ni el disco."""
    src = _script()
    for peligroso in (".delete()", ".unlink()", "os.remove", "shutil.rmtree", "DROP "):
        assert peligroso not in src, f"el script no debe usar {peligroso}"


def test_el_script_acepta_console_utf8():
    """El aviso usa caracteres no-ASCII: con cp1252 (consola de Windows)
    revienta con UnicodeEncodeError."""
    src = _script()
    assert 'sys.stdout.reconfigure(encoding="utf-8"' in src


# ════════════════════════════════════════════════════════════════════════
# 3. El runbook
# ════════════════════════════════════════════════════════════════════════

def test_el_runbook_documenta_el_procedimiento_completo():
    doc = _runbook()
    assert "/app/storage" in doc, "debe indicar el Mount Path exacto"
    assert "RAILWAY_RUN_UID=0" in doc, (
        "debe indicar la variable que resuelve los permisos del volumen"
    )
    assert "check_missing_uploads" in doc, (
        "debe indicar cómo saber qué imágenes hay que resubir"
    )
    assert "Rollback" in doc or "rollback" in doc.lower()


def test_el_runbook_explica_el_paso_de_verificacion():
    """La verificación clave: forzar un redeploy y ver si la imagen sigue."""
    doc = _runbook()
    assert "Redeploy" in doc
    assert "sigue" in doc.lower()


def test_railway_json_no_declara_volumemounts():
    """El esquema oficial de railway.json no admite `volumeMounts`: el
    volumen se crea desde el panel, no en el repo.

    Si alguien lo agrega, el deploy puede fallar por un volumeId que no
    existe en el proyecto.
    """
    import json

    with io.open(os.path.join(ROOT, "railway.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    deploy = data.get("deploy", {})
    assert "volumeMounts" not in deploy, (
        "railway.json no admite volumeMounts (el volumen va en el panel)"
    )
