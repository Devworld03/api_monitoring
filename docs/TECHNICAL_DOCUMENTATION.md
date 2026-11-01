# Technical Documentation: API Monitoring Dashboard

## 1. Overview
This project demonstrates API health tracking, performance monitoring, failure detection, alerting and root cause analysis for a sample FastAPI service. The approach is "the application exposes metrics, and standard tools collect, visualise and alert on them".

## 2. Architecture

```
Client / simulate_failures.py
        |
        v
FastAPI app (:8000)  --- MonitoringMiddleware records every request
        |  GET /metrics
        v
Prometheus (:9090)  - scrapes every 5s, stores time series, evaluates alert rules every 5s
        |                         |
        v                         v
Grafana (:3000)           Alertmanager (:9093) --> Slack webhook, Gmail SMTP
```

| Component | Responsibility |
|---|---|
| FastAPI app | Sample endpoints, failure simulation, metrics, error capture |
| prometheus-client | Defines and exposes metrics in Prometheus format |
| Prometheus | Collection, storage, alert rule evaluation |
| Alertmanager | Grouping and delivery of alerts to Slack and Email |
| Grafana | Dashboard (auto-provisioned from files) |
| Docker Compose | Starts the full stack with one command |

## 3. Implementation details

### 3.1 Monitoring middleware (`app/metrics.py`)
A Starlette middleware wraps every request and records:
- `http_requests_total{method, endpoint, status}` (Counter): request count, which gives total requests, failed requests and error percentage.
- `http_request_duration_seconds{method, endpoint}` (Histogram): latency, which gives average response time. Buckets include 3s, matching the alert threshold.
- `app_health_status` (Gauge): 1 healthy, 0 unhealthy.

Details worth knowing:
- The `endpoint` label uses the route template, not the raw URL, to keep the number of time series small.
- `/metrics` itself is excluded so Prometheus scrapes do not distort the numbers.
- Failure series are created at value 0 on startup (`preinit_series`), because Prometheus `increase()` misses a counter that first appears with value 1.

### 3.2 Root cause analysis
When an endpoint raises an unhandled exception, the middleware:
1. returns a clean HTTP 500 JSON response with a `request_id`,
2. writes a structured JSON log line (exception type, message, path, traceback),
3. keeps the last 50 errors in memory, readable at `GET /debug/errors`.

Alert text points the engineer to this endpoint, so the path from "alert fired" to "root cause" is: Slack/Email alert -> `/debug/errors` -> exception type and traceback.

### 3.3 Failure simulation endpoints
- `/simulate-error`: raises `RuntimeError`.
- `/simulate-timeout`: `await asyncio.sleep(4)`.
- `/simulate-rate-limit`: sliding window per client IP, 5 requests per 10 seconds, then 429 with `Retry-After`.
- `/protected`: compares the `X-API-Key` header with the `API_KEY` environment variable, 401 on mismatch.
- `POST /admin/health/down|up`: switches the health state so the health alert can be demonstrated.

## 4. Dashboard (Grafana)
Provisioned automatically from `grafana/provisioning` and `grafana/dashboards/api-monitoring.json`.

| Panel | PromQL |
|---|---|
| Current service status | `up{job="fastapi-app"}` (mapped to UP/DOWN) |
| API uptime % (1h) | `avg_over_time(up{job="fastapi-app"}[1h]) * 100` |
| Avg response time | `sum(rate(..._sum[5m])) / sum(rate(..._count[5m]))` |
| Total API requests | `sum(http_requests_total)` |
| Failed requests | `sum(http_requests_total{status=~"[45].."})` |
| Error % | failed rate divided by total rate, x100 |
| Error trend | `sum by (status) (rate(http_requests_total{status=~"[45].."}[1m]))` |
| Requests/s and latency by endpoint | extra panels for drill-down |

"Failed" is defined as HTTP status 400 or above, so authentication and rate limit failures are counted too.

## 5. Alert rules (`prometheus/alert_rules.yml`)

| Alert | Condition | Severity |
|---|---|---|
| APIDown | `up == 0` for 15s | critical |
| SlowResponse | average response time per endpoint > 3s | warning |
| HTTP500Errors | any 500 in the last minute | critical |
| HighFailureRate | failed requests > 10% of traffic for 15s | warning |
| ServiceHealthFailure | `app_health_status == 0` for 10s | critical |
| AuthenticationFailures | any 401/403 in the last minute | warning |
| RateLimitExceeded | any 429 in the last minute | warning |

Delivery: Alertmanager groups by alert name and endpoint, then sends to Slack (webhook) and Email (Gmail SMTP). A phone/call channel is optional in the task and was not implemented. Secrets come from `.env`; a `sed` command in the Alertmanager container fills them into `alertmanager.tmpl` at startup because Alertmanager cannot read environment variables itself.

Timings (5s scrape, short `for` durations) are tuned for a quick demo. In production they would be longer to avoid noisy alerts.

## 6. Failure simulation and expected results

| Scenario | Trigger | Detected as | Alert |
|---|---|---|---|
| Invalid authentication | `GET /protected` with wrong key | 401 on `/protected` | AuthenticationFailures |
| API timeout | `GET /simulate-timeout` | average latency about 4s | SlowResponse |
| Server error | `GET /simulate-error` | 500 + traceback in `/debug/errors` | HTTP500Errors, HighFailureRate |
| Rate limit | 8 quick calls to `/simulate-rate-limit` | 429 responses | RateLimitExceeded |
| Health failure | `POST /admin/health/down` | `app_health_status == 0` | ServiceHealthFailure |
| Downtime | `docker compose stop app` | `up == 0` | APIDown |

Run with `python scripts/simulate_failures.py`. Capture screenshots of the Grafana dashboard, the Prometheus alerts page, the Slack message and the email as evidence.

## 7. Key technical decisions
1. **Prometheus + Grafana instead of a hosted SaaS tool**: shows the backend logic (instrumentation, alert rules as code) and is free and reproducible.
2. **Custom middleware instead of an off-the-shelf instrumentator library**: about 60 lines, easy to explain, full control over labels and error capture.
3. **No database**: not needed for monitoring; sample data is in memory.
4. **Alerts as code**: rules live in version control and are reviewable.
5. **Docker Compose**: one command for the whole stack.
6. **In-memory error store**: simple and sufficient for a demo. Production would use centralised logging or error tracking.

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Prometheus target `fastapi-app` is DOWN | App container not running | `docker compose ps`, `docker compose logs app` |
| Grafana panels show "No data" | No traffic yet, or datasource wrong | Send requests, check Prometheus is reachable |
| Alert is Pending but never Firing | `for` duration not yet satisfied | Wait, or keep generating failures |
| Alert Firing but no Slack/Email | Wrong webhook or app password in `.env` | `docker compose logs alertmanager`, fix `.env`, `docker compose up -d --force-recreate alertmanager` |
| Alertmanager exits at start | `.env` missing | `cp .env.example .env` |
| Email fails with authentication error | Normal Gmail password used | Use a Gmail App Password |
| 500 alert fired, need the cause | | `curl localhost:8000/debug/errors` or `docker compose logs app` |

## 9. Maintenance process
- **Change thresholds:** edit `prometheus/alert_rules.yml`, then `docker compose restart prometheus`.
- **Add an endpoint:** no monitoring change needed; the middleware instruments it automatically.
- **Change alert receivers:** edit `alertmanager/alertmanager.tmpl`, then recreate the alertmanager container.
- **Update the dashboard:** edit in Grafana, export JSON, replace `grafana/dashboards/api-monitoring.json`.
- **Rotate secrets:** update `.env` and recreate the alertmanager container.
- **Keep images current:** review pinned versions in `docker-compose.yml` and `requirements.txt` periodically.
- **Data retention:** Prometheus keeps 15 days by default; add a volume to persist data across restarts.
