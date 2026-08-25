import json

import pytest

from training_cost_optimizer.models import TrainingRequest
from training_cost_optimizer.optimizer import optimize_training_cost
from training_cost_optimizer.providers.runpod import (
    RunPodAPIError,
    RunPodGPURepository,
    build_runpod_gpu_selection,
)


def sample_transport(url: str, body: bytes, timeout: float) -> dict:
    assert "api_key=test-key" in url
    assert "gpuTypes" in json.loads(body)["query"]
    assert timeout == 15.0
    return {
        "data": {
            "gpuTypes": [
                {
                    "id": "NVIDIA GeForce RTX 4090",
                    "displayName": "RTX 4090",
                    "memoryInGb": 24,
                    "lowestPrice": {
                        "stockStatus": "High",
                        "uninterruptablePrice": 0.44,
                    },
                },
                {
                    "id": "NVIDIA H100 80GB HBM3",
                    "displayName": "H100 SXM",
                    "memoryInGb": 80,
                    "lowestPrice": {
                        "stockStatus": "Low",
                        "uninterruptablePrice": 2.69,
                    },
                },
            ]
        }
    }


def test_converts_runpod_response_to_internal_gpu_models(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")

    offers = RunPodGPURepository(transport=sample_transport).list_gpus()

    assert len(offers) == 2
    assert offers[0].name == "RTX 4090"
    assert offers[0].provider == "RunPod"
    assert offers[0].vram_gb == 24
    assert offers[0].price_per_hour == 0.44
    assert offers[0].performance_score == 1.0
    assert offers[0].source.startswith("runpod_graphql")
    assert offers[0].fetched_at is not None
    assert offers[0].provider_resource_id == "NVIDIA GeForce RTX 4090"


def test_excludes_missing_unavailable_invalid_and_unsupported_gpus(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")

    def transport(url: str, body: bytes, timeout: float) -> dict:
        return {"data": {"gpuTypes": [
            {"id": "NVIDIA GeForce RTX 4090", "displayName": "RTX 4090",
             "memoryInGb": None, "lowestPrice": {"stockStatus": "High",
             "uninterruptablePrice": 0.4}},
            {"id": "NVIDIA GeForce RTX 4090", "displayName": "RTX 4090",
             "memoryInGb": 24, "lowestPrice": {"stockStatus": "High",
             "uninterruptablePrice": None}},
            {"id": "NVIDIA GeForce RTX 4090", "displayName": "RTX 4090",
             "memoryInGb": 24, "lowestPrice": {"stockStatus": "None",
             "uninterruptablePrice": 0.4}},
            {"id": "Unknown GPU", "displayName": "Unknown",
             "memoryInGb": 24, "lowestPrice": {"stockStatus": "High",
             "uninterruptablePrice": 0.1}},
            {"id": "NVIDIA GeForce RTX 4090", "displayName": "RTX 4090",
             "memoryInGb": 24, "lowestPrice": {"stockStatus": "High",
             "uninterruptablePrice": 0}},
            {"id": "NVIDIA GeForce RTX 4090", "displayName": "RTX 4090",
             "memoryInGb": 24, "lowestPrice": {"stockStatus": "High",
             "uninterruptablePrice": -0.1}},
        ]}}

    assert RunPodGPURepository(transport=transport).list_gpus() == ()


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)

    with pytest.raises(RunPodAPIError, match="RUNPOD_API_ERROR.*not set"):
        RunPodGPURepository(transport=sample_transport).list_gpus()


def test_graphql_errors_are_not_replaced_with_mock_data(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")

    with pytest.raises(RunPodAPIError, match="RUNPOD_API_ERROR"):
        RunPodGPURepository(
            transport=lambda *_: {"errors": [{"message": "denied"}]}
        ).list_gpus()


def test_runpod_offers_feed_existing_optimizer(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    repository = RunPodGPURepository(transport=sample_transport)
    request = TrainingRequest(
        model_name="integration-model",
        required_vram_gb=24,
        estimated_base_hours=10,
    )

    result = optimize_training_cost(request, repository)

    assert result.recommended_gpu.gpu_name == "RTX 4090"
    assert result.recommended_gpu.estimated_hours == pytest.approx(10.0)
    assert result.recommended_gpu.estimated_total_cost == pytest.approx(4.4)
    assert result.recommended_gpu.provider_resource_id == "NVIDIA GeForce RTX 4090"


def test_recommended_runpod_id_flows_to_v1_pods_gpu_type_ids(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    repository = RunPodGPURepository(transport=sample_transport)
    request = TrainingRequest(
        model_name="integration-model",
        required_vram_gb=24,
        estimated_base_hours=10,
        max_budget_krw=100_000,
    )

    from training_cost_optimizer.currency import FixedExchangeRateProvider
    from training_cost_optimizer.service import OptimizationService

    result = OptimizationService(
        [repository], FixedExchangeRateProvider(1000)
    ).optimize(request)

    assert result.recommended_provider == "RunPod"
    assert result.recommended_provider_resource_id == "NVIDIA GeForce RTX 4090"
    assert build_runpod_gpu_selection(result.recommended_provider_resource_id) == {
        "gpuTypeIds": ["NVIDIA GeForce RTX 4090"]
    }


def test_runpod_offer_without_official_gpu_type_id_is_excluded(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")

    def missing_id_transport(*_):
        return {"data": {"gpuTypes": [{
            "id": None,
            "displayName": "RTX 4090",
            "memoryInGb": 24,
            "lowestPrice": {"stockStatus": "High", "uninterruptablePrice": 0.44},
        }]}}

    assert RunPodGPURepository(transport=missing_id_transport).list_gpus() == ()


@pytest.mark.parametrize("provider_resource_id", ["", "   ", None])
def test_pod_gpu_selection_rejects_missing_provider_id(provider_resource_id):
    with pytest.raises(ValueError, match="provider-supplied"):
        build_runpod_gpu_selection(provider_resource_id)
