from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from training_cost_optimizer.models import GPU, TrainingRequest
from training_cost_optimizer.optimizer import NoCompatibleGPUError, optimize_training_cost
from training_cost_optimizer.repository import MockGPURepository


def test_returns_all_candidates_and_recommends_lowest_total_cost():
    request = TrainingRequest(model_name="small", required_vram_gb=20,
                              estimated_base_hours=10)

    result = optimize_training_cost(request, MockGPURepository())

    assert {item.gpu_name for item in result.candidates} == {
        "RTX 4090", "A100 40GB", "A100 80GB", "H100 80GB"
    }
    assert result.recommended_gpu.gpu_name == "A100 40GB"
    assert result.recommended_gpu.estimated_hours == pytest.approx(10 / 2.2)
    assert result.recommended_gpu.estimated_total_cost == pytest.approx((10 / 2.2) * 1.4)


def test_filters_gpus_with_insufficient_vram():
    request = TrainingRequest(model_name="large", required_vram_gb=50,
                              estimated_base_hours=12)

    result = optimize_training_cost(request, MockGPURepository())

    assert [item.gpu_name for item in result.candidates] == ["H100 80GB", "A100 80GB"]
    assert result.recommended_gpu.gpu_name == "H100 80GB"


def test_gpu_with_exact_required_vram_is_included():
    request = TrainingRequest(model_name="exact", required_vram_gb=40,
                              estimated_base_hours=5)

    result = optimize_training_cost(request, MockGPURepository())

    assert "A100 40GB" in {item.gpu_name for item in result.candidates}


def test_raises_when_no_gpu_has_enough_vram():
    request = TrainingRequest(model_name="huge", required_vram_gb=81,
                              estimated_base_hours=5)

    with pytest.raises(NoCompatibleGPUError, match="81 GB"):
        optimize_training_cost(request, MockGPURepository())


@pytest.mark.parametrize(
    ("field", "value"),
    [("required_vram_gb", 0), ("estimated_base_hours", 0)],
)
def test_request_rejects_non_positive_numbers(field: str, value: float):
    data = {"model_name": "invalid", "required_vram_gb": 1,
            "estimated_base_hours": 1}
    data[field] = value

    with pytest.raises(ValidationError):
        TrainingRequest(**data)


def test_candidate_contains_all_required_output_fields():
    request = TrainingRequest(model_name="output", required_vram_gb=24,
                              estimated_base_hours=10)
    result = optimize_training_cost(request, MockGPURepository())
    candidate = next(item for item in result.candidates if item.gpu_name == "RTX 4090")

    assert candidate.model_dump() == {
        "gpu_name": "RTX 4090",
        "provider": "MockCloudA",
        "vram_gb": 24.0,
        "price_per_hour": 0.7,
        "estimated_hours": 10.0,
        "estimated_total_cost": 7.0,
    }


class StaticGPURepository:
    def __init__(self, gpus: Sequence[GPU]) -> None:
        self._gpus = gpus

    def list_gpus(self) -> Sequence[GPU]:
        return self._gpus


def test_optimizes_total_cost_instead_of_hourly_price():
    repository = StaticGPURepository([
        GPU(name="Cheap but slow", provider="Mock", vram_gb=24,
            price_per_hour=0.5, performance_score=0.5),
        GPU(name="Expensive but fast", provider="Mock", vram_gb=24,
            price_per_hour=1.5, performance_score=2.0),
    ])
    request = TrainingRequest(model_name="cost", required_vram_gb=24,
                              estimated_base_hours=10)

    result = optimize_training_cost(request, repository)

    assert result.recommended_gpu.gpu_name == "Expensive but fast"
    assert result.recommended_gpu.estimated_total_cost == pytest.approx(7.5)

