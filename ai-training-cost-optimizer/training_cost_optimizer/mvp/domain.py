"""MVP-only domain types and stable time handling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum


class Priority(str, Enum):
    CHEAPEST = "CHEAPEST"
    BALANCED = "BALANCED"
    FASTEST = "FASTEST"


class MvpJobStatus(str, Enum):
    DRAFT = "DRAFT"
    PROVISIONING = "PROVISIONING"
    RUNNING = "RUNNING"
    TERMINATING = "TERMINATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


FINAL_STATUSES = {
    MvpJobStatus.COMPLETED,
    MvpJobStatus.FAILED,
    MvpJobStatus.CANCELLED,
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def from_utc_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


@dataclass(frozen=True)
class AnonymousSession:
    id: str
    token_hash: str
    execution_used: bool
    expires_at: datetime
    created_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class MvpJob:
    id: str
    owner_session_id: str
    golden_path_version: str
    selection_policy_version: str
    max_budget_krw: int
    priority: Priority
    selection_snapshot: dict
    selected_profile_id: str
    gpu_type: str
    status: MvpJobStatus
    max_runtime_minutes: int
    created_at: datetime
    runpod_pod_id: str | None = None
    requested_final_status: MvpJobStatus | None = None
    failure_message: str | None = None
    exit_code: int | None = None
    completion_log: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    pod_terminated_at: datetime | None = None


class MvpServiceError(Exception):
    """A user-safe application error which maps directly to the MVP API format."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)

