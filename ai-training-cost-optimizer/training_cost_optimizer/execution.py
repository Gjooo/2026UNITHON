"""Execution boundary and in-memory mock; no cloud API calls."""

from typing import Protocol

from .models import JobStatus, TrainingJob


class ExecutionProvider(Protocol):
    def provision(self, job: TrainingJob) -> str: ...
    def start(self, resource_id: str) -> None: ...
    def get_status(self, resource_id: str) -> JobStatus: ...
    def stop(self, resource_id: str) -> None: ...
    def cleanup(self, resource_id: str) -> None: ...


class MockExecutionProvider:
    """Test-only lifecycle implementation that never provisions a real GPU."""

    def __init__(self) -> None:
        self.resources: dict[str, JobStatus] = {}

    def provision(self, job: TrainingJob) -> str:
        resource_id = f"DEMO-FIXTURE-{job.id}"
        self.resources[resource_id] = JobStatus.QUEUED
        return resource_id

    def start(self, resource_id: str) -> None:
        self._require(resource_id)
        self.resources[resource_id] = JobStatus.RUNNING

    def get_status(self, resource_id: str) -> JobStatus:
        self._require(resource_id)
        return self.resources[resource_id]

    def stop(self, resource_id: str) -> None:
        self._require(resource_id)
        self.resources[resource_id] = JobStatus.STOPPED

    def cleanup(self, resource_id: str) -> None:
        self._require(resource_id)
        del self.resources[resource_id]

    def _require(self, resource_id: str) -> None:
        if resource_id not in self.resources:
            raise KeyError(f"Unknown mock resource: {resource_id}")

