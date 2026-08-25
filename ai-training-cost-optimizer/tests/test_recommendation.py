import pytest

from training_cost_optimizer.analysis import analyze_workload
from training_cost_optimizer.currency import FixedExchangeRateProvider
from training_cost_optimizer.models import GPU, TrainingRequest
from training_cost_optimizer.recommendation import recommend_gpu
from training_cost_optimizer.service import OptimizationService


def gpu(name: str, provider: str, vram: float, price: float, performance: float,
        *, data_type: str = "actual", provider_resource_id: str | None = None) -> GPU:
    return GPU(
        name=name, provider=provider, vram_gb=vram, price_per_hour=price,
        performance_score=performance, source=f"{provider}_official_api",
        price_data_type=data_type,
        provider_resource_id=provider_resource_id,
    )


def request(*, budget: float = 10_000, vram: float = 20, hours: float = 10) -> TrainingRequest:
    return TrainingRequest(
        model_name="test", max_budget_krw=budget,
        required_vram_gb=vram, estimated_base_hours=hours,
    )


def recommend(req: TrainingRequest, offers: list[GPU]):
    return recommend_gpu(req, analyze_workload(req), offers, 1.0)


def test_excludes_gpu_below_required_vram():
    result = recommend(request(vram=24), [
        gpu("too-small", "A", 16, 1, 1),
        gpu("fits", "B", 24, 2, 1),
    ])
    assert [item.gpu_name for item in result.candidates] == ["fits"]


def test_recommends_job_cost_not_lowest_hourly_price():
    result = recommend(request(), [
        gpu("GPU A", "A", 24, 500, 1),
        gpu("GPU B", "B", 24, 1000, 10 / 3),
    ])
    assert result.recommended_gpu == "GPU B"
    assert result.estimated_total_cost_krw == pytest.approx(3000)
    assert "higher hourly price" in result.recommendation_reason


def test_selects_lowest_completion_cost_among_multiple_affordable_candidates():
    result = recommend(request(budget=8_000), [
        gpu("cost-7000", "A", 24, 700, 1),
        gpu("cost-4000", "B", 24, 800, 2),
        gpu("cost-6000", "C", 24, 600, 1),
    ])
    assert result.status == "OK"
    assert result.recommended_gpu == "cost-4000"


def test_budget_too_low_returns_minimum_budget_and_shortfall():
    result = recommend(request(budget=3_000), [
        gpu("minimum", "A", 24, 500, 1),
        gpu("other", "B", 24, 800, 1),
    ])
    assert result.status == "BUDGET_TOO_LOW"
    assert result.recommended_gpu is None
    assert result.minimum_required_budget_krw == 5_750
    assert result.budget_shortfall_krw == 2_750
    assert result.cheapest_option.gpu_name == "minimum"


class StaticRepository:
    def __init__(self, offers):
        self.offers = offers
    def list_gpus(self):
        return self.offers


class FailedRepository:
    def list_gpus(self):
        raise RuntimeError("PROVIDER_FAILED")


def test_one_provider_failure_still_uses_another_provider():
    service = OptimizationService(
        [FailedRepository(), StaticRepository([gpu("working", "Healthy", 24, 1, 1)])],
        FixedExchangeRateProvider(1000),
    )
    result = service.optimize(request(budget=20_000))
    assert result.status == "OK"
    assert result.recommended_provider == "Healthy"


def test_all_provider_failures_return_no_provider_available():
    service = OptimizationService(
        [FailedRepository(), FailedRepository()], FixedExchangeRateProvider(1000)
    )
    result = service.optimize(request())
    assert result.status == "NO_PROVIDER_AVAILABLE"
    assert not result.can_run


def test_unavailable_workload_does_not_recommend_gpu():
    req = TrainingRequest(model_name="unknown", max_budget_krw=10_000)
    result = recommend_gpu(req, analyze_workload(req), [gpu("gpu", "A", 80, 1, 1)], 1000)
    assert result.status == "ESTIMATE_UNAVAILABLE"
    assert result.recommended_gpu is None


def test_response_separates_actual_provider_data_from_estimates():
    result = recommend(request(), [gpu("gpu", "RunPod", 24, 1, 2)])
    candidate = result.candidates[0]
    assert candidate.pricing_data_type == "actual"
    assert candidate.pricing_source == "RunPod_official_api"
    assert candidate.estimation_data_type == "estimated"
    assert candidate.estimated_performance_factor == 2


def test_same_gpu_from_different_providers_is_compared_independently():
    result = recommend(request(), [
        gpu("RTX 4090", "Provider A", 24, 2, 1),
        gpu("RTX 4090", "Provider B", 24, 1, 1),
    ])
    assert len(result.candidates) == 2
    assert result.recommended_provider == "Provider B"


def test_recommendation_preserves_selected_provider_resource_id():
    result = recommend(request(), [
        gpu("RTX 4090", "RunPod", 24, 1, 1,
            provider_resource_id="NVIDIA GeForce RTX 4090")
    ])
    assert result.candidates[0].provider_resource_id == "NVIDIA GeForce RTX 4090"
    assert result.recommended_provider_resource_id == "NVIDIA GeForce RTX 4090"


def test_savings_are_compared_with_next_cheapest_candidate():
    result = recommend(request(), [
        gpu("selected", "A", 24, 100, 1),
        gpu("next", "B", 24, 120, 1),
        gpu("expensive", "C", 24, 500, 1),
    ])
    assert result.estimated_savings_krw == 230
    assert result.estimated_savings_percent == pytest.approx(230 / 1380 * 100)


def test_unavailable_gpu_is_excluded():
    unavailable = gpu("unavailable", "A", 80, 0.1, 10).model_copy(update={"available": False})
    result = recommend(request(), [unavailable, gpu("available", "B", 24, 1, 1)])
    assert [item.gpu_name for item in result.candidates] == ["available"]


def test_single_candidate_has_zero_savings():
    result = recommend(request(), [gpu("only", "A", 24, 1, 1)])
    assert result.recommended_gpu == "only"
    assert result.estimated_savings_krw == 0
    assert result.estimated_savings_percent == 0


def test_large_candidate_collection_is_sorted_and_optimized():
    offers = [gpu(f"gpu-{index}", f"provider-{index}", 24, index + 1, 1)
              for index in range(500)]
    result = recommend(request(budget=100_000), offers)
    assert len(result.candidates) == 500
    assert result.recommended_gpu == "gpu-0"


def test_budget_uses_total_charge_after_agent_fee():
    result = recommend(request(budget=5_500), [gpu("gpu", "A", 24, 500, 1)])
    assert result.estimated_gpu_cost_krw == 5_000
    assert result.agent_fee_krw == 750
    assert result.estimated_total_charge_krw == 5_750
    assert not result.within_budget_after_fee
    assert result.status == "BUDGET_TOO_LOW"


@pytest.mark.parametrize("price", [0, -1])
def test_non_positive_gpu_price_is_rejected_by_internal_model(price):
    with pytest.raises(Exception):
        gpu("invalid", "A", 24, price, 1)
