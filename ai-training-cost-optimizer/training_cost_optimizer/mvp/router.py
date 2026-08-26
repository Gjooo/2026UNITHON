"""HTTP boundary for the Loop 1 anonymous-session and recommendation flow."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from .config import (
    SESSION_COOKIE_NAME,
    SESSION_EXECUTION_LIMIT,
    SESSION_TTL_DAYS,
    WORKLOAD,
    MvpConfigError,
    get_settings,
    real_execution_available,
)
from .domain import ExecutionMode, MvpJob, MvpServiceError, Priority, to_utc_iso
from .credentials import SessionCredentialStore
from .repository import SQLiteMvpRepository
from .runner import BackgroundJobRunner, JobLifecycleWorker
from .simulated_provider import SimulatedRunpodLifecycleProvider
from .service import JobApplicationService
from training_cost_optimizer.providers.runpod_lifecycle import (
    RunpodLifecycleError,
    RunpodRestLifecycleProvider,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["MVP"])


class CreateJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    max_budget_krw: int = Field(gt=0, alias="maxBudgetKrw")
    priority: Priority
    # 시연 현장에서 진행자가 고른다. 기본값은 비용이 없는 시뮬레이터다.
    execution_mode: ExecutionMode = Field(
        default=ExecutionMode.SIMULATED, alias="executionMode"
    )


class ProviderCredentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_key: str = Field(min_length=1, max_length=200, alias="apiKey")


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    outcome: Literal["SUCCEEDED", "FAILED"]
    exit_code: int = Field(alias="exitCode")
    message: str = Field(min_length=1, max_length=500)


def get_mvp_service() -> JobApplicationService:
    try:
        settings = get_settings()
        return _default_mvp_service(
            str(settings.database_path),
            settings.provider_mode,
            settings.max_runtime_minutes,
            settings.simulated_provisioning_seconds,
            settings.simulated_training_seconds,
            settings.poll_interval_seconds,
        )
    except (MvpConfigError, RunpodLifecycleError) as exc:
        logger.error("MVP execution configuration is invalid: %s", exc)
        raise MvpServiceError(
            "RUNPOD_UNAVAILABLE", "Runpod 실행 설정을 확인할 수 없습니다.", 503
        ) from exc


@lru_cache(maxsize=8)
def _default_mvp_service(
    database_path: str,
    provider_mode: str,
    max_runtime_minutes: int,
    simulated_provisioning_seconds: float = 6.0,
    simulated_training_seconds: float = 8.0,
    poll_interval_seconds: float = 2.0,
) -> JobApplicationService:
    """Keep the Fake provider and background runner coherent across requests.

    ``fake`` is the explicit safe development default; ``runpod`` uses the
    server-only environment configuration after it has been validated.
    """

    repository = SQLiteMvpRepository(database_path)
    credentials = SessionCredentialStore()
    simulated = SimulatedRunpodLifecycleProvider(
        provisioning_seconds=simulated_provisioning_seconds,
        training_seconds=simulated_training_seconds,
    )
    real_available = real_execution_available(provider_mode)
    callback_base_url = os.getenv("BACKEND_PUBLIC_BASE_URL", "")

    def provider_for(job):
        """작업의 모드와 소유 세션의 키로 Provider 를 만든다.

        실제 실행에 쓰는 키는 그 작업을 만든 사용자의 것이다. 팀 키로 대신하지
        않는다. 세션이 연결을 끊었거나 프로세스가 재시작돼 키가 사라지면
        여기서 실패하고, Worker 가 그 상황을 사용자에게 드러낸다.
        """

        if job.execution_mode is not ExecutionMode.REAL:
            return simulated
        api_key = credentials.api_key(session_id=job.owner_session_id, provider_id="runpod")
        if not api_key:
            raise RunpodLifecycleError("연결된 Runpod 자격증명이 없습니다")
        return RunpodRestLifecycleProvider(
            api_key=api_key, callback_base_url=callback_base_url
        )
    logger.info(
        "MVP service ready: provider_mode=%s max_runtime_minutes=%s database=%s",
        provider_mode,
        max_runtime_minutes,
        database_path,
    )
    runner = BackgroundJobRunner(
        JobLifecycleWorker(repository, provider_for), poll_interval_seconds=poll_interval_seconds
    )
    service = JobApplicationService(
        repository,
        runner=runner,
        max_runtime_minutes=max_runtime_minutes,
        real_execution_available=real_available,
        credentials=credentials,
    )

    # 시뮬레이터에는 학습 컨테이너가 없다. 그 컨테이너가 보낼 완료 신호를
    # 여기서 대신 보낸다. 없으면 작업이 실행 중 상태로 상한까지 남는다.
    def report_simulated_completion(job_id: str) -> None:
        service.record_completion(
            job_id=job_id,
            outcome="SUCCEEDED",
            exit_code=0,
            message="Training completed. 200/200 steps.",
        )

    simulated.report_completion = report_simulated_completion
    return service


@router.post("/session", status_code=201)
def create_session(
    request: Request,
    response: Response,
    service: JobApplicationService = Depends(get_mvp_service),
) -> dict:
    session, raw_token = service.create_or_refresh_session(request.cookies.get(SESSION_COOKIE_NAME))
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    return {
        "expiresAt": to_utc_iso(session.expires_at),
        # 화면이 실행 버튼을 누르기 전에 남은 횟수를 안내할 수 있게 한다.
        "executionAllowance": {
            "used": int(session.execution_used),
            "limit": SESSION_EXECUTION_LIMIT,
        },
        # 화면이 "실제 실행" 선택지를 보여줄지 판단하는 값이다.
        "realExecutionAvailable": service.real_execution_available,
    }


@router.get("/providers")
def list_providers(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    service: JobApplicationService = Depends(get_mvp_service),
) -> dict:
    """이 세션의 공급자 연결 상태만 알려준다. 키는 어떤 형태로도 반환하지 않는다."""

    connection = service.provider_connection(raw_session_token=session_token)
    return {
        "providers": [
            {
                "id": "runpod",
                "name": "Runpod",
                "connectionStatus": "CONNECTED" if connection else "NOT_CONNECTED",
                "connectedAt": to_utc_iso(connection.connected_at) if connection else None,
            }
        ]
    }


@router.post("/providers/{provider_id}/credential", status_code=status.HTTP_204_NO_CONTENT)
def connect_provider(
    provider_id: str,
    payload: ProviderCredentialRequest,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    service: JobApplicationService = Depends(get_mvp_service),
) -> Response:
    service.connect_provider(
        raw_session_token=session_token, provider_id=provider_id, api_key=payload.api_key
    )
    # 키는 메모리에만 남기고 응답에는 아무것도 담지 않는다.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/providers/{provider_id}/credential", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_provider(
    provider_id: str,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    service: JobApplicationService = Depends(get_mvp_service),
) -> Response:
    service.disconnect_provider(raw_session_token=session_token, provider_id=provider_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/jobs", status_code=201)
def create_job(
    payload: CreateJobRequest,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    service: JobApplicationService = Depends(get_mvp_service),
) -> dict:
    job = service.create_draft_job(
        raw_session_token=session_token,
        max_budget_krw=payload.max_budget_krw,
        priority=payload.priority,
        execution_mode=payload.execution_mode,
    )
    return serialize_job(job)


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    service: JobApplicationService = Depends(get_mvp_service),
) -> dict:
    return serialize_job(service.get_owned_job(raw_session_token=session_token, job_id=job_id))


@router.post("/jobs/{job_id}/start", status_code=202)
def start_job(
    job_id: str,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    service: JobApplicationService = Depends(get_mvp_service),
) -> dict:
    job = service.start_job(raw_session_token=session_token, job_id=job_id)
    return {"id": job.id, "status": job.status.value}


@router.post("/jobs/{job_id}/cancel", status_code=202)
def cancel_job(
    job_id: str,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    service: JobApplicationService = Depends(get_mvp_service),
) -> dict:
    job = service.cancel_job(raw_session_token=session_token, job_id=job_id)
    return {"id": job.id, "status": job.status.value}


@router.post("/internal/jobs/{job_id}/completion", status_code=status.HTTP_204_NO_CONTENT)
def complete_job(
    job_id: str,
    payload: CompletionRequest,
    service: JobApplicationService = Depends(get_mvp_service),
) -> Response:
    service.record_completion(
        job_id=job_id,
        outcome=payload.outcome,
        exit_code=payload.exit_code,
        message=payload.message,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def serialize_job(job: MvpJob) -> dict:
    """Expose only the approved contract, never a provider GPU ID or start command."""

    return {
        "id": job.id,
        "scenario": {
            "name": WORKLOAD.name,
            "repositoryUrl": WORKLOAD.repository_url,
            "executionCommand": WORKLOAD.display_execution_command,
            "requiredVramGb": WORKLOAD.required_vram_gb,
            "maxRuntimeMinutes": job.max_runtime_minutes,
        },
        "constraint": {
            "maxBudgetKrw": job.max_budget_krw,
            "priority": job.priority.value,
        },
        "executionMode": job.execution_mode.value,
        "executionPlan": job.selection_snapshot,
        "status": job.status.value,
        "failureMessage": job.failure_message,
        "exitCode": job.exit_code,
        "completionLog": job.completion_log,
        "startedAt": to_utc_iso(job.started_at),
        "finishedAt": to_utc_iso(job.finished_at),
        "podTerminatedAt": to_utc_iso(job.pod_terminated_at),
    }
