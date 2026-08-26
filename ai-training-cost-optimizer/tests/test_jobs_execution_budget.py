from datetime import datetime, timezone

import pytest

from training_cost_optimizer.budget import (
    BudgetDecision, preflight_budget_decision, runtime_budget_decision)
from training_cost_optimizer.execution import MockExecutionProvider
from training_cost_optimizer.jobs import InvalidJobTransition, transition_job
from training_cost_optimizer.models import JobStatus, TrainingJob


def job() -> TrainingJob:
    now = datetime.now(timezone.utc)
    return TrainingJob(
        id="job-1", model_name="bert-base-uncased", task_type="fine_tuning",
        training_type="lora", selected_provider="DEMO", selected_gpu="RTX 4090",
        estimated_gpu_cost_krw=1000, agent_fee_krw=150,
        estimated_total_charge_krw=1150, max_budget_krw=2000,
        created_at=now, updated_at=now,
    )


def test_allowed_job_lifecycle_and_resume():
    current = transition_job(job(), JobStatus.QUEUED)
    current = transition_job(current, JobStatus.RUNNING)
    current = transition_job(current, JobStatus.INTERRUPTED)
    current = transition_job(current, JobStatus.QUEUED)
    current = transition_job(current, JobStatus.RUNNING)
    current = transition_job(current, JobStatus.COMPLETED)
    current = transition_job(current, JobStatus.STOPPED)
    assert current.status == JobStatus.STOPPED


def test_invalid_completed_to_running_transition_is_blocked():
    completed = job().model_copy(update={"status": JobStatus.COMPLETED})
    with pytest.raises(InvalidJobTransition):
        transition_job(completed, JobStatus.RUNNING)


def test_mock_execution_provider_lifecycle_without_cloud_calls():
    provider = MockExecutionProvider()
    resource_id = provider.provision(job())
    assert resource_id.startswith("DEMO-FIXTURE-")
    provider.start(resource_id)
    assert provider.get_status(resource_id) == JobStatus.RUNNING
    provider.stop(resource_id)
    assert provider.get_status(resource_id) == JobStatus.STOPPED
    provider.cleanup(resource_id)
    with pytest.raises(KeyError):
        provider.get_status(resource_id)


def test_budget_guards_only_return_decisions():
    assert preflight_budget_decision(1200, 1000) == BudgetDecision.BLOCK_EXECUTION
    assert preflight_budget_decision(1000, 1000) == BudgetDecision.ALLOW
    assert runtime_budget_decision(1200, 1000) == BudgetDecision.STOP_REQUIRED
    assert runtime_budget_decision(900, 1000) == BudgetDecision.ALLOW

