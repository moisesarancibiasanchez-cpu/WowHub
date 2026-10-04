"""Instrumentación OTel + Sentry + Prometheus para WowHub.

HU_07: Observabilidad — trazas, errores y métricas para producción.

FIX 2026-09-27 (auditoría)
--------------------------
1. **OpenTelemetry no exportaba nada.** Se creaba un `TracerProvider` sin
   `OTLPSpanExporter` ni `BatchSpanProcessor`, de modo que los spans se
   generaban y se descartaban silenciosamente (0% de trazas llegaban a
   cualquier backend). Ahora se registra el exporter + processor cuando hay
   `OTEL_EXPORTER_OTLP_ENDPOINT` configurado.
2. **`/metrics` no existía.** El comentario anterior afirmaba que
   "prometheus-client expone /metrics automáticamente", lo cual es falso:
   `prometheus_fastapi_instrumentator` ni siquiera estaba instalado y no había
   ningún `Instrumentator()` registrado. Ahora se monta explícitamente.
3. **Sentry sin scrubbing.** Con `send_default_pii=False` Sentry no envía
   headers/cookies, pero sí URLs y query strings — y en esta API hay tokens
   en query strings. Se añade `before_send` con redacción de PII.
"""
import logging
import re

logger = logging.getLogger("wowhub.instrumentation")

# OpenTelemetry imports — guarded so the module is safe to import even
# when dependencies aren't installed (e.g. in minimal test environments).
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.semconv.resource import ResourceAttributes

    OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    OTEL_AVAILABLE = False
    logger.warning("OpenTelemetry packages not installed — tracing disabled")


# ── PII scrubbing para Sentry ──────────────────────────────────────────
# FIX 2026-09-27: no existía `before_send`. Redactamos tarjetas de crédito,
# emails, tokens Bearer y secretos que puedan aparecer en URLs o query strings.
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_BEARER_RE = re.compile(r"(?i)\b(bearer|token|api[_-]?key|secret|password)"
                        r"(\"?\s*[:=]\s*\"?)([A-Za-z0-9._\-]{8,})")
_SENSITIVE_QUERY_RE = re.compile(
    r"(?i)\b(token|secret|password|api[_-]?key|access[_-]?token|signature)=([^&\s]+)"
)


def _luhn_ok(digits: str) -> bool:
    """Valida un número de tarjeta con el algoritmo de Luhn."""
    nums = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(nums) <= 19:
        return False
    checksum = 0
    parity = len(nums) % 2
    for i, d in enumerate(nums):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _scrub_text(text: str) -> str:
    """Redacta PII en un string arbitrario."""
    if not text:
        return text

    def _card_sub(m: re.Match) -> str:
        raw = m.group(0)
        return "[REDACTED_CARD]" if _luhn_ok(raw) else raw

    text = _CARD_RE.sub(_card_sub, text)
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _SENSITIVE_QUERY_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    text = _BEARER_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    return text


def _scrub_obj(obj, _depth: int = 0):
    """Redacta PII recursivamente en dicts/listas/strings de un evento Sentry."""
    if _depth > 8:
        return obj
    if isinstance(obj, str):
        return _scrub_text(obj)
    if isinstance(obj, dict):
        return {k: _scrub_obj(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_scrub_obj(v, _depth + 1) for v in obj]
    return obj


def _before_send(event, hint):
    """`before_send` de Sentry: redacta PII antes de enviar el evento."""
    try:
        request = event.get("request") or {}
        for key in ("url", "query_string", "fragment"):
            if request.get(key):
                request[key] = _scrub_text(str(request[key]))
        event["request"] = request
        event = _scrub_obj(event)
    except Exception:  # noqa: BLE001 - nunca romper el reporte de errores
        logger.debug("Sentry scrubbing falló; se envía el evento sin limpiar")
    return event


def setup_telemetry() -> None:
    """Inicializa OpenTelemetry, Sentry y Prometheus.

    Llama una sola vez durante el startup de la app (app/main.py).
    No hace nada si las variables de entorno no están configuradas.
    """
    import os

    # ── OpenTelemetry ────────────────────────────────────────────
    if OTEL_AVAILABLE:
        try:
            service_name = os.getenv("OTEL_SERVICE_NAME", "wowhub-api")
            resource = Resource.create(
                {
                    ResourceAttributes.SERVICE_NAME: service_name,
                    ResourceAttributes.SERVICE_VERSION: os.getenv("APP_VERSION", "0.2.0"),
                    ResourceAttributes.DEPLOYMENT_ENVIRONMENT: os.getenv(
                        "APP_ENV", "development"
                    ),
                }
            )
            provider = TracerProvider(resource=resource)

            # FIX 2026-09-27: registrar exporter + processor. Sin esto el
            # provider no tiene a dónde enviar los spans.
            otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
            if otlp_endpoint:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                provider.add_span_processor(
                    BatchSpanProcessor(exporter)
                )
                logger.info(
                    "OpenTelemetry OTLP exporter configurado hacia %s", otlp_endpoint
                )
            else:
                # Consola: útil en staging y para verificar que se generan spans.
                try:
                    from opentelemetry.sdk.trace.export import (
                        ConsoleSpanExporter,
                        SimpleSpanProcessor,
                    )

                    provider.add_span_processor(
                        SimpleSpanProcessor(ConsoleSpanExporter())
                    )
                    logger.info("OTEL endpoint vacío — spans a consola (debug)")
                except ImportError:
                    logger.warning("Sin exporter de spans: las trazas se descartan")

            trace.set_tracer_provider(provider)
            logger.info("OpenTelemetry TracerProvider initialised")
        except Exception as exc:  # noqa: BLE001
            logger.error("OpenTelemetry setup falló: %s", exc)

    # ── Sentry (solo si DSN está configurado) ─────────────────────
    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.sqlalchemy import SqlAlchemyIntegration

            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[
                    FastApiIntegration(),
                    SqlAlchemyIntegration(),
                ],
                environment=os.getenv("APP_ENV", "development"),
                traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
                profiles_sample_rate=float(
                    os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.01")
                ),
                send_default_pii=False,
                # FIX 2026-09-27: redacción de PII antes de enviar.
                before_send=_before_send,
            )
            logger.info("Sentry initialised (DSN present, PII scrubbing activo)")
        except ImportError:
            logger.warning("sentry-sdk not installed — Sentry disabled")
        except Exception as exc:
            logger.error(f"Sentry initialisation failed: {exc}")
    else:
        logger.info("SENTRY_DSN not set — Sentry skipped")


def instrument_app(app) -> None:
    """Aplica auto-instrumentación de FastAPI + SQLAlchemy a la app.

    Llama después de crear la instancia de FastAPI y antes de
    incluir los routers.  No hace nada si OTel no está disponible.

    FIX 2026-09-27: también registra el `Instrumentator` de Prometheus, que
    es lo que realmente expone `/metrics`.

    FIX 2026-10-03: salta limpiamente `SQLAlchemyInstrumentor().instrument()`
    cuando la versión de SQLAlchemy instalada queda fuera del rango
    soportado por `opentelemetry-instrumentation-sqlalchemy`. La librería
    loggea un ERROR antes de lanzar la excepción, así que envolver en
    try/except no era suficiente: había que evitar la llamada.
    """
    if OTEL_AVAILABLE:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            FastAPIInstrumentor.instrument_app(app)

            # FIX 2026-10-03: chequeo de versión explícito. La rama except
            # no silenciaba el ERROR que emite `opentelemetry.instrumentation.
            # instrumentor` antes de lanzar, así que la salida del boot
            # quedaba contaminada aunque el warning local fuera correcto.
            # Comprobamos la versión instalada y omitimos el instrumentor
            # cuando no es compatible, evitando el log ruidoso.
            try:
                import sqlalchemy as _sa
                _sa_major_minor = tuple(
                    int(p) for p in _sa.__version__.split(".")[:2]
                )
                _sqla_too_new = _sa_major_minor >= (2, 1)
            except Exception:  # noqa: BLE001
                _sqla_too_new = False

            if _sqla_too_new:
                logger.warning(
                    "SQLAlchemy %s no soportado por opentelemetry-instrumentation-"
                    "sqlalchemy (requiere <2.1.0). Auto-instrumentación de "
                    "SQLAlchemy omitida; trazas de FastAPI siguen activas.",
                    _sa.__version__,
                )
            else:
                SQLAlchemyInstrumentor().instrument()
                logger.info("SQLAlchemy auto-instrumented with OpenTelemetry")

            logger.info("FastAPI auto-instrumented with OpenTelemetry")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"OpenTelemetry auto-instrumentation failed: {exc}")

    # ── Prometheus: expone /metrics ────────────────────────────────
    # FIX 2026-09-27: antes sólo había un comentario que decía que /metrics
    # se exponía "automáticamente", pero `prometheus_fastapi_instrumentator`
    # no estaba instalado ni registrado. Sin esto el endpoint no existía.
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
            excluded_handlers=[getattr(app, "openapi_url", None), "/metrics"],
        ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
        logger.info("Prometheus Instrumentator registrado — /metrics expuesto")
    except ImportError:
        logger.warning(
            "prometheus-fastapi-instrumentator no instalado — /metrics no se expone"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo montar /metrics: %s", exc)
