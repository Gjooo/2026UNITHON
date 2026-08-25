# UNWORK 학습 실행 Agent — 최소 MVP API 명세

`MVP-implementation-plan.md`와 `ERD.md`를 기준으로 한 단일 Golden Path 데모용 REST API다. API의 중심 리소스는 `TrainingJob`이며, GPU Pod·비용·artifact는 사용자 API로 노출하지 않는다.

## 1. 공통 규약

- Base URL: `/api/v1`
- Content-Type: `application/json`
- 모든 ID: UUID 문자열
- 모든 시간: ISO 8601 UTC
- MVP 실행 Provider: 팀 Runpod 계정의 단일 GPU Pod
- 웹 사용자는 로그인 없이 익명 세션으로 Job을 분리한다.
- 팀 Runpod API 키는 서버 환경변수 또는 Secret Vault에서만 읽는다. 클라이언트·DB·응답에는 노출하지 않는다.

### 익명 세션

### `POST /session`

익명 세션을 만들거나 갱신한다. 서버는 임의 토큰을 `HttpOnly`, `Secure`, `SameSite=Lax` 쿠키로 설정하고 DB에는 토큰 해시만 저장한다. 세션은 7일 동안 유효하다.

Request body: 없음

Response: `201 Created`

```json
{
  "expiresAt": "2026-09-01T12:00:00Z"
}
```

### 공통 오류 응답

```json
{
  "error": {
    "code": "DEMO_BUSY",
    "message": "다른 데모 실행이 진행 중입니다. 잠시 후 다시 시도해 주세요."
  }
}
```

| HTTP | 코드 | 의미 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 요청 형식 오류 |
| 401 | `SESSION_REQUIRED`, `SESSION_EXPIRED` | 세션 쿠키 없음 또는 만료 |
| 404 | `JOB_NOT_FOUND` | Job이 없거나 현재 세션의 Job이 아님 |
| 409 | `INVALID_JOB_STATE`, `DEMO_BUSY`, `EXECUTION_ALREADY_USED` | 현재 상태에서 실행·취소할 수 없거나 실행 제한에 도달 |
| 503 | `RUNPOD_UNAVAILABLE` | Pod 생성 또는 상태 확인 실패 |

## 2. 핵심 리소스

### TrainingJob

```json
{
  "id": "job_uuid",
  "scenario": {
    "name": "Stable Diffusion 1.5 LoRA",
    "repositoryUrl": "https://github.com/example/golden-path",
    "executionCommand": "./run-demo-training.sh",
    "gpuType": "NVIDIA RTX 4090",
    "maxRuntimeMinutes": 10
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

`scenario`의 값은 읽기 전용이다. 사용자는 Repository, 실행 명령, GPU, 최대 실행시간을 바꿀 수 없다.

### Job 상태

`DRAFT → PROVISIONING → RUNNING → TERMINATING → COMPLETED | FAILED | CANCELLED`

`COMPLETED`는 학습 성공 callback, 종료 코드 `0`, Pod 종료 확인이 모두 끝났을 때만 표시한다.

## 3. Job 생성·조회·실행

### `POST /jobs`

고정 Golden Path Job을 생성한다. Pod를 만들지 않으며 비용도 발생하지 않는다.

Request body: 없음

Response: `201 Created` — `TrainingJob` (`status: DRAFT`)

### `GET /jobs/{jobId}`

현재 세션이 소유한 Job의 상태를 반환한다. 프런트엔드는 실행 중일 때 2~3초 간격으로 이 API를 폴링한다.

Response: `200 OK` — `TrainingJob`

### `POST /jobs/{jobId}/start`

고정 실행 계획을 승인하고 실제 Pod 생성을 시작한다.

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
2. 세션의 `execution_used`가 `false`여야 한다. Pod 생성을 시작하면 `true`로 변경한다.
3. 서비스 전체에 `PROVISIONING`, `RUNNING`, `TERMINATING` Job이 있으면 `409 DEMO_BUSY`를 반환한다. 대기열은 제공하지 않는다.
4. 서버는 팀 Runpod 키로 사전 검증된 이미지·단일 GPU·최대 10분 설정의 Pod를 생성한다.

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
2. 학습 컨테이너는 사전 검증된 이미지와 고정 명령으로 실행된다. 최대 10분 timeout을 넘기면 학습을 중단한다.
3. 성공, 실패, 취소, timeout의 모든 경로에서 Pod 삭제를 요청하고 Runpod 상태 조회로 종료를 확인한다.
4. Pod 생성 실패, 학습 오류, timeout은 재시도 없이 `FAILED`와 짧은 원인 메시지로 표시한다.
5. 성공 화면에는 `Training completed` 로그, 종료 코드, 실행 시간, GPU 정보, Pod 자동 종료 완료를 표시한다.
6. MVP는 artifact 저장·다운로드, 사용자 API 키 연결, GPU 비교, 비용 계산·가드레일, OOM 재계획을 제공하지 않는다.
