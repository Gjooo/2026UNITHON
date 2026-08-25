"""Documented FastAPI surface with stable frontend-oriented responses."""

import os
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .models import (APIErrorResponse, BudgetSummary, ExecutionPlan, GPU,
    OptimizeAPIResponse, PricingSummary, RecommendationResult,
    RecommendationSummary, TrainingRequest, WorkloadEstimate)
from .planning import create_execution_plan
from .service import OptimizationService

ERROR_RESPONSES = {
    422: {"model": APIErrorResponse, "description": "Request, workload, budget, or compatibility error"},
    503: {"model": APIErrorResponse, "description": "No GPU provider is available"},
    500: {"model": APIErrorResponse, "description": "Unexpected internal error"},
}

app = FastAPI(
    title="AI Training Cost Optimizer", version="0.3.0",
    description="Estimate workload requirements and recommend the lowest projected total charge. No GPU is provisioned.",
)

DEFAULT_FRONTEND_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def frontend_origins() -> list[str]:
    configured = os.getenv("FRONTEND_ORIGINS")
    if not configured:
        return list(DEFAULT_FRONTEND_ORIGINS)
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


class APIError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int, details: dict | None = None) -> None:
        self.code, self.message, self.status_code = code, message, status_code
        self.details = details or {}


@app.exception_handler(APIError)
def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})


@app.exception_handler(RequestValidationError)
def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": {"code": "INVALID_REQUEST", "message": "Request validation failed.", "details": {"errors": exc.errors()}}})


@app.exception_handler(Exception)
def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected internal error occurred.", "details": {}}})


def get_service() -> OptimizationService:
    return OptimizationService()


def _raise_for_result(result: RecommendationResult) -> None:
    mapping = {
        "NO_PROVIDER_AVAILABLE": (503, "NO_PROVIDER_AVAILABLE"),
        "BUDGET_TOO_LOW": (422, "BUDGET_TOO_LOW"),
        "NO_COMPATIBLE_GPU": (422, "NO_COMPATIBLE_GPU"),
        "ESTIMATE_UNAVAILABLE": (422, "WORKLOAD_ESTIMATION_FAILED"),
    }
    if result.status in mapping:
        status_code, code = mapping[result.status]
        raise APIError(code, result.recommendation_reason, status_code=status_code, details={
            "minimum_required_budget_krw": result.minimum_required_budget_krw,
            "budget_shortfall_krw": result.budget_shortfall_krw,
            "estimated_required_vram_gb": result.estimated_required_vram_gb,
        })


def _response(workload: WorkloadEstimate, result: RecommendationResult) -> OptimizeAPIResponse:
    selected = next(item for item in result.candidates
                    if item.gpu_name == result.recommended_gpu and item.provider == result.recommended_provider)
    return OptimizeAPIResponse(
        workload=workload, candidates=result.candidates,
        recommendation=RecommendationSummary(
            status=result.status, can_run=result.can_run,
            provider=result.recommended_provider or "", gpu=result.recommended_gpu or "",
            provider_resource_id=result.recommended_provider_resource_id,
            available_vram_gb=result.available_vram_gb or 0,
            estimated_training_hours=result.estimated_training_hours or 0,
            estimated_savings_krw=result.estimated_savings_krw or 0,
            estimated_savings_percent=result.estimated_savings_percent or 0,
            reason=result.recommendation_reason),
        pricing=PricingSummary(
            estimated_gpu_cost_krw=result.estimated_gpu_cost_krw or 0,
            agent_fee_krw=result.agent_fee_krw or 0,
            estimated_total_charge_krw=result.estimated_total_charge_krw or 0,
            gpu_price_data_type=selected.pricing_data_type,
            gpu_price_source=selected.pricing_source),
        budget=BudgetSummary(
            max_budget_krw=result.max_budget_krw,
            within_budget_after_fee=result.within_budget_after_fee,
            minimum_required_budget_krw=result.minimum_required_budget_krw,
            budget_shortfall_krw=result.budget_shortfall_krw),
        estimation_notes=result.estimation_notes, assumptions=result.assumptions)


@app.get("/health", summary="Health check", description="Verify that the API process is running.")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/providers", summary="List configured providers", description="List provider adapters without exposing credentials.")
def providers() -> list[dict[str, object]]:
    return [{"name": "RunPod", "official_api": True, "configured": bool(os.getenv("RUNPOD_API_KEY"))}]


@app.get("/gpus", response_model=list[GPU], responses=ERROR_RESPONSES,
         summary="Fetch normalized GPU offers", description="Fetch valid offers from configured official provider APIs.")
def gpus(service: OptimizationService = Depends(get_service)) -> list[GPU]:
    offers, errors = service.list_gpus()
    if not offers and errors:
        raise APIError("NO_PROVIDER_AVAILABLE", "All configured GPU providers failed.", status_code=503)
    return list(offers)


@app.post("/analyze", response_model=WorkloadEstimate, responses=ERROR_RESPONSES,
          summary="Analyze a training workload", description="Estimate VRAM and base-hours without querying a GPU provider.")
def analyze(request: TrainingRequest, service: OptimizationService = Depends(get_service)) -> WorkloadEstimate:
    workload = service.analyze(request)
    if workload.status != "READY":
        raise APIError("WORKLOAD_ESTIMATION_FAILED", "The workload could not be estimated.", status_code=422,
                       details={"estimation_notes": workload.estimation_notes})
    return workload


@app.post("/optimize", response_model=OptimizeAPIResponse, responses=ERROR_RESPONSES,
          summary="Recommend a GPU within budget", description="Compare normalized offers by projected total charge including agent fee.")
def optimize(request: TrainingRequest, service: OptimizationService = Depends(get_service)) -> OptimizeAPIResponse:
    workload, result = service.analyze(request), service.optimize(request)
    _raise_for_result(result)
    return _response(workload, result)


@app.post("/plan", response_model=ExecutionPlan, responses=ERROR_RESPONSES,
          summary="Create a planned execution", description="Create a PLANNED-only plan. No provider resource is created or stopped.")
def plan(request: TrainingRequest, service: OptimizationService = Depends(get_service)) -> ExecutionPlan:
    result = service.optimize(request)
    _raise_for_result(result)
    return create_execution_plan(result)
