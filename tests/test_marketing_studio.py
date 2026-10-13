"""Tests del Marketing Studio (Cap. 19.1 del WowHub AI Core).

Cubre:
1. Schemas Pydantic: validación, defaults, límites.
2. Servicio MarketingStudio: contexto, system prompt, parsing.
3. Fallback: cuando el LLM no está disponible o falla.
4. Endpoint POST /api/v1/ai/marketing/generate: integración.

Las pruebas del LLM mockean `LLMClient.generate` para no depender
del proveedor real. El comportamiento end-to-end real se prueba en
staging con la API key configurada.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.schemas.ai import (
    MarketingAudience,
    MarketingContext,
    MarketingIntent,
    MarketingRequest,
    MarketingResponse,
    MarketingTone,
    MarketingVariant,
)
from app.services import llm_client as llm_client_module
from app.services.marketing_studio import (
    MarketingStudio,
    TenantContext,
    _MARKETING_SYSTEM_PROMPT,
)
from app.services.llm_client import LLMResponse


# ── 1) Schemas ─────────────────────────────────────────
class TestSchemas:
    def test_request_minimal_valid(self):
        """El request mínimo (solo topic) debe ser válido."""
        req = MarketingRequest(topic="Promoción 2x1 en café")
        assert req.intent == MarketingIntent.GENERAL
        assert req.tone == MarketingTone.FRIENDLY
        assert req.audience == MarketingAudience.ALL
        assert req.variants == 3
        assert req.include_emojis is True
        assert req.include_hashtags is False
        assert req.hashtag_count == 5
        assert req.language == "es"

    def test_request_full_valid(self):
        """El request completo con todos los campos debe ser válido."""
        req = MarketingRequest(
            intent=MarketingIntent.INSTAGRAM_POST,
            topic="Black Friday 50% off",
            tone=MarketingTone.URGENT,
            audience=MarketingAudience.EXISTING,
            keywords=["black friday", "descuento", "café"],
            include_emojis=True,
            include_hashtags=True,
            hashtag_count=7,
            language="es",
            max_length=400,
            variants=4,
            context=MarketingContext(
                business_name="Café Luna",
                business_type="Cafetería",
                city="Bogotá",
                product_name="Café de origen",
                product_features=["100% arábigo", "Tostado artesanal"],
                price="$15.000",
                promotion_details="50% off hasta el 30/11",
                cta="Pedí por WhatsApp",
                public_url="https://wowhub.app/u/cafeluna",
            ),
        )
        assert req.intent == MarketingIntent.INSTAGRAM_POST
        assert req.context.business_name == "Café Luna"
        assert len(req.context.product_features) == 2

    def test_request_rejects_empty_topic(self):
        with pytest.raises(ValueError):
            MarketingRequest(topic="")

    def test_request_rejects_short_topic(self):
        """Mínimo 3 chars en topic."""
        with pytest.raises(ValueError):
            MarketingRequest(topic="ab")

    def test_request_rejects_too_many_variants(self):
        """Max 5 variants."""
        with pytest.raises(ValueError):
            MarketingRequest(topic="hola mundo", variants=10)

    def test_request_rejects_too_many_hashtags(self):
        """Max 20 hashtag_count."""
        with pytest.raises(ValueError):
            MarketingRequest(
                topic="hola mundo",
                include_hashtags=True,
                hashtag_count=50,
            )

    def test_request_rejects_too_many_keywords(self):
        """Max 12 keywords."""
        with pytest.raises(ValueError):
            MarketingRequest(
                topic="hola",
                keywords=["k"] * 20,
            )

    def test_context_optional_fields(self):
        """Todos los campos del context son opcionales."""
        ctx = MarketingContext()
        assert ctx.business_name is None
        assert ctx.business_type is None
        assert ctx.product_features is None

    def test_variant_required_fields(self):
        v = MarketingVariant(index=1, content="Hola mundo", character_count=10)
        assert v.index == 1
        assert v.content == "Hola mundo"
        assert v.character_count == 10
        assert v.hashtags == []  # default


# ── 2) Servicio: resolución de contexto ─────────────────
class TestContextResolution:
    def test_user_context_wins_over_tenant(self):
        """Si el usuario pasa business_name, el del tenant se ignora."""
        req = MarketingRequest(
            topic="hola",
            context=MarketingContext(business_name="Mi Café Custom"),
        )
        ctx = TenantContext(
            tenant_id="t1", slug="cafeluna", name="Café Luna",
            public_base_url="https://wowhub.app",
        )
        resolved = MarketingStudio._resolve_context(req, ctx)
        assert resolved.business_name == "Mi Café Custom"

    def test_tenant_fills_user_gaps(self):
        """Si el usuario NO pasa business_name, se usa el del tenant."""
        req = MarketingRequest(topic="hola")
        ctx = TenantContext(
            tenant_id="t1", slug="cafeluna", name="Café Luna",
            public_base_url="https://wowhub.app",
        )
        resolved = MarketingStudio._resolve_context(req, ctx)
        assert resolved.business_name == "Café Luna"

    def test_tenant_public_url_filled_if_missing(self):
        """Si el usuario no pasa public_url, se calcula del tenant."""
        req = MarketingRequest(topic="hola")
        ctx = TenantContext(
            tenant_id="t1", slug="cafeluna", name="Café Luna",
            public_base_url="https://wowhub.app",
        )
        resolved = MarketingStudio._resolve_context(req, ctx)
        assert resolved.public_url == "https://wowhub.app/u/cafeluna"

    def test_user_public_url_wins(self):
        """Si el usuario pasa su propia public_url, se respeta."""
        req = MarketingRequest(
            topic="hola",
            context=MarketingContext(public_url="https://otrodominio.com/x"),
        )
        ctx = TenantContext(
            tenant_id="t1", slug="cafeluna", name="Café Luna",
            public_base_url="https://wowhub.app",
        )
        resolved = MarketingStudio._resolve_context(req, ctx)
        assert resolved.public_url == "https://otrodominio.com/x"

    def test_no_slug_no_public_url(self):
        """Si el tenant no tiene slug, public_url queda None."""
        req = MarketingRequest(topic="hola")
        ctx = TenantContext(
            tenant_id="t1", slug=None, name="Café Sin Slug",
            public_base_url="https://wowhub.app",
        )
        resolved = MarketingStudio._resolve_context(req, ctx)
        assert resolved.public_url is None

    def test_tenant_context_public_url_property(self):
        """TenantContext.public_url devuelve la URL completa con slug."""
        ctx = TenantContext(
            tenant_id="t1", slug="mi-cafe", name="Mi Café",
            public_base_url="https://wowhub.app/",
        )
        # Trailing slash debe ser removido
        assert ctx.public_url == "https://wowhub.app/u/mi-cafe"

    def test_tenant_context_has_slug(self):
        assert TenantContext(tenant_id="t", slug="x", name="X",
                             public_base_url=None).has_slug is True
        assert TenantContext(tenant_id="t", slug=None, name="X",
                             public_base_url=None).has_slug is False


# ── 3) Servicio: system prompt ─────────────────────────
class TestSystemPrompt:
    def test_system_prompt_includes_no_inventar(self):
        """El system prompt debe prohibir inventar URLs/precios."""
        assert "NO inventes" in _MARKETING_SYSTEM_PROMPT

    def test_system_prompt_includes_json_format(self):
        """El system prompt debe exigir JSON estructurado."""
        assert '"variants"' in _MARKETING_SYSTEM_PROMPT
        assert '"content"' in _MARKETING_SYSTEM_PROMPT
        assert '"hashtags"' in _MARKETING_SYSTEM_PROMPT

    def test_system_prompt_includes_emoji_rule(self):
        """El system prompt debe tener regla de emojis condicional."""
        assert "emojis" in _MARKETING_SYSTEM_PROMPT.lower()

    def test_system_prompt_explicitly_prohibits_markdown_fences(self):
        """El system prompt debe DECIR que no use ```markdown``` (lo
        prohíbe explícitamente para que el parseo sea robusto)."""
        # Verifica que el prompt tiene la regla de no usar fences
        assert "```" in _MARKETING_SYSTEM_PROMPT
        # Y que la regla aparece en contexto negativo (no / NUNCA)
        low = _MARKETING_SYSTEM_PROMPT.lower()
        # Debe haber una mención de "sin ```" o "nunca uses bloques"
        assert "sin ```" in low or "nunca" in low and "```" in low


# ── 4) Servicio: parsing de respuesta LLM ───────────────
class TestLLMResponseParsing:
    def test_parse_clean_json(self):
        raw = json.dumps({
            "variants": [
                {"content": "Hola mundo 1", "hashtags": ["cafe", "promo"]},
                {"content": "Hola mundo 2", "hashtags": ["cafe"]},
            ]
        })
        out = MarketingStudio._parse_llm_response(
            raw, expected_count=2, include_hashtags=True, hashtag_count=5
        )
        assert len(out) == 2
        assert out[0].content == "Hola mundo 1"
        assert out[0].hashtags == ["cafe", "promo"]
        assert out[0].character_count == 12

    def test_parse_strips_markdown_fences(self):
        raw = "```json\n" + json.dumps({
            "variants": [{"content": "Hi", "hashtags": []}]
        }) + "\n```"
        out = MarketingStudio._parse_llm_response(
            raw, expected_count=1, include_hashtags=False, hashtag_count=5
        )
        assert len(out) == 1
        assert out[0].content == "Hi"

    def test_parse_with_surrounding_text(self):
        """El LLM a veces pone texto antes/después del JSON."""
        raw = (
            "Aquí está tu copy:\n"
            + json.dumps({"variants": [{"content": "Copy 1", "hashtags": []}]})
            + "\n¡Espero que te sirva!"
        )
        out = MarketingStudio._parse_llm_response(
            raw, expected_count=1, include_hashtags=False, hashtag_count=5
        )
        assert len(out) == 1
        assert out[0].content == "Copy 1"

    def test_parse_caps_variants_to_expected(self):
        """Si el LLM devuelve más variantes de las pedidas, cap."""
        raw = json.dumps({
            "variants": [{"content": f"V{i}", "hashtags": []} for i in range(5)]
        })
        out = MarketingStudio._parse_llm_response(
            raw, expected_count=2, include_hashtags=False, hashtag_count=5
        )
        assert len(out) == 2

    def test_parse_cleans_hashtags(self):
        """Hashtags sin #, lowercase, sin espacios, sin duplicados."""
        raw = json.dumps({
            "variants": [{
                "content": "x",
                "hashtags": ["#Cafe", "CAFE", "cafe", "promo", "promo"]
            }]
        })
        out = MarketingStudio._parse_llm_response(
            raw, expected_count=1, include_hashtags=True, hashtag_count=5
        )
        # Sin #, lowercase, sin duplicados → "cafe" y "promo" sobreviven
        assert out[0].hashtags == ["cafe", "promo"]

    def test_parse_caps_hashtag_count(self):
        raw = json.dumps({
            "variants": [{
                "content": "x",
                "hashtags": ["t1", "t2", "t3", "t4", "t5"]
            }]
        })
        out = MarketingStudio._parse_llm_response(
            raw, expected_count=1, include_hashtags=True, hashtag_count=2
        )
        assert len(out[0].hashtags) == 2

    def test_parse_empty_hashtags_when_disabled(self):
        """Si include_hashtags=False, siempre se devuelven vacíos."""
        raw = json.dumps({
            "variants": [{
                "content": "x",
                "hashtags": ["t1", "t2"]
            }]
        })
        out = MarketingStudio._parse_llm_response(
            raw, expected_count=1, include_hashtags=False, hashtag_count=5
        )
        assert out[0].hashtags == []

    def test_parse_raises_on_empty(self):
        with pytest.raises(ValueError):
            MarketingStudio._parse_llm_response(
                "", expected_count=1, include_hashtags=False, hashtag_count=5
            )

    def test_parse_raises_on_no_json(self):
        with pytest.raises(ValueError):
            MarketingStudio._parse_llm_response(
                "no json here", expected_count=1,
                include_hashtags=False, hashtag_count=5
            )

    def test_parse_raises_on_bad_json(self):
        with pytest.raises(ValueError):
            MarketingStudio._parse_llm_response(
                "{variants: [malformed]",
                expected_count=1, include_hashtags=False, hashtag_count=5
            )

    def test_parse_raises_on_no_variants(self):
        raw = json.dumps({"variants": []})
        with pytest.raises(ValueError):
            MarketingStudio._parse_llm_response(
                raw, expected_count=1, include_hashtags=False, hashtag_count=5
            )

    def test_parse_skips_empty_content(self):
        """Variantes con content vacío se descartan."""
        raw = json.dumps({
            "variants": [
                {"content": "", "hashtags": []},
                {"content": "   ", "hashtags": []},
                {"content": "valid", "hashtags": []},
            ]
        })
        out = MarketingStudio._parse_llm_response(
            raw, expected_count=3, include_hashtags=False, hashtag_count=5
        )
        assert len(out) == 1
        assert out[0].content == "valid"


# ── 5) Servicio: generate() con LLM mockeado ───────────
class TestGenerateWithLLM:
    @pytest.mark.asyncio
    async def test_returns_llm_result_when_ok(self, monkeypatch):
        """Cuando el LLM responde bien, devuelve sus variantes con
        fallback=False y los tokens."""
        # Mockear el LLM client
        async def fake_generate(messages, **kwargs):
            return LLMResponse(
                content=json.dumps({
                    "variants": [
                        {"content": "Copy 1 de prueba", "hashtags": ["cafe", "promo"]},
                        {"content": "Copy 2 de prueba", "hashtags": ["cafe", "promo"]},
                        {"content": "Copy 3 de prueba", "hashtags": ["cafe"]},
                    ]
                }),
                tokens_in=120, tokens_out=80, finish_reason="stop",
            )
        mock_client = MagicMock()
        mock_client.generate = AsyncMock(side_effect=fake_generate)

        studio = MarketingStudio(client=mock_client)
        req = MarketingRequest(
            intent=MarketingIntent.INSTAGRAM_POST,
            topic="Promo 2x1",
            tone=MarketingTone.FRIENDLY,
            audience=MarketingAudience.ALL,
            include_hashtags=True,
            hashtag_count=3,
            variants=3,
        )
        ctx = TenantContext(
            tenant_id="t1", slug="cafeluna", name="Café Luna",
            public_base_url="https://wowhub.app",
        )
        resp = await studio.generate(req, ctx)

        assert resp.fallback is False
        assert len(resp.variants) == 3
        assert resp.primary.content == "Copy 1 de prueba"
        assert resp.tokens_in == 120
        assert resp.tokens_out == 80
        assert resp.latency_ms >= 0
        # Hashtags globales deduplicados
        assert set(resp.hashtags) == {"cafe", "promo"}
        # Contexto resuelto
        assert resp.resolved_context is not None
        assert resp.resolved_context.get("business_name") == "Café Luna"
        assert resp.resolved_context.get("public_url") == "https://wowhub.app/u/cafeluna"

    @pytest.mark.asyncio
    async def test_fallback_when_llm_fails(self, monkeypatch):
        """Cuando el LLM lanza excepción, se devuelve fallback=True."""
        # Forzar LLM no configurado
        from app.config import settings
        monkeypatch.setattr(settings, "llm_api_key", "")
        # Resetear circuit (puede que tests anteriores lo hayan abierto)
        llm_client_module._circuit = llm_client_module.CircuitBreaker(
            fail_threshold=5, reset_seconds=60
        )

        studio = MarketingStudio()
        req = MarketingRequest(
            intent=MarketingIntent.WHATSAPP_BROADCAST,
            topic="Promo 2x1",
            tone=MarketingTone.URGENT,
            variants=2,
            include_hashtags=True,
            hashtag_count=2,
        )
        ctx = TenantContext(
            tenant_id="t1", slug="cafeluna", name="Café Luna",
            public_base_url="https://wowhub.app",
        )
        resp = await studio.generate(req, ctx)

        assert resp.fallback is True
        assert len(resp.variants) == 2
        # El copy debe mencionar el topic y el business_name
        assert "Café Luna" in resp.primary.content
        assert "Promo 2x1" in resp.primary.content
        # model vacío en fallback
        assert resp.model is None
        assert resp.tokens_in is None

    @pytest.mark.asyncio
    async def test_fallback_when_circuit_open(self):
        """Si el circuit está abierto, fallback inmediato."""
        llm_client_module._circuit = llm_client_module.CircuitBreaker(
            fail_threshold=1, reset_seconds=60
        )
        llm_client_module._circuit.force_open()

        studio = MarketingStudio()
        req = MarketingRequest(topic="Promo test")
        ctx = TenantContext(tenant_id="t1", name="X", public_base_url=None)
        resp = await studio.generate(req, ctx)

        assert resp.fallback is True
        # Limpiar el circuit para no afectar otros tests
        llm_client_module._circuit.force_close()

    @pytest.mark.asyncio
    async def test_fallback_uses_default_business_name(self):
        """Si no hay tenant name ni en el request, usa 'tu negocio'."""
        llm_client_module._circuit = llm_client_module.CircuitBreaker(
            fail_threshold=1, reset_seconds=60
        )
        llm_client_module._circuit.force_open()

        studio = MarketingStudio()
        req = MarketingRequest(topic="Promo test")
        ctx = TenantContext(tenant_id="t1")  # sin name
        resp = await studio.generate(req, ctx)

        assert resp.fallback is True
        assert "tu negocio" in resp.primary.content
        llm_client_module._circuit.force_close()

    @pytest.mark.asyncio
    async def test_fallback_appends_public_url(self):
        """Si hay public_url, se agrega al final del copy de fallback."""
        llm_client_module._circuit = llm_client_module.CircuitBreaker(
            fail_threshold=1, reset_seconds=60
        )
        llm_client_module._circuit.force_open()

        studio = MarketingStudio()
        req = MarketingRequest(topic="Promo test")
        ctx = TenantContext(
            tenant_id="t1", slug="cafeluna", name="Café Luna",
            public_base_url="https://wowhub.app",
        )
        resp = await studio.generate(req, ctx)

        assert resp.fallback is True
        # La URL debe estar al final del copy
        assert "https://wowhub.app/u/cafeluna" in resp.primary.content
        llm_client_module._circuit.force_close()

    @pytest.mark.asyncio
    async def test_fallback_generates_requested_variants(self):
        """El fallback genera EXACTAMENTE N variantes como pidió el request."""
        llm_client_module._circuit = llm_client_module.CircuitBreaker(
            fail_threshold=1, reset_seconds=60
        )
        llm_client_module._circuit.force_open()

        studio = MarketingStudio()
        for n in (1, 3, 5):
            req = MarketingRequest(topic="hola mundo test", variants=n)
            ctx = TenantContext(tenant_id="t1", name="X")
            resp = await studio.generate(req, ctx)
            assert len(resp.variants) == n, f"Pedí {n} variants, devolvió {len(resp.variants)}"
        llm_client_module._circuit.force_close()


# ── 6) Servicio: build_messages ────────────────────────
class TestBuildMessages:
    def test_includes_all_params(self):
        """El user prompt debe mencionar intent, tone, audience."""
        req = MarketingRequest(
            intent=MarketingIntent.EMAIL_SUBJECT,
            topic="Black Friday",
            tone=MarketingTone.URGENT,
            audience=MarketingAudience.EXISTING,
            keywords=["black", "friday"],
            include_emojis=False,
            include_hashtags=True,
            hashtag_count=3,
        )
        ctx = MarketingContext(business_name="Mi Negocio")
        msgs = MarketingStudio()._build_messages(req, ctx)
        assert len(msgs) == 2
        user_content = msgs[1].content
        assert "email_subject" in user_content
        assert "urgent" in user_content
        assert "existing" in user_content
        assert "black" in user_content
        assert "friday" in user_content
        assert "NUNCA uses emojis" in user_content
        assert "3 por variante" in user_content
        assert "Mi Negocio" in user_content

    def test_context_dict_included(self):
        req = MarketingRequest(
            topic="hola mundo test",
            context=MarketingContext(
                business_name="X",
                product_name="Y",
                price="$10",
                city="Bogotá",
            ),
        )
        msgs = MarketingStudio()._build_messages(req, req.context)
        user = msgs[1].content
        assert "business_name: X" in user
        assert "product_name: Y" in user
        assert "price: $10" in user
        assert "city: Bogotá" in user

    def test_no_context_omitted_gracefully(self):
        """Si el contexto está vacío, no rompe el prompt."""
        req = MarketingRequest(topic="hola mundo test")
        msgs = MarketingStudio()._build_messages(req, MarketingContext())
        # No debe haber línea de CONTEXTO DEL NEGOCIO si todo está vacío
        user = msgs[1].content
        # Solo verifica que no rompe
        assert "TEMA: hola mundo test" in user


# ── 7) Test de integración: endpoint E2E ───────────────
# Usa el cliente de FastAPI con un usuario autenticado.
@pytest.fixture
def auth_user_and_tenant(db_session):
    """Crea un user + tenant + membership para tests E2E."""
    from app.models.user import User, UserRole
    from app.models.tenant import Tenant, TenantMembership
    import uuid as _uuid

    user = User(
        id=_uuid.uuid4(),
        email=f"test-{_uuid.uuid4().hex[:8]}@example.com",
        password_hash="fake",
        full_name="Test User",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    tenant = Tenant(
        id=_uuid.uuid4(),
        slug=f"test-{_uuid.uuid4().hex[:8]}",
        legal_name="Café Test SpA",
        display_name="Café Test",
        industry="other",
    )
    db_session.add(tenant)
    db_session.flush()

    membership = TenantMembership(
        id=_uuid.uuid4(),
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        role=UserRole.OWNER,
        is_owner=True,
        is_active=True,
    )
    db_session.add(membership)
    db_session.commit()

    return user, tenant


@pytest.fixture
def auth_headers(client, auth_user_and_tenant):
    """Genera headers con Authorization Bearer y X-Tenant-Id."""
    from app.security import create_access_token
    user, tenant = auth_user_and_tenant
    token = create_access_token(
        subject=str(user.id),
        tenant_id=str(tenant.id),
        role="owner",
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(tenant.id),
        "Content-Type": "application/json",
    }


class TestEndpointE2E:
    @pytest.mark.asyncio
    async def test_endpoint_returns_fallback_when_no_llm(
        self, client, auth_headers, monkeypatch
    ):
        """E2E: el endpoint responde con fallback=True cuando el LLM
        no está configurado."""
        from app.config import settings
        monkeypatch.setattr(settings, "llm_api_key", "")
        # Resetear circuit
        llm_client_module._circuit = llm_client_module.CircuitBreaker(
            fail_threshold=5, reset_seconds=60
        )

        payload = {
            "intent": "instagram_post",
            "topic": "Promo 2x1 en café",
            "tone": "friendly",
            "audience": "all",
            "variants": 2,
            "include_hashtags": True,
            "hashtag_count": 3,
            "context": {
                "business_name": "Café Luna",
                "business_type": "Cafetería",
            },
        }
        r = client.post(
            "/api/v1/ai/marketing/generate",
            json=payload,
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["fallback"] is True
        assert len(data["variants"]) == 2
        # El primary es variants[0]
        assert data["primary"]["index"] == 1
        # El contexto resuelto incluye el del usuario
        assert data["resolved_context"]["business_name"] == "Café Luna"

    @pytest.mark.asyncio
    async def test_endpoint_resolves_tenant_slug_in_context(
        self, client, auth_headers, monkeypatch
    ):
        """E2E: si el usuario no pasa business_name ni public_url,
        se completan desde el tenant."""
        from app.config import settings
        monkeypatch.setattr(settings, "llm_api_key", "")
        llm_client_module._circuit = llm_client_module.CircuitBreaker(
            fail_threshold=5, reset_seconds=60
        )

        # Usamos INSTAGRAM_POST (urgent) que sí incluye business_name en
        # el template de fallback
        payload = {
            "intent": "instagram_post",
            "topic": "Oferta del día",
            "tone": "urgent",
            "variants": 1,
        }
        r = client.post(
            "/api/v1/ai/marketing/generate",
            json=payload,
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # El business_name del tenant "Café Test" debe aparecer
        assert "Café Test" in data["primary"]["content"]
        # Y la URL pública (con el slug del tenant) también
        assert data["resolved_context"]["public_url"].startswith("https://")
        assert "/u/" in data["resolved_context"]["public_url"]

    @pytest.mark.asyncio
    async def test_endpoint_returns_401_without_auth(self, client):
        r = client.post(
            "/api/v1/ai/marketing/generate",
            json={"intent": "general", "topic": "hola mundo"},
        )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_endpoint_rejects_short_topic(self, client, auth_headers):
        r = client.post(
            "/api/v1/ai/marketing/generate",
            json={"intent": "general", "topic": "ab"},
            headers=auth_headers,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_endpoint_rejects_invalid_intent(self, client, auth_headers):
        r = client.post(
            "/api/v1/ai/marketing/generate",
            json={"intent": "no_existe", "topic": "hola mundo"},
            headers=auth_headers,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_endpoint_with_llm_mock(
        self, client, auth_headers, monkeypatch
    ):
        """E2E: con el LLM mockeado, devuelve fallback=False."""
        # Mockear el LLM client a nivel global
        async def fake_generate(messages, **kwargs):
            return LLMResponse(
                content=json.dumps({
                    "variants": [
                        {"content": "Copy LLM 1", "hashtags": ["a", "b"]},
                        {"content": "Copy LLM 2", "hashtags": ["a"]},
                    ]
                }),
                tokens_in=50, tokens_out=30, finish_reason="stop",
            )

        # El LLMClient se instancia DENTRO del endpoint, así que
        # parchamos el método generate de la clase para que TODAS
        # las instancias devuelvan nuestro mock.
        original_generate = llm_client_module.LLMClient.generate

        async def patched_generate(self, messages, **kwargs):
            return await fake_generate(messages, **kwargs)

        monkeypatch.setattr(
            llm_client_module.LLMClient, "generate", patched_generate
        )

        payload = {
            "intent": "instagram_post",
            "topic": "Promo test",
            "tone": "friendly",
            "variants": 2,
        }
        r = client.post(
            "/api/v1/ai/marketing/generate",
            json=payload,
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["fallback"] is False
        assert data["primary"]["content"] == "Copy LLM 1"
        assert data["tokens_in"] == 50
        assert data["tokens_out"] == 30
