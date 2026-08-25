# 실행 상태와 Pod 종료 책임이 프로세스 안에 있으므로, 이 이미지는 반드시
# 단일 worker · 단일 인스턴스로 실행한다. 수평 확장은 MVP 범위 밖이다.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY training_cost_optimizer ./training_cost_optimizer
RUN pip install --no-cache-dir .

# SQLite 파일은 컨테이너 재시작에도 남아야 하므로 지속 볼륨 마운트 지점에 둔다.
# 배포 플랫폼에서 /data 를 볼륨으로 마운트한다.
ENV MVP_DATABASE_PATH=/data/mvp.sqlite3 \
    MVP_PROVIDER_MODE=fake \
    MVP_MAX_RUNTIME_MINUTES=10 \
    PORT=8080

RUN useradd --system --uid 10001 unwork && mkdir -p /data && chown unwork /data
USER unwork

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health',timeout=3)"

CMD ["sh", "-c", "exec uvicorn training_cost_optimizer.api:app --host 0.0.0.0 --port ${PORT} --workers 1"]
