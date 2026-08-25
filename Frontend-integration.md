# 프런트엔드 연동 안내 (백엔드 → 프런트엔드)

백엔드 `/api/v1`이 `backend` 브랜치에 구현·검증돼 있다. 이 문서는 프런트엔드가 MSW를 벗기고 실제 백엔드에 붙일 때 필요한 것과, [frontend/docs/api-contract.md](.) 초안과 실제 구현이 어긋나는 지점을 정리한 것이다.

기준 계약은 [API-spec.md](API-spec.md)이고, 실제 응답 샘플 18건은 [api-samples.json](api-samples.json)에 있다. 샘플은 손으로 쓴 것이 아니라 돌아가는 서버에서 그대로 캡처한 값이므로 MSW fixture로 바로 써도 된다.

## 1. 먼저 확인한 것

프런트엔드가 **이미 구현한** 코드는 백엔드와 일치한다. 고칠 것이 없다.

| 프런트엔드 | 백엔드 | 상태 |
| --- | --- | --- |
| `client.ts` — base `/api/v1`, `credentials: 'include'` | 세션 쿠키 기반 | 일치 |
| `session.ts` — `{ expiresAt }` | 동일 | 일치 |
| `errors.ts` — `{ error: { code, message } }` | 동일 | 일치 |
| `ConstraintForm` — `maxBudgetKrw`, `priority` 두 값만 | `POST /jobs` 입력과 동일 | 일치 |
| `scenario.ts` — CHEAPEST / BALANCED / FASTEST | 동일한 세 정책 | 일치 |

## 2. 붙이기 전에 필요한 두 가지

### 2-1. Vite dev proxy

현재 `vite.config.ts`에 proxy가 없어 `/api/v1` 요청이 Vite dev 서버로 가서 404가 난다.

```ts
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } },
  },
})
```

proxy를 쓰면 브라우저 기준 same-origin이 되어 CORS와 SameSite 문제를 둘 다 피한다. `VITE_API_BASE_URL`은 기본값(`/api/v1`) 그대로 두면 된다.

다른 origin으로 직접 붙이려면 백엔드에 `FRONTEND_ORIGINS=http://localhost:5173`을 설정한다. 백엔드는 자격증명 포함 요청을 허용하며 wildcard origin은 무시한다.

### 2-2. 로컬에서는 `MVP_COOKIE_SECURE=false`

세션 쿠키는 기본이 `Secure`다. `Secure` 쿠키는 `http://`로 전송되지 않으므로 이 설정 없이는 세션이 매 요청 끊긴다. proxy를 써도 마찬가지다 (브라우저가 보는 주소가 `http://localhost:5173`이므로).

```bash
cd ai-training-cost-optimizer
export MVP_PROVIDER_MODE=fake MVP_COOKIE_SECURE=false
python -m uvicorn training_cost_optimizer.api:app --port 8000
```

배포 환경에서는 이 값을 건드리지 않는다 (기본 `true`).

### 로컬 `fake` 모드가 하는 일

Runpod을 호출하지 않고 GPU 생애주기만 재현한다. Pod는 약 10초 뒤 `RUNNING`이 되고, 종료 요청을 받으면 `TERMINATED`가 된다. 서버의 상태 감시 주기는 5초이므로 `PROVISIONING → RUNNING`은 10~15초 걸린다.

학습 컨테이너가 로컬에 없으므로 완료 화면을 보려면 완료 callback을 직접 호출한다.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/internal/jobs/<jobId>/completion \
  -H "Content-Type: application/json" \
  -d '{"outcome":"SUCCEEDED","exitCode":0,"message":"Training completed"}'
```

## 3. 응답 형태

전체는 [api-samples.json](api-samples.json)에 있다. 화면을 만들 때 필요한 요점만 옮기면 다음과 같다.

- `POST /jobs`와 `GET /jobs/{id}`는 **같은 형태**를 반환한다. 상태만 달라진다.
- 실행안은 `executionPlan.candidates[]`와 `executionPlan.recommended`로 나뉜다. `recommended`에는 `reason`이 있고 `eligibility`가 없다. `candidates[]`에는 반대로 `eligibility`(`ELIGIBLE` / `OVER_BUDGET`)가 있고 `reason`이 없다.
- 예산 안에 후보가 하나도 없으면 Job을 만들지 않고 `422 NO_ELIGIBLE_PLAN`이다. 부분 성공은 없다.
- `status`: `DRAFT → PROVISIONING → RUNNING → TERMINATING → COMPLETED | FAILED | CANCELLED`
- `exitCode`, `completionLog`, `finishedAt`, `podTerminatedAt`은 종료 전까지 `null`이다.
- 시간 값은 모두 `...Z`로 끝나는 ISO 8601 UTC다.

### 오류 코드

| HTTP | 코드 | 언제 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 요청 형식 오류 (예: `maxBudgetKrw`가 0 이하) |
| 401 | `SESSION_REQUIRED` / `SESSION_EXPIRED` | 쿠키 없음 또는 만료 |
| 404 | `JOB_NOT_FOUND` | 없거나 현재 세션의 Job이 아님 |
| 409 | `EXECUTION_ALREADY_USED` | 이 세션의 실행 횟수 소진 |
| 409 | `DEMO_BUSY` | 다른 실행이 진행 중 (대기열 없음) |
| 409 | `INVALID_JOB_STATE` | 이미 끝난 Job을 취소하는 등 |
| 422 | `NO_ELIGIBLE_PLAN` | 예산 안에 후보 없음 |
| 503 | `RUNPOD_UNAVAILABLE` | 실행 설정 오류 |

`details` 필드는 MVP 응답에 없다. 초안에 있던 `minimumRequiredBudgetKrw`도 아직 내려주지 않는다.

## 4. 초안과 구현의 차이

`frontend/docs/api-contract.md`는 PRD 전체 기준이라 지금 구현 범위보다 넓다. 아래는 **구현되지 않은 것**이므로 실제 백엔드에 붙는 화면에서는 쓰지 않는다. MSW 안에서만 유지한다.

| 초안 | 현재 |
| --- | --- |
| `POST /jobs`에 `repositoryUrl`, `revision`, `executionCommand`, `completionCriteria`, `maxRuntimeMinutes` | 입력은 `maxBudgetKrw`, `priority` 둘뿐. workload는 서버 고정 상수 |
| `status: ANALYZING`, `PLAN_READY`, `PREPARING`, `AWAITING_DECISION`, `BUDGET_STOPPED` | 없음. `DRAFT`가 초안의 `PLAN_READY`에 해당 |
| `analysis` (framework, CUDA, 의존성, unknowns) | 없음 |
| `plans[]` 3개 + `POST /jobs/{id}/approve { planId }` | `executionPlan.candidates[]` + `recommended` 하나. 실행은 `POST /jobs/{id}/start` (본문 없음) |
| `cost.agentFeeKrw`, `storageAndTransferKrw`, `estimatedTotalKrw` | `estimatedGpuCostKrw` 하나 |
| `risk`, `alternatives`, `environment` | 없음 |
| `execution.steps`, `cost.accruedKrw`, `progress`, `logTail` | 없음. 상태 문자열과 `startedAt`만 |
| `result.artifacts`, `checkpoints`, `resourceTeardown` | 없음. `exitCode`, `completionLog`, `podTerminatedAt`만 |
| `GET /providers`, `POST /providers/{id}/credential` | 없음. 팀 단일 계정 |
| `pendingDecision`, `POST /jobs/{id}/decisions/{id}` | 없음 |
| `PLAN_EXPIRED` (승인 직전 가격 재검증) | 없음. 스냅샷 가격이라 재검증 대상이 없다 |
| 세션 응답의 `executionAllowance` | 없음. `expiresAt`만 |

## 5. 프런트엔드에서 고쳐야 할 것 하나

`features/training/scenario.ts`의 `DEMO_SCENARIO.maxRuntimeMinutes = 10`이 하드코딩돼 있다. 백엔드는 이 값을 Job마다 응답의 `scenario.maxRuntimeMinutes`로 내려주고, 서버 설정(`MVP_MAX_RUNTIME_MINUTES`)으로 바뀔 수 있다. 부스 시연에서 상한을 1분으로 낮춰 자동 종료를 보여줄 계획이므로, 화면은 상수 대신 응답 값을 읽어야 한다.

`name`, `requiredVramGb`도 같은 이유로 응답의 `scenario`에서 읽는 편이 안전하다. Job을 만들기 전 화면에서 미리 보여줘야 한다면 상수를 유지하되, Job 응답을 받은 뒤에는 응답 값으로 덮어쓴다.

## 6. 합의가 필요한 것

아래 세 가지는 백엔드가 임의로 정하지 않고 남겨둔다.

1. **후보 선택권** — 지금은 사용자가 우선순위를 고르면 Agent가 하나를 추천하고 그대로 실행한다. 초안처럼 후보 3개를 보여주고 사용자가 그중 하나를 골라 실행하게 하려면 `POST /jobs/{id}/start`가 `{ planId }`를 받아야 한다. 저장된 스냅샷 안에서만 고르는 것이라 계약 불변 원칙과는 충돌하지 않는다.
2. **`DEMO_BUSY` 이름** — 프런트엔드가 UI 문구에서 데모 단계 표현을 걷어내기로 했는데 이 코드에는 남아 있다. `CONCURRENT_EXECUTION_LIMIT` 같은 이름으로 바꿀 수 있다. 바꾸면 API-spec.md도 함께 고친다.
3. **세션 응답의 `executionAllowance`** — 세션당 1회 제한을 화면에서 미리 안내하려면 필요하다. 백엔드는 이미 알고 있는 값이라 추가는 어렵지 않다.

정해지면 백엔드가 구현하고 API-spec.md에 반영한 뒤 알린다.
