"""Runner boundary used by the approval transaction.

Loop 2 deliberately uses an observable no-op worker. The lifecycle worker is
introduced only after the approval and concurrency guarantees are tested.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from time import sleep
from typing import Callable, Protocol

from training_cost_optimizer.providers.runpod_lifecycle import PodStatus, RunpodLifecycleProvider

from .config import profile_for_id
from .domain import FINAL_STATUSES, ExecutionMode, MvpJobStatus, utc_now
from .repository import SQLiteMvpRepository


logger = logging.getLogger(__name__)


class JobRunner(Protocol):
    def start(self, job_id: str) -> None:
        """Register work only after the execution approval transaction commits."""


class FakeJobRunner:
    """A test/development runner that cannot create a provider resource."""

    def __init__(self) -> None:
        self.started_job_ids: list[str] = []

    def start(self, job_id: str) -> None:
        self.started_job_ids.append(job_id)


class JobLifecycleWorker:
    """One polling iteration of the provider lifecycle state machine."""

    def __init__(
        self,
        repository: SQLiteMvpRepository,
        provider: RunpodLifecycleProvider | dict[ExecutionMode, RunpodLifecycleProvider],
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.repository = repository
        # 작업마다 실행 모드와 자격증명이 다를 수 있다. 함수를 주면 작업별로
        # 해석하고, dict 나 provider 하나를 주면 그대로 쓴다.
        if isinstance(provider, dict):
            self.providers = dict(provider)
            self._resolve = lambda job: self.providers[job.execution_mode]
        elif hasattr(provider, "create_pod"):
            self.providers = {mode: provider for mode in ExecutionMode}
            self._resolve = lambda job: provider
        else:
            self.providers = {}
            self._resolve = provider
        self.clock = clock

    def provider_for(self, job) -> RunpodLifecycleProvider:
        return self._resolve(job)

    def run_once(self, job_id: str) -> MvpJobStatus:
        job = self.repository.get_job(job_id)
        if job is None:
            return MvpJobStatus.FAILED

        now = self.clock()
        try:
            provider = self.provider_for(job)
        except Exception as exc:  # noqa: BLE001 - 연결이 사라진 경우
            logger.error("job=%s provider를 준비할 수 없습니다: %s", job.id, exc)
            if job.runpod_pod_id is None and job.status is MvpJobStatus.PROVISIONING:
                return self.repository.fail_before_pod(
                    job_id=job.id,
                    failure_message="실행에 필요한 연결이 끊겼습니다.",
                    finished_at=now,
                ).status
            self.repository.record_termination_error(
                job_id=job.id, failure_message="연결이 끊겨 자원 종료를 확인할 수 없습니다."
            )
            return job.status
        if (
            job.status in {MvpJobStatus.PROVISIONING, MvpJobStatus.RUNNING}
            and job.started_at is not None
            and now >= job.started_at + timedelta(minutes=job.max_runtime_minutes)
        ):
            # 준비 중에 시간을 넘긴 경우와 학습 중에 넘긴 경우는 사용자에게
            # 뜻이 다르다. 전자는 학습이 시작조차 못 했다는 뜻이다.
            if job.status is MvpJobStatus.PROVISIONING:
                message = (
                    f"실행 환경을 준비하는 동안 최대 실행 시간 {job.max_runtime_minutes}분을 "
                    "넘겨 중단했습니다. 학습은 시작되지 않았습니다."
                )
            else:
                message = f"최대 실행 시간 {job.max_runtime_minutes}분을 초과했습니다."
            logger.warning(
                "job=%s timed out after %s minutes (pod=%s)",
                job.id,
                job.max_runtime_minutes,
                job.runpod_pod_id,
            )
            if job.runpod_pod_id is None:
                return self.repository.fail_before_pod(
                    job_id=job.id, failure_message=message, finished_at=now
                ).status
            return self.repository.request_termination(
                job_id=job.id,
                requested_final_status=MvpJobStatus.FAILED,
                failure_message=message,
            ).status

        if job.status is MvpJobStatus.PROVISIONING:
            if job.runpod_pod_id is None:
                try:
                    pod_id = provider.create_pod(profile_for_id(job.selected_profile_id), job.id)
                except Exception as exc:
                    logger.error(
                        "job=%s profile=%s pod creation failed: %s",
                        job.id,
                        job.selected_profile_id,
                        exc,
                    )
                    return self.repository.fail_before_pod(
                        job_id=job.id,
                        failure_message="실행 환경을 만들지 못했습니다.",
                        finished_at=now,
                    ).status
                logger.info(
                    "job=%s profile=%s pod=%s created", job.id, job.selected_profile_id, pod_id
                )
                job = self.repository.attach_pod(job_id=job.id, pod_id=pod_id)
            try:
                pod_status = provider.get_pod_status(job.runpod_pod_id)
            except Exception as exc:
                logger.error("job=%s pod=%s status check failed: %s", job.id, job.runpod_pod_id, exc)
                return self.repository.request_termination(
                    job_id=job.id,
                    requested_final_status=MvpJobStatus.FAILED,
                    failure_message="실행 환경 상태를 확인하지 못했습니다.",
                ).status
            if pod_status is PodStatus.RUNNING:
                logger.info("job=%s pod=%s is RUNNING", job.id, job.runpod_pod_id)
                return self.repository.mark_running(job.id).status
            if pod_status is PodStatus.FAILED:
                logger.error("job=%s pod=%s failed while provisioning", job.id, job.runpod_pod_id)
                return self.repository.request_termination(
                    job_id=job.id,
                    requested_final_status=MvpJobStatus.FAILED,
                    failure_message="실행 환경 준비에 실패했습니다.",
                ).status
            return job.status

        if job.status is MvpJobStatus.TERMINATING:
            if job.runpod_pod_id is None:
                return self.repository.finalize_terminated(
                    job_id=job.id, terminated_at=now
                ).status
            try:
                provider.delete_pod(job.runpod_pod_id)
                pod_status = provider.get_pod_status(job.runpod_pod_id)
            except Exception as exc:
                logger.error("job=%s pod=%s termination failed: %s", job.id, job.runpod_pod_id, exc)
                self.repository.record_termination_error(
                    job_id=job.id, failure_message="GPU 종료를 확인하지 못했습니다."
                )
                return job.status
            if pod_status is PodStatus.TERMINATED:
                final = self.repository.finalize_terminated(job_id=job.id, terminated_at=now)
                logger.info(
                    "job=%s pod=%s terminated, final status=%s",
                    job.id,
                    job.runpod_pod_id,
                    final.status.value,
                )
                return final.status
        return job.status


class BackgroundJobRunner:
    """Runs one polling worker per active Job in a daemon thread."""

    def __init__(self, worker: JobLifecycleWorker, *, poll_interval_seconds: float = 5) -> None:
        self.worker = worker
        self.poll_interval_seconds = poll_interval_seconds
        self._lock = threading.Lock()
        self._active_job_ids: set[str] = set()

    def start(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._active_job_ids:
                return
            self._active_job_ids.add(job_id)
        threading.Thread(target=self._run, args=(job_id,), daemon=True).start()

    def _run(self, job_id: str) -> None:
        try:
            while True:
                status = self.worker.run_once(job_id)
                if status in FINAL_STATUSES:
                    return
                sleep(self.poll_interval_seconds)
        finally:
            with self._lock:
                self._active_job_ids.discard(job_id)
