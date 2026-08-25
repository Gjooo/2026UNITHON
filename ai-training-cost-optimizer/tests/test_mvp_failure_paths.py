from fastapi.testclient import TestClient

from training_cost_optimizer.api import app
from training_cost_optimizer.mvp.fake_provider import FakeRunpodLifecycleProvider
from training_cost_optimizer.mvp.repository import SQLiteMvpRepository
from training_cost_optimizer.mvp.router import get_mvp_service
from training_cost_optimizer.mvp.runner import FakeJobRunner, JobLifecycleWorker
from training_cost_optimizer.mvp.service import JobApplicationService


class _Harness:
    """Client, worker, and provider sharing one database, as the deployment does."""

    def __init__(self, tmp_path):
        self.repository = SQLiteMvpRepository(tmp_path / "mvp.sqlite3")
        self.provider = FakeRunpodLifecycleProvider()
        self.worker = JobLifecycleWorker(self.repository, self.provider)
        service = JobApplicationService(self.repository, runner=FakeJobRunner())
        app.dependency_overrides[get_mvp_service] = lambda: service
        self.client = TestClient(app, base_url="https://testserver")

    def start_job(self, priority: str = "CHEAPEST") -> str:
        self.client.post("/api/v1/session")
        job_id = self.client.post(
            "/api/v1/jobs", json={"maxBudgetKrw": 1_000, "priority": priority}
        ).json()["id"]
        assert self.client.post(f"/api/v1/jobs/{job_id}/start").status_code == 202
        return job_id

    def status(self, job_id: str) -> str:
        return self.client.get(f"/api/v1/jobs/{job_id}").json()["status"]


def test_failed_callback_deletes_pod_and_becomes_failed(tmp_path):
    harness = _Harness(tmp_path)
    try:
        job_id = harness.start_job()
        harness.worker.run_once(job_id)
        pod_id = harness.repository.get_job(job_id).runpod_pod_id
        harness.provider.mark_running(pod_id)
        harness.worker.run_once(job_id)

        callback = harness.client.post(
            f"/api/v1/internal/jobs/{job_id}/completion",
            json={"outcome": "FAILED", "exitCode": 1, "message": "CUDA out of memory"},
        )

        assert callback.status_code == 204
        assert harness.status(job_id) == "TERMINATING"

        harness.worker.run_once(job_id)
        assert harness.provider.deleted_pod_ids == [pod_id]
        assert harness.status(job_id) == "TERMINATING"

        harness.provider.mark_terminated(pod_id)
        harness.worker.run_once(job_id)
        job = harness.client.get(f"/api/v1/jobs/{job_id}").json()
        assert job["status"] == "FAILED"
        assert job["exitCode"] == 1
        assert job["failureMessage"] == "CUDA out of memory"
        assert job["podTerminatedAt"].endswith("Z")
    finally:
        app.dependency_overrides.clear()


def test_pod_creation_error_fails_without_a_delete_request(tmp_path):
    harness = _Harness(tmp_path)
    try:
        job_id = harness.start_job()
        harness.provider.create_error = RuntimeError("Runpod create request failed with HTTP 400")

        assert harness.worker.run_once(job_id).value == "FAILED"

        job = harness.client.get(f"/api/v1/jobs/{job_id}").json()
        assert job["status"] == "FAILED"
        assert job["failureMessage"] == "Pod 생성에 실패했습니다."
        assert harness.repository.get_job(job_id).runpod_pod_id is None
        # There is no provider resource yet, so cleanup must not be attempted.
        assert harness.provider.deleted_pod_ids == []
    finally:
        app.dependency_overrides.clear()


def test_pod_provisioning_failure_deletes_pod_and_becomes_failed(tmp_path):
    harness = _Harness(tmp_path)
    try:
        job_id = harness.start_job()
        harness.worker.run_once(job_id)
        pod_id = harness.repository.get_job(job_id).runpod_pod_id
        harness.provider.mark_failed(pod_id)

        assert harness.worker.run_once(job_id).value == "TERMINATING"

        harness.worker.run_once(job_id)
        assert harness.provider.deleted_pod_ids == [pod_id]

        harness.provider.mark_terminated(pod_id)
        harness.worker.run_once(job_id)
        job = harness.client.get(f"/api/v1/jobs/{job_id}").json()
        assert job["status"] == "FAILED"
        assert job["failureMessage"] == "Pod provisioning에 실패했습니다."
    finally:
        app.dependency_overrides.clear()


def test_duplicate_completion_callback_is_rejected(tmp_path):
    harness = _Harness(tmp_path)
    try:
        job_id = harness.start_job()
        harness.worker.run_once(job_id)
        pod_id = harness.repository.get_job(job_id).runpod_pod_id
        harness.provider.mark_running(pod_id)
        harness.worker.run_once(job_id)

        payload = {"outcome": "SUCCEEDED", "exitCode": 0, "message": "Training completed"}
        assert harness.client.post(
            f"/api/v1/internal/jobs/{job_id}/completion", json=payload
        ).status_code == 204

        # The callback is valid exactly once, while the job is RUNNING.
        duplicate = harness.client.post(f"/api/v1/internal/jobs/{job_id}/completion", json=payload)
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "INVALID_JOB_STATE"

        job = harness.repository.get_job(job_id)
        assert job.completion_log == "Training completed"
        assert job.requested_final_status.value == "COMPLETED"
    finally:
        app.dependency_overrides.clear()


def test_completion_callback_for_unknown_job_is_not_found(tmp_path):
    harness = _Harness(tmp_path)
    try:
        response = harness.client.post(
            "/api/v1/internal/jobs/00000000-0000-0000-0000-000000000000/completion",
            json={"outcome": "SUCCEEDED", "exitCode": 0, "message": "Training completed"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "JOB_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()


def test_cancel_is_rejected_after_the_job_reached_a_final_status(tmp_path):
    harness = _Harness(tmp_path)
    try:
        job_id = harness.start_job()
        harness.provider.create_error = RuntimeError("Runpod create request failed with HTTP 400")
        harness.worker.run_once(job_id)

        cancelled = harness.client.post(f"/api/v1/jobs/{job_id}/cancel")
        assert cancelled.status_code == 409
        assert cancelled.json()["error"]["code"] == "INVALID_JOB_STATE"
    finally:
        app.dependency_overrides.clear()
