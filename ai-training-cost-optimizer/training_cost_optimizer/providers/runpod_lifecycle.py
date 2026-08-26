"""Provider lifecycle boundary for the restricted MVP execution flow."""

from __future__ import annotations

import json
import logging
import os
from enum import Enum
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from training_cost_optimizer.mvp.config import GpuExecutionProfile


logger = logging.getLogger(__name__)


class PodStatus(str, Enum):
    PROVISIONING = "PROVISIONING"
    RUNNING = "RUNNING"
    TERMINATED = "TERMINATED"
    FAILED = "FAILED"


class RunpodLifecycleProvider(Protocol):
    def create_pod(self, profile: GpuExecutionProfile, job_id: str) -> str:
        """Create the selected fixed-profile Pod and return its provider ID."""

    def get_pod_status(self, pod_id: str) -> PodStatus:
        """Return a normalized provider status only."""

    def delete_pod(self, pod_id: str) -> None:
        """Request Pod deletion. Termination is confirmed by a later status check."""


RUNPOD_PODS_URL = "https://rest.runpod.io/v1/pods"
Transport = Callable[[str, str, dict[str, Any] | None, dict[str, str], float], tuple[int, dict[str, Any]]]


class RunpodLifecycleError(RuntimeError):
    """A provider failure whose message never includes request credentials."""


def _transport(
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    headers: dict[str, str],
    timeout: float,
) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8")
            return exc.code, json.loads(raw) if raw else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return exc.code, {}
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RunpodLifecycleError("Runpod API request failed") from exc


def verify_api_key(api_key: str, *, transport: Transport = _transport, timeout: float = 15.0) -> bool:
    """키가 실제로 Runpod 에서 통하는지 확인한다.

    형식 검사만으로는 부족하다. 승인 뒤 Pod 생성 단계에서 실패하면 사용자는
    이미 비용이 발생했다고 믿는 상태다. 읽기 전용 호출이라 자원을 만들지 않는다.
    """

    if not api_key.strip():
        return False
    status, _ = transport(
        "GET", RUNPOD_PODS_URL, None, {"Authorization": f"Bearer {api_key}"}, timeout
    )
    if status == 200:
        return True
    if status in {401, 403}:
        return False
    raise RunpodLifecycleError(f"Runpod key verification failed with HTTP {status}")


class RunpodRestLifecycleProvider:
    """Translate only the fixed MVP execution contract to Runpod REST calls."""

    def __init__(
        self,
        *,
        api_key: str,
        callback_base_url: str,
        transport: Transport = _transport,
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise RunpodLifecycleError("RUNPOD_API_KEY is not set")
        parsed = urlparse(callback_base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise RunpodLifecycleError("BACKEND_PUBLIC_BASE_URL must be an absolute HTTPS URL")
        self._api_key = api_key
        self._callback_base_url = callback_base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    @classmethod
    def from_environment(cls) -> "RunpodRestLifecycleProvider":
        return cls(
            api_key=os.getenv("RUNPOD_API_KEY", ""),
            callback_base_url=os.getenv("BACKEND_PUBLIC_BASE_URL", ""),
        )

    def create_pod(self, profile: GpuExecutionProfile, job_id: str) -> str:
        # Only the public profile ID is logged; the provider GPU type ID, image,
        # start command, and API key stay out of operational output.
        logger.info("runpod create requested: job=%s profile=%s", job_id, profile.id)
        status, response = self._transport(
            "POST", RUNPOD_PODS_URL, self._create_payload(profile, job_id), self._headers(), self._timeout
        )
        if status not in {200, 201}:
            logger.error("runpod create failed: job=%s http_status=%s", job_id, status)
            self._raise_for_status("create", status)
        pod_id = response.get("id")
        if not isinstance(pod_id, str) or not pod_id:
            raise RunpodLifecycleError("Runpod create response did not include a Pod ID")
        logger.info("runpod create succeeded: job=%s pod=%s", job_id, pod_id)
        return pod_id

    def get_pod_status(self, pod_id: str) -> PodStatus:
        status, response = self._transport(
            "GET", f"{RUNPOD_PODS_URL}/{pod_id}", None, self._headers(), self._timeout
        )
        if status == 404:
            return PodStatus.TERMINATED
        if not 200 <= status < 300:
            logger.error("runpod status failed: pod=%s http_status=%s", pod_id, status)
            self._raise_for_status("status", status)
        return self._pod_status(response)

    def delete_pod(self, pod_id: str) -> None:
        status, _ = self._transport(
            "DELETE", f"{RUNPOD_PODS_URL}/{pod_id}", None, self._headers(), self._timeout
        )
        # A previously removed Pod has already met the requested outcome.
        if status == 404:
            return
        if not 200 <= status < 300:
            logger.error("runpod delete failed: pod=%s http_status=%s", pod_id, status)
            self._raise_for_status("delete", status)
        logger.info("runpod delete requested: pod=%s", pod_id)

    def _create_payload(self, profile: GpuExecutionProfile, job_id: str) -> dict[str, Any]:
        return {
            "gpuTypeIds": [profile.runpod_gpu_type_id],
            "gpuCount": 1,
            "imageName": profile.image_name,
            "dockerStartCmd": ["/bin/sh", "-lc", profile.start_command],
            "env": {"UNWORK_COMPLETION_URL": self._completion_url(job_id)},
            "name": f"unwork-mvp-{job_id}"[:191],
            "interruptible": False,
        }

    def _completion_url(self, job_id: str) -> str:
        return f"{self._callback_base_url}/api/v1/internal/jobs/{job_id}/completion"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    @classmethod
    def _pod_status(cls, response: dict[str, Any]) -> PodStatus:
        """Report what the Pod is doing, not what we asked it to do.

        Runpod sets ``desiredStatus`` to RUNNING the moment a Pod is created and
        leaves it there while the image is still being pulled — measured at over
        seven minutes for a multi-gigabyte image. Reading it as the live status
        marks a job RUNNING long before the container starts, so the screen
        claims training is under way while nothing is running yet.

        ``runtime`` is populated only once the container is actually up, so it
        is what separates provisioning from running.
        """

        desired = response.get("desiredStatus")
        desired = desired.upper() if isinstance(desired, str) else ""
        if desired == "RUNNING":
            return (
                PodStatus.RUNNING
                if isinstance(response.get("runtime"), dict)
                else PodStatus.PROVISIONING
            )
        if desired:
            return cls._normalize_status(desired)

        raw = response.get("status")
        if isinstance(raw, str) and raw:
            return cls._normalize_status(raw.upper())
        raise RunpodLifecycleError("Runpod status response did not include a recognizable status")

    @staticmethod
    def _normalize_status(raw_status: str) -> PodStatus:
        if raw_status == "RUNNING":
            return PodStatus.RUNNING
        if raw_status in {"TERMINATED", "DELETED", "STOPPED", "EXITED"}:
            return PodStatus.TERMINATED
        if raw_status in {"FAILED", "ERROR", "UNHEALTHY"}:
            return PodStatus.FAILED
        if raw_status in {"CREATED", "PROVISIONING", "PENDING", "SCHEDULED", "STARTING"}:
            return PodStatus.PROVISIONING
        raise RunpodLifecycleError(f"Unsupported Runpod Pod status: {raw_status}")

    @staticmethod
    def _raise_for_status(operation: str, status: int) -> None:
        if status == 401:
            raise RunpodLifecycleError("Runpod authentication failed")
        if status == 429:
            raise RunpodLifecycleError("Runpod rate limit reached")
        if status >= 500:
            raise RunpodLifecycleError("Runpod service is unavailable")
        raise RunpodLifecycleError(f"Runpod {operation} request failed with HTTP {status}")
