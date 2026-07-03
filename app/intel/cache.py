from __future__ import annotations

import json
from typing import Any

import redis


class LookupCache:
    def __init__(self, redis_url: str, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._client = None
        if ttl_seconds <= 0:
            return
        try:
            self._client = redis.from_url(
                redis_url,
                socket_connect_timeout=1,
                socket_timeout=1,
                decode_responses=True,
            )
            self._client.ping()
        except Exception:
            self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None and self.ttl_seconds > 0

    def get(self, key: str) -> dict[str, Any] | None:
        if self._client is None:
            return None
        try:
            raw = self._client.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        if self._client is None:
            return
        try:
            self._client.setex(key, self.ttl_seconds, json.dumps(value, separators=(",", ":")))
        except Exception:
            return

    def clear_namespace(self, namespace: str = "ipatlas:lookup:") -> None:
        if self._client is None:
            return
        try:
            for key in self._client.scan_iter(f"{namespace}*"):
                self._client.delete(key)
        except Exception:
            return

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
