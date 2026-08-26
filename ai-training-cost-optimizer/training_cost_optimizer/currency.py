"""Exchange-rate boundary. The MVP rate is configured, never labeled live."""

import os
from typing import Protocol


class ExchangeRateProvider(Protocol):
    source: str

    def usd_to_krw(self) -> float: ...


class ConfiguredExchangeRateProvider:
    source = "configured_USD_TO_KRW_RATE"

    def usd_to_krw(self) -> float:
        raw = os.getenv("USD_TO_KRW_RATE", "1350")
        try:
            rate = float(raw)
        except ValueError as exc:
            raise ValueError("USD_TO_KRW_RATE must be a positive number") from exc
        if rate <= 0:
            raise ValueError("USD_TO_KRW_RATE must be a positive number")
        return rate


class FixedExchangeRateProvider:
    source = "test_fixed_rate"

    def __init__(self, rate: float) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self._rate = rate

    def usd_to_krw(self) -> float:
        return self._rate

