# 학습 컨테이너

백엔드가 선택한 GPU에서 실행되는 컨테이너다. 하는 일은 두 가지다.

1. 고정된 SD 1.5 LoRA 학습을 수행한다.
2. **어떤 경로로 끝나든** 완료 결과를 백엔드에 정확히 한 번 알린다.

두 번째가 이 컨테이너의 핵심 책임이다. 결과가 오지 않으면 백엔드는 최대 실행시간까지 기다린 뒤 실패로 처리하고 GPU를 종료하므로 자원이 남지는 않지만, 사용자는 이유를 알 수 없는 실패를 보게 된다.

## 구성

| 파일 | 역할 |
| --- | --- |
| `run-demo-training.sh` | 백엔드가 호출하는 진입점. 학습을 실행하고 종료 코드를 보존해 결과를 전달한다 |
| `report_completion.py` | 백엔드 완료 callback 계약을 지키는 전송기 |
| `train_sd15_lora.py` | SD 1.5 UNet에 LoRA를 짧게 학습한다 |
| `Dockerfile` | CUDA 런타임 + 고정 의존성 + 모델 가중치 사전 다운로드 |

## 검증 상태

**검증됨** — 실제 백엔드(`/api/v1`)를 상대로 확인했다.

| 확인한 것 | 결과 |
| --- | --- |
| 학습 성공 → 작업이 완료로 바뀜 | `COMPLETED`, exit 0, 로그 전달 |
| 학습 실패(exit 3) → 실패로 바뀜 | `FAILED`, exitCode 3 보존 |
| 학습이 신호로 죽음 | 결과가 그래도 전달됨, `FAILED` |
| 로그가 길 때 | 메시지를 500자로 자름 (백엔드 상한) |
| 없는 작업에 전달 | HTTP 404 받고 0.5초 만에 포기, 재시도 폭주 없음 |
| 백엔드가 닿지 않을 때 | 4회 재시도 후 18초 만에 포기, 매달리지 않음 |

**아직 검증되지 않음** — GPU가 필요하다.

- `train_sd15_lora.py`가 실제 GPU에서 도는지, 10분 안에 끝나는지
- 이미지 빌드(모델 가중치 사전 다운로드 포함)와 크기
- Runpod에서 이 이미지로 Pod가 뜨는지

## GPU 없이 왕복부터 확인하는 법

학습 스크립트가 검증되기 전에도 백엔드 ↔ 컨테이너 왕복은 확인할 수 있다. `TRAINING_COMMAND`를 넘기면 학습 대신 그 명령이 실행된다.

```bash
TRAINING_COMMAND="echo 'step 200/200 loss=0.13'" \
  ./run-demo-training.sh --completion-url "https://<배포주소>/api/v1/internal/jobs/<jobId>/completion"
```

실제 GPU에서 컨테이너 생성·삭제만 먼저 확인하고 싶다면 Runpod Pod의 실행 명령을 `TRAINING_COMMAND="sleep 60"`으로 두고 한 번 돌린다. 학습이 되는지와 무관하게 생성 → 실행 → 완료 전달 → 삭제 경로가 증명된다.

## 빌드와 배포

이미지 이름은 백엔드 프로필 상수(`mvp/config.py`의 `image_name`)와 같아야 한다. 현재 값은 `unwork/sd15-lora:1`이다.

```bash
docker build -t <레지스트리>/unwork-sd15-lora:1 .
docker push <레지스트리>/unwork-sd15-lora:1
```

빌드는 CUDA 베이스 이미지와 SD 1.5 가중치를 포함해 수 GB가 된다. 푸시한 뒤 백엔드의 `image_name`을 실제 태그로 바꾼다. 비공개 레지스트리를 쓰면 Runpod에 registry 자격증명을 등록해야 한다.

## 백엔드와의 계약

백엔드는 Pod를 만들 때 다음을 넘긴다.

- 환경변수 `UNWORK_COMPLETION_URL` — 이 작업 전용 완료 주소
- 실행 명령 `./run-demo-training.sh --completion-url "$UNWORK_COMPLETION_URL"`

컨테이너가 보내는 본문은 이 형태여야 한다. 추가 필드가 있으면 백엔드가 400으로 거절한다.

```json
{ "outcome": "SUCCEEDED", "exitCode": 0, "message": "Training completed" }
```

`message`는 1~500자이며 완료 화면에 그대로 보인다. 자격증명이나 내부 경로를 담지 않는다.

callback은 작업이 실행 중일 때 **한 번만** 유효하다. 두 번째 전달은 409로 거절되며, 이는 정상 동작이다.
