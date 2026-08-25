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

## 5. 프런트엔드에서 고쳐야 할 것 하나

`features/training/scenario.ts`의 `DEMO_SCENARIO.maxRuntimeMinutes = 10`이 하드코딩돼 있다. 백엔드는 이 값을 Job마다 응답의 `scenario.maxRuntimeMinutes`로 내려주고, 서버 설정(`MVP_MAX_RUNTIME_MINUTES`)으로 바뀔 수 있다. 부스 시연에서 상한을 1분으로 낮춰 자동 종료를 보여줄 계획이므로, 화면은 상수 대신 응답 값을 읽어야 한다.

`name`, `requiredVramGb`도 같은 이유로 응답의 `scenario`에서 읽는 편이 안전하다. Job을 만들기 전 화면에서 미리 보여줘야 한다면 상수를 유지하되, Job 응답을 받은 뒤에는 응답 값으로 덮어쓴다.

## 6. 합의 결과 (반영 완료)

| 항목 | 결정 | 상태 |
| --- | --- | --- |
| 후보 선택권 | 우선순위 기반 추천 1개를 승인하는 현행 유지. `start`는 본문을 받지 않는다 | 변경 없음 |
| `DEMO_BUSY` 이름 | 코드 이름은 유지. 대신 사용자에게 나가는 문구에서 데모 단계 표현을 걷어냄 | 반영 완료 |
| 세션 `executionAllowance` | 추가한다 | 반영 완료 |

### 사용자 문구 정책

응답의 `message`, `failureMessage`, `reason`에는 데모 단계 표현(데모, MVP)과 인프라 용어(Pod, provisioning)를 쓰지 않는다. 테스트로 고정해 두었다.

바뀐 문구는 다음과 같다. MSW fixture를 쓰고 있다면 함께 고쳐야 한다.

| 이전 | 현재 |
| --- | --- |
| 다른 데모 실행이 진행 중입니다… | 다른 실행이 진행 중입니다. 잠시 후 다시 시도해 주세요. |
| 입력한 예산 안에서 실행할 수 있는 데모 GPU 후보가 없습니다. | 입력한 예산 안에서 실행할 수 있는 GPU 후보가 없습니다. |
| 예상 시간과 GPU 비용은 데모 전 검증한 프로필 스냅샷이며… | 예상 시간과 GPU 비용은 사전 검증한 실행 프로필 기준 추정치이며 실제 청구액을 보장하지 않습니다. |
| Job을 찾을 수 없습니다. | 요청한 작업을 찾을 수 없습니다. |
| Draft Job만 실행할 수 있습니다. | 이미 실행했거나 실행할 수 없는 작업입니다. |
| 현재 Job 상태에서는 종료를 요청할 수 없습니다. | 현재 상태에서는 중단할 수 없습니다. |
| Pod 생성에 실패했습니다. | 실행 환경을 만들지 못했습니다. |
| Pod provisioning에 실패했습니다. | 실행 환경 준비에 실패했습니다. |
| Pod 상태를 확인할 수 없습니다. | 실행 환경 상태를 확인하지 못했습니다. |
| Pod 종료를 확인할 수 없습니다. | GPU 종료를 확인하지 못했습니다. |

오류 `code`(`DEMO_BUSY` 포함)와 `priceDataType`(`DEMO_SNAPSHOT`)은 기계 판독 값이라 그대로 둔다. **이 값들을 화면에 그대로 출력하지 않는다.** 코드는 화면 문구로 매핑하고, `priceDataType`은 "추정치" 같은 표현으로 바꿔 보여준다.

### 세션 응답

```json
{
  "expiresAt": "2026-09-01T19:40:35.305815Z",
  "executionAllowance": { "used": 0, "limit": 1 }
}
```

`used`가 `limit`에 도달하면 그 세션은 더 실행할 수 없다. 실행 버튼을 누르기 전에 안내하면 `409 EXECUTION_ALREADY_USED`를 모르고 맞는 일이 줄어든다.


---

## 7. 실제 GPU에서 재본 사실 (화면 설계에 영향)

2026-08-26에 실제 Runpod GPU(RTX 4090)로 학습을 끝까지 돌렸다. 시뮬레이터와 시간 분포가 크게 다르므로 화면이 이를 전제해야 한다.

| 구간 | 실측 |
| --- | --- |
| `PROVISIONING` (GPU 확보 + 이미지 내려받기 + 모델 로딩) | 약 7분 30초 |
| `RUNNING` (학습 50 step) | 7초 |
| `TERMINATING` (삭제 요청 + 종료 확인) | 약 1초 |

- **`PROVISIONING`이 몇 분씩 이어진다.** 이 구간을 짧게 지나가는 단계로 다루면 사용자가 멈춘 것으로 오해한다. 경과 시간과 단계 안내가 필요하다.
- **`RUNNING`을 못 보고 지나갈 수 있다.** 학습이 7초면 2~3초 폴링으로 한 번도 안 잡힐 수 있다. 상태 전이를 순서대로 모두 거친다고 가정하지 않는다.

### `startedAt`은 실행 승인 시각이다

Pod 생성 요청보다 앞선다. 승인 트랜잭션이 커밋되는 순간에 찍히고, 그 뒤에야 Worker가 Pod를 만든다. 따라서 `startedAt` 기준 경과 시간은 **사용자가 승인 버튼을 누른 뒤 기다린 전체 시간**이며, 준비 구간이 포함된다.

최대 실행시간도 같은 기준이다. 학습 시간이 아니라 승인 이후 전체 시간을 덮으므로, 준비에 7분 30초가 들면 10분 상한에서는 학습에 2분 반만 남는다. 그래서 실제 GPU 실행에는 상한을 15분으로 둔다. 화면이 `scenario.maxRuntimeMinutes`를 응답에서 읽으면 이 변경이 그대로 반영된다.

### `POST /session`은 만들거나 갱신한다

유효한 쿠키가 함께 오면 같은 세션의 만료를 연장하고 **같은 토큰**을 돌려준다. 새 세션을 발급하지 않으므로 세션을 다시 읽어도 진행 중인 Job의 소유권이 끊기지 않는다. 쿠키가 없거나 만료됐을 때만 새로 만든다. `executionAllowance`는 이 경로에서 매번 현재 값으로 계산되므로, 실행 승인 직후 다시 읽으면 `used: 1`이 온다.

### 전역 동시 실행 제한과 테스트 순서

서비스 전체 동시 실행 1건 제한은 `PROVISIONING`, `RUNNING`, `TERMINATING` 세 상태를 모두 센다. 앞 시나리오가 `TERMINATING`에 남아 있으면 다음 시나리오의 start가 `DEMO_BUSY`로 막힌다. 실행하는 E2E는 직렬로 돌리고 반드시 최종 상태까지 끌고 간 뒤 끝내야 한다.


---

## 8. Vercel 배포: 쿠키를 잃지 않으려면 rewrite 를 쓴다

프런트엔드를 Vercel, 백엔드를 Railway에 두면 브라우저 입장에서 **서로 다른 사이트**가 된다. 이 상태에서 세션 쿠키를 직접 주고받으면 두 가지가 동시에 걸린다.

1. `SameSite=Lax` 쿠키는 cross-site fetch 에 실리지 않는다 → 모든 요청이 401
2. `SameSite=None; Secure` 로 바꿔도 **third-party 쿠키**가 되어 Safari 는 기본 차단, Chrome 도 차단 방향이다 → 심사위원이 아이폰으로 열면 로그인 자체가 안 되는 것과 같은 상태가 된다

데모 당일 아이폰 하나로 무너질 수 있는 지점이다.

### 해결: Vercel rewrite 로 같은 origin 에서 부른다

개발에서 쓰는 Vite proxy 와 같은 모양을 배포에도 적용한다. 브라우저는 Vercel 주소만 보게 되므로 same-origin 이 되고, 쿠키 문제와 CORS 가 **둘 다 사라진다.**

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://miraculous-bravery-production-2d72.up.railway.app/api/:path*"
    }
  ]
}
```

`vercel.json` 에 넣으면 된다. 이렇게 하면

- `VITE_API_BASE_URL` 은 기본값 `/api/v1` 그대로 둔다
- 백엔드 쿠키는 `SameSite=Lax` 유지 (바꿀 필요 없다)
- 백엔드 `FRONTEND_ORIGINS` 도 필요 없다. cross-origin 요청 자체가 생기지 않는다
- Safari·iOS 에서도 동작한다

### rewrite 를 쓰지 않는 경우

굳이 브라우저가 Railway 를 직접 부르게 하려면 백엔드에 다음이 필요하다.

```text
MVP_COOKIE_SAMESITE=none
FRONTEND_ORIGINS=https://<vercel 도메인>
```

`none` 은 `Secure` 없이는 브라우저가 버리므로 서버가 기동 단계에서 막는다. 그래도 Safari 의 third-party 쿠키 차단은 남는다. Vercel preview 배포는 매번 다른 주소가 생겨 `FRONTEND_ORIGINS` 에 걸리지 않는 문제도 따라온다. rewrite 를 권한다.
