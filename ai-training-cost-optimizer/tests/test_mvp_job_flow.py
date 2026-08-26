from fastapi.testclient import TestClient
from datetime import timedelta

from training_cost_optimizer.mvp.recommendation import ProfileRecommendationService
from training_cost_optimizer.mvp.repository import SQLiteMvpRepository
from training_cost_optimizer.mvp.service import JobApplicationService
from training_cost_optimizer.mvp.router import get_mvp_service
from training_cost_optimizer.mvp.runner import FakeJobRunner
from training_cost_optimizer.mvp.domain import utc_now
from training_cost_optimizer.mvp.runner import JobLifecycleWorker
from training_cost_optimizer.mvp.fake_provider import FakeRunpodLifecycleProvider
from training_cost_optimizer.api import app


def _service(database_path) -> JobApplicationService:
    return JobApplicationService(SQLiteMvpRepository(database_path))


def _client(service: JobApplicationService) -> TestClient:
    app.dependency_overrides[get_mvp_service] = lambda: service
    return TestClient(app, base_url="https://testserver")


def test_recommendation_policies_choose_deterministic_profiles():
    recommendation = ProfileRecommendationService()

    assert recommendation.recommend(max_budget_krw=1_000, priority="CHEAPEST").selected_profile_id == "runpod-rtx4090-v1"
    assert recommendation.recommend(max_budget_krw=1_000, priority="FASTEST").selected_profile_id == "runpod-a100-v1"
    assert recommendation.recommend(max_budget_krw=1_000, priority="BALANCED").selected_profile_id == "runpod-l40s-v1"


def test_create_job_persists_recommendation_snapshot(tmp_path):
    service = _service(tmp_path / "mvp.sqlite3")
    client = _client(service)
    try:
        session = client.post("/api/v1/session")
        assert session.status_code == 201
        assert "HttpOnly" in session.headers["set-cookie"]
        assert "Secure" in session.headers["set-cookie"]
        assert session.json()["expiresAt"].endswith("Z")

        created = client.post("/api/v1/jobs", json={
            "maxBudgetKrw": 1_000,
            "priority": "BALANCED",
        })

        assert created.status_code == 201
        job = created.json()
        assert job["status"] == "DRAFT"
        assert job["constraint"] == {"maxBudgetKrw": 1_000, "priority": "BALANCED"}
        assert job["executionPlan"]["priceDataType"] == "DEMO_SNAPSHOT"
        assert job["executionPlan"]["recommended"]["profileId"] == "runpod-l40s-v1"
        assert {candidate["eligibility"] for candidate in job["executionPlan"]["candidates"]} == {"ELIGIBLE"}

        fetched = client.get(f"/api/v1/jobs/{job['id']}")
        assert fetched.status_code == 200
        assert fetched.json() == job
        assert service.repository.get_job(job["id"]).selection_snapshot == job["executionPlan"]
    finally:
        app.dependency_overrides.clear()


def test_budget_filters_and_returns_no_eligible_plan(tmp_path):
    service = _service(tmp_path / "mvp.sqlite3")
    client = _client(service)
    try:
        assert client.post("/api/v1/session").status_code == 201
        response = client.post("/api/v1/jobs", json={
            "maxBudgetKrw": 449,
            "priority": "CHEAPEST",
        })

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "NO_ELIGIBLE_PLAN"
        assert service.repository.count_jobs() == 0
    finally:
        app.dependency_overrides.clear()


def test_job_is_hidden_from_other_session(tmp_path):
    service = _service(tmp_path / "mvp.sqlite3")
    owner = _client(service)
    other = TestClient(app, base_url="https://testserver")
    try:
        assert owner.post("/api/v1/session").status_code == 201
        job_id = owner.post("/api/v1/jobs", json={
            "maxBudgetKrw": 1_000,
            "priority": "CHEAPEST",
        }).json()["id"]
        assert other.post("/api/v1/session").status_code == 201

        response = other.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "JOB_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()


def test_start_is_atomic_for_session_and_global_limit(tmp_path):
    """실제 실행은 서비스 전체에 하나만 돈다. 횟수 제한은 두지 않는다."""

    repository = SQLiteMvpRepository(tmp_path / "mvp.sqlite3")
    runner = FakeJobRunner()
    service = JobApplicationService(
        repository,
        runner=runner,
        real_execution_available=True,
        verify_credential=lambda key: True,
    )
    owner = _client(service)
    other = TestClient(app, base_url="https://testserver")
    real = {"maxBudgetKrw": 1_000, "priority": "CHEAPEST", "executionMode": "REAL"}
    try:
        assert owner.post("/api/v1/session").status_code == 201
        owner.post("/api/v1/providers/runpod/credential", json={"apiKey": "rpa_valid"})
        first_job = owner.post("/api/v1/jobs", json=real).json()

        started = owner.post(f"/api/v1/jobs/{first_job['id']}/start")
        assert started.status_code == 202
        assert started.json() == {"id": first_job["id"], "status": "PROVISIONING"}
        assert repository.get_job(first_job["id"]).status.value == "PROVISIONING"
        assert runner.started_job_ids == [first_job["id"]]

        # 같은 세션이든 다른 세션이든, 실제 실행이 도는 동안에는 하나만 돈다.
        second_job = owner.post("/api/v1/jobs", json={**real, "priority": "FASTEST"}).json()
        busy = owner.post(f"/api/v1/jobs/{second_job['id']}/start")
        assert busy.status_code == 409
        assert busy.json()["error"]["code"] == "DEMO_BUSY"

        assert other.post("/api/v1/session").status_code == 201
        other.post("/api/v1/providers/runpod/credential", json={"apiKey": "rpa_valid"})
        other_job = other.post("/api/v1/jobs", json=real).json()
        demo_busy = other.post(f"/api/v1/jobs/{other_job['id']}/start")
        assert demo_busy.status_code == 409
        assert demo_busy.json()["error"]["code"] == "DEMO_BUSY"

        # 시뮬레이션은 자원을 만들지 않으므로 같은 상황에서도 막히지 않는다.
        simulated = other.post(
            "/api/v1/jobs", json={"maxBudgetKrw": 1_000, "priority": "CHEAPEST"}
        ).json()
        assert other.post(f"/api/v1/jobs/{simulated['id']}/start").status_code == 202
    finally:
        app.dependency_overrides.clear()


def test_completed_only_after_pod_termination(tmp_path):
    repository = SQLiteMvpRepository(tmp_path / "mvp.sqlite3")
    provider = FakeRunpodLifecycleProvider()
    worker = JobLifecycleWorker(repository, provider)
    service = JobApplicationService(repository, runner=FakeJobRunner())
    client = _client(service)
    try:
        assert client.post("/api/v1/session").status_code == 201
        job = client.post("/api/v1/jobs", json={
            "maxBudgetKrw": 1_000, "priority": "CHEAPEST",
        }).json()
        assert client.post(f"/api/v1/jobs/{job['id']}/start").status_code == 202

        worker.run_once(job["id"])
        pod_id = repository.get_job(job["id"]).runpod_pod_id
        provider.mark_running(pod_id)
        worker.run_once(job["id"])
        assert repository.get_job(job["id"]).status.value == "RUNNING"

        completed = client.post(f"/api/v1/internal/jobs/{job['id']}/completion", json={
            "outcome": "SUCCEEDED", "exitCode": 0, "message": "Training completed",
        })
        assert completed.status_code == 204
        assert client.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "TERMINATING"

        worker.run_once(job["id"])
        assert provider.deleted_pod_ids == [pod_id]
        assert client.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "TERMINATING"

        provider.mark_terminated(pod_id)
        worker.run_once(job["id"])
        final_job = client.get(f"/api/v1/jobs/{job['id']}").json()
        assert final_job["status"] == "COMPLETED"
        assert final_job["exitCode"] == 0
        assert final_job["completionLog"] == "Training completed"
        assert final_job["podTerminatedAt"].endswith("Z")
    finally:
        app.dependency_overrides.clear()


def test_cancel_deletes_pod_and_becomes_cancelled(tmp_path):
    repository = SQLiteMvpRepository(tmp_path / "mvp.sqlite3")
    provider = FakeRunpodLifecycleProvider()
    worker = JobLifecycleWorker(repository, provider)
    service = JobApplicationService(repository, runner=FakeJobRunner())
    client = _client(service)
    try:
        client.post("/api/v1/session")
        job = client.post("/api/v1/jobs", json={
            "maxBudgetKrw": 1_000, "priority": "CHEAPEST",
        }).json()
        client.post(f"/api/v1/jobs/{job['id']}/start")
        worker.run_once(job["id"])
        pod_id = repository.get_job(job["id"]).runpod_pod_id
        provider.mark_running(pod_id)
        worker.run_once(job["id"])

        cancelled = client.post(f"/api/v1/jobs/{job['id']}/cancel")
        assert cancelled.status_code == 202
        assert cancelled.json()["status"] == "TERMINATING"
        worker.run_once(job["id"])
        assert provider.deleted_pod_ids == [pod_id]
        provider.mark_terminated(pod_id)
        worker.run_once(job["id"])
        assert client.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "CANCELLED"
    finally:
        app.dependency_overrides.clear()


def test_timeout_deletes_pod_and_becomes_failed(tmp_path):
    repository = SQLiteMvpRepository(tmp_path / "mvp.sqlite3")
    provider = FakeRunpodLifecycleProvider()
    current_time = [utc_now()]
    worker = JobLifecycleWorker(repository, provider, clock=lambda: current_time[0])
    service = JobApplicationService(repository, runner=FakeJobRunner())
    client = _client(service)
    try:
        client.post("/api/v1/session")
        job = client.post("/api/v1/jobs", json={
            "maxBudgetKrw": 1_000, "priority": "CHEAPEST",
        }).json()
        client.post(f"/api/v1/jobs/{job['id']}/start")
        worker.run_once(job["id"])
        pod_id = repository.get_job(job["id"]).runpod_pod_id
        provider.mark_running(pod_id)
        worker.run_once(job["id"])

        current_time[0] += timedelta(minutes=11)
        assert worker.run_once(job["id"]).value == "TERMINATING"
        worker.run_once(job["id"])
        assert provider.deleted_pod_ids == [pod_id]
        provider.mark_terminated(pod_id)
        worker.run_once(job["id"])
        final_job = client.get(f"/api/v1/jobs/{job['id']}").json()
        assert final_job["status"] == "FAILED"
        assert "10분" in final_job["failureMessage"]
    finally:
        app.dependency_overrides.clear()
