# UNWORK 학습 실행 Agent — MVP 백엔드 구현 계획서

## 1. 목적과 기준 문서

이 문서는 제한된 GPU 선택·실행 MVP를 실제 백엔드로 구현하기 위한 작업 계획이다. 구현 판단은 아래 문서 순서로 따른다.

1. [MVP-implementation-plan.md](MVP-implementation-plan.md)
2. [API-spec.md](API-spec.md)
3. [ERD.md](ERD.md)
4. [PRD-final.md](PRD-final.md) — 제품의 장기 방향

MVP가 증명할 한 가지는 다음이다.

> 사용자는 예산과 완료 우선순위만 정하고, Agent가 검증된 GPU 후보를 비교·선택한 뒤 Runpod 학습 실행과 Pod 종료까지 처리한다.

## 2. 구현 범위와 완료 정의

### 구현 범위

- 익명 세션 생성과 HttpOnly cookie 기반 Job 소유권
- 고정 SD 1.5 LoRA workload에 대한 2~3개 GPU 프로필 비교
- `CHEAPEST`·`BALANCED`·`FASTEST` 추천 정책과 추천 스냅샷 저장
- 추천 실행 계약의 승인, Runpod Pod 생성·상태 확인·삭제
- 10분 timeout, 성공/실패 callback, 사용자 취소
- 프런트엔드 폴링용 Job 상태 조회
- 세션당 실행 1회, 서비스 전체 활성 실행 1개

### 명시적 비범위

- 임의 Repository·명령·GPU·Provider 입력
- BYOK, 다중 Provider, 실시간 가격 조회·실제 비용 계측
- artifact, 재시도, checkpoint, OOM 재계획, 실행 대기열
- 프로세스 재시작 뒤 실행 복구와 다중 서버 인스턴스 분산 처리

### 백엔드 완료 정의

아래 API 시나리오가 Fake Runpod 테스트와 실제 Runpod smoke test에서 모두 성립하면 완료다.

```text
POST /session
→ POST /jobs { maxBudgetKrw, priority }
→ DRAFT Job의 후보 비교·추천 계약 확인
→ POST /jobs/{id}/start
→ PROVISIONING → RUNNING
→ completion callback
→ TERMINATING → COMPLETED
→ Runpod Pod 삭제 확인
```

같은 경로에서 취소, 실패 callback, timeout은 Pod 종료 확인 뒤 각각 `CANCELLED` 또는 `FAILED`가 되어야 한다.

## 3. 구현 원칙

1. **세로 흐름 우선**: 추천, 상태 저장, Pod 실행을 따로 완성하지 않는다. 사용자 흐름 하나가 끝까지 동작할 때마다 기능을 추가한다.
2. **추천 엔진 재사용**: `ai-training-cost-optimizer`의 GPU 모델, 시간·비용 계산 등 순수 로직은 재사용한다. 현재 `/analyze`, `/optimize`, `/plan` HTTP API는 MVP API가 아니다.
3. **추천 계약 불변**: Job 생성 때 계산한 후보·비용·선택 근거를 저장하고, start 시 다시 추천하거나 클라이언트 입력으로 GPU를 바꾸지 않는다.
4. **실제 Pod 호출은 격리**: 테스트와 개발은 Fake Provider만 사용한다. 실제 Runpod 호출은 `RunpodLifecycleProvider` 하나에서만 한다.
5. **단일 프로세스 MVP**: Uvicorn worker는 1개만 실행한다. SQLite 트랜잭션과 프로세스 내 Worker를 전제로 하며, 수평 확장은 범위 밖이다.
6. **비용 발생 전 승인**: `POST /jobs`는 순수 계산만 한다. Pod 생성은 `POST /jobs/{id}/start`에서만 시작한다.

## 4. 목표 아키텍처

```text
Frontend
  └─ FastAPI Router
       └─ JobApplicationService
            ├─ SessionRepository / JobRepository (SQLite)
            ├─ ProfileRecommendationService
            │    └─ 기존 cost-optimizer의 순수 추정 로직
            └─ JobRunner (프로세스 내 background task)
                 └─ RunpodLifecycleProvider
                      ├─ create_pod
                      ├─ get_pod_status
                      └─ delete_pod

Runpod Pod
  └─ 고정 학습 명령
       └─ POST /internal/jobs/{id}/completion
```

### 모듈 경계

| 모듈 | 책임 | 직접 알 필요가 없는 것 |
| --- | --- | --- |
| `ProfileRecommendationService` | 고정 GPU 프로필을 예산·우선순위 기준으로 비교하고 추천 스냅샷 생성 | DB, HTTP, Runpod API |
| `SessionRepository` | 토큰 해시 기반 세션 생성·조회·실행 횟수 갱신 | 추천·Pod 구현 |
| `JobRepository` | Job·상태·callback 결과·선택 계약 저장 | HTTP, Runpod raw API |
| `JobApplicationService` | API 요청 검증, 소유권·상태·동시 실행 제어, Worker 시작 | Runpod 요청 형식 |
| `JobRunner` | Pod 생성, polling, timeout, 종료 요청·확인 | HTTP cookie, 추천 계산 |
| `RunpodLifecycleProvider` | Runpod create/status/delete API 변환 | Job 상태 정책 |

## 5. 코드 배치

기존 팀원 구현체를 유지하고, 동일 패키지 안에 MVP 전용 모듈을 추가한다. 기존 optimizer endpoint를 MVP 앱의 공개 API로 연결하지 않는다.

```text
ai-training-cost-optimizer/
└─ training_cost_optimizer/
   ├─ analysis/                     # 기존: 필요 시 순수 workload 추정 재사용
   ├─ recommendation.py             # 기존: 공통 비용/후보 계산 재사용 가능
   ├─ providers/
   │  ├─ runpod.py                  # 기존: GPU catalog 관련 코드
   │  └─ runpod_lifecycle.py         # 신규: create/status/delete 어댑터
   ├─ mvp/                           # 신규
   │  ├─ config.py                  # 고정 workload·GPU profile·환경변수
   │  ├─ domain.py                  # Session, Job, Plan, 상태 전이 모델
   │  ├─ recommendation.py          # MVP 우선순위 정책 어댑터
   │  ├─ repository.py              # SQLite schema·transaction·repository
   │  ├─ service.py                 # JobApplicationService
   │  ├─ runner.py                  # background Worker·timeout·termination
   │  └─ router.py                  # /api/v1 라우트·응답 모델
   └─ api.py                        # MVP FastAPI app과 router 등록
```

기존 `models.py`의 `PLANNED`, `QUEUED`, `STOPPED` 상태 모델은 MVP Job 상태로 재사용하지 않는다. MVP 전용 상태는 `mvp/domain.py`에 독립적으로 둔다.

## 6. 고정 설정과 추천기

### GPU 실행 프로필

`mvp/config.py`에 2~3개의 버전 관리된 `GpuExecutionProfile` 상수를 둔다.

| 필드 | 용도 |
| --- | --- |
| `id` | `selected_profile_id`와 API 응답의 식별자 |
| `provider` | MVP에서는 `Runpod` 고정 |
| `gpu_type` | 화면에 표시할 GPU 이름 |
| `runpod_gpu_type_id` | Pod 생성에만 쓰는 Provider 식별자 |
| `image_name` | 사전 검증 Docker image |
| `start_command` | callback을 포함한 고정 학습 실행 명령 |
| `estimated_runtime_minutes` | 데모 스냅샷의 추정 실행시간 |
| `estimated_gpu_cost_krw` | 데모 스냅샷의 추정 GPU 비용 |
| `vram_gb` | 고정 workload의 VRAM 적합성 검증 |

- profile의 실제 Pod 생성 가능 여부는 데모 전 각각 한 번씩 확인한다.
- `runpod_gpu_type_id`, API 키, callback base URL은 클라이언트 응답에 반환하지 않는다.
- 비용은 실시간 값이 아니라 데모 스냅샷이다. 실제 비용 자동 중단에는 사용하지 않는다.

### 추천 정책 구현

입력은 `maxBudgetKrw`, `priority`뿐이다. 고정 workload의 필요 VRAM을 충족하고 예상 GPU 비용이 예산 이하인 후보만 추천 대상이다.

| 우선순위 | 구현 규칙 |
| --- | --- |
| `CHEAPEST` | `estimated_gpu_cost_krw ASC`, 시간, profile ID 순 |
| `FASTEST` | `estimated_runtime_minutes ASC`, 비용, profile ID 순 |
| `BALANCED` | `0.5 × (비용 / 최저 비용) + 0.5 × (시간 / 최단 시간) ASC`, 비용, 시간, profile ID 순 |

추천기는 `selection_snapshot`을 만든다. 스냅샷에는 후보 목록, 예산 적합 여부, 추천 결과, reason, `DEMO_SNAPSHOT` 안내 문구, 정책 버전을 포함한다.

기존 구현체의 “최저 완료비용” 추천은 `CHEAPEST`의 재료로 재사용할 수 있다. `FASTEST`와 `BALANCED`는 위 정책을 보장하는 MVP 어댑터에서 구현한다.

## 7. 데이터와 동시성

### 영속성 선택

MVP는 표준 라이브러리 `sqlite3`을 사용한다. `ANONYMOUS_SESSIONS`, `TRAINING_JOBS`의 구조는 [ERD.md](ERD.md)를 따른다. 파일 DB는 배포 환경의 지속 볼륨에 둔다.

- 각 repository 호출은 새 SQLite connection을 열고 닫는다.
- WAL mode를 켠다.
- 상태를 바꾸는 요청은 transaction으로 처리한다.
- 실행 승인에는 `BEGIN IMMEDIATE`를 사용한다.

### `start`의 원자적 처리

한 transaction에서 순서대로 검증하고 갱신한다.

1. 세션 존재·만료·Job 소유권을 검증한다.
2. Job이 `DRAFT`인지 확인한다.
3. 세션의 `execution_used = false`인지 확인한다.
4. 전체 Job 중 `PROVISIONING`, `RUNNING`, `TERMINATING`가 없는지 확인한다.
5. `execution_used = true`, Job `status = PROVISIONING`, `started_at`을 저장한다.
6. commit한 뒤에만 `JobRunner` task를 시작한다.

이렇게 해야 중복 클릭이나 동시 요청이 Pod 두 개를 만드는 일을 막을 수 있다. DB transaction이 실패하면 Worker를 시작하지 않는다.

### 종료 예정 결과 보존

`TERMINATING` 중에도 최종 결과가 무엇인지 보존해야 한다. 따라서 ERD의 `TRAINING_JOBS`에는 내부 필드 `requested_final_status` (`COMPLETED | FAILED | CANCELLED | NULL`)가 있다. 이 값은 사용자 API 응답에는 노출하지 않는다.

- callback 성공 + exit code 0: `requested_final_status = COMPLETED`
- 실패 callback, provisioning 오류, timeout: `requested_final_status = FAILED`
- cancel: `requested_final_status = CANCELLED`
- Pod 종료를 확인한 뒤에만 `status = requested_final_status`로 전환한다.

이 필드는 [ERD.md](ERD.md)에 반영돼 있다.

## 8. API 구현 매핑

| Endpoint | Service 동작 | 저장 결과 |
| --- | --- | --- |
| `POST /api/v1/session` | 원문 토큰 생성, 해시 저장, cookie 설정 | 세션 생성 또는 만료 연장 |
| `POST /api/v1/jobs` | 제약 검증 → 추천기 실행 | `DRAFT` Job + 선택 스냅샷 |
| `GET /api/v1/jobs/{id}` | 세션 소유권 검증 | 실행 계약·현재 상태 반환 |
| `POST /api/v1/jobs/{id}/start` | 원자적 실행 승인 → Worker 등록 | `PROVISIONING` |
| `POST /api/v1/jobs/{id}/cancel` | 종료 예정 결과 기록 → 삭제 요청 | `TERMINATING` |
| `POST /api/v1/internal/jobs/{id}/completion` | callback 결과 기록 → 종료 요청 | `TERMINATING` |

### 세션 처리

- cookie 이름은 하나의 상수로 둔다. 토큰 원문은 HttpOnly·Secure·SameSite=Lax cookie에만 쓴다.
- DB에는 SHA-256 등 단방향 해시만 저장한다.
- 만료 또는 없는 cookie는 사용자 Job API에서 `401`을 반환한다.
- 다른 세션의 Job ID는 존재 여부와 무관하게 `404 JOB_NOT_FOUND`를 반환한다.

### callback 처리

- Runpod Pod의 고정 명령은 `BACKEND_PUBLIC_BASE_URL`과 Job ID를 사용해 종료 직전에 callback을 보낸다.
- MVP에서는 별도 callback 인증을 추가하지 않는다. 이 결정은 공개 서비스 정책이 아니라 사전 검증 컨테이너만 쓰는 데모 범위다.
- callback은 `RUNNING` 상태에서 한 번만 유효하다. 이미 `TERMINATING` 또는 최종 상태면 중복 callback을 무시하거나 `409`을 반환하는 정책을 테스트로 고정한다.

## 9. JobRunner와 Runpod Provider

### Provider 인터페이스

```python
class RunpodLifecycleProvider(Protocol):
    def create_pod(self, profile: GpuExecutionProfile, job_id: str) -> str: ...
    def get_pod_status(self, pod_id: str) -> PodStatus: ...
    def delete_pod(self, pod_id: str) -> None: ...
```

`PodStatus`는 최소 `PROVISIONING`, `RUNNING`, `TERMINATED`, `FAILED`만 표현한다. Runpod의 raw 상태 문자열은 Provider 내부에서만 변환한다.

### Worker 흐름

```text
PROVISIONING Job 조회
→ 선택 profile로 Pod 생성
→ pod ID 저장
→ polling으로 RUNNING 확인
→ callback·cancel·timeout·Pod 오류 감시
→ requested_final_status 기록
→ delete_pod 요청
→ polling으로 TERMINATED 확인
→ requested_final_status를 최종 Job status로 반영
```

- Pod polling은 5초 간격으로 한다. 프런트엔드 polling과 독립적이다.
- timeout 기준은 `started_at + 10분`이다.
- Pod 생성 전 실패하면 Pod 삭제는 생략하고 `FAILED`로 끝낸다. Pod ID가 생긴 뒤의 성공·실패·취소·timeout은 항상 삭제를 시도한다.
- delete 요청이 실패하거나 종료 확인을 못 하면 Job은 `TERMINATING`에 남기고 짧은 실패 메시지를 기록한다. Worker는 데모 종료 전까지 polling을 계속한다.
- 프로세스가 살아 있는 한 브라우저 종료와 관계없이 Worker는 계속된다. 서버 재시작 복구는 MVP 범위 밖이다.

## 10. 구현 Loop

각 Loop는 실패하는 통합 테스트를 먼저 추가하고, Fake Provider로 통과시킨 뒤에 다음 Loop로 넘어간다.

### Loop 1 — 세션과 추천 Draft

**구현**

- SQLite schema와 session cookie
- GPU profile 상수와 `ProfileRecommendationService`
- `POST /session`, `POST /jobs`, `GET /jobs/{id}`

**통과 조건**

- `CHEAPEST`, `FASTEST`, `BALANCED`가 각각 정책대로 추천한다.
- 예산 미달은 Job을 만들지 않고 `422 NO_ELIGIBLE_PLAN`을 반환한다.
- 동일 Job을 다른 session으로 조회하면 `404`다.

### Loop 2 — 승인과 중복 실행 차단

**구현**

- `POST /jobs/{id}/start`
- SQLite `BEGIN IMMEDIATE` transaction
- Fake Worker 등록

**통과 조건**

- start 뒤 Job은 `PROVISIONING`, 세션은 `execution_used = true`다.
- 같은 session의 두 번째 start와 두 번째 Job 실행은 `409 EXECUTION_ALREADY_USED`다.
- 다른 session의 동시 start는 `409 DEMO_BUSY`다.

### Loop 3 — 정상 실행 생애주기

**구현**

- Fake Provider의 create/status/delete
- Worker와 completion callback
- `requested_final_status`

**통과 조건**

- `PROVISIONING → RUNNING → TERMINATING → COMPLETED` 순서를 지킨다.
- `COMPLETED`에는 exit code 0, completion log, `pod_terminated_at`이 있다.
- Pod 종료 전에는 `COMPLETED`가 표시되지 않는다.

### Loop 4 — 취소·실패·timeout

**구현**

- `POST /cancel`
- 실패 callback, Pod provisioning 오류, timeout 처리
- 주입 가능한 clock으로 timeout 테스트

**통과 조건**

- cancel은 `CANCELLED`, 실패·timeout은 `FAILED`로 종료한다.
- Pod ID가 있는 모든 경로에서 delete 요청과 종료 확인이 발생한다.
- 재시도·OOM 재계획·대기열은 생기지 않는다.

### Loop 5 — 실제 Runpod Smoke Test

**구현**

- `RunpodLifecycleProvider`의 create/status/delete
- 고정 image·명령·callback URL을 만드는 payload
- 환경변수 검증과 운영 로그

**통과 조건**

- 데모 후보 profile 각각이 실제 Pod 생성 가능함을 사전 확인한다.
- 하나의 선택 시나리오가 실제 생성·학습 callback·삭제·종료 확인까지 완료된다.
- Runpod API 키와 GPU type ID가 응답·로그에 노출되지 않는다.

### Loop 6 — 프런트엔드 통합과 리허설

**구현**

- CORS를 실제 프런트 origin으로 제한
- 2~3초 `GET /jobs/{id}` polling 연동
- 사용자 오류 메시지와 Demo busy 화면 연동

**통과 조건**

- [frontend-flowchart.txt](frontend-flowchart.txt)의 성공·예산 미달·취소 흐름을 브라우저에서 재현한다.
- 사용자는 Runpod 콘솔·SSH·GPU type ID를 전혀 보거나 조작하지 않는다.

## 11. 테스트 전략

| 계층 | 도구·대상 | 실제 Runpod 호출 |
| --- | --- | --- |
| 단위 테스트 | 추천 정책, 상태 전이, 비용·시간 스냅샷 | 없음 |
| repository 테스트 | SQLite transaction, 소유권, 전역 1개 실행 | 없음 |
| API 통합 테스트 | FastAPI TestClient + Fake Provider | 없음 |
| lifecycle 테스트 | controllable Fake clock·Provider | 없음 |
| smoke test | 배포 환경 + Runpod | 명시적으로 1회씩 |

테스트마다 새 임시 SQLite 파일을 만들고, 테스트가 끝나면 파일을 제거한다. 실제 Runpod smoke test는 일반 test suite에 넣지 않고 별도 명령으로 분리한다.

필수 API 통합 테스트 이름:

```text
test_create_job_persists_recommendation_snapshot
test_budget_filters_and_returns_no_eligible_plan
test_start_is_atomic_for_session_and_global_limit
test_completed_only_after_pod_termination
test_cancel_deletes_pod_and_becomes_cancelled
test_timeout_deletes_pod_and_becomes_failed
test_job_is_hidden_from_other_session
```

## 12. 환경변수와 운영 체크리스트

| 변수 | 용도 |
| --- | --- |
| `RUNPOD_API_KEY` | 서버의 팀 Runpod API 키 |
| `MVP_DATABASE_PATH` | 지속 SQLite 파일 경로 |
| `BACKEND_PUBLIC_BASE_URL` | Pod가 completion callback을 보낼 공개 HTTPS URL |
| `FRONTEND_ORIGINS` | 허용 프런트엔드 origin |
| `MVP_MAX_RUNTIME_MINUTES` | 기본값 10, 데모에서는 10으로 고정 |

실제 데모 전 체크:

1. 단일 Uvicorn worker와 지속 SQLite 경로로 배포한다.
2. `BACKEND_PUBLIC_BASE_URL`이 Runpod 컨테이너에서 접근되는 HTTPS 주소인지 확인한다.
3. 각 GPU profile의 type ID·image·명령을 실제로 한 번 검증한다.
4. 저비용·빠른 완료 입력이 서로 다른 추천을 만드는지 확인한다.
5. 성공, 취소, timeout 중 최소 성공·취소를 실제 Pod에서 리허설한다.
6. Runpod 콘솔에서 모든 리허설 Pod가 삭제됐는지 마지막으로 확인한다.

## 13. 구현 시작 순서

구현은 반드시 Loop 1부터 시작한다. 팀원 구현체의 기존 추천 로직을 먼저 평가·재사용하되, 현재 `/optimize` API를 프런트엔드에 연결하지 않는다.

Loop 1이 끝난 뒤에만 실행 Worker와 Runpod lifecycle 구현을 시작한다. 이 순서를 지키면 추천 기능, 실행 상태, 실제 비용 발생 코드를 서로 독립적으로 검증할 수 있다.
