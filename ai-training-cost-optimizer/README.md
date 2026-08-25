# AI Training Cost Optimizer

첫 클라우드 GPU가 필요한 AI 개발자를 위한 비용 최적화 백엔드다. 기존 API는 모델, 학습 방식, 데이터셋 크기와 예산을 입력하면 필요한 VRAM과 GPU 후보별 예상 학습시간·**총 예상 결제액**을 비교한다. 별도 `/api/v1` MVP는 고정된 SD 1.5 LoRA workload에 대해 익명 세션, 추천 계약, Runpod 생애주기를 제공한다.

## 기술 스택

- Python 3.10+, FastAPI, Pydantic, pytest
- 표준 라이브러리 기반 RunPod GraphQL HTTP client

## 설치와 테스트

```powershell
cd <project-root>
python -m pip install -e ".[test]"
python -m pytest -q -p no:cacheprovider
```

테스트에는 실제 Runpod 호출이 포함되지 않는다.

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

기존 엔드포인트는 `/health`, `/providers`, `/gpus`, `/analyze`, `/optimize`, `/plan`이다. `/optimize` 성공 응답은 `workload`, `candidates`, `recommendation`, `pricing`, `budget`, `estimation_notes`, `assumptions`로 구분된다. 오류는 `{"error":{"code","message","details"}}` 구조다.

### 제한된 실행 MVP

MVP API의 base URL은 `/api/v1`이다.

- `POST /session`: HttpOnly anonymous-session cookie 생성·갱신
- `POST /jobs`, `GET /jobs/{id}`: 고정 GPU profile 추천 계약 Draft 생성·조회
- `POST /jobs/{id}/start`, `POST /jobs/{id}/cancel`: 승인·종료 요청
- `POST /internal/jobs/{id}/completion`: 고정 학습 컨테이너의 내부 완료 callback

기본 `MVP_PROVIDER_MODE=fake`는 비용을 발생시키지 않는다. 실제 실행에는 `MVP_PROVIDER_MODE=runpod`, `RUNPOD_API_KEY`, 공개 HTTPS `BACKEND_PUBLIC_BASE_URL`, 지속 SQLite 경로(`MVP_DATABASE_PATH`)가 필요하다. 배포 시 Uvicorn worker는 반드시 1개로 실행한다. 잘못된 실행 설정은 첫 요청이 아니라 서버 기동 시점에 실패한다.

#### 로컬 개발 모드

`fake` 모드는 Runpod을 호출하지 않고 Pod 생애주기만 흉내 낸다. Pod는 약 10초 뒤 `RUNNING`이 되고, 종료 요청을 받으면 `TERMINATED`가 된다. 로컬에는 학습 컨테이너가 없으므로 완료 화면을 보려면 완료 callback을 직접 호출한다.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/internal/jobs/<jobId>/completion \
  -H "Content-Type: application/json" \
  -d '{"outcome":"SUCCEEDED","exitCode":0,"message":"Training completed"}'
```

HTTPS가 아닌 로컬 주소로 프런트엔드를 붙일 때는 `MVP_COOKIE_SECURE=false`가 필요하다. `Secure` cookie는 `http://`로 전송되지 않아 세션이 매 요청 끊긴다. 배포 환경에서는 기본값 `true`를 유지한다.

#### 프런트엔드 흐름 리허설

```bash
python -m training_cost_optimizer.mvp.rehearsal
```

임시 DB와 `fake` 모드로 서버를 띄워 `frontend-flowchart.txt`의 추천·승인·폴링·완료 callback·취소·세션 격리·CORS를 한 번에 확인한다. Runpod 호출과 비용이 없다.

#### 실제 Runpod smoke test

이 명령만 실제 Pod를 만들고 삭제하며 **비용이 발생한다**. 일반 test suite에는 포함하지 않는다.

```bash
python -m training_cost_optimizer.mvp.smoke --check-env      # 설정과 GPU 프로필 검증, 비용 없음
python -m training_cost_optimizer.mvp.smoke --confirm RUNPOD # 프로필별 실제 Pod 생성·삭제
```

`--check-env`는 환경변수뿐 아니라 각 프로필의 GPU type을 Runpod REST 스펙과 대조한다. Pod를 만들지 않으므로 비용이 없고, Runpod이 제공하지 않는 GPU type을 쓰는 프로필은 과금 전에 걸러진다. 같은 검증은 `--confirm RUNPOD` 실행 앞에서도 수행되며, 문제가 있으면 Pod를 만들지 않고 중단한다.

`--profile <id>`로 하나만 검증할 수 있다. API 키와 Runpod GPU type ID는 출력에 포함되지 않는다.

## 환경변수

- `RUNPOD_API_KEY`: RunPod 공식 API 인증
- `USD_TO_KRW_RATE`: 설정 환율이며 실시간 환율이 아님
- `AGENT_FEE_RATE`: 별도로 표시되는 percentage agent fee
- `AGENT_FIXED_FEE_KRW`: 선택적 고정 agent fee
- `RUNPOD_DEFAULT_IMAGE`: Pod image override. 비어 있으면 문서화된 기본 image 사용
- `FRONTEND_ORIGINS`: 허용할 frontend origin의 comma-separated 목록
- `MVP_DATABASE_PATH`: MVP session·Job SQLite 파일 경로
- `MVP_PROVIDER_MODE`: `fake`(기본) 또는 `runpod`
- `MVP_MAX_RUNTIME_MINUTES`: Job 최대 실행 시간. 기본값 10이며 데모에서는 10으로 고정한다
- `MVP_COOKIE_SECURE`: 세션 cookie의 `Secure` 속성. 기본값 `true`이며 로컬 HTTP 개발에서만 `false`
- `BACKEND_PUBLIC_BASE_URL`: Runpod 컨테이너에서 접근 가능한 공개 HTTPS callback base URL
- `LOG_LEVEL`: 백엔드 운영 로그 수준. 기본값 `INFO`

credential은 코드, 문서, fixture, 테스트에 저장하지 않는다. `.env.example`은 자동 로드되지 않는다.

기본 개발 CORS origin은 `localhost`와 `127.0.0.1`의 3000/5173 포트다. 배포 환경에서는 `FRONTEND_ORIGINS`를 실제 frontend origin으로 제한해야 하며 wildcard origin은 사용하지 않는다. MVP는 세션 cookie를 함께 보내므로 `*`는 브라우저에서도 거부된다. 설정에 포함돼 있으면 무시하고 경고를 남긴다.

운영 로그에는 Job ID, Pod ID, 공개 profile ID만 남는다. Runpod API 키, GPU type ID, image, 실행 명령은 응답과 로그 어디에도 남기지 않는다.

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
