"""Runs the 4 failure scenarios against the API and shows what Prometheus detected.

Usage:
    pip install requests
    python scripts/simulate_failures.py            # run all scenarios
    python scripts/simulate_failures.py 3          # run only scenario 3
"""
import sys
import time

import requests

API = "http://localhost:8000"
PROM = "http://localhost:9090"


def title(text):
    print("\n" + "=" * 60 + f"\n{text}\n" + "=" * 60)


def scenario_1_invalid_auth():
    title("Scenario 1: Invalid API authentication (expect 401)")
    for _ in range(3):
        r = requests.get(f"{API}/protected", headers={"X-API-Key": "wrong-key"})
        print(f"  status={r.status_code} body={r.json()}")
    print("  Expected alert: AuthenticationFailures")


def scenario_2_timeout():
    title("Scenario 2: API timeout (expect ~4s responses)")
    for _ in range(3):
        t = time.time()
        r = requests.get(f"{API}/simulate-timeout", timeout=15)
        print(f"  status={r.status_code} took={time.time() - t:.2f}s")
    print("  Expected alert: SlowResponse (average > 3s)")


def scenario_3_server_error():
    title("Scenario 3: Server error (expect HTTP 500)")
    for _ in range(3):
        r = requests.get(f"{API}/simulate-error")
        print(f"  status={r.status_code} body={r.json()}")
    print("\n  Root cause info captured by the API (GET /debug/errors):")
    last = requests.get(f"{API}/debug/errors").json()[-1]
    print(f"    error_type    : {last['error_type']}")
    print(f"    error_message : {last['error_message']}")
    print(f"    path          : {last['path']}")
    print(f"    request_id    : {last['request_id']}")
    print("  Expected alerts: HTTP500Errors, HighFailureRate")


def scenario_4_rate_limit():
    title("Scenario 4: Rate limit exceeded (expect HTTP 429)")
    for i in range(1, 9):
        r = requests.get(f"{API}/simulate-rate-limit")
        print(f"  request {i}: status={r.status_code}")
    print("  Expected alert: RateLimitExceeded")


def scenario_5_health_failure():
    title("Extra: Health failure (/health returns 503)")
    requests.post(f"{API}/admin/health/down")
    print("  /health ->", requests.get(f"{API}/health").status_code)
    print("  Waiting 25s so the alert can fire, then restoring health ...")
    time.sleep(25)
    show_alerts()
    requests.post(f"{API}/admin/health/up")
    print("  health restored")
    print("  Expected alert: ServiceHealthFailure")


def show_alerts():
    print("\n  Alerts currently seen by Prometheus:")
    try:
        alerts = requests.get(f"{PROM}/api/v1/alerts", timeout=5).json()["data"]["alerts"]
    except Exception as e:
        print(f"  could not reach Prometheus: {e}")
        return
    if not alerts:
        print("   (none yet)")
    for a in alerts:
        print(f"   - {a['labels']['alertname']:<24} state={a['state']}")


SCENARIOS = {
    "1": scenario_1_invalid_auth,
    "2": scenario_2_timeout,
    "3": scenario_3_server_error,
    "4": scenario_4_rate_limit,
    "5": scenario_5_health_failure,
}

if __name__ == "__main__":
    chosen = sys.argv[1:] or ["1", "2", "3", "4"]
    for key in chosen:
        SCENARIOS[key]()
    if "5" not in chosen:
        print("\nWaiting 20s for Prometheus to evaluate alert rules ...")
        time.sleep(20)
        show_alerts()
    print("\nNow check Grafana (http://localhost:3000), Slack and your email.")
