"""Local rehearsal of the frontend flow against a real Uvicorn server.

Runs every path in ``frontend-flowchart.txt`` — recommendation, approval,
polling, completion callback, cancellation, session isolation, and CORS —
against a throwaway database in the cost-free ``fake`` provider mode.

    python -m training_cost_optimizer.mvp.rehearsal

This is an operational check, not a unit test: it starts a server process and
takes about a minute. No Runpod API call and no cost is involved.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ORIGIN = "http://localhost:5173"

failures: list[str] = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label} {detail}")
    if not condition:
        failures.append(label)


def poll_until(client, base, job_id, wanted, timeout=90):
    deadline = time.time() + timeout
    seen = []
    while time.time() < deadline:
        job = client.get(f"{base}/api/v1/jobs/{job_id}").json()
        if not seen or seen[-1] != job["status"]:
            seen.append(job["status"])
        if job["status"] in wanted:
            return job, seen
        time.sleep(2.5)  # the frontend polling interval
    return client.get(f"{base}/api/v1/jobs/{job_id}").json(), seen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m training_cost_optimizer.mvp.rehearsal")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    base = f"http://127.0.0.1:{args.port}"
    database = Path(tempfile.mkdtemp()) / "rehearsal.sqlite3"
    env = {
        **os.environ,
        "MVP_PROVIDER_MODE": "fake",
        "MVP_DATABASE_PATH": str(database),
        "FRONTEND_ORIGINS": f"*,{ORIGIN}",
        "MVP_MAX_RUNTIME_MINUTES": "10",
        "MVP_COOKIE_SECURE": "false",  # the rehearsal server speaks plain HTTP
    }
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "training_cost_optimizer.api:app",
         "--host", "127.0.0.1", "--port", str(args.port), "--workers", "1"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.3)
        else:
            raise SystemExit("server did not start")

        # A: 웹 접속 → B: POST /session
        client = httpx.Client(timeout=10)
        session = client.post(f"{base}/api/v1/session")
        check("POST /session → 201", session.status_code == 201)
        check("session cookie is HttpOnly", "HttpOnly" in session.headers.get("set-cookie", ""))
        check("session cookie is usable over local HTTP", "Secure" not in session.headers.get("set-cookie", ""))

        # D → F: 예산 안의 실행안 없음
        no_plan = client.post(f"{base}/api/v1/jobs", json={"maxBudgetKrw": 449, "priority": "CHEAPEST"})
        check("budget too low → 422 NO_ELIGIBLE_PLAN",
              no_plan.status_code == 422 and no_plan.json()["error"]["code"] == "NO_ELIGIBLE_PLAN")

        # D → E: 추천 실행 계약
        created = client.post(f"{base}/api/v1/jobs", json={"maxBudgetKrw": 1000, "priority": "BALANCED"})
        job = created.json()
        check("POST /jobs → 201 DRAFT", created.status_code == 201 and job["status"] == "DRAFT")
        check("recommended profile is returned",
              job["executionPlan"]["recommended"]["profileId"] == "runpod-l40s-v1",
              job["executionPlan"]["recommended"]["reason"])

        # G → H: 승인
        started = client.post(f"{base}/api/v1/jobs/{job['id']}/start")
        check("POST /start → 202 PROVISIONING",
              started.status_code == 202 and started.json()["status"] == "PROVISIONING")

        # I → M: 폴링으로 RUNNING 확인
        running, seen = poll_until(client, base, job["id"], {"RUNNING", "FAILED"})
        check("polling reaches RUNNING", running["status"] == "RUNNING", f"seen={seen}")
        check("startedAt is exposed", bool(running["startedAt"]))

        # 4: 학습 컨테이너 completion callback
        callback = httpx.post(
            f"{base}/api/v1/internal/jobs/{job['id']}/completion",
            json={"outcome": "SUCCEEDED", "exitCode": 0, "message": "Training completed"},
            timeout=10,
        )
        check("completion callback → 204", callback.status_code == 204)

        # M → R: 완료 화면
        completed, seen = poll_until(client, base, job["id"], {"COMPLETED", "FAILED", "CANCELLED"})
        check("job becomes COMPLETED", completed["status"] == "COMPLETED", f"seen={seen}")
        check("TERMINATING precedes COMPLETED", "TERMINATING" in seen, f"seen={seen}")
        check("completion detail is present",
              completed["exitCode"] == 0
              and completed["completionLog"] == "Training completed"
              and bool(completed["podTerminatedAt"]))

        # K: 세션당 실행 1회
        second = client.post(f"{base}/api/v1/jobs", json={"maxBudgetKrw": 1000, "priority": "CHEAPEST"}).json()
        reused = client.post(f"{base}/api/v1/jobs/{second['id']}/start")
        check("second start → 409 EXECUTION_ALREADY_USED",
              reused.status_code == 409 and reused.json()["error"]["code"] == "EXECUTION_ALREADY_USED")

        # O → P: 실행 중단
        canceller = httpx.Client(timeout=10)
        canceller.post(f"{base}/api/v1/session")
        cancel_job = canceller.post(f"{base}/api/v1/jobs", json={"maxBudgetKrw": 1000, "priority": "FASTEST"}).json()
        canceller.post(f"{base}/api/v1/jobs/{cancel_job['id']}/start")
        cancelled = canceller.post(f"{base}/api/v1/jobs/{cancel_job['id']}/cancel")
        check("POST /cancel → 202 TERMINATING",
              cancelled.status_code == 202 and cancelled.json()["status"] == "TERMINATING")
        final, seen = poll_until(canceller, base, cancel_job["id"], {"CANCELLED", "FAILED", "COMPLETED"})
        check("cancel ends in CANCELLED", final["status"] == "CANCELLED", f"seen={seen}")
        check("pod termination is confirmed", bool(final["podTerminatedAt"]))

        # J: 다른 세션의 Job은 숨겨진다
        hidden = client.get(f"{base}/api/v1/jobs/{cancel_job['id']}")
        check("other session sees 404 JOB_NOT_FOUND",
              hidden.status_code == 404 and hidden.json()["error"]["code"] == "JOB_NOT_FOUND")

        # CORS: 자격증명 포함 요청에 정확한 origin만 허용
        preflight = httpx.options(
            f"{base}/api/v1/jobs",
            headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
            timeout=10,
        )
        check("CORS allows the frontend origin",
              preflight.headers.get("access-control-allow-origin") == ORIGIN)
        check("CORS allows credentials",
              preflight.headers.get("access-control-allow-credentials") == "true")
        blocked = httpx.options(
            f"{base}/api/v1/jobs",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
            timeout=10,
        )
        check("CORS rejects an unknown origin",
              blocked.headers.get("access-control-allow-origin") not in {"*", "https://evil.example"})
    finally:
        server.terminate()
        try:
            logs = server.communicate(timeout=10)[0]
        except subprocess.TimeoutExpired:
            server.kill()
            logs = server.communicate()[0]
        print("\n--- server log (mvp lines) ---")
        for line in logs.splitlines():
            if "mvp" in line or "job=" in line or "pod=" in line or "MVP" in line:
                print(line)
        secrets = ["NVIDIA A100 40GB PCIe", "unwork/sd15-lora:1", "run-demo-training.sh"]
        leaked = [s for s in secrets if s in logs]
        check("server log exposes no provider secrets", not leaked, str(leaked))

    print("\nFAILURES:", failures or "none")
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover - manual operational entrypoint
    raise SystemExit(main())
