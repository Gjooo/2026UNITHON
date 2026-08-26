"""Budget guard decisions. This module never calls a provider stop API."""

from enum import Enum


class BudgetDecision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK_EXECUTION = "BLOCK_EXECUTION"
    STOP_REQUIRED = "STOP_REQUIRED"


def preflight_budget_decision(estimated_total_charge_krw: float, max_budget_krw: float | None) -> BudgetDecision:
    if max_budget_krw is not None and estimated_total_charge_krw > max_budget_krw:
        return BudgetDecision.BLOCK_EXECUTION
    return BudgetDecision.ALLOW


def runtime_budget_decision(projected_total_charge_krw: float, max_budget_krw: float | None) -> BudgetDecision:
    if max_budget_krw is not None and projected_total_charge_krw > max_budget_krw:
        return BudgetDecision.STOP_REQUIRED
    return BudgetDecision.ALLOW

