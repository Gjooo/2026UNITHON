"""RunPod GraphQL GPU catalog adapter."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..models import GPU
from ..performance import estimated_performance_factor

RUNPOD_GRAPHQL_URL = "https://api.runpod.io/graphql"
RUNPOD_GPU_TYPES_QUERY = """
query CostOptimizerGpuTypes {
  gpuTypes {
    id
    displayName
    memoryInGb
    lowestPrice(input: {gpuCount: 1}) {
      stockStatus
      uninterruptablePrice
    }
  }
}
"""

Transport = Callable[[str, bytes, float], dict[str, Any]]


class RunPodAPIError(RuntimeError):
    code = "RUNPOD_API_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(f"{self.code}: {message}")


def build_runpod_gpu_selection(provider_resource_id: str) -> dict[str, list[str]]:
    """Build the GPU selection fragment for POST /v1/pods without making a request."""
    if not isinstance(provider_resource_id, str) or not provider_resource_id.strip():
        raise ValueError("A provider-supplied RunPod gpuTypeId is required")
    return {"gpuTypeIds": [provider_resource_id]}


def _http_transport(url: str, body: bytes, timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RunPodAPIError("RunPod request failed") from exc


class RunPodGPURepository:
    """Fetch valid, currently available RunPod offers for the optimizer."""

    def __init__(
        self,
        *,
        transport: Transport = _http_transport,
        timeout: float = 15.0,
    ) -> None:
        self._transport = transport
        self._timeout = timeout

    def list_gpus(self) -> Sequence[GPU]:
        api_key = os.getenv("RUNPOD_API_KEY")
        if not api_key:
            raise RunPodAPIError("RUNPOD_API_KEY is not set")

        url = f"{RUNPOD_GRAPHQL_URL}?{urlencode({'api_key': api_key})}"
        body = json.dumps({"query": RUNPOD_GPU_TYPES_QUERY}).encode("utf-8")
        try:
            payload = self._transport(url, body, self._timeout)
        except RunPodAPIError:
            raise
        except Exception as exc:
            raise RunPodAPIError("RunPod request failed") from exc

        if payload.get("errors"):
            raise RunPodAPIError("RunPod GraphQL returned errors")

        raw_gpus = payload.get("data", {}).get("gpuTypes")
        if not isinstance(raw_gpus, list):
            raise RunPodAPIError("RunPod response has no gpuTypes list")

        fetched_at = datetime.now(timezone.utc)
        offers: list[GPU] = []
        for raw_gpu in raw_gpus:
            offer = self._to_gpu(raw_gpu, fetched_at)
            if offer is not None:
                offers.append(offer)
        return tuple(offers)

    @staticmethod
    def _to_gpu(raw_gpu: object, fetched_at: datetime) -> GPU | None:
        if not isinstance(raw_gpu, dict):
            return None

        gpu_id = raw_gpu.get("id")
        display_name = raw_gpu.get("displayName")
        name = display_name if isinstance(display_name, str) else gpu_id
        price_data = raw_gpu.get("lowestPrice")
        if (
            not isinstance(gpu_id, str)
            or not gpu_id.strip()
            or not isinstance(name, str)
            or not isinstance(price_data, dict)
        ):
            return None

        vram = raw_gpu.get("memoryInGb")
        price = price_data.get("uninterruptablePrice")
        stock_status = price_data.get("stockStatus")
        performance_score = estimated_performance_factor(gpu_id, display_name)

        if stock_status in (None, "None") or performance_score is None:
            return None
        if isinstance(vram, bool) or not isinstance(vram, (int, float)) or vram <= 0:
            return None
        if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
            return None

        return GPU(
            name=name,
            provider="RunPod",
            vram_gb=float(vram),
            price_per_hour=float(price),
            performance_score=performance_score,
            available=True,
            source="runpod_graphql_gpuTypes.lowestPrice.uninterruptablePrice",
            fetched_at=fetched_at,
            price_data_type="actual",
            provider_resource_id=gpu_id,
        )
