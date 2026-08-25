"""Deterministic workload estimation, intentionally separate from optimization."""

from .config import (
    BASE_HOURS_PER_BILLION_PARAMS_PER_DATASET_GB,
    DEFAULT_DATASET_SIZE_GB,
    KNOWN_MODEL_PARAMETER_COUNTS_BILLION,
    MINIMUM_BASE_HOURS,
    MINIMUM_VRAM_GB,
    VRAM_GB_PER_BILLION_PARAMETERS,
    VRAM_SAFETY_FACTOR,
)
from ..models import TrainingRequest, WorkloadEstimate


def analyze_workload(request: TrainingRequest) -> WorkloadEstimate:
    if request.required_vram_gb is not None and request.estimated_base_hours is not None:
        return WorkloadEstimate(
            status="READY",
            estimated_required_vram_gb=request.required_vram_gb,
            estimated_base_hours=request.estimated_base_hours,
            workload_type=request.training_type,
            estimation_confidence="high",
            estimation_notes=["Advanced user-provided estimates were used."],
            assumptions=["VRAM and base-hours are user estimates, not measured values."],
        )

    parameter_count = request.parameter_count_billion
    parameter_source_note: str | None = None
    if parameter_count is None:
        parameter_count = KNOWN_MODEL_PARAMETER_COUNTS_BILLION.get(request.model_name.lower())
        if parameter_count is not None:
            parameter_source_note = (
                f"Configured model metadata supplied an estimated parameter count of "
                f"{parameter_count:g} billion for {request.model_name}."
            )

    if parameter_count is None:
        return WorkloadEstimate(
            status="ESTIMATE_UNAVAILABLE",
            workload_type=request.training_type,
            estimation_confidence="low",
            estimation_notes=["Parameter count or both advanced estimates are required."],
            assumptions=[],
        )

    dataset_gb = request.dataset_size_gb or DEFAULT_DATASET_SIZE_GB
    vram = max(
        MINIMUM_VRAM_GB,
        parameter_count
        * VRAM_GB_PER_BILLION_PARAMETERS[request.training_type]
        * VRAM_SAFETY_FACTOR,
    )
    base_hours = max(
        MINIMUM_BASE_HOURS,
        parameter_count
        * dataset_gb
        * BASE_HOURS_PER_BILLION_PARAMS_PER_DATASET_GB[request.training_type],
    )
    assumptions = [
        "VRAM and base-hours are deterministic MVP estimates, not measurements.",
        f"Dataset size used for estimation: {dataset_gb:g} GB.",
        "One GPU is assumed.",
    ]
    if request.dataset_size_gb is None:
        assumptions.append("Dataset size was not supplied; configured 1 GB default was used.")
    if parameter_source_note is not None:
        assumptions.append(parameter_source_note)
    return WorkloadEstimate(
        status="READY",
        estimated_required_vram_gb=round(vram, 2),
        estimated_base_hours=round(base_hours, 4),
        workload_type=request.training_type,
        estimation_confidence="medium" if request.dataset_size_gb else "low",
        estimation_notes=[
            "Estimated from parameter count, training type, and dataset size using configured factors."
        ],
        assumptions=assumptions,
    )
