"""Application service for MVP session ownership and immutable Draft jobs."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from uuid import uuid4

from .config import (
    GOLDEN_PATH_VERSION,
    SELECTION_POLICY_VERSION,
    SESSION_TTL_DAYS,
    WORKLOAD,
)
from .domain import (
    AnonymousSession,
    ExecutionMode,
    MvpJob,
    MvpJobStatus,
    MvpServiceError,
    Priority,
    utc_now,
)
from .recommendation import ProfileRecommendationService
from .repository import SQLiteMvpRepository
from .runner import FakeJobRunner, JobRunner


class JobApplicationService:
    def __init__(
        self,
        repository: SQLiteMvpRepository,
        recommendation_service: ProfileRecommendationService | None = None,
        runner: JobRunner | None = None,
        max_runtime_minutes: int = WORKLOAD.max_runtime_minutes,
        real_execution_available: bool = False,
    ) -> None:
        self.repository = repository
        self.recommendation_service = recommendation_service or ProfileRecommendationService()
        self.runner = runner or FakeJobRunner()
        # The limit is stored per Job so a configuration change never alters a
        # contract a user already approved.
        self.max_runtime_minutes = max_runtime_minutes
        # 실제 실행을 고를 수 있는지는 배포 설정이 정한다. 클라이언트가 요청해도
        # Runpod 자격증명이 없는 서버에서는 Pod 를 만들 수 없다.
        self.real_execution_available = real_execution_available

    def create_or_refresh_session(self, raw_token: str | None) -> tuple[AnonymousSession, str]:
        now = utc_now()
        expires_at = now + timedelta(days=SESSION_TTL_DAYS)
        if raw_token:
            existing = self.repository.get_session_by_token_hash(self._token_hash(raw_token))
            if existing and existing.expires_at > now:
                self.repository.refresh_session(
                    session_id=existing.id, expires_at=expires_at, last_seen_at=now
                )
                return AnonymousSession(
                    id=existing.id,
                    token_hash=existing.token_hash,
                    execution_used=existing.execution_used,
                    expires_at=expires_at,
                    created_at=existing.created_at,
                    last_seen_at=now,
                ), raw_token

        token = secrets.token_urlsafe(32)
        session = AnonymousSession(
            id=str(uuid4()),
            token_hash=self._token_hash(token),
            execution_used=False,
            expires_at=expires_at,
            created_at=now,
            last_seen_at=now,
        )
        self.repository.create_session(session)
        return session, token

    def create_draft_job(
        self,
        *,
        raw_session_token: str | None,
        max_budget_krw: int,
        priority: Priority,
        execution_mode: ExecutionMode = ExecutionMode.SIMULATED,
    ) -> MvpJob:
        session = self.require_session(raw_session_token)
        if execution_mode is ExecutionMode.REAL and not self.real_execution_available:
            raise MvpServiceError(
                "REAL_EXECUTION_UNAVAILABLE",
                "이 환경에서는 실제 GPU 실행을 사용할 수 없습니다.",
                409,
            )
        recommendation = self.recommendation_service.recommend(
            max_budget_krw=max_budget_krw, priority=priority
        )
        if recommendation is None:
            raise MvpServiceError(
                "NO_ELIGIBLE_PLAN",
                "입력한 예산 안에서 실행할 수 있는 GPU 후보가 없습니다.",
                422,
            )

        job = MvpJob(
            id=str(uuid4()),
            owner_session_id=session.id,
            golden_path_version=GOLDEN_PATH_VERSION,
            selection_policy_version=SELECTION_POLICY_VERSION,
            max_budget_krw=max_budget_krw,
            priority=priority,
            selection_snapshot=recommendation.selection_snapshot,
            selected_profile_id=recommendation.selected_profile_id,
            gpu_type=recommendation.selected_gpu_type,
            status=MvpJobStatus.DRAFT,
            max_runtime_minutes=self.max_runtime_minutes,
            execution_mode=execution_mode,
            created_at=utc_now(),
        )
        self.repository.create_job(job)
        return job

    def get_owned_job(self, *, raw_session_token: str | None, job_id: str) -> MvpJob:
        session = self.require_session(raw_session_token)
        job = self.repository.get_job_for_owner(job_id=job_id, owner_session_id=session.id)
        if job is None:
            raise MvpServiceError("JOB_NOT_FOUND", "요청한 작업을 찾을 수 없습니다.", 404)
        return job

    def start_job(self, *, raw_session_token: str | None, job_id: str) -> MvpJob:
        if not raw_session_token:
            raise MvpServiceError("SESSION_REQUIRED", "익명 세션이 필요합니다.", 401)
        job = self.repository.approve_start(
            job_id=job_id,
            session_token_hash=self._token_hash(raw_session_token),
            started_at=utc_now(),
        )
        # The repository transaction has committed by this point. A runner can
        # therefore never receive work for a failed approval.
        self.runner.start(job.id)
        return job

    def record_completion(
        self, *, job_id: str, outcome: str, exit_code: int, message: str
    ) -> MvpJob:
        succeeded = outcome == "SUCCEEDED" and exit_code == 0
        job = self.repository.record_completion(
            job_id=job_id,
            requested_final_status=(MvpJobStatus.COMPLETED if succeeded else MvpJobStatus.FAILED),
            exit_code=exit_code,
            completion_log=message,
            failure_message=None if succeeded else message,
        )
        # A lifecycle runner that is already polling stays registered; this is
        # intentionally idempotent for the background implementation.
        self.runner.start(job.id)
        return job

    def cancel_job(self, *, raw_session_token: str | None, job_id: str) -> MvpJob:
        # Ownership is checked before the transition, and the repository checks
        # the current lifecycle state as part of the update.
        self.get_owned_job(raw_session_token=raw_session_token, job_id=job_id)
        job = self.repository.request_termination(
            job_id=job_id,
            requested_final_status=MvpJobStatus.CANCELLED,
        )
        self.runner.start(job.id)
        return job

    def require_session(self, raw_token: str | None) -> AnonymousSession:
        if not raw_token:
            raise MvpServiceError("SESSION_REQUIRED", "익명 세션이 필요합니다.", 401)
        session = self.repository.get_session_by_token_hash(self._token_hash(raw_token))
        if session is None:
            raise MvpServiceError("SESSION_REQUIRED", "익명 세션이 필요합니다.", 401)
        if session.expires_at <= utc_now():
            raise MvpServiceError("SESSION_EXPIRED", "익명 세션이 만료되었습니다.", 401)
        return session

    @staticmethod
    def _token_hash(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
