"""SQLite persistence for anonymous sessions and immutable MVP job contracts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .domain import (
    AnonymousSession,
    MvpJob,
    MvpJobStatus,
    MvpServiceError,
    Priority,
    from_utc_iso,
    to_utc_iso,
)


class SQLiteMvpRepository:
    """Uses a connection per call so the future runner can safely share the database."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        if self.database_path.parent != Path("."):
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path), timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS anonymous_sessions (
                    id TEXT PRIMARY KEY,
                    session_token_hash TEXT NOT NULL UNIQUE,
                    execution_used INTEGER NOT NULL DEFAULT 0,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS training_jobs (
                    id TEXT PRIMARY KEY,
                    owner_session_id TEXT NOT NULL REFERENCES anonymous_sessions(id),
                    golden_path_version TEXT NOT NULL,
                    selection_policy_version TEXT NOT NULL,
                    max_budget_krw INTEGER NOT NULL,
                    priority TEXT NOT NULL,
                    selection_snapshot TEXT NOT NULL,
                    selected_profile_id TEXT NOT NULL,
                    gpu_type TEXT NOT NULL,
                    runpod_pod_id TEXT UNIQUE,
                    status TEXT NOT NULL,
                    requested_final_status TEXT,
                    failure_message TEXT,
                    exit_code INTEGER,
                    completion_log TEXT,
                    max_runtime_minutes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    pod_terminated_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_training_jobs_owner ON training_jobs(owner_session_id);
                CREATE INDEX IF NOT EXISTS idx_training_jobs_status ON training_jobs(status);
                """
            )

    def create_session(self, session: AnonymousSession) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO anonymous_sessions (
                    id, session_token_hash, execution_used, expires_at, created_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.token_hash,
                    int(session.execution_used),
                    to_utc_iso(session.expires_at),
                    to_utc_iso(session.created_at),
                    to_utc_iso(session.last_seen_at),
                ),
            )

    def get_session_by_token_hash(self, token_hash: str) -> AnonymousSession | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM anonymous_sessions WHERE session_token_hash = ?", (token_hash,)
            ).fetchone()
        return self._session_from_row(row) if row else None

    def refresh_session(self, *, session_id: str, expires_at: datetime, last_seen_at: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE anonymous_sessions SET expires_at = ?, last_seen_at = ? WHERE id = ?",
                (to_utc_iso(expires_at), to_utc_iso(last_seen_at), session_id),
            )

    def create_job(self, job: MvpJob) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO training_jobs (
                    id, owner_session_id, golden_path_version, selection_policy_version,
                    max_budget_krw, priority, selection_snapshot, selected_profile_id, gpu_type,
                    runpod_pod_id, status, requested_final_status, failure_message, exit_code,
                    completion_log, max_runtime_minutes, created_at, started_at, finished_at,
                    pod_terminated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.owner_session_id,
                    job.golden_path_version,
                    job.selection_policy_version,
                    job.max_budget_krw,
                    job.priority.value,
                    json.dumps(job.selection_snapshot, ensure_ascii=False, separators=(",", ":")),
                    job.selected_profile_id,
                    job.gpu_type,
                    job.runpod_pod_id,
                    job.status.value,
                    job.requested_final_status.value if job.requested_final_status else None,
                    job.failure_message,
                    job.exit_code,
                    job.completion_log,
                    job.max_runtime_minutes,
                    to_utc_iso(job.created_at),
                    to_utc_iso(job.started_at),
                    to_utc_iso(job.finished_at),
                    to_utc_iso(job.pod_terminated_at),
                ),
            )

    def get_job(self, job_id: str) -> MvpJob | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM training_jobs WHERE id = ?", (job_id,)).fetchone()
        return self._job_from_row(row) if row else None

    def get_job_for_owner(self, *, job_id: str, owner_session_id: str) -> MvpJob | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM training_jobs WHERE id = ? AND owner_session_id = ?",
                (job_id, owner_session_id),
            ).fetchone()
        return self._job_from_row(row) if row else None

    def count_jobs(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM training_jobs").fetchone()[0])

    def approve_start(
        self, *, job_id: str, session_token_hash: str, started_at: datetime
    ) -> MvpJob:
        """Atomically reserve the per-session and global single-run capacity.

        ``BEGIN IMMEDIATE`` obtains SQLite's write reservation before any
        validation, making duplicate clicks and concurrent sessions serialize
        before a worker is allowed to create a Pod.
        """

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            session_row = connection.execute(
                "SELECT * FROM anonymous_sessions WHERE session_token_hash = ?", (session_token_hash,)
            ).fetchone()
            if session_row is None:
                raise MvpServiceError("SESSION_REQUIRED", "익명 세션이 필요합니다.", 401)
            session = self._session_from_row(session_row)
            if session.expires_at <= started_at:
                raise MvpServiceError("SESSION_EXPIRED", "익명 세션이 만료되었습니다.", 401)

            job_row = connection.execute(
                "SELECT * FROM training_jobs WHERE id = ? AND owner_session_id = ?",
                (job_id, session.id),
            ).fetchone()
            if job_row is None:
                raise MvpServiceError("JOB_NOT_FOUND", "요청한 작업을 찾을 수 없습니다.", 404)
            job = self._job_from_row(job_row)
            if job.status is not MvpJobStatus.DRAFT:
                raise MvpServiceError(
                    "INVALID_JOB_STATE", "이미 실행했거나 실행할 수 없는 작업입니다.", 409
                )
            if session.execution_used:
                raise MvpServiceError(
                    "EXECUTION_ALREADY_USED", "이 세션에서는 이미 실행을 시작했습니다.", 409
                )

            active_count = connection.execute(
                """
                SELECT COUNT(*) FROM training_jobs
                WHERE status IN (?, ?, ?)
                """,
                (
                    MvpJobStatus.PROVISIONING.value,
                    MvpJobStatus.RUNNING.value,
                    MvpJobStatus.TERMINATING.value,
                ),
            ).fetchone()[0]
            if active_count:
                raise MvpServiceError(
                    "DEMO_BUSY", "다른 실행이 진행 중입니다. 잠시 후 다시 시도해 주세요.", 409
                )

            connection.execute(
                "UPDATE anonymous_sessions SET execution_used = 1 WHERE id = ?", (session.id,)
            )
            connection.execute(
                "UPDATE training_jobs SET status = ?, started_at = ? WHERE id = ?",
                (MvpJobStatus.PROVISIONING.value, to_utc_iso(started_at), job.id),
            )
            connection.commit()
            return MvpJob(
                **{**job.__dict__, "status": MvpJobStatus.PROVISIONING, "started_at": started_at}
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def attach_pod(self, *, job_id: str, pod_id: str) -> MvpJob:
        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE training_jobs SET runpod_pod_id = ?
                WHERE id = ? AND status = ? AND runpod_pod_id IS NULL
                """,
                (pod_id, job_id, MvpJobStatus.PROVISIONING.value),
            ).rowcount
        if updated != 1:
            raise MvpServiceError("INVALID_JOB_STATE", "Pod을 연결할 수 없는 Job 상태입니다.", 409)
        job = self.get_job(job_id)
        assert job is not None
        return job

    def mark_running(self, job_id: str) -> MvpJob:
        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE training_jobs SET status = ?
                WHERE id = ? AND status = ?
                """,
                (MvpJobStatus.RUNNING.value, job_id, MvpJobStatus.PROVISIONING.value),
            ).rowcount
        if updated != 1:
            raise MvpServiceError("INVALID_JOB_STATE", "실행 상태로 변경할 수 없습니다.", 409)
        job = self.get_job(job_id)
        assert job is not None
        return job

    def record_completion(
        self,
        *,
        job_id: str,
        requested_final_status: MvpJobStatus,
        exit_code: int,
        completion_log: str,
        failure_message: str | None,
    ) -> MvpJob:
        """Accept one callback while running and preserve its result while terminating."""

        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE training_jobs
                SET status = ?, requested_final_status = ?, exit_code = ?, completion_log = ?,
                    failure_message = ?
                WHERE id = ? AND status = ?
                """,
                (
                    MvpJobStatus.TERMINATING.value,
                    requested_final_status.value,
                    exit_code,
                    completion_log,
                    failure_message,
                    job_id,
                    MvpJobStatus.RUNNING.value,
                ),
            ).rowcount
        if updated != 1:
            if self.get_job(job_id) is None:
                raise MvpServiceError("JOB_NOT_FOUND", "요청한 작업을 찾을 수 없습니다.", 404)
            raise MvpServiceError("INVALID_JOB_STATE", "현재 상태에서는 완료 결과를 기록할 수 없습니다.", 409)
        job = self.get_job(job_id)
        assert job is not None
        return job

    def request_termination(
        self,
        *,
        job_id: str,
        requested_final_status: MvpJobStatus,
        failure_message: str | None = None,
    ) -> MvpJob:
        """Begin cleanup while retaining the final result until Pod termination."""

        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE training_jobs
                SET status = ?, requested_final_status = ?,
                    failure_message = COALESCE(?, failure_message)
                WHERE id = ? AND status IN (?, ?)
                """,
                (
                    MvpJobStatus.TERMINATING.value,
                    requested_final_status.value,
                    failure_message,
                    job_id,
                    MvpJobStatus.PROVISIONING.value,
                    MvpJobStatus.RUNNING.value,
                ),
            ).rowcount
        if updated != 1:
            if self.get_job(job_id) is None:
                raise MvpServiceError("JOB_NOT_FOUND", "요청한 작업을 찾을 수 없습니다.", 404)
            raise MvpServiceError("INVALID_JOB_STATE", "현재 상태에서는 중단할 수 없습니다.", 409)
        job = self.get_job(job_id)
        assert job is not None
        return job

    def fail_before_pod(self, *, job_id: str, failure_message: str, finished_at: datetime) -> MvpJob:
        """Finish a provisioning failure only when no provider resource exists."""

        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE training_jobs
                SET status = ?, requested_final_status = ?, failure_message = ?, finished_at = ?
                WHERE id = ? AND status = ? AND runpod_pod_id IS NULL
                """,
                (
                    MvpJobStatus.FAILED.value,
                    MvpJobStatus.FAILED.value,
                    failure_message,
                    to_utc_iso(finished_at),
                    job_id,
                    MvpJobStatus.PROVISIONING.value,
                ),
            ).rowcount
        if updated != 1:
            raise MvpServiceError("INVALID_JOB_STATE", "Pod 생성 실패를 기록할 수 없습니다.", 409)
        job = self.get_job(job_id)
        assert job is not None
        return job

    def record_termination_error(self, *, job_id: str, failure_message: str) -> None:
        """Keep retrying cleanup while exposing a short operational error."""

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE training_jobs SET failure_message = ?
                WHERE id = ? AND status = ?
                """,
                (failure_message, job_id, MvpJobStatus.TERMINATING.value),
            )

    def finalize_terminated(self, *, job_id: str, terminated_at: datetime) -> MvpJob:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT requested_final_status FROM training_jobs WHERE id = ? AND status = ?",
                (job_id, MvpJobStatus.TERMINATING.value),
            ).fetchone()
            if row is None or row["requested_final_status"] is None:
                raise MvpServiceError("INVALID_JOB_STATE", "종료 결과를 확정할 수 없습니다.", 409)
            final_status = MvpJobStatus(row["requested_final_status"])
            connection.execute(
                """
                UPDATE training_jobs
                SET status = ?, finished_at = ?, pod_terminated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    final_status.value,
                    to_utc_iso(terminated_at),
                    to_utc_iso(terminated_at),
                    job_id,
                    MvpJobStatus.TERMINATING.value,
                ),
            )
        job = self.get_job(job_id)
        assert job is not None
        return job

    @staticmethod
    def _session_from_row(row: sqlite3.Row) -> AnonymousSession:
        return AnonymousSession(
            id=row["id"],
            token_hash=row["session_token_hash"],
            execution_used=bool(row["execution_used"]),
            expires_at=from_utc_iso(row["expires_at"]),
            created_at=from_utc_iso(row["created_at"]),
            last_seen_at=from_utc_iso(row["last_seen_at"]),
        )

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> MvpJob:
        requested_final_status = row["requested_final_status"]
        return MvpJob(
            id=row["id"],
            owner_session_id=row["owner_session_id"],
            golden_path_version=row["golden_path_version"],
            selection_policy_version=row["selection_policy_version"],
            max_budget_krw=row["max_budget_krw"],
            priority=Priority(row["priority"]),
            selection_snapshot=json.loads(row["selection_snapshot"]),
            selected_profile_id=row["selected_profile_id"],
            gpu_type=row["gpu_type"],
            status=MvpJobStatus(row["status"]),
            runpod_pod_id=row["runpod_pod_id"],
            requested_final_status=MvpJobStatus(requested_final_status) if requested_final_status else None,
            failure_message=row["failure_message"],
            exit_code=row["exit_code"],
            completion_log=row["completion_log"],
            max_runtime_minutes=row["max_runtime_minutes"],
            created_at=from_utc_iso(row["created_at"]),
            started_at=from_utc_iso(row["started_at"]),
            finished_at=from_utc_iso(row["finished_at"]),
            pod_terminated_at=from_utc_iso(row["pod_terminated_at"]),
        )
