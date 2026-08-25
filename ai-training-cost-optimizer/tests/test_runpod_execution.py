from datetime import datetime, timezone
import json

import pytest

from training_cost_optimizer.models import JobStatus, TrainingJob
from training_cost_optimizer.cli import confirm_real_runpod_creation
from training_cost_optimizer.providers.runpod_execution import (
    AlreadyProvisioned,
    BudgetTooLow,
    InvalidProviderResourceId,
    ProvisioningSafetyError,
    RunPodAPIKeyMissing,
    RunPodAuthFailed,
    RunPodExecutionProvider,
    RunPodGPUUnavailable,
    RunPodInsufficientCredit,
    RunPodProvisioningError,
    RunPodRateLimited,
)


def job(**updates) -> TrainingJob:
    now = datetime.now(timezone.utc)
    base = TrainingJob(
        id="job-1", model_name="bert-base-uncased", task_type="fine_tuning",
        training_type="lora", selected_provider="RunPod", selected_gpu="RTX 4090",
        selected_provider_resource_id="NVIDIA GeForce RTX 4090",
        recommendation_status="OK", gpu_compatible=True, gpu_available=True,
        provider_data_type="actual", estimated_gpu_cost_krw=1000,
        agent_fee_krw=150, estimated_total_charge_krw=1150,
        max_budget_krw=2000, created_at=now, updated_at=now,
    )
    return base.model_copy(update=updates)


def success_transport(url, body, headers, timeout):
    assert url == "https://rest.runpod.io/v1/pods"
    assert headers["Authorization"] == "Bearer test-key"
    assert timeout == 30.0
    payload = json.loads(body)
    assert payload["gpuTypeIds"] == ["NVIDIA GeForce RTX 4090"]
    assert payload["gpuCount"] == 1
    return 201, {
        "id": "pod-123",
        "costPerHr": "0.74",
        "adjustedCostPerHr": 0.69,
        "desiredStatus": "RUNNING",
        "image": "runpod/pytorch:test",
    }


def test_builds_official_minimum_payload_with_exact_provider_id(monkeypatch):
    monkeypatch.setenv("RUNPOD_DEFAULT_IMAGE", "runpod/pytorch:test")
    payload = RunPodExecutionProvider().build_payload(job())
    assert payload == {
        "gpuTypeIds": ["NVIDIA GeForce RTX 4090"],
        "gpuCount": 1,
        "imageName": "runpod/pytorch:test",
        "name": "training-job-job-1",
        "interruptible": False,
    }


def test_dry_run_never_calls_http_and_does_not_require_key(monkeypatch):
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    called = False
    def transport(*_):
        nonlocal called
        called = True
        raise AssertionError("HTTP must not be called")
    result = RunPodExecutionProvider(transport=transport).provision(
        job(provider_data_type="fixture")
    )
    assert result.dry_run
    assert not called
    assert result.job.status == JobStatus.PLANNED


def test_execute_requires_api_key(monkeypatch):
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    with pytest.raises(RunPodAPIKeyMissing):
        RunPodExecutionProvider().provision(job(), execute=True)


def test_budget_excess_blocks_before_http():
    with pytest.raises(BudgetTooLow):
        RunPodExecutionProvider(transport=lambda *_: pytest.fail("HTTP called")).provision(
            job(estimated_total_charge_krw=2001), execute=True
        )


def test_existing_pod_blocks_duplicate_provisioning():
    with pytest.raises(AlreadyProvisioned):
        RunPodExecutionProvider().provision(
            job(provider_resource_instance_id="existing-pod")
        )


def test_wrong_provider_is_blocked():
    with pytest.raises(ProvisioningSafetyError):
        RunPodExecutionProvider().provision(job(selected_provider="Other"))


@pytest.mark.parametrize("updates", [
    {"recommendation_status": None},
    {"gpu_compatible": False},
    {"gpu_available": False},
    {"max_budget_krw": None},
    {"estimated_total_charge_krw": None},
    {"status": JobStatus.QUEUED},
])
def test_each_pre_provision_safety_condition_fails_closed(updates):
    with pytest.raises(ProvisioningSafetyError):
        RunPodExecutionProvider().provision(job(**updates))


def test_missing_provider_gpu_id_is_blocked():
    with pytest.raises(InvalidProviderResourceId):
        RunPodExecutionProvider().provision(job(selected_provider_resource_id=None))


def test_execute_rejects_fixture_recommendation_even_with_confirmation_path():
    with pytest.raises(ProvisioningSafetyError, match="live actual"):
        RunPodExecutionProvider().provision(job(provider_data_type="fixture"), execute=True)


def test_execute_calls_mock_http_and_stores_official_response(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    result = RunPodExecutionProvider(transport=success_transport).provision(job(), execute=True)
    updated = result.job
    assert not result.dry_run
    assert updated.status == JobStatus.QUEUED
    assert updated.provider_resource_instance_id == "pod-123"
    assert updated.provider_gpu_type_id == "NVIDIA GeForce RTX 4090"
    assert updated.cost_per_hour == 0.74
    assert updated.adjusted_cost_per_hour == 0.69
    assert updated.desired_status == "RUNNING"
    assert updated.image_name == "runpod/pytorch:test"
    assert updated.provisioned_at is not None


@pytest.mark.parametrize(
    ("status", "error_type"),
    [(401, RunPodAuthFailed), (429, RunPodRateLimited), (500, RunPodProvisioningError)],
)
def test_maps_documented_http_errors(monkeypatch, status, error_type):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    with pytest.raises(error_type) as captured:
        RunPodExecutionProvider(
            transport=lambda *_: (status, {"error": "redacted"})
        ).provision(job(), execute=True)
    assert captured.value.job.status == JobStatus.PLANNED
    assert captured.value.job.provisioning_error == captured.value.code


@pytest.mark.parametrize(
    ("provider_code", "error_type"),
    [
        ("GPU_UNAVAILABLE", RunPodGPUUnavailable),
        ("INSUFFICIENT_CREDIT", RunPodInsufficientCredit),
    ],
)
def test_maps_only_explicit_provider_error_codes(monkeypatch, provider_code, error_type):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    with pytest.raises(error_type):
        RunPodExecutionProvider(
            transport=lambda *_: (400, {"errorCode": provider_code})
        ).provision(job(), execute=True)


def test_one_active_pod_limit_blocks_second_job(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    provider = RunPodExecutionProvider(transport=success_transport)
    provider.provision(job(), execute=True)
    with pytest.raises(AlreadyProvisioned):
        provider.provision(job(id="job-2"), execute=True)


def test_human_confirmation_requires_exact_runpod_text():
    assert confirm_real_runpod_creation(lambda _: "RUNPOD")
    assert not confirm_real_runpod_creation(lambda _: "runpod")
    assert not confirm_real_runpod_creation(lambda _: "yes")
