try:
    from prometheus_client import CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST, Gauge
    _HAS_PROM = True
except Exception:
    # prometheus_client is optional for local/dev; if it's not installed we expose a harmless fallback.
    _HAS_PROM = False

from django.http import HttpResponse

if _HAS_PROM:
    # Simple metrics endpoint exposing a few basic gauges.
    registry = CollectorRegistry()
    uptime_g = Gauge('connectwell_uptime_seconds', 'Uptime seconds (placeholder)', registry=registry)

    def metrics_view(request):
        # In a real deployment you'd update metrics from application state. Here we expose a static value.
        try:
            import time
            uptime_g.set(time.time())
        except Exception:
            pass
        data = generate_latest(registry)
        return HttpResponse(data, content_type=CONTENT_TYPE_LATEST)
else:
    def metrics_view(request):
        # prometheus_client not available — return a small plain text message so the app loads in tests/dev
        return HttpResponse("prometheus_client not installed", content_type="text/plain")
