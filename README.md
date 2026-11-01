# API Monitoring Dashboard (FastAPI + Prometheus + Grafana + Alertmanager)

A sample FastAPI REST API that exposes its own metrics, monitored by Prometheus, visualised in Grafana, with Slack and Email alerts through Alertmanager. Everything runs with a single `docker compose up`.

```
simulate_failures.py --> FastAPI app (:8000) --/metrics--> Prometheus (:9090) --> Alertmanager (:9093) --> Slack / Email
                                                                 |
                                                                 +--> Grafana (:3000) dashboard
```

## 1. Setup

Requirements: Docker + Docker Compose, a Slack Incoming Webhook, a Gmail App Password.

```bash
git clone <your-repo-url> && cd api-monitoring-dashboard
cp .env.example .env        # then edit .env with your Slack webhook and Gmail details
docker compose up --build
```

| Service | URL | Login |
|---|---|---|
| FastAPI (Swagger docs) | http://localhost:8000/docs | none |
| Prometheus (alerts tab) | http://localhost:9090/alerts | none |
| Alertmanager | http://localhost:9093 | none |
| Grafana dashboard | http://localhost:3000 | admin / admin |

The dashboard "API Monitoring Dashboard" is loaded automatically.

### Getting the notification credentials
- **Slack:** api.slack.com/apps > Create app > Incoming Webhooks > activate > Add New Webhook to Workspace > copy URL into `SLACK_WEBHOOK_URL`.
- **Gmail:** enable 2-Step Verification, then Google Account > Security > App passwords > create one and put it in `GMAIL_APP_PASSWORD`.

## 2. Endpoints

| Endpoint | Behaviour |
|---|---|
| `GET /health` | 200 healthy, 503 if health is switched off |
| `GET /users`, `GET /products` | Sample data |
| `GET /simulate-error` | Raises an exception -> HTTP 500 |
| `GET /simulate-timeout` | Responds after 4 seconds |
| `GET /simulate-rate-limit` | 429 after 5 requests in 10 seconds |
| `GET /protected` | Needs header `X-API-Key: secret-key-123`, else 401 |
| `POST /admin/health/down` or `/up` | Toggle health failure (demo helper) |
| `GET /debug/errors` | Last server errors with traceback (root cause info) |
| `GET /metrics` | Prometheus metrics |

## 3. Run the failure simulation

```bash
pip install requests
python scripts/simulate_failures.py        # scenarios 1-4
python scripts/simulate_failures.py 5      # extra: health failure
docker compose stop app                    # extra: API downtime -> APIDown alert
docker compose start app                   # recover
```

| Scenario | What happens | Alert |
|---|---|---|
| 1 Invalid auth | 401 responses | AuthenticationFailures |
| 2 Timeout | 4s responses | SlowResponse |
| 3 Server error | 500 + traceback stored | HTTP500Errors, HighFailureRate |
| 4 Rate limit | 429 responses | RateLimitExceeded |
| Extra: health down | /health returns 503 | ServiceHealthFailure |
| Extra: stop container | Prometheus cannot scrape | APIDown |

See `docs/TECHNICAL_DOCUMENTATION.md` for architecture, alert rules, troubleshooting and maintenance.
