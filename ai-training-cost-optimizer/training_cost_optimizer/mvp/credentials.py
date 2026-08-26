"""세션에 묶인 Provider 자격증명을 메모리에만 보관한다.

사용자가 입력한 Runpod 키는 그 계정 전체에 대한 권한이다. 그래서 두 가지를
지킨다.

1. **디스크에 쓰지 않는다.** 프로세스가 끝나면 사라진다. 재배포하면 사용자가
   다시 입력해야 하지만, 남의 키를 볼륨에 평문으로 남기지 않는 편이 낫다.
2. **돌려주지 않는다.** 마스킹한 형태로도 응답에 넣지 않는다. 화면은 연결
   여부만 알면 된다.

요청 스레드와 백그라운드 Worker 가 같이 접근하므로 잠금으로 보호한다.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime

from .domain import utc_now


@dataclass(frozen=True)
class ProviderConnection:
    """화면에 보여도 되는 연결 정보. 키 자체는 담지 않는다."""

    provider_id: str
    connected_at: datetime


class SessionCredentialStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._keys: dict[tuple[str, str], str] = {}
        self._connected_at: dict[tuple[str, str], datetime] = {}

    def save(self, *, session_id: str, provider_id: str, api_key: str) -> ProviderConnection:
        key = (session_id, provider_id)
        connected_at = utc_now()
        with self._lock:
            self._keys[key] = api_key
            self._connected_at[key] = connected_at
        return ProviderConnection(provider_id=provider_id, connected_at=connected_at)

    def api_key(self, *, session_id: str, provider_id: str) -> str | None:
        with self._lock:
            return self._keys.get((session_id, provider_id))

    def connection(self, *, session_id: str, provider_id: str) -> ProviderConnection | None:
        with self._lock:
            connected_at = self._connected_at.get((session_id, provider_id))
        if connected_at is None:
            return None
        return ProviderConnection(provider_id=provider_id, connected_at=connected_at)

    def discard(self, *, session_id: str, provider_id: str) -> bool:
        key = (session_id, provider_id)
        with self._lock:
            self._connected_at.pop(key, None)
            return self._keys.pop(key, None) is not None
