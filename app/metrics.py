"""Metrics + monitoring middleware.

This file is the heart of the project. For every request it records:
  1. a counter   -> how many requests, per endpoint and status code
  2. a histogram -> how long each request took
  3. error details (type, message, traceback) when the code crashes
"""
import json
import logging
import time
import traceback
import uuid
from collections import deque
from datetime import datetime, timezone

from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(message)s")

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 10),
)

# 1 = healthy, 0 = unhealthy (used by the "service health failure" alert)
HEALTH_STATUS = Gauge("app_health_status", "1 if service is healthy, 0 otherwise")
HEALTH_STATUS.set(1)

# Last 50 server errors, exposed at /debug/errors for root cause analysis
RECENT_ERRORS: deque = deque(maxlen=50)


def preinit_series() -> None:
    """Create failure series at 0 on startup.

    Prometheus' increase() cannot see a counter that appears for the first
    time with value 1, so we create these at 0. Alerts then fire on the first failure.
    """
    for endpoint, status in [
        ("/simulate-error", "500"),
        ("/protected", "401"),
        ("/simulate-rate-limit", "429"),
        ("/simulate-rate-limit", "200"),
        ("/simulate-timeout", "200"),
        ("/health", "503"),
    ]:
        REQUEST_COUNT.labels("GET", endpoint, status)


def _route_path(request) -> str:
    # Use the route template (e.g. /users/{id}) so labels do not explode.
    route = request.scope.get("route")
    return getattr(route, "path", "unmatched")


class MonitoringMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == "/metrics":  # do not count Prometheus scrapes
            return await call_next(request)

        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except Exception as exc:  # unhandled crash -> HTTP 500 + RCA info
            request_id = str(uuid.uuid4())[:8]
            record = {
                "time": datetime.now(timezone.utc).isoformat(),
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback": traceback.format_exc(),
            }
            RECENT_ERRORS.append(record)
            logger.error(json.dumps(record))
            return JSONResponse(
                status_code=500,
                content={"error": "Internal Server Error", "request_id": request_id},
            )
        finally:
            duration = time.perf_counter() - start
            endpoint = _route_path(request)
            REQUEST_COUNT.labels(request.method, endpoint, str(status)).inc()
            REQUEST_LATENCY.labels(request.method, endpoint).observe(duration)
