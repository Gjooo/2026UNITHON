"""Transparent agent-fee policy, separate from provider GPU prices."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class PricingPolicy:
    percentage_rate: float = 0.15
    fixed_fee_krw: float = 0.0
    name: str = "mvp_percentage_fee"

    def __post_init__(self) -> None:
        if not 0 <= self.percentage_rate <= 1:
            raise ValueError("percentage_rate must be between 0 and 1")
        if self.fixed_fee_krw < 0:
            raise ValueError("fixed_fee_krw must be non-negative")

    @classmethod
    def from_environment(cls) -> "PricingPolicy":
        try:
            rate = float(os.getenv("AGENT_FEE_RATE", "0.15"))
            fixed = float(os.getenv("AGENT_FIXED_FEE_KRW", "0"))
        except ValueError as exc:
            raise ValueError("Agent fee settings must be numeric") from exc
        return cls(percentage_rate=rate, fixed_fee_krw=fixed)

    def calculate_agent_fee(self, estimated_gpu_cost_krw: float, *, fee_waived: bool = False) -> float:
        if estimated_gpu_cost_krw < 0:
            raise ValueError("estimated_gpu_cost_krw must be non-negative")
        if fee_waived:
            return 0.0
        return estimated_gpu_cost_krw * self.percentage_rate + self.fixed_fee_krw

    def calculate_total_charge(self, estimated_gpu_cost_krw: float, *, fee_waived: bool = False) -> float:
        return estimated_gpu_cost_krw + self.calculate_agent_fee(
            estimated_gpu_cost_krw, fee_waived=fee_waived
        )

