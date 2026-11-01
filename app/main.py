import asyncio
import os
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.metrics import HEALTH_STATUS, RECENT_ERRORS, MonitoringMiddleware, preinit_series

app = FastAPI(title="Sample API for Monitoring Demo")
app.add_middleware(MonitoringMiddleware)
preinit_series()

API_KEY = os.getenv("API_KEY", "secret-key-123")
RATE_LIMIT = 5          # max requests ...
RATE_WINDOW = 10        # ... per 10 seconds, per client
_hits = defaultdict(deque)
_state = {"healthy": True}

USERS = [
    {"id": 1, "name": "Asha", "email": "asha@example.com"},
    {"id": 2, "name": "Ravi", "email": "ravi@example.com"},
    {"id": 3, "name": "Meera", "email": "meera@example.com"},
]
PRODUCTS = [
    {"id": 1, "name": "Laptop", "price": 55000},
    {"id": 2, "name": "Phone", "price": 20000},
    {"id": 3, "name": "Headphones", "price": 2500},
]


# ---------- normal endpoints ----------
@app.get("/health")
def health():
    if not _state["healthy"]:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
    return {"status": "healthy"}


@app.get("/users")
def users():
    return USERS


@app.get("/products")
def products():
    return PRODUCTS


# ---------- failure simulation endpoints ----------
@app.get("/simulate-error")
def simulate_error():
    # Unhandled exception -> middleware turns it into HTTP 500 and records RCA info
    raise RuntimeError("Simulated database connection failure")


@app.get("/simulate-timeout")
async def simulate_timeout():
    await asyncio.sleep(4)  # slower than our 3 second alert threshold
    return {"message": "Finally responded after 4 seconds"}


@app.get("/simulate-rate-limit")
def simulate_rate_limit(request: Request):
    client = request.client.host if request.client else "unknown"
    now = time.time()
    hits = _hits[client]
    while hits and now - hits[0] > RATE_WINDOW:
        hits.popleft()
    if len(hits) >= RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(RATE_WINDOW)},
        )
    hits.append(now)
    return {"message": "ok", "requests_in_window": len(hits)}


@app.get("/protected")
def protected(x_api_key: str = Header(default=None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return {"message": "Authenticated"}


# ---------- helper endpoints for the demo ----------
@app.post("/admin/health/{state}")
def set_health(state: str):
    """POST /admin/health/down or /admin/health/up -> simulate health failure."""
    healthy = state == "up"
    _state["healthy"] = healthy
    HEALTH_STATUS.set(1 if healthy else 0)
    return {"healthy": healthy}


@app.get("/debug/errors")
def debug_errors():
    """Root cause analysis info: last server errors with traceback."""
    return list(RECENT_ERRORS)


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
