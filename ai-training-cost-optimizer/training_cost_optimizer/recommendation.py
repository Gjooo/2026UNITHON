"""Budget-aware recommendation built on normalized GPU offers."""

from collections.abc import Sequence

from .models import (
    BudgetCandidate,
    GPU,
    RecommendationResult,
    TrainingRequest,
    WorkloadEstimate,
)
from .pricing import PricingPolicy


def recommend_gpu(
    request: TrainingRequest,
    estimate: WorkloadEstimate,
    offers: Sequence[GPU],
    usd_to_krw_rate: float,
    *,
    provider_errors: Sequence[str] = (),
    pricing_policy: PricingPolicy | None = None,
) -> RecommendationResult:
    pricing_policy = pricing_policy or PricingPolicy.from_environment()
    if estimate.status != "READY" or estimate.estimated_required_vram_gb is None or estimate.estimated_base_hours is None:
        return RecommendationResult(
            status="ESTIMATE_UNAVAILABLE",
            can_run=False,
            max_budget_krw=request.max_budget_krw,
            recommendation_reason="Workload requirements could not be estimated, so no GPU was recommended.",
            estimation_notes=estimate.estimation_notes,
            assumptions=estimate.assumptions,
        )

    if not offers and provider_errors:
        return RecommendationResult(
            status="NO_PROVIDER_AVAILABLE",
            can_run=False,
            estimated_required_vram_gb=estimate.estimated_required_vram_gb,
            max_budget_krw=request.max_budget_krw,
            recommendation_reason="All configured GPU providers failed or were unavailable.",
            estimation_notes=estimate.estimation_notes,
            assumptions=[*estimate.assumptions, *provider_errors],
        )

    candidates: list[BudgetCandidate] = []
    for gpu in offers:
        if not gpu.available or gpu.vram_gb < estimate.estimated_required_vram_gb:
            continue
        hours = estimate.estimated_base_hours / gpu.performance_score
        cost_usd = hours * gpu.price_per_hour
        cost_krw = cost_usd * usd_to_krw_rate
        agent_fee = pricing_policy.calculate_agent_fee(cost_krw)
        total_charge = cost_krw + agent_fee
        within_budget_after_fee = (
            request.max_budget_krw is None or total_charge <= request.max_budget_krw
        )
        candidates.append(BudgetCandidate(
            provider=gpu.provider,
            gpu_name=gpu.name,
            vram_gb=gpu.vram_gb,
            actual_price_per_hour=gpu.price_per_hour,
            estimated_performance_factor=gpu.performance_score,
            estimated_hours=hours,
            estimated_total_cost_usd=cost_usd,
            estimated_total_cost_krw=cost_krw,
            within_budget=within_budget_after_fee,
            estimated_gpu_cost_krw=cost_krw,
            agent_fee_krw=agent_fee,
            estimated_total_charge_krw=total_charge,
            within_budget_after_fee=within_budget_after_fee,
            pricing_data_type=gpu.price_data_type,
            pricing_source=gpu.source,
            provider_resource_id=gpu.provider_resource_id,
        ))

    candidates.sort(key=lambda item: (item.estimated_total_charge_krw, item.estimated_hours, item.provider, item.gpu_name))
    if not candidates:
        return RecommendationResult(
            status="NO_COMPATIBLE_GPU",
            can_run=False,
            estimated_required_vram_gb=estimate.estimated_required_vram_gb,
            max_budget_krw=request.max_budget_krw,
            recommendation_reason="No currently available GPU has enough VRAM.",
            estimation_notes=estimate.estimation_notes,
            assumptions=estimate.assumptions,
        )

    cheapest = candidates[0]
    affordable = [item for item in candidates if item.within_budget_after_fee]
    if not affordable:
        shortfall = cheapest.estimated_total_charge_krw - (request.max_budget_krw or 0)
        return RecommendationResult(
            status="BUDGET_TOO_LOW",
            can_run=True,
            estimated_required_vram_gb=estimate.estimated_required_vram_gb,
            available_vram_gb=cheapest.vram_gb,
            estimated_training_hours=cheapest.estimated_hours,
            estimated_total_cost_krw=cheapest.estimated_total_cost_krw,
            estimated_gpu_cost_krw=cheapest.estimated_gpu_cost_krw,
            agent_fee_krw=cheapest.agent_fee_krw,
            estimated_total_charge_krw=cheapest.estimated_total_charge_krw,
            max_budget_krw=request.max_budget_krw,
            within_budget=False,
            within_budget_after_fee=False,
            minimum_required_budget_krw=cheapest.estimated_total_charge_krw,
            budget_shortfall_krw=shortfall,
            cheapest_option=cheapest,
            candidates=candidates,
            recommendation_reason="The workload can run, but the cheapest estimated total charge including the agent fee exceeds the budget.",
            estimation_notes=estimate.estimation_notes,
            assumptions=estimate.assumptions,
        )

    selected = affordable[0]
    comparison_cost = (
        candidates[1].estimated_total_charge_krw
        if len(candidates) > 1
        else selected.estimated_total_charge_krw
    )
    savings = max(0.0, comparison_cost - selected.estimated_total_charge_krw)
    savings_percent = (savings / comparison_cost * 100) if comparison_cost else 0.0
    hourly_cheapest = min(candidates, key=lambda item: item.actual_price_per_hour)
    if selected is not hourly_cheapest:
        reason = (
            f"{selected.gpu_name} has a higher hourly price than {hourly_cheapest.gpu_name}, "
            "but its shorter estimated training time gives the lowest job completion cost within budget."
        )
    else:
        reason = "This option has the lowest estimated job completion cost among compatible GPUs within budget."
    return RecommendationResult(
        status="OK",
        can_run=True,
        recommended_provider=selected.provider,
        recommended_gpu=selected.gpu_name,
        recommended_provider_resource_id=selected.provider_resource_id,
        estimated_required_vram_gb=estimate.estimated_required_vram_gb,
        available_vram_gb=selected.vram_gb,
        estimated_training_hours=selected.estimated_hours,
        estimated_total_cost_krw=selected.estimated_total_cost_krw,
        estimated_gpu_cost_krw=selected.estimated_gpu_cost_krw,
        agent_fee_krw=selected.agent_fee_krw,
        estimated_total_charge_krw=selected.estimated_total_charge_krw,
        max_budget_krw=request.max_budget_krw,
        within_budget=True,
        within_budget_after_fee=True,
        estimated_savings_krw=savings,
        estimated_savings_percent=savings_percent,
        minimum_required_budget_krw=cheapest.estimated_total_charge_krw,
        cheapest_option=cheapest,
        candidates=candidates,
        recommendation_reason=reason,
        estimation_notes=estimate.estimation_notes,
        assumptions=estimate.assumptions,
    )
