# UNWORK 학습 실행 Agent — 프런트엔드 구현 계획서

## 1. 목적과 구현 기준

이 문서는 [PRD-final.md](PRD-final.md)의 제품 기능 전체를 담는 웹 프런트엔드 구현 계획이다. 구현 판단은 아래 문서 순서로 따른다.

1. [PRD-final.md](PRD-final.md) — 제품 기능과 사람·Agent의 역할 분담
2. [API-spec.md](API-spec.md) — 서버 계약
3. [DESIGN.md](DESIGN.md) — 유일한 디자인 기준
4. [ERD.md](ERD.md) — 데이터 모델

화면이 증명해야 할 것은 다음 한 가지다.

> 사용자는 학습 목표·예산·완료 조건을 정하고 실행 계약을 승인한다. GPU 종류, Region, CUDA 버전, VM 옵션, SSH, 자원 종료를 직접 조작하지 않는다.

프런트엔드는 실행 계획을 **만들거나 변경하지 않는다.** 서버가 계산한 분석 결과·실행안·비용·위험도를 읽기 전용으로 표시하고, 사용자의 승인·중단·판단만 전달한다.

### 범위

- 익명 세션과 cookie 기반 API 호출
- GPU 공급자 계정 연결과 연결 상태 표시
- 학습 Repository·실행 명령·완료 조건·예산·최대 실행시간 입력
- Agent 분석 결과 표시: 프레임워크·CUDA·의존성·필요 VRAM·기준 실행시간·확신하지 못한 항목
- 실행안 3개(`가장 저렴함`·`가장 빠름`·`균형형`) 비교: 총비용 분해, 예상 시간, 위험도, 대체 후보, 지원 환경 버전
- 실행 계약 승인과 승인 직전 재검증(`PLAN_EXPIRED`) 처리
- 실행 감시: 단계 진행, 경과 시간, 누적 비용, 진행률, 최근 로그
- 실행 중단
- 재계획·계속 투자 판단 요청 승인과 거절
- 결과: artifact, 실행 시간, 추정/실제 비용, 자원 종료 확인
- 새로고침 복구, 오류 안내, 데스크톱·모바일 반응형, 키보드 접근성

### 프런트엔드가 하지 않는 것

- 추천 순위·비용·예상 시간·위험도 재계산. 모든 값은 서버가 준 것을 그대로 표시한다.
- GPU type ID, Region, VM 옵션, 이미지 태그, Provider resource ID, Pod ID 노출
- Provider 비밀값 저장·재표시. 입력 즉시 서버로 보내고 클라이언트에 남기지 않는다.
- 실시간 로그 스트림. `execution.logTail` 폴링만 한다.
- 서버가 주지 않은 값의 추정. `progress`가 `null`이면 진행률을 만들어 내지 않는다.

### 데모 운영

데모는 화면 기능을 좁히지 않는다. 진행자가 [API-spec.md의 데모 골든 패스](API-spec.md#11-데모-골든-패스) 값으로 입력하도록 안내하고, 실행 횟수·동시 실행·Repository allowlist는 서버 배포 정책으로 강제한다. 화면은 해당 오류 코드를 다음 행동과 함께 안내할 뿐, 제품 단계나 실행 성격을 라벨로 붙이지 않는다.

## 2. 기술 선택과 앱 경계

**React 18 + TypeScript + Vite** 단일 페이지 앱이다. 익명 session cookie가 `SameSite=Lax`이므로 배포 기본값은 frontend와 API를 같은 origin으로 묶는 reverse proxy다.

| 구분 | 선택 | 이유 |
| --- | --- | --- |
| UI 런타임 | React + TypeScript | Job 상태와 화면 상태를 타입으로 분리한다. |
| 빌드 | Vite | 서버 렌더링이 필요 없다. |
| 서버 상태 | TanStack Query | 폴링·캐시·중단을 선언적으로 관리한다. |
| 폼·검증 | React Hook Form + Zod | Repository URL·명령·완료 조건·예산을 API 요청 전 검증한다. |
| 스타일 | CSS variables + CSS Modules | DESIGN.md 토큰을 직접 유지하고 컴포넌트 라이브러리의 기본 스타일을 피한다. |
| 아이콘 | Lucide React | 상태·진행·위험을 텍스트와 함께 전달한다. 아이콘만으로 의미를 전달하지 않는다. |
| 테스트 | Vitest + Testing Library + MSW, Playwright | 계약·상태 전이·오류를 실제 네트워크 없이 검증한다. |

```text
frontend/
├─ src/
│  ├─ app/                    # bootstrap, providers, 화면 전환
│  ├─ api/                    # fetch client, API DTO, error normalizer
│  ├─ features/
│  │  ├─ providers/           # 공급자 연결
│  │  ├─ workload/            # 학습 작업 입력, 분석 결과
│  │  ├─ plans/               # 실행안 비교, 계약 승인
│  │  └─ execution/           # 감시, 판단 요청, 결과
│  ├─ components/ui/          # token 기반 Button, Card, Dialog, Badge
│  ├─ styles/                 # tokens, global, responsive
│  ├─ hooks/
│  └─ test/                   # MSW handlers, fixtures, utilities
├─ .env.example
└─ package.json
```

환경변수는 `VITE_API_BASE_URL` 하나다. 같은 origin 배포에서는 `/api/v1`을 쓴다. 다른 origin을 쓸 경우 두 origin이 same-site여야 하고 backend의 credential CORS allowlist에 정확한 frontend origin이 있어야 한다. 모든 요청은 `credentials: 'include'`로 보낸다.

## 3. 정보 구조와 화면 흐름

메인 route 하나 안에서 단계별 화면을 전환한다. 새로고침 복구를 위해 현재 Job ID만 `localStorage`의 `unwork.activeJobId`에 저장한다. 서버의 cookie 소유권 검사가 남아 있으므로 이 값은 인증 정보가 아니다. `401` 또는 `404`이면 즉시 제거한다.

```text
앱 초기화 POST /session
  → 공급자 연결 확인 GET /providers
  → 학습 작업 입력
  → POST /jobs
  → 분석 진행        ANALYZING
  → 실행안 검토      PLAN_READY
  → POST /jobs/{id}/approve
  → 실행 감시        PROVISIONING → PREPARING → RUNNING
  → (필요할 때만)    AWAITING_DECISION
  → 종료 확인        TERMINATING
  → 결과             COMPLETED / FAILED / CANCELLED / BUDGET_STOPPED
```

| 화면 상태 | 주 목적 | 주 API | 사용자 행동 |
| --- | --- | --- | --- |
| `PROVIDERS` | 공급자 연결 상태 확인과 연결 | `GET /providers`, `POST /providers/{id}/credential` | 연결, 해제, 다음으로 |
| `WORKLOAD` | 학습 작업과 예산·완료 조건 입력 | `POST /jobs` | 입력, 제출 |
| `ANALYZING` | Agent가 코드를 읽는 중임을 알림 | `GET /jobs/{id}` 2초 폴링 | 취소하고 입력으로 |
| `PLAN_REVIEW` | 실행안 3개 비교와 계약 확인 | `GET /jobs/{id}` | 실행안 선택, 승인, 입력 수정 |
| `APPROVING` | 중복 승인 방지 | `POST /jobs/{id}/approve` | 없음 |
| `EXECUTION` | 단계·경과·비용·진행률 표시 | `GET /jobs/{id}` 3초 폴링 | 실행 중단 |
| `DECISION` | 재계획·계속 투자 판단 | `POST /jobs/{id}/decisions/{id}` | 승인, 여기서 중단 |
| `RESULT` | 결과·artifact·종료 확인 | `GET /jobs/{id}` | artifact 받기, 새 작업 시작 |

페이지를 다시 열면 `POST /session` 후 `activeJobId`가 있으면 `GET /jobs/{id}`로 서버 상태에 맞는 화면을 복구한다. 조회 실패 시 저장값을 지우고 새 흐름을 시작한다. 브라우저가 닫힌 동안 실행 생애주기는 백엔드가 소유하며, 프런트엔드는 재접속 시 상태를 표시할 뿐이다.

## 4. 화면 및 컴포넌트 명세

### 4.1 공통 App shell

- 상단 바: `UNWORK` 워드마크와 우측 세션 상태만 둔다. 로그인·설정 메뉴는 두지 않는다. 제품 단계(`MVP`)나 실행 성격(`데모`)을 라벨로 붙이지 않는다.
- 세션 상태는 `세션 준비 중`(제출 CTA가 비활성인 이유), `익명 세션`(로그인 없이 이 브라우저에서만 작업을 볼 수 있다는 뜻), `세션을 시작하지 못했어요`(재시도 필요) 세 가지다.
- 본문: desktop 최대 폭 1,180px, 상단 48px / 하단 64px 여백.
- 모바일: 단일 열, 핵심 CTA는 화면 하단 sticky action bar.
- 공통 `SystemNotice`: 추정값, 세션, API 오류 안내를 보여 주며 경고와 오류를 구별한다.

**문구 원칙.** 화면에는 제품 단계나 실행 성격을 가리키는 라벨(`MVP`, `데모`, `프로토타입`)을 쓰지 않는다. 라벨은 사용자가 부딪히는 제약을 설명하지 못한다. 제약은 라벨 대신 결과로 적는다 — 실행 횟수가 제한된 것, 대기열이 없는 것, 비용이 추정값인 것을 각각 그 자리에서 문장으로 밝힌다. `PLAN_EXPIRED`, `CONCURRENT_EXECUTION_LIMIT` 같은 API code는 내부 값이므로 그대로 노출하지 않는다.

### 4.2 공급자 연결 (`ProviderConnection`)

- 공급자마다 이름, 연결 상태, 연결 시각, 비교 가능한 GPU 종류 수를 한 줄로 보여 준다.
- `connectionStatus`가 `CONNECTED`가 아니면 상태와 다음 행동을 함께 적는다. `INVALID_CREDENTIAL`은 다시 연결, `UNREACHABLE`은 잠시 후 다시 확인이다.
- 연결 입력은 `type="password"`이고 값을 클라이언트에 저장하지 않는다. 전송 성공 뒤 필드를 비우고 `GET /providers`를 다시 읽는다. 저장된 키를 다시 표시하는 UI는 만들지 않는다.
- 연결된 공급자가 하나도 없으면 학습 작업 제출을 막고 그 이유를 적는다.
- 연결이 여러 곳이면 "연결된 공급자 N곳에서 비교합니다"를 학습 작업 화면에도 표시한다.

### 4.3 학습 작업 입력 (`WorkloadForm`)

사용자가 결정하는 것은 **무엇을 학습할지, 얼마를 쓸지, 무엇을 완료로 볼지**다. GPU·Region·CUDA·VM 옵션은 필드로도 고급 설정으로도 노출하지 않는다.

| 요소 | 구현 | 검증·행동 |
| --- | --- | --- |
| Repository | `repositoryUrl` 텍스트 입력 | http/https Git URL. 형식 오류는 `aria-describedby`로 연결한다. |
| Revision | `revision` 텍스트 입력, 선택 사항 | 비우면 기본 branch를 쓴다고 helper에 적는다. |
| 실행 명령 | `executionCommand` 텍스트 입력, mono | Repository 루트 기준임을 helper에 적는다. |
| 완료 조건 | `PROCESS_EXIT` / `MAX_STEPS` / `TARGET_METRIC` 선택 + 조건부 필드 | 선택에 따라 step 수 또는 지표명·목표값을 요구한다. |
| 최대 예산 | `₩` prefix 숫자 입력 | 0보다 큰 정수. 쉼표는 표시 전용, API에는 number를 보낸다. |
| 최대 실행시간 | 분 단위 숫자 입력 | 0보다 큰 정수. 초과 시 Agent가 중단한다고 helper에 적는다. |
| 제출 CTA | `Agent에게 실행안 요청` | 유효할 때만 활성화하고 제출 중 중복 요청을 막는다. |

폼 아래에는 “예상 비용은 실제 청구액을 보장하지 않습니다. Agent는 승인 직전에 가격과 가용성을 다시 확인합니다.”를 항상 표시한다.

### 4.4 분석 결과 (`AnalysisPanel`)

- `ANALYZING` 중에는 Agent가 하는 일을 단계로 보여 준다 — Repository 읽기, 의존성 확인, GPU 후보 비교. 진행률을 지어내지 않는다.
- `READY`가 되면 프레임워크·버전, CUDA, Python, 감지한 의존성, 필요 VRAM, 기준 실행시간, `confidence`를 표시한다.
- `analysis.unknowns`는 접어 두지 않고 항상 보인다. 이것이 추정값의 근거를 사용자가 판단하게 하는 유일한 자리다.
- `ANALYSIS_FAILED`는 입력을 유지한 채 무엇을 확인해야 하는지 적는다. Repository URL과 실행 명령은 지우지 않는다.

### 4.5 실행안 비교 (`PlanComparison`)

`GET /jobs/{id}`의 `plans`가 화면의 유일한 데이터 원본이다. 클라이언트는 순위·비용·시간·위험도를 재계산하지 않는다.

- `PlanCard` 3개를 `CHEAPEST` → `FASTEST` → `BALANCED` 순서로 고정 배치한다. 서버가 `recommended: true`를 준 안에 추천 배지를 붙이되, 세 안 모두 승인할 수 있다.
- 각 카드는 GPU·공급자, 예상 실행 시간, **총비용**을 먼저 보여 주고, `CostBreakdown` disclosure에 GPU 사용료·저장소/전송비·Agent 실행 수수료를 나눠 적는다. 시간당 단가는 비교 축이 아니다.
- `RiskBadge`는 `level`과 `reasons`를 함께 보여 준다. 위험도를 비용에 섞지 않는다. hover에만 이유를 넣지 않는다.
- `alternatives`는 "이 안이 중단되면 제안할 후보"로 항상 보인다.
- `environment`(프레임워크·CUDA·Python 버전, `verified`)를 카드 안에 적는다. 이미지 태그나 resource ID는 적지 않는다.
- `budget.withinBudget: false`인 안은 비교 근거로 보이되 선택할 수 없고, `shortfallKrw`로 얼마가 모자라는지 적는다.
- `priceDataType: SNAPSHOT`이면 실시간 가격이 아님을 `pricedAt`과 함께 표시한다.

### 4.6 실행 계약 승인 (`ContractApproval`)

- `ContractSummary`: 선택 실행안, 고정 commit SHA, 실행 명령, 완료 조건, 예산, 최대 실행시간, 자동 중단 조건(`autoStop`)을 한자리에 모은다.
- `승인 후 Agent가 환경을 만들고 비용이 발생합니다.`를 적고 `실행 승인` CTA와 `입력 수정` 보조 행동을 둔다. GPU 변경 버튼은 만들지 않는다.
- `실행 승인`은 확인 dialog를 연다. dialog에는 선택 GPU·공급자, 예상 총비용, 자동 중단 조건, 예산이 실제 청구 한도가 아니라는 안내를 다시 표시한다. 확인하면 `POST /jobs/{id}/approve`를 한 번만 호출한다.
- `409 PLAN_EXPIRED`를 받으면 승인하지 않고, 응답의 갱신된 실행안으로 비교 화면을 교체한 뒤 무엇이 달라졌는지 적는다. 이전 실행안으로 승인을 재시도하지 않는다.

### 4.7 실행 감시 (`ExecutionMonitor`)

인프라 콘솔처럼 보이지 않으면서 상태를 숨기지도 않는다.

- `StepTimeline`: `execution.steps`를 서버 순서대로 표시한다. `DONE` / `ACTIVE` / `PENDING`을 아이콘과 텍스트로 함께 전달한다.
- 항상 보이는 값: 선택 GPU·공급자, 경과 시간, 최대 실행시간, 누적 비용과 예산 사용률.
- `CostMeter`: `cost.dataType`이 `ESTIMATED`면 계측값이 아님을 적는다. `METERED`와 시각적으로 구별한다.
- `progress`가 `null`이면 진행률 막대를 그리지 않고 "진행률을 확인할 수 없습니다"를 적는다.
- `logTail`은 `--canvas-night` code block에 mono로 최근 줄만 보여 준다. 자동 스크롤로 focus를 빼앗지 않는다.
- `TERMINATING`에서는 모든 action을 비활성화하고 최종 결과를 표시하지 않는다. 오래 지속되면 "자원 종료 확인을 계속 기다리고 있습니다"와 마지막 갱신 시각을 적는다.
- 중단 버튼은 `PROVISIONING`·`PREPARING`·`RUNNING`·`AWAITING_DECISION`에서만 보인다. 누르면 destructive confirmation dialog를 열고, 확인 시 `POST /jobs/{id}/cancel`을 호출한다. `202` 뒤 즉시 `TERMINATING` UI로 전환하되, 서버가 `CANCELLED`를 주기 전에는 "중단 완료"라고 쓰지 않는다.

### 4.8 판단 요청 (`DecisionPanel`)

`pendingDecision`이 있을 때만 나타난다. 정상 경로에서는 보이지 않는다.

- `reason`을 가장 먼저 보여 준다. 왜 사람의 판단이 필요한지가 첫 문장이다.
- `current`(지금까지 쓴 비용, 완료 비율)와 `proposed`(새 실행안 전문)를 나란히 놓는다.
- `delta`의 추가 비용, 추가 시간, GPU 변경 여부, checkpoint 재개 여부를 명시한다. 추가 비용은 총액이 아니라 **증분**으로 적는다.
- 행동은 `제안대로 계속`과 `여기서 중단` 둘뿐이다. 둘 다 확인 dialog를 거친다.
- `expiresAt`까지 남은 시간을 표시하고, 만료되면 서버가 중단으로 처리한다고 적는다. 만료 뒤 응답은 `409 DECISION_ALREADY_RESOLVED`로 처리한다.

### 4.9 결과 (`ResultPanel`)

- 공통: `outcome`, 선택 GPU·공급자, 시작·완료 시각, 실행 시간, 추정 비용과 실제 비용, 자원 종료 확인.
- `cost.actualTotalKrw`가 `null`이면 실제 비용 자리에 추정값을 넣지 않는다. "실제 청구액을 아직 확인하지 못했습니다"로 적는다.
- `resourceTeardown.status`: `CONFIRMED`는 완료 체크, `PENDING`은 확인 중, `UNCONFIRMED`는 실패가 아니라 **확인되지 않은 상태**로 따로 표시하고 다음 행동을 적는다.
- 성공: `completionLog`, `exitCode`, `artifacts` 목록. artifact는 이름·종류·크기를 보여 주고 받기 행동을 제공한다.
- 실패: `failureMessage`를 먼저 보여 주고 `exitCode`·`completionLog`는 세부 정보 disclosure에 둔다. 재시도 가능성을 추정해 말하지 않는다. `checkpoints`가 있으면 보존됐음을 알린다.
- `BUDGET_STOPPED`: 어떤 상한(예산 또는 시간)에 도달해 Agent가 중단했는지 적는다.
- 중단: 사용자의 중단 요청과 자원 종료 확인을 보여 준다.
- 최종 화면의 `새 학습 작업`은 입력 화면으로 이동한다. 세션 실행 허용 횟수를 모두 쓴 경우에는 그 사실과 다음 행동을 적는다.

## 5. API 연동과 상태 관리

`api/client.ts`는 base URL, JSON headers, `credentials: 'include'`, `AbortSignal`, 공통 오류 파싱만 담당한다. API DTO는 명세의 camelCase를 그대로 쓰고, UI label·색상·문구는 DTO 밖 presenter에서 관리한다.

| 함수 | HTTP | 호출 시점 |
| --- | --- | --- |
| `createSession()` | `POST /session` | 앱 진입, 세션 복구 실패 후 |
| `getProviders()` | `GET /providers` | 앱 진입, 연결 mutation 직후 |
| `connectProvider(id, apiKey)` | `POST /providers/{id}/credential` | 연결 폼 제출 |
| `disconnectProvider(id)` | `DELETE /providers/{id}/credential` | 연결 해제 확인 |
| `createJob(input)` | `POST /jobs` | 유효한 학습 작업 폼 제출 |
| `getJob(id)` | `GET /jobs/{id}` | 복구, 폴링, mutation 직후 재검증 |
| `approveJob(id, planId)` | `POST /jobs/{id}/approve` | 승인 dialog 확인 |
| `cancelJob(id)` | `POST /jobs/{id}/cancel` | 중단 dialog 확인 |
| `resolveDecision(id, decisionId, outcome)` | `POST /jobs/{id}/decisions/{decisionId}` | 판단 dialog 확인 |

### 클라이언트 상태 원칙

- 서버 상태: `TrainingJob`은 TanStack Query cache에만 두고 mutation 성공 뒤 반드시 `GET /jobs/{id}`로 무효화한다.
- UI 상태: 폼 값, dialog 열림 여부, 선택한 실행안 ID, 화면 전환만 React local state/reducer에 둔다.
- 계약 불변: 승인 뒤에는 `contract.planSnapshot`이 화면의 근거다. 이후 `plans`가 바뀌어도 승인된 계약 표시를 바꾸지 않는다.
- 중복 방지: 승인·중단·판단 mutation 동안 관련 CTA를 disabled한다. 최종 동시성 제어는 백엔드 transaction이 담당한다.
- 비밀값: Provider API 키는 mutation 인자로만 존재하고 state·cache·localStorage 어디에도 남기지 않는다.
- 저장: Job ID를 만든 즉시 localStorage에 기록하고, 사용자가 새 작업을 시작하기 전까지 보관한다.

### 폴링 정책

```text
status = ANALYZING
  → GET /jobs/{id} every 2,000ms
status ∈ {PROVISIONING, PREPARING, RUNNING, AWAITING_DECISION, TERMINATING}
  → GET /jobs/{id} every 3,000ms
status ∈ {PLAN_READY, ANALYSIS_FAILED, COMPLETED, FAILED, CANCELLED, BUDGET_STOPPED}
  → polling stop
```

- 화면이 foreground로 돌아오거나 mutation이 끝나면 즉시 한 번 refetch한다.
- 네트워크 오류는 마지막 정상 상태를 유지하고 "연결을 다시 확인하는 중"을 표시한다. 연속 실패는 지수 backoff(3초, 6초, 최대 15초)로 전환하며 최종 상태를 임의로 추정하지 않는다.
- `401`(`SESSION_REQUIRED`/`SESSION_EXPIRED`) 또는 `404 JOB_NOT_FOUND`는 폴링을 중단하고 저장된 Job ID를 제거한 뒤 세션 재시작을 안내한다.

## 6. 오류와 예외 상태 문구

오류 code는 그대로 던지지 않고 아래로 번역한다. 개발 모드에서만 원본 code를 디버그 정보로 볼 수 있다.

| 코드 | 보여 줄 메시지 | 가능한 행동 |
| --- | --- | --- |
| `VALIDATION_ERROR` | 입력한 값을 다시 확인해 주세요. | 폼 수정 |
| `ANALYSIS_FAILED` | Repository와 실행 명령을 분석하지 못했습니다. 접근 가능한 주소인지, 명령이 Repository 루트에서 실행되는지 확인해 주세요. | 입력 수정 후 다시 요청 |
| `NO_ELIGIBLE_PLAN` | 이 예산 안에서 실행할 수 있는 GPU 후보가 없습니다. 최소 ₩{minimumRequiredBudgetKrw}이 필요합니다. | 예산 조정 후 다시 요청 |
| `NO_PROVIDER_CONNECTED` | 연결된 GPU 공급자가 없어 실행안을 만들 수 없습니다. | 공급자 연결 |
| `PLAN_EXPIRED` | 가격 또는 가용성이 바뀌어 실행안을 다시 만들었습니다. 새 실행안을 확인해 주세요. | 갱신된 실행안 검토 후 재승인 |
| `INVALID_JOB_STATE` | 이 작업은 현재 이 행동을 할 수 있는 상태가 아닙니다. | 최신 상태 다시 확인 |
| `DECISION_ALREADY_RESOLVED` | 이 판단 요청은 이미 처리됐습니다. | 최신 상태 다시 확인 |
| `CONCURRENT_EXECUTION_LIMIT` | 지금은 다른 실행이 진행 중입니다. 대기열이 없으니 잠시 후 다시 승인해 주세요. | 계약을 유지하고 나중에 재시도 |
| `EXECUTION_LIMIT_REACHED` | 이 브라우저에서는 실제 실행을 한 번만 할 수 있습니다. | 비용 없는 비교 또는 새 브라우저 세션 |
| `PROVIDER_UNAVAILABLE` | 공급자에 연결하지 못했습니다. 잠시 후 다시 확인해 주세요. | 새로고침, 자동 재시도 없음 |
| `SESSION_REQUIRED` / `SESSION_EXPIRED` | 세션이 만료됐습니다. 새 세션을 시작해 주세요. | 세션 재시작 |
| `JOB_NOT_FOUND` | 이 작업을 찾을 수 없거나 현재 세션에서 볼 수 없습니다. | 새 학습 작업 시작 |
| 알 수 없는 네트워크 오류 | 연결 상태를 확인한 뒤 다시 시도해 주세요. | 동일 행동 재시도 |

오류 메시지에는 API key, request payload, Provider resource ID, raw stack trace를 포함하지 않는다. toast는 일시적 요청 실패에만 쓰고, 현재 흐름을 바꾸는 오류는 해당 화면 상단 alert로 고정한다.

## 7. 디자인 시스템 적용

### 7.1 단일 기준

디자인 기준 문서는 [DESIGN.md](DESIGN.md) 하나다. 흰 캔버스(`#ffffff`), 단일 emerald `#3ecf8e`, 6px 버튼 radius, near-black `#171717` 본문이 제품 기본이며, 다크 표면은 로그·코드 블록에만 쓴다. 이전 판이 참조하던 다크 운영 화면 토큰과 pill 버튼 규칙은 폐기한다.

| 원칙 | 이 제품에서의 적용 |
| --- | --- |
| 흰 캔버스 유지 | 앱 전체가 `#ffffff` / `#fafafa` 위에 놓인다. 실행 추적 화면도 다크로 반전하지 않는다. |
| emerald는 유일한 색 사건 | 추천 후보, 승인 CTA, 완료 상태에만 쓴다. 화면당 filled green은 하나를 원칙으로 한다. |
| green 위 글자는 near-black | `#3ecf8e` 위 흰 글자는 2.00:1로 읽을 수 없고 `#171717`은 8.98:1이다. 버튼 글자는 항상 near-black이다. |
| 6px 기술적 radius | 버튼·입력·표는 6px, 카드 12px, dialog 16px. pill은 상태 tag에만 쓰고 버튼에는 쓰지 않는다. |
| 다크는 코드에만 | `completionLog`, `exitCode`, 고정 실행 명령만 `#1c1c1c` code block에 mono로 넣는다. |
| 장식 금지 | 그라디언트·사진·일러스트·장식 accent 색을 쓰지 않는다. 정보 밀도가 화면의 유일한 시각 재료다. |

### 7.2 토큰

DESIGN.md의 값을 그대로 옮기고, 상태 전달에 필요한 최소한의 semantic 토큰만 파생시킨다.

```css
:root {
  /* Brand — DESIGN.md */
  --primary: #3ecf8e;
  --primary-deep: #24b47e;
  --on-primary: #171717;

  /* Surface — DESIGN.md */
  --canvas: #ffffff;
  --canvas-soft: #fafafa;
  --canvas-night: #1c1c1c;
  --canvas-night-soft: #202020;

  /* Text — DESIGN.md */
  --ink: #171717;
  --ink-secondary: #212121;
  --ink-mute: #707070;      /* 4.95:1 — 보조 텍스트까지 허용 */
  --ink-mute-2: #9a9a9a;    /* 2.81:1 — 텍스트 금지, 아이콘·구분선 전용 */
  --ink-faint: #b2b2b2;     /* placeholder·disabled 전용 */
  --on-dark: #ffffff;

  /* Hairline — DESIGN.md */
  --hairline: #dfdfdf;
  --hairline-strong: #c7c7c7;
  --hairline-cool: #ededed;

  /* Status — DESIGN.md accent에서 AA 대비로 파생 */
  --status-ok: #0f7350;      /* 5.85:1 — 추천·정상 실행·완료 텍스트 */
  --status-info: #054cff;    /* 6.03:1 — accent-indigo 원본 */
  --status-warn: #9a5b00;    /* 5.43:1 — accent-yellow 파생 */
  --status-danger: #c81b01;  /* 5.81:1 — accent-tomato 파생 */

  /* Shape — DESIGN.md rounded */
  --radius-xs: 4px;
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-full: 9999px;

  /* Spacing — DESIGN.md spacing */
  --space-xxs: 2px;
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 12px;
  --space-lg: 16px;
  --space-xl: 24px;
  --space-xxl: 32px;
  --space-huge: 64px;

  /* Elevation — DESIGN.md */
  --shadow-1: 0 1px 3px rgba(0, 0, 0, .06);
  --shadow-2: 0 8px 24px rgba(0, 0, 0, .08);
  --shadow-3: 0 16px 48px rgba(0, 0, 0, .12);

  /* Type — Circular은 상용이므로 Inter로 대체 */
  --font-sans: Inter, Pretendard, "Noto Sans KR", system-ui, -apple-system, sans-serif;
  --font-mono: ui-monospace, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
}
```

- 상태 토큰 4개는 DESIGN.md accent를 흰 배경 대비 4.5:1 이상이 되도록 어둡게 파생한 값이다. 원본 accent는 본문 텍스트 대비를 만족하지 못한다(`#ff2201` 3.83:1, `#ffdb13` 1.36:1). DESIGN.md가 금지한 장식용 accent가 아니라 **상태 전달 전용**이며, 버튼 배경이나 섹션 배경으로 쓰지 않는다.
- `--primary`는 2.00:1이라 텍스트 색이 될 수 없다. 채움(배지·CTA 배경·체크 아이콘)에만 쓰고, 녹색 의미의 글자는 `--status-ok`를 쓴다.
- `--ink-mute-2`와 `--ink-faint`는 텍스트에 쓰지 않는다. 후보 비교표의 보조 정보는 `--ink-mute`까지만 내린다.
- 타이포는 display 36px/500/-0.72px, 카드 제목 28px/500/-0.42px, 섹션 18px/500, body 16px/1.5/400, 버튼 14px/500, caption 13px, micro 12px을 쓴다. display weight는 500을 넘기지 않는다.
- 카드는 1px `--hairline` 테두리와 `--shadow-1`, 떠 있는 dialog는 `--shadow-3`을 쓴다.

### 7.3 상태 시각 언어

- Emerald 채움(`--primary`): 추천 후보 배지, `실행 승인` CTA, 완료 체크. 대응하는 글자색은 `--status-ok`.
- Indigo(`--status-info`): 익명 세션, 스냅샷 가격 안내, 분석 결과의 불확실 항목, 판단 요청 알림.
- Amber(`--status-warn`): `OVER_BUDGET` 후보, `TERMINATING` 종료 확인 대기, 주의 안내.
- Red(`--status-danger`): 실패, 파괴적 중단 확인, 오류 alert.
- 위험도는 `LOW` → 무채색, `MEDIUM` → `--status-warn`, `HIGH` → `--status-danger`로 표시하되 색만으로 전달하지 않고 `level` 텍스트와 `reasons`를 항상 함께 적는다.
- 색상과 함께 아이콘·상태 텍스트를 항상 제공한다. 색상만으로 후보 적합성이나 실행 결과를 표현하지 않는다.
- 실행 추적 화면도 흰 캔버스를 유지한다. 진행 강조는 넓은 색 면적이 아니라 배지·hairline·단계 인디케이터로 만든다.

## 8. 접근성·반응형·성능 기준

### 접근성

- 모든 입력은 visible label을 가지며, 검증 오류와 helper는 `aria-describedby`로 연결한다.
- 완료 조건 선택과 실행안 선택은 native radio group 또는 동등한 `radiogroup` 키보드 조작으로 구현한다. 선택 카드 전체가 44px 이상의 hit target을 가진다.
- dialog(승인·중단·판단)는 focus trap, `Escape` 닫기(확정 전), 최초 focus, 닫힌 뒤 trigger focus 복귀를 보장한다.
- 상태 갱신은 `aria-live="polite"`로 요약만 알린다. 폴링마다 긴 본문·focus를 바꾸지 않는다. `logTail` 갱신은 알리지 않는다.
- 텍스트 대비는 WCAG AA 이상으로 검증한다. `--ink-mute-2`와 `--ink-faint`는 텍스트에 쓰지 않고, 상태색에는 아이콘·텍스트를 병기한다.
- 마우스 hover에만 정보를 넣지 않는다. 위험도 이유, 예산 초과 사유, 추천 근거, 대체 후보는 항상 보인다.
- Provider API 키 입력은 `type="password"`에 `autocomplete="off"`를 쓰고, 저장된 값을 다시 표시하지 않는다.

### 반응형

| 구간 | 레이아웃 |
| --- | --- |
| ≥ 1024px | 12-column container. 학습 작업 요약/실행안 비교를 4:8로 분리하고 실행안 3개를 나란히 놓는다. |
| 768–1023px | app shell은 유지하되 실행안을 2열로, 감시 화면을 단일 열로 전환한다. |
| < 768px | header 축소, 폼·감시·결과 단일 열, 실행안은 세로 카드, 승인·중단 CTA는 sticky bottom bar로 고정한다. |

가로 스크롤에 의존하지 않는다. 모바일 실행안 카드에는 GPU·시간·총비용·예산 적합·위험도를 같은 순서로 놓아 비교 맥락을 유지한다.

### 성능·안정성

- 초기 bundle은 화면 단위 lazy loading과 icon tree-shaking으로 줄인다. 큰 asset을 추가하지 않는다.
- 폴링 query는 terminal 상태에서 즉시 중단하고 component unmount 때 abort한다.
- 화면에서 계산하는 값은 통화 format, 경과 시간, 상태 label뿐이다. 비용·추천·위험도를 재계산하지 않는다.
- 모든 날짜는 UTC API 값을 `Asia/Seoul` 브라우저 locale로 표기하되, 서버 raw 값을 변형·저장하지 않는다.

## 9. 테스트 우선 구현 Loop

프런트엔드는 기능 묶음이 아니라 **사용자가 관찰할 수 있는 한 행동씩** 구현한다. 각 Loop는 red → green 순서이며, red test 없이 구현을 먼저 시작하지 않는다. refactor는 green 이후 별도 code review 단계에서만 수행한다. 구현 세부사항·hook 내부 state·Query cache key·CSS class를 테스트하지 않고, 아래 공개 seam에서만 행동을 관찰한다.

### 9.1 사전 합의된 테스트 seam

| Seam | 관찰하는 공개 행동 | 도구 | 테스트하지 않는 것 |
| --- | --- | --- | --- |
| 브라우저 UI | 사용자가 입력·선택·승인·중단·판단할 때 보이는 결과와 접근 가능한 control | Testing Library | 컴포넌트 state, hook 호출 순서 |
| REST 경계 | `/session`, `/providers`, `/jobs`, `/approve`, `/cancel`, `/decisions` 요청과 명세 응답에 따른 화면 | MSW | fetch wrapper 내부, Query cache 구조 |
| 시간 경계 | 상태별 폴링 간격, terminal 상태 중단, 표시용 경과 시간, 판단 만료 | fake timer + MSW | `setInterval` 또는 라이브러리 내부 timer |
| 브라우저 저장소 | 새로고침 뒤 서버가 소유권을 허용한 Job만 복구, Provider 비밀값 미저장 | jsdom localStorage + MSW | storage helper의 private 함수 |
| 배포 앱 | same-origin cookie, 실제 backend contract, mobile/desktop 흐름 | Playwright | DOM tree의 구체적 구조 |

이 seam은 Frontend와 Backend 담당자가 구현 시작 전에 승인하는 테스트 계약이다. API field나 상태 전이 규칙이 바뀌면 fixture와 해당 seam test를 먼저 수정해 red를 만든 뒤 구현을 바꾼다.

### 9.2 한 Loop의 고정 절차

1. 이번 Loop의 표에서 **첫 번째 미구현 사용자 행동 하나**만 고른다.
2. API-spec의 알려진 값 또는 fixture의 literal을 기대값으로 한 failing test를 작성하고 red를 확인한다.
3. 해당 test를 통과시키는 최소 UI/API 코드를 작성한다. 미래 Loop의 화면·상태·추상화는 미리 만들지 않는다.
4. 같은 Loop의 다음 행동도 1–3을 반복한다. 모든 행동이 green이면 `npm run typecheck && npm run test:unit && npm run test:integration`을 실행한다.
5. green 뒤 mutation 확인을 한다. 그 Loop의 핵심 동작을 하나씩 망가뜨려 해당 test가 실제로 실패하는지 보고 복원한다.
6. code review에서만 중복 제거·구조 정리를 수행하고 위 검증을 다시 통과시킨다. refactor 때문에 새 행동을 추가하지 않는다.
7. Loop의 exit gate를 통과한 뒤에만 다음 Loop로 넘어간다. 실패한 테스트·skipped test·실제 Provider 호출은 다음 Loop로 넘기지 않는다.

### 9.3 Fixture와 Fake API 계약

MSW fixture는 백엔드가 계산한 값을 대신하는 독립 명세 데이터다. 테스트가 UI 코드와 같은 방식으로 비용이나 추천을 계산해서는 안 된다. 모든 Job fixture는 [API-spec.md](API-spec.md)의 `TrainingJob` 형식을 완전하게 만족한다.

```text
src/test/fixtures/
├─ session.json
├─ providers/
│  ├─ connected.json
│  ├─ none-connected.json
│  └─ invalid-credential.json
├─ jobs/
│  ├─ analyzing.json
│  ├─ analysis-failed.json
│  ├─ plan-ready.json
│  ├─ plan-ready-over-budget.json
│  ├─ provisioning.json
│  ├─ preparing.json
│  ├─ running.json
│  ├─ running-no-progress.json
│  ├─ awaiting-decision-replan.json
│  ├─ terminating.json
│  ├─ completed.json
│  ├─ failed.json
│  ├─ cancelled.json
│  └─ budget-stopped.json
└─ errors/
   ├─ no-eligible-plan.json
   ├─ no-provider-connected.json
   ├─ plan-expired.json
   ├─ concurrent-execution-limit.json
   ├─ execution-limit-reached.json
   ├─ session-expired.json
   └─ provider-unavailable.json
```

- `createFakeApi()`는 위 fixture를 반환하는 stateful MSW handler로 만든다. 상태 전이는 REST 응답으로만 노출한다.
- UI test는 fixture의 `reason`, `cost.estimatedTotalKrw`, `risk.level`, `resourceTeardown.status` 같은 API literal을 검증한다. 클라이언트가 계산한 값을 기대값으로 재사용하지 않는다.
- fixture ID는 문서·테스트 전용이며 production API key, Provider resource ID, Pod ID를 포함하지 않는다.
- backend의 OpenAPI schema가 준비되면 fixture를 그 schema에 검증하는 `test:contract`를 추가한다. contract mismatch는 UI 변경으로 덮지 않고 API 계약을 먼저 해결한다.

### 9.4 구현 Loop와 exit gate

일반 개발·CI에서는 MSW/Fake backend만 사용한다. 실제 Provider 호출은 Loop 8의 명시적 수동 smoke test에서만 허용한다.

| Loop | Red → Green 사용자 행동 | 이번 Loop에서 작성할 테스트 | 최소 구현 범위 | Exit gate / 다음 Loop 전 금지 범위 |
| --- | --- | --- | --- | --- |
| 0. 골격·세션 ✅ | 앱을 열면 익명 세션이 준비되고 접근 가능한 빈 폼을 본다. | `creates_an_anonymous_session_before_enabling_submission`, `renders_accessible_empty_form`, `never_labels_the_product_stage_or_run_type` | Vite/TS, DESIGN.md 토큰, app shell, API client, `POST /session`, MSW 하네스 | typecheck·unit green. **완료.** 폼 내용은 Loop 2에서 교체한다. |
| 1. 공급자 연결 | 연결된 공급자와 그 상태를 보고, 연결하거나 해제한다. 연결이 없으면 왜 제출할 수 없는지 안다. | `lists_providers_with_connection_status`, `does_not_persist_provider_secret_anywhere`, `blocks_workload_submission_without_connected_provider`, `shows_next_action_for_invalid_credential` | `getProviders`, `ProviderConnection`, 연결/해제 mutation, `NO_PROVIDER_CONNECTED` presenter | unit/integration green. Job 생성·분석은 구현하지 않는다. |
| 2. 학습 작업·분석 | 학습 작업을 제출하면 Agent가 분석 중임을 보고, 분석 결과와 확신하지 못한 항목을 확인한다. | `submits_workload_and_enters_analyzing`, `polls_analysis_every_two_seconds`, `renders_server_analysis_with_unknowns`, `keeps_input_after_analysis_failed` | `WorkloadForm` + Zod, `createJob`, ANALYZING 폴링, `AnalysisPanel` | unit/integration green. 실행안 비교·승인은 구현하지 않는다. |
| 3. 실행안 비교 | 실행안 3개의 총비용 분해·시간·위험도·대체 후보를 비교하고, 예산 초과 안은 보이되 선택할 수 없다. | `renders_three_plans_in_server_order`, `shows_total_cost_breakdown_from_server`, `keeps_over_budget_plan_visible_but_unselectable`, `shows_risk_reasons_without_hover`, `shows_snapshot_price_age` | `PlanComparison`, `PlanCard`, `CostBreakdown`, `RiskBadge`, `AlternativeList` | unit/integration green. 승인 요청은 보내지 않는다. |
| 4. 계약 승인 | 명시적 확인 전에는 승인 요청을 보내지 않고, 계약 내용을 확인한 뒤 한 번만 승인한다. 가격이 바뀌면 새 실행안을 본다. | `does_not_approve_before_confirmation`, `approves_selected_plan_exactly_once`, `shows_contract_and_auto_stop_in_dialog`, `replaces_plans_after_plan_expired`, `shows_concurrent_limit_without_losing_selection` | `ContractApproval`, `ApprovalDialog`, `approveJob`, `PLAN_EXPIRED` 처리 | `approve`가 `202`인 fixture에서 감시 화면 진입까지 green. 폴링·중단은 구현하지 않는다. |
| 5. 실행 감시·중단 | 진행 중 Job의 단계·경과·누적 비용·진행률을 보고 중단할 수 있으며, 종료 확인 전 최종 결과를 보지 않는다. | `polls_only_while_job_is_non_terminal`, `renders_execution_steps_in_server_order`, `labels_estimated_cost_as_not_metered`, `omits_progress_bar_when_progress_is_null`, `does_not_show_final_result_while_terminating`, `cancel_waits_for_server_confirmed_status` | `getJob` 폴링, `StepTimeline`, `CostMeter`, `LogTail`, cancel dialog | fake timer 포함 unit/integration green. 판단 요청·결과 화면은 구현하지 않는다. |
| 6. 판단 요청 | 판단이 필요할 때만 제안을 보고, 증분 비용·시간을 확인한 뒤 승인하거나 여기서 중단한다. | `shows_decision_panel_only_when_pending_decision_exists`, `shows_incremental_cost_and_time_delta`, `approves_decision_once_after_confirmation`, `stops_execution_when_user_declines`, `handles_expired_decision` | `DecisionPanel`, `DecisionDialog`, `resolveDecision`, 만료 처리 | unit/integration green. 결과 화면은 구현하지 않는다. |
| 7. 결과·복구 | 결과와 artifact·실제 비용·자원 종료 확인을 보고, 새로고침 후 소유한 Job만 복구하며 세션 만료는 정리한다. | `shows_outcome_with_actual_cost_and_teardown`, `marks_unconfirmed_teardown_separately`, `never_presents_estimate_as_actual_cost`, `shows_safe_failure_message_without_provider_secrets`, `lists_artifacts_and_preserved_checkpoints`, `restores_owned_job_after_reload`, `clears_saved_job_after_session_expired`, `backs_off_after_transient_polling_failures` | `ResultPanel`, `ArtifactList`, `TeardownStatus`, localStorage 복구, 폴링 backoff | unit/integration/E2E(Fake backend) green. CI가 실제 backend나 Provider를 호출하지 않는다. |
| 8. 실제 통합·리허설 | 배포된 사용자가 same-origin 세션으로 성공·예산 미달·중단 흐름을 완주한다. | `e2e_successful_execution_flow`, `e2e_no_eligible_plan`, `e2e_cancelled_execution_flow`, `e2e_plan_expired_reapproval`, `e2e_mobile_plan_review` | production API base URL, reverse proxy/CORS, Playwright, visual QA, 실제 backend 연동 | Fake backend E2E와 실제 backend의 non-Provider integration green 후, 승인된 1회 Provider smoke test를 별도 실행한다. smoke는 CI·일반 test script에서 절대 호출하지 않는다. |

## 10. 테스트 실행 체계

### 필수 script

Loop 종료 시 명령의 일부만 선택 실행하지 않고 해당 gate의 전체 명령을 실행한다.

| Script | 대상 | 실제 Provider 호출 |
| --- | --- | --- |
| `npm run typecheck` | TypeScript 및 API DTO | 없음 |
| `npm run test:unit` | formatter, presenter, UI component, fake timer | 없음 |
| `npm run test:integration` | MSW REST handler와 화면의 세로 흐름 | 없음 |
| `npm run test:contract` | fixture와 backend OpenAPI schema | 없음 |
| `npm run test:e2e:fake` | Playwright + Fake backend | 없음 |
| `npm run test:e2e:backend` | Playwright + staging backend/Fake Provider | 없음 |
| `npm run test:visual` | 375px/768px/1440px screenshot 비교 | 없음 |
| `npm run smoke:provider` | 승인된 staging 환경의 한 시나리오 | **명시적 수동 실행만** |

`smoke:provider`는 일반 `test`, CI, pre-commit script에 포함하지 않는다. `RUN_REAL_PROVIDER_SMOKE=true`가 없으면 즉시 종료하게 만들어 우발적인 비용 발생을 막는다. 실행 전 활성 Job이 없는지 확인하고, 실행 뒤 어떤 결과든 `resourceTeardown.status`를 확인한다.

### 계층별 책임

| 계층 | 대상 | 반드시 확인할 행동 |
| --- | --- | --- |
| Unit | money/time formatter, status presenter, error normalizer, poll predicate | `TERMINATING`은 final이 아니며, `actualTotalKrw`가 `null`이면 추정값을 실제 비용으로 쓰지 않는다. |
| Component | 학습 작업 폼, 실행안 카드, 승인/중단/판단 dialog, 공급자 연결 | 유효성·키보드 조작·disabled·예산 초과·위험도 표시가 정확하다. |
| API integration (MSW) | session, providers, job create/get/approve/cancel/decision client | `credentials: include`, API DTO, HTTP/code별 error mapping이 정확하다. |
| Flow integration | fake 상태 전이 | 입력 → 분석 → 비교 → 승인 → 감시 → 판단 → 결과가 REST 응답에 따라 이어진다. |
| E2E | Fake backend, 이후 staging backend | 성공, `NO_ELIGIBLE_PLAN`, `PLAN_EXPIRED`, 중단, 새로고침 복구, mobile viewport를 검증한다. |
| Visual QA | 375px / 768px / 1440px | CTA green의 절제, 정보 밀도, 대비·overflow·sticky bar를 확인한다. |

테스트는 public seam의 결과만 assert한다. API 요청 수 검증은 비용 발생 요청이 명시적 확인 전 절대 나가지 않는지처럼 사용자 행동을 보장할 때만 쓴다. private hook 호출, Query cache key, component tree, CSS class명에 대한 assertion은 금지한다.

## 11. 백엔드 연동 확인 사항과 완료 조건

이 계획의 API 계약은 프런트엔드가 [PRD-final.md](PRD-final.md)에서 도출해 [API-spec.md](API-spec.md)에 정의한 것이다. 백엔드 구현과 다음을 맞춘다.

1. 기본 배포를 same-origin reverse proxy로 구성한다. 분리 origin이 불가피하면 CORS allowlist와 `allow_credentials`를 설정하고, 두 origin이 `SameSite=Lax` cookie가 전송되는 same-site 관계인지 확인한다.
2. `TrainingJob`의 모든 nullable field와 상태별 `analysis`·`plans`·`contract`·`execution`·`pendingDecision`·`result` 채움 규칙을 fixture로 고정한다.
3. mutation이 error를 반환했을 때 Job의 최종 서버 상태를 `GET`으로 확인할 수 있게 한다. UI는 mutation 응답만으로 상태를 추정하지 않는다.
4. `PLAN_EXPIRED` 응답이 갱신된 `plans`를 `details`에 포함하는지 확인한다.
5. `failureMessage`와 `risk.reasons`가 사용자에게 안전한 짧은 문구인지 확인한다.
6. API response와 서버 로그 어디에도 Provider API key, GPU type ID, 이미지 태그, callback URL, Pod ID가 나오지 않는지 함께 점검한다.

### 기존 backend와의 차이

`backend` 브랜치의 `ai-training-cost-optimizer`는 workload 분석, 후보 비교, GPU 사용료·Agent 수수료·총비용, 예산 부족액을 이미 계산한다. 다음이 추가로 필요하다.

- `/api/v1` prefix와 camelCase 직렬화, credential CORS
- 익명 세션과 Job 소유권
- `executionCommand`, `completionCriteria`, `maxRuntimeMinutes` 입력
- 실행안 3종(`CHEAPEST`/`FASTEST`/`BALANCED`)과 `risk`, `alternatives`, `environment`
- 승인 → 환경 생성 → 준비 → 실행 → 종료 확인의 HTTP 노출 (`jobs.py`·`execution.py`의 로직은 있으나 endpoint가 없다)
- 판단 요청(`pendingDecision`)과 응답 endpoint
- artifact 목록과 서명 URL 발급
- `resourceTeardown` 확인 상태

### 완료 조건

1. 사용자는 Repository·실행 명령·완료 조건·예산·최대 실행시간만 입력해 Agent의 분석 결과와 실행안 3개를 볼 수 있다.
2. 실행안은 시간당 단가가 아니라 총비용으로 비교되고, 위험도와 대체 후보가 비용과 분리돼 표시된다.
3. 추천 실행안은 읽기 전용이며, GPU 수동 선택·Provider 콘솔·SSH·CUDA 설정 UI가 없다.
4. 비용 발생 가능성을 설명한 뒤 명시적 승인으로만 실행 요청을 보내고, 승인 직전 가격 변경은 새 실행안으로 다시 승인받는다.
5. 실행 중 단계·경과 시간·누적 비용·진행률이 상태별 폴링으로 정확히 표시되며, 자원 종료 확인 전에는 최종 결과를 표시하지 않는다.
6. 재계획·계속 투자 판단이 필요할 때만 사용자에게 증분 비용·시간과 함께 제시되고, 승인 또는 중단을 선택할 수 있다.
7. 결과 화면에 artifact, 실행 시간, 추정/실제 비용, 자원 종료 확인이 보이고, 확인되지 않은 종료는 성공으로 표시되지 않는다.
8. 공급자 미연결, 예산 미달, 가격 변경, 동시 실행 제한, 실행 횟수 제한, 세션 만료, 공급자 불가 상태가 다음 행동과 함께 이해 가능한 한국어로 안내된다.
9. 375px부터 desktop까지 핵심 흐름이 동작하고, 키보드·스크린리더·명도 대비 기준을 만족한다.
