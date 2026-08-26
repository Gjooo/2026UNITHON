# UNWORK 학습 실행 Agent — 최소 MVP API 명세

`MVP-implementation-plan.md`와 `ERD.md`를 기준으로 한 제한된 GPU 선택·실행 데모용 REST API다. 사용자는 예산과 우선순위만 제시하고, Agent가 사전 검증한 GPU 실행 프로필을 비교해 하나를 추천한다. API의 중심 리소스는 추천 실행 계약을 포함한 `TrainingJob`이다.

## 1. 공통 규약

- Base URL: `/api/v1`
- Content-Type: `application/json`
- 모든 ID: UUID 문자열
- 모든 시간: ISO 8601 UTC
- MVP 실행 Provider: 팀 Runpod 계정
- 웹 사용자는 로그인 없이 익명 세션으로 Job을 분리한다.
- 팀 Runpod API 키는 서버 환경변수 또는 Secret Vault에서만 읽는다. 클라이언트·DB·응답에는 노출하지 않는다.
- 서버는 데모 전에 검증한 2~3개 GPU 실행 프로필만 비교한다. 프로필의 GPU type ID, 이미지, 실행 명령은 서버 상수다.
- 사용자에게 전달되는 `message`, `failureMessage`, `reason`에는 데모 단계 표현(데모, MVP)과 인프라 용어(Pod, provisioning)를 쓰지 않는다. 오류 `code`와 `priceDataType` 같은 기계 판독 값은 예외이며 화면에 그대로 출력하지 않는다.

### 익명 세션

### `POST /session`

익명 세션을 만들거나 갱신한다. 서버는 임의 토큰을 `HttpOnly`, `Secure`, `SameSite=Lax` 쿠키로 설정하고 DB에는 토큰 해시만 저장한다. 세션은 7일 동안 유효하다.

Request body: 없음

Response: `201 Created`

```json
{
  "expiresAt": "2026-09-01T12:00:00Z",
  "executionAllowance": { "used": 0, "limit": 1 },
  "realExecutionAvailable": true
}
```

`executionAllowance`는 이 세션이 실제 비용을 발생시킬 수 있는 횟수와 이미 사용한 횟수다. **시뮬레이션 실행은 이 횟수를 쓰지 않는다.** 화면은 실행 버튼을 누르기 전에 남은 횟수를 안내할 수 있다. 운영 정책 값이며 제품 기능이 아니다.

`realExecutionAvailable`은 이 배포에서 실제 GPU 실행을 고를 수 있는지를 뜻한다. `false`면 화면은 실제 실행 선택지를 감춘다. Runpod 자격증명이 없는 배포에서 실제 실행을 요청하면 `409 REAL_EXECUTION_UNAVAILABLE`이다.

### 공통 오류 응답

```json
{
  "error": {
    "code": "NO_ELIGIBLE_PLAN",
    "message": "입력한 예산 안에서 실행할 수 있는 GPU 후보가 없습니다."
  }
}
```

| HTTP | 코드 | 의미 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 요청 형식 오류 |
| 401 | `SESSION_REQUIRED`, `SESSION_EXPIRED` | 세션 쿠키 없음 또는 만료 |
| 404 | `JOB_NOT_FOUND` | Job이 없거나 현재 세션의 Job이 아님 |
| 409 | `INVALID_JOB_STATE`, `DEMO_BUSY`, `EXECUTION_ALREADY_USED` | 현재 상태에서 실행·취소할 수 없거나 실행 제한에 도달. `DEMO_BUSY`와 `EXECUTION_ALREADY_USED`는 실제 실행에만 적용된다 |
| 409 | `REAL_EXECUTION_UNAVAILABLE` | 이 배포에서 실제 GPU 실행을 쓸 수 없음 |
| 409 | `PROVIDER_NOT_CONNECTED` | 실제 실행인데 연결된 공급자 키가 없음 |
| 401 | `INVALID_PROVIDER_CREDENTIAL` | 입력한 키로 공급자에 연결할 수 없음 |
| 503 | `PROVIDER_UNAVAILABLE` | 공급자 응답이 없어 키를 확인할 수 없음 |
| 422 | `NO_ELIGIBLE_PLAN` | 최대 예산 안의 데모 GPU 후보가 없음 |
| 503 | `RUNPOD_UNAVAILABLE` | Pod 생성 또는 상태 확인 실패 |

## 1-2. 공급자 연결 (BYOK)

실제 GPU 실행은 **사용자가 연결한 Runpod 키**로만 한다. 팀 키로 대신 실행하지 않는다. 화면이 "당신의 계정에서 실행됩니다"라고 말한다면 그것이 사실이어야 하기 때문이다.

시뮬레이터 실행에는 키가 필요 없다. 후보 비교(`POST /jobs`)도 고정 프로필 비교라 키 없이 된다. 비용이 없는 탐색을 막을 이유가 없다.

### `POST /providers/{providerId}/credential`

```json
{ "apiKey": "..." }
```

Response: `204 No Content`

처리 규칙:

1. 받은 즉시 Runpod 읽기 API를 한 번 호출해 **키가 실제로 통하는지 확인한다.** 형식 검사만으로는 부족하다. 승인 뒤 Pod 생성 단계에서 실패하면 사용자는 이미 비용이 발생했다고 믿는 상태다.
2. 유효하면 현재 익명 세션에 묶어 **메모리에만** 보관한다. 디스크에 쓰지 않는다.
3. 응답 본문은 비어 있다. 키는 마스킹한 형태로도 반환하지 않는다.
4. 유효하지 않으면 `401 INVALID_PROVIDER_CREDENTIAL`. 공급자 장애로 확인 자체가 안 되면 `503 PROVIDER_UNAVAILABLE`.

프로세스가 재시작되면 연결이 풀린다. 사용자는 다시 입력해야 한다. 남의 키를 볼륨에 평문으로 남기지 않기 위한 선택이다.

### `GET /providers`

현재 세션의 연결 상태만 반환한다.

```json
{
  "providers": [
    { "id": "runpod", "name": "Runpod", "connectionStatus": "CONNECTED", "connectedAt": "2026-08-26T05:10:00Z" }
  ]
}
```

`connectionStatus`: `CONNECTED` 또는 `NOT_CONNECTED`.

### `DELETE /providers/{providerId}/credential`

연결을 끊고 보관 중인 키를 폐기한다. Response: `204 No Content`

## 2. 핵심 리소스

### 제약 입력

`POST /jobs`는 아래 제약만 받는다. 학습 코드·GPU·Provider는 사용자 입력이 아니다.

```json
{
  "maxBudgetKrw": 10000,
  "priority": "CHEAPEST",
  "executionMode": "SIMULATED"
}
```

| 필드 | 규칙 |
| --- | --- |
| `maxBudgetKrw` | 0보다 큰 정수. 추천 단계의 **예상 GPU 비용** 상한이며, 실제 청구액을 제한하지 않는다. |
| `priority` | `CHEAPEST`, `BALANCED`, `FASTEST` 중 하나. 각각 저비용·균형·빠른 완료를 뜻한다. |
| `executionMode` | `SIMULATED`(기본) 또는 `REAL`. 생략하면 비용이 발생하지 않는 시뮬레이터로 실행한다. |

`executionMode`는 제품 기능이 아니라 시연 제어값이다. `SIMULATED`는 실제 GPU를 만들지 않고 같은 상태 전이를 재현하므로 비용이 없다. `REAL`은 Runpod GPU를 실제로 만들고 과금된다. 승인 이후에는 바꿀 수 없으며 Job 응답의 `executionMode`로 확인한다.

### TrainingJob

```json
{
  "id": "job_uuid",
  "scenario": {
    "name": "Stable Diffusion 1.5 LoRA",
    "repositoryUrl": "https://github.com/example/golden-path",
    "executionCommand": "./run-demo-training.sh",
    "requiredVramGb": 24,
    "maxRuntimeMinutes": 10
  },
  "constraint": {
    "maxBudgetKrw": 10000,
    "priority": "CHEAPEST"
  },
  "executionMode": "SIMULATED",
  "executionPlan": {
    "priceDataType": "DEMO_SNAPSHOT",
    "estimateDisclaimer": "예상 시간과 GPU 비용은 사전 검증한 실행 프로필 기준 추정치이며 실제 청구액을 보장하지 않습니다.",
    "candidates": [
      {
        "profileId": "runpod-rtx4090-v1",
        "provider": "Runpod",
        "gpuType": "NVIDIA RTX 4090",
        "estimatedRuntimeMinutes": 9,
        "estimatedGpuCostKrw": 450,
        "eligibility": "ELIGIBLE"
      },
      {
        "profileId": "runpod-a100-v1",
        "provider": "Runpod",
        "gpuType": "NVIDIA A100 40GB",
        "estimatedRuntimeMinutes": 6,
        "estimatedGpuCostKrw": 780,
        "eligibility": "ELIGIBLE"
      }
    ],
    "recommended": {
      "profileId": "runpod-rtx4090-v1",
      "provider": "Runpod",
      "gpuType": "NVIDIA RTX 4090",
      "estimatedRuntimeMinutes": 9,
      "estimatedGpuCostKrw": 450,
      "reason": "예산 안 후보 중 예상 GPU 비용이 가장 낮습니다."
    }
  },
  "status": "DRAFT",
  "failureMessage": null,
  "exitCode": null,
  "completionLog": null,
  "startedAt": null,
  "finishedAt": null,
  "podTerminatedAt": null
}
```

- `scenario`은 고정 workload를 설명하는 읽기 전용 값이다.
- `executionPlan`은 Job 생성 시 계산한 스냅샷이며, 사용자 요청으로 GPU를 바꿀 수 없다.
- `candidates`에는 VRAM 조건을 만족한 데모 프로필을 모두 표시한다. 예산을 넘는 후보는 `eligibility: OVER_BUDGET`으로 보이지만 추천되지 않는다.
- `priceDataType: DEMO_SNAPSHOT`은 이 값이 실시간 가격이나 실제 청구액이 아님을 뜻한다.

### 추천 정책

예산 안의 후보만 대상으로 아래의 결정적 정책을 적용한다. 동점이면 예상 GPU 비용, 예상 실행시간, `profileId` 순으로 정렬한다.

| `priority` | 선택 정책 |
| --- | --- |
| `CHEAPEST` | 예상 GPU 비용이 가장 낮은 후보 |
| `FASTEST` | 예상 실행시간이 가장 짧은 후보 |
| `BALANCED` | `0.5 × (후보 비용 / 최저 비용) + 0.5 × (후보 시간 / 최단 시간)` 점수가 가장 낮은 후보 |

실행 전에는 추천 결과를 다시 계산하거나 가격을 갱신하지 않는다. 실행 계약은 Job 생성 시점의 추천 스냅샷으로 고정한다.

### Job 상태

`DRAFT → PROVISIONING → RUNNING → TERMINATING → COMPLETED | FAILED | CANCELLED`

`COMPLETED`는 학습 성공 callback, 종료 코드 `0`, Pod 종료 확인이 모두 끝났을 때만 표시한다.

## 3. Job 생성·조회·실행

### `POST /jobs`

최대 예산·우선순위를 받아 GPU 후보를 비교하고, Agent 추천 실행 계약이 담긴 Draft Job을 만든다. Pod를 만들지 않으며 비용도 발생하지 않는다.

Request body: [제약 입력](#제약-입력)

Response: `201 Created` — `TrainingJob` (`status: DRAFT`)

처리 규칙:

1. 서버는 고정 workload의 필요 VRAM을 기준으로 GPU 프로필을 필터한다.
2. 각 후보의 예상 실행시간·예상 GPU 비용을 계산한다.
3. `estimatedGpuCostKrw <= maxBudgetKrw` 후보가 없으면 `422 NO_ELIGIBLE_PLAN`을 반환하고 Job을 만들지 않는다.
4. 추천 정책으로 하나를 선택하고, 후보 비교 결과와 선택 근거를 `selection_snapshot`에 저장한다.

### `GET /jobs/{jobId}`

현재 세션이 소유한 Job의 실행 계약과 상태를 반환한다. 프런트엔드는 실행 중일 때 2~3초 간격으로 이 API를 폴링한다.

Response: `200 OK` — `TrainingJob`

### `POST /jobs/{jobId}/start`

Agent가 추천한 고정 실행 계약을 승인하고 실제 Pod 생성을 시작한다.

Request body: 없음

Response: `202 Accepted`

```json
{
  "id": "job_uuid",
  "status": "PROVISIONING"
}
```

처리 규칙:

1. Job은 `DRAFT`여야 한다.
2. `executionMode`가 `REAL`이면 이 세션에 연결된 공급자 키가 있어야 한다. 없으면 `409 PROVIDER_NOT_CONNECTED`이며, 팀 키로 대신 실행하지 않는다.
3. **아래 3~4번은 `REAL`에만 적용된다.** 시뮬레이션은 자원을 만들지 않으므로 횟수 제한도 동시 실행 제한도 없다. 같은 사람이 여러 번, 여러 사람이 동시에 실행할 수 있다.
4. 세션의 `execution_used`가 `false`여야 한다. Pod 생성을 시작하면 `true`로 변경한다.
5. 서비스 전체에 진행 중인 **실제 실행**이 있으면 `409 DEMO_BUSY`를 반환한다. 대기열은 제공하지 않는다.
6. 서버는 Job의 추천 프로필에 고정된 Runpod GPU type ID·이미지·실행 명령·최대 실행시간 설정으로 Pod를 생성한다. 실제 실행이면 그 사용자가 연결한 키로 만든다.

### `POST /jobs/{jobId}/cancel`

`PROVISIONING` 또는 `RUNNING` Job을 중단한다.

Response: `202 Accepted`

```json
{
  "id": "job_uuid",
  "status": "TERMINATING"
}
```

서버는 학습 중단과 Pod 삭제를 요청하고, Runpod에서 종료를 확인한 뒤 `CANCELLED`로 변경한다.

## 4. 내부 학습 callback

### `POST /internal/jobs/{jobId}/completion`

사전 검증된 학습 컨테이너가 종료 직전에 호출하는 내부 endpoint다. 공개 사용자 UI에서 호출하지 않는다.

Request:

```json
{
  "outcome": "SUCCEEDED",
  "exitCode": 0,
  "message": "Training completed"
}
```

| 필드 | 규칙 |
| --- | --- |
| `outcome` | `SUCCEEDED` 또는 `FAILED` |
| `exitCode` | 학습 프로세스 종료 코드 |
| `message` | 완료 화면에 표시할 짧은 메시지 |

Response: `204 No Content`

처리 규칙:

- `outcome: SUCCEEDED`와 `exitCode: 0`이면 Job의 성공 결과를 기록하고 `TERMINATING`으로 전환한다.
- 그 외에는 실패 원인을 기록하고 `TERMINATING`으로 전환한다.
- callback이 오지 않은 채 10분 timeout이 지나면 서버가 `FAILED`로 기록하고 Pod 종료를 시작한다.

## 5. 서버 실행 규칙

1. 백엔드의 장시간 실행 프로세스가 Pod 생성, 상태 확인, timeout, 종료 처리를 소유한다. 브라우저를 닫아도 실행 처리는 계속된다.
2. 학습 컨테이너는 Job의 추천 프로필에 고정된 이미지와 명령으로 실행된다. 최대 10분 timeout을 넘기면 학습을 중단한다.
3. 성공, 실패, 취소, timeout의 모든 경로에서 Pod 삭제를 요청하고 Runpod 상태 조회로 종료를 확인한다.
4. Pod 생성 실패, 학습 오류, timeout은 재시도 없이 `FAILED`와 짧은 원인 메시지로 표시한다.
5. 성공 화면에는 `Training completed` 로그, 종료 코드, 실행 시간, Agent가 선택한 GPU 정보, Pod 자동 종료 완료를 표시한다.
6. MVP는 임의 코드 실행, BYOK, 다중 Provider 비교, 실시간 가격·비용 계측, artifact, OOM 재계획을 제공하지 않는다.
