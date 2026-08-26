"""GPU catalog abstraction and the initial mock catalog."""

from typing import Protocol, Sequence

from .models import GPU


class GPURepository(Protocol):
    def list_gpus(self) -> Sequence[GPU]: ...


MOCK_GPUS: tuple[GPU, ...] = (
    GPU(name="RTX 4090", provider="MockCloudA", vram_gb=24,
        price_per_hour=0.70, performance_score=1.0),
    GPU(name="A100 40GB", provider="MockCloudB", vram_gb=40,
        price_per_hour=1.40, performance_score=2.2),
    GPU(name="A100 80GB", provider="MockCloudB", vram_gb=80,
        price_per_hour=1.90, performance_score=2.4),
    GPU(name="H100 80GB", provider="MockCloudC", vram_gb=80,
        price_per_hour=2.80, performance_score=4.0),
)


class MockGPURepository:
    def list_gpus(self) -> Sequence[GPU]:
        return MOCK_GPUS

