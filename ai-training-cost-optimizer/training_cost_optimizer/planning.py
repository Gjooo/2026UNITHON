"""Planned-only execution artifacts; no infrastructure action occurs here."""

from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from .models import (
    ExecutionPlan,
    ExecutionStep,
    RecommendationResult,
    TrainingJob,
    TrainingRequest,
    WorkloadEstimate,
)

PLANNED_STEPS = (
    "GPU environment provision",
    "training environment setup",
    "training execution",
    "result save",
    "automatic GPU shutdown",
)


class FutureJobRuntime(Protocol):
    """Boundary for later provisioning/shutdown implementation."""

    def queue(self, job: TrainingJob) -> None: ...
    def shutdown(self, job: TrainingJob, reason: str) -> None: ...


def _duration(hours: float) -> str:
    total_minutes = round(hours * 60)
    return f"{total_minutes // 60}h {total_minutes % 60}m"


def create_execution_plan(recommendation: RecommendationResult) -> ExecutionPlan:
    if recommendation.status != "OK":
        return ExecutionPlan(
            status="NOT_PLANNABLE",
            budget_krw=recommendation.max_budget_krw,
            note=f"No execution is planned because recommendation status is {recommendation.status}.",
        )
    return ExecutionPlan(
        status="PLANNED",
        provider=recommendation.recommended_provider,
        gpu=recommendation.recommended_gpu,
        provider_resource_id=recommendation.recommended_provider_resource_id,
        estimated_vram_required=recommendation.estimated_required_vram_gb,
        gpu_vram=recommendation.available_vram_gb,
        estimated_duration=_duration(recommendation.estimated_training_hours or 0),
        estimated_cost_krw=recommendation.estimated_total_charge_krw,
        budget_krw=recommendation.max_budget_krw,
        steps=[ExecutionStep(name=name) for name in PLANNED_STEPS],
        note="Plan only: no GPU is provisioned and no training or shutdown action is executed.",
    )


def create_planned_job(
    request: TrainingRequest,
    estimate: WorkloadEstimate,
    recommendation: RecommendationResult,
) -> TrainingJob | None:
    if recommendation.status != "OK":
        return None
    selected = next(
        candidate for candidate in recommendation.candidates
        if candidate.provider == recommendation.recommended_provider
        and candidate.gpu_name == recommendation.recommended_gpu
    )
    return TrainingJob(
        id=str(uuid4()),
        model_name=request.model_name,
        task_type=request.task_type,
        training_type=request.training_type,
        selected_provider=recommendation.recommended_provider or "",
        selected_gpu=recommendation.recommended_gpu or "",
        selected_provider_resource_id=recommendation.recommended_provider_resource_id,
        recommendation_status=recommendation.status,
        gpu_compatible=True,
        gpu_available=True,
        provider_data_type=selected.pricing_data_type,
        estimated_gpu_cost_krw=recommendation.estimated_gpu_cost_krw or 0,
        agent_fee_krw=recommendation.agent_fee_krw or 0,
        estimated_total_charge_krw=recommendation.estimated_total_charge_krw or 0,
        max_budget_krw=request.max_budget_krw,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
