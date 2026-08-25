"""Validated inputs and outputs for GPU cost optimization."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TrainingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(min_length=1)
    task_type: Literal["fine_tuning", "training", "inference", "image_generation"] = "fine_tuning"
    parameter_count_billion: float | None = Field(default=None, gt=0)
    dataset_size_gb: float | None = Field(default=None, gt=0)
    training_type: Literal["full_finetuning", "lora", "qlora", "inference"] = "lora"
    max_budget_krw: float | None = Field(default=None, gt=0)
    source_type: Literal["manual", "github", "notebook", "python_script"] = "manual"
    source_reference: str | None = None
    required_vram_gb: float | None = Field(
        default=None, gt=0, description="Advanced estimated VRAM override"
    )
    estimated_base_hours: float | None = Field(
        default=None, gt=0, description="Advanced estimated base-hours override"
    )


class GPU(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    vram_gb: float = Field(gt=0)
    price_per_hour: float = Field(gt=0)
    performance_score: float = Field(
        gt=0,
        description="Estimated performance factor; not provider benchmark data.",
    )
    available: bool = True
    source: str = "mock_fixture"
    fetched_at: datetime | None = None
    price_data_type: Literal["actual", "fixture"] = "fixture"
    region: str | None = None
    provider_resource_id: str | None = Field(
        default=None,
        description="Opaque provider-supplied GPU type/resource ID; never inferred from the display name.",
    )


class GPUCandidate(BaseModel):
    gpu_name: str
    provider: str
    vram_gb: float
    price_per_hour: float
    estimated_hours: float
    estimated_total_cost: float
    provider_resource_id: str | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class OptimizationResult(BaseModel):
    candidates: list[GPUCandidate]
    recommended_gpu: GPUCandidate


class WorkloadEstimate(BaseModel):
    status: Literal["READY", "ESTIMATE_UNAVAILABLE"]
    estimated_required_vram_gb: float | None = None
    estimated_base_hours: float | None = None
    workload_type: str
    estimation_confidence: Literal["low", "medium", "high"]
    estimation_notes: list[str]
    assumptions: list[str]


class BudgetCandidate(BaseModel):
    provider: str
    gpu_name: str
    vram_gb: float
    actual_price_per_hour: float
    estimated_performance_factor: float
    estimated_hours: float
    estimated_total_cost_usd: float
    estimated_total_cost_krw: float
    within_budget: bool
    estimated_gpu_cost_krw: float
    agent_fee_krw: float
    estimated_total_charge_krw: float
    within_budget_after_fee: bool
    pricing_data_type: Literal["actual", "fixture"]
    pricing_source: str
    estimation_data_type: Literal["estimated"] = "estimated"
    provider_resource_id: str | None = None


class RecommendationResult(BaseModel):
    status: Literal["OK", "BUDGET_TOO_LOW", "NO_PROVIDER_AVAILABLE", "ESTIMATE_UNAVAILABLE", "NO_COMPATIBLE_GPU"]
    can_run: bool
    recommended_provider: str | None = None
    recommended_gpu: str | None = None
    recommended_provider_resource_id: str | None = None
    estimated_required_vram_gb: float | None = None
    available_vram_gb: float | None = None
    estimated_training_hours: float | None = None
    estimated_total_cost_krw: float | None = None
    estimated_gpu_cost_krw: float | None = None
    agent_fee_krw: float | None = None
    estimated_total_charge_krw: float | None = None
    max_budget_krw: float | None = None
    within_budget: bool = False
    within_budget_after_fee: bool = False
    estimated_savings_krw: float | None = None
    estimated_savings_percent: float | None = None
    minimum_required_budget_krw: float | None = None
    budget_shortfall_krw: float | None = None
    cheapest_option: BudgetCandidate | None = None
    candidates: list[BudgetCandidate] = Field(default_factory=list)
    recommendation_reason: str
    estimation_notes: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class ExecutionStep(BaseModel):
    name: str
    status: Literal["PLANNED"] = "PLANNED"
    planned: bool = True


class ExecutionPlan(BaseModel):
    status: Literal["PLANNED", "NOT_PLANNABLE"]
    provider: str | None = None
    gpu: str | None = None
    provider_resource_id: str | None = None
    estimated_vram_required: float | None = None
    gpu_vram: float | None = None
    estimated_duration: str | None = None
    estimated_cost_krw: float | None = None
    budget_krw: float | None = None
    steps: list[ExecutionStep] = Field(default_factory=list)
    note: str


class JobStatus(str, Enum):
    PLANNED = "PLANNED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    STOPPED = "STOPPED"


class TrainingJob(BaseModel):
    id: str
    model_name: str
    task_type: str
    training_type: str
    selected_provider: str
    selected_gpu: str
    selected_provider_resource_id: str | None = None
    recommendation_status: str | None = None
    gpu_compatible: bool = False
    gpu_available: bool = False
    provider_data_type: Literal["actual", "fixture"] = "fixture"
    estimated_gpu_cost_krw: float
    agent_fee_krw: float
    estimated_total_charge_krw: float
    max_budget_krw: float | None
    status: JobStatus = JobStatus.PLANNED
    created_at: datetime
    updated_at: datetime
    provider_resource_instance_id: str | None = None
    provider_gpu_type_id: str | None = None
    cost_per_hour: float | None = None
    adjusted_cost_per_hour: float | None = None
    desired_status: str | None = None
    image_name: str | None = None
    provisioned_at: datetime | None = None
    provisioning_error: str | None = None


class RecommendationSummary(BaseModel):
    status: str
    can_run: bool
    provider: str
    gpu: str
    provider_resource_id: str | None = None
    available_vram_gb: float
    estimated_training_hours: float
    estimated_savings_krw: float
    estimated_savings_percent: float
    reason: str


class PricingSummary(BaseModel):
    estimated_gpu_cost_krw: float
    agent_fee_krw: float
    estimated_total_charge_krw: float
    gpu_price_data_type: Literal["actual", "fixture"]
    gpu_price_source: str
    calculation_data_type: Literal["estimated"] = "estimated"


class BudgetSummary(BaseModel):
    max_budget_krw: float | None
    within_budget_after_fee: bool
    minimum_required_budget_krw: float | None
    budget_shortfall_krw: float | None


class OptimizeAPIResponse(BaseModel):
    workload: WorkloadEstimate
    candidates: list[BudgetCandidate]
    recommendation: RecommendationSummary
    pricing: PricingSummary
    budget: BudgetSummary
    estimation_notes: list[str]
    assumptions: list[str]


class APIErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class APIErrorResponse(BaseModel):
    error: APIErrorDetail
