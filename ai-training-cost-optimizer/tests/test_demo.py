from training_cost_optimizer.cli import main
from training_cost_optimizer.demo import DemoFixtureRepository


def test_demo_fixture_is_explicit_and_contains_cross_provider_offers():
    offers = DemoFixtureRepository().list_gpus()
    assert len(offers) >= 6
    assert {offer.name for offer in offers} >= {"RTX 4090", "A100 40GB", "H100 80GB"}
    assert len({offer.provider for offer in offers}) >= 2
    assert any(not offer.available for offer in offers)
    assert all(offer.price_data_type == "fixture" for offer in offers)
    assert all(offer.source == "DEMO_FIXTURE_DO_NOT_USE_AS_LIVE" for offer in offers)


def test_demo_cli_completes_without_credentials(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["optimizer", "demo"])
    assert main() == 0
    output = capsys.readouterr().out
    assert "DEMO FIXTURE - NOT LIVE PROVIDER DATA" in output
    assert "Recommendation:" in output
    assert "Execution Plan: PLANNED" in output
