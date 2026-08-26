"""완료 결과를 백엔드에 한 번 전달한다.

백엔드 계약(API-spec.md의 내부 완료 callback):

    POST {UNWORK_COMPLETION_URL}
    { "outcome": "SUCCEEDED" | "FAILED", "exitCode": <int>, "message": <1~500자> }

계약을 벗어난 본문은 백엔드가 400으로 거절한다. 추가 필드도 허용되지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

MESSAGE_MAX_LENGTH = 500
ATTEMPTS = 4
BACKOFF_SECONDS = 3
TIMEOUT_SECONDS = 15


def build_message(log_path: str | None, exit_code: int) -> str:
    """완료 화면에 그대로 보이는 짧은 메시지를 만든다."""

    tail = ""
    if log_path and os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as log:
                lines = [line.strip() for line in log.readlines() if line.strip()]
            tail = " / ".join(lines[-5:])
        except OSError:
            tail = ""

    if exit_code == 0:
        message = tail or "Training completed"
    else:
        message = f"학습이 실패했습니다. 종료 코드 {exit_code}."
        if tail:
            message = f"{message} {tail}"

    message = message.replace("\n", " ").strip() or "Training finished"
    if len(message) > MESSAGE_MAX_LENGTH:
        # 뒤쪽 로그가 원인에 가까우므로 앞을 자른다.
        message = "…" + message[-(MESSAGE_MAX_LENGTH - 1):]
    return message


def send(url: str, payload: dict) -> int:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--log-file", default=None)
    parser.add_argument("--url", default=os.getenv("UNWORK_COMPLETION_URL", ""))
    args = parser.parse_args(argv)

    if not args.url:
        # 주소가 없으면 알릴 방법이 없다. 백엔드는 최대 실행시간이 지나면
        # 실패로 처리하고 GPU를 종료하므로 자원이 남지는 않는다.
        print("UNWORK_COMPLETION_URL이 없어 완료 결과를 전달하지 못했습니다.", file=sys.stderr)
        return 1

    payload = {
        "outcome": "SUCCEEDED" if args.exit_code == 0 else "FAILED",
        "exitCode": args.exit_code,
        "message": build_message(args.log_file, args.exit_code),
    }

    for attempt in range(1, ATTEMPTS + 1):
        try:
            status = send(args.url, payload)
        except Exception as exc:  # noqa: BLE001 - 마지막 한 번의 네트워크 시도
            print(f"완료 전달 실패({attempt}/{ATTEMPTS}): {type(exc).__name__}", file=sys.stderr)
            status = None

        if status is not None:
            print(f"완료 전달 응답: HTTP {status}")
            # 2xx는 성공. 4xx는 다시 보내도 결과가 같으므로 재시도하지 않는다.
            if 200 <= status < 300:
                return 0
            if 400 <= status < 500:
                return 1

        if attempt < ATTEMPTS:
            time.sleep(BACKOFF_SECONDS * attempt)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
