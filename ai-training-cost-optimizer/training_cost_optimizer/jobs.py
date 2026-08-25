"""Deterministic TrainingJob state transitions."""

from datetime import datetime, timezone

from .models import JobStatus, TrainingJob

ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.PLANNED: frozenset({JobStatus.QUEUED}),
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING}),
    JobStatus.RUNNING: frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.INTERRUPTED}),
    JobStatus.INTERRUPTED: frozenset({JobStatus.QUEUED}),
    JobStatus.COMPLETED: frozenset({JobStatus.STOPPED}),
    JobStatus.FAILED: frozenset(),
    JobStatus.STOPPED: frozenset(),
}


class InvalidJobTransition(ValueError):
    code = "INVALID_JOB_TRANSITION"


def transition_job(job: TrainingJob, target: JobStatus) -> TrainingJob:
    if target not in ALLOWED_TRANSITIONS[job.status]:
        raise InvalidJobTransition(f"Cannot transition {job.status.value} to {target.value}")
    return job.model_copy(update={"status": target, "updated_at": datetime.now(timezone.utc)})

