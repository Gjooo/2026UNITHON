# 배포 절차

이 백엔드는 실행 중인 학습의 상태·최대 실행시간·GPU 종료를 **프로세스 안에서** 책임진다. 배포 환경은 그래서 세 가지를 반드시 만족해야 한다.

1. **인스턴스 1개, worker 1개.** 두 개가 뜨면 같은 작업을 두 프로세스가 관리하고 GPU가 두 개 생길 수 있다.
2. **잠들지 않는다.** 유휴 시 자동 정지되는 플랜은 쓸 수 없다. 프로세스가 멈춘 사이 GPU는 계속 과금된다.
3. **지속 볼륨.** SQLite 파일이 재배포·재시작에도 남아야 한다.

이 세 가지 때문에 무료 sleep 플랜(예: Render 무료 웹 서비스)은 적합하지 않다.

## 컨테이너

`Dockerfile`은 위 조건에 맞춰져 있다. 로컬에서 그대로 확인할 수 있다.

```bash
docker build -t unwork-backend .
docker volume create unwork-data
docker run -d --name unwork -p 8080:8080 -v unwork-data:/data unwork-backend
curl http://127.0.0.1:8080/health
```

검증한 것: 이미지 228MB, 컨테이너에서 세션 → 추천 → 승인 → 실행 → 완료 흐름이 끝까지 동작하고, 컨테이너를 재시작해도 볼륨의 세션·작업이 남는다.

## Fly.io 절차

`fly.toml`이 인스턴스 1개·자동 정지 없음·`/data` 볼륨으로 설정돼 있다.

```bash
fly launch --no-deploy --copy-config --name unwork-agent
fly volumes create unwork_data --size 1 --region nrt
fly deploy
fly scale count 1                      # 인스턴스가 1개인지 확인
fly status
```

배포가 끝나면 공개 주소는 `https://unwork-agent.fly.dev`다.

### 1단계 — fake 모드로 주소부터 확인

`fly.toml`의 기본값이 `MVP_PROVIDER_MODE=fake`라 첫 배포는 GPU를 만들지 않는다. 이 상태에서 공개 주소가 바깥에서 열리는지 확인한다.

```bash
curl -i https://unwork-agent.fly.dev/health
curl -i -X POST https://unwork-agent.fly.dev/api/v1/session
```

`Set-Cookie`에 `Secure`가 붙어 있어야 한다. 붙지 않으면 `MVP_COOKIE_SECURE`가 잘못 설정된 것이다.

**callback 주소가 바깥에서 실제로 닿는지** 반드시 확인한다. Runpod 컨테이너가 이 주소로 완료를 알린다.

```bash
curl -i -X POST https://unwork-agent.fly.dev/api/v1/internal/jobs/none/completion \
  -H "Content-Type: application/json" \
  -d '{"outcome":"SUCCEEDED","exitCode":0,"message":"reachability check"}'
```

`404 JOB_NOT_FOUND`가 오면 성공이다. 요청이 서버까지 도달했다는 뜻이다. 타임아웃이나 502면 주소가 막혀 있는 것이므로 실제 실행으로 넘어가면 안 된다.

### 2단계 — secret 주입 후 실제 모드로 전환

```bash
fly secrets set RUNPOD_API_KEY=<키> \
                BACKEND_PUBLIC_BASE_URL=https://unwork-agent.fly.dev \
                FRONTEND_ORIGINS=https://<프런트엔드 도메인>
```

그다음 `fly.toml`의 `MVP_PROVIDER_MODE`를 `"runpod"`으로 바꾸고 다시 배포한다.

```bash
fly deploy
fly logs
```

로그에 `MVP configuration: provider_mode=runpod max_runtime_minutes=10`이 보이면 정상이다. 키가 없거나 callback 주소가 HTTPS가 아니면 **서버가 기동 단계에서 실패한다.** 첫 사용자 요청까지 기다리지 않는다.

### 3단계 — 실제 GPU 검증

```bash
fly ssh console -C "python -m training_cost_optimizer.mvp.smoke --check-env"
```

GPU를 만들지 않고 설정과 GPU 프로필 유효성만 검사한다. 통과하면 실제 Pod 생성 검증으로 넘어간다 (여기서부터 과금).

```bash
fly ssh console -C "python -m training_cost_optimizer.mvp.smoke --confirm RUNPOD --profile runpod-rtx4090-v1"
```

## Railway를 쓸 경우

Fly보다 단계가 적다. 다음만 지키면 된다.

1. 저장소를 연결하고 `ai-training-cost-optimizer`를 루트로 지정한다 (Dockerfile 자동 인식).
2. Volume을 만들어 `/data`에 마운트한다.
3. Replicas를 1로 고정한다.
4. Variables에 `MVP_PROVIDER_MODE`, `RUNPOD_API_KEY`, `BACKEND_PUBLIC_BASE_URL`, `FRONTEND_ORIGINS`를 넣는다.
5. 공개 도메인을 발급받아 `BACKEND_PUBLIC_BASE_URL`에 그 주소를 넣는다.

검증 절차(1~3단계)는 Fly와 동일하다.

## 환경변수

| 변수 | 배포 값 |
| --- | --- |
| `MVP_PROVIDER_MODE` | 검증 전 `fake`, 실제 실행은 `runpod` |
| `RUNPOD_API_KEY` | secret으로만 주입. 변수 목록에 평문으로 두지 않는다 |
| `BACKEND_PUBLIC_BASE_URL` | 배포된 공개 HTTPS 주소. Runpod 컨테이너가 이 주소로 완료를 알린다 |
| `MVP_DATABASE_PATH` | `/data/mvp.sqlite3` (볼륨 안) |
| `FRONTEND_ORIGINS` | 실제 프런트엔드 origin. wildcard는 무시된다 |
| `MVP_MAX_RUNTIME_MINUTES` | 10 |
| `MVP_COOKIE_SECURE` | 설정하지 않는다 (기본 `true`). 로컬 HTTP 개발에서만 `false` |

## 배포 후 점검

- [ ] `/health`가 200을 반환한다
- [ ] `POST /api/v1/session`의 `Set-Cookie`에 `HttpOnly`와 `Secure`가 있다
- [ ] callback 경로가 바깥에서 닿는다 (`404 JOB_NOT_FOUND` 확인)
- [ ] 인스턴스가 1개다
- [ ] 로그에 API 키와 GPU type ID가 없다
- [ ] `--check-env`가 통과한다
- [ ] 리허설이 끝난 뒤 Runpod 콘솔에 남은 Pod가 없다
