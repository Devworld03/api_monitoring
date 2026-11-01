# Video outline (aim for 8-10 minutes)

1. **Intro (30s):** Task kya tha. Ek line: "App apni metrics banati hai, Prometheus collect karta hai, Grafana dikhata hai, Alertmanager Slack/Email bhejta hai."
2. **Architecture (1 min):** diagram dikhao (README) aur har tool ka kaam bolo.
3. **Code walkthrough (3 min):**
   - `app/main.py`: endpoints, har failure endpoint kya karta hai.
   - `app/metrics.py`: middleware. Counter, histogram, exception capture, `/debug/errors`.
   - Bolo kyu: pre-init series, route template label.
4. **Config (1.5 min):** `prometheus.yml` (scrape), `alert_rules.yml` (5 required + 2 extra), `alertmanager.tmpl` (Slack + Email), `docker-compose.yml`.
5. **Live demo (3 min):**
   - `docker compose up`, Grafana dashboard dikhao.
   - `python scripts/simulate_failures.py`
   - Grafana graph change hote dikhao, Prometheus Alerts tab (Pending -> Firing).
   - Slack message aur email dikhao.
   - Scenario 3 ka root cause: `curl localhost:8000/debug/errors`.
   - `docker compose stop app` -> APIDown alert.
6. **Decisions + wrap up (1 min):** Prometheus kyu, DB kyu nahi, alerts as code, kya aage improve ho sakta hai (phone alert, centralized logging).
