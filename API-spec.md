# UNWORK 학습 실행 Agent — MVP API 명세

`PRD-final.md`와 `ERD.md`를 기준으로 한 REST API 명세다. API의 중심 리소스는 GPU VM이 아닌 **Training Job**이다.

## 1. 공통 규약

- Base URL: `/api/v1`
- Content-Type: `application/json`
- 모든 ID: UUID 문자열
- 모든 시간: ISO 8601 UTC (`2026-08-25T12:00:00Z`)
- 모든 금액: USD 문자열 (`"1.2450"`). 부동소수점으로 전달하지 않는다.
- MVP 실행 Provider: `RUNPOD`만 허용한다. 응답의 `provider` 필드는 공급자 어댑터 확장을 위한 값이다.
- 웹 배포 MVP는 익명 세션으로 Job 소유권을 분리한다. 회원가입·로그인 UI는 없지만 모든 `/jobs` 요청은 세션 소유자를 검증한다.
- 세션 쿠키: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/api/v1`, 최대 7일. 개발 환경의 HTTP에서는 `Secure`만 해제한다.
- `POST`, `PUT`, `PATCH`, `DELETE` 요청은 세션 쿠키와 `X-CSRF-Token` 헤더를 함께 요구한다. 단, 세션을 처음 만드는 `POST /session`은 예외다. `GET`은 CSRF 토큰을 요구하지 않는다.

### 익명 세션

### `POST /session`

익명 세션을 생성하거나 현재 세션을 갱신한다. 서버는 암호학적으로 안전한 세션 토큰을 `HttpOnly` 쿠키로 설정하고, DB에는 토큰의 해시와 만료 시각만 저장한다.

Request body: 없음

Response: `201 Created`

```json
{
  "expiresAt": "2026-09-01T12:00:00Z",
  "csrfToken": "opaque-csrf-token"
}
```

프런트엔드는 `csrfToken`을 메모리에만 보관하고 이후 상태 변경 요청의 `X-CSRF-Token` 헤더에 넣는다. 서로 다른 세션의 Job은 존재를 노출하지 않도록 `404`를 반환한다.

### 공통 오류 응답

```json
{
  "error": {
    "code": "PLAN_NOT_APPROVABLE",
    "message": "선택한 실행안은 더 이상 승인할 수 없습니다.",
    "details": { "planId": "uuid" }
  }
}
```

| HTTP | 대표 코드 | 의미 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 필수값·형식·범위 오류 |
| 401 | `SESSION_REQUIRED`, `SESSION_EXPIRED` | 세션 쿠키가 없거나 만료됨 |
| 403 | `CSRF_TOKEN_INVALID` | 상태 변경 요청의 CSRF 토큰이 없거나 불일치 |
| 404 | `JOB_NOT_FOUND`, `ARTIFACT_NOT_FOUND` | 리소스 없음 |
| 409 | `INVALID_JOB_STATE`, `ACTIVE_ATTEMPT_EXISTS`, `DUPLICATE_APPROVAL` | 현재 상태에서 수행 불가 또는 중복 요청 |
| 422 | `ANALYSIS_FAILED`, `NO_FEASIBLE_PLAN`, `PLAN_NOT_APPROVABLE`, `PROVIDER_CREDENTIAL_REQUIRED`, `INVALID_PROVIDER_CREDENTIAL` | 형식은 맞지만 실행 계획을 만들거나 승인할 수 없음 |
| 429 | `ANALYSIS_IN_PROGRESS` | 같은 Job 분석이 진행 중 |
| 503 | `PROVIDER_UNAVAILABLE` | Runpod 재검증 또는 Provider API 호출 실패 |

### Job 상태

`DRAFT → ANALYZING → AWAITING_APPROVAL → PROVISIONING → PREPARING → RUNNING → FINALIZING → COMPLETED`

종료 상태는 `COMPLETED`, `FAILED`, `CANCELLED`다. 자원 종료를 확인하지 못하면 `CLEANUP_ATTENTION_REQUIRED`이며, 정상 완료로 표시하지 않는다.

## 2. 핵심 리소스 형식

### TrainingJob

```json
{
  "id": "job_uuid",
  "repositoryUrl": "https://github.com/example/training-repo",
  "executionCommand": "python train.py --steps 100",
  "completionCondition": "100 steps completed and output artifact uploaded",
  "maxBudgetUsd": "3.0000",
  "maxRuntimeMinutes": 60,
  "status": "AWAITING_APPROVAL",
  "activePlanId": "plan_uuid",
  "activeAttempt": null,
  "createdAt": "2026-08-25T12:00:00Z",
  "updatedAt": "2026-08-25T12:01:00Z",
  "completedAt": null
}
```

### PlanOption

```json
{
  "id": "option_uuid",
  "strategy": "BALANCED",
  "isExecutable": true,
  "provider": "RUNPOD",
  "gpuType": "NVIDIA RTX 4090",
  "vramGb": 24,
  "region": "US-CA",
  "availabilityStatus": "AVAILABLE",
  "hourlyGpuPriceUsd": "0.6900",
  "estimatedRuntimeMinutes": 42,
  "estimatedGpuCostUsd": "0.4830",
  "estimatedStorageTransferCostUsd": "0.0000",
  "agentFeeUsd": "0.0000",
  "estimatedTotalCostUsd": "0.4830",
  "riskLevel": "LOW",
  "selectionRationale": "예산 안에서 필요한 VRAM을 만족하는 균형형 후보입니다.",
  "priceObservedAt": "2026-08-25T12:02:00Z"
}
```

`strategy`는 `CHEAPEST`, `FASTEST`, `BALANCED` 중 하나다. 실행할 수 없는 옵션은 `isExecutable: false`와 `unavailableReason`을 반환한다.

### ExecutionAttempt 요약

```json
{
  "id": "attempt_uuid",
  "attemptNo": 1,
  "attemptKind": "INITIAL",
  "status": "RUNNING",
  "stopReason": null,
  "elapsedSeconds": 900,
  "currentEstimatedTotalCostUsd": "0.1725",
  "startedAt": "2026-08-25T12:05:00Z",
  "endedAt": null
}
```

## 3. Job 생성·수정·조회

### `POST /jobs`

학습 Job을 생성한다. 생성만으로 분석·Provider 호출·비용 발생은 없다.

Request:

```json
{
  "repositoryUrl": "https://github.com/example/training-repo",
  "executionCommand": "python train.py --steps 100",
  "completionCondition": "100 steps completed and output artifact uploaded",
  "maxBudgetUsd": "3.0000",
  "maxRuntimeMinutes": 60
}
```

| 필드 | 규칙 |
| --- | --- |
| `repositoryUrl` | Public GitHub HTTPS URL |
| `executionCommand` | 공백이 아닌 실행 명령 |
| `completionCondition` | 완료 판정 가능한 조건. MVP Golden Path는 step/epoch 완료와 artifact 업로드만 허용 |
| `maxBudgetUsd` | 0 초과 |
| `maxRuntimeMinutes` | 1 이상, 서비스 상한 이하 |

Response: `201 Created` — `TrainingJob` (`status: DRAFT`)

### `GET /jobs`

Job 목록을 최신순으로 반환한다.

Query: `status`, `cursor`, `limit`(기본 20, 최대 50)

Response: `200 OK`

```json
{
  "items": [{ "id": "job_uuid", "status": "RUNNING", "repositoryUrl": "..." }],
  "nextCursor": null
}
```

### `GET /jobs/{jobId}`

Job, 현재 Plan, 활성 Attempt의 요약을 반환한다.

Response: `200 OK` — `TrainingJob`

### `PATCH /jobs/{jobId}`

승인 전 입력을 수정한다. 허용 상태는 `DRAFT`, `ANALYSIS_FAILED`, `AWAITING_APPROVAL`이다. `AWAITING_APPROVAL`에서 수정하면 이전 Plan은 `SUPERSEDED`가 된다.

Request는 `POST /jobs`의 필드를 부분적으로 받는다. 승인된 Contract가 있거나 활성 Attempt가 있으면 `409 INVALID_JOB_STATE`를 반환한다.

Response: `200 OK` — 수정된 `TrainingJob` (`status: DRAFT`)

## 4. API 키 연결과 분석

### `PUT /jobs/{jobId}/provider-credential`

이 Job이 사용할 Provider API 키를 Vault에 일시 보관한다. DB에는 `secretVaultRef`만 기록한다.

Request:

```json
{
  "provider": "RUNPOD",
  "apiKey": "rp_live_..."
}
```

Response: `204 No Content`

- `apiKey`는 응답·로그·이벤트·DB에 원문으로 저장하거나 반환하지 않는다.
- API 키 연결은 **분석 및 Plan 생성 전에 필요**하다. Runpod의 현재 GPU 사양·가격·가용성 조회에 API 키가 필요하기 때문이다. 이 조회는 VM을 생성하지 않으므로 GPU 비용을 발생시키지 않는다.
- Job이 `COMPLETED`, `FAILED`, `CANCELLED` 또는 `CLEANUP_ATTENTION_REQUIRED`로 끝나면 Credential을 폐기한다.
- 승인 전에는 교체할 수 있고, 승인 뒤 생성된 Contract에 연결한 후에는 변경할 수 없다.

### `POST /jobs/{jobId}/analyses`

Repository와 실행 명령을 분석하여 지원 가능 여부, commit SHA, Runtime Requirement, Plan을 비동기로 생성한다. 최신 GPU 사양·가격·가용성을 포함한 Plan을 만들기 위해 유효한 Provider Credential이 필요하다.

Response: `202 Accepted`

```json
{
  "jobId": "job_uuid",
  "analysisId": "analysis_uuid",
  "status": "ANALYZING"
}
```

분석이 끝나면 Job은 `AWAITING_APPROVAL`이 된다. 지원 불가·필수값 불명은 `ANALYSIS_FAILED`가 되며 `GET /jobs/{jobId}/analyses/latest`에서 이유를 확인한다. Credential이 없거나 유효하지 않으면 `422 PROVIDER_CREDENTIAL_REQUIRED` 또는 `422 INVALID_PROVIDER_CREDENTIAL`을 반환한다.

### `GET /jobs/{jobId}/analyses/latest`

최신 분석 결과를 반환한다.

```json
{
  "id": "analysis_uuid",
  "sequenceNo": 1,
  "status": "SUCCEEDED",
  "resolvedCommitSha": "a1b2c3d4",
  "framework": "PYTORCH",
  "runtimeRequirements": { "python": "3.10", "cuda": "12.1" },
  "requiredVramGb": 16,
  "requirementConfidence": "ESTIMATED",
  "failureReason": null,
  "analyzedAt": "2026-08-25T12:02:00Z"
}
```

## 5. 실행 계획과 승인

### `GET /jobs/{jobId}/plans/latest`

최신 실행 계획과 최대 세 옵션을 반환한다.

Response: `200 OK`

```json
{
  "id": "plan_uuid",
  "versionNo": 1,
  "status": "AWAITING_APPROVAL",
  "analysisId": "analysis_uuid",
  "options": [{ "id": "option_uuid", "strategy": "BALANCED" }],
  "generatedAt": "2026-08-25T12:03:00Z"
}
```

Plan이 없거나 실행 가능한 Option이 없으면 `422 NO_FEASIBLE_PLAN`을 반환한다.

### `POST /jobs/{jobId}/contracts`

선택 Option을 재검증하고 실행 계약을 승인한다. 이 요청에서만 실제 Provider 자원 생성이 시작될 수 있다.

Headers:

```text
Idempotency-Key: 2e76f1bd-...
```

Request:

```json
{
  "planId": "plan_uuid",
  "selectedOptionId": "option_uuid"
}
```

성공 Response: `201 Created`

```json
{
  "contractId": "contract_uuid",
  "status": "APPROVED",
  "attempt": {
    "id": "attempt_uuid",
    "attemptNo": 1,
    "status": "PROVISIONING"
  },
  "jobStatus": "PROVISIONING"
}
```

승인 처리 규칙:

1. 선택 Option의 가격·가용성·GPU 유형을 승인 직전에 재조회한다.
2. 값이 바뀌거나 Budget을 넘으면 기존 Plan을 `SUPERSEDED` 처리하고 `409 PLAN_NOT_APPROVABLE`을 반환한다.
3. 같은 `Idempotency-Key`는 최초 응답을 그대로 반환하며, 하나의 Plan에 활성 Attempt는 하나만 존재한다.
4. Contract에는 Repository URL, 분석 commit SHA, 명령, 예산, 시간 상한, 가격, Golden Path 버전 스냅샷을 고정한다.

## 6. 실행 상태·비용·이벤트

### `GET /jobs/{jobId}/attempts/{attemptId}`

현재 또는 과거 Attempt의 상세 상태를 반환한다.

Response: `200 OK` — `ExecutionAttempt` 요약에 다음을 추가한다.

```json
{
  "resource": {
    "status": "RUNNING",
    "terminationRequestCount": 0
  },
  "latestCost": {
    "elapsedSeconds": 900,
    "estimatedGpuCostUsd": "0.1725",
    "estimatedTotalCostUsd": "0.1725",
    "observedAt": "2026-08-25T12:20:00Z"
  },
  "budgetStatus": "NORMAL"
}
```

`budgetStatus`: `NORMAL`, `WARNING_80`, `STOPPING_90`, `EXCEEDED_TECHNICAL_VARIANCE`.

### `GET /jobs/{jobId}/cost-snapshots`

비용 추이 데이터를 반환한다.

Query: `attemptId`(선택), `from`, `to`, `limit`(기본 120, 최대 1,440)

Response: `200 OK`

```json
{
  "items": [
    {
      "elapsedSeconds": 900,
      "hourlyGpuPriceUsd": "0.6900",
      "estimatedGpuCostUsd": "0.1725",
      "estimatedTotalCostUsd": "0.1725",
      "observedAt": "2026-08-25T12:20:00Z"
    }
  ]
}
```

### `GET /jobs/{jobId}/events`

사용자 타임라인용 Event를 오래된 순서로 반환한다.

Query: `after`, `limit`(기본 50, 최대 200)

Response: `200 OK`

```json
{
  "items": [
    {
      "id": "event_uuid",
      "eventType": "RESOURCE_PROVISIONED",
      "message": "실행 환경 준비를 시작했습니다.",
      "occurredAt": "2026-08-25T12:06:00Z"
    }
  ]
}
```

일반 사용자 이벤트에는 API 키, Runpod Pod ID, Provider 오류 원문을 포함하지 않는다.

## 7. 취소·재계획·결과물

### `POST /jobs/{jobId}/cancel`

활성 Attempt를 취소한다. 허용 상태는 `PROVISIONING`, `PREPARING`, `RUNNING`, `FINALIZING`이다.

Response: `202 Accepted`

```json
{
  "jobId": "job_uuid",
  "status": "FINALIZING",
  "stopReason": "USER_CANCELLED"
}
```

Training 중단, 로그·부분 artifact 보존, VM 종료와 종료 확인은 비동기로 계속된다. 종료 확인 후에만 Job은 `CANCELLED`가 된다.

### `POST /jobs/{jobId}/replans`

OOM 또는 Plan 만료 후 새 Plan을 만든다. 기존 실행 계약·Attempt의 입력은 변경하지 않으며, 새 Plan은 반드시 다시 승인해야 한다.

Request:

```json
{ "reason": "OOM" }
```

허용 `reason`: `OOM`, `PLAN_SUPERSEDED`.

Response: `202 Accepted` — 분석·Plan 생성을 시작하며 Job은 `ANALYZING`이 된다.

### `GET /jobs/{jobId}/artifacts`

Job의 artifact 목록을 반환한다.

```json
{
  "items": [
    {
      "id": "artifact_uuid",
      "artifactType": "OUTPUT",
      "byteSize": 1240000,
      "status": "AVAILABLE",
      "downloadExpiresAt": "2026-08-26T12:30:00Z"
    }
  ]
}
```

### `POST /jobs/{jobId}/artifacts/{artifactId}/download-url`

사용 가능한 artifact의 짧은 수명 서명 다운로드 URL을 발급한다.

Response: `200 OK`

```json
{
  "downloadUrl": "https://storage.example/...",
  "expiresAt": "2026-08-25T12:35:00Z"
}
```

artifact의 `downloadExpiresAt`이 지났거나 `DELETED`이면 `410 Gone`과 `ARTIFACT_EXPIRED`를 반환한다.

## 8. 서버 처리 규칙

- 비용 Snapshot은 1분마다, 그리고 상태가 바뀔 때 기록한다.
- 비용이 예산의 80%에 도달하면 경고 Event를 한 번 남긴다.
- 비용이 90% 이상이거나 최대 실행시간에 도달하면 Training 중단, checkpoint 보관 시도, VM 종료를 시작한다.
- 모든 성공·실패·취소·예산 중단 경로는 `FINALIZING`을 거쳐 종료를 확인한다.
- VM 종료 요청은 멱등적이며, Provider timeout 때는 새 VM을 만들기 전에 기존 Resource를 조회·조정한다.
- 5분 동안 종료 요청과 상태 조회를 재시도한다. 확인이 계속 안 되면 `CLEANUP_ATTENTION_REQUIRED`로 전환한다.
- Credential 원문은 Job 종료 처리 뒤 폐기한다. artifact 원본은 업로드 뒤 24시간에 삭제한다.
