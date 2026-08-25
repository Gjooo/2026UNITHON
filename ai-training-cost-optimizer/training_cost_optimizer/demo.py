"""Explicit demo-fixture repository. Never used by production defaults."""

import json
from pathlib import Path

from .models import GPU

DEMO_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "demo_gpu_offers.json"
RUNPOD_PROVISIONING_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "runpod_provisioning_demo.json"
)


class DemoFixtureRepository:
    def __init__(self, path: Path = DEMO_FIXTURE_PATH) -> None:
        self.path = path

    def list_gpus(self) -> tuple[GPU, ...]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("fixture_type") != "DEMO_FIXTURE_DO_NOT_USE_AS_LIVE":
            raise ValueError("Refusing to load an unmarked demo GPU fixture")
        return tuple(GPU(
            **raw,
            source="DEMO_FIXTURE_DO_NOT_USE_AS_LIVE",
            price_data_type="fixture",
        ) for raw in payload["offers"])


class RunPodProvisioningDemoRepository:
    """Dry-run-only RunPod-shaped offers with explicit, never-inferred GPU IDs."""

    def list_gpus(self) -> tuple[GPU, ...]:
        payload = json.loads(RUNPOD_PROVISIONING_FIXTURE_PATH.read_text(encoding="utf-8"))
        if payload.get("fixture_type") != "RUNPOD_PROVISIONING_DEMO_DO_NOT_USE_AS_LIVE":
            raise ValueError("Refusing to load an unmarked provisioning fixture")
        return tuple(GPU(
            **raw,
            source="RUNPOD_PROVISIONING_DEMO_DO_NOT_USE_AS_LIVE",
            price_data_type="fixture",
        ) for raw in payload["offers"])
