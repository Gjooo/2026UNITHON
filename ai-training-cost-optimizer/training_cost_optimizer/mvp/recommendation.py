"""Pure, deterministic recommendation policy for fixed MVP GPU profiles."""

from __future__ import annotations

from dataclasses import dataclass

from .config import (
    ESTIMATE_DISCLAIMER,
    GPU_EXECUTION_PROFILES,
    PRICE_DATA_TYPE,
    SELECTION_POLICY_VERSION,
    WORKLOAD,
    GpuExecutionProfile,
)
from .domain import Priority


@dataclass(frozen=True)
class Recommendation:
    selected_profile_id: str
    selected_gpu_type: str
    selection_snapshot: dict


class ProfileRecommendationService:
    """Compare server-defined profiles without knowing about HTTP, DB, or Runpod."""

    def __init__(self, profiles: tuple[GpuExecutionProfile, ...] = GPU_EXECUTION_PROFILES) -> None:
        self._profiles = profiles

    def recommend(self, *, max_budget_krw: int, priority: Priority | str) -> Recommendation | None:
        policy = Priority(priority)
        vram_compatible = [
            profile for profile in self._profiles if profile.vram_gb >= WORKLOAD.required_vram_gb
        ]
        candidates = [
            self._candidate(profile, max_budget_krw=max_budget_krw) for profile in vram_compatible
        ]
        eligible_profiles = [
            profile for profile in vram_compatible if profile.estimated_gpu_cost_krw <= max_budget_krw
        ]
        if not eligible_profiles:
            return None

        selected = self._select(eligible_profiles, policy)
        recommended = self._candidate(selected, max_budget_krw=max_budget_krw)
        recommended.pop("eligibility")
        recommended["reason"] = self._reason(policy)
        snapshot = {
            "priceDataType": PRICE_DATA_TYPE,
            "estimateDisclaimer": ESTIMATE_DISCLAIMER,
            "selectionPolicyVersion": SELECTION_POLICY_VERSION,
            "candidates": candidates,
            "recommended": recommended,
        }
        return Recommendation(
            selected_profile_id=selected.id,
            selected_gpu_type=selected.gpu_type,
            selection_snapshot=snapshot,
        )

    @staticmethod
    def _candidate(profile: GpuExecutionProfile, *, max_budget_krw: int) -> dict:
        return {
            "profileId": profile.id,
            "provider": profile.provider,
            "gpuType": profile.gpu_type,
            "estimatedRuntimeMinutes": profile.estimated_runtime_minutes,
            "estimatedGpuCostKrw": profile.estimated_gpu_cost_krw,
            "eligibility": (
                "ELIGIBLE" if profile.estimated_gpu_cost_krw <= max_budget_krw else "OVER_BUDGET"
            ),
        }

    @staticmethod
    def _select(profiles: list[GpuExecutionProfile], policy: Priority) -> GpuExecutionProfile:
        if policy is Priority.CHEAPEST:
            return min(profiles, key=lambda item: (
                item.estimated_gpu_cost_krw, item.estimated_runtime_minutes, item.id
            ))
        if policy is Priority.FASTEST:
            return min(profiles, key=lambda item: (
                item.estimated_runtime_minutes, item.estimated_gpu_cost_krw, item.id
            ))

        minimum_cost = min(item.estimated_gpu_cost_krw for item in profiles)
        minimum_runtime = min(item.estimated_runtime_minutes for item in profiles)
        return min(profiles, key=lambda item: (
            0.5 * (item.estimated_gpu_cost_krw / minimum_cost)
            + 0.5 * (item.estimated_runtime_minutes / minimum_runtime),
            item.estimated_gpu_cost_krw,
            item.estimated_runtime_minutes,
            item.id,
        ))

    @staticmethod
    def _reason(policy: Priority) -> str:
        return {
            Priority.CHEAPEST: "예산 안 후보 중 예상 GPU 비용이 가장 낮습니다.",
            Priority.FASTEST: "예산 안 후보 중 예상 실행시간이 가장 짧습니다.",
            Priority.BALANCED: "예상 GPU 비용과 실행시간의 균형 점수가 가장 낮습니다.",
        }[policy]

