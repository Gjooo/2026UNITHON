import io
import logging

import pytest
from fastapi.testclient import TestClient

from training_cost_optimizer.api import app, frontend_origins
from training_cost_optimizer.mvp import smoke
from training_cost_optimizer.mvp.config import (
    GPU_EXECUTION_PROFILES,
    MvpConfigError,
    get_settings,
)
from training_cost_optimizer.mvp.fake_provider import FakeRunpodLifecycleProvider
from training_cost_optimizer.mvp.repository import SQLiteMvpRepository
from training_cost_optimizer.mvp.router import get_mvp_service
from training_cost_optimizer.mvp.runner import FakeJobRunner, JobLifecycleWorker
from training_cost_optimizer.mvp.service import JobApplicationService
from training_cost_optimizer.mvp.simulated_provider import SimulatedRunpodLifecycleProvider
from training_cost_optimizer.providers.runpod_lifecycle import (
    PodStatus,
    RunpodLifecycleError,
    RunpodRestLifecycleProvider,
)


DOCUMENTED_CANDIDATE_KEYS = {
    "profileId",
    "provider",
    "gpuType",
    "estimatedRuntimeMinutes",
    "estimatedGpuCostKrw",
    "eligibility",
    "reason",
}


def _server_only_values() -> set[str]:
    """Values that must never leave the server.

    ``gpu_type`` is a documented display field, so a ``runpod_gpu_type_id``
    that happens to equal it (NVIDIA L40S) is not a leak and is skipped.
    """

    values: set[str] = set()
    for profile in GPU_EXECUTION_PROFILES:
        values.update({profile.image_name, profile.start_command})
        if profile.runpod_gpu_type_id != profile.gpu_type:
            values.add(profile.runpod_gpu_type_id)
    return values


def _spec_transport(offered_ids=None):
    """Serve a Runpod OpenAPI spec whose Pod-create schema lists the given GPU types."""

    if offered_ids is None:
        offered_ids = [profile.runpod_gpu_type_id for profile in GPU_EXECUTION_PROFILES]

    def transport(method, url, body, headers, timeout):
        assert method == "GET" and url.endswith("openapi.json")
        return 200, {
            "paths": {"/pods": {"post": {"requestBody": {"content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/PodCreate"}}}}}}},
            "components": {"schemas": {"PodCreate": {"properties": {
                "gpuTypeIds": {"items": {"enum": list(offered_ids)}}}}}},
        }

    return transport


class _AutoAdvancingProvider(FakeRunpodLifecycleProvider):
    """Reaches RUNNING after one poll and TERMINATED after deletion."""

    def get_pod_status(self, pod_id: str) -> PodStatus:
        if pod_id in self.deleted_pod_ids:
            self.mark_terminated(pod_id)
        elif self.pod_statuses[pod_id] is PodStatus.PROVISIONING:
            self.mark_running(pod_id)
        return super().get_pod_status(pod_id)


def test_max_runtime_minutes_is_read_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("MVP_MAX_RUNTIME_MINUTES", "4")
    assert get_settings().max_runtime_minutes == 4

    service = JobApplicationService(
        SQLiteMvpRepository(tmp_path / "mvp.sqlite3"),
        runner=FakeJobRunner(),
        max_runtime_minutes=4,
    )
    app.dependency_overrides[get_mvp_service] = lambda: service
    try:
        client = TestClient(app, base_url="https://testserver")
        client.post("/api/v1/session")
        job = client.post(
            "/api/v1/jobs", json={"maxBudgetKrw": 1_000, "priority": "CHEAPEST"}
        ).json()
        assert job["scenario"]["maxRuntimeMinutes"] == 4
    finally:
        app.dependency_overrides.clear()


def test_default_max_runtime_minutes_is_ten(monkeypatch):
    monkeypatch.delenv("MVP_MAX_RUNTIME_MINUTES", raising=False)
    assert get_settings().max_runtime_minutes == 10


@pytest.mark.parametrize("value", ["0", "-1", "ten", "10.5"])
def test_invalid_runtime_configuration_is_rejected(monkeypatch, value):
    monkeypatch.setenv("MVP_MAX_RUNTIME_MINUTES", value)
    with pytest.raises(MvpConfigError):
        get_settings()


def test_unknown_provider_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("MVP_PROVIDER_MODE", "aws")
    with pytest.raises(MvpConfigError):
        get_settings()


def test_job_contract_and_logs_never_expose_provider_secrets(tmp_path, caplog):
    repository = SQLiteMvpRepository(tmp_path / "mvp.sqlite3")
    provider = _AutoAdvancingProvider()
    worker = JobLifecycleWorker(repository, provider)
    service = JobApplicationService(repository, runner=FakeJobRunner())
    app.dependency_overrides[get_mvp_service] = lambda: service
    try:
        client = TestClient(app, base_url="https://testserver")
        with caplog.at_level(logging.DEBUG, logger="training_cost_optimizer"):
            client.post("/api/v1/session")
            job_id = client.post(
                "/api/v1/jobs", json={"maxBudgetKrw": 1_000, "priority": "CHEAPEST"}
            ).json()["id"]
            client.post(f"/api/v1/jobs/{job_id}/start")
            worker.run_once(job_id)
            worker.run_once(job_id)
            client.post(
                f"/api/v1/internal/jobs/{job_id}/completion",
                json={"outcome": "SUCCEEDED", "exitCode": 0, "message": "Training completed"},
            )
            worker.run_once(job_id)
            body = client.get(f"/api/v1/jobs/{job_id}").text

        job = client.get(f"/api/v1/jobs/{job_id}").json()
        assert job["status"] == "COMPLETED"
        for secret in _server_only_values():
            assert secret not in body
            assert secret not in caplog.text
        # The response carries only the documented execution contract.
        candidates = job["executionPlan"]["candidates"] + [job["executionPlan"]["recommended"]]
        for candidate in candidates:
            assert set(candidate) <= DOCUMENTED_CANDIDATE_KEYS
        # The lifecycle still has to be observable for operations.
        assert f"job={job_id}" in caplog.text
        assert "pod=" in caplog.text
    finally:
        app.dependency_overrides.clear()


def test_runpod_errors_and_logs_never_include_the_api_key(caplog):
    def transport(method, url, body, headers, timeout):
        return 401, {"error": "unauthorized"}

    provider = RunpodRestLifecycleProvider(
        api_key="super-secret-key",
        callback_base_url="https://api.example.test",
        transport=transport,
    )
    with caplog.at_level(logging.DEBUG, logger="training_cost_optimizer"):
        with pytest.raises(RunpodLifecycleError) as error:
            provider.create_pod(GPU_EXECUTION_PROFILES[0], "job-123")

    assert "super-secret-key" not in str(error.value)
    assert "super-secret-key" not in caplog.text
    for secret in _server_only_values():
        assert secret not in caplog.text


def test_frontend_origins_never_allow_a_wildcard(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGINS", "*, https://unwork.example")
    assert frontend_origins() == ["https://unwork.example"]

    monkeypatch.setenv("FRONTEND_ORIGINS", "*")
    assert "*" not in frontend_origins()


def test_smoke_check_env_reports_missing_configuration(monkeypatch):
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    monkeypatch.delenv("BACKEND_PUBLIC_BASE_URL", raising=False)
    output = io.StringIO()

    exit_code = smoke.main(["--check-env"], stdout=output, transport=_spec_transport())

    assert exit_code == 1
    assert "RUNPOD_API_KEY" in output.getvalue()
    assert "BACKEND_PUBLIC_BASE_URL" in output.getvalue()


def test_smoke_check_env_passes_with_valid_configuration(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "super-secret-key")
    monkeypatch.setenv("BACKEND_PUBLIC_BASE_URL", "https://api.example.test")
    output = io.StringIO()

    exit_code = smoke.main(["--check-env"], stdout=output, transport=_spec_transport())

    assert exit_code == 0
    assert "super-secret-key" not in output.getvalue()


def test_smoke_run_requires_explicit_confirmation(monkeypatch):
    provider = _AutoAdvancingProvider()
    output = io.StringIO()

    exit_code = smoke.main([], provider_factory=lambda: provider, stdout=output, sleep=lambda _: None)

    assert exit_code == 2
    assert provider.created_pods == []
    assert "--confirm RUNPOD" in output.getvalue()


def test_smoke_run_creates_and_deletes_every_profile(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "super-secret-key")
    monkeypatch.setenv("BACKEND_PUBLIC_BASE_URL", "https://api.example.test")
    provider = _AutoAdvancingProvider()
    output = io.StringIO()

    exit_code = smoke.main(
        ["--confirm", "RUNPOD"],
        provider_factory=lambda: provider,
        stdout=output,
        sleep=lambda _: None,
        transport=_spec_transport(),
    )

    assert exit_code == 0
    created_profiles = [job_id for _, job_id in provider.created_pods]
    assert len(created_profiles) == len(GPU_EXECUTION_PROFILES)
    assert provider.deleted_pod_ids == [pod_id for pod_id, _ in provider.created_pods]
    assert all(
        provider.pod_statuses[pod_id] is PodStatus.TERMINATED for pod_id, _ in provider.created_pods
    )
    report = output.getvalue()
    for profile in GPU_EXECUTION_PROFILES:
        assert profile.id in report
    for secret in _server_only_values():
        assert secret not in report


def test_smoke_run_deletes_the_pod_even_when_it_never_starts(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "super-secret-key")
    monkeypatch.setenv("BACKEND_PUBLIC_BASE_URL", "https://api.example.test")
    provider = FakeRunpodLifecycleProvider()  # stays PROVISIONING forever
    output = io.StringIO()

    exit_code = smoke.main(
        ["--confirm", "RUNPOD", "--profile", GPU_EXECUTION_PROFILES[0].id, "--timeout-seconds", "0"],
        provider_factory=lambda: provider,
        stdout=output,
        sleep=lambda _: None,
        transport=_spec_transport(),
    )

    assert exit_code == 1
    assert len(provider.created_pods) == 1
    assert provider.deleted_pod_ids == [provider.created_pods[0][0]]
    assert "TIMEOUT" in output.getvalue().upper()


def test_smoke_run_reports_a_create_failure_without_leaking_details(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "super-secret-key")
    monkeypatch.setenv("BACKEND_PUBLIC_BASE_URL", "https://api.example.test")
    provider = FakeRunpodLifecycleProvider()
    provider.create_error = RunpodLifecycleError("Runpod authentication failed")
    output = io.StringIO()

    exit_code = smoke.main(
        ["--confirm", "RUNPOD", "--profile", GPU_EXECUTION_PROFILES[0].id],
        provider_factory=lambda: provider,
        stdout=output,
        sleep=lambda _: None,
        transport=_spec_transport(),
    )

    assert exit_code == 1
    assert provider.deleted_pod_ids == []
    assert "Runpod authentication failed" in output.getvalue()


def test_startup_fails_fast_when_runpod_mode_is_misconfigured(monkeypatch):
    """실제 실행 배포에는 공개 callback 주소가 반드시 있어야 한다.

    실행에 쓰는 키는 사용자가 연결하므로 서버 키는 요구하지 않는다.
    """

    monkeypatch.setenv("MVP_PROVIDER_MODE", "runpod")
    monkeypatch.delenv("BACKEND_PUBLIC_BASE_URL", raising=False)

    with pytest.raises(RunpodLifecycleError):
        with TestClient(app):
            pass

    # 팀 키가 없어도 callback 주소만 있으면 기동한다.
    monkeypatch.setenv("BACKEND_PUBLIC_BASE_URL", "https://api.example.test")
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def test_startup_succeeds_in_the_default_fake_mode(monkeypatch, tmp_path):
    monkeypatch.delenv("MVP_PROVIDER_MODE", raising=False)
    monkeypatch.setenv("MVP_DATABASE_PATH", str(tmp_path / "mvp.sqlite3"))

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def test_simulated_provider_starts_after_a_delay_and_terminates_on_request():
    now = [0.0]
    provider = SimulatedRunpodLifecycleProvider(provisioning_seconds=10, clock=lambda: now[0])
    pod_id = provider.create_pod(GPU_EXECUTION_PROFILES[0], "job-123")

    assert provider.get_pod_status(pod_id) is PodStatus.PROVISIONING
    now[0] = 10.0
    assert provider.get_pod_status(pod_id) is PodStatus.RUNNING

    provider.delete_pod(pod_id)
    assert provider.get_pod_status(pod_id) is PodStatus.TERMINATED


def test_fake_provider_mode_never_reaches_the_runpod_client(tmp_path, monkeypatch):
    monkeypatch.setenv("MVP_PROVIDER_MODE", "fake")
    monkeypatch.setenv("MVP_DATABASE_PATH", str(tmp_path / "mvp.sqlite3"))
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)

    service = get_mvp_service()

    # 두 모드 모두 시뮬레이터로 연결된다. Runpod 자격증명이 없는 배포에서
    # 실제 실행을 요청해도 Pod 가 만들어지지 않는다.
    assert not service.real_execution_available
    assert all(
        isinstance(provider, SimulatedRunpodLifecycleProvider)
        for provider in service.runner.worker.providers.values()
    )


def test_session_cookie_is_secure_unless_local_http_is_opted_into(monkeypatch, tmp_path):
    service = JobApplicationService(
        SQLiteMvpRepository(tmp_path / "mvp.sqlite3"), runner=FakeJobRunner()
    )
    app.dependency_overrides[get_mvp_service] = lambda: service
    try:
        client = TestClient(app, base_url="https://testserver")

        monkeypatch.delenv("MVP_COOKIE_SECURE", raising=False)
        assert "Secure" in client.post("/api/v1/session").headers["set-cookie"]

        monkeypatch.setenv("MVP_COOKIE_SECURE", "false")
        local = client.post("/api/v1/session").headers["set-cookie"]
        assert "Secure" not in local
        assert "HttpOnly" in local and "SameSite=lax" in local

        monkeypatch.setenv("MVP_COOKIE_SECURE", "maybe")
        with pytest.raises(MvpConfigError):
            get_settings()
    finally:
        app.dependency_overrides.clear()


def test_check_env_rejects_a_profile_runpod_does_not_offer(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "super-secret-key")
    monkeypatch.setenv("BACKEND_PUBLIC_BASE_URL", "https://api.example.test")
    output = io.StringIO()
    # Runpod offers every profile except the last one.
    offered = [p.runpod_gpu_type_id for p in GPU_EXECUTION_PROFILES[:-1]]

    exit_code = smoke.main(["--check-env"], stdout=output, transport=_spec_transport(offered))

    report = output.getvalue()
    assert exit_code == 1
    assert GPU_EXECUTION_PROFILES[-1].id in report
    for secret in _server_only_values():
        assert secret not in report


def test_an_unoffered_profile_blocks_the_billable_run(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "super-secret-key")
    monkeypatch.setenv("BACKEND_PUBLIC_BASE_URL", "https://api.example.test")
    provider = _AutoAdvancingProvider()
    output = io.StringIO()

    exit_code = smoke.main(
        ["--confirm", "RUNPOD"],
        provider_factory=lambda: provider,
        stdout=output,
        sleep=lambda _: None,
        transport=_spec_transport([]),
    )

    assert exit_code == 1
    assert provider.created_pods == []
    assert "Refusing to create Pods" in output.getvalue()


def test_unconfirmed_run_makes_no_network_call(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "super-secret-key")

    def forbidden(*args, **kwargs):
        raise AssertionError("an unconfirmed run must not call Runpod")

    assert smoke.main([], stdout=io.StringIO(), transport=forbidden) == 2


def test_a_broken_spec_response_is_reported_not_raised(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "super-secret-key")
    monkeypatch.setenv("BACKEND_PUBLIC_BASE_URL", "https://api.example.test")
    output = io.StringIO()

    exit_code = smoke.main(
        ["--check-env"], stdout=output, transport=lambda *a: (500, {})
    )

    assert exit_code == 1
    assert "500" in output.getvalue()


def test_session_response_reports_the_remaining_execution_allowance(tmp_path):
    repository = SQLiteMvpRepository(tmp_path / "mvp.sqlite3")
    service = JobApplicationService(repository, runner=FakeJobRunner())
    app.dependency_overrides[get_mvp_service] = lambda: service
    try:
        client = TestClient(app, base_url="https://testserver")
        assert client.post("/api/v1/session").json()["executionAllowance"] == {"used": 0, "limit": 1}

        job = client.post(
            "/api/v1/jobs", json={"maxBudgetKrw": 1_000, "priority": "CHEAPEST"}
        ).json()
        client.post(f"/api/v1/jobs/{job['id']}/start")

        # 실행을 승인한 뒤에는 화면이 남은 횟수 0을 그대로 안내할 수 있다.
        assert client.post("/api/v1/session").json()["executionAllowance"] == {"used": 1, "limit": 1}
    finally:
        app.dependency_overrides.clear()


def test_user_facing_messages_avoid_demo_and_infrastructure_words(tmp_path):
    """사용자에게 나가는 문구에 데모 단계 표현과 인프라 용어가 없어야 한다."""

    from training_cost_optimizer.mvp.config import ESTIMATE_DISCLAIMER
    from training_cost_optimizer.mvp.recommendation import ProfileRecommendationService

    repository = SQLiteMvpRepository(tmp_path / "mvp.sqlite3")
    provider = FakeRunpodLifecycleProvider()
    provider.create_error = RunpodLifecycleError("boom")
    worker = JobLifecycleWorker(repository, provider)
    service = JobApplicationService(repository, runner=FakeJobRunner())
    app.dependency_overrides[get_mvp_service] = lambda: service
    banned = ("데모", "MVP", "Pod", "provisioning", "callback", "Draft")
    try:
        client = TestClient(app, base_url="https://testserver")
        client.post("/api/v1/session")
        messages = [ESTIMATE_DISCLAIMER]
        messages.append(
            client.post("/api/v1/jobs", json={"maxBudgetKrw": 1, "priority": "CHEAPEST"})
            .json()["error"]["message"]
        )
        job = client.post(
            "/api/v1/jobs", json={"maxBudgetKrw": 1_000, "priority": "CHEAPEST"}
        ).json()
        messages.append(client.get("/api/v1/jobs/unknown-id").json()["error"]["message"])
        client.post(f"/api/v1/jobs/{job['id']}/start")
        worker.run_once(job["id"])
        messages.append(client.get(f"/api/v1/jobs/{job['id']}").json()["failureMessage"])
        messages.append(client.post(f"/api/v1/jobs/{job['id']}/cancel").json()["error"]["message"])
        for reason in [
            ProfileRecommendationService().recommend(max_budget_krw=1_000, priority=p)
            .selection_snapshot["recommended"]["reason"]
            for p in ("CHEAPEST", "BALANCED", "FASTEST")
        ]:
            messages.append(reason)

        for message in messages:
            assert message
            for word in banned:
                assert word not in message, f"{word!r} in {message!r}"
    finally:
        app.dependency_overrides.clear()


def test_training_image_and_command_can_be_overridden(monkeypatch):
    """레지스트리 태그가 정해지기 전에도 배포 환경에서 이미지를 바꿀 수 있어야 한다."""

    from training_cost_optimizer.mvp.config import profile_for_id

    base = GPU_EXECUTION_PROFILES[0]
    monkeypatch.delenv("MVP_TRAINING_IMAGE", raising=False)
    monkeypatch.delenv("MVP_TRAINING_COMMAND", raising=False)
    assert profile_for_id(base.id).image_name == base.image_name

    monkeypatch.setenv("MVP_TRAINING_IMAGE", "registry.example/unwork-sd15-lora:7")
    monkeypatch.setenv("MVP_TRAINING_COMMAND", "sleep 60")
    overridden = profile_for_id(base.id)

    assert overridden.image_name == "registry.example/unwork-sd15-lora:7"
    assert overridden.start_command == "sleep 60"
    # 비교·추천에 쓰이는 값은 그대로여야 한다.
    assert overridden.estimated_gpu_cost_krw == base.estimated_gpu_cost_krw
    assert overridden.runpod_gpu_type_id == base.runpod_gpu_type_id


def test_cookie_samesite_supports_a_cross_site_frontend(monkeypatch, tmp_path):
    """다른 도메인에 배포된 프런트엔드는 SameSite=None 이어야 쿠키를 받는다."""

    service = JobApplicationService(
        SQLiteMvpRepository(tmp_path / "mvp.sqlite3"), runner=FakeJobRunner()
    )
    app.dependency_overrides[get_mvp_service] = lambda: service
    try:
        client = TestClient(app, base_url="https://testserver")

        monkeypatch.delenv("MVP_COOKIE_SAMESITE", raising=False)
        assert "SameSite=lax" in client.post("/api/v1/session").headers["set-cookie"]

        monkeypatch.setenv("MVP_COOKIE_SAMESITE", "none")
        cross_site = client.post("/api/v1/session").headers["set-cookie"]
        assert "SameSite=none" in cross_site
        assert "Secure" in cross_site

        # None 쿠키는 Secure 없이는 브라우저가 버린다. 조용히 깨지느니 기동에서 막는다.
        monkeypatch.setenv("MVP_COOKIE_SECURE", "false")
        with pytest.raises(MvpConfigError):
            get_settings()

        monkeypatch.setenv("MVP_COOKIE_SAMESITE", "diagonal")
        with pytest.raises(MvpConfigError):
            get_settings()
    finally:
        app.dependency_overrides.clear()


def test_execution_mode_is_chosen_per_job(tmp_path):
    """시연자가 작업마다 시뮬레이터와 실제 실행을 고른다."""

    from training_cost_optimizer.mvp.domain import ExecutionMode

    repository = SQLiteMvpRepository(tmp_path / "mvp.sqlite3")
    simulated = FakeRunpodLifecycleProvider()
    real = FakeRunpodLifecycleProvider()
    worker = JobLifecycleWorker(
        repository, {ExecutionMode.SIMULATED: simulated, ExecutionMode.REAL: real}
    )
    service = JobApplicationService(
        repository,
        runner=FakeJobRunner(),
        real_execution_available=True,
        verify_credential=lambda key: True,
    )
    app.dependency_overrides[get_mvp_service] = lambda: service
    try:
        client = TestClient(app, base_url="https://testserver")
        assert client.post("/api/v1/session").json()["realExecutionAvailable"] is True
        assert client.post(
            "/api/v1/providers/runpod/credential", json={"apiKey": "rpa_valid"}
        ).status_code == 204

        job = client.post(
            "/api/v1/jobs",
            json={"maxBudgetKrw": 1_000, "priority": "CHEAPEST", "executionMode": "REAL"},
        ).json()
        assert job["executionMode"] == "REAL"

        client.post(f"/api/v1/jobs/{job['id']}/start")
        worker.run_once(job["id"])

        # 실제 모드 작업은 실제 Provider 로만 간다.
        assert len(real.created_pods) == 1
        assert simulated.created_pods == []
    finally:
        app.dependency_overrides.clear()


def test_execution_mode_defaults_to_the_simulator(tmp_path):
    service = JobApplicationService(
        SQLiteMvpRepository(tmp_path / "mvp.sqlite3"), runner=FakeJobRunner()
    )
    app.dependency_overrides[get_mvp_service] = lambda: service
    try:
        client = TestClient(app, base_url="https://testserver")
        session = client.post("/api/v1/session").json()
        assert session["realExecutionAvailable"] is False

        job = client.post(
            "/api/v1/jobs", json={"maxBudgetKrw": 1_000, "priority": "CHEAPEST"}
        ).json()
        assert job["executionMode"] == "SIMULATED"
    finally:
        app.dependency_overrides.clear()


def test_real_execution_is_refused_where_runpod_is_not_configured(tmp_path):
    """Runpod 설정이 없는 배포는 실제 실행 요청을 만들기 전에 거절한다."""

    service = JobApplicationService(
        SQLiteMvpRepository(tmp_path / "mvp.sqlite3"), runner=FakeJobRunner()
    )
    app.dependency_overrides[get_mvp_service] = lambda: service
    try:
        client = TestClient(app, base_url="https://testserver")
        client.post("/api/v1/session")
        response = client.post(
            "/api/v1/jobs",
            json={"maxBudgetKrw": 1_000, "priority": "CHEAPEST", "executionMode": "REAL"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "REAL_EXECUTION_UNAVAILABLE"
        assert service.repository.count_jobs() == 0
    finally:
        app.dependency_overrides.clear()


def _byok_service(tmp_path, *, valid=True, **kwargs):
    return JobApplicationService(
        SQLiteMvpRepository(tmp_path / "mvp.sqlite3"),
        runner=FakeJobRunner(),
        real_execution_available=True,
        verify_credential=(lambda key: valid),
        **kwargs,
    )


def test_a_key_is_verified_against_runpod_before_it_is_accepted(tmp_path):
    """형식만 보고 저장하면 사용자는 승인 버튼을 누른 뒤에야 키가 틀린 걸 안다."""

    service = _byok_service(tmp_path, valid=False)
    app.dependency_overrides[get_mvp_service] = lambda: service
    try:
        client = TestClient(app, base_url="https://testserver")
        client.post("/api/v1/session")

        rejected = client.post(
            "/api/v1/providers/runpod/credential", json={"apiKey": "rpa_wrong"}
        )
        assert rejected.status_code == 401
        assert rejected.json()["error"]["code"] == "INVALID_PROVIDER_CREDENTIAL"
        assert client.get("/api/v1/providers").json()["providers"][0][
            "connectionStatus"
        ] == "NOT_CONNECTED"
    finally:
        app.dependency_overrides.clear()


def test_a_connected_key_is_never_returned(tmp_path):
    service = _byok_service(tmp_path)
    app.dependency_overrides[get_mvp_service] = lambda: service
    try:
        client = TestClient(app, base_url="https://testserver")
        client.post("/api/v1/session")
        secret = "rpa_super_secret_value"
        assert client.post(
            "/api/v1/providers/runpod/credential", json={"apiKey": secret}
        ).status_code == 204

        listed = client.get("/api/v1/providers")
        assert secret not in listed.text
        provider = listed.json()["providers"][0]
        assert provider["connectionStatus"] == "CONNECTED"
        assert provider["connectedAt"].endswith("Z")

        # 연결을 끊으면 즉시 사라진다.
        assert client.delete("/api/v1/providers/runpod/credential").status_code == 204
        assert client.get("/api/v1/providers").json()["providers"][0][
            "connectionStatus"
        ] == "NOT_CONNECTED"
    finally:
        app.dependency_overrides.clear()


def test_real_execution_needs_a_connected_key_and_never_falls_back(tmp_path):
    """팀 키로 대신 실행하지 않는다. 화면이 '당신의 계정'이라 말하면 사실이어야 한다."""

    service = _byok_service(tmp_path)
    app.dependency_overrides[get_mvp_service] = lambda: service
    try:
        client = TestClient(app, base_url="https://testserver")
        client.post("/api/v1/session")
        job = client.post(
            "/api/v1/jobs",
            json={"maxBudgetKrw": 1_000, "priority": "CHEAPEST", "executionMode": "REAL"},
        ).json()

        refused = client.post(f"/api/v1/jobs/{job['id']}/start")
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "PROVIDER_NOT_CONNECTED"
        assert service.repository.get_job(job["id"]).status.value == "DRAFT"

        client.post("/api/v1/providers/runpod/credential", json={"apiKey": "rpa_valid"})
        assert client.post(f"/api/v1/jobs/{job['id']}/start").status_code == 202
    finally:
        app.dependency_overrides.clear()


def test_the_simulator_never_needs_a_key(tmp_path):
    service = _byok_service(tmp_path)
    app.dependency_overrides[get_mvp_service] = lambda: service
    try:
        client = TestClient(app, base_url="https://testserver")
        client.post("/api/v1/session")
        job = client.post(
            "/api/v1/jobs", json={"maxBudgetKrw": 1_000, "priority": "CHEAPEST"}
        ).json()
        assert client.post(f"/api/v1/jobs/{job['id']}/start").status_code == 202
    finally:
        app.dependency_overrides.clear()


def test_one_session_cannot_use_another_sessions_key(tmp_path):
    service = _byok_service(tmp_path)
    app.dependency_overrides[get_mvp_service] = lambda: service
    try:
        owner = TestClient(app, base_url="https://testserver")
        other = TestClient(app, base_url="https://testserver")
        owner.post("/api/v1/session")
        owner.post("/api/v1/providers/runpod/credential", json={"apiKey": "rpa_valid"})
        other.post("/api/v1/session")

        assert other.get("/api/v1/providers").json()["providers"][0][
            "connectionStatus"
        ] == "NOT_CONNECTED"
        job = other.post(
            "/api/v1/jobs",
            json={"maxBudgetKrw": 1_000, "priority": "CHEAPEST", "executionMode": "REAL"},
        ).json()
        assert other.post(f"/api/v1/jobs/{job['id']}/start").json()["error"][
            "code"
        ] == "PROVIDER_NOT_CONNECTED"
    finally:
        app.dependency_overrides.clear()
