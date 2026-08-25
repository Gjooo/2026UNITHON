"""Controllable lifecycle provider used by tests and local MVP development."""

from __future__ import annotations

from uuid import uuid4

from training_cost_optimizer.mvp.config import GpuExecutionProfile
from training_cost_optimizer.providers.runpod_lifecycle import PodStatus


class FakeRunpodLifecycleProvider:
    """Does not call Runpod; tests explicitly move Pods through their states."""

    def __init__(self) -> None:
        self.pod_statuses: dict[str, PodStatus] = {}
        self.created_pods: list[tuple[str, str]] = []
        self.deleted_pod_ids: list[str] = []
        # Injection points for the provider failures the runner must survive.
        self.create_error: Exception | None = None
        self.status_error: Exception | None = None
        self.delete_error: Exception | None = None

    def create_pod(self, profile: GpuExecutionProfile, job_id: str) -> str:
        if self.create_error is not None:
            raise self.create_error
        pod_id = f"fake-pod-{uuid4()}"
        self.pod_statuses[pod_id] = PodStatus.PROVISIONING
        self.created_pods.append((pod_id, job_id))
        return pod_id

    def get_pod_status(self, pod_id: str) -> PodStatus:
        if self.status_error is not None:
            raise self.status_error
        return self.pod_statuses[pod_id]

    def delete_pod(self, pod_id: str) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted_pod_ids.append(pod_id)

    def mark_running(self, pod_id: str) -> None:
        self.pod_statuses[pod_id] = PodStatus.RUNNING

    def mark_terminated(self, pod_id: str) -> None:
        self.pod_statuses[pod_id] = PodStatus.TERMINATED

    def mark_failed(self, pod_id: str) -> None:
        self.pod_statuses[pod_id] = PodStatus.FAILED
