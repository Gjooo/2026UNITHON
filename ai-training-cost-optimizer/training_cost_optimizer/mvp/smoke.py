"""Explicitly invoked real-Runpod smoke command.

This command is deliberately kept out of the normal test suite: it creates and
deletes real Pods and therefore costs money.  It answers the Loop 5 question
"can every demo profile actually be provisioned and torn down?" before the
rehearsal, and never prints the API key or the provider GPU type ID.

    python -m training_cost_optimizer.mvp.smoke --check-env
    python -m training_cost_optimizer.mvp.smoke --confirm RUNPOD
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import Callable, Iterable, TextIO
from uuid import uuid4

from training_cost_optimizer.providers.runpod_lifecycle import (
    PodStatus,
    RunpodLifecycleError,
    RunpodLifecycleProvider,
    RunpodRestLifecycleProvider,
    Transport,
    _transport,
)

from .config import GPU_EXECUTION_PROFILES, GpuExecutionProfile, profile_for_id

RUNPOD_OPENAPI_URL = "https://rest.runpod.io/v1/openapi.json"
DEFAULT_TIMEOUT_SECONDS = 600.0
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
CONFIRMATION_PHRASE = "RUNPOD"


@dataclass(frozen=True)
class SmokeResult:
    profile_id: str
    gpu_type: str
    outcome: str
    pod_id: str | None = None
    reached_running: bool = False
    delete_requested: bool = False
    termination_confirmed: bool = False
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.outcome == "PASS"


def check_environment() -> list[str]:
    """Report every configuration problem at once, never echoing a secret."""

    problems: list[str] = []
    if not os.getenv("RUNPOD_API_KEY", "").strip():
        problems.append("RUNPOD_API_KEY is not set")
    callback_base_url = os.getenv("BACKEND_PUBLIC_BASE_URL", "").strip()
    if not callback_base_url:
        problems.append("BACKEND_PUBLIC_BASE_URL is not set")
    elif not callback_base_url.startswith("https://"):
        problems.append("BACKEND_PUBLIC_BASE_URL must be an absolute HTTPS URL")
    return problems


def offered_gpu_type_ids(
    api_key: str, *, transport: Transport = _transport, timeout: float = 20.0
) -> set[str]:
    """Read the Pod-create schema to learn which GPU types Runpod actually offers."""

    status, spec = transport(
        "GET", RUNPOD_OPENAPI_URL, None, {"Authorization": f"Bearer {api_key}"}, timeout
    )
    if status != 200:
        raise RunpodLifecycleError(f"Runpod API spec request failed with HTTP {status}")
    try:
        reference = spec["paths"]["/pods"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        schema = spec["components"]["schemas"][reference.rsplit("/", 1)[-1]]
        return set(schema["properties"]["gpuTypeIds"]["items"]["enum"])
    except (KeyError, TypeError, AttributeError) as exc:
        raise RunpodLifecycleError("Runpod API spec did not describe gpuTypeIds") from exc


def check_profiles(
    profiles: Iterable[GpuExecutionProfile],
    *,
    api_key: str,
    transport: Transport = _transport,
) -> list[str]:
    """Reject a profile Runpod cannot serve before any billable Pod is created.

    The provider GPU type ID stays out of the report; the profile ID is enough
    to find the offending constant in ``mvp/config.py``.
    """

    try:
        offered = offered_gpu_type_ids(api_key, transport=transport)
    except RunpodLifecycleError as exc:
        return [str(exc)]
    return [
        f"{profile.id} ({profile.gpu_type}): Runpod does not offer this profile's GPU type"
        for profile in profiles
        if profile.runpod_gpu_type_id not in offered
    ]


def verify_profile(
    provider: RunpodLifecycleProvider,
    profile: GpuExecutionProfile,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> SmokeResult:
    """Create one Pod, wait for RUNNING, then always delete and confirm termination."""

    job_id = f"smoke-{uuid4()}"
    try:
        pod_id = provider.create_pod(profile, job_id)
    except Exception as exc:  # noqa: BLE001 - the report is the user-facing surface
        return SmokeResult(
            profile_id=profile.id,
            gpu_type=profile.gpu_type,
            outcome="CREATE_FAILED",
            error=str(exc),
        )

    outcome = "PASS"
    error: str | None = None
    reached_running = False
    deadline = monotonic() + timeout_seconds
    while True:
        try:
            status = provider.get_pod_status(pod_id)
        except Exception as exc:  # noqa: BLE001
            outcome, error = "STATUS_FAILED", str(exc)
            break
        if status is PodStatus.RUNNING:
            reached_running = True
            break
        if status is PodStatus.FAILED:
            outcome, error = "POD_FAILED", "Runpod reported a failed Pod"
            break
        if status is PodStatus.TERMINATED:
            outcome, error = "POD_TERMINATED_EARLY", "The Pod terminated before it started"
            break
        if monotonic() >= deadline:
            outcome = "TIMEOUT"
            error = f"The Pod did not reach RUNNING within {timeout_seconds:.0f}s"
            break
        sleep(poll_interval_seconds)

    # A Pod exists from here on, so cleanup is attempted on every path.
    cleanup = _terminate(
        provider,
        pod_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        sleep=sleep,
        monotonic=monotonic,
    )
    if outcome == "PASS" and cleanup.outcome != "PASS":
        outcome, error = cleanup.outcome, cleanup.error

    return SmokeResult(
        profile_id=profile.id,
        gpu_type=profile.gpu_type,
        outcome=outcome,
        pod_id=pod_id,
        reached_running=reached_running,
        delete_requested=cleanup.delete_requested,
        termination_confirmed=cleanup.termination_confirmed,
        error=error,
    )


@dataclass(frozen=True)
class _Cleanup:
    outcome: str
    delete_requested: bool
    termination_confirmed: bool
    error: str | None = None


def _terminate(
    provider: RunpodLifecycleProvider,
    pod_id: str,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> _Cleanup:
    try:
        provider.delete_pod(pod_id)
    except Exception as exc:  # noqa: BLE001
        return _Cleanup("DELETE_FAILED", False, False, str(exc))

    deadline = monotonic() + timeout_seconds
    while True:
        try:
            status = provider.get_pod_status(pod_id)
        except Exception as exc:  # noqa: BLE001
            return _Cleanup("TERMINATION_UNCONFIRMED", True, False, str(exc))
        if status is PodStatus.TERMINATED:
            return _Cleanup("PASS", True, True)
        if monotonic() >= deadline:
            return _Cleanup(
                "TERMINATION_UNCONFIRMED",
                True,
                False,
                "Runpod did not confirm termination; check the console manually",
            )
        sleep(poll_interval_seconds)


def render_report(results: Iterable[SmokeResult]) -> str:
    lines = []
    for result in results:
        detail = (
            f"pod={result.pod_id or '-'} running={result.reached_running} "
            f"deleted={result.delete_requested} terminated={result.termination_confirmed}"
        )
        line = f"[{result.outcome}] {result.profile_id} ({result.gpu_type}) {detail}"
        if result.error:
            line += f" — {result.error}"
        lines.append(line)
    return "\n".join(lines)


def _selected_profiles(profile_ids: list[str]) -> tuple[GpuExecutionProfile, ...]:
    if not profile_ids:
        return GPU_EXECUTION_PROFILES
    return tuple(profile_for_id(profile_id) for profile_id in profile_ids)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m training_cost_optimizer.mvp.smoke",
        description="Create and delete one real Runpod Pod per demo GPU profile.",
    )
    parser.add_argument(
        "--confirm",
        default="",
        help=f"Must be '{CONFIRMATION_PHRASE}'. Real Pods are created and billed.",
    )
    parser.add_argument("--check-env", action="store_true", help="Validate configuration only.")
    parser.add_argument(
        "--profile", action="append", default=[], dest="profiles", help="Profile ID (repeatable)."
    )
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    provider_factory: Callable[[], RunpodLifecycleProvider] = RunpodRestLifecycleProvider.from_environment,
    stdout: TextIO = sys.stdout,
    sleep: Callable[[float], None] = time.sleep,
    transport: Transport = _transport,
) -> int:
    args = _parser().parse_args(argv)

    try:
        profiles = _selected_profiles(args.profiles)
    except KeyError as exc:
        print(f"Unknown profile: {exc}", file=stdout)
        return 2

    # The confirmation gate comes first so an unconfirmed run stays free of any
    # network call as well as any Pod.
    if not args.check_env and args.confirm != CONFIRMATION_PHRASE:
        print(
            "This command creates real, billable Runpod Pods.\n"
            f"Re-run with --confirm {CONFIRMATION_PHRASE} to proceed, "
            "or use --check-env to validate configuration only.",
            file=stdout,
        )
        return 2

    problems = check_environment()
    api_key = os.getenv("RUNPOD_API_KEY", "").strip()
    if api_key:
        # Free and Pod-free: the API states which GPU types it will accept.
        problems.extend(check_profiles(profiles, api_key=api_key, transport=transport))

    if args.check_env:
        if problems:
            print("Configuration problems:", file=stdout)
            for problem in problems:
                print(f"  - {problem}", file=stdout)
            return 1
        print(
            f"Configuration is valid and Runpod offers all {len(profiles)} demo GPU profile(s).",
            file=stdout,
        )
        return 0

    if problems:
        print("Refusing to create Pods while the configuration is invalid:", file=stdout)
        for problem in problems:
            print(f"  - {problem}", file=stdout)
        return 1

    try:
        provider = provider_factory()
    except RunpodLifecycleError as exc:
        print(f"Runpod is not configured: {exc}", file=stdout)
        return 1

    print(f"Verifying {len(profiles)} profile(s) against the real Runpod API.", file=stdout)
    results = [
        verify_profile(
            provider,
            profile,
            timeout_seconds=args.timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
            sleep=sleep,
        )
        for profile in profiles
    ]
    print(render_report(results), file=stdout)
    if all(result.passed for result in results):
        print("All profiles were created and terminated.", file=stdout)
        return 0
    print("Check the Runpod console for any Pod that was not confirmed terminated.", file=stdout)
    return 1


if __name__ == "__main__":  # pragma: no cover - manual operational entrypoint
    raise SystemExit(main())
