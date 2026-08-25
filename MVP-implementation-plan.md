# UNWORK 학습 실행 Agent — MVP 구현 계획서

## 1. 구현 목표

해커톤 데모에서 다음을 실제로 증명한다.

> 사용자는 GPU 공급자 콘솔, SSH, CUDA 설정, Pod 종료를 직접 조작하지 않고 학습 실행을 시작하고 종료할 수 있다.

제품 PRD의 전체 기능을 구현하지 않는다. 사전 검증한 학습 작업 하나를 실제 Runpod Pod에서 실행하고, 상태를 보여 주며, 종료를 확인하는 데 집중한다.

## 2. 데모 Golden Path

| 항목 | 고정값 |
| --- | --- |
| 학습 작업 | SD 1.5 LoRA fine-tuning |
| 코드·명령 | 사전 검증된 Repository와 고정 실행 명령 |
| 실행 환경 | 사전 검증된 Docker/Runpod 템플릿 이미지 |
| GPU | 단일 사전 선택 GPU |
| 공급자 | 팀 Runpod 계정 |
| 최대 실행시간 | 10분 |
| 결과물 | artifact 전달 없이 성공 로그·종료 코드·실행 시간·GPU 정보 표시 |

사용자는 Repository, 실행 명령, GPU, Provider, 예산을 수정하지 않는다. 화면에서 읽기 전용 실행 계획을 확인하고 `실행 승인`만 한다.

## 3. 사용자 흐름

```text
익명 세션 생성
→ Golden Path 실행 계획 확인
→ 실행 승인
→ Pod 생성 중
→ 학습 실행 중
→ 성공 또는 실패 표시
→ Pod 자동 종료 확인
```

- 실행 중 프런트엔드는 2~3초마다 Job 상태를 폴링한다.
- 사용자는 `실행 중단`을 누를 수 있다.
- 다른 Job이 실행 중이면 대기열 없이 `다른 데모 실행 중`을 표시한다.
- 세션당 실제 실행은 1회만 허용한다. 서비스 전체 동시 실행도 1개다.

## 4. 구현 구조

```text
Web frontend
  └─ REST API (익명 세션·Job 생성·시작·조회·취소)
       └─ Long-running backend worker
            ├─ Runpod Pod 생성·상태 조회·삭제
            ├─ 10분 timeout 감시
            └─ Job 상태 저장

Runpod Pod
  └─ 고정 학습 스크립트 실행
       └─ 완료/실패 callback → Backend
```

### 책임 분리

| 구성요소 | 책임 |
| --- | --- |
| 프런트엔드 | 실행 계획 표시, 승인·취소 요청, Job 상태 폴링 |
| 백엔드 Worker | Pod 생애주기, timeout, callback 처리, 종료 확인 |
| Runpod Pod | 고정 학습 스크립트 실행, 성공/실패와 종료 코드 callback |

브라우저를 닫아도 백엔드 Worker는 Pod 상태와 종료를 계속 관리한다.

## 5. 상태와 처리 정책

```text
DRAFT → PROVISIONING → RUNNING → TERMINATING → COMPLETED
                                  ↘ FAILED
                                  ↘ CANCELLED
```

- 학습 성공 callback과 종료 코드 `0`을 받으면 `TERMINATING`으로 전환한다.
- 실패 callback, Pod 생성 실패, 학습 명령 오류, 10분 timeout은 모두 짧은 원인 메시지와 함께 `FAILED` 처리한다.
- 사용자 취소는 `CANCELLED` 처리한다.
- 성공·실패·취소·timeout의 모든 경로에서 Pod 삭제를 요청한다.
- Runpod 상태 조회로 Pod 종료를 확인하기 전에는 최종 상태를 표시하지 않는다.
- 재시도, OOM 재계획, checkpoint 복구는 구현하지 않는다.

## 6. API·데이터 구현 기준

- API: [API-spec.md](API-spec.md)
- 데이터 모델: [ERD.md](ERD.md)

구현할 사용자 API는 아래 다섯 개다.

| API | 용도 |
| --- | --- |
| `POST /api/v1/session` | 익명 세션 생성 |
| `POST /api/v1/jobs` | 고정 Golden Path Job 생성 |
| `GET /api/v1/jobs/{jobId}` | Job 상태 조회 |
| `POST /api/v1/jobs/{jobId}/start` | 실행 승인과 Pod 생성 시작 |
| `POST /api/v1/jobs/{jobId}/cancel` | 실행 중단과 Pod 종료 시작 |

Pod만 호출하는 내부 API:

| API | 용도 |
| --- | --- |
| `POST /api/v1/internal/jobs/{jobId}/completion` | 성공/실패, 종료 코드, 짧은 메시지 callback |

## 7. 비밀값과 실행 제한

- 팀 Runpod API 키는 서버 환경변수 또는 Secret Vault에서만 읽는다.
- 클라이언트와 DB에는 Runpod API 키를 저장하거나 반환하지 않는다.
- 로그인·비밀번호 없이 익명 세션으로 Job 소유권을 분리한다.
- 세션당 한 번만 실제 실행하고, 전체 서비스에서 활성 Job은 하나만 허용한다.

## 8. 명시적 제외 범위

- 임의 Repository와 실행 명령 입력·분석
- 사용자 GPU 공급자 API 키 연결(BYOK)
- GPU 후보 비교, 다중 Provider, 동적 추천
- 예산 입력, 비용 계산, 비용 가드레일
- artifact 저장·전달·다운로드
- 실시간 로그 뷰어, 모델 결과 이미지 렌더링
- OOM 재계획, 자동 재시도, checkpoint 복구, 실행 대기열
- 계정 로그인, 팀 기능, 결제·정산

## 9. 데모 완료 기준

다음이 실제로 동작하면 데모 구현을 완료한 것으로 본다.

1. 웹에서 Golden Path 실행 계획을 확인하고 승인할 수 있다.
2. 팀 Runpod 계정에서 실제 Pod가 생성된다.
3. 사전 검증된 학습 스크립트가 Pod에서 실행되고 성공 또는 실패 callback을 보낸다.
4. 웹 화면이 폴링으로 `PROVISIONING`, `RUNNING`, 최종 상태를 표시한다.
5. 정상 실행 시 완료 로그, 종료 코드, 실행 시간, GPU 정보, Pod 종료 확인이 표시된다.
6. 취소·실패·timeout에서도 Pod 삭제가 요청되고 종료 확인 뒤 최종 상태가 표시된다.
7. 사용자는 Runpod 콘솔·SSH·Pod 종료를 직접 조작하지 않는다.
