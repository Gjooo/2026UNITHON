from training_cost_optimizer.analysis import analyze_workload
from training_cost_optimizer.models import TrainingRequest


def test_estimates_workload_from_basic_user_inputs():
    estimate = analyze_workload(TrainingRequest(
        model_name="example-7b",
        parameter_count_billion=7,
        dataset_size_gb=2,
        training_type="qlora",
        max_budget_krw=100_000,
    ))

    assert estimate.status == "READY"
    assert estimate.estimated_required_vram_gb == 16.8
    assert estimate.estimated_base_hours == 0.84
    assert estimate.estimation_confidence == "medium"
    assert "not measurements" in estimate.assumptions[0]


def test_does_not_guess_when_workload_cannot_be_estimated():
    estimate = analyze_workload(TrainingRequest(model_name="unknown"))

    assert estimate.status == "ESTIMATE_UNAVAILABLE"
    assert estimate.estimated_required_vram_gb is None
    assert estimate.estimated_base_hours is None


def test_keeps_advanced_inputs_for_backward_compatibility():
    estimate = analyze_workload(TrainingRequest(
        model_name="advanced",
        required_vram_gb=32,
        estimated_base_hours=10,
    ))

    assert estimate.status == "READY"
    assert estimate.estimated_required_vram_gb == 32
    assert estimate.estimated_base_hours == 10


def test_known_model_metadata_allows_basic_bert_request():
    estimate = analyze_workload(TrainingRequest(
        model_name="bert-base-uncased",
        task_type="fine_tuning",
        training_type="lora",
        dataset_size_gb=2,
        max_budget_krw=10_000,
        source_type="manual",
    ))

    assert estimate.status == "READY"
    assert estimate.estimated_required_vram_gb == 8
    assert estimate.estimated_base_hours == 0.25
    assert any("0.11 billion" in item for item in estimate.assumptions)


def test_missing_dataset_uses_explicit_configured_default():
    estimate = analyze_workload(TrainingRequest(
        model_name="custom", parameter_count_billion=1, training_type="lora"
    ))
    assert estimate.status == "READY"
    assert estimate.estimation_confidence == "low"
    assert any("configured 1 GB default" in item for item in estimate.assumptions)


def test_unknown_model_with_missing_parameter_count_fails_estimation():
    estimate = analyze_workload(TrainingRequest(model_name="unknown-model"))
    assert estimate.status == "ESTIMATE_UNAVAILABLE"
