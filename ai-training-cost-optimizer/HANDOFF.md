# AI Training Cost Optimizer — 개발 인수인계

> 최신 상태: credential 없이 실행되는 demo/dry-run, 투명한 Agent fee, budget guard, TrainingJob 상태 머신, MockExecutionProvider와 safety-first RunPod Pod provisioning 코드까지 구현됐다. 실제 POST 검증과 Vast.ai 연동은 여전히 대기 상태다.
>
> 백엔드 MVP는 이 상태로 동결한다. 이후에는 frontend 연결을 위한 API 계약/CORS/직렬화 호환 및 명백한 결함 수정만 최소 범위로 허용한다.

## 1. 프로젝트 목적

AI 학습 작업에 필요한 GPU 조건을 추정하고, 여러 GPU 상품의 시간당 가격과 예상 처리 성능을 조합해 **전체 Job Completion Cost가 가장 낮은 실행 환경**을 추천하는 MVP다.

단순히 시간당 가격이 가장 싼 GPU를 찾는 것이 아니라 다음 질문에 답하는 것을 목표로 한다.

1. 사용자의 코드와 학습 작업이 실행 가능한가?
2. 완료까지 얼마나 걸릴 것으로 추정되는가?
3. 전체 작업 비용은 얼마로 추정되는가?

현재 단계에서는 실제 인스턴스를 생성하거나 학습을 실행하지 않는다. Workload 분석부터 추천 및 계획 생성까지가 구현 범위다.

## 2. 현재 제품 정의

사용자가 모델, 작업 유형, 학습 방식, 데이터셋 크기, 예산 등을 입력하면 시스템이 다음 작업을 수행한다.

```text
Training Request
→ Workload 분석
→ GPU 요구사항 추정
→ Provider GPU 조회
→ VRAM 및 availability 필터링
→ 예상 학습시간 계산
→ Job Completion Cost 계산
→ 예산 비교
→ 최적 GPU 추천
→ 계획 상태의 Execution Plan 생성
```

실제 GPU 가격 및 VRAM 같은 Provider 데이터와 시스템이 계산한 학습시간 및 비용 추정값은 명시적으로 구분한다.

## 3. 핵심 타겟 사용자

핵심 사용자는 **첫 클라우드 GPU가 필요한 AI 개발자**다.

구체적으로는 Colab의 성능과 실행시간 한계를 느끼기 시작했지만 다음 인프라 요소를 직접 학습하거나 관리하고 싶지 않은 사용자다.

- AWS 또는 기타 클라우드 인프라
- GPU 서버
- SSH
- CUDA
- Docker
- Provider별 GPU 상품과 서버 유형

사용자가 GPU 모델이나 VRAM을 직접 고르는 대신, 작업과 예산 중심으로 의사결정할 수 있게 하는 것이 제품 방향이다.

## 4. 현재 구현된 기능

- Pydantic 기반 `TrainingRequest` 입력 검증
- 기본 입력과 하위 호환용 advanced override 지원
- deterministic rule 기반 Workload Analyzer
- 알려진 모델 메타데이터 설정
  - 현재 `bert-base-uncased`의 추정 파라미터 수 지원
- 필요 VRAM 및 기준 학습시간 추정
- 분석 불가능 시 `ESTIMATE_UNAVAILABLE` 반환
- 공통 내부 GPU 모델 정규화
- RunPod 공식 GraphQL Provider 코드
- Provider별 오류 격리 및 복수 repository 취합 구조
- availability 및 최소 VRAM 필터링
- 성능 계수 기반 예상 학습시간 계산
- 실제/fixture 시간당 가격 기반 Job Completion Cost 계산
- 원화 환산을 위한 별도 환율 Provider
- 사용자 예산 내 후보 필터링
- 예산 내 최저 총비용 GPU 추천
- `BUDGET_TOO_LOW`, 최소 필요 예산, 예산 부족액 반환
- `NO_PROVIDER_AVAILABLE`, `NO_COMPATIBLE_GPU` 상태 처리
- 결정적 recommendation reason 생성
- 차선의 저비용 후보 대비 추정 절감액 및 절감률 계산
- 계획 전용 Execution Plan 생성
- 향후 Job lifecycle을 위한 `TrainingJob`, `JobStatus`, runtime interface
- FastAPI 엔드포인트
- RunPod 조회 및 최적화 CLI
- 외부 API를 호출하지 않는 fixture/mock 기반 테스트
- `fixtures/demo_gpu_offers.json` 기반 credential-free end-to-end demo
- GPU 사용료, Agent fee, 총 예상 결제액을 분리하는 `PricingPolicy`
- 총 예상 결제액 기준 budget 판단과 runtime `STOP_REQUIRED` decision
- deterministic TrainingJob 상태 머신
- test-only `MockExecutionProvider`
- frontend-oriented `/optimize` 응답과 공통 API 오류 schema
- `RunPodExecutionProvider`의 실제 `POST /v1/pods` 구현
- 기본 dry-run, `--execute`, 정확한 `RUNPOD` human confirmation
- provider/ID/recommendation/compatibility/availability/budget/state/duplicate 안전검사
- 프로세스 내 활성 Pod 최대 1개 제한

## 5. 아직 구현되지 않은 기능

- Vast.ai Provider
- 실제 RunPod Pod 생성 라이브 검증
- 실제 Vast.ai instance 생성
- AWS EC2 또는 기타 Provider provisioning
- 사용자 GitHub, notebook, Python script 실제 분석
- 사용자 코드 업로드 및 실행
- SSH 자동 접속
- CUDA 및 학습 환경 자동 설치
- Docker 이미지 생성 또는 실행
- 실제 모델 학습
- 실제 checkpoint 저장 및 resume
- 실시간 비용 계측
- 예산 초과 시 실제 training stop
- 실제 GPU 자동 종료
- 결과 artifact 저장
- 데이터베이스 영속화
- 사용자 인증 및 권한 관리
- 프론트엔드

## 6. 전체 프로젝트 구조와 파일 역할

```text
ai-training-cost-optimizer/
├── HANDOFF.md
├── .env.example
├── pyproject.toml
├── tests/
│   ├── test_optimizer.py
│   ├── test_plan_and_api.py
│   ├── test_recommendation.py
│   ├── test_runpod_provider.py
│   └── test_workload_analyzer.py
└── training_cost_optimizer/
    ├── __init__.py
    ├── api.py
    ├── cli.py
    ├── currency.py
    ├── pricing.py
    ├── budget.py
    ├── jobs.py
    ├── execution.py
    ├── demo.py
    ├── models.py
    ├── optimizer.py
    ├── performance.py
    ├── planning.py
    ├── recommendation.py
    ├── repository.py
    ├── service.py
    ├── analysis/
    │   ├── __init__.py
    │   ├── config.py
    │   └── workload_analyzer.py
    └── providers/
        ├── __init__.py
        ├── collector.py
        └── runpod.py
```

### 루트 파일

- `pyproject.toml`: 패키지 메타데이터, FastAPI/Pydantic/Uvicorn 의존성, pytest 설정
- `.env.example`: 필요한 환경변수 이름을 안내하는 예시 파일. 실제 credential을 저장하면 안 된다.
- `HANDOFF.md`: 현재 구현 및 운영 인수인계 문서

### 핵심 패키지

- `models.py`: Training Request, GPU, Workload Estimate, 후보, 추천 결과, Execution Plan, Training Job 모델
- `optimizer.py`: advanced 입력을 사용하는 기존 순수 optimizer. 기존 동작과 테스트를 위해 유지한다.
- `recommendation.py`: Workload Estimate와 GPU 목록을 받아 예산 기반 추천 결과 생성
- `service.py`: Analyzer, Provider collector, 환율, recommendation, planning을 연결하는 application service
- `repository.py`: `GPURepository` 프로토콜과 테스트용 Mock GPU fixture
- `performance.py`: GPU 모델별 **추정 성능 계수** 설정
- `currency.py`: 설정 기반 USD/KRW 환율 Provider 및 테스트용 고정 환율 Provider
- `pricing.py`: percentage/fixed Agent fee와 총 예상 결제액 계산
- `budget.py`: 실행 전 차단 및 실행 중 `STOP_REQUIRED` decision
- `jobs.py`: 허용된 TrainingJob 상태 전이와 잘못된 전이 차단
- `execution.py`: 향후 cloud 실행 인터페이스와 test-only MockExecutionProvider
- `demo.py`: production과 분리된 명시적 demo fixture loader
- `planning.py`: 실제 실행 없이 `PLANNED` 상태의 Execution Plan과 Training Job 생성
- `api.py`: FastAPI 앱과 HTTP 엔드포인트
- `cli.py`: RunPod 실제 조회 및 최적화 CLI

### Workload 분석

- `analysis/config.py`: VRAM, 학습량, 알려진 모델 메타데이터 등 추정 규칙을 중앙 관리
- `analysis/workload_analyzer.py`: `TrainingRequest`를 `WorkloadEstimate`로 변환

### GPU Provider

- `providers/runpod.py`: RunPod 공식 GraphQL API 호출 및 내부 GPU 모델 변환
- `providers/runpod_execution.py`: REST Pod payload, 안전검사, POST transport 및 응답 저장. status/stop/cleanup은 미구현
- `providers/collector.py`: Provider 하나의 장애가 다른 Provider 결과를 막지 않도록 오류를 격리하고 GPU 목록 취합

### 테스트

- `test_optimizer.py`: 기존 VRAM 필터와 총비용 optimizer 회귀 테스트
- `test_runpod_provider.py`: sample GraphQL 응답 변환, 오류 처리, optimizer 연결 테스트
- `test_workload_analyzer.py`: 기본/advanced/알려진 모델 workload 분석 테스트
- `test_recommendation.py`: 예산, 총 완료비용, Provider 장애, 데이터 구분 테스트
- `test_plan_and_api.py`: Execution Plan과 FastAPI 흐름 테스트

## 7. 현재 백엔드 동작 흐름

FastAPI 또는 CLI에서 `TrainingRequest`를 받으면 `OptimizationService`가 다음 순서로 실행한다.

1. `analyze_workload()` 호출
2. 분석 불가능 시 `ESTIMATE_UNAVAILABLE` 반환
3. 등록된 `GPURepository` 호출
4. Provider별 오류 격리 및 유효 GPU 목록 취합
5. 모든 Provider 실패 시 `NO_PROVIDER_AVAILABLE` 반환
6. availability와 VRAM 조건 필터링
7. GPU별 예상 시간과 총비용 계산
8. 설정 환율로 원화 추정 비용 계산
9. 예산 내 후보 선택
10. 예산 내 최저 Job Completion Cost 후보 추천
11. 예산 부족 시 `BUDGET_TOO_LOW`와 최소 예산 반환
12. `/plan`에서는 추천 결과를 계획 전용 Execution Plan으로 변환

## 8. Workload Analyzer 동작 방식

`TrainingRequest`의 기본 입력은 다음과 같다.

- `model_name`
- `task_type`
- `parameter_count_billion`
- `dataset_size_gb`
- `training_type`
- `max_budget_krw`
- `source_type`
- `source_reference`

현재 분석 순서는 다음과 같다.

1. `required_vram_gb`와 `estimated_base_hours`가 모두 있으면 advanced 사용자 추정값으로 사용한다.
2. 파라미터 수가 입력되면 이를 사용한다.
3. 파라미터 수가 없으면 알려진 모델 설정에서 모델명을 조회한다.
4. 파라미터 수를 결정할 수 없으면 임의로 추측하지 않고 `ESTIMATE_UNAVAILABLE`을 반환한다.
5. 파라미터 수, training type, dataset size, 중앙 설정 계수를 이용해 VRAM과 기준 학습시간을 계산한다.

주요 추정 규칙은 `analysis/config.py`에 모여 있다. 계산 결과에는 `estimation_notes`와 `assumptions`가 포함되며 실제 측정값으로 표시하지 않는다.

## 9. GPU Cost Optimizer 계산 방식

GPU 후보 조건:

```text
available == true
GPU VRAM >= estimated required VRAM
```

예상 학습시간:

```text
estimated_hours = estimated_base_hours / estimated_performance_factor
```

총 Job Completion Cost:

```text
estimated_total_cost_usd = actual_or_fixture_price_per_hour × estimated_hours
estimated_total_cost_krw = estimated_total_cost_usd × configured_USD_TO_KRW_RATE
```

추천 우선순위:

1. VRAM 조건 충족
2. 현재 사용 가능
3. 사용자 예산 이내
4. 예상 Job Completion Cost 최저

따라서 시간당 가격이 비싸더라도 예상 학습시간이 충분히 짧으면 추천될 수 있다.

예산 내 후보가 없으면 `BUDGET_TOO_LOW`를 반환하고 다음 정보를 제공한다.

- 가장 저렴한 실행 옵션
- 추정 최소 필요 예산
- 현재 예산과의 추정 차이

## 10. RunPod Provider 구현 상태

RunPod Provider 코드는 구현되어 있다.

- 공식 GraphQL endpoint 사용
- `gpuTypes` 조회
- `displayName`에서 GPU 이름 수집
- `memoryInGb`에서 VRAM 수집
- `lowestPrice.uninterruptablePrice`에서 시간당 가격 수집
- `stockStatus`로 availability 판단
- 내부 공통 `GPU` 모델로 변환
- VRAM, 가격, availability 또는 성능 계수가 유효하지 않은 항목 제외
- API 키 누락 및 API/GraphQL 오류를 `RUNPOD_API_ERROR`로 반환
- 오류 시 Mock 가격으로 자동 fallback하지 않음
- GraphQL `gpuTypes.id`를 추측 없이 `provider_resource_id`로 보존
- 추천 결과의 ID를 REST `POST /v1/pods`용 `gpuTypeIds` fragment로 변환하는 순수 함수 제공
- 실제 Pod 생성 요청은 아직 구현하거나 호출하지 않음

중요: `RUNPOD_API_KEY`를 이용한 실제 라이브 조회는 아직 최종 검증 전이다. 현재 개발 환경에서는 키가 설정되지 않아 라이브 호출이 `NO_PROVIDER_AVAILABLE`로 종료되는 것까지만 확인했다.

## 11. 실제 데이터와 추정 데이터 구분

### Provider에서 가져오는 실제 데이터

RunPod 라이브 API가 정상 연결된 경우 다음은 실제 Provider 데이터다.

- Provider 이름
- GPU 이름
- VRAM
- 시간당 가격
- availability
- 조회 시각
- region — Provider가 제공하는 경우

후보 응답은 `pricing_data_type="actual"`과 `pricing_source`로 출처를 표시한다.

### 시스템이 계산하는 추정 데이터

- 필요 VRAM
- 기준 학습시간
- GPU 성능 계수
- GPU별 예상 학습시간
- 총 Job Completion Cost
- 원화 환산 비용
- 예상 절감액과 절감률

이 값은 `estimation_data_type="estimated"`, notes 및 assumptions를 통해 추정값임을 표시한다.

Mock repository 가격은 `pricing_data_type="fixture"`로 표시되며 실제 가격으로 취급하지 않는다.

## 12. 필요한 환경변수

- `RUNPOD_API_KEY`: RunPod 공식 API 인증
- `USD_TO_KRW_RATE`: 비용 환산에 사용할 설정 환율
- `AGENT_FEE_RATE`: GPU 사용료와 별도로 계산하는 percentage Agent fee
- `AGENT_FIXED_FEE_KRW`: 선택적 고정 Agent fee
- `RUNPOD_DEFAULT_IMAGE`: Pod image override. 비어 있으면 공식 문서 예시 image 사용
- `FRONTEND_ORIGINS`: frontend 개발/배포 origin의 comma-separated allowlist

`USD_TO_KRW_RATE`는 실시간 환율이 아니다. 설정값임을 결과 assumptions에 표시한다.

## 13. API key 관리 방식

- API key는 `RUNPOD_API_KEY` 환경변수에서만 읽는다.
- 소스코드, 문서, fixture, 테스트에 실제 key를 저장하지 않는다.
- `.env.example`에는 변수 이름과 빈 예시만 관리한다.
- `.env.example`은 자동으로 로드되지 않는다. 실행 환경에서 환경변수를 직접 설정해야 한다.
- 로그, 오류 메시지, CLI 출력에 API key 값을 출력하지 않는다.
- 운영 환경에서는 secret manager 또는 배포 플랫폼의 secret 기능을 사용한다.

## 14. 설치 명령

PowerShell 기준:

```powershell
cd <project-root>
python -m pip install -e ".[test]"
```

## 15. 테스트 실행 명령

```powershell
cd <project-root>
python -m pytest -q -p no:cacheprovider
```

## 16. FastAPI 실행 명령

```powershell
cd <project-root>
python -m uvicorn training_cost_optimizer.api:app --reload
```

기본 주소:

- API 문서: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

지원 엔드포인트:

```text
GET  /health
GET  /providers
GET  /gpus
POST /analyze
POST /optimize
POST /plan
```

## 17. RunPod 실제 조회 명령

환경변수를 먼저 설정한다. 실제 key 값은 문서나 저장소에 기록하지 않는다.

```powershell
$env:RUNPOD_API_KEY = "<RunPod API key>"
$env:USD_TO_KRW_RATE = "<configured rate>"
```

GPU 카탈로그 조회:

```powershell
python -m training_cost_optimizer.cli fetch-runpod
```

실제 RunPod 데이터 기반 최적화 예시:

```powershell
python -m training_cost_optimizer.cli optimize-runpod `
  --model-name bert-base-uncased `
  --dataset-size-gb 2 `
  --training-type lora `
  --max-budget-krw 10000
```

## 18. 현재 테스트 결과

현재 전체 테스트 결과:

```text
80 passed
```

fixture 기반 optimizer, analyzer, recommendation, provider 변환, 수수료 포함 예산 처리, Job 상태 머신, MockExecutionProvider, budget guard, Execution Plan, FastAPI/OpenAPI 흐름이 통과한다.

## 19. 알려진 문제와 제한사항

- RunPod Provider 코드는 구현됐지만 실제 API key를 사용한 라이브 응답은 최종 검증 전이다.
- 실제 Pod 생성 POST 코드도 구현됐지만 이번 작업에서는 호출하지 않았다.
- 비용은 safety check와 human confirmation 후 `POST /v1/pods`가 성공해 리소스가 생성되는 시점부터 발생할 수 있다. dry-run과 unit test에는 비용이 없다.
- Pod status polling, start, stop, delete/cleanup은 아직 REST API와 연결되지 않았다.
- Vast.ai Provider는 아직 없다.
- 지원하는 추정 성능 계수 GPU 모델이 제한적이다. RunPod에 GPU가 있어도 성능 계수 매핑이 없으면 optimizer 후보에서 제외된다.
- 알려진 모델 메타데이터는 현재 매우 제한적이다.
- Workload Analyzer 공식은 MVP용 deterministic 추정이며 실제 benchmark로 보정되지 않았다.
- 최소 VRAM 및 최소 base-hours 규칙 때문에 작은 작업도 하한값이 적용된다.
- 환율은 실시간 데이터가 아니라 환경설정 값이다.
- savings는 선택된 후보와 차선의 저비용 후보 간 추정 차이다.
- 모든 실행 단계는 계획일 뿐 실제 provisioning이나 shutdown을 수행하지 않는다.
- 데이터베이스가 없어 Training Job이 영속화되지 않는다.
- Provider 응답 캐시, rate limit, retry/backoff가 없다.
- `.env` 자동 로딩 기능이 없다.
- 프론트엔드가 없다.
- MockExecutionProvider는 test-only이며 실제 cloud resource를 만들거나 종료하지 않는다.
- runtime budget guard는 decision만 반환하며 실제 stop API를 호출하지 않는다.

## 20. 다음 개발자가 가장 먼저 해야 할 작업 순서

1. 제한 권한의 RunPod API key로 실제 `gpuTypes` 응답을 검증한다.
2. RunPod 스키마, 가격 단위, stock status, 빈 가격 응답을 실제 데이터에 맞춰 보정한다.
3. Vast.ai 공식 API Provider를 공통 `GPU` 모델로 구현한다.
4. 두 Provider의 실제 데이터를 동시에 수집해 부분 실패 및 중복 GPU 비교를 검증한다.
5. 성능 계수 설정을 더 많은 GPU 모델로 확장하고 근거를 문서화한다.
6. Workload Analyzer 모델 메타데이터 및 추정 규칙을 확장한다.
7. SQLite/SQLAlchemy 기반 Training Job 저장과 상태 전이를 추가한다.
8. 비용 누적, budget stop, checkpoint, shutdown interface를 실제 runtime과 연결한다.
9. Provider timeout, retry/backoff, 캐시 및 관측성을 추가한다.
10. optimizer와 job 흐름이 안정된 후 프론트엔드를 구현한다.

## 다음 개발자를 위한 첫 실행 체크리스트

- [ ] 프로젝트 루트로 이동한다.
- [ ] 지원되는 Python 버전을 확인한다.
- [ ] `python -m pip install -e ".[test]"`로 의존성을 설치한다.
- [ ] `python -m pytest -q -p no:cacheprovider`를 실행해 `80 passed`를 확인한다.
- [ ] `python -m training_cost_optimizer.cli create-runpod-demo`로 비용 없는 dry-run payload를 확인한다.
- [ ] `python -m training_cost_optimizer.cli demo`로 credential-free 전체 흐름을 확인한다.
- [ ] 실제 key 값을 코드나 문서에 기록하지 않는다.
- [ ] 실행 환경에 `RUNPOD_API_KEY`를 설정한다.
- [ ] `USD_TO_KRW_RATE`가 실시간 환율이 아닌 설정값임을 확인한다.
- [ ] `python -m training_cost_optimizer.cli fetch-runpod`로 라이브 응답을 확인한다.
- [ ] GPU 이름, VRAM, 가격, stock status 필드가 예상 스키마와 일치하는지 확인한다.
- [ ] 실제 가격이 `pricing_data_type="actual"`로 표시되는지 확인한다.
- [ ] 예상 시간과 비용이 `estimated`로 구분되는지 확인한다.
- [ ] BERT 예제로 `optimize-runpod`을 실행한다.
- [ ] `python -m uvicorn training_cost_optimizer.api:app --reload`로 API를 시작한다.
- [ ] `/health`, `/providers`, `/gpus`, `/analyze`, `/optimize`, `/plan`을 순서대로 확인한다.
- [ ] Execution Plan이 실제 실행이 아닌 `PLANNED` 상태인지 확인한다.
- [ ] 라이브 검증 결과와 발견한 RunPod 스키마 차이를 테스트 fixture에 반영한다.
