"""Tests HU_39 — helper de encriptación Fernet para campos sensibles.

NO prueba columnas reales todavía (la migración a columnas cifradas es
un fix separado que requiere backfill + fallback de plaintext legado).
Sólo cubre el contrato del helper:
  * roundtrip encrypt/decrypt
  * detección heurística is_encrypted()
  * inputs malformados / inválidos
  * fail-closed en producción sin FIELD_ENCRYPTION_KEY
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core import encryption
from app.core.encryption import (
    EncryptionError,
    decrypt_value,
    encrypt_value,
    is_encrypted,
)


@pytest.fixture(autouse=True)
def _reset_fernet_cache():
    """Limpia el singleton Fernet entre tests (cada test setea sus propias
    env vars y necesita recalcular la clave)."""
    encryption._get_fernet.cache_clear()
    yield
    encryption._get_fernet.cache_clear()


# ── Roundtrip básico ──────────────────────────────────────────────────
def test_roundtrip_con_clave_derivada_en_dev():
    """En dev (sin FIELD_ENCRYPTION_KEY), encrypt + decrypt debe ser inverso."""
    # El fixture limpia la cache; por defecto APP_ENV no es production en
    # conftest (APP_ENV=testing), así que se usa la derivación HKDF.
    ct = encrypt_value("+56 9 1234 5678")
    assert ct != "+56 9 1234 5678"
    assert decrypt_value(ct) == "+56 9 1234 5678"


def test_roundtrip_string_vacio():
    """encrypt('') devuelve un token; decrypt('') devuelve '' (atajo seguro)."""
    ct = encrypt_value("")
    # Fernet cifra empty string como un token válido (no es lo mismo que "").
    assert isinstance(ct, str) and ct != ""
    # Pero decrypt('') es shortcut: devuelve "" sin tocar Fernet.
    assert decrypt_value("") == ""


def test_roundtrip_caracteres_unicode():
    """Acepta tildes, emojis, CJK — codificación UTF-8 end-to-end."""
    for sample in [
        "Mesa 4 — reserva confirmada",
        "Café con leche ☕",
        "予約 #1234 山田太郎",
        "Dirección: Calle Ñuble #1234, Depto. 4B",
    ]:
        assert decrypt_value(encrypt_value(sample)) == sample


def test_roundtrip_string_largo():
    """Strings largos (e.g. direcciones extensas) deben cifrar/descifrar OK."""
    long_value = "Línea 1\nLínea 2\n" + ("x" * 5000) + "\nFin"
    assert decrypt_value(encrypt_value(long_value)) == long_value


# ── Tokens NO son deterministas ───────────────────────────────────────
def test_ciphertext_no_es_determinista():
    """Fernet incluye IV aleatorio + timestamp: cifrar el mismo plaintext
    dos veces produce tokens distintos (anti-correlation attacks)."""
    a = encrypt_value("mismo valor")
    b = encrypt_value("mismo valor")
    assert a != b
    # Pero ambos descifran al mismo plaintext.
    assert decrypt_value(a) == decrypt_value(b) == "mismo valor"


# ── Detección heurística is_encrypted ──────────────────────────────────
def test_is_encrypted_true_para_token_fernet():
    ct = encrypt_value("cualquier cosa")
    assert is_encrypted(ct) is True


def test_is_encrypted_false_para_texto_plano():
    assert is_encrypted("+56 9 1234 5678") is False
    assert is_encrypted("juan@example.com") is False
    assert is_encrypted("Av. Apoquindo 4501") is False


def test_is_encrypted_false_para_none_y_vacio():
    assert is_encrypted(None) is False
    assert is_encrypted("") is False


def test_is_encrypted_solo_es_heuristica():
    """Un plaintext que coincidentemente empiece con 'gAAAAA' pasa el
    filtro — pero ``decrypt_value`` lo rechaza porque Fernet.valid signature
    falla. Documentamos esa limitación."""
    fake = "gAAAAA" + "x" * 100  # parece Fernet, pero no lo es
    assert is_encrypted(fake) is True  # heurística OK
    with pytest.raises(EncryptionError):
        decrypt_value(fake)  # Fernet real rechaza


# ── Clave explícita vía env var ────────────────────────────────────────
def test_roundtrip_con_clave_explicita(monkeypatch):
    """Si FIELD_ENCRYPTION_KEY está seteada, se usa esa (no la derivada).

    Para que Pydantic re-lea el env var, monkeypatch debe operar ANTES del
    primer import de ``app.config.settings`` (o forzar reload). Como el
    fixture autouse limpia el cache del helper, sólo necesitamos que el
    helper VUELVA a llamar a ``_get_fernet()`` con la nueva ``settings``
    que apunta al valor actualizado."""
    real_key = Fernet.generate_key().decode()
    # Mutamos settings directamente (Pydantic permite setear atributos
    # mientras no estén en ``model_config['frozen']``).
    monkeypatch.setattr(
        encryption.settings, "field_encryption_key", real_key
    )
    encryption._get_fernet.cache_clear()

    ct = encrypt_value("dato bajo clave explícita")
    assert decrypt_value(ct) == "dato bajo clave explícita"


def test_clave_explicita_invalida_rechaza(monkeypatch):
    """FIELD_ENCRYPTION_KEY que no es base64 url-safe válido → EncryptionError."""
    monkeypatch.setattr(
        encryption.settings, "field_encryption_key", "esto-no-es-base64!!!"
    )
    encryption._get_fernet.cache_clear()
    with pytest.raises(EncryptionError, match="base64"):
        encrypt_value("test")


def test_clave_explicita_longitud_incorrecta_rechaza(monkeypatch):
    """base64 url-safe válido pero de longitud ≠ 32 bytes → EncryptionError."""
    import base64
    # 32 chars base64 = 24 bytes → no es Fernet key.
    bad = base64.urlsafe_b64encode(b"x" * 24).decode()
    monkeypatch.setattr(encryption.settings, "field_encryption_key", bad)
    encryption._get_fernet.cache_clear()
    with pytest.raises(EncryptionError, match="32 bytes"):
        encrypt_value("test")


# ── Fail-closed en producción ──────────────────────────────────────────
def test_sin_clave_en_produccion_aborta_en_config():
    """En APP_ENV=production, ``Settings()`` levanta ``ValidationError`` si
    ``FIELD_ENCRYPTION_KEY`` está vacía o placeholder. Verificamos la rama
    aislada de _reject_placeholder_secrets_in_production usando una
    instancia de Settings construida manualmente con los demás secretos
    válidos."""
    from pydantic import ValidationError

    from app.config import Settings

    # Construimos Settings con APP_ENV=production y FIELD_ENCRYPTION_KEY vacía.
    # Los demás los pasamos válidos para aislar la culpa.
    with pytest.raises(ValidationError, match="FIELD_ENCRYPTION_KEY"):
        Settings(
            app_env="production",
            field_encryption_key="",
            secret_key="a" * 32,
            jwt_secret="b" * 32,
            webhook_secret="c" * 32,
            debug=False,
            storage_public=False,
        )


def test_helper_falla_si_alguien_instancia_sin_settings_de_prod(monkeypatch):
    """Belt-and-suspenders: aunque la validación de Settings fallara, el
    helper debe negarse a derivar la clave en producción. Simulamos
    ``settings.app_env='production'`` y ``field_encryption_key=''``.
    ``is_production`` es un @property de Settings, así que mutamos la
    variable de la que depende."""
    monkeypatch.setattr(encryption.settings, "field_encryption_key", "")
    monkeypatch.setattr(encryption.settings, "app_env", "production")
    encryption._get_fernet.cache_clear()
    with pytest.raises(EncryptionError, match="producción"):
        encrypt_value("test")


# ── Inputs malformados ─────────────────────────────────────────────────
def test_encrypt_no_acepta_int():
    with pytest.raises(EncryptionError, match="str"):
        encrypt_value(123)  # type: ignore[arg-type]


def test_encrypt_no_acepta_none():
    with pytest.raises(EncryptionError, match="str"):
        encrypt_value(None)  # type: ignore[arg-type]


def test_decrypt_no_acepta_int():
    with pytest.raises(EncryptionError, match="str"):
        decrypt_value(123)  # type: ignore[arg-type]


def test_decrypt_rechaza_token_garbage():
    """Texto que no parece Fernet → EncryptionError (no 500 silencioso)."""
    for bad in [
        "hola mundo",  # plaintext
        "Bearer xyz",  # parece JWT
        "ZmFrZQ==",  # base64 válido pero no Fernet
        "gAAAAA",  # prefijo Fernet pero muy corto
        "x" * 200,  # basura genérica
    ]:
        with pytest.raises(EncryptionError):
            decrypt_value(bad)


# ── Compatibilidad entre entornos (NO esperada) ───────────────────────
def test_datos_cifrados_en_dev_no_se_descifran_con_otra_clave(monkeypatch):
    """Si subimos los datos cifrados en dev a prod (con clave distinta), el
    descifrado falla. Esto es esperado y se documenta — recordatorio de
    que la derivación HKDF es específica del ``SECRET_KEY`` del entorno."""
    # Cifrar con la clave actual (derivada de SECRET_KEY).
    ct = encrypt_value("dato ultra-secreto")

    # Ahora simular prod con una clave Fernet DIFERENTE.
    other_key = Fernet.generate_key().decode()
    monkeypatch.setattr(encryption.settings, "field_encryption_key", other_key)
    encryption._get_fernet.cache_clear()
    with pytest.raises(EncryptionError):
        decrypt_value(ct)


# ── Singleton: misma instancia a través de llamadas ────────────────────
def test_singleton_no_recrea_fernet():
    """``_get_fernet`` usa ``lru_cache`` → misma instancia entre llamadas.
    Confirma que el contrato de singleton se mantiene (importante para
    que Fernet reuse el timestamp clock entre enc/decisadas muy seguidas)."""
    encryption._get_fernet.cache_clear()
    a = encryption._get_fernet()
    b = encryption._get_fernet()
    assert a is b


# ── Smoke: import no rompe el resto de WowHub ──────────────────────────
def test_import_no_contamina_app_main():
    """Importar el helper no debe tener efectos secundarios (ni logging
    ruidoso en import-time, ni registro de middlewares, etc.)."""
    import app.main  # noqa: F401  — sólo verifica que sigue cargando
    import app.core.encryption  # noqa: F401