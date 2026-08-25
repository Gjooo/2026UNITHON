from fastapi.testclient import TestClient

from training_cost_optimizer.api import app, get_service
from training_cost_optimizer.currency import FixedExchangeRateProvider
from training_cost_optimizer.models import GPU, TrainingRequest
from training_cost_optimizer.planning import create_execution_plan
from training_cost_optimizer.service import OptimizationService


class Repository:
    def list_gpus(self):
        return (GPU(
            name="RTX 4090", provider="RunPod", vram_gb=24,
            price_per_hour=0.5, performance_score=1,
            source="RunPod official API", price_data_type="actual",
        ),)


def service() -> OptimizationService:
    return OptimizationService([Repository()], FixedExchangeRateProvider(1000))


def test_execution_plan_is_explicitly_planned_only():
    req = TrainingRequest(
        model_name="demo", required_vram_gb=20, estimated_base_hours=2,
        max_budget_krw=5000,
    )
    plan = create_execution_plan(service().optimize(req))
    assert plan.status == "PLANNED"
    assert plan.estimated_duration == "2h 0m"
    assert all(step.planned and step.status == "PLANNED" for step in plan.steps)
    assert "no GPU is provisioned" in plan.note


def test_api_flow_health_analyze_optimize_and_plan():
    app.dependency_overrides[get_service] = service
    client = TestClient(app)
    payload = {
        "model_name": "demo-7b",
        "parameter_count_billion": 7,
        "dataset_size_gb": 1,
        "training_type": "qlora",
        "max_budget_krw": 5000,
        "task_type": "fine_tuning",
        "source_type": "manual",
    }
    try:
        assert client.get("/health").json() == {"status": "ok"}
        preflight = client.options("/optimize", headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert client.post("/analyze", json=payload).json()["status"] == "READY"
        optimized = client.post("/optimize", json=payload).json()
        assert set(optimized) == {
            "workload", "candidates", "recommendation", "pricing",
            "budget", "estimation_notes", "assumptions",
        }
        assert optimized["recommendation"]["status"] == "OK"
        assert optimized["recommendation"]["provider"] == "RunPod"
        assert optimized["pricing"]["estimated_gpu_cost_krw"] > 0
        assert optimized["pricing"]["agent_fee_krw"] > 0
        assert optimized["pricing"]["estimated_total_charge_krw"] > optimized["pricing"]["estimated_gpu_cost_krw"]
        planned = client.post("/plan", json=payload).json()
        assert planned["status"] == "PLANNED"
        assert all(step["planned"] for step in planned["steps"])
    finally:
        app.dependency_overrides.clear()


class FailedRepository:
    def list_gpus(self):
        raise RuntimeError("provider failed")


class SmallRepository:
    def list_gpus(self):
        return (GPU(name="small", provider="demo", vram_gb=4,
                    price_per_hour=1, performance_score=1),)


def _client_for(repository, *, raise_server_exceptions=True):
    app.dependency_overrides[get_service] = lambda: OptimizationService(
        [repository], FixedExchangeRateProvider(1000)
    )
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_common_api_error_schemas():
    valid = {"model_name": "demo", "required_vram_gb": 8,
             "estimated_base_hours": 1, "max_budget_krw": 10000}
    cases = [
        (FailedRepository(), "/optimize", valid, 503, "NO_PROVIDER_AVAILABLE"),
        (SmallRepository(), "/optimize", valid, 422, "NO_COMPATIBLE_GPU"),
        (Repository(), "/optimize", {**valid, "max_budget_krw": 1}, 422, "BUDGET_TOO_LOW"),
        (Repository(), "/analyze", {"model_name": "unknown"}, 422, "WORKLOAD_ESTIMATION_FAILED"),
        (Repository(), "/optimize", {"model_name": ""}, 422, "INVALID_REQUEST"),
    ]
    try:
        for repository, path, payload, status, code in cases:
            client = _client_for(repository)
            response = client.post(path, json=payload)
            assert response.status_code == status
            assert response.json()["error"]["code"] == code
            assert set(response.json()["error"]) == {"code", "message", "details"}
    finally:
        app.dependency_overrides.clear()


def test_internal_error_schema_hides_exception_details():
    class BrokenService:
        def analyze(self, request):
            raise RuntimeError("secret internal detail")

    app.dependency_overrides[get_service] = lambda: BrokenService()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/analyze", json={"model_name": "bert-base-uncased"})
        assert response.status_code == 500
        assert response.json() == {"error": {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected internal error occurred.",
            "details": {},
        }}
    finally:
        app.dependency_overrides.clear()
