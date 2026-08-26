"""MVP estimated performance factors, separate from provider-supplied data.

These values are product assumptions for relative training-time estimation. They
are not RunPod measurements, prices, availability signals, or benchmark results.
"""

ESTIMATED_PERFORMANCE_FACTORS: dict[str, float] = {
    "NVIDIA GeForce RTX 4090": 1.0,
    "RTX 4090": 1.0,
    "NVIDIA A100 40GB PCIe": 2.2,
    "A100 40GB": 2.2,
    "NVIDIA A100 80GB PCIe": 2.4,
    "NVIDIA A100-SXM4-80GB": 2.4,
    "A100 PCIe": 2.4,
    "A100 SXM": 2.4,
    "A100 80GB": 2.4,
    "NVIDIA H100 80GB HBM3": 4.0,
    "NVIDIA H100 PCIe": 4.0,
    "H100 SXM": 4.0,
    "H100 PCIe": 4.0,
    "H100 80GB": 4.0,
}


def estimated_performance_factor(*names: object) -> float | None:
    """Return an explicitly configured estimate for a provider GPU name."""
    for name in names:
        if isinstance(name, str) and name in ESTIMATED_PERFORMANCE_FACTORS:
            return ESTIMATED_PERFORMANCE_FACTORS[name]
    return None

