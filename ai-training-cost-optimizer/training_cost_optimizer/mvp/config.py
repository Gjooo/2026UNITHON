"""Versioned, server-only configuration for the fixed MVP workload."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


SESSION_COOKIE_NAME = "unwork_session"
SESSION_TTL_DAYS = 7
GOLDEN_PATH_VERSION = "sd15-lora-golden-path-v1"
SELECTION_POLICY_VERSION = "mvp-gpu-selection-v1"
PRICE_DATA_TYPE = "DEMO_SNAPSHOT"
ESTIMATE_DISCLAIMER = (
    "예상 시간과 GPU 비용은 데모 전 검증한 프로필 스냅샷이며 실제 청구액을 보장하지 않습니다."
)


@dataclass(frozen=True)
class FixedWorkload:
    name: str
    repository_url: str
    display_execution_command: str
    required_vram_gb: int
    max_runtime_minutes: int


@dataclass(frozen=True)
class GpuExecutionProfile:
    """A pre-validated provider profile; sensitive execution fields stay server-side."""

    id: str
    provider: str
    gpu_type: str
    runpod_gpu_type_id: str
    image_name: str
    start_command: str
    estimated_runtime_minutes: int
    estimated_gpu_cost_krw: int
    vram_gb: int


WORKLOAD = FixedWorkload(
    name="Stable Diffusion 1.5 LoRA",
    repository_url="https://github.com/example/golden-path",
    display_execution_command="./run-demo-training.sh",
    required_vram_gb=24,
    max_runtime_minutes=10,
)

# The Runpod identifiers and commands are deliberately not serialized into an
# API response. Their real availability is validated in Loop 5.
GPU_EXECUTION_PROFILES: tuple[GpuExecutionProfile, ...] = (
    GpuExecutionProfile(
        id="runpod-rtx4090-v1",
        provider="Runpod",
        gpu_type="NVIDIA RTX 4090",
        runpod_gpu_type_id="NVIDIA GeForce RTX 4090",
        image_name="unwork/sd15-lora:1",
        start_command='./run-demo-training.sh --completion-url "$UNWORK_COMPLETION_URL"',
        estimated_runtime_minutes=10,
        estimated_gpu_cost_krw=450,
        vram_gb=24,
    ),
    GpuExecutionProfile(
        id="runpod-l40s-v1",
        provider="Runpod",
        gpu_type="NVIDIA L40S",
        runpod_gpu_type_id="NVIDIA L40S",
        image_name="unwork/sd15-lora:1",
        start_command='./run-demo-training.sh --completion-url "$UNWORK_COMPLETION_URL"',
        estimated_runtime_minutes=7,
        estimated_gpu_cost_krw=650,
        vram_gb=48,
    ),
    GpuExecutionProfile(
        id="runpod-a100-v1",
        provider="Runpod",
        gpu_type="NVIDIA A100 40GB",
        runpod_gpu_type_id="NVIDIA A100-SXM4-40GB",
        image_name="unwork/sd15-lora:1",
        start_command='./run-demo-training.sh --completion-url "$UNWORK_COMPLETION_URL"',
        estimated_runtime_minutes=5,
        estimated_gpu_cost_krw=900,
        vram_gb=40,
    ),
)


def profile_for_id(profile_id: str) -> GpuExecutionProfile:
    for profile in GPU_EXECUTION_PROFILES:
        if profile.id == profile_id:
            return profile
    raise KeyError(f"Unknown MVP GPU profile: {profile_id}")


PROVIDER_MODES = ("fake", "runpod")


class MvpConfigError(RuntimeError):
    """A deployment configuration problem that must be fixed before serving traffic."""


@dataclass(frozen=True)
class MvpSettings:
    database_path: Path
    provider_mode: str
    max_runtime_minutes: int
    cookie_secure: bool


def get_settings() -> MvpSettings:
    """Read settings per service construction so tests and deployments can override them."""

    return MvpSettings(
        database_path=Path(os.getenv("MVP_DATABASE_PATH", "mvp.sqlite3")),
        provider_mode=_provider_mode(),
        max_runtime_minutes=_max_runtime_minutes(),
        cookie_secure=_cookie_secure(),
    )


def _cookie_secure() -> bool:
    """Deployments keep ``Secure``; local HTTP development must opt out explicitly.

    A ``Secure`` cookie is never sent over ``http://``, so leaving this on while
    serving the frontend from plain HTTP silently breaks every session.
    """

    raw = os.getenv("MVP_COOKIE_SECURE", "").strip().lower()
    if not raw:
        return True
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    raise MvpConfigError("MVP_COOKIE_SECURE must be true or false")


def _provider_mode() -> str:
    mode = os.getenv("MVP_PROVIDER_MODE", "fake").strip().lower() or "fake"
    if mode not in PROVIDER_MODES:
        raise MvpConfigError(
            f"MVP_PROVIDER_MODE must be one of {', '.join(PROVIDER_MODES)}"
        )
    return mode


def _max_runtime_minutes() -> int:
    raw = os.getenv("MVP_MAX_RUNTIME_MINUTES", "").strip()
    if not raw:
        return WORKLOAD.max_runtime_minutes
    try:
        minutes = int(raw)
    except ValueError as exc:
        raise MvpConfigError("MVP_MAX_RUNTIME_MINUTES must be a positive integer") from exc
    if minutes <= 0:
        raise MvpConfigError("MVP_MAX_RUNTIME_MINUTES must be a positive integer")
    return minutes
