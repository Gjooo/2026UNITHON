# UNWORK 학습 실행 Agent — API 명세

[PRD-final.md](PRD-final.md)의 제품 기능 전체를 담는 REST API다. 사용자는 학습 Repository·실행 명령·예산·완료 조건을 제공하고, Agent는 코드 분석부터 실행안 비교, 환경 준비, 학습 감시, 결과 전달, 자원 종료 확인까지 하나의 `TrainingJob`으로 수행한다.

> **데모 운영**은 이 API를 좁히지 않는다. 화면과 계약은 제품 전체를 그대로 노출하고, 데모에서는 [11. 데모 골든 패스](#11-데모-골든-패스)의 값으로 진행하도록 진행자가 안내한다.

## 1. 공통 규약

- Base URL: `/api/v1`
- Content-Type: `application/json`
- 모든 ID: 문자열 (`job_`, `plan_`, `dec_`, `art_` 접두사)
- 모든 시간: ISO 8601 UTC
- 모든 금액: 원(KRW) 정수
- 인증: HttpOnly·Secure·SameSite=Lax 세션 쿠키. 모든 요청은 `credentials: 'include'`.
- Provider API 키는 서버 Secret Vault에서만 읽는다. 응답·로그·클라이언트 어디에도 노출하지 않는다.
- 응답에 Provider resource ID, VM/Pod ID, 이미지 태그, callback URL을 포함하지 않는다. 사용자에게 보이는 환경 정보는 프레임워크·CUDA·Python 버전까지다.

### 공통 오류 응답

```json
{
  "error": {
    "code": "NO_ELIGIBLE_PLAN",
    "message": "이 예산 안에서 실행할 수 있는 GPU 후보가 없습니다.",
    "details": { "minimumRequiredBudgetKrw": 7300 }
  }
}
```

| HTTP | 코드 | 의미 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 요청 형식 오류 |
| 401 | `SESSION_REQUIRED`, `SESSION_EXPIRED` | 세션 쿠키 없음 또는 만료 |
| 404 | `JOB_NOT_FOUND`, `ARTIFACT_NOT_FOUND` | 없거나 현재 세션 소유가 아님 |
| 409 | `INVALID_JOB_STATE` | 현재 상태에서 할 수 없는 행동 |
| 409 | `PLAN_EXPIRED` | 승인 직전 재검증에서 가격·가용성이 바뀜 |
| 409 | `NO_PROVIDER_CONNECTED` | 연결된 공급자가 없음 |
| 409 | `DECISION_ALREADY_RESOLVED` | 이미 처리된 판단 요청 |
| 409 | `EXECUTION_LIMIT_REACHED` | 이 세션의 실행 허용 횟수 소진 |
| 409 | `CONCURRENT_EXECUTION_LIMIT` | 동시 실행 상한 도달. 대기열은 제공하지 않음 |
| 422 | `ANALYSIS_FAILED` | Repository·실행 명령을 분석하지 못함 |
| 422 | `NO_ELIGIBLE_PLAN` | 예산 안에서 실행 가능한 후보 없음 |
| 503 | `PROVIDER_UNAVAILABLE` | 공급자 조회·생성·상태 확인 실패 |

## 2. 세션

### `POST /session`

익명 세션을 만들거나 갱신한다. DB에는 토큰 해시만 저장한다.

Response: `201 Created`

```json
{
  "expiresAt": "2026-09-02T12:00:00Z",
  "executionAllowance": { "used": 0, "limit": 1 }
}
```

`executionAllowance`는 이 세션이 실제 비용을 발생시킬 수 있는 남은 횟수다. 운영 정책 값이며 제품 기능이 아니다.

## 3. 공급자 연결

### `GET /providers`

Response: `200 OK`

```json
{
  "providers": [
    {
      "id": "runpod",
      "name": "Runpod",
      "connectionStatus": "CONNECTED",
      "connectedAt": "2026-08-20T09:12:00Z",
      "availableGpuTypes": 14
    },
    {
      "id": "vastai",
      "name": "Vast.ai",
      "connectionStatus": "NOT_CONNECTED",
      "connectedAt": null,
      "availableGpuTypes": 0
    }
  ]
}
```

`connectionStatus`: `CONNECTED`, `NOT_CONNECTED`, `INVALID_CREDENTIAL`, `UNREACHABLE`.

### `POST /providers/{providerId}/credential`

공급자 계정을 연결한다. 서버는 값을 즉시 Secret Vault에 저장하고 다시 반환하지 않는다.

Request:

```json
{ "apiKey": "..." }
```

Response: `204 No Content`

### `DELETE /providers/{providerId}/credential`

연결을 해제하고 저장된 비밀값을 폐기한다. Response: `204 No Content`

## 4. 학습 작업 생성

### `POST /jobs`

사용자가 제공하는 값은 학습 Repository, 실행 명령, 예산, 완료 조건뿐이다. GPU 종류·Region·CUDA 버전·VM 옵션은 요청에 없다.

```json
{
  "repositoryUrl": "https://github.com/example/sd15-lora",
  "revision": "main",
  "executionCommand": "python train_lora.py --config configs/demo.yaml",
  "completionCriteria": {
    "type": "PROCESS_EXIT",
    "maxSteps": null,
    "metricName": null,
    "targetValue": null
  },
  "maxBudgetKrw": 10000,
  "maxRuntimeMinutes": 60
}
```

| 필드 | 규칙 |
| --- | --- |
| `repositoryUrl` | 공개 접근 가능한 Git URL. |
| `revision` | branch, tag, 또는 commit SHA. 생략하면 기본 branch. |
| `executionCommand` | Repository 루트에서 실행할 단일 명령. |
| `completionCriteria.type` | `PROCESS_EXIT`, `MAX_STEPS`, `TARGET_METRIC`. |
| `maxBudgetKrw` | 0보다 큰 정수. 실행안 비교와 자동 중단의 기준이다. |
| `maxRuntimeMinutes` | 0보다 큰 정수. 초과하면 Agent가 학습을 중단한다. |

Response: `202 Accepted` — `TrainingJob` (`status: ANALYZING`)

Agent는 Repository를 읽어 프레임워크·의존성·필요 VRAM·기준 실행시간을 도출한 뒤, 연결된 공급자들의 GPU 후보를 비교해 실행안 3개를 만든다. 이 단계에서는 비용이 발생하지 않는다.

## 5. TrainingJob

```json
{
  "id": "job_5f2c",
  "status": "PLAN_READY",
  "workload": {
    "repositoryUrl": "https://github.com/example/sd15-lora",
    "revision": "main",
    "commitSha": "9c1d4ab",
    "executionCommand": "python train_lora.py --config configs/demo.yaml",
    "completionCriteria": { "type": "PROCESS_EXIT", "maxSteps": null, "metricName": null, "targetValue": null }
  },
  "constraint": { "maxBudgetKrw": 10000, "maxRuntimeMinutes": 60 },
  "analysis": {
    "status": "READY",
    "confidence": "MEDIUM",
    "framework": "PyTorch",
    "frameworkVersion": "2.3.0",
    "cudaVersion": "12.1",
    "pythonVersion": "3.10",
    "requiredVramGb": 24,
    "estimatedBaseMinutes": 45,
    "detectedDependencies": ["diffusers==0.27.2", "peft==0.10.0", "accelerate==0.29.3"],
    "notes": ["requirements.txt에서 CUDA 12.1과 호환되는 버전을 확인했습니다."],
    "unknowns": ["데이터셋 크기를 코드에서 확인하지 못해 기본값으로 추정했습니다."]
  },
  "plans": [],
  "approvedPlanId": null,
  "contract": null,
  "execution": null,
  "pendingDecision": null,
  "result": null,
  "createdAt": "2026-08-26T03:10:00Z",
  "updatedAt": "2026-08-26T03:10:42Z"
}
```

`analysis.unknowns`는 Agent가 확신하지 못한 요구사항이다. 화면은 이를 숨기지 않는다.

### ExecutionPlan

`plans`에는 `CHEAPEST`, `FASTEST`, `BALANCED` 세 실행안이 항상 이 순서로 들어간다. 예산을 넘는 안도 비교 근거로 남기되 `budget.withinBudget: false`로 표시하고 승인할 수 없다.

```json
{
  "id": "plan_cheapest",
  "kind": "CHEAPEST",
  "label": "가장 저렴함",
  "provider": { "id": "runpod", "name": "Runpod" },
  "gpu": { "name": "NVIDIA RTX 4090", "vramGb": 24, "count": 1 },
  "estimatedRuntimeMinutes": 52,
  "cost": {
    "gpuCostKrw": 4200,
    "agentFeeKrw": 630,
    "storageAndTransferKrw": 120,
    "estimatedTotalKrw": 4950,
    "priceDataType": "SNAPSHOT",
    "pricedAt": "2026-08-26T03:10:40Z"
  },
  "budget": { "withinBudget": true, "shortfallKrw": null },
  "risk": {
    "level": "MEDIUM",
    "reasons": ["커뮤니티 클라우드 인스턴스라 다른 사용자에게 회수될 수 있습니다."]
  },
  "alternatives": [
    {
      "provider": { "id": "runpod", "name": "Runpod" },
      "gpu": { "name": "NVIDIA A100 40GB", "vramGb": 40, "count": 1 },
      "estimatedRuntimeMinutes": 31,
      "estimatedTotalKrw": 7180,
      "reason": "선택 GPU가 중단되면 이 후보로 재계획을 제안합니다."
    }
  ],
  "environment": {
    "frameworkVersion": "PyTorch 2.3.0",
    "cudaVersion": "12.1",
    "pythonVersion": "3.10",
    "verified": true
  },
  "reason": "예산 안 후보 중 예상 총비용이 가장 낮습니다.",
  "recommended": true
}
```

- `cost.estimatedTotalKrw`는 GPU 사용료·저장소/전송비·Agent 실행 수수료의 합이다. 시간당 단가가 아니라 **작업 완료 비용**으로 비교한다.
- `risk`는 비용에 섞지 않고 따로 표시한다. `level`: `LOW`, `MEDIUM`, `HIGH`.
- `priceDataType`: `LIVE`(조회 시점 실시간) 또는 `SNAPSHOT`(검증된 스냅샷).
- `recommended`는 사용자의 제약에 대해 Agent가 먼저 제시하는 안이다. 세 안 모두 승인 가능하다.

### 상태

```text
ANALYZING → PLAN_READY → PROVISIONING → PREPARING → RUNNING → TERMINATING → COMPLETED
    ↓                         ↓             ↓          ↓  ↑                 ↘ FAILED
ANALYSIS_FAILED               ↘─────────────┴──────────┘  │                 ↘ CANCELLED
                                                RUNNING ⇄ AWAITING_DECISION ↘ BUDGET_STOPPED
```

| 상태 | 의미 |
| --- | --- |
| `ANALYZING` | Repository와 실행 요구사항을 분석하고 후보를 비교하는 중. 비용 없음 |
| `ANALYSIS_FAILED` | 코드·명령을 분석하지 못해 실행안을 만들 수 없음 |
| `PLAN_READY` | 실행안 3개가 준비되고 승인을 기다리는 중. 비용 없음 |
| `PROVISIONING` | 승인된 실행안의 GPU 환경을 생성하는 중 |
| `PREPARING` | Repository 배포, 의존성·모델·데이터 준비 중 |
| `RUNNING` | 학습 실행 중 |
| `AWAITING_DECISION` | 재계획 또는 계속 투자 여부에 사용자 판단이 필요한 상태 |
| `TERMINATING` | 종료 처리와 자원 회수 확인 중 |
| `COMPLETED` | 완료 조건 충족, 결과 보관, 자원 종료 확인이 모두 끝남 |
| `FAILED` | 실패로 종료 처리가 끝남 |
| `CANCELLED` | 사용자 중단으로 종료 처리가 끝남 |
| `BUDGET_STOPPED` | 예산 또는 최대 실행시간 상한에 도달해 Agent가 중단함 |

`TERMINATING` 동안에는 최종 결과를 표시하지 않는다. 자원 종료 확인이 끝난 뒤에만 최종 상태로 바꾼다.

## 6. 조회

### `GET /jobs/{jobId}`

현재 세션이 소유한 Job을 반환한다. 다른 세션의 Job은 `404 JOB_NOT_FOUND`다.

Response: `200 OK` — `TrainingJob`

폴링 간격 권장: `ANALYZING` 2초, `PROVISIONING`/`PREPARING`/`RUNNING`/`TERMINATING` 3초, 최종 상태에서는 중단.

### `GET /jobs`

Response: `200 OK` — `{ "jobs": [TrainingJobSummary] }`

## 7. 실행 계약 승인

### `POST /jobs/{jobId}/approve`

```json
{ "planId": "plan_balanced" }
```

처리 규칙:

1. Job은 `PLAN_READY`여야 한다.
2. 서버는 승인 직전 선택 실행안의 가격·가용성을 재검증한다. 달라졌으면 `409 PLAN_EXPIRED`와 함께 갱신된 실행안을 `details.plans`로 돌려주고 Job은 `PLAN_READY`로 남긴다.
3. 통과하면 `contract`를 고정하고 환경 생성을 시작한다.

Response: `202 Accepted`

```json
{ "id": "job_5f2c", "status": "PROVISIONING", "contract": { "...": "..." } }
```

### Contract

승인 시점에 고정되어 변경되지 않는다. GPU·비용·시간이 달라지는 변경은 새 계약으로 다시 승인받는다.

```json
{
  "approvedAt": "2026-08-26T03:12:05Z",
  "planId": "plan_balanced",
  "planSnapshot": { "...": "ExecutionPlan 전문" },
  "commitSha": "9c1d4ab",
  "executionCommand": "python train_lora.py --config configs/demo.yaml",
  "completionCriteria": { "type": "PROCESS_EXIT" },
  "autoStop": {
    "budgetKrw": 10000,
    "runtimeMinutes": 60,
    "noProgressMinutes": 15
  }
}
```

## 8. 실행 감시와 중단

`PROVISIONING` 이후의 `execution`:

```json
{
  "phase": "TRAINING",
  "startedAt": "2026-08-26T03:12:40Z",
  "elapsedMinutes": 18,
  "steps": [
    { "name": "환경 생성", "status": "DONE", "startedAt": "...", "finishedAt": "..." },
    { "name": "코드·의존성 준비", "status": "DONE", "startedAt": "...", "finishedAt": "..." },
    { "name": "학습 실행", "status": "ACTIVE", "startedAt": "...", "finishedAt": null },
    { "name": "결과 보관·자원 종료", "status": "PENDING", "startedAt": null, "finishedAt": null }
  ],
  "cost": { "accruedKrw": 1820, "dataType": "ESTIMATED", "budgetUsedPercent": 18 },
  "progress": { "currentStep": 320, "totalSteps": 1000, "lastMetric": { "name": "loss", "value": 0.41 } },
  "lastCheckpointAt": "2026-08-26T03:28:10Z",
  "logTail": ["step 320/1000 loss=0.41", "saved checkpoint step-300"]
}
```

- `cost.dataType`: `METERED`(공급자 계측) 또는 `ESTIMATED`(계약 단가 기반 추정).
- `logTail`은 최근 몇 줄만 담는 폴링 값이다. 실시간 스트림이 아니다.
- `progress`는 알 수 없으면 `null`이다. 화면은 없는 값을 추정하지 않는다.

### `POST /jobs/{jobId}/cancel`

`PROVISIONING`, `PREPARING`, `RUNNING`, `AWAITING_DECISION`에서 호출한다.

Response: `202 Accepted` — `{ "id": "job_5f2c", "status": "TERMINATING" }`

서버는 학습 중단, checkpoint 보존, 자원 삭제를 요청하고 종료를 확인한 뒤 `CANCELLED`로 바꾼다.

## 9. 판단 요청

예산·시간·GPU가 바뀌는 재계획, 추가 투자 여부처럼 사람의 판단이 필요할 때 Job은 `AWAITING_DECISION`이 되고 `pendingDecision`이 채워진다. 정상 경로에서는 나타나지 않는다.

```json
{
  "id": "dec_1",
  "type": "REPLAN",
  "raisedAt": "2026-08-26T03:31:00Z",
  "reason": "선택한 GPU가 회수돼 남은 학습을 이어갈 수 없습니다.",
  "current": { "gpu": "NVIDIA RTX 4090", "spentKrw": 2100, "completedPercent": 42 },
  "proposed": { "...": "ExecutionPlan 전문" },
  "delta": { "additionalCostKrw": 3400, "additionalMinutes": 26, "gpuChanged": true, "resumesFromCheckpoint": true },
  "expiresAt": "2026-08-26T03:46:00Z"
}
```

`type`: `REPLAN`(다른 GPU로 이어감), `CONTINUE_INVESTMENT`(예상보다 오래 걸려 추가 비용 필요), `BUDGET_EXCEEDED`(상한 도달).

### `POST /jobs/{jobId}/decisions/{decisionId}`

```json
{ "outcome": "APPROVE" }
```

`outcome`: `APPROVE`(제안대로 계속) 또는 `STOP`(여기서 종료).

Response: `202 Accepted` — `{ "id": "job_5f2c", "status": "PROVISIONING" }` 또는 `{ "status": "TERMINATING" }`

`expiresAt`이 지나면 서버가 `STOP`으로 처리한다. 만료된 판단 요청에 응답하면 `409 DECISION_ALREADY_RESOLVED`다.

## 10. 결과

최종 상태의 `result`:

```json
{
  "outcome": "SUCCEEDED",
  "finishedAt": "2026-08-26T04:02:11Z",
  "runtimeMinutes": 49,
  "exitCode": 0,
  "completionLog": "Training completed. 1000/1000 steps.",
  "failureMessage": null,
  "cost": { "estimatedTotalKrw": 4950, "actualTotalKrw": 5120, "dataType": "METERED" },
  "artifacts": [
    { "id": "art_1", "name": "lora_weights.safetensors", "kind": "MODEL", "sizeBytes": 145000000, "createdAt": "..." },
    { "id": "art_2", "name": "training.log", "kind": "LOG", "sizeBytes": 82000, "createdAt": "..." }
  ],
  "checkpoints": [{ "id": "ckpt_3", "step": 900, "createdAt": "..." }],
  "resourceTeardown": { "status": "CONFIRMED", "confirmedAt": "2026-08-26T04:02:40Z", "message": null }
}
```

- `outcome`: `SUCCEEDED`, `FAILED`, `CANCELLED`, `BUDGET_STOPPED`.
- `cost.actualTotalKrw`는 계측값이 없으면 `null`이다. 화면은 추정값을 실제 비용으로 표시하지 않는다.
- `resourceTeardown.status`: `PENDING`, `CONFIRMED`, `UNCONFIRMED`. `UNCONFIRMED`는 실패가 아니라 확인되지 않은 상태로 따로 표시한다.
- `failureMessage`는 사용자에게 안전한 짧은 문구다. stack trace, 자격 증명, Provider resource ID를 담지 않는다.

### `GET /jobs/{jobId}/artifacts/{artifactId}`

Response: `302 Found` — 만료되는 서명 URL로 redirect. URL은 세션 소유자에게만 발급한다.

## 11. 데모 골든 패스

제품 API와 화면은 좁히지 않는다. 데모에서는 진행자가 아래 값으로 입력하도록 안내하고, 서버는 운영 안전장치만 적용한다.

| 입력 | 데모 값 |
| --- | --- |
| `repositoryUrl` | 사전 검증된 SD 1.5 LoRA repository |
| `revision` | 고정 commit SHA |
| `executionCommand` | 사전 검증된 학습 명령 |
| `completionCriteria` | `PROCESS_EXIT` |
| `maxBudgetKrw` | 실행안 3개가 모두 비교되도록 정한 값 |
| `maxRuntimeMinutes` | 10 |

서버 측 운영 안전장치(제품 기능이 아니라 배포 설정):

1. 세션당 실제 비용이 발생하는 실행은 1회 (`EXECUTION_LIMIT_REACHED`).
2. 서비스 전체 동시 실행 1개, 대기열 없음 (`CONCURRENT_EXECUTION_LIMIT`).
3. 실행 가능한 Repository allowlist. 벗어나면 `ANALYSIS_FAILED`.
4. `maxRuntimeMinutes` 상한 강제.

이 네 가지는 API 계약이 아니라 배포 정책이다. 프런트엔드는 해당 오류 코드를 다음 행동과 함께 안내하기만 한다.
