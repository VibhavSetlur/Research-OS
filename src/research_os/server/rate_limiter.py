"""Per-client rate limiter for the MCP dispatcher."""
from __future__ import annotations

import logging
import time
from collections import defaultdict


logger = logging.getLogger("research-os.server")


class RateLimiter:
    def __init__(self, max_calls: int = 200, window_seconds: int = 60) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_id: str = "default") -> bool:
        now = time.time()
        self.calls[client_id] = [
            t for t in self.calls[client_id] if now - t < self.window_seconds
        ]
        if len(self.calls[client_id]) >= self.max_calls:
            logger.warning(f"Rate limit exceeded for {client_id}")
            return False
        self.calls[client_id].append(now)
        return True


_rate_limiter = RateLimiter()
