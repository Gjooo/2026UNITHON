"""비용 없이 실행 한 판을 그대로 재현하는 Provider.

실제 실행에서는 Runpod 이 GPU 를 주고, 학습 컨테이너가 끝나면 스스로 완료를
알린다. 시뮬레이터에는 그 컨테이너가 없으므로 **완료를 알리는 일까지** 여기서
흉내 낸다. 그러지 않으면 작업이 실행 중 상태로 최대 실행시간까지 앉아 있고,
시연에서 결과 화면을 보여줄 수 없다.

시간은 시연에서 지켜볼 만한 길이로 잡는다. 실제 실행의 8분을 재현하는 것이
목적이 아니라, 같은 상태 전이를 같은 순서로 보여주는 것이 목적이다.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from training_cost_optimizer.providers.runpod_lifecycle import PodStatus

from .config import GpuExecutionProfile

DEFAULT_PROVISIONING_SECONDS = 6.0
DEFAULT_TRAINING_SECONDS = 8.0
DEFAULT_TERMINATION_SECONDS = 3.0

logger = logging.getLogger(__name__)


@dataclass
class _SimulatedPod:
    job_id: str
    created_at: float
    deleted_at: float | None = None


class SimulatedRunpodLifecycleProvider:
    """Pod 는 잠시 뒤 뜨고, 학습은 잠시 뒤 끝나며, 끝나면 스스로 알린다."""

    def __init__(
        self,
        *,
        provisioning_seconds: float = DEFAULT_PROVISIONING_SECONDS,
        training_seconds: float = DEFAULT_TRAINING_SECONDS,
        termination_seconds: float = DEFAULT_TERMINATION_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        report_completion: Callable[[str], None] | None = None,
    ) -> None:
        self._provisioning_seconds = provisioning_seconds
        self._training_seconds = training_seconds
        # 실제 Pod 도 삭제 요청 즉시 사라지지 않는다. 그 구간을 재현하면
        # 화면이 "자원을 정리하는 중"을 실제로 보여줄 수 있다.
        self._termination_seconds = termination_seconds
        self._clock = clock
        # 학습 컨테이너가 백엔드로 보내는 완료 신호를 대신한다.
        self.report_completion = report_completion
        self._pods: dict[str, _SimulatedPod] = {}
        self._timers: dict[str, threading.Timer] = {}

    def create_pod(self, profile: GpuExecutionProfile, job_id: str) -> str:
        pod_id = f"sim-pod-{uuid4()}"
        self._pods[pod_id] = _SimulatedPod(job_id=job_id, created_at=self._clock())
        logger.info("simulated pod created: job=%s profile=%s pod=%s", job_id, profile.id, pod_id)
        self._schedule_completion(pod_id, job_id)
        return pod_id

    def get_pod_status(self, pod_id: str) -> PodStatus:
        pod = self._pods[pod_id]
        if pod.deleted_at is not None:
            if self._clock() - pod.deleted_at < self._termination_seconds:
                return PodStatus.RUNNING  # 아직 내려가는 중
            return PodStatus.TERMINATED
        if self._clock() - pod.created_at < self._provisioning_seconds:
            return PodStatus.PROVISIONING
        return PodStatus.RUNNING

    def delete_pod(self, pod_id: str) -> None:
        pod = self._pods[pod_id]
        if pod.deleted_at is None:
            pod.deleted_at = self._clock()
        timer = self._timers.pop(pod_id, None)
        if timer is not None:
            timer.cancel()
        logger.info("simulated pod deleted: pod=%s", pod_id)

    def _schedule_completion(self, pod_id: str, job_id: str) -> None:
        """학습이 끝나는 시점에 완료를 알린다.

        중단된 작업에는 알리지 않는다. 실제 컨테이너도 삭제되면 아무것도 보내지
        못하고, 백엔드는 이미 끝난 작업의 완료 신호를 거절한다.
        """

        if self.report_completion is None:
            return

        delay = self._provisioning_seconds + self._training_seconds

        def fire() -> None:
            self._timers.pop(pod_id, None)
            pod = self._pods.get(pod_id)
            if pod is None or pod.deleted_at is not None:
                return
            try:
                self.report_completion(job_id)
                logger.info("simulated training finished: job=%s pod=%s", job_id, pod_id)
            except Exception as exc:  # noqa: BLE001 - 이미 끝난 작업이면 거절된다
                logger.info("simulated completion ignored: job=%s (%s)", job_id, exc)

        timer = threading.Timer(delay, fire)
        timer.daemon = True
        self._timers[pod_id] = timer
        timer.start()
