# AI Training Cost Optimizer

첫 클라우드 GPU가 필요한 AI 개발자를 위한 비용 최적화 백엔드 MVP다. 모델, 학습 방식, 데이터셋 크기와 예산을 입력하면 필요한 VRAM을 추정하고 GPU 후보별 예상 학습시간과 **총 예상 결제액**을 비교한다. 현재는 분석, 추천, 계획 생성까지만 수행하며 실제 GPU나 학습을 실행하지 않는다.

## 기술 스택

- Python 3.10+, FastAPI, Pydantic, pytest
- 표준 라이브러리 기반 RunPod GraphQL HTTP client

## 설치와 테스트

```powershell
cd <project-root>
python -m pip install -e ".[test]"
python -m pytest -q -p no:cacheprovider
```

현재 인수인계 기준 전체 테스트 결과는 `80 passed`다.

## Credential 없는 Demo

```powershell
python -m training_cost_optimizer.cli demo
```

이 명령은 `fixtures/demo_gpu_offers.json`만 사용한다. 모든 Provider와 가격은 `DEMO/FIXTURE`이며 라이브 데이터가 아니다. production service는 fixture로 자동 fallback하지 않는다.

```text
TrainingRequest → Workload Analyzer → VRAM 필터 → 시간/비용 추정
→ Agent fee → 예산 비교 → 추천 → PLANNED Execution Plan
```

## FastAPI

```powershell
python -m uvicorn training_cost_optimizer.api:app --reload
```

- Swagger: `http://127.0.0.1:8000/docs`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`
- Health: `http://127.0.0.1:8000/health`

엔드포인트는 `/health`, `/providers`, `/gpus`, `/analyze`, `/optimize`, `/plan`이다. `/optimize` 성공 응답은 `workload`, `candidates`, `recommendation`, `pricing`, `budget`, `estimation_notes`, `assumptions`로 구분된다. 오류는 `{"error":{"code","message","details"}}` 구조다.

## 환경변수

- `RUNPOD_API_KEY`: RunPod 공식 API 인증
- `USD_TO_KRW_RATE`: 설정 환율이며 실시간 환율이 아님
- `AGENT_FEE_RATE`: 별도로 표시되는 percentage agent fee
- `AGENT_FIXED_FEE_KRW`: 선택적 고정 agent fee
- `RUNPOD_DEFAULT_IMAGE`: Pod image override. 비어 있으면 문서화된 기본 image 사용
- `FRONTEND_ORIGINS`: 허용할 frontend origin의 comma-separated 목록

credential은 코드, 문서, fixture, 테스트에 저장하지 않는다. `.env.example`은 자동 로드되지 않는다.

기본 개발 CORS origin은 `localhost`와 `127.0.0.1`의 3000/5173 포트다. 배포 환경에서는 `FRONTEND_ORIGINS`를 실제 frontend origin으로 제한해야 하며 wildcard origin은 사용하지 않는다.

## Frontend API 계약

공통 입력 예시:

```json
{
  "model_name": "bert-base-uncased",
  "task_type": "fine_tuning",
  "dataset_size_gb": 2,
  "training_type": "lora",
  "max_budget_krw": 10000,
  "source_type": "manual"
}
```

`POST /analyze`는 `status`, `estimated_required_vram_gb`, `estimated_base_hours`, `estimation_notes`, `assumptions`를 반환한다.

`POST /optimize`는 다음 최상위 구조를 반환한다.

```json
{
  "workload": {},
  "candidates": [],
  "recommendation": {},
  "pricing": {
    "estimated_gpu_cost_krw": 0,
    "agent_fee_krw": 0,
    "estimated_total_charge_krw": 0,
    "gpu_price_data_type": "actual",
    "gpu_price_source": "provider source",
    "calculation_data_type": "estimated"
  },
  "budget": {},
  "estimation_notes": [],
  "assumptions": []
}
```

`POST /plan`은 `PLANNED` 또는 `NOT_PLANNABLE` 계획과 estimated duration/cost 및 planned step을 반환한다. 어떤 API endpoint도 Pod를 생성하지 않는다.

공통 오류 구조:

```json
{"error":{"code":"ERROR_CODE","message":"...","details":{}}}
```

## RunPod 라이브 조회

Provider 코드는 구현됐지만 credential을 이용한 라이브 조회는 최종 검증 전이다.

GraphQL `gpuTypes.id`는 Provider 중립적인 `provider_resource_id`로 보존되어 추천 결과까지 전달된다. 이 값을 REST `POST /v1/pods`의 `gpuTypeIds`에 전달하는 실행 코드는 구현됐지만 실제 요청은 아직 호출하지 않았다.

### Pod provisioning 안전 실행

기본 명령은 provisioning fixture로 payload만 만드는 dry-run이다. 외부 API를 호출하지 않으며 비용이 발생하지 않는다.

```powershell
python -m training_cost_optimizer.cli create-runpod-demo
```

실제 생성 기능은 구현되어 있지만 `--execute`와 정확한 `RUNPOD` 확인 입력을 모두 요구한다.

```powershell
python -m training_cost_optimizer.cli create-runpod-demo --execute
```

`--execute`에서는 fixture 추천을 거부하고 라이브 RunPod GPU 조회와 recommendation을 다시 수행한다. 모든 안전검사를 통과한 뒤 `POST https://rest.runpod.io/v1/pods`가 201로 성공해 리소스가 생성되는 시점부터 RunPod 과금이 발생할 수 있다.

기본 image는 RunPod 공식 문서 예시인 `runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04`이며 `RUNPOD_DEFAULT_IMAGE`로 변경할 수 있다. 실제 POST는 현재까지 실행하지 않았다.

```powershell
python -m training_cost_optimizer.cli fetch-runpod
python -m training_cost_optimizer.cli optimize-runpod `
  --model-name bert-base-uncased `
  --dataset-size-gb 2 `
  --training-type lora `
  --max-budget-krw 10000
```

Provider 오류 시 fixture로 fallback하지 않고 명시적 오류를 반환한다.

## 데이터 구분과 비용

- **Actual:** 라이브 API의 GPU 이름, VRAM, 시간당 가격, availability, 조회 시각
- **Fixture:** `fixtures/demo_gpu_offers.json`의 합성 시연 데이터
- **Estimated:** 필요 VRAM, 성능 계수, 시간, GPU 비용, 수수료, 총 결제액, 절감액

```text
estimated_gpu_cost_krw = price_per_hour × estimated_hours × configured exchange rate
agent_fee_krw = PricingPolicy(estimated_gpu_cost_krw)
estimated_total_charge_krw = estimated_gpu_cost_krw + agent_fee_krw
```

예산은 총 예상 결제액을 기준으로 판단한다. GPU 가격에 수수료를 숨기지 않는다.

## 구현됨

- Workload Analyzer, RunPod catalog adapter, 공통 GPU 모델
- Provider 장애 격리, VRAM/availability 필터, 완료비용 추천
- PricingPolicy, 수수료 포함 budget guard
- TrainingJob 모델과 상태 머신, MockExecutionProvider
- safety-first RunPodExecutionProvider, dry-run, human confirmation, budget/duplicate guard
- PLANNED Execution Plan, credential-free demo
- frontend-oriented API와 공통 오류 schema

## 미구현

- RunPod provisioning 라이브 최종 검증, Vast.ai Provider
- Pod status polling/start/stop/cleanup 및 training/checkpoint
- 실시간 비용 계측, DB 영속화, 코드 분석, 프론트엔드

## 다음 단계

1. 제한 권한 RunPod key로 실제 스키마와 가격 단위를 검증한다.
2. Vast.ai 공식 Provider를 구현한다.
3. TrainingJob을 SQLite/SQLAlchemy에 저장한다.
4. RunPod ExecutionProvider와 실제 budget stop을 연결한다.
5. 모델 및 GPU 성능 추정 근거를 확장한다.

## Backend freeze

현재 백엔드 MVP 기능은 동결한다. 이후에는 frontend API 계약, CORS, 직렬화 호환 또는 명백한 결함 수정처럼 frontend 연결에 필요한 최소 변경만 허용한다. 실제 유료 provisioning은 CLI의 명시적 `--execute`와 확인 절차 밖에서 호출하지 않는다.
