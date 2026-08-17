"""Marketing Studio — WowHub AI Core™ (Cap. 19.1).

Genera copy de marketing (Instagram, WhatsApp, email, SMS, etc.)
contextual al negocio del tenant, usando el LLM. Tiene un fallback
con templates pre-armados para cuando el LLM no está disponible.

Pipeline:
1. `MarketingStudio.generate(req, tenant_ctx)` recibe un
   `MarketingRequest` validado por Pydantic.
2. Resuelve el contexto del negocio: combina lo que pasó el usuario
   con lo que se puede inferir del tenant (nombre, slug, URL pública).
3. Construye un system prompt especializado en marketing (no el genérico
   de los sub-agentes de chat) + un user prompt con el tema y los parámetros.
4. Llama al LLM con `temperature=0.8` (alta creatividad) y `max_tokens`
   adaptado a la cantidad de variantes pedidas.
5. Parsea la respuesta. El LLM DEBE devolver JSON estructurado con
   `{"variants": [{"content": "...", "hashtags": [...]}]}`.
6. Si el LLM falla (circuit abierto, key faltante, JSON inválido) →
   usa templates de fallback basados en el intent + tone.

Diseño clave (lecciones aprendidas del scrubber anti-{slug}):
- Si el tenant tiene `slug` y `public_url` se calculan en el servicio
  y se pasan YA SUSTITUIDAS al prompt. NUNCA se le pide al LLM que
  invente URLs.
- El response incluye `resolved_context` para que la UI/debug vean
  exactamente qué datos usó.

Tests: `tests/test_marketing_studio.py`.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

from app.config import settings
from app.schemas.ai import (
    MarketingAudience,
    MarketingContext,
    MarketingIntent,
    MarketingRequest,
    MarketingResponse,
    MarketingTone,
    MarketingVariant,
)
from app.services.llm_client import (
    LLMClient,
    LLMFallback,
    LLMMessage,
    get_circuit,
)

logger = logging.getLogger("wowhub.ai.marketing")


# ── System prompt (NO es el genérico de los sub-agentes) ─────────
# Este prompt está especializado en copy de marketing: conciso,
# creativo, y con instrucciones de output JSON estricto para que el
# parseo sea robusto.
_MARKETING_SYSTEM_PROMPT = """Eres un copywriter (redactor de textos de marketing) experto para
pequeños negocios latinoamericanos. Tu trabajo es escribir TEXTO DE
MARKETING (publicidad) para redes sociales, WhatsApp, email y SMS.

REGLAS OBLIGATORIAS:
1. Responde SIEMPRE en español neutro (no uses modismos regionales
   muy fuertes). Si el usuario pide otro idioma, responde en ese.
2. Sé CONCISO: el copy debe caber en el canal destino (ej. SMS ≤160
   chars, story ≤80 chars, email subject ≤60 chars, post IG ≤2200
   pero idealmente ≤500 para engagement).
3. Tono: síguelo ESTRICTAMENTE. Si el usuario pidió "urgente",
   incluye sentido de tiempo limitado. Si pidió "luxury", no uses
   signos de exclamación.
4. NO inventes datos que no estén en el contexto (precios, fechas,
   URLs). Si falta información, usa placeholders neutros como
   "[precio]", "[fecha]" o "[tu web]". NUNCA inventes links.
5. Emojis: úsalos SOLO si el `include_emojis` del usuario es true.
   Si es false, NO pongas emojis en ningún copy.
6. Hashtags: ponlos SOLO si `include_hashtags` es true, y EXACTAMENTE
   la cantidad indicada en `hashtag_count`. Sin el símbolo "#" en
   cada tag (lo agregamos nosotros).
7. Si el contexto trae una `public_url`, puedes incluirla UNA vez
   como link natural en el copy (en la CTA), pero NUNCA con
   placeholders tipo "{slug}" o "/u/..." incompleto.

FORMATO DE SALIDA — DEVUELVE SOLO ESTE JSON (sin markdown, sin ```):
{
  "variants": [
    {
      "content": "texto del copy variante 1",
      "hashtags": ["tag1", "tag2", "tag3"]
    },
    {
      "content": "texto del copy variante 2",
      "hashtags": ["tag1", "tag2", "tag3"]
    }
  ]
}

- Devuelve EXACTAMENTE la cantidad de variantes pedidas.
- Cada `hashtags` debe tener como máximo `hashtag_count` tags, sin "#".
- Si `include_hashtags` es false, devuelve `hashtags: []` en TODAS
  las variantes.
- Si `include_emojis` es false, no uses emojis en `content`.
- NUNCA añadas texto fuera del JSON. NUNCA uses bloques ```json.
"""


# ── Templates de fallback (LLM caído) ───────────────────────────
# Estos se usan cuando el LLM no responde. No son perfectos, pero
# mantienen la UX viva: el usuario siempre recibe ALGO publicable.
_FALLBACK_TEMPLATES: dict[str, dict[str, str]] = {
    MarketingIntent.INSTAGRAM_POST.value: {
        "friendly": "{greeting} {business_name} tiene algo especial para vos: {topic}. {cta}",
        "urgent": "Última oportunidad ✨ {topic} en {business_name}. {cta} (oferta limitada)",
        "playful": "¡Alerta! 🚨 {business_name} trae {topic}. {cta}",
        "professional": "En {business_name} presentamos {topic}. {cta}",
        "luxury": "Una experiencia exclusiva te espera en {business_name}: {topic}. {cta}",
        "casual": "¿Viste lo nuevo de {business_name}? {topic}. {cta}",
        "inspirational": "Hoy puede ser el día: {topic} en {business_name}. {cta}",
    },
    MarketingIntent.WHATSAPP_BROADCAST.value: {
        "friendly": "¡Hola! 👋 {business_name} te trae {topic}. {cta}",
        "urgent": "¡Última hora! {topic} en {business_name}. {cta}",
        "professional": "Estimado cliente: {business_name} le informa sobre {topic}. {cta}",
        "playful": "¡Hey! {business_name} tiene algo rico para vos: {topic}. {cta}",
        "luxury": "Le invitamos a descubrir {topic} en {business_name}. {cta}",
        "casual": "Pasada por {business_name}: {topic}. {cta}",
        "inspirational": "Tu próximo momento favorito empieza acá: {topic} en {business_name}. {cta}",
    },
    MarketingIntent.EMAIL_SUBJECT.value: {
        "friendly": "{topic} — te va a encantar",
        "urgent": "Última oportunidad: {topic}",
        "playful": "Hey, ¿viste esto? {topic}",
        "professional": "Novedades en {business_name}: {topic}",
        "luxury": "Una experiencia para vos: {topic}",
        "casual": "Pasada por {business_name}",
        "inspirational": "Hoy empieza algo nuevo: {topic}",
    },
    MarketingIntent.SMS.value: {
        "friendly": "{business_name}: {topic}. {cta}",
        "urgent": "{business_name} HOY: {topic}. {cta}",
        "playful": "{business_name} trae {topic}. {cta}",
        "professional": "{business_name}: {topic}. {cta}",
        "luxury": "{business_name} presenta {topic}. {cta}",
        "casual": "{business_name}: {topic}",
        "inspirational": "{business_name}: {topic}",
    },
    MarketingIntent.PROMOTION_HEADLINE.value: {
        "friendly": "{topic}",
        "urgent": "¡{topic}! (oferta limitada)",
        "playful": "🎉 {topic}",
        "professional": "{topic} en {business_name}",
        "luxury": "Exclusivo: {topic}",
        "casual": "{topic}",
        "inspirational": "Tu momento: {topic}",
    },
    MarketingIntent.PROMOTION_BODY.value: {
        "friendly": "En {business_name} tenemos {topic}. {promotion_details} {cta}",
        "urgent": "Por tiempo limitado en {business_name}: {topic}. {promotion_details} {cta}",
        "playful": "¡{topic}! {promotion_details} Pasá por {business_name} y aprovechá. {cta}",
        "professional": "Le invitamos a conocer {topic} en {business_name}. {promotion_details} {cta}",
        "luxury": "Disfrute de {topic} en {business_name}. {promotion_details} {cta}",
        "casual": "{topic} en {business_name}. {promotion_details}",
        "inspirational": "Hoy puede ser el día: {topic} en {business_name}. {promotion_details} {cta}",
    },
    MarketingIntent.PRODUCT_DESCRIPTION.value: {
        "friendly": "Conocé {product_name} en {business_name}. {product_features}",
        "urgent": "¡{product_name} te espera! {product_features} {price}",
        "playful": "Mirá lo que tenemos: {product_name}. {product_features}",
        "professional": "{product_name} — {product_features} {price}",
        "luxury": "Presentamos {product_name}: {product_features} {price}",
        "casual": "{product_name}: {product_features}",
        "inspirational": "Descubrí {product_name} en {business_name}. {product_features}",
    },
    MarketingIntent.INSTAGRAM_STORY.value: {
        "friendly": "{topic} ✨ {cta}",
        "urgent": "¡HOY! {topic}",
        "playful": "🎉 {topic}",
        "professional": "{topic}",
        "luxury": "{topic}",
        "casual": "{topic}",
        "inspirational": "{topic}",
    },
    MarketingIntent.INSTAGRAM_REEL.value: {
        "friendly": "[Guion Reel] Hoy te mostramos {topic}. Pasá por {business_name} y viví la experiencia. {cta}",
        "urgent": "[Guion Reel] HOY: {topic}. No te lo pierdas. {cta}",
        "playful": "[Guion Reel] Mirá esto: {topic}. Pasá ya por {business_name}. {cta}",
        "professional": "[Guion Reel] {topic} en {business_name}. {cta}",
        "luxury": "[Guion Reel] Te invitamos a descubrir {topic}. {business_name}. {cta}",
        "casual": "[Guion Reel] {topic}. Pasá por {business_name}.",
        "inspirational": "[Guion Reel] Tu momento es hoy: {topic}. {business_name}. {cta}",
    },
    MarketingIntent.FACEBOOK_POST.value: {
        "friendly": "¡Hola comunidad! En {business_name} tenemos {topic}. {cta}",
        "urgent": "¡Última oportunidad! {topic} en {business_name}. {cta}",
        "playful": "Pasada por {business_name}: {topic}. {cta}",
        "professional": "Les presentamos {topic} en {business_name}. {cta}",
        "luxury": "Les invitamos a conocer {topic} en {business_name}. {cta}",
        "casual": "{topic} en {business_name}. {cta}",
        "inspirational": "Hoy empieza algo nuevo: {topic} en {business_name}. {cta}",
    },
    MarketingIntent.WHATSAPP_STATUS.value: {
        "friendly": "{topic} ✨",
        "urgent": "HOY: {topic}",
        "playful": "🎉 {topic}",
        "professional": "{topic}",
        "luxury": "{topic}",
        "casual": "{topic}",
        "inspirational": "{topic}",
    },
    MarketingIntent.EMAIL_BODY.value: {
        "friendly": "¡Hola! Te escribimos de {business_name} para contarte sobre {topic}. {promotion_details} {cta}",
        "urgent": "Hola — {topic} está por terminar. {promotion_details} {cta}",
        "playful": "¡Hey! Mira lo que trajo {business_name}: {topic}. {promotion_details} {cta}",
        "professional": "Estimado/a: le informamos sobre {topic} en {business_name}. {promotion_details} {cta}",
        "luxury": "Le invitamos a disfrutar {topic} en {business_name}. {promotion_details} {cta}",
        "casual": "Hola — {topic} en {business_name}. {promotion_details} {cta}",
        "inspirational": "Hoy te presentamos {topic} en {business_name}. {promotion_details} {cta}",
    },
    MarketingIntent.GENERAL.value: {
        "friendly": "{topic} en {business_name}. {cta}",
        "urgent": "¡{topic}! Oferta limitada en {business_name}. {cta}",
        "playful": "🎉 {topic} — pasá por {business_name}. {cta}",
        "professional": "{business_name} presenta {topic}. {cta}",
        "luxury": "Exclusivo en {business_name}: {topic}. {cta}",
        "casual": "{topic} — {business_name}. {cta}",
        "inspirational": "Tu próximo favorito: {topic} en {business_name}. {cta}",
    },
}


# ── TenantContext: lo que el caller (endpoint) sabe del tenant ──
@dataclass(frozen=True)
class TenantContext:
    """Contexto del tenant resuelto por el endpoint antes de llamar
    al servicio. Permite que el service NO toque la DB."""
    tenant_id: str
    slug: Optional[str] = None
    name: Optional[str] = None
    public_base_url: Optional[str] = None

    @property
    def has_slug(self) -> bool:
        return bool(self.slug)

    @property
    def public_url(self) -> Optional[str]:
        """Devuelve la URL pública de la landing si hay slug y base_url."""
        if not (self.slug and self.public_base_url):
            return None
        return f"{self.public_base_url.rstrip('/')}/u/{self.slug}"


# ── MarketingStudio ──────────────────────────────────────────────
class MarketingStudio:
    """Generador de copy de marketing con LLM + fallback."""

    def __init__(self, client: Optional[LLMClient] = None) -> None:
        self._client = client  # inyectable para tests
        # Si no se inyecta, se usa el singleton lazy
        if self._client is None:
            self._client = LLMClient()

    # ── API pública ──────────────────────────────────────
    async def generate(
        self,
        req: MarketingRequest,
        tenant_ctx: TenantContext,
    ) -> MarketingResponse:
        """Genera variantes de copy. SIEMPRE devuelve una respuesta
        (con fallback=True si el LLM falló). Nunca lanza excepciones
        hacia el caller — convierte todo a fallback."""
        started = time.monotonic()

        # 1) Resolver contexto: lo del request + lo del tenant
        resolved = self._resolve_context(req, tenant_ctx)

        # 2) Intentar LLM
        try:
            resp = await self._generate_with_llm(req, resolved)
            latency_ms = int((time.monotonic() - started) * 1000)
            resp.latency_ms = latency_ms
            resp.resolved_context = self._ctx_to_dict(resolved)
            return resp
        except Exception as e:  # noqa: BLE001
            # Cualquier error (circuit, JSON, timeout, key faltante) → fallback
            logger.warning(
                "[marketing] LLM falló, usando fallback. intent=%s err=%s",
                req.intent.value, e,
            )
            latency_ms = int((time.monotonic() - started) * 1000)
            resp = self._generate_fallback(req, resolved, reason=str(e))
            resp.latency_ms = latency_ms
            resp.resolved_context = self._ctx_to_dict(resolved)
            return resp

    # ── Resolución de contexto ───────────────────────────
    @staticmethod
    def _resolve_context(
        req: MarketingRequest, tenant_ctx: TenantContext
    ) -> MarketingContext:
        """Combina lo que el usuario pasó en `req.context` con lo que
        sabemos del tenant. El request tiene prioridad; el tenant es
        fallback SOLO para los campos que el usuario NO especificó."""
        ctx = req.context  # copia shallow
        # business_name: si el usuario no lo pasó, usar el del tenant
        if not ctx.business_name and tenant_ctx.name:
            ctx = ctx.model_copy(update={"business_name": tenant_ctx.name})
        # public_url: si el usuario no la pasó y el tenant tiene slug+base
        if not ctx.public_url and tenant_ctx.public_url:
            ctx = ctx.model_copy(update={"public_url": tenant_ctx.public_url})
        return ctx

    @staticmethod
    def _ctx_to_dict(ctx: MarketingContext) -> dict[str, Any]:
        """Serializa el contexto resuelto (excluye None)."""
        return ctx.model_dump(exclude_none=True)

    # ── LLM ──────────────────────────────────────────────
    async def _generate_with_llm(
        self, req: MarketingRequest, ctx: MarketingContext
    ) -> MarketingResponse:
        """Llama al LLM y parsea el JSON estructurado. Si el LLM
        no está disponible → LLMFallback → caller usa fallback."""
        if not settings.llm_enabled:
            raise LLMFallback("LLM no configurado", code="not_configured")
        if not get_circuit().can_pass():
            raise LLMFallback("Circuit breaker abierto", code="circuit_open")

        messages = self._build_messages(req, ctx)
        # Temperature más alta = más creatividad. Cap a 1.2 para
        # que el LLM no se desboque.
        temperature = 0.8
        # max_tokens: ~150 tokens por variante es seguro para copy
        # + 100 de overhead para JSON + hashtags
        max_tokens = min(2000, 200 + 150 * req.variants + 20 * req.hashtag_count)

        response = await self._client.generate(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        variants = self._parse_llm_response(
            response.content,
            expected_count=req.variants,
            include_hashtags=req.include_hashtags,
            hashtag_count=req.hashtag_count,
        )

        # Aplicar max_length si se pidió (recortar variants largos)
        if req.max_length:
            variants = [
                v.model_copy(update={"content": v.content[:req.max_length]})
                for v in variants
            ]
            # Recalcular character_count
            variants = [
                v.model_copy(update={"character_count": len(v.content)})
                for v in variants
            ]

        primary = variants[0] if variants else self._emergency_variant(req, ctx, 1)
        # Hashtags globales: unión deduplicada de las variantes
        seen: set[str] = set()
        global_tags: list[str] = []
        for v in variants:
            for tag in v.hashtags:
                norm = tag.lstrip("#").lower()
                if norm and norm not in seen:
                    seen.add(norm)
                    global_tags.append(norm)

        return MarketingResponse(
            intent=req.intent,
            topic=req.topic,
            tone=req.tone,
            audience=req.audience,
            primary=primary,
            variants=variants,
            hashtags=global_tags,
            fallback=False,
            model=response.finish_reason and settings.llm_model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
        )

    def _build_messages(
        self, req: MarketingRequest, ctx: MarketingContext
    ) -> list[LLMMessage]:
        """Construye system + user prompt."""
        system = _MARKETING_SYSTEM_PROMPT

        # User prompt: instrucciones puntuales con TODOS los parámetros
        user_parts: list[str] = []
        user_parts.append(f"Genera {req.variants} variantes de copy.")
        user_parts.append(f"\nTEMA: {req.topic}")
        user_parts.append(f"\nINTENT (canal/formato): {req.intent.value}")
        user_parts.append(f"\nTONO: {req.tone.value}")
        user_parts.append(f"\nAUDIENCIA: {req.audience.value}")
        if req.keywords:
            user_parts.append(
                f"\nKEYWORDS A INCLUIR: {', '.join(req.keywords)}"
            )
        user_parts.append(
            f"\nINCLUIR EMOJIS: {'sí' if req.include_emojis else 'no, NUNCA uses emojis'}"
        )
        user_parts.append(
            f"\nINCLUIR HASHTAGS: {'sí, ' + str(req.hashtag_count) + ' por variante (sin #)' if req.include_hashtags else 'no, devuelve hashtags vacíos'}"
        )
        if req.max_length:
            user_parts.append(
                f"\nLARGO MÁXIMO del content: {req.max_length} caracteres"
            )

        # Contexto del negocio
        ctx_dict = self._ctx_to_dict(ctx)
        if ctx_dict:
            user_parts.append("\n\nCONTEXTO DEL NEGOCIO:")
            for k, v in ctx_dict.items():
                if isinstance(v, list):
                    user_parts.append(f"\n- {k}: {', '.join(str(x) for x in v)}")
                else:
                    user_parts.append(f"\n- {k}: {v}")

        # Recordatorio crítico
        user_parts.append(
            "\n\nRecordá: respondé SOLO con el JSON, sin markdown, sin ```."
        )

        return [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content="".join(user_parts)),
        ]

    # ── Parsing de la respuesta LLM ─────────────────────
    @staticmethod
    def _parse_llm_response(
        raw: str,
        *,
        expected_count: int,
        include_hashtags: bool,
        hashtag_count: int,
    ) -> list[MarketingVariant]:
        """Extrae el JSON de la respuesta del LLM. Robusto a:
        - JSON envuelto en ```json ... ```
        - Texto antes/después del JSON
        - Listas con más o menos items de los pedidos
        """
        if not raw:
            raise ValueError("LLM devolvió respuesta vacía")

        # Intentar encontrar el primer {...} de la respuesta
        text = raw.strip()
        # Quitar fences si los hay
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        # Buscar el primer { y el último }
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            raise ValueError(f"No se encontró JSON en la respuesta: {raw[:200]!r}")
        json_str = text[first:last + 1]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON inválido del LLM: {e}. raw={raw[:300]!r}") from e

        raw_variants = data.get("variants")
        if not isinstance(raw_variants, list) or not raw_variants:
            raise ValueError(f"'variants' vacío o inválido: {raw_variants!r}")

        variants: list[MarketingVariant] = []
        for i, item in enumerate(raw_variants[:expected_count], start=1):
            if not isinstance(item, dict):
                continue
            content = (item.get("content") or "").strip()
            if not content:
                continue
            tags_raw = item.get("hashtags") or []
            if not isinstance(tags_raw, list):
                tags_raw = []
            # Limpiar hashtags: sin "#", lowercase, sin espacios
            tags_clean: list[str] = []
            for t in tags_raw:
                if not isinstance(t, str):
                    continue
                norm = t.lstrip("#").strip().lower().replace(" ", "")
                if norm and norm not in tags_clean:
                    tags_clean.append(norm)
            # Limitar a hashtag_count
            if include_hashtags and hashtag_count > 0:
                tags_clean = tags_clean[:hashtag_count]
            else:
                tags_clean = []

            variants.append(
                MarketingVariant(
                    index=i,
                    content=content,
                    hashtags=tags_clean,
                    character_count=len(content),
                )
            )

        if not variants:
            raise ValueError("Ninguna variante válida en la respuesta LLM")
        return variants

    # ── Fallback ─────────────────────────────────────────
    def _generate_fallback(
        self,
        req: MarketingRequest,
        ctx: MarketingContext,
        reason: str = "",
    ) -> MarketingResponse:
        """Genera variantes con templates pre-armados cuando el LLM
        no está disponible. El copy es menos personalizado pero
        mantiene la UX viva."""
        # Plantilla por intent+tone
        templates = _FALLBACK_TEMPLATES.get(
            req.intent.value, _FALLBACK_TEMPLATES[MarketingIntent.GENERAL.value]
        )
        template = templates.get(
            req.tone.value, templates[MarketingTone.FRIENDLY.value]
        )

        # Sustituir placeholders con lo que tengamos
        product_features_str = (
            ", ".join(ctx.product_features)
            if ctx.product_features
            else "Hecho con los mejores ingredientes"
        )
        # Defaults amistosos para los placeholders
        subs: dict[str, str] = {
            "business_name": ctx.business_name or "tu negocio",
            "product_name": ctx.product_name or "nuestro producto",
            "product_features": product_features_str,
            "price": ctx.price or "",
            "promotion_details": ctx.promotion_details or "",
            "topic": req.topic,
            "cta": ctx.cta or "Más info por WhatsApp",
            "greeting": "¡Hola!",
        }
        # Limpiar espacios dobles y trim
        def _sub(s: str) -> str:
            try:
                return s.format(**subs).strip()
            except KeyError:
                return s

        # Generar N variantes: rotamos entre tonos disponibles si hay menos
        # tonos que variantes pedidas
        available_tones = list(templates.keys())
        variants: list[MarketingVariant] = []
        for i in range(1, req.variants + 1):
            tone_key = (
                req.tone.value
                if i == 1
                else available_tones[(i - 1) % len(available_tones)]
            )
            tmpl = templates.get(tone_key, template)
            content = _sub(tmpl)
            # Quitar dobles espacios
            content = re.sub(r"\s{2,}", " ", content).strip()
            if not content.endswith((".", "!", "?", ">", "/", "»")):
                content += "."
            # Si pidió URL pública, agregarla como cierre
            if ctx.public_url and "{url}" not in content:
                content = f"{content}\n{ctx.public_url}"

            # Hashtags: solo si pidió. Tags genéricos según intent
            tags: list[str] = []
            if req.include_hashtags and req.hashtag_count > 0:
                tags = self._fallback_hashtags(req, ctx)

            variants.append(
                MarketingVariant(
                    index=i,
                    content=content,
                    hashtags=tags[: req.hashtag_count] if req.include_hashtags else [],
                    character_count=len(content),
                )
            )

        # Hashtags globales
        seen: set[str] = set()
        global_tags: list[str] = []
        for v in variants:
            for t in v.hashtags:
                if t not in seen:
                    seen.add(t)
                    global_tags.append(t)

        return MarketingResponse(
            intent=req.intent,
            topic=req.topic,
            tone=req.tone,
            audience=req.audience,
            primary=variants[0],
            variants=variants,
            hashtags=global_tags,
            fallback=True,
            model=None,
            tokens_in=None,
            tokens_out=None,
        )

    @staticmethod
    def _fallback_hashtags(
        req: MarketingRequest, ctx: MarketingContext
    ) -> list[str]:
        """Hashtags genéricos para el fallback. Se eligen según el intent
        y el nombre del negocio (slugificado)."""
        intent_tags: dict[str, list[str]] = {
            "instagram_post": ["#WowHub", "#HechoConCorazón"],
            "instagram_story": ["#WowHub"],
            "instagram_reel": ["#Reel", "#WowHub"],
            "facebook_post": ["#Comunidad", "#WowHub"],
            "whatsapp_broadcast": [],
            "whatsapp_status": [],
            "email_subject": [],
            "email_body": [],
            "sms": [],
            "product_description": ["#ProductoLocal", "#WowHub"],
            "promotion_headline": ["#Promo", "#Oferta"],
            "promotion_body": ["#Promo", "#Oferta", "#WowHub"],
            "general": ["#WowHub"],
        }
        tags = list(intent_tags.get(req.intent.value, ["#WowHub"]))
        # Tag del negocio (slugificado)
        if ctx.business_name:
            slug = re.sub(r"[^a-z0-9]+", "", ctx.business_name.lower())[:30]
            if slug:
                tag = "#" + slug.capitalize()
                if tag not in tags:
                    tags.append(tag)
        # Tag de ciudad
        if ctx.city:
            city_slug = re.sub(r"[^a-z0-9]+", "", ctx.city.lower())[:20]
            if city_slug:
                tag = "#" + city_slug.capitalize()
                if tag not in tags:
                    tags.append(tag)
        return tags

    @staticmethod
    def _emergency_variant(
        req: MarketingRequest, ctx: MarketingContext, index: int
    ) -> MarketingVariant:
        """Último recurso: una variante mínima para no devolver lista vacía."""
        content = f"{req.topic} en {ctx.business_name or 'tu negocio'}."
        return MarketingVariant(
            index=index,
            content=content,
            hashtags=[],
            character_count=len(content),
        )
