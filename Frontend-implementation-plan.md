# UNWORK 학습 실행 Agent — MVP 프런트엔드 구현 계획서

## 1. 목적과 구현 기준

이 문서는 제한된 GPU 선택·실행 MVP의 웹 프런트엔드 구현 계획이다. 구현 판단은 아래 문서 순서로 따른다.

1. [MVP-implementation-plan.md](MVP-implementation-plan.md)
2. [API-spec.md](API-spec.md)
3. [ERD.md](ERD.md)
4. [Backend-implementation-plan.md](Backend-implementation-plan.md)
5. [PRD-final.md](PRD-final.md) — 장기 제품 방향

MVP 화면이 증명해야 할 것은 다음 한 가지다.

> 사용자는 최대 예산과 완료 우선순위만 결정하고, Agent가 비교·추천한 실행 계약을 승인한다. 사용자는 GPU 콘솔, GPU type ID, SSH, CUDA, Pod 종료를 직접 조작하지 않는다.

프런트엔드는 실행 계획을 **만들거나 변경하지 않는다.** 서버가 `POST /jobs`에서 고정한 `executionPlan`을 읽기 전용 계약으로 표시하고, 사용자의 승인·취소 의사와 현재 Job 상태를 전달한다.

### MVP 프런트엔드 범위

- 익명 세션 초기화와 cookie 기반 API 호출
- 최대 예산·우선순위 입력 및 추천 실행 계약 생성
- GPU 후보 비교, 추천 근거, 데모 추정값 한계 표시
- 실행 계약 승인과 시작 결과 처리
- `PROVISIONING`·`RUNNING`·`TERMINATING` 상태의 2.5초 폴링
- 중단 요청, 성공·실패·중단 완료 화면 및 사용자 오류 안내
- 데스크톱·모바일 반응형, 키보드 접근성, 로딩·빈 상태

### 명시적 제외 범위

- Repository·실행 명령·GPU·Provider를 사용자가 입력하거나 수정하는 UI
- Runpod 콘솔, API 키, resource ID, 이미지명, Pod ID, raw Provider 상태를 보여 주는 UI
- 실시간 로그 스트림, artifact 다운로드, 실제 비용 계측, 대기열, 재시도, OOM 재계획
- 로그인·팀·결제·실행 이력 목록

## 2. 기술 선택과 앱 경계

현재 저장소에는 웹 앱 구현체가 없으므로, 해커톤 MVP에는 **React 18 + TypeScript + Vite** 단일 페이지 앱을 기준으로 한다. 익명 session cookie가 `SameSite=Lax`인 API 명세를 따르므로, 배포 기본값은 frontend와 API를 같은 origin으로 묶는 reverse proxy다.

| 구분 | 선택 | 이유 |
| --- | --- | --- |
| UI 런타임 | React + TypeScript | Job 상태와 화면 상태를 타입으로 분리하고, 작은 단일 흐름을 빠르게 구현한다. |
| 빌드 | Vite | 서버 렌더링이 필요 없는 MVP에 가볍고 빠르다. |
| 서버 상태 | TanStack Query | `GET /jobs/{id}` 폴링·캐시·중단을 선언적으로 관리한다. |
| 폼·검증 | React Hook Form + Zod | 예산 정수 및 우선순위 enum을 API 요청 전 검증한다. |
| 스타일 | CSS variables + CSS Modules 또는 vanilla CSS | 두 디자인 레퍼런스의 토큰을 직접 유지하고, 별도 컴포넌트 라이브러리의 기본 스타일을 피한다. |
| 아이콘 | Lucide React | 상태·진행·경고를 텍스트와 함께 일관되게 전달한다. 아이콘만으로 의미를 전달하지 않는다. |
| 테스트 | Vitest + Testing Library + MSW, Playwright | 추천 계약·상태 전이·API 오류를 실제 네트워크 없이 검증하고, 브라우저 흐름을 리허설한다. |

권장 디렉터리 구조는 다음과 같다.

```text
frontend/
├─ src/
│  ├─ app/                 # App bootstrap, providers, route-level 화면 전환
│  ├─ api/                 # fetch client, API DTO, error normalizer
│  ├─ features/training/   # form, plan, approval, job tracking 기능
│  ├─ components/ui/       # token 기반 Button, Card, Dialog, Badge 등
│  ├─ styles/              # reset, tokens, global, responsive styles
│  ├─ hooks/               # useSession, useTrainingJob, useActiveJob
│  └─ test/                # MSW handlers, fixtures, test utilities
├─ .env.example
└─ package.json
```

환경변수는 `VITE_API_BASE_URL` 하나를 둔다. 같은 origin 배포에서는 빈 문자열 또는 `/api/v1` 상대 경로를 사용한다. 다른 origin을 쓸 경우에는 두 origin이 same-site여야 하고, backend의 credential CORS allowlist에도 정확한 frontend origin이 있어야 한다. `SameSite=Lax` cookie만으로는 서로 다른 site 간 XHR 세션을 유지할 수 없다. 모든 요청은 `credentials: 'include'`로 보내 HttpOnly 세션 cookie를 포함한다. 브라우저에서 Provider 비밀값을 읽거나 저장하지 않는다.

## 3. 정보 구조와 화면 흐름

별도 계정·대시보드·Job 목록이 없는 MVP이므로, 메인 route 하나 안에서 단계별 화면을 전환한다. 새로고침 복구를 위해 현재 Job ID만 `localStorage`의 `unwork.activeJobId`에 저장한다. UUID만으로는 Job을 읽을 수 없고 서버 cookie 소유권 검사가 남아 있으므로, 이 저장값은 인증 정보가 아니다. `401` 또는 `404`이면 즉시 제거한다.

```text
앱 초기화
  → POST /session
  → 제약 입력
  → POST /jobs
  → 실행 계약 검토 (DRAFT)
  → POST /jobs/{id}/start
  → Job 추적 (PROVISIONING / RUNNING / TERMINATING)
  → 최종 결과 (COMPLETED / FAILED / CANCELLED)
```

| 화면 상태 | 주 목적 | 주 API | 가능한 사용자 행동 |
| --- | --- | --- | --- |
| `CONFIGURE` | 제약을 두 가지로 한정해 입력 | `POST /session` | 예산 입력, 우선순위 선택, 실행안 비교 |
| `PLAN_LOADING` | Agent가 후보를 비교 중임을 알림 | `POST /jobs` | 이전 화면으로 돌아가기 |
| `PLAN_REVIEW` | 고정된 추천 실행 계약을 읽고 승인 | `POST /jobs/{id}` | 승인, 제약 수정 후 새 비교 |
| `STARTING` | 중복 승인 방지 및 시작 결과 대기 | `POST /jobs/{id}/start` | 없음 |
| `TRACKING` | Job 상태·선택 GPU·경과 시간 표시 | `GET /jobs/{id}` | 실행 중단 (`RUNNING`/`PROVISIONING`) |
| `RESULT` | 최종 결과와 종료 확인 전달 | `GET /jobs/{id}` | 새 실행안 만들기(실행 소진 여부에 따라 안내) |

페이지를 다시 열면 먼저 `POST /session`으로 기존 cookie 세션을 갱신한 뒤, `activeJobId`가 있으면 `GET /jobs/{id}`를 호출한다. 조회 성공 시 서버 상태에 맞는 계약 검토·추적·결과 화면으로 복구한다. 조회 실패 시 저장값을 지우고 새 세션/입력 화면을 보여 준다. 브라우저가 닫힌 동안 Pod 생애주기는 백엔드 Worker가 소유하며, 프런트엔드는 재접속 시 결과를 표시할 뿐 실행을 이어서 제어하지 않는다.

## 4. 화면 및 컴포넌트 명세

### 4.1 공통 App shell

- 상단 바: `UNWORK` 워드마크, `MVP · SD 1.5 LoRA` 배지, 우측에 `익명 데모 세션` 상태만 표시한다. 로그인·Provider 연결·설정 메뉴는 두지 않는다.
- 본문: desktop 최대 폭 1,180px, 상단 48px / 하단 64px 여백. 계약 검토 화면은 좌측 제약 요약(4/12), 우측 실행안(8/12)의 2열이다.
- 모바일: 단일 열로 접고, 상단 바는 워드마크와 상태 점만 남긴다. 핵심 CTA는 화면 하단의 sticky action bar에 둔다.
- 공통 `SystemNotice`: 추정값, 세션, API 오류 같은 제품 안내를 보여 주며 경고와 오류를 구별한다.

### 4.2 제약 입력 (`ConstraintForm`)

입력은 다음 두 개만 제공한다. GPU 종류, 공급자, 명령, 최대 실행 시간은 필드나 고급 설정으로도 노출하지 않는다.

| 요소 | 구현 | 검증·행동 |
| --- | --- | --- |
| 최대 예산 | `₩` prefix와 숫자 입력을 가진 `BudgetInput` | 0보다 큰 정수만 허용한다. 쉼표 표시는 view layer에서만 적용하고 API에는 number를 전송한다. |
| 우선순위 | `CHEAPEST` / `BALANCED` / `FASTEST` 3개 선택 카드 | 사람이 읽는 제목은 `저비용`·`균형`·`빠른 완료`, 보조문은 각각 비용·시간의 선택 기준을 설명한다. 선택값만 API enum으로 변환한다. |
| 고정 시나리오 | 읽기 전용 `ScenarioSummary` | `Stable Diffusion 1.5 LoRA`, 필요 VRAM 24GB, 최대 10분을 알려 주고 “사전 검증된 데모 작업”임을 명시한다. |
| 비교 CTA | `Agent에게 실행안 요청` | 유효할 때만 활성화한다. 제출 중에는 중복 요청을 막는다. |

폼 아래에는 “예상 비용은 실제 청구액을 제한하지 않으며, Agent는 검증된 데모 실행안 안에서 선택합니다.”를 항상 표시한다. `NO_ELIGIBLE_PLAN`은 인라인 오류 영역에 보여 주고 입력한 예산은 유지한다.

### 4.3 실행 계약 검토 (`ExecutionPlanReview`)

`POST /jobs` 응답 전체가 화면의 유일한 데이터 원본이다. 클라이언트는 추천 순위·비용·시간을 재계산하지 않는다.

- `RecommendedPlanCard`: 선택 GPU 이름, Provider(`Runpod`), 예상 실행 시간, 예상 GPU 비용, 서버가 준 `reason`을 가장 먼저 보여 준다. `recommended.profileId`는 화면에 노출하지 않는다.
- `CandidateComparison`: desktop은 표(`GPU`, `예상 시간`, `예상 GPU 비용`, `예산 적합 여부`, `추천 여부`), mobile은 후보 카드 목록이다. `OVER_BUDGET` 후보도 비교 근거로 보이되 선택 불가·비추천 상태로 표시한다.
- `ContractDetails`: 고정 시나리오, 최대 예산, 선택한 우선순위, 최대 실행 시간, `DEMO_SNAPSHOT` 배지와 API의 `estimateDisclaimer`를 표시한다. Repository URL·실행 명령은 기본 화면에서 감추고 “고정 워크로드 정보” disclosure 안에서만 읽기 전용으로 제공한다.
- `ApprovalPanel`: “승인 후 Agent가 선택된 환경을 생성하고 비용이 발생할 수 있습니다.”를 적고 `실행 승인` CTA와 `제약 수정` 보조 행동을 둔다. GPU 변경 버튼은 만들지 않는다.

`실행 승인`은 확인 dialog를 연다. dialog에는 선택 GPU, 예상 시간·비용, 예산은 실제 한도가 아니라는 안내, 한 세션에서 실제 실행은 1회라는 점을 다시 표시한다. 확인하면 `POST /jobs/{id}/start`를 한 번만 호출한다.

### 4.4 실행 추적 (`JobTracker`)

추적 화면은 상태를 숨기지 않되 사용자가 인프라를 조작하는 콘솔처럼 보이지 않아야 한다. 항상 Agent가 선택한 `gpuType`, 시작 후 경과 시간, 고정 최대 실행 시간(10분)을 보여 준다. 경과 시간은 `startedAt`을 기준으로 클라이언트에서 갱신하는 표시용 값이며, timeout 판단은 서버가 수행한다.

| API 상태 | 사용자 제목 | 상태 표현 | 행동 |
| --- | --- | --- | --- |
| `PROVISIONING` | 실행 환경을 준비하고 있어요 | 첫 단계 active, “Agent가 선택한 GPU로 Pod를 생성 중” | 중단 가능 |
| `RUNNING` | 학습을 실행하고 있어요 | 두 번째 단계 active, 펄스 상태 점 | `실행 중단` |
| `TERMINATING` | Pod 자동 종료를 확인하고 있어요 | 세 번째 단계 active, final 결과를 아직 표시하지 않음 | 모든 action 비활성 |
| `COMPLETED` | 학습이 완료됐어요 | 완료 체크 | 새 실행안 만들기 안내 |
| `FAILED` | 학습이 완료되지 않았어요 | 실패 상태 | 원인 확인, 새 실행안 만들기 안내 |
| `CANCELLED` | 실행이 중단됐어요 | 중단 상태 | 새 실행안 만들기 안내 |

`RUNNING`과 `PROVISIONING`에서만 중단 버튼을 표시한다. 누르면 destructive confirmation dialog를 열고, 확인 시 `POST /jobs/{id}/cancel`을 호출한다. `202`를 받으면 즉시 `TERMINATING` UI로 전환하고 polling을 유지한다. 서버가 `CANCELLED`를 반환하기 전에는 “중단 완료”라고 표시하지 않는다.

### 4.5 최종 결과 (`JobResult`)

- 공통: 선택 GPU, 시작·완료 시각, 실행 시간, Pod 종료 확인 여부를 표기한다. `podTerminatedAt`이 있는 경우에만 `Pod 자동 종료 완료` 체크를 보여 준다.
- 성공: `completionLog`, `exitCode: 0`, 선택 GPU, 실행 시간과 종료 확인을 표시한다.
- 실패: `failureMessage`를 우선 표시하고, `exitCode`나 `completionLog`가 있으면 세부 정보 disclosure에 표시한다. 실제 비용이나 재시도 가능성을 추정해 말하지 않는다.
- 중단: 사용자의 중단 요청을 확인하고 Pod 종료 확인을 보여 준다.
- 최종 화면의 “새 실행안 만들기”는 입력 화면으로 이동한다. 이미 실행을 사용한 동일 세션에는 버튼 대신 “이 익명 데모 세션에서는 실제 실행을 한 번만 할 수 있습니다.”를 표시한다. 새 Job의 **비용 없는 비교**는 허용되므로, 별도 `다시 비교` 행동은 제공할 수 있다.

## 5. API 연동과 상태 관리

### API client

`api/client.ts`는 base URL, JSON headers, `credentials: 'include'`, `AbortSignal`, 공통 오류 파싱만 담당한다. API DTO는 백엔드 명세의 camelCase를 그대로 사용하고, UI용 label·색상·문구는 DTO 밖의 presenter에서 관리한다.

| 함수 | HTTP | 호출 시점 | UI 처리 |
| --- | --- | --- | --- |
| `createSession()` | `POST /api/v1/session` | 앱 최초 진입, 세션 복구 실패 후 | cookie 기반 세션을 보장한다. |
| `createJob(constraint)` | `POST /api/v1/jobs` | 유효한 제약 폼 제출 | `TrainingJob`을 저장하고 계약 검토로 전환한다. |
| `getJob(jobId)` | `GET /api/v1/jobs/{id}` | 복구, 상태 polling, mutation 직후 재검증 | 서버 Job을 화면의 source of truth로 둔다. |
| `startJob(jobId)` | `POST /api/v1/jobs/{id}/start` | 승인 dialog 확인 | `202` 뒤 `getJob`을 즉시 갱신한다. |
| `cancelJob(jobId)` | `POST /api/v1/jobs/{id}/cancel` | 중단 dialog 확인 | `202` 뒤 `TERMINATING` 상태로 갱신한다. |

### 클라이언트 상태 원칙

- 서버 상태: `TrainingJob`은 TanStack Query cache에만 보관하고 mutation 성공 뒤 반드시 `GET /jobs/{id}`로 무효화한다.
- UI 상태: 폼 값, dialog 열림 여부, 현재 화면 전환만 React local state/reducer에 둔다.
- 계약 불변: `DRAFT` Job을 만든 뒤 폼을 수정해도 기존 `executionPlan`을 바꾸지 않는다. 수정 후 비교는 새 `POST /jobs`로만 만든다.
- 중복 방지: 시작·취소 mutation 동안 관련 CTA를 disabled한다. 이는 보조 장치이며 최종 동시성 제어는 백엔드 transaction이 담당한다.
- 저장: Job ID를 만든 즉시 localStorage에 기록하고, 최종 Job도 사용자가 새 흐름을 시작하기 전까지 보관한다.

### Polling 정책

```text
status ∈ {PROVISIONING, RUNNING, TERMINATING}
  → GET /jobs/{id} every 2,500ms
status ∈ {COMPLETED, FAILED, CANCELLED}
  → polling stop
```

- 화면이 다시 foreground가 되거나 start/cancel mutation이 끝나면 즉시 한 번 refetch한다.
- 네트워크 오류는 현재의 마지막 정상 상태를 유지하고 “연결을 다시 확인하는 중” 안내를 표시한다. 연속 실패는 지수 backoff(2.5초, 5초, 최대 15초)로 전환하며 최종 상태를 임의로 추정하지 않는다.
- `401 SESSION_REQUIRED`/`SESSION_EXPIRED` 또는 `404 JOB_NOT_FOUND`는 polling을 중단하고 localStorage Job ID를 제거한 뒤 세션 재시작 안내를 보여 준다.
- `TERMINATING`이 오래 지속돼도 완료·실패·취소를 앞당겨 표시하지 않는다. “Pod 종료 확인을 계속 기다리고 있습니다.”와 마지막 갱신 시각을 표시한다.

## 6. 오류와 예외 상태 문구

오류 code는 사용자에게 그대로 던지지 않고 아래와 같이 번역한다. 개발 모드에서만 원본 code를 디버그 정보로 볼 수 있다.

| 코드 | 보여 줄 메시지 | 가능한 행동 |
| --- | --- | --- |
| `VALIDATION_ERROR` | 입력한 예산과 우선순위를 다시 확인해 주세요. | 폼 수정 |
| `NO_ELIGIBLE_PLAN` | 이 예산 안에서 실행할 수 있는 데모 GPU 후보가 없습니다. | 예산 조정 후 다시 비교 |
| `DEMO_BUSY` | 다른 데모 실행이 진행 중입니다. 대기열은 제공하지 않습니다. | 계약을 유지하고 나중에 승인 재시도 |
| `EXECUTION_ALREADY_USED` | 이 익명 세션에서는 실제 실행을 한 번만 할 수 있습니다. | 비용 없는 비교 또는 새 브라우저 세션 안내 |
| `INVALID_JOB_STATE` | 이 작업은 현재 이 행동을 할 수 있는 상태가 아닙니다. | 최신 상태 다시 확인 |
| `RUNPOD_UNAVAILABLE` | 실행 환경을 시작하거나 확인하지 못했습니다. 서버 상태를 다시 확인해 주세요. | Job 새로고침; 자동 재시도 없음 |
| `SESSION_REQUIRED` / `SESSION_EXPIRED` | 데모 세션이 만료됐습니다. 새 세션을 시작해 주세요. | 세션 재시작 |
| `JOB_NOT_FOUND` | 이 작업을 찾을 수 없거나 현재 세션에서 볼 수 없습니다. | 새 실행안 만들기 |
| 알 수 없는 네트워크 오류 | 연결 상태를 확인한 뒤 다시 시도해 주세요. | 동일 행동 재시도 |

오류 메시지에는 API key, request payload, Pod ID, raw stack trace를 포함하지 않는다. 오류 toast는 일시적 요청 실패에만 사용하고, 현재 흐름을 바꾸는 오류는 해당 화면의 상단 alert로 고정해 읽을 시간을 보장한다.

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
- Indigo(`--status-info`): 익명 데모 세션, `DEMO_SNAPSHOT` 배지, 추정값 안내.
- Amber(`--status-warn`): `OVER_BUDGET` 후보, `TERMINATING` 종료 확인 대기, 주의 안내.
- Red(`--status-danger`): 실패, 파괴적 중단 확인, 오류 alert.
- 색상과 함께 아이콘·상태 텍스트를 항상 제공한다. 색상만으로 후보 적합성이나 실행 결과를 표현하지 않는다.
- 실행 추적 화면도 흰 캔버스를 유지한다. 진행 강조는 넓은 색 면적이 아니라 배지·hairline·단계 인디케이터로 만든다.

## 8. 접근성·반응형·성능 기준

### 접근성

- 모든 입력은 visible label을 가지며 예산 오류는 `aria-describedby`로 연결한다.
- priority 선택 카드는 native radio group 또는 동등한 `radiogroup` 키보드 조작으로 구현한다. 카드 전체가 44px 이상의 hit target을 가진다.
- dialog는 focus trap, `Escape` 닫기(실행·중단 확정 전), 최초 focus, 닫힌 뒤 trigger focus 복귀를 보장한다.
- 상태 갱신은 `aria-live="polite"`로 요약만 알린다. 2.5초 polling마다 긴 본문·focus를 바꾸지 않는다.
- 텍스트 대비는 WCAG AA 이상으로 검증한다. muted text를 작은 크기의 주요 정보에 사용하지 않고, green·orange·red에는 텍스트/아이콘을 병기한다.
- 마우스 hover에만 정보를 넣지 않는다. 후보 선택 불가 사유와 추천 근거는 항상 보인다.

### 반응형

| 구간 | 레이아웃 |
| --- | --- |
| ≥ 1024px | 12-column container. 제약 요약/계약 비교를 4:8로 분리하고 후보는 table로 표시한다. |
| 768–1023px | app shell은 유지하되 계약 영역을 단일 열로 전환한다. |
| < 768px | header 축소, form/결과 단일 열, 후보는 카드, 승인·중단 CTA는 sticky bottom bar로 고정한다. |

표는 화면 밖 가로 스크롤에 의존하지 않는다. 모바일 candidate card에는 GPU·시간·비용·예산 적합 여부를 같은 순서로 놓아 비교 맥락을 유지한다.

### 성능·안정성

- 초기 bundle은 route 수준 lazy loading과 icon tree-shaking으로 줄인다. 화면에 이미지가 필요 없으므로 큰 asset을 추가하지 않는다.
- polling query는 terminal 상태에서 즉시 중단하고 component unmount 때 abort한다.
- 화면에서 계산하는 값은 통화 format, 시간 경과, 상태 label뿐이다. GPU 비용·추천을 재계산하지 않는다.
- 모든 날짜는 UTC API 값을 `Asia/Seoul` 브라우저 locale로 표기하되, 서버 raw 값을 별도로 변형·저장하지 않는다.

## 9. 테스트 우선 구현 Loop

프런트엔드는 기능 묶음이 아니라 **사용자가 관찰할 수 있는 한 행동씩** 구현한다. 각 Loop는 red → green 순서이며, red test 없이 구현을 먼저 시작하지 않는다. refactor는 green 이후 별도 code review 단계에서만 수행한다. 구현 세부사항·hook 내부 state·Query cache key·CSS class를 테스트하지 않고, 아래의 공개 seam에서만 행동을 관찰한다.

### 9.1 사전 합의된 테스트 seam

| Seam | 관찰하는 공개 행동 | 도구 | 테스트하지 않는 것 |
| --- | --- | --- |
| 브라우저 UI | 사용자가 입력·선택·승인·중단할 때 보이는 결과와 접근 가능한 control | Testing Library | 컴포넌트의 state, 내부 hook 호출 순서 |
| REST 경계 | `/session`, `/jobs`, `/jobs/{id}`, `/start`, `/cancel` 요청과 명세 응답에 따른 화면 | MSW | fetch wrapper 내부 구현, Query cache 구조 |
| 시간 경계 | 2.5초 polling, terminal 상태 중단, 표시용 elapsed time | fake timer + MSW | `setInterval` 또는 라이브러리 내부 timer 구현 |
| 브라우저 저장소 | 새로고침 뒤 서버가 소유권을 허용한 Job만 복구 | jsdom localStorage + MSW | localStorage helper의 private 함수 |
| 배포 앱 | same-origin cookie, 실제 backend contract, mobile/desktop 사용자 흐름 | Playwright | DOM tree의 구체적 구조 |

이 seam은 Frontend와 Backend 담당자가 구현 시작 전에 승인하는 테스트 계약이다. API field나 상태 전이 규칙이 바뀌면 fixture와 해당 seam test를 먼저 수정해 red 상태를 만든 뒤 구현을 바꾼다.

### 9.2 한 Loop의 고정 절차

1. 이번 Loop의 표에서 **첫 번째 미구현 사용자 행동 하나**만 고른다.
2. API-spec의 알려진 값 또는 fixture의 literal을 기대값으로 한 failing test를 작성하고 `npm run test:unit -- <test-file>`로 red를 확인한다.
3. 해당 test를 통과시키는 최소 UI/API 코드를 작성한다. 미래 Loop의 화면·상태·추상화는 미리 만들지 않는다.
4. 같은 Loop의 다음 행동도 1–3을 반복한다. 모든 행동이 green이면 `npm run typecheck && npm run test:unit && npm run test:integration`을 실행한다.
5. code review에서만 중복 제거·구조 정리를 수행하고, 위 검증 명령을 다시 통과시킨다. refactor 때문에 새 행동을 추가하지 않는다.
6. Loop의 exit gate를 통과한 뒤에만 다음 Loop로 넘어간다. 실패한 테스트·skipped test·실제 Provider 호출은 다음 Loop로 넘기지 않는다.

### 9.3 Fixture와 Fake API 계약

MSW fixture는 백엔드에서 계산한 값을 흉내 내는 독립적인 명세 데이터다. 테스트가 UI 코드와 같은 방식으로 비용이나 추천을 계산해서는 안 된다. 모든 Job fixture는 [API-spec.md](API-spec.md)의 `TrainingJob` 형식을 완전하게 만족하며, backend 담당자가 제공한 계약 fixture와 비교한다.

```text
src/test/fixtures/
├─ session.json
├─ jobs/
│  ├─ draft-cheapest.json
│  ├─ draft-balanced.json
│  ├─ draft-fastest.json
│  ├─ provisioning.json
│  ├─ running.json
│  ├─ terminating-completed.json
│  ├─ completed.json
│  ├─ failed.json
│  └─ cancelled.json
└─ errors/
   ├─ no-eligible-plan.json
   ├─ demo-busy.json
   ├─ execution-already-used.json
   ├─ session-expired.json
   └─ runpod-unavailable.json
```

- `createFakeMvpApi()`는 위 fixture를 반환하는 stateful MSW handler로 만든다. `start` 뒤에는 `PROVISIONING`, 이후 `RUNNING`, completion 뒤에는 `TERMINATING → COMPLETED`를 REST 응답으로만 노출한다.
- UI test는 fixture의 `recommended.reason`, `estimatedGpuCostKrw`, `eligibility`, `podTerminatedAt` 같은 API literal을 검증한다. 클라이언트가 계산한 추천 결과를 기대값으로 재사용하지 않는다.
- fixture의 ID는 문서·테스트 전용 값이며 production API key, Runpod GPU type ID, Pod ID를 포함하지 않는다.
- backend의 Pydantic/OpenAPI schema가 준비되면, fixture를 그 schema에 검증하는 별도 `test:contract` 명령을 추가한다. contract mismatch는 UI 변경으로 덮지 않고 API 계약을 먼저 해결한다.

### 9.4 구현 Loop와 exit gate

백엔드 계획의 Loop와 같은 세로 흐름으로 진행한다. 일반 개발·CI에서는 MSW/Fake backend만 사용하며, 실제 Runpod 호출은 Loop 5의 명시적 수동 smoke test에서만 허용한다.

| Loop | Red → Green 사용자 행동 | 이번 Loop에서 작성할 테스트 | 최소 구현 범위 | Exit gate / 다음 Loop 전 금지 범위 |
| --- | --- | --- | --- | --- |
| 0. 골격·계약 | 사용자가 앱을 열면 익명 session이 준비되고 접근 가능한 빈 제약 폼을 본다. | `creates_an_anonymous_session_before_enabling_constraint_submission`, `renders_accessible_empty_constraint_form` | Vite/TS, token, app shell, API client, `POST /session`, MSW/fixture, test commands | typecheck·unit green. Job 생성·승인·polling UI는 아직 만들지 않는다. |
| 1. 제약·추천 계약 | 유효한 예산·우선순위 제출 시 서버가 준 불변 계약을 보고, 예산 미달이면 입력을 유지한 채 조정한다. | `submits_only_budget_and_priority_and_renders_server_recommended_plan`, `keeps_over_budget_candidates_visible_but_unselectable`, `keeps_constraints_after_no_eligible_plan` | `ConstraintForm`, validation, `createJob`, `ExecutionPlanReview`, candidate comparison, disclaimer | unit/integration green. GPU override, start request, cancel, polling을 구현하지 않는다. |
| 2. 승인 | 사용자는 명시적으로 확인하기 전에는 실행 요청을 보내지 않으며, 한 번의 승인만 start 요청을 보낸다. | `does_not_start_before_approval_confirmation`, `starts_once_after_confirming_execution_contract`, `shows_demo_busy_without_changing_the_contract`, `shows_execution_limit_message` | approval dialog, `startJob`, pending CTA lock, start error presenter | `start`가 `202`인 fixture에서 tracking 진입까지 green. 상태 polling·cancel은 구현하지 않는다. |
| 3. 실행 추적·중단 | 진행 중 Job은 polling하고, 사용자는 중단을 요청할 수 있지만 서버의 종료 확인 전 final 결과를 보지 않는다. | `polls_only_while_job_is_non_terminal`, `renders_provisioning_running_and_terminating_in_order`, `does_not_show_final_result_while_terminating`, `cancel_waits_for_server_confirmed_cancelled_status` | `getJob`, 2.5초 polling, status timeline, elapsed time, cancel dialog/mutation | fake timer를 포함한 unit/integration green. 실제 Runpod·실제 timeout·새로고침 복구는 구현하지 않는다. |
| 4. 최종 결과·복구 | 완료/실패/중단 결과를 안전하게 보고, 새로고침 후 소유한 Job만 복구하며 세션 만료는 정리한다. | `shows_completion_log_exit_code_and_confirmed_termination`, `shows_safe_failure_message_without_provider_secrets`, `restores_active_job_after_reload_when_session_owns_it`, `clears_saved_job_after_session_expired_or_job_not_found`, `backs_off_after_transient_polling_failures` | `JobResult`, localStorage recovery, session/error reset, polling backoff | unit/integration/E2E(Fake backend) green. CI가 실제 backend나 Runpod를 호출하지 않는다. |
| 5. 실제 통합·리허설 | 배포된 사용자가 same-origin session으로 성공·예산 미달·취소 흐름을 완주한다. | `e2e_successful_execution_flow`, `e2e_no_eligible_plan`, `e2e_cancelled_execution_flow`, `e2e_mobile_contract_review` | production API base URL, reverse proxy/CORS, Playwright, visual QA, 실제 backend 연동 | Fake backend E2E와 실제 backend의 non-Runpod integration green 후, 승인된 1회 Runpod smoke test를 별도 실행한다. smoke는 CI·일반 test script에서 절대 호출하지 않는다. |

## 10. 테스트 실행 체계

### 필수 script

`package.json`에는 아래 script를 만든다. Loop 종료 시 명령의 일부만 선택 실행하지 않고, 해당 gate의 전체 명령을 실행한다.

| Script | 대상 | 실제 Provider 호출 |
| --- | --- | --- |
| `npm run typecheck` | TypeScript 및 API DTO | 없음 |
| `npm run test:unit` | formatter, presenter, UI component, fake timer | 없음 |
| `npm run test:integration` | MSW REST handler와 화면의 세로 흐름 | 없음 |
| `npm run test:contract` | fixture와 backend OpenAPI/Pydantic schema | 없음 |
| `npm run test:e2e:fake` | Playwright + Fake backend | 없음 |
| `npm run test:e2e:backend` | Playwright + 배포 staging backend/Fake Provider | 없음 |
| `npm run test:visual` | 375px/768px/1440px screenshot 비교 | 없음 |
| `npm run smoke:runpod` | 승인된 staging 환경의 한 선택 시나리오 | **명시적 수동 실행만** |

`smoke:runpod`은 일반 `test`, CI, pre-commit script에 포함하지 않는다. 명령은 `RUN_REAL_RUNPOD_SMOKE=true`가 없으면 즉시 종료하게 만들어 우발적인 비용 발생을 막는다. smoke 실행 전에는 backend의 전역 활성 Job이 없는지 확인하고, 실행 뒤에는 `COMPLETED`/`CANCELLED`/`FAILED` 어느 결과든 `podTerminatedAt`을 확인한다.

### 계층별 책임

| 계층 | 대상 | 반드시 확인할 행동 |
| --- | --- | --- |
| Unit | money/time formatter, status presenter, error normalizer, poll predicate | `TERMINATING`은 final이 아니며 `podTerminatedAt`이 있어야 종료 완료 문구를 낸다. |
| Component | 예산 폼, priority radio cards, 후보 비교, approval/cancel dialog | 유효성·키보드 조작·disabled·예산 초과 표시가 정확하다. |
| API integration (MSW) | session, create/get/start/cancel client | `credentials: include`, API DTO, HTTP/code별 error mapping이 정확하다. |
| Flow integration | fake 상태 전이 | contract 생성 → 승인 → polling → 완료/실패/중단 화면이 REST 응답에 따라 이어진다. |
| E2E | Fake backend, 이후 staging backend/Fake Provider | 성공, `NO_ELIGIBLE_PLAN`, `DEMO_BUSY`, cancel, 새로고침 복구, mobile viewport를 검증한다. |
| Visual QA | 375px / 768px / 1440px | CTA green의 절제, information density, 대비·overflow·sticky bar를 확인한다. |

테스트는 public seam의 결과만 assert한다. API 요청 수 검증은 비용 발생 요청이 명시적 확인 전 절대 나가지 않는지처럼 사용자 행동을 보장할 때만 사용한다. private hook 호출, TanStack Query cache key, component tree, CSS class명에 대한 assertion은 금지한다.

## 11. 백엔드 연동 확인 사항과 완료 조건

프런트엔드 작업 시작 전 백엔드와 다음을 합의·확인한다.

1. 기본 배포를 same-origin reverse proxy로 구성한다. 분리 origin이 불가피하면 CORS allowlist·credential header를 설정하고, 두 origin이 `SameSite=Lax` cookie가 전송되는 same-site 관계인지 확인한다.
2. `TrainingJob` 응답의 모든 nullable field와 상태별 `startedAt`·`finishedAt`·`podTerminatedAt` 채움 규칙을 fixture로 고정한다.
3. `POST /start` 또는 `POST /cancel`이 error를 반환했을 때 Job의 최종 서버 상태를 `GET`으로 확인할 수 있게 한다. UI는 mutation 응답만으로 상태를 추정하지 않는다.
4. `TERMINATING` 장기 지속·Runpod 상태 확인 실패 시 `failureMessage`가 사용자에게 안전한 짧은 문구인지 확인한다.
5. API response와 서버 로그 어디에도 Runpod API key, GPU type ID, image, callback URL, Pod ID가 나오지 않는지 함께 점검한다.

다음이 충족되면 프런트엔드 MVP를 완료로 본다.

1. 사용자는 예산과 우선순위만 입력해 2개 이상 GPU 후보의 시간·비용 비교와 Agent 추천 근거를 볼 수 있다.
2. 추천 실행 계약은 읽기 전용이며, GPU 수동 선택·Provider 콘솔·SSH·CUDA 설정 UI가 없다.
3. 비용 발생 가능성을 설명한 뒤 명시적 승인으로만 start 요청을 보낸다.
4. `PROVISIONING`, `RUNNING`, `TERMINATING`, 최종 상태를 2~3초 polling으로 정확히 표시하며, Pod 종료 확인 전 성공·실패·중단 완료를 표시하지 않는다.
5. 성공 화면에는 완료 로그·종료 코드·실행 시간·선택 GPU·Pod 자동 종료 완료가, 실패/중단 화면에는 안전한 원인·종료 결과가 보인다.
6. 예산 미달, 다른 데모 실행 중, 세션당 실행 1회 제한, 세션 만료, Provider 불가 상태가 다음 행동과 함께 이해 가능한 한국어로 안내된다.
7. 375px부터 desktop까지 핵심 흐름이 동작하고, 키보드·스크린리더·명도 대비 기준을 만족한다.
