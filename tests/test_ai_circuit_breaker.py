"""Tests del Circuit Breaker del LLM client."""
import time
import pytest

from app.services.llm_client import (
    CircuitBreaker, LLMClient, LLMError, LLMFallback, LLMMessage,
)


# ── Circuit Breaker unit ──────────────────────────────
class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(fail_threshold=3, reset_seconds=10)
        assert cb.state == "closed"
        assert cb.can_pass() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(fail_threshold=3, reset_seconds=10)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"
        assert cb.can_pass() is False

    def test_half_open_after_reset(self):
        cb = CircuitBreaker(fail_threshold=2, reset_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        assert cb.can_pass() is False
        time.sleep(0.15)
        # Al consultar de nuevo, debe transicionar a half_open
        assert cb.can_pass() is True
        assert cb.state == "half_open"

    def test_success_closes(self):
        cb = CircuitBreaker(fail_threshold=2, reset_seconds=0.05)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.07)
        cb.can_pass()  # transiciona a half_open
        cb.record_success()
        assert cb.state == "closed"
        assert cb.consecutive_failures == 0

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(fail_threshold=2, reset_seconds=0.05)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.07)
        cb.can_pass()  # half_open
        cb.record_failure()
        assert cb.state == "open"

    def test_force_open_and_close(self):
        cb = CircuitBreaker(fail_threshold=10, reset_seconds=10)
        cb.force_open()
        assert cb.state == "open"
        assert cb.can_pass() is False
        cb.force_close()
        assert cb.state == "closed"
        assert cb.can_pass() is True


# ── LLMClient integration (con mock httpx) ────────────
class TestLLMClientFallback:
    @pytest.mark.asyncio
    async def test_not_configured_raises_fallback(self, monkeypatch):
        # Forzar LLM deshabilitado
        from app.config import settings
        monkeypatch.setattr(settings, "llm_api_key", "")
        # Re-crear singleton del circuit
        from app.services import llm_client
        llm_client._circuit = CircuitBreaker(fail_threshold=5, reset_seconds=60)
        client = LLMClient()
        with pytest.raises(LLMFallback) as exc:
            await client.generate([LLMMessage(role="user", content="hola")])
        assert exc.value.code in ("not_configured", "circuit_open")

    @pytest.mark.asyncio
    async def test_circuit_open_raises_fallback(self):
        from app.services import llm_client
        llm_client._circuit = CircuitBreaker(fail_threshold=5, reset_seconds=60)
        llm_client._circuit.force_open()
        client = LLMClient()
        # Asegurar que parece configurado
        from app.config import settings
        orig_key = settings.llm_api_key
        settings.llm_api_key = "test-key"
        try:
            with pytest.raises(LLMFallback) as exc:
                await client.generate([LLMMessage(role="user", content="hola")])
            assert exc.value.code == "circuit_open"
        finally:
            settings.llm_api_key = orig_key
            llm_client._circuit.force_close()
