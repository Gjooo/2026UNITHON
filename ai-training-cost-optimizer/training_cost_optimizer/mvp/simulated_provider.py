"""Cost-free provider used by ``MVP_PROVIDER_MODE=fake`` for local development.

Unlike :class:`FakeRunpodLifecycleProvider`, which tests drive step by step,
this one advances on a clock so the frontend sees the real
``PROVISIONING → RUNNING → TERMINATING`` progression while polling. No Runpod
API is contacted and no Pod is billed. The training container does not exist
locally, so the completion callback is sent by hand during frontend work.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from training_cost_optimizer.providers.runpod_lifecycle import PodStatus

from .config import GpuExecutionProfile

DEFAULT_PROVISIONING_SECONDS = 10.0

logger = logging.getLogger(__name__)


@dataclass
class _SimulatedPod:
    created_at: float
    deleted_at: float | None = None


class SimulatedRunpodLifecycleProvider:
    """A local stand-in whose Pods start after a delay and terminate on request."""

    def __init__(
        self,
        *,
        provisioning_seconds: float = DEFAULT_PROVISIONING_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._provisioning_seconds = provisioning_seconds
        self._clock = clock
        self._pods: dict[str, _SimulatedPod] = {}

    def create_pod(self, profile: GpuExecutionProfile, job_id: str) -> str:
        pod_id = f"sim-pod-{uuid4()}"
        self._pods[pod_id] = _SimulatedPod(created_at=self._clock())
        logger.info("simulated pod created: job=%s profile=%s pod=%s", job_id, profile.id, pod_id)
        return pod_id

    def get_pod_status(self, pod_id: str) -> PodStatus:
        pod = self._pods[pod_id]
        if pod.deleted_at is not None:
            return PodStatus.TERMINATED
        if self._clock() - pod.created_at < self._provisioning_seconds:
            return PodStatus.PROVISIONING
        return PodStatus.RUNNING

    def delete_pod(self, pod_id: str) -> None:
        pod = self._pods[pod_id]
        if pod.deleted_at is None:
            pod.deleted_at = self._clock()
        logger.info("simulated pod deleted: pod=%s", pod_id)
