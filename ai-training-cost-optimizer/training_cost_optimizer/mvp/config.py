"""Versioned, server-only configuration for the fixed MVP workload."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path


SESSION_COOKIE_NAME = "unwork_session"
SESSION_TTL_DAYS = 7
SESSION_EXECUTION_LIMIT = 1
GOLDEN_PATH_VERSION = "sd15-lora-golden-path-v1"
SELECTION_POLICY_VERSION = "mvp-gpu-selection-v1"
PRICE_DATA_TYPE = "DEMO_SNAPSHOT"
ESTIMATE_DISCLAIMER = (
    "예상 시간과 GPU 비용은 사전 검증한 실행 프로필 기준 추정치이며 실제 청구액을 보장하지 않습니다."
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
        image_name="ghcr.io/gjooo/unwork-sd15-lora:latest",
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
        image_name="ghcr.io/gjooo/unwork-sd15-lora:latest",
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
        image_name="ghcr.io/gjooo/unwork-sd15-lora:latest",
        start_command='./run-demo-training.sh --completion-url "$UNWORK_COMPLETION_URL"',
        estimated_runtime_minutes=5,
        estimated_gpu_cost_krw=900,
        vram_gb=40,
    ),
)


def profile_for_id(profile_id: str) -> GpuExecutionProfile:
    for profile in GPU_EXECUTION_PROFILES:
        if profile.id == profile_id:
            return _with_overrides(profile)
    raise KeyError(f"Unknown MVP GPU profile: {profile_id}")


def _with_overrides(profile: GpuExecutionProfile) -> GpuExecutionProfile:
    """실행 이미지와 명령을 배포 환경에서 바꿀 수 있게 한다.

    학습 이미지는 레지스트리에 올린 실제 태그로 바뀌고, 리허설에서는 학습
    대신 짧은 명령으로 Pod 생애주기만 확인하고 싶을 때가 있다. 둘 다 코드
    변경 없이 처리한다. 비교·추천에 쓰이는 값은 override 대상이 아니다.
    """

    image = os.getenv("MVP_TRAINING_IMAGE", "").strip()
    command = os.getenv("MVP_TRAINING_COMMAND", "").strip()
    if not image and not command:
        return profile
    return replace(
        profile,
        image_name=image or profile.image_name,
        start_command=command or profile.start_command,
    )


PROVIDER_MODES = ("fake", "runpod")


class MvpConfigError(RuntimeError):
    """A deployment configuration problem that must be fixed before serving traffic."""


@dataclass(frozen=True)
class MvpSettings:
    database_path: Path
    provider_mode: str
    max_runtime_minutes: int
    cookie_secure: bool
    cookie_samesite: str


def get_settings() -> MvpSettings:
    """Read settings per service construction so tests and deployments can override them."""

    return MvpSettings(
        database_path=Path(os.getenv("MVP_DATABASE_PATH", "mvp.sqlite3")),
        provider_mode=_provider_mode(),
        max_runtime_minutes=_max_runtime_minutes(),
        cookie_secure=_cookie_secure(),
        cookie_samesite=_cookie_samesite(),
    )


def _cookie_samesite() -> str:
    """같은 사이트에 배포하면 ``lax``, 다른 사이트면 ``none`` 이어야 한다.

    ``Lax`` 쿠키는 cross-site fetch 에 실려 나가지 않는다. 프런트엔드를 백엔드와
    다른 도메인에 배포하면 세션 쿠키가 아예 전송되지 않아 모든 요청이 401이 된다.
    그 경우 ``none`` 이 필요하고, 브라우저는 ``None`` 쿠키에 ``Secure`` 를 함께
    요구한다.
    """

    value = os.getenv("MVP_COOKIE_SAMESITE", "lax").strip().lower() or "lax"
    if value not in {"lax", "none", "strict"}:
        raise MvpConfigError("MVP_COOKIE_SAMESITE must be lax, none, or strict")
    if value == "none" and not _cookie_secure():
        raise MvpConfigError(
            "MVP_COOKIE_SAMESITE=none requires MVP_COOKIE_SECURE=true; "
            "browsers reject a SameSite=None cookie without Secure"
        )
    return value


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


def real_execution_available(provider_mode: str) -> bool:
    """실제 실행을 고를 수 있는 배포인지.

    ``fake`` 로 뜬 서버에는 Runpod 자격증명이 없을 수 있으므로 시뮬레이터만
    허용한다. 실제 실행을 요청받아도 Pod 를 만들 수 없다.
    """

    return provider_mode == "runpod"


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
