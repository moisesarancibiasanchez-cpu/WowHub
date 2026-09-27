"""Instrumentación OTel + Sentry + Prometheus para WowHub.

HU_07: Observabilidad — trazas, errores y métricas para producción.
Se activa automáticamente al importar este módulo o al llamar setup_telemetry().
"""
import logging

logger = logging.getLogger("wowhub.instrumentation")

# OpenTelemetry imports — guarded so the module is safe to import even
# when dependencies aren't installed (e.g. in minimal test environments).
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.semconv.resource import ResourceAttributes
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    logger.warning("OpenTelemetry packages not installed — tracing disabled")


def setup_telemetry() -> None:
    """Inicializa OpenTelemetry, Sentry y Prometheus.

    Llama una sola vez durante el startup de la app (app/main.py).
    No hace nada si las variables de entorno no están configuradas.
    """
    import os

    # ── OpenTelemetry ────────────────────────────────────────────
    if OTEL_AVAILABLE:
        resource = Resource.create({ResourceAttributes.SERVICE_NAME: "wowhub-api"})
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)
        logger.info("OpenTelemetry TracerProvider initialised")

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
                send_default_pii=False,
            )
            logger.info("Sentry initialised (DSN present)")
        except ImportError:
            logger.warning("sentry-sdk not installed — Sentry disabled")
        except Exception as exc:
            logger.error(f"Sentry initialisation failed: {exc}")
    else:
        logger.info("SENTRY_DSN not set — Sentry skipped")

    # ── Prometheus ─────────────────────────────────────────────────
    # FastAPI + prometheus-client (via prometheus_fastapi_instrumentator)
    # automatically exposes /metrics.  No extra setup needed here.
    # The prometheus_client registry is the default one used by the
    # instrumentator, so counters/histograms defined elsewhere just work.
    logger.info("Prometheus metrics available at /metrics (if instrumentator is registered)")


def instrument_app(app) -> None:
    """Aplica auto-instrumentación de FastAPI + SQLAlchemy a la app.

    Llama después de crear la instancia de FastAPI y antes de
    incluir los routers.  No hace nada si OTel no está disponible.
    """
    if not OTEL_AVAILABLE:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument()
        logger.info("FastAPI + SQLAlchemy auto-instrumented with OpenTelemetry")
    except Exception as exc:
        logger.warning(f"OpenTelemetry auto-instrumentation failed: {exc}")
