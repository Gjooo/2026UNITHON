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

## 홈서버 운영 (선택한 방식)

백엔드는 홈서버에서 돌린다. 부스에서 로그를 그대로 볼 수 있고, 데모 중 외부 플랫폼 장애에 영향을 받지 않는다.

```bash
cd ai-training-cost-optimizer
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

`compose.yaml`은 인스턴스 1개, 재시작 유지(`unless-stopped`), `/data` 볼륨을 전제로 한다. 서버가 재부팅돼도 컨테이너가 다시 뜨고 작업 기록이 남는다.

### 반드시 필요한 것: 공개 HTTPS 주소

홈서버는 공유기 뒤에 있어 Runpod에서 닿지 않는다. 학습이 끝났을 때 Runpod 컨테이너가 결과를 알릴 **공개 HTTPS 주소**가 필요하다. 이것이 없으면 모든 작업이 최대 실행시간까지 기다렸다가 실패로 끝난다.

포트 포워딩은 권하지 않는다. 국내 가정용 회선은 80·443이 막힌 경우가 많고, 홈서버를 인터넷 전체에 직접 여는 셈이 된다. 터널을 쓰면 공유기 설정 없이 바깥에서 들어오는 길만 열린다.

**Cloudflare Tunnel** — 즉시 쓸 수 있는 임시 주소

```bash
brew install cloudflared
cloudflared tunnel --url http://127.0.0.1:8000
# → https://<임의단어>.trycloudflare.com
```

계정도 도메인도 필요 없다. 다만 재시작하면 주소가 바뀌므로, 바뀔 때마다 `BACKEND_PUBLIC_BASE_URL`을 갱신하고 백엔드를 다시 띄워야 한다. 검증과 리허설에는 이걸로 충분하다.

도메인이 있다면 named tunnel로 고정 주소를 만들 수 있다. 데모 당일에는 주소가 바뀌지 않는 편이 안전하다.

**Tailscale Funnel** — 계정만 있으면 고정 주소

```bash
tailscale funnel 8000
# → https://<기기이름>.<tailnet>.ts.net
```

도메인 없이도 주소가 고정된다. 홈서버가 항상 켜져 있다면 이쪽이 관리가 편하다.

### 주소를 얻은 뒤

```bash
export BACKEND_PUBLIC_BASE_URL=https://<터널 주소>
docker compose up -d
```

바깥에서 callback 경로가 실제로 닿는지 확인한다. 이 확인 없이 실제 실행으로 넘어가면 안 된다.

```bash
curl -i -X POST $BACKEND_PUBLIC_BASE_URL/api/v1/internal/jobs/none/completion \
  -H "Content-Type: application/json" \
  -d '{"outcome":"SUCCEEDED","exitCode":0,"message":"reachability check"}'
```

`404 JOB_NOT_FOUND`가 오면 성공이다. 요청이 홈서버까지 도달했다는 뜻이다. 타임아웃이나 502면 터널이 끊긴 것이다.

### 실제 모드로 전환

```bash
export RUNPOD_API_KEY=<키> MVP_PROVIDER_MODE=runpod
docker compose up -d
docker compose logs -f
```

로그에 `provider_mode=runpod`이 보이면 정상이다. 키가 없거나 주소가 HTTPS가 아니면 컨테이너가 기동 단계에서 죽는다. 첫 요청까지 기다리지 않는다.

```bash
docker compose exec backend python -m training_cost_optimizer.mvp.smoke --check-env
```

### 홈서버 점검

- [ ] 터널 주소로 `/health`가 200을 반환한다
- [ ] callback 경로가 바깥에서 닿는다 (`404 JOB_NOT_FOUND`)
- [ ] 컨테이너가 `unless-stopped`로 떠 있고 재부팅 후에도 살아난다
- [ ] 데모 중 홈서버가 절전으로 잠들지 않는다
- [ ] 데모 당일 주소가 바뀌지 않는다 (임시 터널이면 그날 다시 확인)

## Fly.io 절차 (쓰지 않는 경우 무시)

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

## Railway (프런트엔드 연동용)

프런트엔드가 항상 붙어 있을 수 있는 주소가 필요해 Railway에 올린다. **실제 GPU를 쓰는 실행은 여기서 하지 않는다.** `MVP_PROVIDER_MODE=fake`로 두면 GPU가 만들어지지 않으므로 크레딧이 끊겨도 잃을 것이 없다. 실제 GPU 시연은 맥북 + 터널로 한다.

`railway.json`이 Dockerfile 빌드, `/health` 헬스체크, replica 1개를 지정한다. 웹 UI에서 할 일은 다음뿐이다.

1. **New Project → Deploy from GitHub repo** → `2026UNITHON` 선택
2. 서비스 **Settings**
   - Root Directory: `ai-training-cost-optimizer`
   - Branch: `backend`
   - Serverless(App Sleeping)가 꺼져 있는지 확인한다. 잠들면 실행 중 작업을 아무도 종료하지 못한다
3. **Variables**

   ```text
   MVP_PROVIDER_MODE=fake
   MVP_DATABASE_PATH=/data/mvp.sqlite3
   MVP_MAX_RUNTIME_MINUTES=10
   FRONTEND_ORIGINS=<프런트엔드 배포 origin>
   ```

   `RUNPOD_API_KEY`와 `BACKEND_PUBLIC_BASE_URL`은 넣지 않는다. fake 모드에서는 쓰이지 않는다.
4. **Volume** 생성 후 마운트 경로를 `/data`로 지정
5. **Settings → Networking → Generate Domain**으로 공개 주소 발급

### Free 요금제로 충분한가

실측 기준 이 서비스의 유휴 사용량은 메모리 62MB, CPU 0.3%다. Railway 요율(RAM $10/GB·월, CPU $20/vCPU·월, 볼륨 $0.15/GB·월)로 환산하면 월 $0.75 안팎이라 Free의 월 $1 크레딧 안에 들어온다. Free 상한인 replica 1개, 메모리 0.5GB, 볼륨 0.5GB도 모두 만족한다.

폴링이 계속 붙어 CPU가 3%까지 오르면 월 $1.2가 되어 크레딧을 넘길 수 있다. 넘기면 서비스가 멈추고 청구되지는 않는다. fake 모드로만 쓰는 한 이것이 유일한 영향이다.

### 배포 확인

```bash
curl -i https://<발급받은 주소>/health
curl -i -X POST https://<발급받은 주소>/api/v1/session
```

`Set-Cookie`에 `HttpOnly`와 `Secure`가 함께 있어야 한다. 프런트엔드는 이 주소를 `VITE_API_BASE_URL`로 쓰거나, 자신의 배포 도메인에서 `/api`를 이 주소로 프록시한다.

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
