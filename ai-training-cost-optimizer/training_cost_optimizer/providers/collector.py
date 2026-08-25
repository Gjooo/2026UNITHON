"""Collect independent providers while isolating individual provider failures."""

from collections.abc import Sequence
from dataclasses import dataclass

from ..models import GPU
from ..repository import GPURepository


@dataclass(frozen=True)
class CollectionResult:
    offers: tuple[GPU, ...]
    errors: tuple[str, ...]


def collect_gpu_offers(repositories: Sequence[GPURepository]) -> CollectionResult:
    offers: list[GPU] = []
    errors: list[str] = []
    for repository in repositories:
        try:
            offers.extend(repository.list_gpus())
        except Exception as exc:
            errors.append(str(exc))
    return CollectionResult(tuple(offers), tuple(errors))

