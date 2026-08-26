import pytest

from training_cost_optimizer.currency import ConfiguredExchangeRateProvider
from training_cost_optimizer.pricing import PricingPolicy


def test_percentage_fee_and_total_charge_are_transparent():
    policy = PricingPolicy(percentage_rate=0.15)
    assert policy.calculate_agent_fee(10_000) == 1_500
    assert policy.calculate_total_charge(10_000) == 11_500


def test_fixed_fee_and_future_fee_waiver():
    policy = PricingPolicy(percentage_rate=0, fixed_fee_krw=500)
    assert policy.calculate_total_charge(1_000) == 1_500
    assert policy.calculate_total_charge(1_000, fee_waived=True) == 1_000


@pytest.mark.parametrize("rate", [-0.1, 1.1])
def test_invalid_fee_rate_is_rejected(rate):
    with pytest.raises(ValueError):
        PricingPolicy(percentage_rate=rate)


@pytest.mark.parametrize("value", ["not-a-number", "0", "-1"])
def test_invalid_exchange_rate_setting_is_rejected(monkeypatch, value):
    monkeypatch.setenv("USD_TO_KRW_RATE", value)
    with pytest.raises(ValueError, match="USD_TO_KRW_RATE"):
        ConfiguredExchangeRateProvider().usd_to_krw()

