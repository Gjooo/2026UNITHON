"""CLI for live RunPod catalog inspection and optimization."""

import argparse
import json

from .currency import FixedExchangeRateProvider
from .demo import DemoFixtureRepository, RunPodProvisioningDemoRepository
from .models import TrainingRequest
from .optimizer import NoCompatibleGPUError, optimize_training_cost
from .providers.runpod import RunPodAPIError, RunPodGPURepository
from .providers.runpod_execution import RunPodExecutionProvider, RunPodProvisioningError
from .planning import create_planned_job
from .service import OptimizationService


def confirm_real_runpod_creation(input_fn=input) -> bool:
    return input_fn("Type RUNPOD to confirm real GPU creation: ") == "RUNPOD"


def _print_demo() -> int:
    request = TrainingRequest(
        model_name="bert-base-uncased", task_type="fine_tuning",
        training_type="lora", dataset_size_gb=2,
        max_budget_krw=10_000, source_type="manual",
    )
    service = OptimizationService(
        [DemoFixtureRepository()], FixedExchangeRateProvider(1350)
    )
    workload = service.analyze(request)
    recommendation = service.optimize(request)
    plan = service.plan(request)
    print("=== DEMO FIXTURE - NOT LIVE PROVIDER DATA ===")
    print(f"TrainingRequest: {request.model_name}, {request.training_type}, dataset {request.dataset_size_gb:g} GB")
    print(f"Workload: estimated VRAM {workload.estimated_required_vram_gb:g} GB, estimated base-hours {workload.estimated_base_hours:g}")
    print("\nEligible GPU candidates (prices are DEMO FIXTURE values):")
    for item in recommendation.candidates:
        print(
            f"- {item.provider} | {item.gpu_name} | {item.vram_gb:g} GB | "
            f"${item.actual_price_per_hour:.2f}/h fixture | {item.estimated_hours:.3f}h estimated | "
            f"GPU KRW {item.estimated_gpu_cost_krw:.0f} + fee KRW {item.agent_fee_krw:.0f} "
            f"= charge KRW {item.estimated_total_charge_krw:.0f} | budget={item.within_budget_after_fee}"
        )
    print(f"\nRecommendation: {recommendation.recommended_provider} / {recommendation.recommended_gpu}")
    print(f"Reason: {recommendation.recommendation_reason}")
    print(f"Estimated savings: KRW {recommendation.estimated_savings_krw:.0f}")
    print(f"Execution Plan: {plan.status}, {plan.estimated_duration}")
    for step in plan.steps:
        print(f"- [{step.status}] {step.name}")
    print(plan.note)
    return 0


def _print_offer(gpu) -> None:
    print(f"\n{gpu.name}")
    print(f"VRAM: {gpu.vram_gb:g} GB")
    print(f"Price: ${gpu.price_per_hour:.4f} / hour")
    print(f"Available: {gpu.available}")
    print(f"Performance factor (estimated): {gpu.performance_score:g}")


def _create_runpod_demo(*, execute: bool) -> int:
    request = TrainingRequest(
        model_name="bert-base-uncased", task_type="fine_tuning",
        training_type="lora", dataset_size_gb=2,
        max_budget_krw=10_000, source_type="manual",
    )
    repository = RunPodGPURepository() if execute else RunPodProvisioningDemoRepository()
    service = OptimizationService([repository], FixedExchangeRateProvider(1350))
    estimate = service.analyze(request)
    recommendation = service.optimize(request)
    job = create_planned_job(request, estimate, recommendation)
    if job is None:
        print(f"Provisioning blocked: {recommendation.status}")
        print(recommendation.recommendation_reason)
        return 1

    executor = RunPodExecutionProvider()
    preview = executor.provision(job, execute=False)
    print("REAL RUNPOD CREATION REQUEST" if execute else "DRY RUN")
    if not execute:
        print("No GPU will be created. No cost will be incurred.")
    print(f"Recommended Provider: {recommendation.recommended_provider}")
    print(f"Recommended GPU: {recommendation.recommended_gpu}")
    print(f"GPU Type ID: {recommendation.recommended_provider_resource_id}")
    print(f"Estimated GPU Cost: KRW {recommendation.estimated_gpu_cost_krw:.0f}")
    print(f"Agent Fee: KRW {recommendation.agent_fee_krw:.0f}")
    print(f"Estimated Total Charge: KRW {recommendation.estimated_total_charge_krw:.0f}")
    print(f"Max Budget: KRW {recommendation.max_budget_krw:.0f}")
    print("Payload:")
    print(json.dumps(preview.payload, indent=2))
    if not execute:
        return 0

    if not confirm_real_runpod_creation():
        print("Cancelled. No Pod was created.")
        return 1
    result = executor.provision(job, execute=True)
    print(f"Pod created: {result.job.provider_resource_instance_id}")
    print("Billing may now be active in RunPod.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AI training cost optimizer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("demo", help="run an explicit credential-free DEMO fixture flow")
    subparsers.add_parser("fetch-runpod", help="print current valid RunPod offers")
    create = subparsers.add_parser(
        "create-runpod-demo",
        help="preview RunPod Pod creation; requires --execute plus confirmation for a real POST",
    )
    create.add_argument("--execute", action="store_true")
    optimize = subparsers.add_parser("optimize-runpod", help="optimize with RunPod offers")
    optimize.add_argument("--model-name", required=True)
    optimize.add_argument("--parameter-count-billion", type=float)
    optimize.add_argument("--dataset-size-gb", type=float)
    optimize.add_argument(
        "--training-type",
        choices=("full_finetuning", "lora", "qlora", "inference"),
        default="lora",
    )
    optimize.add_argument("--max-budget-krw", type=float)
    optimize.add_argument("--required-vram-gb", type=float,
                          help="advanced estimated override")
    optimize.add_argument("--estimated-base-hours", type=float,
                          help="advanced estimated override")
    args = parser.parse_args()

    if args.command == "demo":
        return _print_demo()
    if args.command == "create-runpod-demo":
        try:
            return _create_runpod_demo(execute=args.execute)
        except (RunPodAPIError, RunPodProvisioningError) as exc:
            print(str(exc))
            return 1

    repository = RunPodGPURepository()
    try:
        if args.command == "fetch-runpod":
            offers = repository.list_gpus()
            print("Provider: RunPod")
            for offer in offers:
                _print_offer(offer)
            print(f"\nValid optimizer offers: {len(offers)}")
            return 0

        request = TrainingRequest(
            model_name=args.model_name,
            parameter_count_billion=args.parameter_count_billion,
            dataset_size_gb=args.dataset_size_gb,
            training_type=args.training_type,
            max_budget_krw=args.max_budget_krw,
            required_vram_gb=args.required_vram_gb,
            estimated_base_hours=args.estimated_base_hours,
        )
        result = OptimizationService([repository]).optimize(request)
        print("Provider: RunPod")
        for candidate in result.candidates:
            print(
                f"{candidate.gpu_name}: {candidate.estimated_hours:.2f} hours, "
                f"GPU KRW {candidate.estimated_gpu_cost_krw:.0f} + "
                f"fee KRW {candidate.agent_fee_krw:.0f} = "
                f"charge KRW {candidate.estimated_total_charge_krw:.0f}, "
                f"within budget={candidate.within_budget_after_fee}"
            )
        print(f"Status: {result.status}")
        print(f"Recommended GPU: {result.recommended_gpu or 'none'}")
        print(result.recommendation_reason)
        return 0 if result.status == "OK" else 1
    except (RunPodAPIError, NoCompatibleGPUError) as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
