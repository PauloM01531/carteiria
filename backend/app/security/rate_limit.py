"""Limitação de tentativas em memória (janela deslizante).

Suficiente para uma única instância do servidor. Com várias instâncias, troque
por um armazenamento compartilhado (ex.: Redis) mantendo a mesma interface.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        """Registra uma tentativa. Retorna False se o limite foi excedido."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_seconds:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def enforce(key: str, limit: int, window_seconds: int) -> None:
    if not limiter.hit(key, limit, window_seconds):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Muitas tentativas. Aguarde alguns minutos e tente novamente.",
        )
