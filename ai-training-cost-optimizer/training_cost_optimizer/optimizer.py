"""Pure GPU filtering and total-cost optimization logic."""

from .models import GPUCandidate, OptimizationResult, TrainingRequest
from .repository import GPURepository


class NoCompatibleGPUError(ValueError):
    """Raised when no GPU has enough VRAM for a training request."""


def optimize_training_cost(
    request: TrainingRequest,
    repository: GPURepository,
) -> OptimizationResult:
    if request.required_vram_gb is None or request.estimated_base_hours is None:
        raise ValueError(
            "Legacy optimizer requires advanced required_vram_gb and estimated_base_hours; "
            "use OptimizationService for automatic workload analysis."
        )
    candidates: list[GPUCandidate] = []

    for gpu in repository.list_gpus():
        if not gpu.available or gpu.vram_gb < request.required_vram_gb:
            continue

        estimated_hours = request.estimated_base_hours / gpu.performance_score
        candidates.append(
            GPUCandidate(
                gpu_name=gpu.name,
                provider=gpu.provider,
                vram_gb=gpu.vram_gb,
                price_per_hour=gpu.price_per_hour,
                estimated_hours=estimated_hours,
                estimated_total_cost=estimated_hours * gpu.price_per_hour,
                provider_resource_id=gpu.provider_resource_id,
            )
        )

    if not candidates:
        raise NoCompatibleGPUError(
            f"No GPU has the required {request.required_vram_gb:g} GB of VRAM."
        )

    candidates.sort(
        key=lambda candidate: (
            candidate.estimated_total_cost,
            candidate.estimated_hours,
            candidate.gpu_name,
        )
    )
    return OptimizationResult(
        candidates=candidates,
        recommended_gpu=candidates[0],
    )
