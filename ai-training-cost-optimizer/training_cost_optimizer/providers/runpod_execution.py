"""Safety-first RunPod Pod provisioning. Dry-run is the default."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..jobs import transition_job
from ..models import JobStatus, TrainingJob

RUNPOD_PODS_URL = "https://rest.runpod.io/v1/pods"
RUNPOD_DOCUMENTED_DEFAULT_IMAGE = "runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04"

Transport = Callable[[str, bytes, dict[str, str], float], tuple[int, dict[str, Any]]]


class RunPodProvisioningError(RuntimeError):
    code = "RUNPOD_API_ERROR"

    def __init__(self, message: str) -> None:
        self.job: TrainingJob | None = None
        super().__init__(f"{self.code}: {message}")


class RunPodAPIKeyMissing(RunPodProvisioningError):
    code = "RUNPOD_API_KEY_MISSING"


class RunPodAuthFailed(RunPodProvisioningError):
    code = "RUNPOD_AUTH_FAILED"


class RunPodGPUUnavailable(RunPodProvisioningError):
    code = "RUNPOD_GPU_UNAVAILABLE"


class RunPodInsufficientCredit(RunPodProvisioningError):
    code = "RUNPOD_INSUFFICIENT_CREDIT"


class RunPodRateLimited(RunPodProvisioningError):
    code = "RUNPOD_RATE_LIMITED"


class BudgetTooLow(RunPodProvisioningError):
    code = "BUDGET_TOO_LOW"


class AlreadyProvisioned(RunPodProvisioningError):
    code = "ALREADY_PROVISIONED"


class InvalidProviderResourceId(RunPodProvisioningError):
    code = "INVALID_PROVIDER_RESOURCE_ID"


class ProvisioningSafetyError(RunPodProvisioningError):
    code = "PROVISIONING_SAFETY_CHECK_FAILED"


@dataclass(frozen=True)
class ProvisionResult:
    dry_run: bool
    payload: dict[str, Any]
    job: TrainingJob


def _transport(url: str, body: bytes, headers: dict[str, str], timeout: float) -> tuple[int, dict[str, Any]]:
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
        return exc.code, payload
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RunPodProvisioningError("RunPod Pod request failed") from None


class RunPodExecutionProvider:
    """Create at most one RunPod Pod per provider instance and TrainingJob."""

    def __init__(self, *, transport: Transport = _transport, timeout: float = 30.0) -> None:
        self._transport = transport
        self._timeout = timeout
        self._active_pod_id: str | None = None
        self._provisioned_job_ids: set[str] = set()

    @staticmethod
    def default_image() -> str:
        return os.getenv("RUNPOD_DEFAULT_IMAGE") or RUNPOD_DOCUMENTED_DEFAULT_IMAGE

    def build_payload(self, job: TrainingJob) -> dict[str, Any]:
        if not job.selected_provider_resource_id or not job.selected_provider_resource_id.strip():
            raise InvalidProviderResourceId("A provider-supplied RunPod gpuTypeId is required")
        return {
            "gpuTypeIds": [job.selected_provider_resource_id],
            "gpuCount": 1,
            "imageName": self.default_image(),
            "name": f"training-job-{job.id}"[:191],
            "interruptible": False,
        }

    def provision(self, job: TrainingJob, *, execute: bool = False) -> ProvisionResult:
        self._validate(job, execute=execute)
        payload = self.build_payload(job)
        if not execute:
            return ProvisionResult(dry_run=True, payload=payload, job=job)

        api_key = os.getenv("RUNPOD_API_KEY")
        if not api_key:
            raise RunPodAPIKeyMissing("RUNPOD_API_KEY is not set")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        status, response = self._transport(
            RUNPOD_PODS_URL, json.dumps(payload).encode("utf-8"), headers, self._timeout
        )
        if status != 201:
            try:
                self._raise_api_error(status, response)
            except RunPodProvisioningError as exc:
                exc.job = job.model_copy(update={
                    "provisioning_error": exc.code,
                    "updated_at": datetime.now(timezone.utc),
                })
                raise

        pod_id = response.get("id")
        if not isinstance(pod_id, str) or not pod_id:
            raise RunPodProvisioningError("RunPod success response did not include a Pod id")

        now = datetime.now(timezone.utc)
        queued = transition_job(job, JobStatus.QUEUED)
        updated = queued.model_copy(update={
            "provider_resource_instance_id": pod_id,
            "provider_gpu_type_id": job.selected_provider_resource_id,
            "cost_per_hour": self._optional_number(response.get("costPerHr")),
            "adjusted_cost_per_hour": self._optional_number(response.get("adjustedCostPerHr")),
            "desired_status": response.get("desiredStatus") if isinstance(response.get("desiredStatus"), str) else None,
            "image_name": response.get("image") if isinstance(response.get("image"), str) else payload["imageName"],
            "provisioned_at": now,
            "updated_at": now,
            "provisioning_error": None,
        })
        self._active_pod_id = pod_id
        self._provisioned_job_ids.add(job.id)
        return ProvisionResult(dry_run=False, payload=payload, job=updated)

    def _validate(self, job: TrainingJob, *, execute: bool) -> None:
        if job.selected_provider != "RunPod":
            raise ProvisioningSafetyError("Selected provider must be RunPod")
        if not job.selected_provider_resource_id:
            raise InvalidProviderResourceId("A provider-supplied RunPod gpuTypeId is required")
        if job.recommendation_status != "OK":
            raise ProvisioningSafetyError("A successful recommendation is required")
        if not job.gpu_compatible or not job.gpu_available:
            raise ProvisioningSafetyError("GPU must be compatible and available")
        if job.estimated_total_charge_krw is None or job.max_budget_krw is None:
            raise ProvisioningSafetyError("Estimated charge and max budget are required")
        if job.estimated_total_charge_krw > job.max_budget_krw:
            raise BudgetTooLow("Estimated total charge exceeds max budget")
        if job.status != JobStatus.PLANNED:
            raise ProvisioningSafetyError("TrainingJob must be PLANNED")
        if job.provider_resource_instance_id or job.id in self._provisioned_job_ids:
            raise AlreadyProvisioned("TrainingJob already has a RunPod Pod")
        if self._active_pod_id is not None:
            raise AlreadyProvisioned("This executor already manages an active RunPod Pod")
        if execute and job.provider_data_type != "actual":
            raise ProvisioningSafetyError("Real creation requires a live actual provider recommendation")

    @staticmethod
    def _raise_api_error(status: int, response: dict[str, Any]) -> None:
        provider_code = response.get("errorCode") or response.get("code")
        if provider_code in {"GPU_UNAVAILABLE", "RUNPOD_GPU_UNAVAILABLE"}:
            raise RunPodGPUUnavailable("RunPod reported that the selected GPU is unavailable")
        if provider_code in {"INSUFFICIENT_CREDIT", "RUNPOD_INSUFFICIENT_CREDIT"}:
            raise RunPodInsufficientCredit("RunPod reported insufficient account credit")
        if status == 401:
            raise RunPodAuthFailed("RunPod rejected the API credential")
        if status == 429:
            raise RunPodRateLimited("RunPod rate limit exceeded")
        if status >= 500:
            raise RunPodProvisioningError("RunPod service error")
        raise RunPodProvisioningError(f"RunPod rejected the Pod request with HTTP {status}")

    @staticmethod
    def _optional_number(value: object) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def get_status(self, job: TrainingJob) -> str:
        raise NotImplementedError("RunPod status polling is not implemented")

    def stop(self, job: TrainingJob) -> None:
        raise NotImplementedError("RunPod stop API is not implemented")

    def cleanup(self, job: TrainingJob) -> None:
        raise NotImplementedError("RunPod delete/cleanup API is not implemented")
