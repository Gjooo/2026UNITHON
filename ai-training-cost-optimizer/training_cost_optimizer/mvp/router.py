"""HTTP boundary for the Loop 1 anonymous-session and recommendation flow."""

from __future__ import annotations

import logging
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
)
from .domain import MvpJob, MvpServiceError, Priority, to_utc_iso
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


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    outcome: Literal["SUCCEEDED", "FAILED"]
    exit_code: int = Field(alias="exitCode")
    message: str = Field(min_length=1, max_length=500)


def get_mvp_service() -> JobApplicationService:
    try:
        settings = get_settings()
        return _default_mvp_service(
            str(settings.database_path), settings.provider_mode, settings.max_runtime_minutes
        )
    except (MvpConfigError, RunpodLifecycleError) as exc:
        logger.error("MVP execution configuration is invalid: %s", exc)
        raise MvpServiceError(
            "RUNPOD_UNAVAILABLE", "Runpod 실행 설정을 확인할 수 없습니다.", 503
        ) from exc


@lru_cache(maxsize=8)
def _default_mvp_service(
    database_path: str, provider_mode: str, max_runtime_minutes: int
) -> JobApplicationService:
    """Keep the Fake provider and background runner coherent across requests.

    ``fake`` is the explicit safe development default; ``runpod`` uses the
    server-only environment configuration after it has been validated.
    """

    repository = SQLiteMvpRepository(database_path)
    if provider_mode == "runpod":
        provider = RunpodRestLifecycleProvider.from_environment()
    else:
        provider = SimulatedRunpodLifecycleProvider()
    logger.info(
        "MVP service ready: provider_mode=%s max_runtime_minutes=%s database=%s",
        provider_mode,
        max_runtime_minutes,
        database_path,
    )
    runner = BackgroundJobRunner(JobLifecycleWorker(repository, provider))
    return JobApplicationService(repository, runner=runner, max_runtime_minutes=max_runtime_minutes)


@router.post("/session", status_code=201)
def create_session(
    request: Request,
    response: Response,
    service: JobApplicationService = Depends(get_mvp_service),
) -> dict:
    session, raw_token = service.create_or_refresh_session(request.cookies.get(SESSION_COOKIE_NAME))
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/",
    )
    return {
        "expiresAt": to_utc_iso(session.expires_at),
        # 화면이 실행 버튼을 누르기 전에 남은 횟수를 안내할 수 있게 한다.
        "executionAllowance": {
            "used": int(session.execution_used),
            "limit": SESSION_EXECUTION_LIMIT,
        },
    }


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
        "executionPlan": job.selection_snapshot,
        "status": job.status.value,
        "failureMessage": job.failure_message,
        "exitCode": job.exit_code,
        "completionLog": job.completion_log,
        "startedAt": to_utc_iso(job.started_at),
        "finishedAt": to_utc_iso(job.finished_at),
        "podTerminatedAt": to_utc_iso(job.pod_terminated_at),
    }
