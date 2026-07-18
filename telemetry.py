"""
OpenTelemetry + Prometheus bootstrap for memory-distiller.

Mirrors the Node services' `lib/tracing.ts` / `lib/promMetrics.ts` split:

* OTLP path (traces + metrics) → the bouc.io OTel collector. The collector runs as a
  hostNetwork daemonset, so the endpoint is the node IP — the chart injects
  `OTEL_EXPORTER_OTLP_ENDPOINT=http://$(HOST_IP):4318`. Traces land in Jaeger; OTLP
  metrics re-surface in Prometheus `otel_`-prefixed and `environment`-tagged.
* Direct-scrape path → a Prometheus `/metrics` endpoint (prometheus_client), scraped via
  the chart's `prometheus.io/scrape` pod annotation. Business counters carry a `service`
  and `environment` label so they line up with the collector-routed `otel_*` series.

The OTLP path is a no-op unless `OTEL_EXPORTER_OTLP_ENDPOINT` (or `OTEL_ENABLED=true`) is
set, so local dev without a collector runs untouched and never spams connection errors.
The `/metrics` endpoint is always available.
"""
import logging
import os

from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

logger = logging.getLogger("memory-distiller.telemetry")

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "memory-distiller")
ENVIRONMENT_ID = os.getenv("ENVIRONMENT_ID", "unknown")
_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
_OTEL_ENABLED = os.getenv("OTEL_ENABLED", "").lower() == "true" or bool(_OTLP_ENDPOINT)

# --- Direct-scrape business metrics (always on) ---------------------------------------
# `service` + `environment` mirror the labels the collector stamps on OTLP-routed signals,
# so direct-scraped distiller_* metrics line up with otel_* in Grafana.
_LABELS = {"service": SERVICE_NAME, "environment": ENVIRONMENT_ID}

distill_requests_total = Counter(
    "distiller_requests_total",
    "Distillation requests received by terminal outcome",
    ["service", "environment", "status"],
)
distill_memories_stored_total = Counter(
    "distiller_memories_stored_total",
    "Memory objects stored downstream by category",
    ["service", "environment", "category"],
)


def record_request(status: str) -> None:
    """status: accepted | completed | failed"""
    distill_requests_total.labels(status=status, **_LABELS).inc()


def record_memories_stored(category: str, count: int = 1) -> None:
    if count:
        distill_memories_stored_total.labels(category=category, **_LABELS).inc(count)


def metrics_response():
    """Return (body, content_type) for the GET /metrics endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST


# --- OTLP path (traces + metrics), gated on the collector endpoint --------------------
def setup_otlp() -> None:
    """Configure OTLP trace + metric export. No-op unless the collector endpoint is set."""
    if not _OTEL_ENABLED:
        logger.info("[telemetry] OTLP disabled (OTEL_EXPORTER_OTLP_ENDPOINT unset)")
        return

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # `environment` here matches the collector's resource processor tag.
        resource = Resource.create(
            {"service.name": SERVICE_NAME, "environment": ENVIRONMENT_ID}
        )

        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(tracer_provider)

        reader = PeriodicExportingMetricReader(OTLPMetricExporter())
        metrics.set_meter_provider(
            MeterProvider(resource=resource, metric_readers=[reader])
        )

        logger.info(
            "[telemetry] OpenTelemetry started (endpoint=%s, service=%s, env=%s)",
            _OTLP_ENDPOINT,
            SERVICE_NAME,
            ENVIRONMENT_ID,
        )
    except Exception:  # pragma: no cover - never block startup on telemetry
        logger.exception("[telemetry] OpenTelemetry init failed")


def instrument_app(app) -> None:
    """Auto-instrument the FastAPI app for request traces (no-op if OTLP disabled)."""
    if not _OTEL_ENABLED:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("[telemetry] FastAPI instrumented")
    except Exception:  # pragma: no cover
        logger.exception("[telemetry] FastAPI instrumentation failed")
