"""Application service for MVP session ownership and immutable Draft jobs."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Callable
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
from .credentials import ProviderConnection, SessionCredentialStore
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
        credentials: SessionCredentialStore | None = None,
        verify_credential: "Callable[[str], bool] | None" = None,
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
        self.credentials = credentials or SessionCredentialStore()
        # 키 유효성은 실제 Provider 호출로 확인한다. 테스트는 이 자리를 대체한다.
        self._verify_credential = verify_credential

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

        # 실제 실행은 사용자가 연결한 키로만 한다. 팀 키로 대신하지 않는다.
        # 화면이 "당신의 계정에서 실행됩니다"라고 말하는데 아니면 안 되기 때문이다.
        session = self.require_session(raw_session_token)
        pending = self.repository.get_job_for_owner(job_id=job_id, owner_session_id=session.id)
        if pending is not None and pending.execution_mode is ExecutionMode.REAL:
            if self.credentials.api_key(session_id=session.id, provider_id="runpod") is None:
                raise MvpServiceError(
                    "PROVIDER_NOT_CONNECTED",
                    "실제 실행을 시작하려면 먼저 Runpod 계정을 연결해 주세요.",
                    409,
                )

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

    def connect_provider(
        self, *, raw_session_token: str | None, provider_id: str, api_key: str
    ) -> ProviderConnection:
        """키를 받아 실제로 통하는지 확인한 뒤 세션에 묶는다.

        형식만 보고 저장하면 사용자는 승인 버튼을 누른 뒤에야 키가 틀렸다는 것을
        알게 된다. 그 시점에는 이미 비용이 발생했다고 믿는 상태다.
        """

        session = self.require_session(raw_session_token)
        if provider_id != "runpod":
            raise MvpServiceError("PROVIDER_NOT_SUPPORTED", "지원하지 않는 공급자입니다.", 404)

        verifier = self._verify_credential
        if verifier is None:
            from training_cost_optimizer.providers.runpod_lifecycle import verify_api_key

            verifier = verify_api_key
        try:
            valid = verifier(api_key)
        except Exception as exc:  # noqa: BLE001 - 공급자 장애와 잘못된 키를 구분한다
            raise MvpServiceError(
                "PROVIDER_UNAVAILABLE", "지금은 키를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.", 503
            ) from exc
        if not valid:
            raise MvpServiceError(
                "INVALID_PROVIDER_CREDENTIAL", "이 키로는 Runpod에 연결할 수 없습니다.", 401
            )

        return self.credentials.save(
            session_id=session.id, provider_id=provider_id, api_key=api_key
        )

    def provider_connection(
        self, *, raw_session_token: str | None, provider_id: str = "runpod"
    ) -> ProviderConnection | None:
        session = self.require_session(raw_session_token)
        return self.credentials.connection(session_id=session.id, provider_id=provider_id)

    def disconnect_provider(self, *, raw_session_token: str | None, provider_id: str) -> None:
        session = self.require_session(raw_session_token)
        self.credentials.discard(session_id=session.id, provider_id=provider_id)

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
