"""권한을 맞춘 뒤 권한을 내려놓고 서버를 실행한다.

배포 플랫폼은 지속 볼륨을 root 소유 bind mount 로 붙인다. 이미지 안에서 미리
만들어 둔 디렉터리의 소유권은 그 마운트에 덮여 사라지므로, 컨테이너가 비-root
사용자로 시작하면 SQLite 파일을 만들지 못하고 모든 요청이 500이 된다.

그래서 root 로 시작해 데이터 디렉터리 소유권만 정리하고, 곧바로 권한을 내려놓은
뒤 서버를 실행한다. 서버 프로세스 자체는 root 로 돌지 않는다.
"""

from __future__ import annotations

import os
import pwd
import sys

APP_USER = "unwork"
DEFAULT_PORT = "8080"


def prepare_data_directory(path: str) -> None:
    directory = os.path.dirname(path) or "."
    user = pwd.getpwnam(APP_USER)
    os.makedirs(directory, exist_ok=True)
    os.chown(directory, user.pw_uid, user.pw_gid)
    for name in os.listdir(directory):
        try:
            os.chown(os.path.join(directory, name), user.pw_uid, user.pw_gid)
        except OSError as error:  # 남의 파일이 섞여 있어도 기동을 막지는 않는다
            print(f"소유권을 바꾸지 못했습니다: {name} ({error})", file=sys.stderr)


def drop_privileges() -> None:
    user = pwd.getpwnam(APP_USER)
    os.setgid(user.pw_gid)
    os.setgroups([user.pw_gid])
    os.setuid(user.pw_uid)


def main() -> None:
    database_path = os.environ.get("MVP_DATABASE_PATH", "/data/mvp.sqlite3")

    if os.geteuid() == 0:
        prepare_data_directory(database_path)
        drop_privileges()

    port = os.environ.get("PORT", DEFAULT_PORT)
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "training_cost_optimizer.api:app",
            "--host",
            "0.0.0.0",
            "--port",
            port,
            "--workers",
            "1",
        ],
    )


if __name__ == "__main__":
    main()
