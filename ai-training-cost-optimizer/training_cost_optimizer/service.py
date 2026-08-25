"""Application orchestration across analysis, providers, and recommendation."""

from collections.abc import Sequence

from .analysis import analyze_workload
from .currency import ConfiguredExchangeRateProvider, ExchangeRateProvider
from .models import ExecutionPlan, GPU, RecommendationResult, TrainingRequest, WorkloadEstimate
from .planning import create_execution_plan
from .pricing import PricingPolicy
from .providers.collector import collect_gpu_offers
from .providers.runpod import RunPodGPURepository
from .recommendation import recommend_gpu
from .repository import GPURepository


class OptimizationService:
    def __init__(
        self,
        repositories: Sequence[GPURepository] | None = None,
        exchange_rates: ExchangeRateProvider | None = None,
        pricing_policy: PricingPolicy | None = None,
    ) -> None:
        self.repositories = tuple(repositories or (RunPodGPURepository(),))
        self.exchange_rates = exchange_rates or ConfiguredExchangeRateProvider()
        self.pricing_policy = pricing_policy or PricingPolicy.from_environment()

    def analyze(self, request: TrainingRequest) -> WorkloadEstimate:
        return analyze_workload(request)

    def list_gpus(self) -> tuple[tuple[GPU, ...], tuple[str, ...]]:
        collected = collect_gpu_offers(self.repositories)
        return collected.offers, collected.errors

    def optimize(self, request: TrainingRequest) -> RecommendationResult:
        estimate = self.analyze(request)
        if estimate.status != "READY":
            return recommend_gpu(request, estimate, (), self.exchange_rates.usd_to_krw(), pricing_policy=self.pricing_policy)
        collected = collect_gpu_offers(self.repositories)
        result = recommend_gpu(
            request,
            estimate,
            collected.offers,
            self.exchange_rates.usd_to_krw(),
            provider_errors=collected.errors,
            pricing_policy=self.pricing_policy,
        )
        result.assumptions.append(
            f"USD/KRW uses {self.exchange_rates.source}; it is not a live exchange rate."
        )
        return result

    def plan(self, request: TrainingRequest) -> ExecutionPlan:
        return create_execution_plan(self.optimize(request))
